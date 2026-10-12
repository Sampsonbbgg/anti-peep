"""用户配置文件的读写。"""

import os
from typing import Any, Dict, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

from .paths import get_base_dir


def get_user_config_path() -> str:
    """返回运行目录中的用户配置路径。"""
    return os.path.join(get_base_dir(), "user_config.yml")


def save_user_config(config: Dict[str, Any], path: Optional[str] = None) -> bool:
    """保存用户配置到 YAML 文件。"""
    if yaml is None:
        print("警告：未安装 PyYAML，无法保存配置")
        return False

    config_path = path or get_user_config_path()
    try:
        content = "# Anti-Peep 用户配置文件\n# 此文件由程序自动生成，可手动编辑\n\n"
        content += yaml.dump(
            config,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        with open(config_path, "w", encoding="utf-8") as file:
            file.write(content)
        return True
    except Exception as error:
        print(f"保存配置失败: {error}")
        return False


def load_user_config(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """读取用户配置；文件不存在或内容损坏时返回 None。"""
    config_path = path or get_user_config_path()
    if yaml is None or not os.path.exists(config_path):
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        return data if isinstance(data, dict) else None
    except Exception:
        return None
