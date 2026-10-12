import math
import unittest

import numpy as np

from anti_peep.core.deps import cv2
from anti_peep.core.face_engine import FaceEngine, MODEL_POINTS_5, euler_from_rotation


def _rotation_matrix(axis: int, deg: float):
    rvec = np.zeros((3, 1), dtype=np.float64)
    rvec[axis, 0] = math.radians(deg)
    rmat, _ = cv2.Rodrigues(rvec)
    return rmat


class EulerMathTests(unittest.TestCase):
    def test_yaw_about_y(self):
        pitch, yaw, roll = euler_from_rotation(_rotation_matrix(1, 30))
        self.assertAlmostEqual(30.0, yaw, places=1)
        self.assertAlmostEqual(0.0, pitch, places=1)

    def test_pitch_about_x(self):
        pitch, yaw, roll = euler_from_rotation(_rotation_matrix(0, 25))
        self.assertAlmostEqual(25.0, pitch, places=1)

    def test_roll_about_z(self):
        pitch, yaw, roll = euler_from_rotation(_rotation_matrix(2, 20))
        self.assertAlmostEqual(20.0, roll, places=1)


class EstimatePoseTests(unittest.TestCase):
    """用已知姿态投影出关键点，再验证 estimate_pose 能还原朝向。"""

    WIDTH = 640
    HEIGHT = 480

    @classmethod
    def setUpClass(cls):
        cls.focal = float(max(cls.WIDTH, cls.HEIGHT))
        cls.camera = np.array(
            [
                [cls.focal, 0.0, cls.WIDTH / 2.0],
                [0.0, cls.focal, cls.HEIGHT / 2.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        cls.model6 = np.vstack(
            [MODEL_POINTS_5, np.array([[0.0, -150.0, -125.0]])]
        )

    def _row_for_pose(self, yaw_deg=0.0, pitch_deg=0.0, roll_deg=0.0):
        rvec = np.array(
            [
                math.radians(pitch_deg),
                math.radians(yaw_deg),
                math.radians(roll_deg),
            ],
            dtype=np.float64,
        )
        tvec = np.array([[0.0], [0.0], [700.0]], dtype=np.float64)
        projected, _ = cv2.projectPoints(
            self.model6, rvec, tvec, self.camera, np.zeros((4, 1))
        )
        pts = projected.reshape(-1, 2)
        row = np.zeros(15, dtype=np.float32)
        row[8], row[9] = pts[0]  # 鼻尖
        row[4], row[5] = pts[1]  # 右眼
        row[6], row[7] = pts[2]  # 左眼
        row[10], row[11] = pts[3]  # 右嘴角
        row[12], row[13] = pts[4]  # 左嘴角
        row[14] = 0.9
        return row

    def _engine(self):
        return FaceEngine.__new__(FaceEngine)

    def test_recovers_facing_yaw(self):
        shape = (self.HEIGHT, self.WIDTH, 3)
        for deg in (0.0, 20.0, 40.0, -30.0):
            with self.subTest(yaw=deg):
                pose = self._engine().estimate_pose(self._row_for_pose(yaw_deg=deg), shape)
                self.assertIsNotNone(pose)
                _pitch, yaw, _roll = pose
                self.assertAlmostEqual(deg, yaw, delta=4.0)

    def test_mirroring_negates_yaw(self):
        shape = (self.HEIGHT, self.WIDTH, 3)
        row = self._row_for_pose(yaw_deg=30.0)
        pose = self._engine().estimate_pose(row, shape)
        self.assertIsNotNone(pose)
        _p, yaw_a, _r = pose
        mirrored = row.copy()
        for i in (4, 6, 8, 10, 12):
            mirrored[i] = self.WIDTH - row[i]
        pose_m = self._engine().estimate_pose(mirrored, shape)
        self.assertIsNotNone(pose_m)
        _p, yaw_b, _r = pose_m
        self.assertAlmostEqual(yaw_a, -yaw_b, delta=4.0)


if __name__ == "__main__":
    unittest.main()
