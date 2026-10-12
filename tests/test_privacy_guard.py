import unittest

from anti_peep.core.analysis_worker import Analysis
from anti_peep.services.privacy_guard import PrivacyGuard


def cfg():
    return {
        "privacy_guard": {
            "enabled": True,
            "peep": {"enabled": True, "min_faces": 2, "action": "blur"},
            "stranger": {"enabled": True, "hold_seconds": 3, "action": "cover"},
            "away": {"enabled": True, "seconds": 60, "action": "cover"},
        }
    }


def A(count=0, owner=False, stranger=False):
    return Analysis(face_count=count, has_owner=owner, has_stranger=stranger)


class PrivacyGuardTests(unittest.TestCase):
    def test_peep_triggers_blur(self):
        g = PrivacyGuard(cfg())
        d = g.update(A(count=2, owner=True, stranger=True), now=100, session_locked=False)
        self.assertEqual("blur", d.mode)
        self.assertEqual("peep", d.reason)

    def test_stranger_hold_then_cover(self):
        g = PrivacyGuard(cfg())
        self.assertEqual(
            "none", g.update(A(count=1, stranger=True), now=0, session_locked=False).mode
        )
        self.assertEqual(
            "none", g.update(A(count=1, stranger=True), now=2, session_locked=False).mode
        )
        d = g.update(A(count=1, stranger=True), now=3, session_locked=False)
        self.assertEqual("cover", d.mode)
        self.assertEqual("stranger", d.reason)
        self.assertEqual("none", g.update(A(count=0), now=4, session_locked=False).mode)

    def test_away_then_cover_and_release_on_owner(self):
        g = PrivacyGuard(cfg())
        self.assertEqual("none", g.update(A(count=0), now=0, session_locked=False).mode)
        self.assertEqual("none", g.update(A(count=0), now=59, session_locked=False).mode)
        d = g.update(A(count=0), now=60, session_locked=False)
        self.assertEqual("cover", d.mode)
        self.assertEqual("away", d.reason)
        self.assertEqual(
            "none", g.update(A(count=1, owner=True), now=61, session_locked=False).mode
        )

    def test_disabled_when_locked(self):
        g = PrivacyGuard(cfg())
        g.update(A(count=0), now=0, session_locked=False)
        d = g.update(A(count=0), now=999, session_locked=True)
        self.assertEqual("none", d.mode)


if __name__ == "__main__":
    unittest.main()
