<p align="center"><img src="packaging/hex-companion.ico" width="64" alt="海克斯随行图标"></p>

# 海克斯随行 · Hex Companion

一款以轻量化、低资源占用为设计目标的 Windows 英雄联盟海克斯大乱斗浮窗助手。用一个紧凑浮窗，在选人时查看英雄梯队，在局内查看海克斯评级与模式出装参考。

平时驻留托盘，进入海克斯模式后显示，需要时可收起为小浮标。更多细节见 [详细说明](docs/guide.md)。

## 界面预览

以下为程序实际窗口截图，使用模拟客户端状态和本地真实资料。

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

- **选人**：显示当前英雄原画与可选英雄头像，按所选来源的 T 档和排名排序；推荐召唤师技能。
- **局内**：自动识别三张海克斯并显示评级（OP.GG 为 S～E，101 为 S～C），显示三件核心成装、一双鞋和技能加点。
- **两套数据来源**：浮窗顶部随时切换 OP.GG 或 101 数据站，两套资料分别缓存；尚未评级的新海克斯也能识别出名称。
- **快速识别**：优先使用 Windows 自带的文字识别，读不准时由内置模型补读，每张卡约 5 ms；画面没变时复用结果。
- **浮窗操作**：面板和浮标均可拖动；拖动右下角等比缩放；快捷键可自定义；点击海克斯卡片可手动修正。
- **自动更新**：后台下载差量包，在托盘选“重启并更新”或退出时安装；国内优先走 CNB 镜像。
- **轻量**：界面由 GPU 合成，静止时不重绘；资料按需获取，图片本地缓存。安装包约 140 MB。

## 下载与使用

从 [Releases](https://github.com/haixianma422-maker/hex-companion/releases) 或 [CNB 镜像](https://cnb.cool/haixianma422-maker/hex-companion/-/releases) 下载，需要 Windows 10/11 x64：

- 安装包 `HexCompanion-Windows-x64-Setup.exe`：运行后自动安装并创建快捷方式。
- 免安装包 `HexCompanion-Windows-x64.zip`：解压后运行 `海克斯随行.exe`，同目录的 `Update.exe` 和 `current` 文件夹需保留。

1. 启动并确认 Windows 管理员权限提示。工具先驻留系统托盘，进入海克斯大乱斗后自动显示浮窗。
2. 将游戏窗口模式设为 **无边框**，独占全屏可能遮住浮窗。
3. 识别位置不合适时，在“设置 → 识别与连接”调整三个标题区域。
4. 右键托盘图标可打开设置、检查更新或退出。

| 操作 | 效果 |
| --- | --- |
| F6 | 强制重新识别；取消手动修正的保留状态 |
| F7 | 刷新英雄榜、当前英雄资料及客户端状态 |
| F8 | 在展开面板与小浮标之间切换 |
| Esc / 收起 | 将面板收起为可拖动小浮标 |

快捷键可在“设置 → 快捷键”修改。设置和缓存保存在 `%LOCALAPPDATA%\HexCompanion\data`，更新和重装都会保留。v0.7.0 及更早的压缩包不含更新程序，需要重新下载一次。

## 数据来源

英雄梯队、海克斯评级、出装与加点来自 [OP.GG 海克斯大乱斗](https://op.gg/zh-cn/lol/modes/aram-mayhem) 和 [101 数据站](https://101.qq.com/)；图标与原画来自 Riot Data Dragon、腾讯和 CommunityDragon。英雄详情超过 24 小时或游戏版本更新后自动重新获取，F7 可立即刷新。来源明细与刷新规则见 [详细说明](docs/guide.md#数据来源与刷新)。

客户端连接凭据仅用于本机状态读取，标题截图在内存中处理。工具不代替用户选人或操作游戏。

## 常见问题

- **看不到浮窗**：确认游戏为无边框模式、联盟在前台，并在“设置 → 识别与连接”检查状态。
- **海克斯显示待确认**：按 F6 重识别，或调整标题区域、点击卡片手动选择。
- **双击程序没有反应**：已有一个在运行，请在托盘找到它。

更多问题见 [详细说明](docs/guide.md#常见问题)。

## 开发

使用 Windows 与 Python 3.13：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start_companion.cmd
```

`preview_companion.cmd` 不连接联盟、用模拟状态预览界面；`scripts/run_native_tests.py` 运行全部自动测试。构建、验收与发布流程见 [详细说明](docs/guide.md#测试与打包)。

## 许可证

本项目原创代码和文档采用 [MIT License](LICENSE)，版权归 haixianma422-maker 所有。

第三方依赖、识别模型、OP.GG 统计快照、Riot Games 游戏文本及图标等资源，适用各自的许可证或服务条款，见 [第三方组件说明](packaging/THIRD_PARTY.txt)；发布包中的 `licenses/` 目录提供依赖许可证文本。
