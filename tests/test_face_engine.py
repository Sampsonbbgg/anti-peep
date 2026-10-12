import os
import tempfile
import unittest
from unittest.mock import patch

from anti_peep.core import face_engine


class EnsureModelsTests(unittest.TestCase):
    def test_downloads_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            calls = []

            def fake_download(url, dest):
                calls.append(url)
                with open(dest, "wb") as f:
                    f.write(b"x")

            with patch.object(face_engine, "_download", side_effect=fake_download):
                yunet, sface = face_engine.ensure_models(d)

            self.assertTrue(os.path.exists(yunet))
            self.assertTrue(os.path.exists(sface))
            self.assertEqual(2, len(calls))

    def test_skips_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            for name in (face_engine.YUNET_FILENAME, face_engine.SFACE_FILENAME):
                with open(os.path.join(d, name), "wb") as f:
                    f.write(b"x")
            with patch.object(face_engine, "_download") as dl:
                face_engine.ensure_models(d)
            dl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
