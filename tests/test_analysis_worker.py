import unittest

from anti_peep.core.analysis_worker import FaceAnalysisWorker


class SummarizeTests(unittest.TestCase):
    def _worker(self):
        # 不触发摄像头：用 __new__ 跳过 __init__ 的重资源初始化
        w = FaceAnalysisWorker.__new__(FaceAnalysisWorker)
        w.min_faces_for_alert = 2
        return w

    def test_summary_labels_and_counts(self):
        w = self._worker()
        rows = [
            ((0, 0, 10, 10, 0.9), "owner", 0.8),
            ((20, 0, 10, 10, 0.9), "stranger", 0.1),
        ]
        analysis = w._summarize(rows)
        self.assertEqual(2, analysis.face_count)
        self.assertTrue(analysis.has_owner)
        self.assertTrue(analysis.has_stranger)
        self.assertAlmostEqual(0.8, analysis.max_owner_sim)

    def test_summary_carries_owner_pose(self):
        w = self._worker()
        rows = [
            ((0, 0, 10, 10, 0.9), "owner", 0.8, 12.0, -3.0),
            ((20, 0, 10, 10, 0.9), "stranger", 0.1, 30.0, 5.0),
        ]
        analysis = w._summarize(rows)
        self.assertTrue(analysis.has_owner)
        self.assertAlmostEqual(12.0, analysis.owner_yaw)
        self.assertAlmostEqual(-3.0, analysis.owner_pitch)

    def test_largest_owner_box_wins_pose(self):
        w = self._worker()
        rows = [
            ((0, 0, 10, 10, 0.9), "owner", 0.8, 5.0, 0.0),
            ((0, 0, 40, 40, 0.9), "owner", 0.9, 40.0, 0.0),
        ]
        analysis = w._summarize(rows)
        self.assertAlmostEqual(40.0, analysis.owner_yaw)

    def test_empty(self):
        w = self._worker()
        analysis = w._summarize([])
        self.assertEqual(0, analysis.face_count)
        self.assertFalse(analysis.has_owner)
        self.assertFalse(analysis.has_stranger)


if __name__ == "__main__":
    unittest.main()
