import os
from datetime import datetime, timezone

from aws_lambda_powertools.utilities.typing import LambdaContext

from spot_reconciler.io import S3Client
from spot_reconciler.logger import get_logger, inject_lambda_context
from spot_reconciler.reconciler import reconcile_spots

logger = get_logger()

s3_client = S3Client()


@inject_lambda_context(log_event=False)
def lambda_handler(event: dict, context: LambdaContext):
    """Lambda handler triggered by EventBridge schedule.

    Reads sitemap and taxonomy data, reconciles them, detects changes,
    and writes results to S3.
    """
    logger.debug("Received event", extra={"event": event})

    bucket = os.environ.get("BUCKET_NAME", "surf-alerts-data")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Read sitemap data
    sitemap_key = f"spots/{date_str}/sitemap.json.gz"
    sitemap_data = s3_client.get_json(bucket, sitemap_key)
    if not sitemap_data:
        logger.error("Sitemap data not found", extra={"key": sitemap_key})
        return {
            "statusCode": 404,
            "body": f"Sitemap data not found: {sitemap_key}",
        }

    # Read taxonomy data
    taxonomy_key = f"taxonomy/{date_str}/taxonomy.json.gz"
    taxonomy_data = s3_client.get_json(bucket, taxonomy_key)
    if not taxonomy_data:
        logger.error("Taxonomy data not found", extra={"key": taxonomy_key})
        return {
            "statusCode": 404,
            "body": f"Taxonomy data not found: {taxonomy_key}",
        }

    # Read previous state (may not exist on first run)
    state_key = "spots/latest/state.json.gz"
    previous_state = s3_client.get_json(bucket, state_key)

    # Reconcile and detect changes
    current_spots, changes = reconcile_spots(sitemap_data, taxonomy_data, previous_state)

    # Build output data
    reconciled_at = datetime.now(timezone.utc).isoformat()

    spots_data = {
        "reconciled_at": reconciled_at,
        "spot_count": len(current_spots),
        "spots": current_spots,
    }

    changes_data = {
        "reconciled_at": reconciled_at,
        "change_count": len(changes),
        "changes": changes,
    }

    state_data = {
        "updated_at": reconciled_at,
        "spot_count": len(current_spots),
        "spots": current_spots,
    }

    # Write outputs to S3
    spots_key = f"spots/{date_str}/spots_data.json"
    s3_client.put_json(bucket, spots_key, spots_data)

    changes_key = f"spots/{date_str}/changes.json"
    s3_client.put_json(bucket, changes_key, changes_data)

    s3_client.put_json(bucket, state_key, state_data)

    logger.info(
        "Reconciliation complete",
        extra={
            "spot_count": len(current_spots),
            "change_count": len(changes),
        },
    )

    return {
        "statusCode": 200,
        "body": f"Reconciled {len(current_spots)} spots, detected {len(changes)} changes",
    }
