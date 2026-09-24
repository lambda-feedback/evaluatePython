import os
from typing import TypedDict
from urllib.parse import urlparse

import requests

_MAX_FILE_BYTES = 5 * 1024 * 1024
_MAX_TOTAL_BYTES = 20 * 1024 * 1024
_DOWNLOAD_TIMEOUT = 10
_CHUNK_SIZE = 65536


class FileSpec(TypedDict):
    url: str
    name: str


def _valid_filename(filename: str) -> bool:
    if not filename or filename in (".", ".."):
        return False
    return os.path.basename(filename) == filename


class _FileTooLarge(Exception):
    pass


def _download_one(url: str, target: str, remaining_budget: int) -> int:
    """Stream url into target. Returns bytes written.

    Raises _FileTooLarge (and removes any partial file) if the download
    exceeds _MAX_FILE_BYTES or remaining_budget, or requests.RequestException
    for network/HTTP errors — both handled by the caller.
    """
    resp = requests.get(url, stream=True, timeout=_DOWNLOAD_TIMEOUT)
    resp.raise_for_status()

    content_length = resp.headers.get("Content-Length")
    cap = min(_MAX_FILE_BYTES, remaining_budget)
    if content_length is not None and int(content_length) > cap:
        raise _FileTooLarge()

    written = 0
    try:
        with open(target, "wb") as f:
            for chunk in resp.iter_content(chunk_size=_CHUNK_SIZE):
                written += len(chunk)
                if written > cap:
                    raise _FileTooLarge()
                f.write(chunk)
    except _FileTooLarge:
        if os.path.exists(target):
            os.unlink(target)
        raise
    return written


def download_files(files: list[FileSpec], dest_dir: str) -> list[str]:
    """Download each file into dest_dir.

    Returns a list of warning strings for files that were skipped (invalid
    filename/URL, too large, or errored) — never raises.
    """
    if not files:
        return []

    real_dest_dir = os.path.realpath(dest_dir)
    warnings: list[str] = []
    total_bytes = 0

    for spec in files:
        if not isinstance(spec, dict):
            warnings.append(
                "One of the provided files is missing required information (url/name) and was skipped."
            )
            continue

        url = spec.get("url")
        filename = spec.get("name")
        has_url = isinstance(url, str) and bool(url)
        has_filename = isinstance(filename, str) and bool(filename)

        if not has_url or not has_filename:
            if has_filename:
                warnings.append(f"File '{filename}' is missing a valid URL and was not made available.")
            else:
                warnings.append(
                    "One of the provided files is missing required information (url/name) and was skipped."
                )
            continue

        if not _valid_filename(filename):
            warnings.append(f"File '{filename}' has an invalid filename and was not made available.")
            continue

        target = os.path.realpath(os.path.join(real_dest_dir, filename))
        if os.path.commonpath([target, real_dest_dir]) != real_dest_dir:
            warnings.append(f"File '{filename}' has an invalid filename and was not made available.")
            continue

        if urlparse(url).scheme != "https":
            warnings.append(f"File '{filename}' has an invalid URL and was not made available.")
            continue

        remaining_budget = _MAX_TOTAL_BYTES - total_bytes
        if remaining_budget <= 0:
            warnings.append(
                f"File '{filename}' was skipped because it would exceed the total "
                f"{_MAX_TOTAL_BYTES // (1024 * 1024)}MB size limit for this run."
            )
            continue

        try:
            written = _download_one(url, target, remaining_budget)
        except _FileTooLarge:
            warnings.append(
                f"File '{filename}' exceeds the {_MAX_FILE_BYTES // (1024 * 1024)}MB size limit "
                "and was not made available."
            )
            continue
        except requests.exceptions.RequestException as e:
            warnings.append(f"File '{filename}' could not be downloaded ({e}).")
            continue

        total_bytes += written

    return warnings
