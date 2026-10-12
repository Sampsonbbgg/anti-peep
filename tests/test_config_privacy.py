import unittest

from anti_peep.core.config_loader import load_config


class ConfigPrivacyTests(unittest.TestCase):
    def test_privacy_defaults_present(self):
        c = load_config()
        pg = c["privacy_guard"]
        self.assertTrue(pg["enabled"])
        self.assertEqual(2, pg["peep"]["min_faces"])
        self.assertEqual("blur", pg["peep"]["action"])
        self.assertEqual("cover", pg["stranger"]["action"])
        self.assertEqual(1.5, pg["blur"]["hold_seconds"])
        self.assertEqual("blur", pg["blur"]["action"])
        self.assertEqual(25, pg["looking"]["max_yaw_deg"])
        self.assertEqual(10, pg["shield"]["blur_radius"])
        self.assertEqual(350, pg["shield"]["blur_anim_ms"])
        self.assertNotIn("away", pg)
        self.assertIn("identity", c)
        self.assertAlmostEqual(0.363, c["identity"]["match_threshold"], places=3)


if __name__ == "__main__":
    unittest.main()
