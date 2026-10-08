"""boto3 factories that work against LocalStack or real AWS.

Local mode (AWS_ENDPOINT_URL set): explicit credentials from env
(default test/test) so tests never depend on ~/.aws files.
AWS mode: named profile, no keys in code, ever.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
import botocore.client
import botocore.exceptions

from .config import Settings


def new_session(settings: Settings) -> boto3.Session:
    if settings.is_local:
        return boto3.Session(
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
            region_name=settings.aws_region,
        )
    return boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region)


def client(settings: Settings, service: str) -> Any:
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
