"""S3 data-lake primitives: bucket lifecycle, keyed objects, copy/promote."""

from __future__ import annotations

import logging

import botocore.exceptions

from de_common.aws import client as aws_client
from de_common.config import Settings
from de_common.logging import bind, get_logger

log = get_logger("lake.s3")

LAYERS = ("raw", "bronze", "silver", "gold")


def layer_key(layer: str, date: str, name: str) -> str:
    assert layer in LAYERS, f"unknown layer: {layer}"
    return f"{layer}/date={date}/{name}"


class LakeManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bucket = settings.lake_bucket
        self._s3 = aws_client(settings, "s3")

    def ensure_bucket(self) -> None:
        try:
            self._s3.head_bucket(Bucket=self.bucket)
            bind(log, logging.INFO, "bucket exists", bucket=self.bucket)
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            kwargs: dict[str, object] = {"Bucket": self.bucket}
            if self.settings.aws_region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {
                    "LocationConstraint": self.settings.aws_region
                }
            self._s3.create_bucket(**kwargs)
            bind(log, logging.INFO, "bucket created", bucket=self.bucket)

    def upload_bytes(self, key: str, data: bytes, metadata: dict[str, str]) -> None:
        safe_meta = {k.lower().replace("_", "-"): v for k, v in metadata.items()}
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, Metadata=safe_meta)
        bind(log, logging.INFO, "uploaded", key=key, size=len(data))

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except botocore.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "404":
                return False
            raise

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return sorted(keys)

    def get_bytes(self, key: str) -> bytes:
        body = self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        assert isinstance(body, bytes), f"unexpected S3 body type for {key}"
        return body

    def copy(self, src_key: str, dest_key: str, metadata: dict[str, str]) -> None:
        safe_meta = {k.lower().replace("_", "-"): v for k, v in metadata.items()}
        self._s3.copy_object(
            Bucket=self.bucket,
            Key=dest_key,
            CopySource={"Bucket": self.bucket, "Key": src_key},
            Metadata=safe_meta,
            MetadataDirective="REPLACE",
        )
        bind(log, logging.INFO, "copied", src=src_key, dest=dest_key)
