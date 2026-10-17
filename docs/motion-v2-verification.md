# 动效与浮窗缩放验证

> v0.4.0-preview（Tk 界面）的记录。界面迁移到 Qt Quick 后，文中的 `verify_motion_ui.py` 已移除，现行验证见 [Qt 界面迁移验证](qt-migration-verification.md)。

日期：2026-10-15。版本：v0.4.0-preview。

本次更新英雄切换、来源更新、单卡结果揭示、识别活动反馈、设置切换及浮标展开收起动效，并加入右下角等比例缩放与大小保存。

## 已执行检查

- 完整回归：184 项通过，其中动效与缩放专项 18 项。
- 原生窗口：以 1.0、1.25、1.5 逻辑 DPI 比例检查坐标、图片、控件、点击区域和右下角拖拽缩放；窗口回调错误为 0，结束后动效任务为 0。
- 中断与失败：连续切换、来源请求失败、识别中移出按钮、关闭动画、隐藏后恢复、拖动后缩放及工作区变化均有回归检查。
- 实际 Windows EXE：离线中文 OCR、两套来源快照、1,189 份缓存资源、托盘、快捷键、缩放保存、“已应用”反馈及正常退出通过。
- 参考演示：内嵌参考包哈希验证通过，六场景浏览器交互通过，四张基线截图一致，外网请求和页面错误均为 0。

逻辑 DPI 检查使用程序的显式绘图比例。此次没有切换 Windows 物理显示缩放，也没有运行真实游戏对局。

## 本地重跑

在仓库根目录、已安装依赖的 Windows 环境运行：

```powershell
.\.venv\Scripts\python.exe scripts/run_native_tests.py
.\.venv\Scripts\python.exe scripts/run_native_tests.py test_motion_v2.py
.\.venv\Scripts\python.exe scripts/verify_motion_ui.py
```

测试在独立隐藏桌面执行。原生截图与检查报告输出到本地 `artifacts/motion-v2/native`，该目录不加入源码仓库。

构建后运行实际 EXE 验收：

```powershell
.\.venv\Scripts\python.exe scripts/check_frozen_hidden.py dist/Motion-V2-20261015/HexCompanion.exe dist/Motion-V2-20261015/verification.json
```

Release 中的 `verification.json` 记录实际 EXE 的 SHA-256。`SHA256SUMS.txt` 可用于校验下载的 ZIP 和 EXE。
