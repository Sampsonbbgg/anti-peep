import unittest

from moyu.core.config_loader import load_config


class ConfigPrivacyTests(unittest.TestCase):
    def test_privacy_defaults_present(self):
        c = load_config()
        pg = c["privacy_guard"]
        self.assertTrue(pg["enabled"])
        self.assertEqual(2, pg["peep"]["min_faces"])
        self.assertEqual("blur", pg["peep"]["action"])
        self.assertEqual("cover", pg["stranger"]["action"])
        self.assertEqual(60, pg["away"]["seconds"])
        self.assertIn("identity", c)
        self.assertAlmostEqual(0.363, c["identity"]["match_threshold"], places=3)


if __name__ == "__main__":
    unittest.main()
