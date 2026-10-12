# 魔芋 MoYu 视觉防护扩展 · 设计稿

- 日期：2026-10-12
- 基于：GitHub `x7722/moyu`（MIT）本地克隆于 `D:\anti-peep\moyu`
- 目标：在保留原有多人脸检测骨架的前提下，把"检测到多人 → 切换工作软件"升级为"检测 + 身份判别 → 视觉防护（模糊/遮屏）"，并对偷窥者友好（无红色警告、无系统提醒、不真锁屏）。

## 1. 需求（用户确认）

| 场景 | 条件 | 动作 |
|---|---|---|
| 多人偷看 | 同屏人脸 ≥2 | **所有显示器变模糊**；抓拍留证；无提示、无提醒、不锁屏 |
| 陌生人 | 识别到非主人人脸持续 ≥ 阈值 | **全屏遮屏**，直到陌生人离开 |
| 人离开 | 连续 ≥ 阈值无人脸 | **全屏遮屏**，主人回来被识别到即自动解除 |
| 抓拍 | 每次触发（模糊/遮屏） | 保存到配置目录，带冷却 |

关键取舍（用户确认）：
- 身份识别方案 = OpenCV **YuNet + SFace**（离线、轻量、纯 CPU）。
- 模糊态：**点击穿透、不拦截输入**（偷窥者看不清、主人仍可盲操作、不惊动对方）。
- 遮屏态：**拦截输入**（主人不在场，回来靠人脸识别自动解除）。

## 2. 架构

现有链路：`FaceDetectionWorker`（MediaPipe，计数+去抖）→ `CameraPreviewApp`（上升沿触发）→ 抓拍 + 切应用 + 托盘。

扩展后链路：

```
摄像头帧
  └─ FaceAnalysisWorker (新，替代/扩展 FaceDetectionWorker)
        ├─ FaceEngine: YuNet 检测 + SFace 特征 + 与主人库比对
        └─ 输出 FaceRecord[]  {bbox, landmarks, score, label(owner/stranger/unknown), sim}
  └─ PrivacyGuard (新，状态机)
        输入：FaceRecord[]、时间、Windows 锁屏状态
        输出：ShieldDecision {mode: none|blur|cover, reason}
  └─ ScreenShield (新)
        按显示器铺满无边框置顶窗口；blur=模糊桌面截图(穿透)，cover=不透明(拦截)
  └─ 抓拍：复用 services/snapshot.py
```

### 2.1 新增模块

- `moyu/core/face_engine.py`
  - `FaceEngine`：`load()`（YuNet+SFace）、`detect(frame) -> list[Face]`、`embed(frame, face) -> np.ndarray`、`identify(emb) -> (label, sim)`。
  - 主人库：`OwnerStore`，读写 `owner_faces.json`（多张 128 维归一化特征 + 阈值）。
  - 模型下载：缺失时从 `hf-mirror.com` 拉取，存 `models/`。
- `moyu/core/worker.py`（或扩展 `detector.py`）
  - `FaceAnalysisWorker(threading.Thread)`：保留旧接口 `get_latest_frame_and_states()`，新增 `get_analysis() -> Analysis`（含 `faces`、`face_count`、`has_owner`、`has_stranger`）。
  - 去抖逻辑沿用（on/off frames）。
- `moyu/services/privacy_guard.py`
  - `PrivacyGuard.update(analysis, now, session_locked) -> ShieldDecision`。
  - 规则：peep（≥2 脸）、stranger（连续 stranger ≥ hold_seconds）、away（连续无脸 ≥ away_seconds）；带冷却与解除条件。
- `moyu/services/screen_shield.py`
  - `ScreenShield.set_mode(mode)`；`list_monitors()` 用 `EnumDisplayMonitors`；每屏一个 Toplevel。
  - blur：`ImageGrab.grab(all_screens=True)` → `GaussianBlur` → 定时刷新；`WS_EX_TRANSPARENT` 穿透。
  - cover：不透明，`grab_set`/拦截输入。
- `moyu/ui/enroll_dialog.py`：主人人脸录入（倒计时 + 采集 N 张 + 写库）。

### 2.2 改动模块

- `moyu/ui/ui_app.py`：主循环改为驱动 `PrivacyGuard` + `ScreenShield`；保留托盘；新增「暂停防护」入口。
- `moyu/ui/settings_dialog.py`：新增「🛡 防偷窥」标签页。
- `moyu/ui/setup_wizard.py`：可选加入"立即录入主人人脸"。
- `config/default.yml`：新增 `privacy_guard`、`identity` 两节。
- `main.spec`：加入 `models/` 数据与新模块 hiddenimports。
- `requirements.txt`：不变（opencv 已含 YuNet/SFace；mediapipe 保留但非必需）。

## 3. 配置项（默认值）

```yaml
identity:
  enabled: true
  match_threshold: 0.363      # SFace 余弦相似度判定主人
  samples: 9                  # 录入样本数
  owner_file: "owner_faces.json"

privacy_guard:
  enabled: true
  peep:
    enabled: true
    min_faces: 2
    action: "blur"
  stranger:
    enabled: true
    hold_seconds: 3
    action: "cover"
  away:
    enabled: true
    seconds: 60
    action: "cover"
  shield:
    blur_radius: 28
    blur_refresh_ms: 800
    cover_text: ""
    block_input_on_cover: true
  snapshot:
    cooldown_seconds: 15
  # 原"多人→切工作软件"降级为可选，默认关闭
  legacy_switch_work_app: false
```

## 4. 错误处理

- 模型缺失且无法下载 → 明确提示，身份功能降级为"仅多人检测"（peep 仍可用，stranger/away 关闭）。
- 摄像头打不开 → 沿用原逻辑报错退出。
- 主人库不存在 → stranger/away 视为"未知"处理：away 仍可工作（无人脸计时）；stranger 在无主人库时不误判（把 unknown 视作非陌生人，避免把主人自己锁）。
- 遮罩窗口创建失败 → 记录并继续（不崩溃）。
- Windows 已锁屏 / 屏幕关闭 → 不触发遮屏。

## 5. 测试

- 单元：`OwnerStore` 读写与匹配（伪造特征向量）；`PrivacyGuard` 状态机（注入时钟，覆盖 peep/stranger/away/解除/冷却）；显示器矩形解析（mock）；配置合并。
- 手动：真机录入 → 多人/陌生人/离开模拟；双屏铺满验证；模糊穿透与遮屏拦截验证。

## 6. 非目标（YAGNI）

- 不做真实 Windows 锁屏（用户明确选择"仅视觉遮屏"）。
- 不做活体防翻拍（本期不含，后续可加）。
- 不做云端/联网身份复核。
