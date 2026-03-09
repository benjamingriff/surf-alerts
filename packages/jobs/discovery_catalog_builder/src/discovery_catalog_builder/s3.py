import gzip
import io
import json
from datetime import datetime

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

    def list_keys(self, bucket: str, prefix: str) -> list[str]:
        paginator = self.s3.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                keys.append(item["Key"])
        return sorted(keys)

    def read_parquet_prefix(self, bucket: str, prefix: str) -> list[dict]:
        rows: list[dict] = []
        for key in self.list_keys(bucket, prefix):
            if not key.endswith(".parquet"):
                continue
            response = self.s3.get_object(Bucket=bucket, Key=key)
            table = pq.read_table(io.BytesIO(response["Body"].read()))
            rows.extend(table.to_pylist())
        return rows

    def _coerce_row(self, row: dict, schema: pa.Schema) -> dict:
        coerced: dict = {}
        for field in schema:
            value = row.get(field.name)
            if value is None:
                coerced[field.name] = None
            elif pa.types.is_timestamp(field.type):
                coerced[field.name] = (
                    value
                    if isinstance(value, datetime)
                    else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                )
            elif pa.types.is_int64(field.type):
                coerced[field.name] = int(value)
            elif pa.types.is_float64(field.type):
                coerced[field.name] = float(value)
            elif pa.types.is_boolean(field.type):
                coerced[field.name] = bool(value)
            else:
                coerced[field.name] = value
        return coerced

    def write_parquet(self, bucket: str, key: str, rows: list[dict], schema: pa.Schema) -> None:
        table = pa.Table.from_pylist([self._coerce_row(row, schema) for row in rows], schema=schema)
        buffer = io.BytesIO()
        pq.write_table(table, buffer, compression="snappy")
        self.s3.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue(), ContentType="application/octet-stream")
