from spot_scraper.scraper.core import scrape_spot


def run_spot_scraper(spot_id: str) -> dict:
    """Run the spot scraper and return the data."""
    return scrape_spot(spot_id)
