import asyncio
import logging
from pathlib import Path

import click

from jobhunter.config.loader import load_config
from jobhunter.config.schema import AppConfig, ConfigurationError, SecretsConfig
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


@cli.command()
@click.option(
    "--scraper",
    type=click.Choice(["remote_io", "remote_rocketship", "wellfound", "linkedin"]),
    default=None,
    help="Run a specific scraper (default: all enabled)",
)
@click.pass_context
def scrape(ctx: click.Context, scraper: str | None) -> None:
    """Run job scrapers to collect new postings."""
    config = _load_config(ctx)
    secrets = SecretsConfig()

    from jobhunter.db.session import create_engine, get_session
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
            orchestrator = ScraperOrchestrator(config, secrets, session)
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
@click.pass_context
def filter_cmd(ctx: click.Context) -> None:
    """Apply Tier 1 rule-based filters."""
    _load_config(ctx)
    click.echo("Filtering not yet implemented (M2)")


@cli.command()
@click.pass_context
def evaluate(ctx: click.Context) -> None:
    """Run AI evaluation (Tier 2 + Tier 3)."""
    _load_config(ctx)
    click.echo("Evaluation not yet implemented (M3)")


@cli.command()
@click.pass_context
def generate(ctx: click.Context) -> None:
    """Generate cover letters and why-company answers."""
    _load_config(ctx)
    click.echo("Generation not yet implemented (M4)")


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
