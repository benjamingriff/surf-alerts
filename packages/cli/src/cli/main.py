import json
from datetime import datetime
from pathlib import Path

import typer
from rich import print as rprint

from cli.scrapers.forecast import run_forecast_scraper
from cli.scrapers.sitemap import run_sitemap_scraper
from cli.scrapers.taxonomy import run_taxonomy_scraper
from cli.scrapers.spot import run_spot_scraper

app = typer.Typer(
    help="CLI tool to run scrapers locally and save sample data",
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """CLI tool to run scrapers locally and save sample data."""
    if ctx.invoked_subcommand is None:
        rprint(ctx.get_help())
        raise typer.Exit(0)


# Default spot ID for Rest Bay
DEFAULT_SPOT_ID = "584204204e65fad6a77090d2"

# Data directory relative to project root
DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / "data"


def get_timestamped_dir(scraper_name: str) -> Path:
    """Create and return a timestamped output directory."""
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    output_dir = DATA_DIR / scraper_name / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


@app.command()
def forecast(
    spot_id: str = typer.Option(DEFAULT_SPOT_ID, "--spot-id", "-s", help="Surfline spot ID"),
):
    """Scrape forecast data for a surf spot and save to data/forecast/"""
    rprint(f"[blue]Scraping forecast for spot:[/blue] {spot_id}")

    try:
        data = run_forecast_scraper(spot_id)
    except Exception as e:
        rprint(f"[red]Error scraping forecast:[/red] {e}")
        raise typer.Exit(code=1)

    output_dir = get_timestamped_dir("forecast")

    # Write data.json
    data_file = output_dir / "data.json"
    with open(data_file, "w") as f:
        json.dump(data, f, indent=2)

    # Write metadata.json
    metadata = {
        "spot_id": spot_id,
        "timestamp": datetime.now().isoformat(),
        "scraper": "forecast",
    }
    metadata_file = output_dir / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    rprint(f"[green]Data saved to:[/green] {output_dir}")
    rprint(f"  - {data_file.name}")
    rprint(f"  - {metadata_file.name}")


@app.command()
def sitemap():
    """Scrape Surfline sitemap for all surf spot URLs and save to data/sitemap/"""
    rprint("[blue]Scraping Surfline sitemap...[/blue]")

    try:
        data = run_sitemap_scraper()
    except Exception as e:
        rprint(f"[red]Error scraping sitemap:[/red] {e}")
        raise typer.Exit(code=1)

    output_dir = get_timestamped_dir("sitemap")

    # Write data.json
    data_file = output_dir / "data.json"
    with open(data_file, "w") as f:
        json.dump(data, f, indent=2)

    # Write metadata.json
    metadata = {
        "timestamp": datetime.now().isoformat(),
        "scraper": "sitemap",
        "spot_count": len(data.get("spots", {})),
    }
    metadata_file = output_dir / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    rprint(f"[green]Data saved to:[/green] {output_dir}")
    rprint(f"  - {data_file.name} ({len(data.get('spots', {}))} spots)")
    rprint(f"  - {metadata_file.name}")


@app.command()
def taxonomy():
    """Scrape Surfline taxonomy for all surf spot information and save to data/taxonomy/"""
    rprint("[blue]Scraping Surfline taxonomy...[/blue]")

    try:
        data = run_taxonomy_scraper()
    except Exception as e:
        rprint(f"[red]Error scraping sitemap:[/red] {e}")
        raise typer.Exit(code=1)

    output_dir = get_timestamped_dir("taxonomy")

    data_file = output_dir / "data.json"
    with open(data_file, "w") as f:
        json.dump(data, f, indent=2)

    metadata = {
        "timestamp": datetime.now().isoformat(),
        "scraper": "taxonomy",
    }
    metadata_file = output_dir / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    rprint(f"[green]Data saved to:[/green] {output_dir}")
    rprint(f"  - {metadata_file.name}")


@app.command()
def spot(
    spot_id: str = typer.Option(DEFAULT_SPOT_ID, "--spot-id", "-s", help="Surfline spot ID"),
):
    """Scrape spot data for a surf spot and save to data/spot/"""
    rprint(f"[blue]Scraping spot report for spot:[/blue] {spot_id}")

    try:
        data = run_spot_scraper(spot_id)
    except Exception as e:
        rprint(f"[red]Error scraping spot:[/red] {e}")
        raise typer.Exit(code=1)

    output_dir = get_timestamped_dir("spot")

    # Write data.json
    data_file = output_dir / "data.json"
    with open(data_file, "w") as f:
        json.dump(data, f, indent=2)

    # Write metadata.json
    metadata = {
        "spot_id": spot_id,
        "timestamp": datetime.now().isoformat(),
        "scraper": "spot",
    }
    metadata_file = output_dir / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    rprint(f"[green]Data saved to:[/green] {output_dir}")
    rprint(f"  - {data_file.name}")
    rprint(f"  - {metadata_file.name}")


if __name__ == "__main__":
    app()
