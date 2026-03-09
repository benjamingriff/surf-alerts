import gzip
import json

import boto3
from botocore.exceptions import ClientError


class S3Client:
    def __init__(self, s3_client=None):
        self.s3 = s3_client or boto3.client("s3")

    def get_json(self, bucket: str, key: str) -> dict | None:
        try:
            response = self.s3.get_object(Bucket=bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] in {"404", "NoSuchKey"}:
                return None
            raise
        payload = response["Body"].read()
        if response.get("ContentEncoding") == "gzip" or key.endswith(".gz"):
            payload = gzip.decompress(payload)
        return json.loads(payload)

    def put_json(self, bucket: str, key: str, body: dict, compress: bool = True) -> None:
        payload = json.dumps(body).encode("utf-8")
        extra_args = {"ContentType": "application/json"}
        if compress:
            payload = gzip.compress(payload)
            extra_args["ContentEncoding"] = "gzip"
            if not key.endswith(".gz"):
                key = f"{key}.gz"
        self.s3.put_object(Bucket=bucket, Key=key, Body=payload, **extra_args)

    def object_exists(self, bucket: str, key: str) -> bool:
        try:
            self.s3.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] in {"404", "NoSuchKey"}:
                return False
            raise

    def list_keys(self, bucket: str, prefix: str) -> list[str]:
        paginator = self.s3.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                keys.append(item["Key"])
        return sorted(keys)
