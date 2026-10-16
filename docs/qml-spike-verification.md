# QML 选人面板验证样例

日期：2026-10-17。分支：`spike/qml-select-panel`。

用 PySide6 6.12 / QML 复刻 V2 选人面板，验证迁移的技术风险。数据、客户端读取、图片缓存、快捷键直接复用 `aram_demo` 现有模块；Tk 版本没有改动。

## 范围

已实现：选人面板（英雄横幅、召唤师技能、候选英雄网格、来源切换、刷新）、收起浮标、阴影、拖动、F7/F8/Esc 快捷键。进入对局后同一面板贴在游戏窗口旁，只用于验证叠加效果。

未实现：局内海克斯与出装、OCR、设置页、托盘、缩放。

## 动效

| 场景 | 做法 |
| --- | --- |
| 英雄切换 | 旧名字 110ms 淡出左移，新名字 240ms 淡入并从右侧滑入；原画在新图解码完成后叠加淡入，任何时刻只显示一个名字 |
| 候选卡片 | 悬停变色 120ms，按下缩到 0.97，选中背景 200ms 过渡，选中圆点弹簧出现；候选列表增删和换位有位移动画 |
| 来源切换 | 滑块弹簧移动；加载时状态点呼吸、刷新图标旋转 |
| 收起 / 展开 | 面板朝右下角缩小淡出，浮标弹出；展开反向 |

## 本机验证结果

环境：Windows 11，100% 缩放，180Hz 显示器，Direct3D11 渲染。运行 `python -m qml_spike.verify`，加 `--exe` 测试打包版。

| 检查项 | 结果 |
| --- | --- |
| 窗口样式 | 置顶、工具窗口、`WS_EX_NOACTIVATE`；`WM_MOUSEACTIVATE` 返回 `MA_NOACTIVATE` |
| 焦点 | 窗口出现后、点击卡片后，前台窗口都不变 |
| 点击 | 向窗口投递点击消息能落到候选卡片（源码版和打包版都通过） |
| 阴影区域 | 鼠标穿透，点击落到下层窗口；四个圆角外各有几个像素仍会拦截点击 |
| 空闲 | 静止时 10 秒渲染 0 帧，CPU 约 0.5% |
| 连续切换英雄（每 0.6 秒一次） | 帧间隔中位数 5.6ms，p99 8ms；首次切换有 1–2 帧 39–54ms（图片首次解码） |
| GPU 占用（每 0.8 秒切换一次） | 0.37–0.43%，CPU 11–17% |
| 逻辑缩放 1 / 1.25 / 1.5 / 2 | 截图尺寸按比例，文字和图片清晰（`QT_SCALE_FACTOR` 模拟） |
| 未连接客户端 | 不显示窗口，内存 85MB，CPU 0.4–1.3% |

## 打包对比

两边都用文件夹形式打包，并带上 OCR 依赖（rapidocr、onnxruntime、OpenCV），Tk 版用现有 spec 改成文件夹输出。

| 指标 | Tk（现状） | QML 样例 |
| --- | --- | --- |
| 文件夹体积 | 304MB | 376MB |
| zip 体积 | 154MB | 182MB |
| 启动到窗口出现 | 1.0–1.8s | 0.8–1.7s |
| 预览空闲内存（工作集 / 私有） | 125MB / 84MB | 146MB / 152MB |
| 预览空闲 CPU | 2.8–4.1% | 0.6–1.2% |

QML 私有内存多出约 65MB，主要是 Direct3D 设备和显存映射。Tk 预览运行的是完整应用（托盘、识别调度），QML 样例没有这些部分。

## 发现的问题

1. 第一版把阴影画在面板窗口的透明边缘里，这圈 14px 的边缘会拦截点击。现在阴影放在单独的 `WindowTransparentForInput` 窗口中，面板窗口只有面板大小。
2. Qt 对透明像素不做穿透判断。面板窗口四个圆角外的几个像素会拦截点击；如果要消除，可以给窗口加遮罩，但圆角边缘会出现锯齿。

## 尚未验证

- 真实对局：叠在无边框游戏上的显示、点击、焦点，以及游戏运行时的 GPU 占用。
- 物理显示缩放和多显示器：本机只有 100% 显示器，缩放只用 `QT_SCALE_FACTOR` 模拟。
- 跨 DPI 显示器之间拖动。
- 长时间运行的内存：连续切换 30 秒，工作集从 154MB 增至 157MB，可能是图片缓存增长，需要观察整局下来的变化。

## 真实对局测试

1. 退出 Tk 版海克斯随行（两者共用单实例锁）。
2. 用管理员身份打开终端，读取管理员运行的联盟客户端需要这个权限。在仓库根目录运行：

   ```powershell
   .\.venv-qml\Scripts\python.exe -m qml_spike.main --hud --metrics artifacts\qml-spike\live.jsonl --gpu
   ```

   也可以右键 `dist\qml-spike\HexCompanionQml\HexCompanionQml.exe` 以管理员身份运行，参数相同。
3. 进入海克斯大乱斗，逐项观察：

   | 阶段 | 观察 |
   | --- | --- |
   | 选人 | 面板贴在客户端右侧；切换英雄、悬停和点击卡片的动画是否顺滑；点击面板后客户端是否保持前台 |
   | 选人 | 切换 OP.GG / 101 后数据是否更新；F8 收起再展开；拖动面板 |
   | 对局（无边框窗口） | 面板是否显示在游戏上方；点击面板后游戏是否仍能接收键盘；点击阴影区域是否落到游戏里 |
   | 对局 | 切出游戏后面板是否隐藏，切回后是否出现；游戏帧数和流畅度是否有可感知的变化 |

4. 结束后把 `artifacts\qml-spike\live.jsonl` 和观察结果发给我。文件每 10 秒记一行：内存、CPU、GPU、渲染帧数和帧间隔。

## 本地重跑

```powershell
python -m venv .venv-qml
.\.venv-qml\Scripts\python.exe -m pip install -r requirements-qml.txt
.\.venv-qml\Scripts\python.exe -m qml_spike.main --preview --cycle 1.5 --hud
.\.venv-qml\Scripts\python.exe -m qml_spike.verify
.\.venv-qml\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist/qml-spike --workpath .build-cache/qml-spike qml_spike/HexCompanionQml.spec
```

截图、指标和对比结果输出到 `artifacts/qml-spike`，该目录不加入源码仓库。
