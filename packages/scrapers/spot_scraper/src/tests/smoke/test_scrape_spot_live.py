from spot_scraper.scraper import scrape_spot
from rich import print


def test_scrape_spot_live():
    spot_id = "584204204e65fad6a77090d2"  # Rest Bay
    results = scrape_spot(spot_id)
    print(results)
    assert results
