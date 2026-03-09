# CLI

Command-line interface for running scrapers locally and saving sample data.

See [docs/packages/cli.md](../../docs/packages/cli.md).

## Usage

```bash
# Install dependencies (from project root)
uv sync

# Show help
uv run sample --help

# Scrape forecast data (default spot: Rest Bay)
uv run sample forecast

# Scrape forecast for a specific spot
uv run sample forecast --spot-id <SURFLINE_SPOT_ID>

# Scrape sitemap
uv run sample sitemap

# Scrape taxonomy
uv run sample taxonomy

# Scrape spot report
uv run sample spot
uv run sample spot --spot-id <SURFLINE_SPOT_ID>
```

Output is saved to `data/<scraper_name>/<timestamp>/` with `data.json` and `metadata.json` files.
