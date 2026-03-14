import asyncio
import logging
import math
from pathlib import Path

import click

from jobhunter.config.loader import load_config
from jobhunter.config.schema import AppConfig, ConfigurationError, ScrapingConfig, SecretsConfig
from jobhunter.utils.logging_setup import configure_logging

logger = logging.getLogger(__name__)


@click.group()
@click.option("--config", "config_path", default="config.yaml", help="Path to config file")
@click.option("--verbose", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, config_path: str, verbose: bool) -> None:
    """JobHunter - Job Search Automation Platform"""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = Path(config_path)
    ctx.obj["verbose"] = verbose


def _load_config(ctx: click.Context) -> AppConfig:
    """Lazy config loader — called by commands, not the group."""
    if "config" not in ctx.obj:
        configure_logging(verbose=ctx.obj["verbose"])
        try:
            ctx.obj["config"] = load_config(ctx.obj["config_path"])
        except ConfigurationError as e:
            raise click.ClickException(str(e)) from e
    config: AppConfig = ctx.obj["config"]
    return config


def _apply_limit(scraping: ScrapingConfig, limit: int, scraper: str | None) -> ScrapingConfig:
    """Override scraping config with a result limit.

    Apify scrapers (linkedin, wellfound): sets max_results = limit.
    Playwright scrapers (remote_io, remote_rocketship): sets each profile's
    max_pages = ceil(limit / num_profiles), minimum 1.

    Uses model_copy to preserve all existing profile fields regardless of
    profile names or future schema additions.
    """
    updates: dict[str, object] = {}
    targets = [scraper] if scraper else ["linkedin", "wellfound", "remote_io", "remote_rocketship"]

    for name in targets:
        cfg = getattr(scraping, name)
        if name in ("linkedin", "wellfound"):
            updates[name] = cfg.model_copy(update={"max_results": limit})
        elif name in ("remote_io", "remote_rocketship"):
            profiles = cfg.search_profiles
            pages_per = max(1, math.ceil(limit / max(len(profiles), 1)))
            new_profiles = [p.model_copy(update={"max_pages": pages_per}) for p in profiles]
            updates[name] = cfg.model_copy(update={"search_profiles": new_profiles})

    return scraping.model_copy(update=updates)


@cli.command()
@click.option(
    "--scraper",
    type=click.Choice(["remote_io", "remote_rocketship", "wellfound", "linkedin"]),
    default=None,
    help="Run a specific scraper (default: all enabled)",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Max total results (divided across search profiles)",
)
@click.pass_context
def scrape(ctx: click.Context, scraper: str | None, limit: int | None) -> None:
    """Run job scrapers to collect new postings."""
    config = _load_config(ctx)
    secrets = SecretsConfig()

    from jobhunter.db.session import create_engine, get_session
    from jobhunter.db.settings import get_scraping_config
    from jobhunter.scrapers.orchestrator import ScraperOrchestrator, ScraperRunResult

    create_engine(config.database)

    def _print_scraper_result(result: ScraperRunResult) -> None:
        status_icon = "+" if result.status == "success" else "x"
        click.echo(
            f"  {status_icon} {result.scraper_name}: {result.status} "
            f"({result.jobs_found} found, {result.jobs_new} new, "
            f"{result.duration_seconds:.1f}s)"
        )
        if result.error_message:
            click.echo(f"    Error: {result.error_message}")

    async def _run() -> None:
        with get_session() as session:
            # Load scraping config from DB (overrides YAML) — matches
            # the pattern in 8_scraper_runs.py so profile renames,
            # URL changes, etc. made in the dashboard are respected.
            db_scraping = get_scraping_config(session)
            if limit is not None:
                db_scraping = _apply_limit(db_scraping, limit, scraper)
            effective_config = config.model_copy(update={"scraping": db_scraping})
            orchestrator = ScraperOrchestrator(effective_config, secrets, session)
            if scraper:
                result = await orchestrator.run_single(scraper)
                _print_scraper_result(result)
            else:
                orch_result = await orchestrator.run_all()
                for r in orch_result.results:
                    _print_scraper_result(r)
                click.echo(f"\nTotal: {orch_result.total_jobs_found} found, {orch_result.total_jobs_new} new")

    asyncio.run(_run())


@cli.command(name="filter")
@click.option("--force", is_flag=True, help="Re-filter already-filtered jobs")
@click.option("--dry-run", is_flag=True, help="Show what would be filtered without writing")
@click.pass_context
def filter_cmd(ctx: click.Context, force: bool, dry_run: bool) -> None:
    """Apply Tier 1 rule-based filtering to raw job postings."""
    config = _load_config(ctx)

    from jobhunter.db.session import create_engine, get_session
    from jobhunter.db.settings import get_filtering_config
    from jobhunter.filters.service import filter_unprocessed_jobs

    create_engine(config.database)

    with get_session() as session:
        filtering_config = get_filtering_config(session)

        if dry_run:
            click.echo("DRY RUN: No changes will be written to database")

        total, passed, failed, ambiguous = filter_unprocessed_jobs(
            session, filtering_config, force=force, dry_run=dry_run
        )

        click.echo("\nFiltering complete:")
        click.echo(f"  Total processed: {total}")
        click.echo(f"  Passed (tier1_pass): {passed}")
        click.echo(f"  Failed (tier1_fail): {failed}")
        click.echo(f"  Ambiguous (tier1_ambiguous): {ambiguous}")


@cli.command()
@click.option("--tier2-only", is_flag=True, help="Run Tier 2 only (skip Tier 3)")
@click.option("--dry-run", is_flag=True, help="Show what would be evaluated without API calls")
@click.option("--force", is_flag=True, help="Re-evaluate already-evaluated jobs")
@click.pass_context
def evaluate(ctx: click.Context, tier2_only: bool, dry_run: bool, force: bool) -> None:
    """Run AI evaluation (Tier 2 + Tier 3)."""
    config = _load_config(ctx)
    secrets = SecretsConfig()

    # Determine provider from tier2 config (tier2 and tier3 must use same provider)
    provider = config.ai_models.tier2.provider
    if provider == "anthropic":
        if not secrets.anthropic_api_key:
            raise click.ClickException("ANTHROPIC_API_KEY not set in .env")
        from jobhunter.ai.claude_client import AIClient, ClaudeClient

        client: AIClient = ClaudeClient(api_key=secrets.anthropic_api_key)
    elif provider == "openai":
        if not secrets.openai_api_key:
            raise click.ClickException("OPENAI_API_KEY not set in .env")
        from jobhunter.ai.openai_client import OpenAIClient

        client = OpenAIClient(api_key=secrets.openai_api_key)
    else:
        raise click.ClickException(
            f"Unsupported AI provider: '{provider}'. "
            "Use 'anthropic' or 'openai'."
        )

    from jobhunter.ai.evaluator import EvaluationService
    from jobhunter.db.session import create_engine, get_session
    from jobhunter.db.settings import get_ai_cost_config

    create_engine(config.database)

    with get_session() as session:
        cost_config = get_ai_cost_config(session)
        service = EvaluationService(session, client, config.ai_models, cost_config)

        result = asyncio.run(service.run(
            tier2_only=tier2_only,
            force=force,
            dry_run=dry_run,
        ))

        click.echo("\nEvaluation complete:")
        click.echo(
            f"  Tier 2: {result.tier2_evaluated} evaluated "
            f"({result.tier2_passed} pass, {result.tier2_failed} fail, "
            f"{result.tier2_maybe} maybe, {result.tier2_errors} errors)"
        )
        if not tier2_only:
            click.echo(
                f"  Tier 3: {result.tier3_evaluated} evaluated "
                f"({result.tier3_strong} strong, {result.tier3_moderate} moderate, "
                f"{result.tier3_weak} weak, {result.tier3_errors} errors)"
            )
        click.echo(f"  Total cost: ${result.total_cost_usd:.4f}")
        if result.cap_reached:
            click.echo("  Daily cost cap reached — remaining jobs deferred")


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be generated without API calls")
@click.option("--force", is_flag=True, help="Regenerate even if content already exists")
@click.pass_context
def generate(ctx: click.Context, dry_run: bool, force: bool) -> None:
    """Generate cover letters and why-company answers for shortlisted jobs."""
    config = _load_config(ctx)
    secrets = SecretsConfig()

    # Content gen uses the content_gen model config — select provider
    provider = config.ai_models.content_gen.provider
    if provider == "anthropic":
        if not secrets.anthropic_api_key:
            raise click.ClickException("ANTHROPIC_API_KEY not set in .env")
        from jobhunter.ai.claude_client import AIClient, ClaudeClient

        client: AIClient = ClaudeClient(api_key=secrets.anthropic_api_key)
    elif provider == "openai":
        if not secrets.openai_api_key:
            raise click.ClickException("OPENAI_API_KEY not set in .env")
        from jobhunter.ai.openai_client import OpenAIClient

        client = OpenAIClient(api_key=secrets.openai_api_key)
    else:
        raise click.ClickException(
            f"Unsupported content_gen provider: '{provider}'. "
            "Use 'anthropic' or 'openai'."
        )

    from jobhunter.db.session import create_engine, get_session
    from jobhunter.db.settings import get_ai_cost_config
    from jobhunter.generation.service import GenerationService

    create_engine(config.database)

    with get_session() as session:
        cost_config = get_ai_cost_config(session)
        service = GenerationService(session, client, config.ai_models, cost_config)

        result = asyncio.run(service.run(force=force, dry_run=dry_run))

        click.echo("\nGeneration complete:")
        click.echo(
            f"  Cover letters: {result.cover_letters_generated} generated, "
            f"{result.cover_letters_skipped} skipped"
        )
        click.echo(
            f"  Why-company answers: {result.why_company_generated} generated, "
            f"{result.why_company_skipped} skipped"
        )
        click.echo(f"  Errors: {result.errors}")
        click.echo(f"  Total cost: ${result.total_cost_usd:.4f}")
        if result.cap_reached:
            click.echo("  Daily cost cap reached — remaining jobs deferred")


@cli.command()
@click.pass_context
def run_all(ctx: click.Context) -> None:
    """Run the full pipeline: scrape -> filter -> evaluate -> generate."""
    _load_config(ctx)
    click.echo("Full pipeline not yet implemented (M6)")


@cli.command(name="ingest-resumes")
@click.pass_context
def ingest_resumes(ctx: click.Context) -> None:
    """Extract text from resume PDFs and store in database."""
    config = _load_config(ctx)

    from jobhunter.db.session import create_engine, get_session
    from jobhunter.resume.manager import ResumeManager

    create_engine(config.database)
    with get_session() as session:
        manager = ResumeManager(session)
        profiles = manager.sync_resumes()
        if profiles:
            click.echo(f"Processed {len(profiles)} resume profile(s):")
            for p in profiles:
                click.echo(f"  - {p.label}: {len(p.extracted_text)} chars extracted")
        else:
            click.echo("No resume profiles found. Place PDF files in data/resumes/")


@cli.command(name="init-db")
def init_db() -> None:
    """Create/upgrade the database to the latest schema."""
    from alembic.config import Config

    from alembic import command

    configure_logging(verbose=False)
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    click.echo("Database initialized/upgraded to latest schema.")


def main() -> None:
    """Entry point for [project.scripts] console command."""
    cli()
