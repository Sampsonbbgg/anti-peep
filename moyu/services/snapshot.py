import os
import time
from typing import Optional

from moyu.core.deps import cv2
from moyu.core.paths import get_base_dir


def get_snapshot_dir(config: dict, section: str = "snapshot") -> Optional[str]:
    """从配置中读取抓拍保存目录。"""
    snap_cfg = config.get(section)
    if not isinstance(snap_cfg, dict):
        return None
    directory = snap_cfg.get("directory")
    if not directory:
        return None
    if os.path.isabs(directory):
        return directory
    return os.path.join(get_base_dir(), directory)


def save_snapshot(
    config: dict,
    frame,
    section: str = "snapshot",
    filename_prefix: str = "people",
) -> Optional[str]:
    """
    将当前画面保存到配置的目录中，用于事后检查是谁在看屏幕。
    命名格式：{filename_prefix}_YYYYMMDD_HHMMSS_mmm.jpg
    """
    if frame is None or cv2 is None:
        return None

    directory = get_snapshot_dir(config, section)
    enabled = bool(config.get(section, {}).get("enabled", True))
    if not enabled or not directory:
        return None

    try:
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        print(f"创建抓拍目录失败: {e}")
        return None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    millis = int((time.time() % 1) * 1000)
    filename = f"{filename_prefix}_{timestamp}_{millis:03d}.jpg"
    filepath = os.path.join(directory, filename)

    try:
        # Windows 下 cv2.imwrite 对包含中文等非 ASCII 字符的路径支持不稳定。
        # 先在内存中编码，再交给 Python 文件接口写入，确保 Unicode 路径可用。
        success, encoded_image = cv2.imencode(".jpg", frame)
        if not success:
            raise OSError("OpenCV 未能编码图片")
        with open(filepath, "wb") as file:
            file.write(encoded_image.tobytes())
        print(f"已保存抓拍: {filepath}")
        return filepath
    except Exception as e:
        print(f"保存抓拍失败: {e}")
        return None
