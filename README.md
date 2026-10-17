<p align="center"><img src="packaging/hex-companion.ico" width="64" alt="海克斯随行图标"></p>

# 海克斯随行 · Hex Companion

一款以轻量化、低资源占用为设计目标的 Windows 英雄联盟海克斯大乱斗浮窗助手。用一个紧凑浮窗，在选人时查看英雄梯队，在局内查看海克斯评级与模式出装参考。

界面使用 Qt Quick，动画由 GPU 合成并在独立渲染线程运行；资料按需获取、图标本地缓存；OCR 只处理三张海克斯的标题区域，重复画面复用识别结果。平时驻留托盘，进入海克斯模式后显示，需要时可收起为小浮标，减少屏幕占用。

## 界面预览

以下为程序实际窗口截图（Qt 界面），使用模拟客户端状态和本地真实资料，截图过程禁用网络。

<table>
  <tr><th>选人：英雄梯队</th><th>局内：海克斯与装备</th><th>设置：自定义快捷键</th></tr>
  <tr>
    <td valign="top"><img src="docs/images/champion-select.png" width="224" alt="选人浮窗，显示当前英雄与候选英雄梯队"></td>
    <td valign="top"><img src="docs/images/in-game.png" width="224" alt="局内浮窗，显示三张海克斯评级和四件带图标的装备"></td>
    <td valign="top"><img src="docs/images/hotkey-settings.png" width="300" alt="快捷键设置，配置识别、刷新和展开收起"></td>
  </tr>
</table>

收起后保留可拖动小浮标，单击或按快捷键展开：<img src="docs/images/collapsed-bubble.png" width="48" alt="可拖动海克斯浮标">

## 功能

- **轻量化优先**：局部 OCR、重复画面复用与本地缓存，减少重复识别和网络请求；界面静止时不重绘。
- **第二版界面**：墨紫底色、淡丁香英雄区域和酸柠黄强调色；选人双列候选、局内三列海克斯及四列装备。
- **选人浮窗**：显示当前英雄原画与客户端返回的可选英雄头像，按所选来源的 T 档和排名排序；高亮表示客户端当前选择。
- **数据来源切换**：在选人、局内浮窗顶部随时选择 OP.GG 或 101 数据站，选择会保存；设置中也可切换，两套资料分别缓存。
- **技能加点**：仅局内浮窗显示当前英雄的主、副技能，配技能图标、字母角标和箭头。
- **召唤师技能推荐**：仅在选人界面显示推荐图标组合；101 缺少的推荐由 OP.GG 补充并标明来源。
- **海克斯评级**：OCR 识别左、中、右三张增幅装置；OP.GG 使用 S～E，101 使用 S～C，保留各自评级。
- **核心出装与图标**：只显示海克斯大乱斗页面的三件核心成装与一双鞋，保留来源顺序；装备图标本地缓存。
- **可拖动浮标**：收起后变为小浮标，单击展开；面板和浮标均可拖动。
- **浮窗缩放**：拖动浮窗右下角等比例调整大小，文字、图片和点击区域同步缩放；松开后保存大小，窗口受屏幕工作区限制。
- **自定义快捷键**：默认 F8 展开 / 收起，在设置里修改识别、刷新和浮窗快捷键，保存后立即生效。
- **后台运行**：系统托盘管理，切出联盟或离开海克斯模式时隐藏；支持对局已经开始后启动。
- **本地识别与缓存**：只识别三个标题区域，重复画面复用结果，识别完成后原位更新卡片。
- **真实图片与状态**：英雄、海克斯、技能和装备使用真实静态资源；加载或读取失败时显示状态，缺图时保留名称。点击局内海克斯卡片可打开对应位置的手动修正。
- **界面动效**：英雄切换先淡出旧名字再滑入新名字，原画在新图解码后叠加淡入；识别结果只重播变化的那张卡片；来源切换期间内容变暗，资料到达后恢复；收起时面板缩向浮标，浮标弹出。动画在渲染线程运行，后台处理资料时不卡顿。识别活动反馈随实际任务结束，保存成功后按钮显示“已应用”。设置中可关闭动效，并读取 Windows 减少动画偏好。

本轮 185 项回归通过，[Qt 界面迁移验证](docs/qt-migration-verification.md)记录窗口行为、动效、打包体积与性能对比。Windows 发布包附 `verification.json` 和校验文件，覆盖中文 OCR、两套来源快照、图片、界面、托盘、快捷键及正常退出。内置 1,189 个基础图片资源。迁移后的完整版本使用离线客户端状态验收；真实对局只在迁移前的验证样例上测试过，见[样例记录](docs/qml-spike-verification.md)。

## 直接使用

从本仓库的 [Releases](https://github.com/haixianma422-maker/hex-companion/releases) 下载 Windows x64 发布包，解压后打开 `HexCompanion` 文件夹运行 `HexCompanion.exe`。`_internal` 文件夹保存运行所需文件，需与 EXE 放在一起。需要 Windows 10/11 x64，无需安装 Python。

1. 退出旧版工具，双击 EXE 并确认 Windows 管理员权限提示。
2. 将游戏视频设置中的窗口模式设为 **无边框**。桌面浮窗可能被独占全屏遮住。
3. 进入海克斯大乱斗；工具启动后先驻留系统托盘，在对应模式中自动显示浮窗。
4. 首次识别位置不合适时，打开“设置 → 识别与连接”，调整三个标题区域。
5. 右键托盘图标可打开设置或退出程序。

| 操作 | 效果 |
| --- | --- |
| F6 | 强制重新识别；取消手动修正的保留状态 |
| F7 | 刷新英雄榜、当前英雄资料及客户端状态 |
| F8 | 在展开面板与小浮标之间切换 |
| Esc / 收起 | 将面板收起为可拖动小浮标 |
| 单击浮标 | 展开面板 |

EXE 的设置和更新缓存保存在 `%LOCALAPPDATA%\HexCompanion\data`。获取新资料需要能够访问所选数据来源；101 的召唤师技能补充需要访问 OP.GG。已有缓存和内置 OCR 模型可离线使用。

在“设置 → 快捷键”中点击输入框后按下组合键，或填写 `F8`、`Ctrl+Alt+H` 等形式。重复、无效或已被其他程序占用的组合会提示错误，并保留原设置；设置窗口打开期间暂停全局快捷键。

## 数据来源

| 内容 | 来源与处理方式 |
| --- | --- |
| 英雄 T 档 | [OP.GG 海克斯大乱斗英雄榜](https://op.gg/zh-cn/lol/modes/aram-mayhem)，同档按来源排名排序 |
| 海克斯评级 | 对应英雄的 `/augments` 页面；原始 tier 0～5 映射为 S～E，见 [映射核对记录](data/tier_mapping_evidence.json) |
| 模式出装 | 对应英雄的 `/build` 页面，写入前校验 Mayhem 路径、页面标题和模式标记 |
| 技能与召唤师技能推荐 | 同一海克斯大乱斗 `/build` 页面，取来源第一组完整推荐；缺少数据时显示“暂无推荐” |
| 装备筛选 | Riot 装备元数据，见 [装备目录](data/item_catalog.json) |
| 装备图标 | Riot [Data Dragon](https://support-developer.riotgames.com/hc/en-us/articles/22698698001939-League-of-Legends) 静态资源，按装备 ID 缓存；已有快照对应的图标随 EXE 提供 |
| 中文分类标签 | CommunityDragon 中文游戏文本中的标签定义，见 [标签快照](data/augment_display_tags.json) |
| 101 英雄榜、海克斯评级、加点与出装 | [101 数据站](https://101.qq.com/) 使用的海克斯模式公开接口；评级保留来源 S / A / B / C |
| 技能与召唤师技能图标 | Riot Data Dragon 基础资源及推荐页面的图标；同版本的已知技能 URL 共用本地缓存。已校验的加点推荐可直接复用本地 Q／W／E 图标 |
| 英雄原画、头像与海克斯图标 | 原画、头像优先使用 Riot Data Dragon；腾讯提供原画备用地址及海克斯大小图，两个海克斯图标使用 CommunityDragon。目录保存在 `data/visual_catalog.json`，校验后的图片存放在 `visual-assets` |

首次进入对应模式时更新所选来源的英雄榜，选中英雄时按需更新详情；F7 可手动刷新。切换来源后重新读取对应缓存和资料，网络失败时保留该来源已有缓存。101 资料保存在数据目录下的 `sources/qq101`，OP.GG 沿用原目录。数据文件记录来源、抓取时间及来源版本或统计日期。

101 英雄 T 档沿用其网页按角色排名计算档位的规则；海克斯的 S～C 评级直接读取接口。OP.GG 的海克斯保留 S～E。两种来源的评级不合并换算。101 出装按其网页默认的核心组合排序取首组；召唤师技能补充使用经过海克斯模式校验的 OP.GG 推荐，并单独标明来源。

出装按**英雄与海克斯大乱斗模式**提供，不根据已选海克斯动态配装。从所选来源的首组核心中取前三件成装，过滤散件，并取首双推荐鞋子。资料不足时保留空位。图标在后台按需获取，下载失败时保留名称，可按刷新快捷键重试。

随仓库提供英雄梯队和经过模式校验的部分英雄详情快照。客户端连接凭据仅用于本机状态读取；标题截图在内存中处理。工具不代替用户选人或操作游戏。

## 源码运行

使用 Windows 与 Python 3.13。从仓库根目录运行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start_companion.cmd
```

也可双击 `setup_demo.cmd` 安装依赖，再启动工具。联盟以管理员权限运行时，使用 `start_companion_admin.cmd`；该入口会请求 Windows 权限确认。

功能与稳定性验收使用上述正常入口（`start_demo.cmd` 也是正常入口），连接真实客户端，执行自动识别、在线资料更新、设置与快捷键等完整流程。工具先驻留系统托盘，进入海克斯大乱斗后自动显示浮窗。

不开联盟查看界面：

```powershell
.\preview_companion.cmd
```

预览中双击浮窗标题切换选人与游戏界面；点击齿轮打开设置，`F8` 收起/展开，从托盘退出。浮窗不接收键盘焦点，因此不提供窗口内快捷键。源码预览的设置与缓存使用 `.build-cache` 下的独立目录；正常运行仍使用项目的 `data` 目录。

预览沿用正式版的浮窗、设置、托盘和单实例流程；模拟客户端状态仅用于提供选人与局内场景。浮窗不占任务栏，右下角系统托盘提供设置和退出入口。正常版或预览已在运行时，再次启动不会打开第二个实例。

运行日志保存在数据目录的 `logs/runtime.log`，源码正常运行对应 `data/logs/runtime.log`，EXE 对应 `%LOCALAPPDATA%\HexCompanion\data\logs\runtime.log`。日志记录启动模式、连接阶段、资料来源、识别结果变化、异常和每分钟的资源采样；不写入连接令牌或游戏截图。单个日志达到约 2 MB 时轮转，保留三个备份。

## 测试与打包

自动测试（在不可见的独立桌面运行，不抢焦点）：

```powershell
.\.venv\Scripts\python.exe scripts/run_native_tests.py
```

窗口行为验收（置顶、不抢焦点、阴影可穿透点击、静止不重绘、三档缩放截图），可加 `--exe` 检查打包版：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts/verify_overlay.py
```

构建程序文件夹：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts/build_exe.py
```

成品位于 `dist/HexCompanion/`，`HexCompanion.exe` 与 `_internal` 文件夹一起包含 Python、Qt、OCR 模型、两套来源的已校验初始快照和本地图片。采用文件夹形式是因为单文件 EXE 每次启动都要先解压 Qt，启动需 5–6 秒；文件夹形式约 1 秒。可用 `--dist-dir dist/版本目录` 单独输出新版，避免覆盖运行中的旧版本。正常启动会请求管理员权限。

对实际 EXE 执行离线验收，并生成分享包：

```powershell
$exePath = (Resolve-Path .\dist\HexCompanion\HexCompanion.exe).Path
$reportPath = Join-Path (Get-Location) 'dist\verification.json'
$checkProcess = Start-Process -FilePath $exePath -ArgumentList @('--self-test', ('"' + $reportPath + '"')) -Wait -PassThru
if ($checkProcess.ExitCode -ne 0) { throw 'EXE 验收失败，请检查 verification.json' }
.\.venv\Scripts\python.exe scripts/package_binary.py --exe $exePath --check $reportPath
```

验收会短暂显示程序窗口，禁用网络并使用临时设置，不连接真实对局；也可用 `scripts/check_frozen_hidden.py` 在不可见桌面运行。打包脚本核对验收报告与 EXE 的 SHA-256，检查图片、两套来源、OCR 模型、界面文件及个人文件排除情况。分享包 `HexCompanion-Windows-x64.zip`、`release_manifest.json` 和 EXE 校验文件输出在程序文件夹的上一级目录，包内附使用说明、MIT 许可证、第三方依赖许可证和验收报告。

## 常见问题

**已经进入对局，但看不到浮窗**

先切换为无边框模式，并将联盟置于前台。在托盘打开“设置 → 识别与连接”检查状态；已核实 `InProgress · 队列 2400` 可以在对局中启动。独占全屏下曾出现浮窗被遮挡，切换无边框后恢复。

**客户端连接失败**

EXE 启动时确认管理员提示。源码版使用管理员入口，必要时在设置里选择包含 `LeagueClient.exe` 或 `LeagueClient` 子目录的安装位置。目前识别匹配队列 `2400` 与国服自定义海克斯队列 `3270`，普通大乱斗 `450` 不触发。

**部分海克斯显示待确认**

按 F6 重识别，或调整三个标题区域。也可在设置里手动选择选项。OCR 无法确定名称时保留待确认状态；手动修正后按 F6 恢复自动识别。

**切换 101 后加载较慢或图片不完整**

首次获取 101 资料时，已校验的评级与加点先显示，名称和图标在后台补齐。近期已校验的 OP.GG 召唤师技能缓存直接用于补充，并保留来源标记。图片下载完成一张就刷新一张；超出单批预算的图片继续加载，网络失败的图片间隔 60 秒重试。首次加载耗时取决于来源服务器和网络状态。

本次 EXE 内置 1,189 个基础资源，合计约 40 MB，覆盖 173 位英雄的基础原画与头像、290 个海克斯图标、553 个技能与召唤师技能图标。已有图片直接本地加载，缺失时才请求网络。缓存目录清单和文件 SHA-256 位于 `data/visual-assets/resource-cache-manifest.json`。

来源切换时，推荐内容变暗直到新来源的资料到达，再用 200ms 恢复；设置中关闭动效后直接显示结果。窗口和操作按钮在过渡期间保持可用。

可选英雄列表使用原生惯性滚动；列表增减或换位时卡片平移到新位置。资料刷新时复用已有卡片，悬停状态和滚动位置保持不变。

自动扫描期间“重新识别”按钮保持稳定；手动点击或按 F6 后显示“识别中”。更新源码后需退出工具并重新启动，正在运行的进程不会自动载入新代码。

**如何更新本地元数据**

`scripts/refresh_data.py` 更新 OP.GG 英雄榜与指定英雄；`scripts/sync_item_catalog.py --patch 版本号` 更新装备目录；`scripts/audit_augment_tags.py` 检查中文标签快照。以上脚本支持 `--help`。`scripts/sync_item_icons.py` 下载已校验英雄快照对应的装备图标，`scripts/export_demo_images.py` 重新生成上方模拟预览截图。

`scripts/cache_resources.py` 更新基础图片目录并补齐本地缓存；已有有效文件会复用。可加 `--workers 2` 降低下载并发，或用 `--only reported` 只准备此次报告的泽拉斯及两项海克斯图片。图片预取是维护步骤，运行工具时按当前英雄和选项补图。

## 目录

```text
aram_demo/       客户端连接、OCR、数据处理；qt_overlay.py、qt_settings.py 与 qml/ 为界面
data/           可共享的数据快照；个人 settings.json 被忽略
docs/images/    选人、局内、快捷键设置和浮标演示图片
scripts/        数据更新、界面验证、EXE 构建与验收
tests/          自动测试
packaging/      图标、使用说明和第三方依赖说明
app.py          启动入口
```

## 许可证

本项目原创代码和文档采用 [MIT License](LICENSE)，版权归 haixianma422-maker 所有。

第三方依赖、OCR 模型、OP.GG 统计快照、Riot Games 游戏文本及图标等资源，适用各自的许可证或服务条款。来源与许可说明见 [第三方组件说明](packaging/THIRD_PARTY.txt)；Windows 发布包中的 `licenses/` 目录提供依赖许可证文本。
