import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from .s3_files import download_files, FileDownloadError, _MAX_FILE_BYTES


def _client_error():
    return ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")


class TestDownloadFiles(unittest.TestCase):

    def setUp(self):
        self.dest_dir = tempfile.mkdtemp()
        self.env_patcher = patch.dict(os.environ, {"S3_FILES_BUCKET": "test-bucket"})
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def test_no_files_returns_empty_without_client(self):
        warnings = download_files([], self.dest_dir)
        self.assertEqual(warnings, [])

    @patch("evaluation_function.s3_files.boto3.client")
    def test_successful_download_writes_file(self, mock_client_factory):
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentLength": 10}

        def fake_download(bucket, key, target):
            with open(target, "w") as f:
                f.write("hello")

        mock_client.download_file.side_effect = fake_download
        mock_client_factory.return_value = mock_client

        warnings = download_files([{"key": "data.csv", "filename": "data.csv"}], self.dest_dir)

        self.assertEqual(warnings, [])
        with open(os.path.join(self.dest_dir, "data.csv")) as f:
            self.assertEqual(f.read(), "hello")

    @patch("evaluation_function.s3_files.boto3.client")
    def test_oversized_file_skipped(self, mock_client_factory):
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentLength": _MAX_FILE_BYTES + 1}
        mock_client_factory.return_value = mock_client

        warnings = download_files([{"key": "big.csv", "filename": "big.csv"}], self.dest_dir)

        self.assertEqual(len(warnings), 1)
        self.assertIn("big.csv", warnings[0])
        mock_client.download_file.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.dest_dir, "big.csv")))

    @patch("evaluation_function.s3_files.boto3.client")
    def test_total_size_cap_skips_later_files(self, mock_client_factory):
        # 5 files at exactly the per-file cap: the first 4 sum to exactly
        # _MAX_TOTAL_BYTES (allowed), the 5th would push over it (skipped).
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentLength": _MAX_FILE_BYTES}
        mock_client_factory.return_value = mock_client

        files = [{"key": f"{i}.csv", "filename": f"{i}.csv"} for i in range(5)]
        warnings = download_files(files, self.dest_dir)

        self.assertEqual(mock_client.download_file.call_count, 4)
        self.assertEqual(len(warnings), 1)
        self.assertIn("4.csv", warnings[0])

    def test_missing_bucket_env_var_raises_only_when_files_present(self):
        self.env_patcher.stop()
        try:
            with self.assertRaises(FileDownloadError):
                download_files([{"key": "data.csv", "filename": "data.csv"}], self.dest_dir)
            self.assertEqual(download_files([], self.dest_dir), [])
        finally:
            self.env_patcher.start()

    @patch("evaluation_function.s3_files.boto3.client")
    def test_missing_s3_object_skipped_others_continue(self, mock_client_factory):
        mock_client = MagicMock()

        def fake_head(Bucket, Key):
            if Key == "missing.csv":
                raise _client_error()
            return {"ContentLength": 5}

        mock_client.head_object.side_effect = fake_head

        def fake_download(bucket, key, target):
            with open(target, "w") as f:
                f.write("ok")

        mock_client.download_file.side_effect = fake_download
        mock_client_factory.return_value = mock_client

        files = [
            {"key": "missing.csv", "filename": "missing.csv"},
            {"key": "ok.csv", "filename": "ok.csv"},
        ]
        warnings = download_files(files, self.dest_dir)

        self.assertEqual(len(warnings), 1)
        self.assertIn("missing.csv", warnings[0])
        self.assertTrue(os.path.exists(os.path.join(self.dest_dir, "ok.csv")))

    @patch("evaluation_function.s3_files.boto3.client")
    def test_download_error_skipped(self, mock_client_factory):
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentLength": 5}
        mock_client.download_file.side_effect = _client_error()
        mock_client_factory.return_value = mock_client

        warnings = download_files([{"key": "data.csv", "filename": "data.csv"}], self.dest_dir)

        self.assertEqual(len(warnings), 1)
        self.assertIn("data.csv", warnings[0])

    def test_filename_validation_rejects_traversal(self):
        for bad_name in ("../evil.py", "/etc/passwd", "", ".", ".."):
            warnings = download_files([{"key": "k", "filename": bad_name}], self.dest_dir)
            self.assertEqual(len(warnings), 1, f"expected a warning for filename={bad_name!r}")


if __name__ == "__main__":
    unittest.main()
