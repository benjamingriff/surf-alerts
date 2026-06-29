import gzip
import json

import boto3
from botocore.exceptions import ClientError

from spot_reconciler.logger import get_logger


logger = get_logger()


class S3Client:
    def __init__(self, s3_client=None):
        self.s3 = s3_client or boto3.client("s3")

    def get_json(self, bucket: str, key: str) -> dict | None:
        """Read and decompress a JSON file from S3.

        Args:
            bucket: S3 bucket name
            key: S3 object key

        Returns:
            Parsed JSON data, or None if the file doesn't exist
        """
        try:
            response = self.s3.get_object(Bucket=bucket, Key=key)
            data = response["Body"].read()

            # Decompress if gzipped
            if key.endswith(".gz") or response.get("ContentEncoding") == "gzip":
                data = gzip.decompress(data)

            return json.loads(data.decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.info(f"File not found: s3://{bucket}/{key}")
                return None
            logger.error(f"Failed to read: {e}")
            raise

    def put_json(self, bucket: str, key: str, body: dict, compress: bool = True) -> str:
        """Write a JSON file to S3 with optional compression.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            body: Data to serialize as JSON
            compress: Whether to gzip compress the data

        Returns:
            S3 URI of the uploaded file
        """
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
