# UI modules for anti_peep
from .tray import get_tray_manager, SystemTrayManager, DummyTrayManager

__all__ = [
    "get_tray_manager",
    "SystemTrayManager",
    "DummyTrayManager",
]
