import gzip
import json

import boto3
from botocore.exceptions import ClientError

from spot_scraper.logger import get_logger


logger = get_logger()


class S3Writer:
    def __init__(self, s3_client=None):
        self.s3 = s3_client or boto3.client("s3")

    def put_json(self, bucket: str, key: str, body: dict, compress: bool = True):
        extra_args = {"ContentType": "application/json"}
        data_bytes = json.dumps(body).encode("utf-8")

        if compress:
            data_bytes = gzip.compress(data_bytes)
            extra_args["ContentEncoding"] = "gzip"
            if not key.endswith(".gz"):
                key = f"{key}.gz"
        try:
            self.s3.put_object(Bucket=bucket, Key=key, Body=data_bytes, **extra_args)
            return f"s3://{bucket}/{key}"
        except ClientError as e:
            logger.error(f"Failed to upload: {e}")
            raise
