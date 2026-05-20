import gzip
import json

import boto3


class S3Client:
    def __init__(self, s3_client=None):
        self.s3 = s3_client or boto3.client("s3")

    def put_json(self, bucket: str, key: str, body: dict, compress: bool = True) -> None:
        payload = json.dumps(body).encode("utf-8")
        extra_args = {"ContentType": "application/json"}
        if compress:
            payload = gzip.compress(payload)
            extra_args["ContentEncoding"] = "gzip"
            if not key.endswith(".gz"):
                key = f"{key}.gz"
        self.s3.put_object(Bucket=bucket, Key=key, Body=payload, **extra_args)
