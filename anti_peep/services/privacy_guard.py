from dataclasses import dataclass
from typing import Optional


@dataclass
class ShieldDecision:
    mode: str = "none"  # none | blur | cover
    reason: str = ""  # "" | peep | stranger | away | not_looking


class PrivacyGuard:
    """把逐帧人脸/朝向状态决策为防护模式：none / blur / cover。

    规则（按优先级）：
      1. 陌生人持续 hold_seconds 秒 → 遮屏（cover）
      2. 多人同屏 → 模糊（blur，立即）
      3. 主人在场且看向屏幕 → 清晰（none）
      4. 陌生人正在计时（未满 hold）→ 暂不模糊
      5. 其余（没我 / 我没看屏幕）→ 持续 blur_hold 秒后模糊（blur）

    未录入主人人脸时（owner_enrolled=False），无法判断"有没有我"，
    仅保留陌生人/多人规则。
    """

    def __init__(self, config: dict, owner_enrolled: bool = True):
        self._stranger_since: Optional[float] = None
        self._blur_since: Optional[float] = None
        self.owner_enrolled = bool(owner_enrolled)
        self.update_config(config)

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
        bl = g.get("blur", {})
        self.blur_enabled = bool(bl.get("enabled", True))
        self.blur_hold = float(bl.get("hold_seconds", 1.5))
        self.blur_action = str(bl.get("action", "blur"))
        lk = g.get("looking", {})
        self.max_yaw = float(lk.get("max_yaw_deg", 25))

    def _reset(self):
        self._stranger_since = None
        self._blur_since = None

    def _owner_looking(self, analysis) -> bool:
        """主人是否在场且看向屏幕；无法估朝向时按"在看"处理以免误报。"""
        if not getattr(analysis, "has_owner", False):
            return False
        yaw = getattr(analysis, "owner_yaw", None)
        if yaw is None:
            return True
        return abs(yaw) <= self.max_yaw

    def update(self, analysis, now: float, session_locked: bool) -> ShieldDecision:
        if not self.enabled or session_locked:
            self._reset()
            return ShieldDecision("none", "")

        face_count = int(getattr(analysis, "face_count", 0))

        # 陌生人计时
        if self.stranger_enabled and getattr(analysis, "has_stranger", False):
            if self._stranger_since is None:
                self._stranger_since = now
        else:
            self._stranger_since = None

        # 1) 陌生人持续 hold → 遮屏
        if (
            self.stranger_enabled
            and self._stranger_since is not None
            and now - self._stranger_since >= self.stranger_hold
        ):
            self._blur_since = None
            return ShieldDecision(self.stranger_action, "stranger")

        # 2) 多人同屏 → 模糊（立即）
        if self.peep_enabled and face_count >= self.peep_min_faces:
            self._blur_since = None
            return ShieldDecision(self.peep_action, "peep")

        # 未录入主人：无法判断"有没有我"，此层规则不生效
        if not self.owner_enrolled:
            self._blur_since = None
            return ShieldDecision("none", "")

        # 3) 主人在场且看向屏幕 → 清晰
        if self._owner_looking(analysis):
            self._blur_since = None
            return ShieldDecision("none", "")

        # 4) 陌生人正在计时（未满 hold）→ 暂不模糊，等其转为遮屏
        if self.stranger_enabled and getattr(analysis, "has_stranger", False):
            self._blur_since = None
            return ShieldDecision("none", "")

        # 5) 没我 / 我没看屏幕 → 缓冲后模糊
        if not self.blur_enabled:
            self._blur_since = None
            return ShieldDecision("none", "")
        if self._blur_since is None:
            self._blur_since = now
        if now - self._blur_since >= self.blur_hold:
            reason = "away" if face_count == 0 else "not_looking"
            return ShieldDecision(self.blur_action, reason)
        return ShieldDecision("none", "")
