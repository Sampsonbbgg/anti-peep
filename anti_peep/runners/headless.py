import sys
import time
from typing import Optional

from anti_peep.core.constants import APP_NAME
from anti_peep.core.deps import cv2
from anti_peep.core.analysis_worker import FaceAnalysisWorker
from anti_peep.services.snapshot import save_snapshot
from anti_peep.services.lock_screen_capture import LockScreenCaptureService
from anti_peep.services.work_app import switch_to_work_app
from anti_peep.ui.tray import get_tray_manager


def run_headless(config: dict) -> None:
    """无界面模式：只检测、打印状态与抓拍，不显示遮罩窗口。"""
    if cv2 is None:
        print("未安装 OpenCV。请先执行\n  pip install opencv-python")
        sys.exit(1)

    from anti_peep.core.face_engine import FaceEngine
    from anti_peep.core.owner_store import OwnerStore
    from anti_peep.core.paths import get_models_dir, get_owner_file_path
    from anti_peep.services.privacy_guard import PrivacyGuard
    from anti_peep.platforms.windows_session import WindowsSessionState

    identity_cfg = config.get("identity", {})
    store = OwnerStore(
        get_owner_file_path(),
        threshold=float(identity_cfg.get("match_threshold", 0.363)),
    )
    store.load()
    engine = FaceEngine(get_models_dir(), store)
    try:
        engine.load()
    except Exception as e:
        print(f"人脸模型加载失败，降级为仅多人检测：{e}")
        store.clear()

    detector = FaceAnalysisWorker(config, engine)
    detector.start()
    lock_screen_capture = LockScreenCaptureService(config)
    guard = PrivacyGuard(config, owner_enrolled=not store.is_empty)
    session_state = WindowsSessionState()

    ui_cfg = config.get("ui", {})
    tray_seconds = int(ui_cfg.get("tray_notification_seconds", 8))
    tray_seconds = max(5, min(tray_seconds, 10))
    TrayManager = get_tray_manager()
    tray: Optional[TrayManager] = None  # type: ignore[assignment]
    if TrayManager is not None:
        tray = TrayManager(APP_NAME, on_restore=lambda: None, on_exit=lambda: None)
        try:
            tray.start()
        except Exception:
            tray = None

    cooldown_seconds = float(config.get("alert_cooldown_seconds", 15))
    pg_cfg = config.get("privacy_guard", {})
    snapshot_cooldown = float(pg_cfg.get("snapshot", {}).get("cooldown_seconds", 15))
    last_action_time = 0.0
    last_snapshot_time = 0.0
    prev_mode = "none"

    print("当前环境不支持 GUI 或未启用 Tkinter，已使用无界面模式运行。")
    print(" - 触发时会抓拍一张画面；视觉遮罩在无界面模式下不生效。")
    print(" - 按 Ctrl + C 结束程序。")

    try:
        while True:
            time.sleep(0.1)
            frame_bgr, analysis = detector.get_latest()
            now = time.time()
            lock_face_present = bool(getattr(analysis, "face_count", 0) > 0)
            lock_screen_capture.process(frame_bgr, lock_face_present)

            decision = guard.update(analysis, now, session_state.is_locked())
            if decision.mode != prev_mode:
                print(f"防护模式：{prev_mode} -> {decision.mode}（{decision.reason}）")
                prev_mode = decision.mode
            if decision.mode in ("blur", "cover") and now - last_snapshot_time >= snapshot_cooldown:
                last_snapshot_time = now
                save_snapshot(config, frame_bgr, filename_prefix=f"shield_{decision.reason}")

            if pg_cfg.get("legacy_switch_work_app") and getattr(analysis, "face_count", 0) >= 2:
                if now - last_action_time >= cooldown_seconds:
                    last_action_time = now
                    save_snapshot(config, frame_bgr)
                    switch_to_work_app(config)
    except KeyboardInterrupt:
        print("正在退出…")
    finally:
        detector.stop()
        detector.join(timeout=2)
        if tray:
            tray.stop()
