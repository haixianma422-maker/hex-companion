# Qt 界面迁移验证

日期：2026-10-17。分支：`feat/qml-ui`。

浮窗、浮标和设置窗口从 Tk 迁移到 Qt Quick（PySide6 6.12）。`CompanionApp` 的调度与业务逻辑保持不变，只替换其中依赖 Tk 的部分；数据、客户端读取、OCR、图片缓存、快捷键和托盘模块未改动。视觉沿用 V2 配色与坐标，颜色等设计变量集中在 `aram_demo/qml/Theme.qml`。

## 结构

| 部分 | 文件 |
| --- | --- |
| 面板、浮标的视图数据与窗口位置（物理像素 ↔ 逻辑像素） | `aram_demo/qt_overlay.py` |
| 设置表单与保存规则（沿用 Tk 版的校验与回滚） | `aram_demo/qt_settings.py` |
| 界面 | `aram_demo/qml/` |
| 托盘与 EXE 图标 | `aram_demo/brand.py`（与 Tk 版逐像素一致） |

约束：图片校验在后台线程完成，主线程只读取结果；位移、透明度、缩放和旋转动画使用渲染线程的 Animator；Python 代码不连接渲染线程发出的信号。

## 验证结果

| 项目 | 结果 |
| --- | --- |
| 自动回归（`scripts/run_native_tests.py`） | 185 项通过（迁移前 Tk 版 194 项；删除仅测 Tk 内部实现的用例，新增 Qt 行为用例） |
| 打包版离线自检（不可见桌面） | 通过：中文 OCR、1,189 个资源哈希、两套来源切换、图片、缩放保存、收起展开、设置保存、全局快捷键、托盘、正常退出；渲染后端 Direct3D11 |
| 窗口验收（`scripts/verify_overlay.py`，源码与 EXE） | 置顶、工具窗口、`WS_EX_NOACTIVATE`、`MA_NOACTIVATE`；点击前后前台窗口不变；阴影区域点击穿透到下层窗口；投递点击可收起面板；静止 10 秒渲染 0 帧（源码）；1 / 1.5 / 2 倍缩放截图 |
| 启动到面板出现（预览） | 源码 0.89 秒，EXE 0.73 秒 |
| 识别基准（合成截图） | 重选一张海克斯后 0.36 秒在面板显示；过程中窗口未隐藏，卡片未重建 |
| 主线程被占用时的动画（样例中测得） | 每 0.7 秒占用 60 ms 时，最长帧间隔 8–11 ms，卡顿帧 0；见[样例记录](qml-spike-verification.md) |

## 发布包

| 指标 | Tk 单文件（v0.5.0-preview） | Qt 文件夹 |
| --- | --- | --- |
| 形式 | `HexCompanion.exe` | `HexCompanion/` 文件夹（EXE + `_internal`） |
| 解压后体积 | 单个 EXE 161.3 MB，每次启动时解压 | 405.6 MB，2,134 个文件 |
| zip | 160.8 MB | 197.2 MB（+36.4 MB） |

单文件形式每次启动需要先解压 Qt，启动 5–6 秒，因此改为文件夹形式。Qt 以未修改的独立动态库随附，使用 LGPL-3.0；许可证原文在包内 `licenses/LGPL-3.0.txt` 与 `licenses/GPL-3.0.txt`。

## 迁移中发现并修复的问题

1. 关闭动效时，零时长的 Animator 不会写回结束值，原画、候选卡片和面板本身都停在透明状态。现在“关闭”使用 1 ms；`test_motion_off_still_ends_with_everything_opaque` 覆盖，把修复撤回会使该用例失败。
2. 设置窗口由 Python 创建后被 QML 垃圾回收删除；现在显式设为 C++ 所有。
3. 窗口查找按名称遍历所有顶层窗口，可能取到上一个正在关闭的同名窗口；现在只在本次加载创建的窗口中查找。
4. 大厅阶段错误显示“召唤师技能”；Tk 版只在选人阶段显示，已恢复。
5. PySide6 的安装包没有附带 LGPL 原文，构建脚本现在把 LGPL-3.0 / GPL-3.0 原文写入 `licenses/`。

## 与 Tk 版的差异

- 预览中的 `Ctrl+Tab`、`F10` 不再可用：浮窗不接收键盘焦点。双击标题切换场景，从托盘退出。
- 可选英雄列表使用原生惯性滚动，替代 Tk 版手写的 140 ms 滚动。
- 浮标的悬停提示是一个独立的点击穿透小窗口。
- 设置窗口不再有外阴影，改为 1 px 描边。
- 开发用资料查看器（`--inspector`）仍使用 Tk，不随发布包提供。

## 尚未验证

- 局内 OCR 与界面同时运行时的帧率与 CPU。2026-10-17 用完整版本打过一局真实对局，未发现问题，但未记录帧率与 CPU。
- 物理显示缩放、多显示器与跨 DPI 拖动；本机为 100% 显示器，缩放用 `QT_SCALE_FACTOR` 模拟。
- 整局下来的内存变化。
- 安装目录的原生文件夹对话框只验证了模块可加载，未自动化打开。

## 本地重跑

```powershell
.\.venv\Scripts\python.exe scripts/run_native_tests.py
.\.venv\Scripts\python.exe scripts/verify_overlay.py
.\.venv\Scripts\python.exe scripts/build_exe.py --dist-dir dist/qt-ui
.\.venv\Scripts\python.exe scripts/check_frozen_hidden.py dist/qt-ui/HexCompanion/HexCompanion.exe dist/qt-ui/verification.json
.\.venv\Scripts\python.exe scripts/package_binary.py --exe dist/qt-ui/HexCompanion/HexCompanion.exe --check dist/qt-ui/verification.json
.\.venv\Scripts\python.exe scripts/verify_overlay.py --exe dist/qt-ui/HexCompanion/HexCompanion.exe
```
