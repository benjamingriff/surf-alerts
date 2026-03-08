from spot_scraper.scraper import scrape_spot
from rich import print


def test_scrape_spot_live():
    spot_id = "584204204e65fad6a77090d2"  # Rest Bay
    result = scrape_spot(spot_id)
    print(result)

    assert result["scraped_at"] is not None

    spot = result["spot"]
    assert spot["spot_id"] == spot_id
    assert spot["name"] == "Rest Bay"
    assert spot["lat"] is not None
    assert spot["lon"] is not None
    assert spot["timezone"] is not None
    assert spot["utc_offset"] is not None
    assert spot["breadcrumbs"] is not None
    assert len(spot["breadcrumbs"]) > 0
    assert spot["subregion"] is not None
    assert spot["cameras"] is not None
