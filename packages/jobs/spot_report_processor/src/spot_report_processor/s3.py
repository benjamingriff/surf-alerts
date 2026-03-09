import gzip
import io
import json

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
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

    def get_parquet_rows(self, bucket: str, key: str) -> list[dict]:
        if not self.object_exists(bucket, key):
            return []
        response = self.s3.get_object(Bucket=bucket, Key=key)
        table = pq.read_table(io.BytesIO(response["Body"].read()))
        return table.to_pylist()

    def put_parquet(self, bucket: str, key: str, rows: list[dict]) -> None:
        if not rows:
            return
        table = pa.Table.from_pylist(rows)
        buffer = io.BytesIO()
        pq.write_table(table, buffer, compression="snappy")
        self.s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=buffer.getvalue(),
            ContentType="application/octet-stream",
        )
