import unittest

from anti_peep.services.screen_shield import blur_radius_at, ease_in_out


class EaseInOutTests(unittest.TestCase):
    def test_endpoints(self):
        self.assertEqual(0.0, ease_in_out(0.0))
        self.assertEqual(1.0, ease_in_out(1.0))

    def test_midpoint(self):
        self.assertAlmostEqual(0.5, ease_in_out(0.5))

    def test_clamped_out_of_range(self):
        self.assertEqual(0.0, ease_in_out(-1.0))
        self.assertEqual(1.0, ease_in_out(2.0))

    def test_monotonic_nondecreasing(self):
        vals = [ease_in_out(i / 20.0) for i in range(21)]
        for a, b in zip(vals, vals[1:]):
            self.assertLessEqual(a, b)


class BlurRadiusAtTests(unittest.TestCase):
    def test_starts_sharp_and_ends_at_target(self):
        self.assertEqual(0, blur_radius_at(10, 0.0))
        self.assertEqual(10, blur_radius_at(10, 1.0))

    def test_monotonic_and_bounded(self):
        vals = [blur_radius_at(10, i / 10.0) for i in range(11)]
        for a, b in zip(vals, vals[1:]):
            self.assertLessEqual(a, b)
        self.assertTrue(all(0 <= v <= 10 for v in vals))

    def test_clamped(self):
        self.assertEqual(0, blur_radius_at(10, -0.5))
        self.assertEqual(10, blur_radius_at(10, 5.0))


if __name__ == "__main__":
    unittest.main()
