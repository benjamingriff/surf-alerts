import hashlib
import json
from datetime import datetime, timezone

from spot_reconciler.logger import get_logger

logger = get_logger()


def compute_checksum(spot: dict) -> str:
    """Compute a deterministic checksum of mutable spot fields.

    Args:
        spot: Spot data dictionary

    Returns:
        16-character hex checksum
    """
    data = {
        "name": spot.get("name"),
        "lat": spot.get("lat"),
        "lng": spot.get("lng"),
        "timezone": spot.get("timezone"),
        "utc_offset": spot.get("utc_offset"),
        "link": spot.get("link"),
    }
    serialized = json.dumps(data, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def _flatten_taxonomy(node: dict, sitemap_spots: dict) -> dict[str, dict]:
    """Recursively flatten taxonomy tree into a spot dictionary.

    Args:
        node: A taxonomy node
        sitemap_spots: Sitemap data to merge URLs from

    Returns:
        Dictionary mapping spot_id to merged spot data
    """
    spots = {}

    if node.get("type") == "spot":
        spot_id = node.get("spot_id")
        if spot_id:
            # Merge with sitemap data if available
            sitemap_data = sitemap_spots.get(spot_id, {})

            spot = {
                "spot_id": spot_id,
                "tax_id": node.get("tax_id"),
                "name": node.get("name"),
                "lat": node.get("lat"),
                "lng": node.get("lng"),
                "timezone": node.get("timezone"),
                "utc_offset": node.get("utc_offset"),
                "link": sitemap_data.get("link") or node.get("link"),
                "forecast": sitemap_data.get("forecast"),
            }

            spot["checksum"] = compute_checksum(spot)
            spots[spot_id] = spot

    # Recurse into children
    for child in node.get("contains", []):
        spots.update(_flatten_taxonomy(child, sitemap_spots))

    return spots


def detect_changes(
    current: dict[str, dict],
    previous: dict[str, dict],
    timestamp: str,
) -> list[dict]:
    """Compare current vs previous state to detect changes.

    Args:
        current: Current spot data with checksums
        previous: Previous spot data with checksums
        timestamp: ISO timestamp for change records

    Returns:
        List of change records
    """
    changes = []
    current_ids = set(current.keys())
    previous_ids = set(previous.keys())

    # New spots
    for spot_id in current_ids - previous_ids:
        changes.append({
            "spot_id": spot_id,
            "change_type": "added",
            "timestamp": timestamp,
            "checksum": current[spot_id]["checksum"],
            "data": current[spot_id],
        })

    # Removed spots
    for spot_id in previous_ids - current_ids:
        changes.append({
            "spot_id": spot_id,
            "change_type": "removed",
            "timestamp": timestamp,
            "previous_checksum": previous[spot_id].get("checksum"),
        })

    # Modified spots (checksum changed)
    for spot_id in current_ids & previous_ids:
        if current[spot_id]["checksum"] != previous[spot_id].get("checksum"):
            changes.append({
                "spot_id": spot_id,
                "change_type": "modified",
                "timestamp": timestamp,
                "previous_checksum": previous[spot_id].get("checksum"),
                "new_checksum": current[spot_id]["checksum"],
                "data": current[spot_id],
            })

    return changes


def reconcile_spots(
    sitemap_data: dict,
    taxonomy_data: dict,
    previous_state: dict | None,
) -> tuple[dict, list[dict]]:
    """Reconcile sitemap and taxonomy data, detecting changes.

    Args:
        sitemap_data: Raw sitemap scrape data
        taxonomy_data: Raw taxonomy scrape data
        previous_state: Previous state data (or None for first run)

    Returns:
        Tuple of (current_spots, changes)
    """
    logger.info("Starting spot reconciliation")

    # Extract spots from sitemap
    sitemap_spots = sitemap_data.get("spots", {})
    logger.info("Loaded sitemap spots", extra={"count": len(sitemap_spots)})

    # Flatten taxonomy tree and merge with sitemap
    taxonomy_root = taxonomy_data.get("taxonomy", {})
    current_spots = _flatten_taxonomy(taxonomy_root, sitemap_spots)
    logger.info("Flattened taxonomy spots", extra={"count": len(current_spots)})

    # Get previous state
    previous_spots = {}
    if previous_state:
        previous_spots = previous_state.get("spots", {})
        logger.info("Loaded previous state", extra={"count": len(previous_spots)})
    else:
        logger.info("No previous state found, treating all spots as new")

    # Detect changes
    timestamp = datetime.now(timezone.utc).isoformat()
    changes = detect_changes(current_spots, previous_spots, timestamp)

    # Log change summary
    added = sum(1 for c in changes if c["change_type"] == "added")
    removed = sum(1 for c in changes if c["change_type"] == "removed")
    modified = sum(1 for c in changes if c["change_type"] == "modified")

    logger.info(
        "Change detection complete",
        extra={
            "added": added,
            "removed": removed,
            "modified": modified,
            "total_changes": len(changes),
        },
    )

    return current_spots, changes
