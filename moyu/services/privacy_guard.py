from dataclasses import dataclass
from typing import Optional


@dataclass
class ShieldDecision:
    mode: str = "none"  # none | blur | cover
    reason: str = ""  # "" | peep | stranger | away


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

        # 优先级：cover(away/stranger) > blur(peep)
        if (
            self.away_enabled
            and self._empty_since is not None
            and now - self._empty_since >= self.away_seconds
        ):
            return ShieldDecision(self.away_action, "away")
        if (
            self.stranger_enabled
            and self._stranger_since is not None
            and now - self._stranger_since >= self.stranger_hold
        ):
            return ShieldDecision(self.stranger_action, "stranger")
        if (
            self.peep_enabled
            and getattr(analysis, "face_count", 0) >= self.peep_min_faces
        ):
            return ShieldDecision(self.peep_action, "peep")
        return ShieldDecision("none", "")
