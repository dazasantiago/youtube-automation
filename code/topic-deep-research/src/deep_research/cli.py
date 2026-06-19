from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(name="deep-research", add_completion=False)


@app.command()
def research(
    input: Path | None = typer.Option(None, "--input", help="Path to topic input JSON file"),
    topic: str | None = typer.Option(
        None, "--topic", help="Research a topic from scratch (no prior signals)"
    ),
    out_dir: Path = typer.Option(Path("results"), "--out-dir", help="Base output directory"),
    top_signals: int = typer.Option(20, "--top-signals", help="Max signals to enrich"),
    top_comments: int = typer.Option(10, "--top-comments", help="Max Reddit comments per post"),
    per_source: int = typer.Option(
        8, "--per-source", help="Signals discovered per source in --topic mode"
    ),
) -> None:
    """Deep-scrape a classified topic: enrich signals and discover new sources.

    Provide exactly one of --input (pre-classified signals JSON) or --topic (discover from scratch).
    """
    if (input is None) == (topic is None):
        typer.echo("Error: provide exactly one of --input or --topic", err=True)
        raise typer.Exit(1)

    if topic is not None:
        from deep_research.pipeline import run_topic

        typer.echo(f"[{topic}] discovering signals from scratch...")
        out_path, result = run_topic(
            topic,
            top_signals=top_signals,
            top_comments=top_comments,
            per_source=per_source,
            out_dir=out_dir,
        )
    else:
        assert input is not None
        from deep_research.loader import load_topic_input
        from deep_research.pipeline import run

        if not input.exists():
            typer.echo(f"Error: input file not found: {input}", err=True)
            raise typer.Exit(1)

        topic_input = load_topic_input(input)
        typer.echo(f"[{topic_input.topic}] {len(topic_input.signals)} signals loaded")
        out_path, result = run(
            topic_input,
            top_signals=top_signals,
            top_comments=top_comments,
            out_dir=out_dir,
        )

    kept = len(result.enriched_signals)
    discarded = result.signals_attempted - kept

    typer.echo(f"\n[{result.topic_input.topic}] -> {out_path}/")
    typer.echo(
        f"  signals_enriched.json    ({kept} with content, {discarded} discarded empty)"
    )
    typer.echo(f"  discovered_sources.json  ({len(result.discovered_sources)} sources)")
