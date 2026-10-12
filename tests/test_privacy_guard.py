import unittest

from anti_peep.core.analysis_worker import Analysis
from anti_peep.services.privacy_guard import PrivacyGuard


def cfg():
    return {
        "privacy_guard": {
            "enabled": True,
            "peep": {"enabled": True, "min_faces": 2, "action": "blur"},
            "stranger": {"enabled": True, "hold_seconds": 3, "action": "cover"},
            "blur": {"enabled": True, "hold_seconds": 1.5, "action": "blur"},
            "looking": {"max_yaw_deg": 25},
        }
    }


def A(count=0, owner=False, stranger=False, yaw=None, pitch=None):
    return Analysis(
        face_count=count,
        has_owner=owner,
        has_stranger=stranger,
        owner_yaw=yaw,
        owner_pitch=pitch,
    )


class PrivacyGuardTests(unittest.TestCase):
    def test_peep_triggers_blur_immediately(self):
        g = PrivacyGuard(cfg())
        d = g.update(
            A(count=2, owner=True, stranger=True, yaw=0), now=100, session_locked=False
        )
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

    def test_away_blurs_after_hold(self):
        g = PrivacyGuard(cfg())
        self.assertEqual("none", g.update(A(count=0), now=0, session_locked=False).mode)
        self.assertEqual("none", g.update(A(count=0), now=1, session_locked=False).mode)
        d = g.update(A(count=0), now=1.5, session_locked=False)
        self.assertEqual("blur", d.mode)
        self.assertEqual("away", d.reason)

    def test_owner_looking_keeps_clear(self):
        g = PrivacyGuard(cfg())
        self.assertEqual(
            "none", g.update(A(count=1, owner=True, yaw=10), now=0, session_locked=False).mode
        )
        self.assertEqual(
            "none", g.update(A(count=1, owner=True, yaw=-20), now=5, session_locked=False).mode
        )

    def test_owner_not_looking_blurs(self):
        g = PrivacyGuard(cfg())
        self.assertEqual(
            "none", g.update(A(count=1, owner=True, yaw=40), now=0, session_locked=False).mode
        )
        d = g.update(A(count=1, owner=True, yaw=40), now=2, session_locked=False)
        self.assertEqual("blur", d.mode)
        self.assertEqual("not_looking", d.reason)
        # 转回屏幕 → 立即清晰
        self.assertEqual(
            "none",
            g.update(A(count=1, owner=True, yaw=0), now=2.1, session_locked=False).mode,
        )

    def test_unknown_pose_treated_as_looking(self):
        g = PrivacyGuard(cfg())
        self.assertEqual(
            "none", g.update(A(count=1, owner=True, yaw=None), now=0, session_locked=False).mode
        )
        self.assertEqual(
            "none", g.update(A(count=1, owner=True, yaw=None), now=5, session_locked=False).mode
        )

    def test_not_enrolled_skips_owner_rules(self):
        g = PrivacyGuard(cfg(), owner_enrolled=False)
        self.assertEqual("none", g.update(A(count=0), now=0, session_locked=False).mode)
        self.assertEqual("none", g.update(A(count=0), now=99, session_locked=False).mode)

    def test_disabled_when_locked(self):
        g = PrivacyGuard(cfg())
        g.update(A(count=0), now=0, session_locked=False)
        d = g.update(A(count=0), now=999, session_locked=True)
        self.assertEqual("none", d.mode)


if __name__ == "__main__":
    unittest.main()
