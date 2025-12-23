from spot_scraper.http.client import make_request
from spot_scraper.logger import get_logger
from spot_scraper.parser.response import parse_response

logger = get_logger()

ENDPOINTS = {
    "rating": "https://services.surfline.com/kbyg/spots/forecasts/rating?spotId={}&days=5&intervalHours=1&cacheEnabled=true",
    "sunlight": "https://services.surfline.com/kbyg/spots/forecasts/sunlight?spotId={}&days=16&intervalHours=1",
    "tides": "https://services.surfline.com/kbyg/spots/forecasts/tides?spotId={}&days=6&cacheEnabled=true&units[tideHeight]=M",
    "wave": "https://services.surfline.com/kbyg/spots/forecasts/wave?spotId={}&days=5&intervalHours=1&cacheEnabled=true&units[swellHeight]=FT&units[waveHeight]=FT",
    "weather": "https://services.surfline.com/kbyg/spots/forecasts/weather?spotId={}&days=16&intervalHours=1&cacheEnabled=true&units[temperature]=C",
    "wind": "https://services.surfline.com/kbyg/spots/forecasts/wind?spotId={}&days=5&intervalHours=1&corrected=false&cacheEnabled=true&units[windSpeed]=MPH",
}


def scrape_spot(spot_id: str) -> dict:
    logger.info("Scraping spot", extra={"spot_id": spot_id})

    results = {}
    for key, endpoint in ENDPOINTS.items():
        url = endpoint.replace("{}", spot_id)
        response = make_request(url)
        data = parse_response(response)
        logger.info(f"Successfully scraped {key}", extra={"spot_id": spot_id, "data": data})
        results[key] = data

    return results
