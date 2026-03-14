"""OpenAI Chat Completions client conforming to AIClient protocol.

Supports service_tier="flex" for cost-optimized content generation.
Mirrors ClaudeClient retry logic and error handling.
"""

import asyncio
import logging

from openai import APIStatusError, AuthenticationError, OpenAI, RateLimitError

from jobhunter.ai.claude_client import AIResponse

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (input, output) — Flex mode rates from M3.5 §15
OPENAI_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5-nano": (0.025, 0.20),
    "gpt-5.2": (0.875, 7.00),
    "gpt-5.4": (1.25, 7.50),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}


class OpenAIClient:
    """Wrapper for OpenAI Chat Completions API.

    Uses the sync OpenAI client wrapped in asyncio.to_thread for async
    compatibility. Supports service_tier="flex" for cost-optimized calls.
    Retry logic mirrors ClaudeClient (exponential backoff on rate limits
    and transient 5xx errors).
    """

    def __init__(self, api_key: str, service_tier: str = "flex") -> None:
        self._client = OpenAI(api_key=api_key)
        self._service_tier = service_tier

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        max_retries: int = 3,
    ) -> AIResponse:
        """Send a chat completion request and return parsed response.

        Retries on RateLimitError and transient APIError (5xx).
        Raises on auth errors, validation errors, or exhausted retries.
        """
        last_error: Exception | None = None

        logger.debug(
            "OpenAI request: model=%s, max_tokens=%d, temperature=%.1f, "
            "service_tier=%s, system_prompt_len=%d, user_prompt_len=%d",
            model, max_tokens, temperature, self._service_tier,
            len(system_prompt), len(user_prompt),
        )

        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    self._create_completion,
                    model,
                    max_tokens,
                    temperature,
                    system_prompt,
                    user_prompt,
                )

                choice = response.choices[0] if response.choices else None
                content = choice.message.content if choice and choice.message else ""
                finish_reason = choice.finish_reason if choice else None

                logger.debug(
                    "OpenAI response: model=%s, finish_reason=%s, "
                    "content_len=%d, choices=%d, content_preview=%.200s",
                    model, finish_reason,
                    len(content) if content else 0,
                    len(response.choices) if response.choices else 0,
                    content[:200] if content else "<empty>",
                )

                if not content:
                    refusal = getattr(choice.message, "refusal", None) if choice and choice.message else None
                    logger.warning(
                        "Empty content from OpenAI: finish_reason=%s, refusal=%s, choices=%d",
                        finish_reason, refusal, len(response.choices) if response.choices else 0,
                    )
                    raise ValueError("Empty response from OpenAI")

                prompt_tokens = response.usage.prompt_tokens if response.usage else 0
                completion_tokens = response.usage.completion_tokens if response.usage else 0

                # Extract cached token count from prompt_tokens_details
                cached_tokens = 0
                if response.usage and hasattr(response.usage, "prompt_tokens_details"):
                    details = response.usage.prompt_tokens_details
                    if details and hasattr(details, "cached_tokens"):
                        cached_tokens = details.cached_tokens or 0

                cost = self._estimate_cost(model, prompt_tokens, completion_tokens, cached_tokens)

                if cached_tokens:
                    logger.info(
                        "OpenAI API call: model=%s, tier=%s, tokens=%d+%d "
                        "(cached=%d, %.0f%%), cost=$%.4f",
                        model,
                        self._service_tier,
                        prompt_tokens,
                        completion_tokens,
                        cached_tokens,
                        (cached_tokens / max(prompt_tokens, 1)) * 100,
                        cost,
                    )
                else:
                    logger.info(
                        "OpenAI API call: model=%s, tier=%s, tokens=%d+%d, cost=$%.4f",
                        model,
                        self._service_tier,
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
                logger.error("Authentication failed — check OPENAI_API_KEY")
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

        raise RuntimeError(f"Exhausted {max_retries} retries for OpenAI API call") from last_error

    # GPT-5 family models are reasoning models that reject custom temperature
    _NO_TEMPERATURE_MODELS = frozenset({"gpt-5-nano", "gpt-5-mini", "gpt-5", "gpt-5.2", "gpt-5.4"})

    def _create_completion(
        self,
        model: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str,
        user_prompt: str,
    ):  # type: ignore[no-untyped-def]
        """Create a chat completion (called via asyncio.to_thread)."""
        kwargs: dict[str, object] = {
            "model": model,
            "max_completion_tokens": max_tokens,
            "service_tier": self._service_tier,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if model not in self._NO_TEMPERATURE_MODELS:
            kwargs["temperature"] = temperature
        return self._client.chat.completions.create(**kwargs)  # type: ignore[call-overload]

    def _estimate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
    ) -> float:
        """Estimate USD cost from token counts and model pricing.

        OpenAI prompt caching: cached input tokens cost 50% of base input price.
        Caching is automatic for prompts ≥1024 tokens with matching prefixes.
        """
        pricing = OPENAI_MODEL_PRICING.get(model)
        if pricing is None:
            logger.warning("No pricing for model '%s', cost estimated as $0.00", model)
            return 0.0
        input_price, output_price = pricing
        uncached_tokens = prompt_tokens - cached_tokens
        input_cost = (
            uncached_tokens * input_price + cached_tokens * input_price * 0.50
        ) / 1_000_000
        output_cost = (completion_tokens * output_price) / 1_000_000
        return round(input_cost + output_cost, 6)
