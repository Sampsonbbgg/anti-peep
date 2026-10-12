import os
import urllib.request
from typing import Tuple

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

    def close(self) -> None:
        self._detector = None
        self._recognizer = None
