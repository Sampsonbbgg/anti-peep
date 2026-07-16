import os
import tempfile
import unittest
from unittest.mock import patch

from moyu.platforms.windows_session import WindowsSessionState
from moyu.services.lock_screen_capture import LockScreenCaptureService
from moyu.services import snapshot


class FakeSessionState:
    def __init__(self, locked=False):
        self.locked = locked

    def is_locked(self):
        return self.locked


class LockScreenCaptureServiceTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSessionState(locked=True)
        self.saved = []
        self.config = {
            "lock_screen": {
                "enabled": True,
                "directory": "locked",
                "cooldown_seconds": 10,
            }
        }

        def saver(config, frame, section, filename_prefix):
            self.saved.append((config, frame, section, filename_prefix))
            return "locked/photo.jpg"

        self.service = LockScreenCaptureService(
            self.config,
            session_state=self.session,
            snapshot_saver=saver,
        )

    def test_captures_face_while_locked_and_obeys_cooldown(self):
        self.assertEqual("locked/photo.jpg", self.service.process("frame", True, now=100))
        self.assertIsNone(self.service.process("frame", True, now=105))
        self.assertEqual("locked/photo.jpg", self.service.process("frame", True, now=110))
        self.assertEqual(2, len(self.saved))
        self.assertEqual("lock_screen", self.saved[0][2])
        self.assertEqual("lock_screen", self.saved[0][3])

    def test_does_not_capture_without_lock_or_face(self):
        self.session.locked = False
        self.assertIsNone(self.service.process("frame", True, now=100))
        self.session.locked = True
        self.assertIsNone(self.service.process("frame", False, now=100))
        self.assertEqual([], self.saved)

    def test_unlock_resets_cooldown_for_next_lock(self):
        self.service.process("frame", True, now=100)
        self.session.locked = False
        self.service.process("frame", True, now=101)
        self.session.locked = True
        self.assertEqual("locked/photo.jpg", self.service.process("frame", True, now=102))


class WindowsSessionStateTests(unittest.TestCase):
    def test_caches_probe_result(self):
        calls = []

        def probe():
            calls.append(True)
            return True

        state = WindowsSessionState(probe=probe, cache_seconds=60)
        self.assertTrue(state.is_locked())
        self.assertTrue(state.is_locked())
        self.assertEqual(1, len(calls))


class SnapshotTests(unittest.TestCase):
    def test_relative_directory_uses_runtime_base(self):
        class FakeEncodedImage:
            @staticmethod
            def tobytes():
                return b"jpeg data"

        class FakeCv2:
            @staticmethod
            def imencode(_extension, _frame):
                return True, FakeEncodedImage()

        with tempfile.TemporaryDirectory() as temp_dir:
            config = {"lock_screen": {"enabled": True, "directory": "锁屏抓拍"}}
            with (
                patch.object(snapshot, "cv2", FakeCv2),
                patch.object(snapshot, "get_base_dir", return_value=temp_dir),
            ):
                filepath = snapshot.save_snapshot(
                    config,
                    "frame",
                    section="lock_screen",
                    filename_prefix="lock_screen",
                )

            self.assertIsNotNone(filepath)
            self.assertEqual(os.path.join(temp_dir, "锁屏抓拍"), os.path.dirname(filepath))
            self.assertTrue(os.path.exists(filepath))


if __name__ == "__main__":
    unittest.main()
