from taxonomy_scraper.scraper.core import scrape_taxonomy


def run_taxonomy_scraper() -> dict:
    """Run the sitemap scraper and return the data."""
    return scrape_taxonomy()
