from aws_lambda_powertools import Logger
from postgres_client import get_reusable_connection

from forecast_partition_maintenance.core import maintain_partitions

logger = Logger(service="forecast-partition-maintenance")


@logger.inject_lambda_context
def lambda_handler(event, context):
    conn = get_reusable_connection()
    result = maintain_partitions(conn)
    logger.info("forecast partition maintenance complete", extra=result)
    return result
