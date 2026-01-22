from sitemap_scraper.scraper.core import scrape_sitemap


def run_sitemap_scraper() -> dict:
    """Run the sitemap scraper and return the data."""
    return scrape_sitemap()
