import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

from taxonomy_scraper.http import make_request
from taxonomy_scraper.logger import get_logger

logger = get_logger()

TAXONOMY_API_URL = "https://services.surfline.com/taxonomy?type=taxonomy&id={}&maxDepth=0"
EARTH_LEVEL_ID = "58f7ed51dadb30820bb38782"
RATE_LIMIT_DELAY = 0.5  # 500ms between requests

tf = TimezoneFinder()


def _get_timezone_info(lat: float, lng: float) -> tuple[str | None, float | None]:
    """Get timezone string and UTC offset for coordinates."""
    try:
        timezone_str = tf.certain_timezone_at(lat=lat, lng=lng)
        if timezone_str:
            tz = ZoneInfo(timezone_str)
            current_time = datetime.now(tz)
            utc_offset = current_time.utcoffset()
            utc_offset_hours = utc_offset.total_seconds() / 3600 if utc_offset else None
            return timezone_str, utc_offset_hours
    except Exception as e:
        logger.warning(
            "Failed to determine timezone", extra={"lat": lat, "lng": lng, "error": str(e)}
        )
    return None, None


def _fetch_taxonomy_node(taxonomy_id: str) -> dict | None:
    """Fetch and process a single taxonomy node, recursively fetching children.

    Args:
        taxonomy_id: The taxonomy ID to fetch

    Returns:
        Processed node data with nested children, or None on error
    """
    logger.info("Fetching taxonomy node", extra={"taxonomy_id": taxonomy_id})

    # Rate limiting
    time.sleep(RATE_LIMIT_DELAY)

    url = TAXONOMY_API_URL.format(taxonomy_id)
    response = make_request(url)
    data = response.json()

    # Determine type
    node_type = data.get("geonames", {}).get("fcodeName", data.get("type"))

    # Extract coordinates based on type
    if node_type == "spot":
        coords = data.get("location", {}).get("coordinates", [0, 0])
        longitude = float(coords[0]) if coords else 0.0
        latitude = float(coords[1]) if len(coords) > 1 else 0.0
    else:
        latitude = float(data.get("geonames", {}).get("lat", 0))
        longitude = float(data.get("geonames", {}).get("lng", 0))

    # Get timezone info
    timezone_str, utc_offset_hours = _get_timezone_info(latitude, longitude)

    # Extract link from associated data
    link = None
    associated = data.get("associated", {})
    links = associated.get("links", [])
    for link_item in links:
        if link_item and link_item.get("key") == "www":
            link = link_item.get("href")
            break

    node_info = {
        "tax_id": taxonomy_id,
        "spot_id": data.get("geonameId") or data.get("spot"),
        "name": data.get("name"),
        "type": node_type,
        "lat": latitude,
        "lng": longitude,
        "timezone": timezone_str,
        "utc_offset": utc_offset_hours,
        "link": link,
    }

    # Recursively fetch children for non-spot nodes
    if node_type != "spot":
        node_info["contains"] = []
        contains = data.get("contains", [])

        for item in contains:
            child_id = item.get("_id")
            if child_id:
                child_data = _fetch_taxonomy_node(child_id)
                if child_data:
                    node_info["contains"].append(child_data)

    return node_info


def scrape_taxonomy(root_id: str = EARTH_LEVEL_ID) -> dict:
    """Scrape the full Surfline taxonomy tree.

    Args:
        root_id: The root taxonomy ID to start from (defaults to Earth level)

    Returns:
        Dictionary with scraped_at timestamp and full taxonomy tree
    """
    logger.info("Starting taxonomy scrape", extra={"root_id": root_id})

    taxonomy_tree = _fetch_taxonomy_node(root_id)

    result = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "taxonomy": taxonomy_tree,
    }

    # Count total nodes
    def count_nodes(node: dict) -> int:
        count = 1
        for child in node.get("contains", []):
            count += count_nodes(child)
        return count

    total_nodes = count_nodes(taxonomy_tree) if taxonomy_tree else 0

    logger.info(
        "Taxonomy scrape complete",
        extra={"total_nodes": total_nodes},
    )

    return result
