# 海克斯随行 · 详细说明

[README](../README.md) 介绍功能和基本用法，本页补充其余细节，分为使用和开发两部分。

- [数据来源与刷新](#数据来源与刷新)
- [海克斯识别](#海克斯识别)
- [程序更新](#程序更新)
- [界面细节](#界面细节)
- [常见问题](#常见问题)
- [源码运行与预览](#源码运行与预览)
- [测试与打包](#测试与打包)
- [发布自动更新版本](#发布自动更新版本)
- [维护数据与资源](#维护数据与资源)
- [目录与验证记录](#目录与验证记录)

## 数据来源与刷新

| 内容 | 来源与处理方式 |
| --- | --- |
| 英雄 T 档 | [OP.GG 海克斯大乱斗英雄榜](https://op.gg/zh-cn/lol/modes/aram-mayhem)，同档按来源排名排序 |
| 海克斯评级 | 对应英雄的 `/augments` 页面；原始 tier 0～5 映射为 S～E，见 [映射核对记录](../data/tier_mapping_evidence.json) |
| 模式出装 | 对应英雄的 `/build` 页面，写入前校验 Mayhem 路径、页面标题和模式标记 |
| 技能与召唤师技能推荐 | 同一海克斯大乱斗 `/build` 页面，取来源第一组完整推荐；缺少数据时显示“暂无推荐” |
| 装备筛选 | Riot 装备元数据，见 [装备目录](../data/item_catalog.json) |
| 装备图标 | Riot [Data Dragon](https://support-developer.riotgames.com/hc/en-us/articles/22698698001939-League-of-Legends) 静态资源，按装备 ID 缓存；已有快照对应的图标随程序提供 |
| 中文分类标签 | CommunityDragon 中文游戏文本中的标签定义，见 [标签快照](../data/augment_display_tags.json) |
| 海克斯名称表 | 101 数据站海克斯字典中已上线的海克斯大乱斗条目，排除测试服与内部占位条目，只用于识别名称、不含评级，见 [名称表](../data/augment_catalog.json)；每天最多更新一次 |
| 101 英雄榜、海克斯评级、加点与出装 | [101 数据站](https://101.qq.com/) 使用的海克斯模式公开接口；评级保留来源 S / A / B / C |
| 技能与召唤师技能图标 | Riot Data Dragon 基础资源及推荐页面的图标；同版本的已知技能 URL 共用本地缓存 |
| 英雄原画、头像与海克斯图标 | 原画、头像优先使用 Riot Data Dragon；腾讯提供原画备用地址及海克斯大小图，两个海克斯图标使用 CommunityDragon。目录保存在 `data/visual_catalog.json` |

**刷新规则**

- 首次进入对应模式时更新所选来源的英雄榜；选中英雄时按需更新这名英雄的详情。
- 英雄详情超过 24 小时，或来源英雄榜已是更新的游戏版本时，切到这名英雄会在后台重新获取。F7 立即刷新当前英雄，不受 24 小时限制。
- 来源尚未评级的新海克斯按名称表识别，显示名称和“暂无评级”；来源评级后，重新获取的详情会替换为来源评级。
- 网络失败时保留已有缓存。两套来源分别缓存：101 资料在数据目录的 `sources/qq101`，OP.GG 沿用原目录。数据文件记录来源、抓取时间及来源版本或统计日期。

**评级与出装规则**

- 101 英雄 T 档沿用其网页按角色排名计算档位的规则；海克斯 S～C 评级直接读取接口。OP.GG 海克斯保留 S～E。两种来源的评级不合并换算。
- 出装按英雄与海克斯大乱斗模式提供，不根据已选海克斯动态配装。从首组核心中取前三件成装，过滤散件，并取首双推荐鞋子；资料不足时保留空位。
- 101 出装取网页默认的核心组合首组；101 缺少的召唤师技能推荐由经过模式校验的 OP.GG 推荐补充，并标明来源。

随仓库提供英雄梯队和经过模式校验的部分英雄详情快照，对应游戏版本 16.21.1（海克斯大乱斗 26.21）。客户端连接凭据仅用于本机状态读取；标题截图在内存中处理。工具不代替用户选人或操作游戏。

## 海克斯识别

识别只截取左、中、右三个标题区域。画面不像选择界面时跳过识别；画面没变时复用上次结果。

1. Windows 自带的简体中文文字识别先读标题，最多换三种放大比例，读出的文字对上海克斯名称即停。每张卡约 5 ms。
2. 三次都对不上时，由内置的 PP-OCRv6 识别模型补读。游戏标题是固定位置的奶白色文字，程序按颜色找出标题行，不需要检测模型。
3. 系统没有中文文字识别组件时只用内置模型，每张卡约 10 ms。组件可在“设置 → 时间和语言 → 语言和区域”中，为“中文(简体)”安装“光学字符识别”。

识别结果与英雄的海克斯列表模糊匹配；无法确定时保留“待确认”，可按 F6 重识别、调整标题区域，或点击卡片手动选择。手动修正后按 F6 恢复自动识别。

## 程序更新

- 安装包装到 `%LOCALAPPDATA%\HaixianMa.HexCompanion`；免安装包解压到任意位置即可，`Update.exe` 和 `current` 文件夹需与 `海克斯随行.exe` 放在一起。
- 启动约 1 分钟后检查一次新版本，之后每 6 小时检查一次；先查 [CNB 镜像](https://cnb.cool/haixianma422-maker/hex-companion)，连不上再查 GitHub。新版本在后台下载，通常只需下载差量包。
- 下载完成后发一条托盘通知，托盘菜单出现“重启并更新”。组队、选人和对局中不会重启；直接退出时也会自动安装。
- 托盘的“检查更新”和“重启并更新”用对话框回复结果，关闭 Windows 通知或开启勿扰时也能看到。
- v0.8.0 的文件名为 `HaixianMa.HexCompanion-win-Setup.exe` 和 `HaixianMa.HexCompanion-win-Portable.zip`，v0.9.0 起为 `HexCompanion-Windows-x64-Setup.exe` 和 `HexCompanion-Windows-x64.zip`。v0.7.0 及更早的压缩包不含更新程序，需要重新下载一次。

设置和缓存保存在 `%LOCALAPPDATA%\HexCompanion\data`，与安装位置无关，更新和重装都会保留。

## 界面细节

- 英雄切换先淡出旧名字再滑入新名字；原画在新图解码后叠加淡入；识别结果只重播变化的那张卡片。
- 来源切换时推荐内容变暗，新来源的资料到达后用 200 ms 恢复；窗口和按钮在过渡期间保持可用。
- 收起时面板缩向浮标，浮标弹出。动画在渲染线程运行，后台处理资料时不卡顿。设置中可关闭动效，也会读取 Windows“减少动画”偏好。
- 可选英雄列表使用惯性滚动；列表增减或换位时卡片平移到新位置，悬停状态和滚动位置保持不变。
- 自动扫描期间“重新识别”按钮保持不变；手动点击或按 F6 后显示“识别中”，任务结束即恢复。设置保存成功后按钮显示“已应用”。
- 程序内置 1,189 个基础图片资源，约 42 MB：173 位英雄的原画与头像、290 个海克斯图标、553 个技能与召唤师技能图标。缺失的图片按需下载，网络失败的图片间隔 60 秒重试。清单和 SHA-256 在 `data/visual-assets/resource-cache-manifest.json`。

运行日志在数据目录的 `logs/runtime.log`（源码运行为 `data/logs/runtime.log`），记录启动模式、连接阶段、资料来源、识别结果变化、异常和每分钟的资源采样，不写入连接令牌或游戏截图。单个日志约 2 MB 时轮转，保留三个备份。

## 常见问题

**已经进入对局，但看不到浮窗**

将游戏窗口模式设为无边框，并把联盟置于前台；独占全屏可能遮住浮窗。在托盘打开“设置 → 识别与连接”检查状态。对局开始后再启动工具也能识别当前对局。

**客户端连接失败**

启动时确认管理员权限提示。必要时在设置里选择包含 `LeagueClient.exe` 或 `LeagueClient` 子目录的安装位置。目前匹配队列 `2400` 与国服自定义海克斯队列 `3270`，普通大乱斗 `450` 不触发。

**部分海克斯显示待确认**

按 F6 重识别，或在“设置 → 识别与连接”调整三个标题区域；也可点击卡片手动选择。识别方式见[海克斯识别](#海克斯识别)。

**双击程序没有反应**

同一时间只能运行一个海克斯随行。已有一个在运行时，再次启动会直接退出；请在托盘找到它，或先从托盘退出再启动。

**切换 101 后加载较慢或图片不完整**

首次获取 101 资料时，评级与加点先显示，名称和图标在后台补齐；图片下载完成一张就刷新一张。加载耗时取决于来源服务器和网络状态。

## 源码运行与预览

使用 Windows 与 Python 3.13。从仓库根目录运行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start_companion.cmd
```

也可双击 `setup_demo.cmd` 安装依赖。联盟以管理员权限运行时，使用 `start_companion_admin.cmd`。源码运行的设置与缓存在项目的 `data` 目录；更新源码后需退出工具并重新启动。

不开联盟查看界面：

```powershell
.\preview_companion.cmd
```

预览中双击浮窗标题切换选人与局内界面；点击齿轮打开设置，`F8` 收起或展开，从托盘退出。预览使用 `.build-cache` 下的独立设置与缓存，模拟客户端状态只用于提供场景。

## 测试与打包

窗口验收和打包需要先安装构建依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

自动测试在不可见的独立桌面运行，不抢焦点：

```powershell
.\.venv\Scripts\python.exe scripts/run_native_tests.py
```

窗口行为验收（置顶、不抢焦点、阴影可穿透点击、静止不重绘、三档缩放截图），可加 `--exe` 检查打包版：

```powershell
.\.venv\Scripts\python.exe scripts/verify_overlay.py
```

构建程序文件夹：

```powershell
.\.venv\Scripts\python.exe scripts/build_exe.py
```

成品在 `dist/HexCompanion/`，`HexCompanion.exe` 与 `_internal` 文件夹一起包含 Python、Qt、识别模型、两套来源的初始快照和本地图片。可用 `--dist-dir dist/版本目录` 输出到别处，避免覆盖运行中的版本。采用文件夹形式是因为单文件 EXE 每次启动都要先解压，实测约 5 秒；文件夹形式约 0.3 秒。

对实际 EXE 离线验收：

```powershell
.\.venv\Scripts\python.exe scripts/check_frozen_hidden.py dist/HexCompanion/HexCompanion.exe dist/verification.json
```

验收在不可见桌面运行，禁用网络并使用临时设置，覆盖中文识别（两个识别引擎各自验证）、两套来源快照、图片、界面、托盘、快捷键及正常退出。`scripts/package_binary.py --exe … --check …` 再核对验收报告与 EXE 的 SHA-256，检查打包内容，并在程序文件夹的上一级生成本地分享包 `HexCompanion-Windows-x64.zip`。这个本地分享包不含更新程序，与 Releases 中同名的免安装包不同，发布时不上传。

## 发布自动更新版本

1. 修改 `aram_demo/__init__.py` 的 `__version__`，提交并推送到 `main`。
2. 构建并验收（见上一节）。
3. 用 Velopack 打包；需要 .NET SDK 和与 `requirements.txt` 中 velopack 同版本的 vpk：

```powershell
dotnet tool install -g vpk --version 1.2.161
.\.venv\Scripts\python.exe scripts/publish_update.py --exe dist/版本目录/HexCompanion/HexCompanion.exe --check dist/版本目录/verification.json --notes 版本说明.md
```

不加 `--upload` 时只打包，产物在 `dist/velopack-releases`。该目录保留历次完整包和差量包，下一版据此生成差量；目录不存在时，脚本从 GitHub 已发布的更新源取回上一版完整包。

4. 加 `--upload` 正式发布。前提：在已推送的 `main` 上、工作区无未提交修改；`gh` 已登录；已添加 CNB 远程仓库（`git remote add cnb https://cnb.cool/haixianma422-maker/hex-companion.git`）；环境变量 `CNB_TOKEN` 是有 Release 读写权限的 CNB 令牌。已用同一份构建打过包时，上传沿用现有包，不重新打包。

脚本在当前提交创建 `v版本号` 标签并推送到两边，然后：

- **GitHub**：版本 Release 上传完整包、最近 10 个差量包、安装包和免安装包，最后上传 `releases.win.json`，再标为最新正式版。客户端从 GitHub 固定的 `latest/download` 地址读取更新，所以带更新的版本不能标为预发布。
- **CNB**：完整包、差量包和 `releases.win.json` 上传到固定标签 `update-feed` 的 Release（“自动更新源”），新更新源上线后删除它不再列出的旧包；安装包和免安装包上传到本版 Release，再标为最新正式版。`update-feed` 标签首次发布时创建，之后不移动，这个 Release 不要删除。

安装包和免安装包以 `HexCompanion-Windows-x64-Setup.exe`、`HexCompanion-Windows-x64.zip` 发布；更新包保留 `HaixianMa.HexCompanion` 前缀，已安装的程序靠这个标识找到更新。

CNB 上传中断时，用同一版本号补传；已完整上传的附件会跳过，不重新打包，也不再上传 GitHub：

```powershell
.\.venv\Scripts\python.exe scripts/publish_update.py --cnb-only --notes 版本说明.md
```

CNB 仓库地址改变时，同步修改 `aram_demo/updater.py` 的 `CNB_REPO`。测试时可设置环境变量 `HEX_COMPANION_UPDATE_URL` 指向本地更新目录，代替两个线上地址。

## 维护数据与资源

- `scripts/refresh_data.py`：更新 OP.GG 英雄榜与指定英雄。
- `scripts/sync_item_catalog.py --patch 版本号`：更新装备目录；`scripts/sync_item_icons.py` 下载已校验快照对应的装备图标。
- `scripts/audit_augment_tags.py`：检查中文标签快照。
- `scripts/cache_resources.py`：更新基础图片目录并补齐本地缓存，已有有效文件会复用；可加 `--workers 2` 降低下载并发。
- `scripts/export_demo_images.py`：重新生成 README 的界面截图。
- `scripts/verify_game_capture.py 截图.png --champion-id 英雄ID`：用一张游戏截图离线验证识别结果。

以上脚本支持 `--help`。

## 目录与验证记录

```text
aram_demo/       客户端连接、识别、数据处理；qt_overlay.py、qt_settings.py 与 qml/ 为界面
data/            可共享的数据快照；个人 settings.json 被忽略
docs/            详细说明、验证记录和界面截图
scripts/         数据更新、界面验证、构建、验收与发布
tests/           自动测试
packaging/       图标、使用说明和第三方组件说明
app.py           启动入口
```

- v0.9.0：231 项自动测试通过；打包版离线验收通过；已在真实对局中使用。识别改造时在 360 张合成卡片（同一英雄的 30 个海克斯名称、4 种字体、1440p/1080p/720p）上全部识别正确。
- [Qt 界面迁移验证](qt-migration-verification.md)：窗口行为、动效、打包体积与性能对比。
- [QML 选人面板验证样例](qml-spike-verification.md)；[动效与浮窗缩放验证](motion-v2-verification.md)为 Tk 界面时期的记录。
