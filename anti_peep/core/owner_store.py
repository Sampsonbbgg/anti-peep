import json
import os
from typing import List, Tuple

import numpy as np


def _normalize(vec) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm < 1e-8:
        return arr
    return arr / norm


class OwnerStore:
    """主人人脸特征库：JSON 存储，L2 归一化后做余弦比对。"""

    def __init__(self, path: str, threshold: float = 0.363):
        self.path = path
        self.threshold = float(threshold)
        self._embs: List[np.ndarray] = []

    @property
    def count(self) -> int:
        return len(self._embs)

    @property
    def is_empty(self) -> bool:
        return not self._embs

    def load(self) -> None:
        self._embs = []
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.threshold = float(data.get("threshold", self.threshold))
            for row in data.get("embeddings", []):
                self._embs.append(_normalize(row))
        except Exception:
            self._embs = []

    def save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        data = {
            "threshold": self.threshold,
            "embeddings": [emb.tolist() for emb in self._embs],
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def add(self, emb) -> None:
        self._embs.append(_normalize(emb))

    def clear(self) -> None:
        self._embs = []

    def match(self, emb) -> Tuple[bool, float]:
        if not self._embs:
            return False, 0.0
        query = _normalize(emb)
        sims = [float(np.dot(query, owner)) for owner in self._embs]
        best = max(sims)
        return best >= self.threshold, best
