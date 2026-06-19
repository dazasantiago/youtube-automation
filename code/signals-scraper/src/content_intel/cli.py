"""CLI entrypoint for the content-intel scraper."""

from __future__ import annotations

import typer

app = typer.Typer(name="content-intel", help="Signal scraping pipeline.")


@app.command()
def pull(
    sources: str = typer.Option("all", help="Comma-separated source names or 'all'"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch signals but skip DB writes"),
) -> None:
    """Fetch signals from configured sources."""
    from content_intel.pipeline.ingest import run_pull

    run_pull(sources=sources, dry_run=dry_run)


@app.command("yt-scan")
def yt_scan() -> None:
    """Scan YouTube channels for new uploads and outliers."""
    from content_intel.sources.youtube import run_yt_scan

    run_yt_scan()


@app.command()
def export(
    days: int = typer.Option(7, help="Number of past days to include"),
    out: str = typer.Option("data/signals.json", help="Output file path"),
) -> None:
    """Export recent signals to JSON for LLM consumption."""
    from content_intel.export import run_export

    run_export(days=days, out=out)


if __name__ == "__main__":
    app()
