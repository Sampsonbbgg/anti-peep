"""Windows 锁屏人脸抓拍服务。"""

import time
from typing import Callable, Optional

from moyu.platforms.windows_session import WindowsSessionState
from moyu.services.snapshot import save_snapshot


class LockScreenCaptureService:
    """锁屏时按配置的冷却间隔保存检测到人脸的画面。"""

    def __init__(
        self,
        config: dict,
        session_state: Optional[WindowsSessionState] = None,
        snapshot_saver: Callable = save_snapshot,
    ):
        self._session_state = session_state or WindowsSessionState()
        self._snapshot_saver = snapshot_saver
        self._last_capture_time: Optional[float] = None
        self.update_config(config)

    def update_config(self, config: dict) -> None:
        self.config = config
        lock_cfg = config.get("lock_screen", {})
        self.enabled = bool(lock_cfg.get("enabled", True))
        self.cooldown_seconds = float(lock_cfg.get("cooldown_seconds", 10))

    def process(
        self,
        frame,
        face_present: bool,
        now: Optional[float] = None,
    ) -> Optional[str]:
        """处理一帧；满足锁屏、人脸和冷却条件时返回照片路径。"""
        if not self.enabled:
            return None

        if not self._session_state.is_locked():
            # 每次重新锁屏后允许立即抓拍。
            self._last_capture_time = None
            return None

        if frame is None or not face_present:
            return None

        current_time = time.monotonic() if now is None else now
        if (
            self._last_capture_time is not None
            and current_time - self._last_capture_time < self.cooldown_seconds
        ):
            return None

        filepath = self._snapshot_saver(
            self.config,
            frame,
            section="lock_screen",
            filename_prefix="lock_screen",
        )
        if filepath:
            self._last_capture_time = current_time
        return filepath
