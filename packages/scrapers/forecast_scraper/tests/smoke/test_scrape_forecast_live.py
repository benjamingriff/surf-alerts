from forecast_scraper.scraper import scrape_forecast
from rich import print


def test_scrape_forecast_live():
    spot_id = "584204204e65fad6a77090d2"  # Rest Bay
    results = scrape_forecast(spot_id)
    print(results)
    assert results
