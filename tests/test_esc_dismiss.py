import unittest

from anti_peep.services.esc_dismiss import next_override, effective_mode


class EscDismissTests(unittest.TestCase):
    def test_override_not_active_stays_false(self):
        self.assertFalse(next_override(False, "none"))
        self.assertFalse(next_override(False, "blur"))
        self.assertFalse(next_override(False, "cover"))

    def test_override_holds_while_trigger_persists(self):
        self.assertTrue(next_override(True, "blur"))
        self.assertTrue(next_override(True, "cover"))

    def test_override_releases_when_scene_safe(self):
        self.assertFalse(next_override(True, "none"))

    def test_effective_mode_masks_to_none(self):
        self.assertEqual("none", effective_mode("blur", True))
        self.assertEqual("none", effective_mode("cover", True))

    def test_effective_mode_passthrough_when_no_override(self):
        self.assertEqual("blur", effective_mode("blur", False))
        self.assertEqual("cover", effective_mode("cover", False))
        self.assertEqual("none", effective_mode("none", False))


if __name__ == "__main__":
    unittest.main()
