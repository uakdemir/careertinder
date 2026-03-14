"""AI client abstraction and Anthropic Claude implementation.

Provides a provider-neutral AIClient protocol with ClaudeClient as the
sole M3 implementation. Handles retry logic, cost estimation, and token tracking.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from anthropic import Anthropic, APIStatusError, AuthenticationError, RateLimitError
from anthropic.types import TextBlock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AIResponse:
    """Parsed response from an AI API call."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class AIClient(Protocol):
    """Provider-neutral interface for AI API calls.

    Concrete implementations: ClaudeClient (M3), OpenAIClient (M4).
    """

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        max_retries: int = 3,
    ) -> AIResponse: ...


# Pricing per 1M tokens (input, output) — updated as needed
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
}


class ClaudeClient:
    """Wrapper for Anthropic Claude API calls.

    Uses the sync Anthropic client wrapped in asyncio.to_thread for async
    compatibility. Retries on rate limits and transient server errors.
    """

    def __init__(self, api_key: str) -> None:
        self._client = Anthropic(api_key=api_key)

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        max_retries: int = 3,
    ) -> AIResponse:
        """Send a message to Claude and return parsed response.

        Retries on RateLimitError and transient APIError (5xx).
        Raises on auth errors, validation errors, or exhausted retries.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    lambda: self._client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=[
                            {
                                "type": "text",
                                "text": system_prompt,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                )

                first_block = response.content[0] if response.content else None
                content = first_block.text if isinstance(first_block, TextBlock) else ""
                if not content:
                    raise ValueError("Empty response from Claude")

                prompt_tokens = response.usage.input_tokens
                completion_tokens = response.usage.output_tokens

                # Log prompt caching stats when available
                cache_created = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
                cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
                if cache_created or cache_read:
                    logger.info(
                        "Claude cache: %d tokens written, %d tokens read (%.0f%% cached)",
                        cache_created,
                        cache_read,
                        (cache_read / max(prompt_tokens, 1)) * 100,
                    )

                cost = self._estimate_cost(
                    model, prompt_tokens, completion_tokens, cache_created, cache_read
                )

                logger.info(
                    "Claude API call: model=%s, tokens=%d+%d, cost=$%.4f",
                    model,
                    prompt_tokens,
                    completion_tokens,
                    cost,
                )

                return AIResponse(
                    content=content,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost,
                )

            except AuthenticationError:
                logger.error("Authentication failed — check ANTHROPIC_API_KEY")
                raise
            except RateLimitError as e:
                last_error = e
                wait = 2**attempt
                logger.warning("Rate limited (attempt %d/%d), waiting %ds", attempt + 1, max_retries, wait)
                await asyncio.sleep(wait)
            except APIStatusError as e:
                if e.status_code >= 500:
                    last_error = e
                    wait = 2**attempt
                    logger.warning(
                        "Server error %d (attempt %d/%d), waiting %ds",
                        e.status_code,
                        attempt + 1,
                        max_retries,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

        raise RuntimeError(f"Exhausted {max_retries} retries for Claude API call") from last_error

    def _estimate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """Estimate USD cost from token counts and model pricing.

        Anthropic prompt caching pricing:
        - Cache writes: 25% more than base input price
        - Cache reads: 90% less than base input price
        - Uncached input: base price
        """
        pricing = MODEL_PRICING.get(model)
        if pricing is None:
            logger.warning("No pricing for model '%s', cost estimated as $0.00", model)
            return 0.0
        input_price, output_price = pricing

        # Tokens not involved in caching
        uncached_tokens = prompt_tokens - cache_creation_tokens - cache_read_tokens
        input_cost = (
            uncached_tokens * input_price
            + cache_creation_tokens * input_price * 1.25  # 25% premium for writes
            + cache_read_tokens * input_price * 0.10  # 90% discount for reads
        ) / 1_000_000
        output_cost = (completion_tokens * output_price) / 1_000_000
        return round(input_cost + output_cost, 6)
