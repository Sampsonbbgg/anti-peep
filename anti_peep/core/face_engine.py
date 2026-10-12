import math
import os
import urllib.request
from typing import Optional, Tuple

import numpy as np

from .deps import cv2

YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
SFACE_FILENAME = "face_recognition_sface_2021dec.onnx"
YUNET_URL = (
    "https://hf-mirror.com/opencv/face_detection_yunet/resolve/main/" + YUNET_FILENAME
)
SFACE_URL = (
    "https://hf-mirror.com/opencv/face_recognition_sface/resolve/main/" + SFACE_FILENAME
)
LABEL_OWNER = "owner"
LABEL_STRANGER = "stranger"
LABEL_UNKNOWN = "unknown"

# 通用 3D 五点人脸模型，行顺序与 YuNet 关键点一致：
# 鼻尖、右眼、左眼、右嘴角、左嘴角。单位为任意尺度，焦距同步近似即可。
MODEL_POINTS_5 = np.array(
    [
        [0.0, 0.0, 0.0],  # 鼻尖
        [225.0, 170.0, -135.0],  # 右眼
        [-225.0, 170.0, -135.0],  # 左眼
        [150.0, -150.0, -125.0],  # 右嘴角
        [-150.0, -150.0, -125.0],  # 左嘴角
    ],
    dtype=np.float64,
)


def euler_from_rotation(rmat) -> Tuple[float, float, float]:
    """由旋转矩阵解出 (pitch, yaw, roll)，单位：度。

    pitch 绕 X（抬头低头）、yaw 绕 Y（左右转头）、roll 绕 Z（歪头）。
    """
    sy = math.sqrt(float(rmat[0, 0]) ** 2 + float(rmat[1, 0]) ** 2)
    if sy > 1e-6:
        pitch = math.degrees(math.atan2(float(rmat[2, 1]), float(rmat[2, 2])))
        yaw = math.degrees(math.atan2(-float(rmat[2, 0]), sy))
        roll = math.degrees(math.atan2(float(rmat[1, 0]), float(rmat[0, 0])))
    else:
        pitch = math.degrees(math.atan2(-float(rmat[1, 2]), float(rmat[1, 1])))
        yaw = math.degrees(math.atan2(-float(rmat[2, 0]), sy))
        roll = 0.0
    return pitch, yaw, roll


def _download(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    tmp = dest + ".part"
    with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as out:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
    os.replace(tmp, dest)


def ensure_models(models_dir: str) -> Tuple[str, str]:
    """确保 YuNet / SFace 模型存在，缺失时从 hf-mirror 下载，返回两者路径。"""
    yunet = os.path.join(models_dir, YUNET_FILENAME)
    sface = os.path.join(models_dir, SFACE_FILENAME)
    if not os.path.exists(yunet):
        _download(YUNET_URL, yunet)
    if not os.path.exists(sface):
        _download(SFACE_URL, sface)
    return yunet, sface


class FaceEngine:
    """YuNet 人脸检测 + SFace 特征与主人比对。"""

    def __init__(self, models_dir, owner_store, det_size=(640, 640)):
        self.models_dir = models_dir
        self.owner_store = owner_store
        self.det_size = tuple(det_size)
        self._detector = None
        self._recognizer = None

    def load(self) -> bool:
        if cv2 is None:
            return False
        yunet, sface = ensure_models(self.models_dir)
        self._detector = cv2.FaceDetectorYN.create(
            yunet, "", self.det_size, 0.7, 0.3, 5000
        )
        self._recognizer = cv2.FaceRecognizerSF.create(sface, "")
        return True

    def detect(self, frame_bgr) -> np.ndarray:
        if self._detector is None:
            return np.zeros((0, 15), dtype=np.float32)
        h, w = frame_bgr.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(frame_bgr)
        if faces is None:
            return np.zeros((0, 15), dtype=np.float32)
        return faces

    def feature(self, frame_bgr, row) -> np.ndarray:
        aligned = self._recognizer.alignCrop(frame_bgr, row)
        feat = self._recognizer.feature(aligned).reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(feat))
        return feat / norm if norm > 1e-8 else feat

    def identify(self, frame_bgr, row) -> Tuple[str, float]:
        if self.owner_store is None or self.owner_store.is_empty:
            return LABEL_UNKNOWN, 0.0
        emb = self.feature(frame_bgr, row)
        is_owner, sim = self.owner_store.match(emb)
        return (LABEL_OWNER if is_owner else LABEL_STRANGER), sim

    def estimate_pose(self, row, frame_shape) -> Optional[Tuple[float, float, float]]:
        """由 YuNet 五点估计头部朝向，返回 (pitch, yaw, roll) 度；无法解算返回 None。

        使用通用五点 3D 模型 + solvePnP，焦距近似取画面长边（无相机标定）。
        左右转头(yaw)较可靠；俯仰(pitch)偏粗，仅作参考。
        """
        if cv2 is None:
            return None
        nose = (float(row[8]), float(row[9]))
        reye = (float(row[4]), float(row[5]))
        leye = (float(row[6]), float(row[7]))
        rmouth = (float(row[10]), float(row[11]))
        lmouth = (float(row[12]), float(row[13]))
        mouth_center = ((rmouth[0] + lmouth[0]) / 2.0, (rmouth[1] + lmouth[1]) / 2.0)
        # DLT 需要至少 6 个对应点，补一个嘴部中心（与模型嘴中对应）。
        image_points = np.array(
            [nose, reye, leye, rmouth, lmouth, mouth_center], dtype=np.float64
        )
        model_points = np.vstack(
            [MODEL_POINTS_5, np.array([[0.0, -150.0, -125.0]], dtype=np.float64)]
        )
        h, w = frame_shape[:2]
        focal = float(max(w, h))
        camera = np.array(
            [[focal, 0.0, w / 2.0], [0.0, focal, h / 2.0], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        dist = np.zeros((4, 1), dtype=np.float64)
        # 五点近共面，ITERATIVE 在部分角度会收敛到镜像解；EPNP 稳定无歧义。
        ok, rvec, _tvec = cv2.solvePnP(
            model_points, image_points, camera, dist, flags=cv2.SOLVEPNP_EPNP
        )
        if not ok:
            return None
        rmat, _ = cv2.Rodrigues(rvec)
        return euler_from_rotation(rmat)

    def close(self) -> None:
        self._detector = None
        self._recognizer = None
