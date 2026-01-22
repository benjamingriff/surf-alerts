import re

from lxml import etree

from sitemap_scraper.logger import get_logger

logger = get_logger()

URL_PATTERN = re.compile(r"https://www\.surfline\.com/surf-report/[^/]+/([^/]+)(/forecast)?")


def parse_sitemap(xml_content: bytes) -> dict[str, dict]:
    """Parse sitemap XML and extract spot data.

    Args:
        xml_content: Raw XML bytes from sitemap

    Returns:
        Dictionary mapping spot_id to spot data with link and forecast URLs
    """
    root = etree.fromstring(xml_content)

    urls = [
        loc.text
        for loc in root.xpath(
            "//xmlns:loc",
            namespaces={"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"},
        )
    ]

    logger.info("Parsed sitemap URLs", extra={"url_count": len(urls)})

    spots_dict = {}

    for url in urls:
        match = URL_PATTERN.match(url)
        if match:
            spot_id, forecast_part = match.groups()

            if spot_id not in spots_dict:
                spots_dict[spot_id] = {
                    "spot_id": spot_id,
                    "link": None,
                    "forecast": None,
                }

            if forecast_part:
                spots_dict[spot_id]["forecast"] = url
            else:
                spots_dict[spot_id]["link"] = url

    logger.info("Extracted spots from sitemap", extra={"spot_count": len(spots_dict)})

    return spots_dict
