from forecast_scraper.scraper.core import scrape_forecast


def run_forecast_scraper(spot_id: str) -> dict:
    """Run the forecast scraper and return the data."""
    return scrape_forecast(spot_id)
