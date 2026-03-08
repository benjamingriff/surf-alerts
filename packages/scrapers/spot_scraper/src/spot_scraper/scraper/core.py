from datetime import datetime, timezone

from spot_scraper.http import make_request
from spot_scraper.logger import get_logger

logger = get_logger()

SPOT_REPORTS_URL = "https://services.surfline.com/kbyg/spots/reports?spotId={}"


def _parse_spot_data(spot_id: str, data: dict) -> dict:
    spot = data.get("spot", {})
    associated = data.get("associated", {})

    return {
        "spot_id": spot_id,
        "name": spot.get("name"),
        "lat": spot.get("lat"),
        "lon": spot.get("lon"),
        "timezone": associated.get("timezone"),
        "utc_offset": associated.get("utcOffset"),
        "abbr_timezone": associated.get("abbrTimezone"),
        "href": associated.get("href"),
        "breadcrumbs": spot.get("breadcrumb", []),
        "subregion": spot.get("subregion"),
        "cameras": [
            {
                "id": cam.get("_id"),
                "title": cam.get("title"),
                "stream_url": cam.get("streamUrl"),
                "still_url": cam.get("stillUrl"),
                "is_premium": cam.get("isPremium"),
            }
            for cam in spot.get("cameras", [])
        ],
        "ability_levels": spot.get("abilityLevels", []),
        "board_types": spot.get("boardTypes", []),
        "travel_details": _parse_travel_details(spot.get("travelDetails")),
    }


def _parse_travel_details(details: dict | None) -> dict | None:
    if not details:
        return None
    return {
        "description": details.get("description"),
        "break_type": details.get("breakType", []),
        "access": details.get("access"),
        "hazards": details.get("hazards"),
        "best_season": details.get("best", {}).get("season", {}).get("value", []),
        "best_tide": details.get("best", {}).get("tide", {}).get("value", []),
        "best_swell_direction": details.get("best", {}).get("swellDirection", {}).get("value", []),
        "best_wind_direction": details.get("best", {}).get("windDirection", {}).get("value", []),
        "best_size": details.get("best", {}).get("size", {}).get("description"),
        "bottom": details.get("bottom", {}).get("value", []),
        "crowd_factor": details.get("crowdFactor", {}).get("summary"),
        "spot_rating": details.get("spotRating", {}).get("rating"),
    }


def scrape_spot(spot_id: str) -> dict:
    logger.info("Scraping spot", extra={"spot_id": spot_id})

    url = SPOT_REPORTS_URL.format(spot_id)
    response = make_request(url)
    data = response.json()

    spot_data = _parse_spot_data(spot_id, data)

    result = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "spot": spot_data,
    }

    logger.info(
        "Spot scrape complete",
        extra={"spot_id": spot_id, "spot_name": spot_data.get("name")},
    )
    return result
