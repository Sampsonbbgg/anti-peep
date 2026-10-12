# 魔芋 MoYu 视觉防护扩展 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在魔芋 MoYu 上新增"人脸身份识别 + 视觉防护（模糊/遮屏）"链路，实现多人偷看→全屏模糊、陌生人/人离开→全屏遮屏、抓拍留证。

**Architecture:** 用 OpenCV YuNet+SFace 做人脸检测与身份比对，替代 MediaPipe 承担检测；新增 `PrivacyGuard` 状态机把"人脸状态"决策为"防护模式"，由 `ScreenShield` 用多显示器无边框置顶窗口呈现；主循环在 `ui_app` 中编排。

**Tech Stack:** Python 3.14、opencv-contrib-python 5.x（YuNet/SFace）、Pillow（ImageGrab/GaussianBlur）、pywin32（窗口样式）、tkinter（遮罩窗口）、unittest。

**Spec:** `docs/superpowers/specs/2026-10-12-moyu-visual-privacy-design.md`

## Global Constraints

- 运行环境：Windows，仓库根 `D:\anti-peep\moyu`，虚拟环境 `.venv`（Python 3.14）。
- 测试框架：`unittest`（与现有 `tests/` 保持一致），运行方式 `.venv\Scripts\python.exe -m unittest discover -s tests`。
- 模型下载源固定为 `hf-mirror.com`（`raw.githubusercontent.com`/`huggingface.co` 在本机不可达）。
- 身份特征维度 128，做 L2 归一化；主人判定默认余弦阈值 `0.363`。
- 不真锁 Windows；防护仅"视觉"（模糊/遮屏）。
- 抓拍复用 `moyu/services/snapshot.py` 的 `save_snapshot`。
- 提交/推送需用户明确同意；计划中的 commit 步骤为可选项，执行前询问。

---

### Task 1: 主人人脸库 OwnerStore

**Files:**
- Create: `moyu/core/owner_store.py`
- Test: `tests/test_owner_store.py`

**Interfaces:**
- Produces:
  - `OwnerStore(path: str, threshold: float = 0.363)`
  - `.load() -> None`、`.save() -> None`、`.add(emb: np.ndarray) -> None`、`.clear() -> None`
  - `.count -> int`、`.is_empty -> bool`
  - `.match(emb: np.ndarray) -> tuple[bool, float]`（返回是否主人、最高相似度）
  - 特征一律 L2 归一化后存储与比对。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_owner_store.py
import os, tempfile, unittest
import numpy as np
from moyu.core.owner_store import OwnerStore


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


class OwnerStoreTests(unittest.TestCase):
    def test_match_owner_and_stranger(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "owner_faces.json")
            store = OwnerStore(path, threshold=0.363)
            a = _unit([1, 0, 0, 0])
            store.add(a)
            store.save()
            store2 = OwnerStore(path, threshold=0.363)
            store2.load()
            self.assertEqual(1, store2.count)
            near = _unit([0.99, 0.01, 0, 0])
            far = _unit([0, 1, 0, 0])
            is_owner, sim = store2.match(near)
            self.assertTrue(is_owner)
            self.assertGreater(sim, 0.36)
            self.assertFalse(store2.match(far)[0])

    def test_empty_store_never_matches(self):
        with tempfile.TemporaryDirectory() as d:
            store = OwnerStore(os.path.join(d, "o.json"))
            self.assertTrue(store.is_empty)
            self.assertEqual((False, 0.0), store.match(_unit([1, 0])))
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m unittest tests.test_owner_store -v`
Expected: FAIL（`ModuleNotFoundError: moyu.core.owner_store`）

- [ ] **Step 3: 实现 OwnerStore**

```python
# moyu/core/owner_store.py
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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python.exe -m unittest tests.test_owner_store -v`
Expected: PASS（2 tests）

- [ ] **Step 5: 提交（可选，需用户同意）**

```bash
git add moyu/core/owner_store.py tests/test_owner_store.py
git commit -m "feat: add OwnerStore for owner face embeddings"
```

---

### Task 2: FaceEngine（YuNet 检测 + SFace 特征）+ 模型下载

**Files:**
- Create: `moyu/core/face_engine.py`
- Test: `tests/test_face_engine.py`

**Interfaces:**
- Consumes: `OwnerStore`（Task 1）。
- Produces:
  - 常量 `YUNET_FILENAME`、`SFACE_FILENAME`、`YUNET_URL`、`SFACE_URL`
  - `ensure_models(models_dir: str) -> tuple[str, str]`（返回 YuNet/SFace 路径，缺失则下载）
  - `FaceEngine(models_dir: str, owner_store: OwnerStore, det_size=(640, 640))`
  - `.load() -> bool`、`.detect(frame_bgr) -> np.ndarray`（(N,15) 行，空为 shape (0,15)）
  - `.feature(frame_bgr, row) -> np.ndarray`（128 维归一化）
  - `.identify(frame_bgr, row) -> tuple[str, float]`（label ∈ {owner, stranger, unknown}）
  - `.close() -> None`

- [ ] **Step 1: 写失败测试**（不依赖真实模型/摄像头：mock `cv2`）

```python
# tests/test_face_engine.py
import os, tempfile, unittest, urllib.request
from unittest.mock import patch
import numpy as np

from moyu.core import face_engine
from moyu.core.owner_store import OwnerStore


class EnsureModelsTests(unittest.TestCase):
    def test_downloads_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            calls = []

            def fake_download(url, dest):
                calls.append(url)
                with open(dest, "wb") as f:
                    f.write(b"x")

            with patch.object(face_engine, "_download", side_effect=fake_download):
                yunet, sface = face_engine.ensure_models(d)

            self.assertTrue(os.path.exists(yunet))
            self.assertTrue(os.path.exists(sface))
            self.assertEqual(2, len(calls))

    def test_skips_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            for name in (face_engine.YUNET_FILENAME, face_engine.SFACE_FILENAME):
                with open(os.path.join(d, name), "wb") as f:
                    f.write(b"x")
            with patch.object(face_engine, "_download") as dl:
                face_engine.ensure_models(d)
            dl.assert_not_called()
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m unittest tests.test_face_engine -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 FaceEngine 与下载**

```python
# moyu/core/face_engine.py
import os
import urllib.request
from typing import Tuple

import numpy as np

from .deps import cv2

YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
SFACE_FILENAME = "face_recognition_sface_2021dec.onnx"
YUNET_URL = ("https://hf-mirror.com/opencv/face_detection_yunet/resolve/main/"
             + YUNET_FILENAME)
SFACE_URL = ("https://hf-mirror.com/opencv/face_recognition_sface/resolve/main/"
             + SFACE_FILENAME)
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
            yunet, "", self.det_size, 0.7, 0.3, 5000)
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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python.exe -m unittest tests.test_face_engine -v`
Expected: PASS

- [ ] **Step 5: 冒烟（真实模型，联网）**

```bash
.venv\Scripts\python.exe -c "from moyu.core.face_engine import ensure_models; print(ensure_models('models'))"
```
Expected: 打印两个模型路径，`models/` 下出现 232KB 与 38MB 的 onnx。

- [ ] **Step 6: 提交（可选）**

```bash
git add moyu/core/face_engine.py tests/test_face_engine.py
git commit -m "feat: add FaceEngine (YuNet+SFace) and model auto-download"
```

---

### Task 3: FaceAnalysisWorker（检测线程 + 身份汇总）

**Files:**
- Create: `moyu/core/analysis_worker.py`
- Test: `tests/test_analysis_worker.py`

**Interfaces:**
- Consumes: `FaceEngine`（Task 2）。
- Produces:
  - `Analysis` dataclass：`faces: list[tuple[int,int,int,int,float,str,float]]`（x,y,w,h,score,label,sim）、`face_count: int`、`has_owner: bool`、`has_stranger: bool`、`max_owner_sim: float`
  - `FaceAnalysisWorker(config, engine, cap=None)`：`start()/stop()/join()`，`get_latest() -> tuple[frame_bgr, Analysis]`
  - 内部方法 `_summarize(rows) -> list[...]`（可单测，不依赖摄像头）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_analysis_worker.py
import unittest
from moyu.core.analysis_worker import FaceAnalysisWorker, Analysis


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

    def test_empty(self):
        w = self._worker()
        analysis = w._summarize([])
        self.assertEqual(0, analysis.face_count)
        self.assertFalse(analysis.has_owner)
        self.assertFalse(analysis.has_stranger)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m unittest tests.test_analysis_worker -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 Worker**

```python
# moyu/core/analysis_worker.py
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
        backend_ids = {"dshow": getattr(cv2, "CAP_DSHOW", None),
                       "msmf": getattr(cv2, "CAP_MSMF", None)}
        bid = backend_ids.get(self.backend)
        cap = cv2.VideoCapture(self.camera_index, bid) if bid is not None else cv2.VideoCapture(self.camera_index)
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
                    x = max(min(x, w - 1), 0); y = max(min(y, h - 1), 0)
                    bw = max(min(bw, w - x), 1); bh = max(min(bh, h - y), 1)
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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python.exe -m unittest tests.test_analysis_worker -v`
Expected: PASS

- [ ] **Step 5: 提交（可选）**

```bash
git add moyu/core/analysis_worker.py tests/test_analysis_worker.py
git commit -m "feat: add FaceAnalysisWorker producing identity-labeled analysis"
```

---

### Task 4: PrivacyGuard 状态机

**Files:**
- Create: `moyu/services/privacy_guard.py`
- Test: `tests/test_privacy_guard.py`

**Interfaces:**
- Consumes: `Analysis`（Task 3）。
- Produces:
  - `ShieldDecision(mode: str, reason: str)`，`mode ∈ {none, blur, cover}`，`reason ∈ {"", peep, stranger, away}`
  - `PrivacyGuard(config)`：`update(analysis, now: float, session_locked: bool) -> ShieldDecision`
  - 规则优先级：`cover`(stranger/away) > `blur`(peep) > `none`；锁屏时返回 none 并重置计时。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_privacy_guard.py
import unittest
from moyu.core.analysis_worker import Analysis
from moyu.services.privacy_guard import PrivacyGuard


def cfg():
    return {"privacy_guard": {
        "enabled": True,
        "peep": {"enabled": True, "min_faces": 2, "action": "blur"},
        "stranger": {"enabled": True, "hold_seconds": 3, "action": "cover"},
        "away": {"enabled": True, "seconds": 60, "action": "cover"},
    }}


def A(count=0, owner=False, stranger=False):
    return Analysis(face_count=count, has_owner=owner, has_stranger=stranger)


class PrivacyGuardTests(unittest.TestCase):
    def test_peep_triggers_blur(self):
        g = PrivacyGuard(cfg())
        d = g.update(A(count=2, owner=True, stranger=True), now=100, session_locked=False)
        self.assertEqual("blur", d.mode)
        self.assertEqual("peep", d.reason)

    def test_stranger_hold_then_cover(self):
        g = PrivacyGuard(cfg())
        self.assertEqual("none", g.update(A(count=1, stranger=True), now=0, session_locked=False).mode)
        self.assertEqual("none", g.update(A(count=1, stranger=True), now=2, session_locked=False).mode)
        d = g.update(A(count=1, stranger=True), now=3, session_locked=False)
        self.assertEqual("cover", d.mode)
        self.assertEqual("stranger", d.reason)
        # 陌生人离开 → 解除
        self.assertEqual("none", g.update(A(count=0), now=4, session_locked=False).mode)

    def test_away_then_cover_and_release_on_owner(self):
        g = PrivacyGuard(cfg())
        self.assertEqual("none", g.update(A(count=0), now=0, session_locked=False).mode)
        self.assertEqual("none", g.update(A(count=0), now=59, session_locked=False).mode)
        d = g.update(A(count=0), now=60, session_locked=False)
        self.assertEqual("cover", d.mode)
        self.assertEqual("away", d.reason)
        self.assertEqual("none", g.update(A(count=1, owner=True), now=61, session_locked=False).mode)

    def test_disabled_when_locked(self):
        g = PrivacyGuard(cfg())
        g.update(A(count=0), now=0, session_locked=False)
        d = g.update(A(count=0), now=999, session_locked=True)
        self.assertEqual("none", d.mode)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m unittest tests.test_privacy_guard -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 PrivacyGuard**

```python
# moyu/services/privacy_guard.py
from dataclasses import dataclass
from typing import Optional


@dataclass
class ShieldDecision:
    mode: str = "none"
    reason: str = ""


class PrivacyGuard:
    """把逐帧人脸状态决策为防护模式：none / blur / cover。"""

    def __init__(self, config: dict):
        self.update_config(config)
        self._stranger_since: Optional[float] = None
        self._empty_since: Optional[float] = None

    def update_config(self, config: dict) -> None:
        self.config = config
        g = config.get("privacy_guard", {}) if isinstance(config, dict) else {}
        self.enabled = bool(g.get("enabled", True))
        peep = g.get("peep", {})
        self.peep_enabled = bool(peep.get("enabled", True))
        self.peep_min_faces = int(peep.get("min_faces", 2))
        self.peep_action = str(peep.get("action", "blur"))
        st = g.get("stranger", {})
        self.stranger_enabled = bool(st.get("enabled", True))
        self.stranger_hold = float(st.get("hold_seconds", 3))
        self.stranger_action = str(st.get("action", "cover"))
        aw = g.get("away", {})
        self.away_enabled = bool(aw.get("enabled", True))
        self.away_seconds = float(aw.get("seconds", 60))
        self.away_action = str(aw.get("action", "cover"))

    def _reset(self):
        self._stranger_since = None
        self._empty_since = None

    def update(self, analysis, now: float, session_locked: bool) -> ShieldDecision:
        if not self.enabled or session_locked:
            self._reset()
            return ShieldDecision("none", "")

        # 陌生人计时
        if self.stranger_enabled and getattr(analysis, "has_stranger", False):
            if self._stranger_since is None:
                self._stranger_since = now
        else:
            self._stranger_since = None

        # 无人计时（画面中完全没有人脸）
        if getattr(analysis, "face_count", 0) == 0:
            if self._empty_since is None:
                self._empty_since = now
        else:
            self._empty_since = None

        # 优先级：cover > blur
        if (self.away_enabled and self._empty_since is not None
                and now - self._empty_since >= self.away_seconds):
            return ShieldDecision(self.away_action, "away")
        if (self.stranger_enabled and self._stranger_since is not None
                and now - self._stranger_since >= self.stranger_hold):
            return ShieldDecision(self.stranger_action, "stranger")
        if self.peep_enabled and getattr(analysis, "face_count", 0) >= self.peep_min_faces:
            return ShieldDecision(self.peep_action, "peep")
        return ShieldDecision("none", "")
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python.exe -m unittest tests.test_privacy_guard -v`
Expected: PASS

- [ ] **Step 5: 提交（可选）**

```bash
git add moyu/services/privacy_guard.py tests/test_privacy_guard.py
git commit -m "feat: add PrivacyGuard state machine (peep/stranger/away)"
```

---

### Task 5: ScreenShield（多显示器模糊/遮屏）

**Files:**
- Create: `moyu/services/monitors.py`（显示器枚举，纯函数便于测试）
- Create: `moyu/services/screen_shield.py`
- Test: `tests/test_monitors.py`

**Interfaces:**
- Produces:
  - `monitors.list_monitors() -> list[tuple[int,int,int,int]]`（每项 left,top,width,height）
  - `ScreenShield(root, config)`：`set_mode(mode: str) -> None`（none/blur/cover）；`refresh() -> None`（blur 定时重抓）；`close() -> None`
  - blur 窗口点击穿透，cover 窗口拦截输入。

- [ ] **Step 1: 写失败测试**（monitors 用注入的探测函数）

```python
# tests/test_monitors.py
import unittest
from moyu.services import monitors


class MonitorTests(unittest.TestCase):
    def test_parses_rects(self):
        fake = [(0, 0, 1920, 1080), (0, -1080, 1920, 1080)]
        self.assertEqual(fake, monitors._normalize(fake))

    def test_empty_fallback_primary(self):
        self.assertEqual([(0, 0, 800, 600)], monitors._normalize([], primary=(800, 600)))
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m unittest tests.test_monitors -v`
Expected: FAIL

- [ ] **Step 3: 实现 monitors.py**

```python
# moyu/services/monitors.py
import ctypes
import sys
from ctypes import wintypes
from typing import List, Tuple


def _normalize(rects, primary=None):
    out = [tuple(int(v) for v in r) for r in rects if r[2] > 0 and r[3] > 0]
    if out:
        return out
    if primary:
        return [(0, 0, int(primary[0]), int(primary[1]))]
    return [(0, 0, 1920, 1080)]


def list_monitors() -> List[Tuple[int, int, int, int]]:
    if not sys.platform.startswith("win"):
        return _normalize([])
    try:
        user32 = ctypes.windll.user32
        rects = []

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(wintypes.RECT), ctypes.c_double)

        def cb(_hmon, _hdc, lprect, _data):
            r = lprect.contents
            rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return 1

        user32.EnumDisplayMonitors(0, None, MonitorEnumProc(cb), 0)
        primary = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        return _normalize(rects, primary=primary)
    except Exception:
        return _normalize([], primary=(ctypes.windll.user32.GetSystemMetrics(0),
                                       ctypes.windll.user32.GetSystemMetrics(1)))
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python.exe -m unittest tests.test_monitors -v`
Expected: PASS

- [ ] **Step 5: 实现 ScreenShield**

```python
# moyu/services/screen_shield.py
import tkinter as tk
from typing import List

from PIL import Image, ImageGrab, ImageTk

from .monitors import list_monitors


class ScreenShield:
    """用无边框置顶窗口覆盖所有显示器：blur=模糊桌面截图(穿透)，cover=不透明(拦截)。"""

    def __init__(self, root: tk.Tk, config: dict):
        self.root = root
        self.config = config
        g = config.get("privacy_guard", {}).get("shield", {})
        self.blur_radius = int(g.get("blur_radius", 28))
        self.blur_refresh_ms = int(g.get("blur_refresh_ms", 800))
        self.cover_text = str(g.get("cover_text", ""))
        self._mode = "none"
        self._windows: List[tk.Toplevel] = []
        self._labels = []
        self._photos = []
        self._timer = None

    def set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._destroy_windows()
        self._mode = mode
        if mode == "none":
            return
        for (left, top, width, height) in list_monitors():
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.geometry(f"{width}x{height}+{left}+{top}")
            win.attributes("-topmost", True)
            win.configure(bg="black")
            label = tk.Label(win, bg="black", bd=0, highlightthickness=0)
            label.pack(fill="both", expand=True)
            self._windows.append(win)
            self._labels.append(label)
            self._photos.append(None)
        if mode == "cover":
            self._set_click_through(False)
            self._paint_cover()
        else:
            self._set_click_through(True)
            self.refresh()
            self._schedule_refresh()

    def refresh(self) -> None:
        if self._mode != "blur":
            return
        try:
            shot = ImageGrab.grab(all_screens=True).convert("RGB")
        except Exception:
            return
        blurred = shot.filter(__import__("PIL.ImageFilter", fromlist=["ImageFilter"]).GaussianBlur(self.blur_radius))
        origin_x, origin_y = self._virtual_origin()
        for idx, (left, top, width, height) in enumerate(list_monitors()):
            if idx >= len(self._labels):
                break
            x0, y0 = left - origin_x, top - origin_y
            crop = blurred.crop((x0, y0, x0 + width, y0 + height))
            photo = ImageTk.PhotoImage(crop)
            self._photos[idx] = photo
            self._labels[idx].configure(image=photo)

    def _virtual_origin(self):
        import ctypes
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)

    def _paint_cover(self):
        for label in self._labels:
            if self.cover_text:
                label.configure(text=self.cover_text, fg="#888888", bg="black",
                                font=("Microsoft YaHei", 20))
            else:
                label.configure(bg="black")

    def _schedule_refresh(self):
        self._timer = self.root.after(self.blur_refresh_ms, self._on_tick)

    def _on_tick(self):
        if self._mode != "blur":
            return
        self.refresh()
        self._schedule_refresh()

    def _set_click_through(self, enabled: bool):
        try:
            import win32con, win32gui
            for win in self._windows:
                hwnd = win.winfo_id()
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                if enabled:
                    ex |= win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED
                else:
                    ex &= ~win32con.WS_EX_TRANSPARENT
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
        except Exception:
            pass

    def close(self) -> None:
        if self._timer:
            try:
                self.root.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None
        self._destroy_windows()
        self._mode = "none"

    def _destroy_windows(self):
        for win in self._windows:
            try:
                win.destroy()
            except Exception:
                pass
        self._windows = []
        self._labels = []
        self._photos = []
```

- [ ] **Step 6: 提交（可选）**

```bash
git add moyu/services/monitors.py moyu/services/screen_shield.py tests/test_monitors.py
git commit -m "feat: add multi-monitor ScreenShield (blur/cover)"
```

---

### Task 6: 配置新增节 + 合并测试

**Files:**
- Modify: `config/default.yml`（追加 `identity`、`privacy_guard` 两节）
- Modify: `moyu/core/paths.py`（新增 `get_models_dir()`、`get_owner_file_path()`）
- Test: `tests/test_config_privacy.py`

**Interfaces:**
- Produces: `get_models_dir() -> str`（`base/models`）、`get_owner_file_path() -> str`（`base/owner_faces.json`）
- Consumes: `load_config()` 现成能力。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config_privacy.py
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
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m unittest tests.test_config_privacy -v`
Expected: FAIL（KeyError: 'privacy_guard'）

- [ ] **Step 3: 追加默认配置**

在 `config/default.yml` 末尾追加：

```yaml
## 人脸身份识别（主人/陌生人）。
identity:
  ## 是否启用身份识别；关闭后仅保留多人检测。
  enabled: true
  ## SFace 余弦相似度阈值，达到即判定为主人，推荐 0.363。
  match_threshold: 0.363
  ## 录入主人人脸时的采集样本数。
  samples: 9
  ## 主人特征库文件名（相对程序目录）。
  owner_file: "owner_faces.json"

## 视觉防护：多人偷看→模糊；陌生人/人离开→遮屏。
privacy_guard:
  enabled: true
  ## 多人同屏偷看。
  peep:
    enabled: true
    min_faces: 2
    ## blur=变模糊(点击穿透)，cover=遮屏(拦截输入)。
    action: "blur"
  ## 陌生人长时间看屏幕。
  stranger:
    enabled: true
    hold_seconds: 3
    action: "cover"
  ## 主人离开（画面长时间无人脸）。
  away:
    enabled: true
    seconds: 60
    action: "cover"
  shield:
    blur_radius: 28
    blur_refresh_ms: 800
    cover_text: ""
    block_input_on_cover: true
  ## 触发时的抓拍冷却（秒）。
  snapshot:
    cooldown_seconds: 15
  ## 旧行为：检测到人脸时切换工作软件，默认关闭。
  legacy_switch_work_app: false
```

- [ ] **Step 4: 在 `paths.py` 增加两个函数**

```python
def get_models_dir() -> str:
    """模型文件目录。"""
    return os.path.join(get_base_dir(), "models")


def get_owner_file_path() -> str:
    """主人人脸特征库文件路径。"""
    return os.path.join(get_base_dir(), "owner_faces.json")
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv\Scripts\python.exe -m unittest tests.test_config_privacy -v`
Expected: PASS

- [ ] **Step 6: 提交（可选）**

```bash
git add config/default.yml moyu/core/paths.py tests/test_config_privacy.py
git commit -m "feat: add privacy_guard/identity config defaults"
```

---

### Task 7: 主人人脸录入对话框 + 设置页「防偷窥」标签

**Files:**
- Create: `moyu/ui/enroll_dialog.py`
- Modify: `moyu/ui/settings_dialog.py`（新增标签与内容，`_show_tab` 分发）
- Test: 手动（GUI 无法单测）

**Interfaces:**
- Consumes: `FaceEngine`、`OwnerStore`、`get_models_dir()`、`get_owner_file_path()`。
- Produces: `EnrollDialog(parent, engine, owner_store, samples=9).run() -> bool`

- [ ] **Step 1: 实现录入对话框**

要点：打开摄像头预览，倒计时后连拍 `samples` 张，每帧取"最大脸"做 `engine.feature` 并 `owner_store.add`，最后 `save()`。失败（检测不到脸）则提示重试。用 `tk.Toplevel(parent)`，与现有 `SettingsDialog` 一致的深色主题。

- [ ] **Step 2: 设置页接入**

在 `settings_dialog.py`：
- `_create_tabs` 增加 `self._create_tab_button(self.tab_frame, "guard", "🛡 防偷窥")`。
- `_show_tab` 增加 `elif tab_id == "guard": self._create_guard_content()`。
- `_create_guard_content`：四个复选框（总开关、多人模糊、陌生人遮屏、人离开遮屏）+ 数值输入（min_faces、stranger hold_seconds、away seconds、blur_radius）+ 「录入主人人脸」按钮（调用 EnrollDialog）。
- 在 `__init__` 预读 `privacy_guard`/`identity` 到实例变量；在 `_save_current_tab_values` 与 `_on_save` 中写回 `self.config["privacy_guard"]` / `["identity"]`。

- [ ] **Step 3: 手动验证**

Run: `.venv\Scripts\python.exe main.py`
Expected: 设置窗口出现「防偷窥」标签；能录入并保存主人特征；保存后 `user_config.yml` 含 `privacy_guard`。

- [ ] **Step 4: 提交（可选）**

```bash
git add moyu/ui/enroll_dialog.py moyu/ui/settings_dialog.py
git commit -m "feat: add anti-peep settings tab and owner enrollment dialog"
```

---

### Task 8: 主循环编排接入（ui_app / headless）

**Files:**
- Modify: `moyu/ui/ui_app.py`（用 FaceAnalysisWorker + PrivacyGuard + ScreenShield 替换原告警动作）
- Modify: `moyu/runners/headless.py`（同样接入，仅日志）
- Test: 手动

**Interfaces:**
- Consumes: Task 2/3/4/5/6 全部。
- Produces: 无（编排层）。

- [ ] **Step 1: 改造 `CameraPreviewApp`**

- `__init__`：构建 `OwnerStore`（load）+ `FaceEngine`（load，失败则降级并打印）；若 `identity.enabled` 为假或模型不可用，则 `owner_store.clear()` 以"仅多人检测"运行。
- 用 `FaceAnalysisWorker` 取代 `FaceDetectionWorker`；保留预览绘制。
- 创建 `PrivacyGuard(config)` 与 `ScreenShield(self.root, config)`。
- `_update_frame`：取 `(frame, analysis)` → `decision = guard.update(analysis, time.time(), session_locked)` → `shield.set_mode(decision.mode)`；在 mode 变为 blur/cover 时按 `snapshot.cooldown_seconds` 抓拍（`save_snapshot`）。
- `session_locked` 由 `WindowsSessionState().is_locked()` 提供，复用 `lock_screen_capture` 的会话对象。
- `legacy_switch_work_app` 为真时，保留原"切工作软件"动作。
- `_shutdown`：`shield.close()`。

- [ ] **Step 2: 改造 `run_headless`**

同样驱动 `PrivacyGuard`；遮屏/模糊在无界面模式下不生效（打印日志即可），抓拍照常。

- [ ] **Step 3: 手动验证**

Run: `.venv\Scripts\python.exe main.py`
Expected: 录入主人后 → 第二人入镜时屏幕变模糊（可继续操作）；主人离开 60s 后全屏遮屏；主人回来解除。

- [ ] **Step 4: 回归原测试**

Run: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: 全绿（含原有 `test_lock_screen_capture`）。

- [ ] **Step 5: 提交（可选）**

```bash
git add moyu/ui/ui_app.py moyu/runners/headless.py
git commit -m "feat: wire PrivacyGuard and ScreenShield into app loop"
```

---

### Task 9: 打包配置与模型目录

**Files:**
- Modify: `main.spec`（加入 `models/` 数据与新模块 hiddenimports）
- Modify: `.gitignore`（忽略 `models/*.onnx`、`owner_faces.json`、抓拍目录）
- Test: 构建冒烟

- [ ] **Step 1: 更新 spec**

- `datas` 追加 `('models', 'models')`（若目录存在）。
- `hiddenimports` 追加：`moyu.core.face_engine`、`moyu.core.owner_store`、`moyu.core.analysis_worker`、`moyu.services.privacy_guard`、`moyu.services.screen_shield`、`moyu.services.monitors`、`moyu.ui.enroll_dialog`。
- `collect_data_files('mediapipe')` 保留（兼容）。

- [ ] **Step 2: 更新 .gitignore**

追加 `models/`、`owner_faces.json`、`people/`、`lock_screen_people/`、`user_config.yml`。

- [ ] **Step 3: 构建冒烟（可选，需用户确认是否打包）**

Run: `.venv\Scripts\pyinstaller.exe main.spec --noconfirm`
Expected: `dist/moyu.exe` 生成；运行后能加载模型并启动预览。

- [ ] **Step 4: 提交（可选）**

```bash
git add main.spec .gitignore
git commit -m "build: bundle face models and new modules"
```

---

## Self-Review

**Spec coverage：**
- 多人偷看→模糊：Task 4（peep）+ Task 5（blur）+ Task 8（接入）✔
- 陌生人→遮屏：Task 4（stranger）+ Task 5（cover）✔
- 人离开→遮屏：Task 4（away）✔
- 抓拍留证：Task 8（冷却抓拍）✔
- 身份识别 YuNet+SFace：Task 2 ✔；主人库：Task 1 ✔；录入：Task 7 ✔
- 多显示器：Task 5 ✔
- 配置：Task 6 ✔；打包：Task 9 ✔
- 错误处理（模型缺失降级、无主人库不误判）：Task 2/8 ✔

**Placeholder scan：** Task 7 的 GUI 以要点描述（GUI 无法单测，属合理），其余均含完整代码。

**Type consistency：** `Analysis` 字段、`ShieldDecision.mode/reason`、`FaceEngine.identify` 返回 `(label, sim)`、`list_monitors` 返回四元组，在各任务间一致。
