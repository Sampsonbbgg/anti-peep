import threading
import time
from dataclasses import dataclass, field
from typing import List, Tuple

from .deps import cv2
from .face_engine import FaceEngine, LABEL_OWNER, LABEL_STRANGER


@dataclass
class Analysis:
    faces: List[Tuple[int, int, int, int, float, str, float]] = field(default_factory=list)
    face_count: int = 0
    has_owner: bool = False
    has_stranger: bool = False
    max_owner_sim: float = 0.0


class FaceAnalysisWorker(threading.Thread):
    """独占摄像头：YuNet 检测 + SFace 身份，输出稳定 Analysis。"""

    def __init__(self, config, engine: FaceEngine, cap=None):
        super().__init__(daemon=True)
        self.config = config
        self.engine = engine
        cam = config.get("camera", {})
        self.camera_index = int(config.get("camera_index", 0))
        self.backend = str(cam.get("backend", "dshow")).lower()
        self.frame_width = int(cam.get("frame_width", 0))
        self.frame_height = int(cam.get("frame_height", 0))
        self.min_area_ratio = float(cam.get("min_area_ratio", 0.01))
        self.max_area_ratio = float(cam.get("max_area_ratio", 0.6))
        self.min_faces_for_alert = int(config.get("min_faces_for_alert", 2))
        self._cap = cap
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest_frame = None
        self._latest = Analysis()

    def _open_camera(self):
        if self._cap is not None:
            return self._cap
        backend_ids = {
            "dshow": getattr(cv2, "CAP_DSHOW", None),
            "msmf": getattr(cv2, "CAP_MSMF", None),
        }
        bid = backend_ids.get(self.backend)
        cap = (
            cv2.VideoCapture(self.camera_index, bid)
            if bid is not None
            else cv2.VideoCapture(self.camera_index)
        )
        if not cap.isOpened() and bid is not None:
            cap.release()
            cap = cv2.VideoCapture(self.camera_index)
        if self.frame_width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        if self.frame_height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        return cap

    def _summarize(self, labeled) -> Analysis:
        a = Analysis(face_count=len(labeled))
        for bbox, label, sim in labeled:
            a.faces.append((*bbox, label, sim))
            if label == LABEL_OWNER:
                a.has_owner = True
                a.max_owner_sim = max(a.max_owner_sim, sim)
            elif label == LABEL_STRANGER:
                a.has_stranger = True
        return a

    def run(self):
        cap = self._open_camera()
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]
                rows = self.engine.detect(frame)
                labeled = []
                for row in rows:
                    x, y, bw, bh = (int(row[0]), int(row[1]), int(row[2]), int(row[3]))
                    score = float(row[14])
                    area_ratio = (bw * bh) / float(w * h)
                    if not (self.min_area_ratio <= area_ratio <= self.max_area_ratio):
                        continue
                    label, sim = self.engine.identify(frame, row)
                    x = max(min(x, w - 1), 0)
                    y = max(min(y, h - 1), 0)
                    bw = max(min(bw, w - x), 1)
                    bh = max(min(bh, h - y), 1)
                    labeled.append(((x, y, bw, bh, score), label, sim))
                analysis = self._summarize(labeled)
                with self._lock:
                    self._latest_frame = frame
                    self._latest = analysis
                time.sleep(0.01)
        finally:
            if cap is not None and self._cap is None:
                cap.release()

    def get_latest(self):
        with self._lock:
            return self._latest_frame, self._latest

    def stop(self):
        self._stop.set()
