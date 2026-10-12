import unittest

from moyu.services import monitors


class MonitorTests(unittest.TestCase):
    def test_parses_rects(self):
        fake = [(0, 0, 1920, 1080), (0, -1080, 1920, 1080)]
        self.assertEqual(fake, monitors._normalize(fake))

    def test_empty_fallback_primary(self):
        self.assertEqual([(0, 0, 800, 600)], monitors._normalize([], primary=(800, 600)))

    def test_zero_size_filtered(self):
        self.assertEqual([(0, 0, 800, 600)], monitors._normalize([(0, 0, 0, 5)], primary=(800, 600)))


if __name__ == "__main__":
    unittest.main()
