import os
from typing import TypedDict

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

_MAX_FILE_BYTES = 5 * 1024 * 1024
_MAX_TOTAL_BYTES = 20 * 1024 * 1024
_DOWNLOAD_TIMEOUT = 10


class FileSpec(TypedDict):
    key: str
    filename: str


class FileDownloadError(Exception):
    """Raised for whole-request configuration problems (e.g. missing bucket env var)."""
    pass


def _s3_client():
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION", "eu-west-2"),
        config=Config(
            connect_timeout=_DOWNLOAD_TIMEOUT,
            read_timeout=_DOWNLOAD_TIMEOUT,
            retries={"max_attempts": 2},
        ),
    )


def _get_bucket_name() -> str:
    bucket = os.environ.get("S3_FILES_BUCKET")
    if not bucket:
        raise FileDownloadError("S3_FILES_BUCKET environment variable is not set")
    return bucket


def _valid_filename(filename: str) -> bool:
    if not filename or filename in (".", ".."):
        return False
    return os.path.basename(filename) == filename


def download_files(files: list[FileSpec], dest_dir: str) -> list[str]:
    """Download each file into dest_dir.

    Returns a list of warning strings for files that were skipped (missing,
    too large, or errored) — never raises for per-file problems, only for
    whole-config problems (missing bucket env var).
    """
    if not files:
        return []

    bucket = _get_bucket_name()
    client = _s3_client()

    warnings: list[str] = []
    total_bytes = 0

    for spec in files:
        key = spec["key"]
        filename = spec["filename"]

        if not _valid_filename(filename):
            warnings.append(f"File '{filename}' has an invalid filename and was not made available.")
            continue

        real_dest_dir = os.path.realpath(dest_dir)
        target = os.path.realpath(os.path.join(real_dest_dir, filename))
        if os.path.commonpath([target, real_dest_dir]) != real_dest_dir:
            warnings.append(f"File '{filename}' has an invalid filename and was not made available.")
            continue

        try:
            head = client.head_object(Bucket=bucket, Key=key)
        except ClientError as e:
            warnings.append(f"File '{filename}' could not be found or accessed ({e}).")
            continue

        size = head.get("ContentLength", 0)
        if size > _MAX_FILE_BYTES:
            warnings.append(
                f"File '{filename}' exceeds the {_MAX_FILE_BYTES // (1024 * 1024)}MB size limit "
                "and was not made available."
            )
            continue
        if total_bytes + size > _MAX_TOTAL_BYTES:
            warnings.append(
                f"File '{filename}' was skipped because it would exceed the total "
                f"{_MAX_TOTAL_BYTES // (1024 * 1024)}MB size limit for this run."
            )
            continue

        try:
            client.download_file(bucket, key, target)
        except ClientError as e:
            warnings.append(f"File '{filename}' could not be downloaded ({e}).")
            continue

        total_bytes += size

    return warnings
