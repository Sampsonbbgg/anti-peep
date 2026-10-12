"""Esc 退出防护层的状态推进。

用户按下 Esc（或点击遮罩）时应立即撤除当前的模糊/遮屏，并且不要在同一个
触发条件持续期间反复弹出；等画面回到安全状态（决策回到 none）后自动重新
武装，让防护在下一个场景再次生效。
"""


def next_override(active: bool, decision_mode: str) -> bool:
    """推进 Esc 覆盖状态。

    - active=True 且本帧决策已回到 "none" → 释放覆盖（重新武装）。
    - 其它情况保持原状（避免同一触发条件下刚撤掉又弹出）。
    """
    if active and decision_mode == "none":
        return False
    return active


def effective_mode(decision_mode: str, override_active: bool) -> str:
    """应用 Esc 覆盖后真正要显示的模式：覆盖生效时一律清晰。"""
    if override_active:
        return "none"
    return decision_mode
