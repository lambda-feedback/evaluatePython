import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

from .s3_files import download_files, _MAX_FILE_BYTES

_URL = "https://example-bucket.s3.amazonaws.com/data.csv?X-Amz-Signature=abc"


def _fake_response(content: bytes, content_length: int | None = None, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {}
    if content_length is not None:
        resp.headers["Content-Length"] = str(content_length)

    def raise_for_status():
        if status_code >= 400:
            raise requests.exceptions.HTTPError(f"{status_code} error")

    resp.raise_for_status.side_effect = raise_for_status

    chunk_size = 65536

    def iter_content(chunk_size=chunk_size):
        for i in range(0, len(content), chunk_size):
            yield content[i:i + chunk_size]

    resp.iter_content.side_effect = iter_content
    return resp


class TestDownloadFiles(unittest.TestCase):

    def setUp(self):
        self.dest_dir = tempfile.mkdtemp()

    def test_no_files_returns_empty(self):
        self.assertEqual(download_files([], self.dest_dir), [])

    @patch("evaluation_function.s3_files.requests.get")
    def test_successful_download_writes_file(self, mock_get):
        mock_get.return_value = _fake_response(b"hello", content_length=5)

        warnings = download_files([{"url": _URL, "name": "data.csv"}], self.dest_dir)

        self.assertEqual(warnings, [])
        with open(os.path.join(self.dest_dir, "data.csv"), "rb") as f:
            self.assertEqual(f.read(), b"hello")

    @patch("evaluation_function.s3_files.requests.get")
    def test_oversized_via_header_skipped(self, mock_get):
        mock_get.return_value = _fake_response(b"x" * 10, content_length=_MAX_FILE_BYTES + 1)

        warnings = download_files([{"url": _URL, "name": "big.csv"}], self.dest_dir)

        self.assertEqual(len(warnings), 1)
        self.assertIn("big.csv", warnings[0])
        self.assertFalse(os.path.exists(os.path.join(self.dest_dir, "big.csv")))

    @patch("evaluation_function.s3_files.requests.get")
    def test_oversized_via_streaming_skipped(self, mock_get):
        # Content-Length lies (claims small), actual streamed bytes exceed the cap.
        big_content = b"x" * (_MAX_FILE_BYTES + 1)
        mock_get.return_value = _fake_response(big_content, content_length=10)

        warnings = download_files([{"url": _URL, "name": "big.csv"}], self.dest_dir)

        self.assertEqual(len(warnings), 1)
        self.assertIn("big.csv", warnings[0])
        self.assertFalse(os.path.exists(os.path.join(self.dest_dir, "big.csv")))

    @patch("evaluation_function.s3_files.requests.get")
    def test_total_size_cap_skips_later_files(self, mock_get):
        # 5 files at exactly the per-file cap: the first 4 sum to exactly
        # _MAX_TOTAL_BYTES (allowed), the 5th is skipped without a request.
        mock_get.return_value = _fake_response(b"x" * _MAX_FILE_BYTES, content_length=_MAX_FILE_BYTES)

        files = [{"url": _URL, "name": f"{i}.csv"} for i in range(5)]
        warnings = download_files(files, self.dest_dir)

        self.assertEqual(mock_get.call_count, 4)
        self.assertEqual(len(warnings), 1)
        self.assertIn("4.csv", warnings[0])

    @patch("evaluation_function.s3_files.requests.get")
    def test_http_error_skipped_others_continue(self, mock_get):
        def side_effect(url, stream, timeout):
            if url == "https://example.com/missing":
                return _fake_response(b"", status_code=404)
            return _fake_response(b"ok", content_length=2)

        mock_get.side_effect = side_effect

        files = [
            {"url": "https://example.com/missing", "name": "missing.csv"},
            {"url": "https://example.com/ok", "name": "ok.csv"},
        ]
        warnings = download_files(files, self.dest_dir)

        self.assertEqual(len(warnings), 1)
        self.assertIn("missing.csv", warnings[0])
        self.assertTrue(os.path.exists(os.path.join(self.dest_dir, "ok.csv")))

    @patch("evaluation_function.s3_files.requests.get")
    def test_network_error_skipped(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("boom")

        warnings = download_files([{"url": _URL, "name": "data.csv"}], self.dest_dir)

        self.assertEqual(len(warnings), 1)
        self.assertIn("data.csv", warnings[0])

    def test_rejects_non_https_url(self):
        for bad_url in ("http://example.com/data.csv", "file:///etc/passwd", "ftp://example.com/data.csv"):
            warnings = download_files([{"url": bad_url, "name": "data.csv"}], self.dest_dir)
            self.assertEqual(len(warnings), 1, f"expected a warning for url={bad_url!r}")

    def test_filename_validation_rejects_traversal(self):
        for bad_name in ("../evil.py", "/etc/passwd", "", ".", ".."):
            warnings = download_files([{"url": _URL, "name": bad_name}], self.dest_dir)
            self.assertEqual(len(warnings), 1, f"expected a warning for name={bad_name!r}")

    def test_legacy_filename_key_skipped_not_raised(self):
        # Reproduces the real-world crash report: client actually sends "name",
        # not the old "filename" key. A spec using the wrong/legacy key must
        # not raise KeyError — it should be skipped with a warning.
        warnings = download_files(
            [{"url": _URL, "filename": "score_utils.py", "type": "text/x-python-script", "size": 237}],
            self.dest_dir,
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("missing", warnings[0].lower())

    def test_missing_url_key_skipped_not_raised(self):
        warnings = download_files([{"name": "data.csv"}], self.dest_dir)
        self.assertEqual(len(warnings), 1)
        self.assertIn("data.csv", warnings[0])

    def test_non_dict_spec_skipped_not_raised(self):
        warnings = download_files(["not-a-dict", 42, None], self.dest_dir)
        self.assertEqual(len(warnings), 3)

    def test_empty_spec_generic_message(self):
        warnings = download_files([{}], self.dest_dir)
        self.assertEqual(len(warnings), 1)
        self.assertIn("missing", warnings[0].lower())

    @patch("evaluation_function.s3_files.requests.get")
    def test_malformed_spec_skipped_others_continue(self, mock_get):
        mock_get.return_value = _fake_response(b"ok", content_length=2)
        files = [
            {"url": _URL, "filename": "score_utils.py"},  # wrong/legacy key, missing "name"
            {"url": _URL, "name": "ok.csv"},
        ]
        warnings = download_files(files, self.dest_dir)

        self.assertEqual(len(warnings), 1)
        self.assertTrue(os.path.exists(os.path.join(self.dest_dir, "ok.csv")))


if __name__ == "__main__":
    unittest.main()
