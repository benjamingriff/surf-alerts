from datetime import datetime, timezone

from sitemap_scraper.http import make_request
from sitemap_scraper.logger import get_logger
from sitemap_scraper.parser import parse_sitemap

logger = get_logger()

SITEMAP_URL = "https://www.surfline.com/sitemaps/spots.xml"


def scrape_sitemap() -> dict:
    """Scrape Surfline sitemap and return structured spot data.

    Returns:
        Dictionary with scraped_at timestamp and spots data
    """
    logger.info("Starting sitemap scrape", extra={"url": SITEMAP_URL})

    response = make_request(SITEMAP_URL)
    spots = parse_sitemap(response.content)

    result = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "spots": spots,
    }

    logger.info(
        "Sitemap scrape complete",
        extra={"spot_count": len(spots)},
    )

    return result
