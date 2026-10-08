"""boto3 factories that work against S3-compatible stores or real AWS.

Local mode (AWS_ENDPOINT_URL set): explicit credentials from env
(default minioadmin/minioadmin) so tests never depend on ~/.aws files.
Path-style addressing is forced locally: required by MinIO and harmless
elsewhere. AWS mode: named profile, no keys in code, ever.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
import botocore.client
import botocore.config
import botocore.exceptions

from .config import Settings


def new_session(settings: Settings) -> boto3.Session:
    if settings.is_local:
        return boto3.Session(
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            region_name=settings.aws_region,
        )
    return boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region)


def client(settings: Settings, service: str) -> Any:
    if settings.is_local:
        cfg = botocore.config.Config(s3={"addressing_style": "path"})
        return new_session(settings).client(service, endpoint_url=settings.endpoint_url, config=cfg)
    return new_session(settings).client(service, endpoint_url=settings.endpoint_url)


def is_retryable(exc: Exception) -> bool:
    if isinstance(exc, botocore.exceptions.EndpointConnectionError | ConnectionError):
        return True
    if isinstance(exc, botocore.exceptions.ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        return code in {
            "Throttling",
            "ThrottlingException",
            "RequestTimeout",
            "InternalError",
            "ServiceUnavailable",
        }
    return False
