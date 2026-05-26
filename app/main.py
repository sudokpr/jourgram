#!/usr/bin/env python3
"""Life Data Lake - Main CLI entry point."""

from __future__ import annotations

import sys
from typing import Any, Callable

import structlog
import typer
from rich.console import Console

from app.config.settings import Settings

console = Console()
log = structlog.get_logger()

cli = typer.Typer(
    name="life-lake",
    help="Life Data Lake - Local-first personal data management",
    invoke_without_command=True,
)


@cli.callback()
def callback(version: bool = typer.Option(False, "--version", help="Show version")) -> None:
    """Global callback."""
    if version:
        console.print("[bold]Life Data Lake[/bold] v0.1.0")


@cli.command()
def ingest(
    ctx: typer.Context,
    days: int | None = typer.Option(None, "--days", help="Number of days to backfill"),
) -> None:
    """Start Telegram ingestion service."""
    from app.ingestion.service import IngestionService

    settings = Settings.from_env()
    service = IngestionService(settings)
    if days:
        typer.echo(f"Backfilling last {days} days...")
    typer.echo("Starting ingestion service... Press Ctrl+C to stop.")
    try:
        service.run()
    except KeyboardInterrupt:
        typer.echo("\nStopping ingestion...")


@cli.command()
def summarize(
    ctx: typer.Context,
    date: str | None = typer.Option(None, "--date", help="Date in YYYY-MM-DD format"),
    force: bool = typer.Option(False, "--force", help="Force re-summarization"),
) -> None:
    """Generate daily summary."""
    from app.summarizer.daily import DailySummarizer

    settings = Settings.from_env()
    summarizer = DailySummarizer(settings)
    if date:
        import asyncio
        asyncio.run(summarizer.summarize_date(date, force=force))
    else:
        typer.echo("Summarizing today...")
        import asyncio
        asyncio.run(summarizer.summarize_today(force=force))


@cli.command()
def summarize_range(
    ctx: typer.Context,
    start: str = typer.Argument(..., help="Start date YYYY-MM-DD"),
    end: str = typer.Argument(..., help="End date YYYY-MM-DD"),
) -> None:
    """Generate summaries for a date range."""
    from app.summarizer.daily import DailySummarizer

    settings = Settings.from_env()
    summarizer = DailySummarizer(settings)
    import asyncio
    asyncio.run(summarizer.summarize_range(start, end))


@cli.command()
def backfill(
    ctx: typer.Context,
    days: int = typer.Argument(..., help="Number of days to backfill"),
) -> None:
    """Backfill messages from Telegram."""
    from app.ingestion.backfill import BackfillWorker

    settings = Settings.from_env()
    worker = BackfillWorker(settings)
    import asyncio
    asyncio.run(worker.backfill_days(days))


@cli.command()
def export(
    ctx: typer.Context,
    format: str = typer.Option("json", "--format", help="Export format: json, csv"),
    output: str = typer.Option("exports/", "--output", help="Output directory"),
    start: str | None = None,
    end: str | None = None,
) -> None:
    """Export data."""
    from app.storage.exporter import Exporter

    settings = Settings.from_env()
    exporter = Exporter(settings)
    import asyncio
    asyncio.run(exporter.export(format, output, start, end))


@cli.command()
def healthcheck(ctx: typer.Context) -> None:
    """Check system health."""
    from app.config.health import HealthChecker

    settings = Settings.from_env()
    checker = HealthChecker(settings)
    import asyncio
    result = asyncio.run(checker.check_all())
    if result["healthy"]:
        console.print("[green]✓ All systems healthy[/green]")
    else:
        console.print("[red]✗ Issues found:[/red]")
        for issue in result["issues"]:
            console.print(f"  - {issue}")
        raise typer.Exit(1)


@cli.command()
def rebuild_index(ctx: typer.Context) -> None:
    """Rebuild search index."""
    from app.search.indexer import SearchIndexer

    settings = Settings.from_env()
    indexer = SearchIndexer(settings)
    import asyncio
    asyncio.run(indexer.rebuild())


@cli.command()
def fetch_links(ctx: typer.Context) -> None:
    """Fetch and process pending links."""
    from app.knowledge_base.processor import LinkProcessor

    settings = Settings.from_env()
    processor = LinkProcessor(settings)
    import asyncio
    asyncio.run(processor.process_pending())


@cli.command()
def today(ctx: typer.Context) -> None:
    """Show today's summary."""
    from app.api.queries import QueryHandler

    settings = Settings.from_env()
    handler = QueryHandler(settings)
    import asyncio
    result = asyncio.run(handler.get_today_summary())
    console.print(result)


@cli.command()
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", help="Max results"),
) -> None:
    """Search messages."""
    from app.search.engine import SearchEngine

    settings = Settings.from_env()
    engine = SearchEngine(settings)
    import asyncio
    results = asyncio.run(engine.search(query, limit))
    for r in results:
        console.print(f"[dim]{r['date']}[/dim] {r['text'][:100]}")


if __name__ == "__main__":
    cli()