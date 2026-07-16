# UI modules for moyu
from .tray import get_tray_manager, SystemTrayManager, DummyTrayManager

__all__ = [
    "get_tray_manager",
    "SystemTrayManager",
    "DummyTrayManager",
]
