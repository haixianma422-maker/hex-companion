"""Program updates through Velopack: CNB first for mainland users, GitHub as fallback.

Each GitHub release carries releases.win.json and its packages, so the fixed latest/download
address is a complete Velopack feed. CNB documents no such address, so its feed lives in one
release whose tag never changes; the publish script replaces its packages each time.
"""
import logging
import os
import threading

from . import __version__

PACK_ID = 'HaixianMa.HexCompanion'
GITHUB_REPO = 'haixianma422-maker/hex-companion'
CNB_REPO = 'haixianma422-maker/hex-companion'
CNB_FEED_TAG = 'update-feed'
FEEDS = (('CNB', f'https://cnb.cool/{CNB_REPO}/-/releases/download/{CNB_FEED_TAG}'),
         ('GitHub', f'https://github.com/{GITHUB_REPO}/releases/latest/download'))
CHECK_TIMEOUT_MS = 15_000
DOWNLOAD_TIMEOUT_MS = 30 * 60_000
FIRST_CHECK_MS = 60_000
CHECK_INTERVAL_MS = 6 * 3600_000

logger = logging.getLogger(__name__)


def feeds():
    """HEX_COMPANION_UPDATE_URL replaces both hosts, e.g. with a local feed folder for testing."""
    override = os.environ.get('HEX_COMPANION_UPDATE_URL')
    return (('自定义', override),) if override else FEEDS


def velopack_manager(source, timeout_ms):
    """Raises RuntimeError when this copy was not installed by Velopack (source runs, old zips)."""
    import velopack
    if source.startswith(('http://', 'https://')):
        # The timeout covers connection and transfer, so downloads get a separate manager.
        source = velopack.HttpSource(source, velopack.HttpOptions([], timeout_ms))
    return velopack.UpdateManager(source)


class Updater:
    """One check and download at a time, off the GUI thread; results return through dispatch.

    notify carries background news (a finished download). answer replies to a check the user
    started, so it needs a channel that system notification settings cannot hide.
    """

    def __init__(self, dispatch, notify, answer=None, on_ready=None, manager=velopack_manager, sources=None):
        self.dispatch, self.notify, self.on_ready, self.manager = dispatch, notify, on_ready, manager
        self.answer = answer or notify
        self.sources = sources or feeds()
        self.busy = False
        self.ready = None
        try:
            self.manager(self.sources[0][1], CHECK_TIMEOUT_MS)
            self.installed = True
        except Exception as exc:
            logger.info('self-update unavailable: %s', exc)
            self.installed = False

    @property
    def ready_version(self):
        return self.ready[1].TargetFullRelease.Version if self.ready else None

    def check(self, manual=False):
        if not self.installed:
            if manual:
                self.answer('当前运行的不是安装版，无法自动更新。请从发布页下载安装包。')
            return
        if self.ready:
            if manual:
                self.answer(f'新版本 {self.ready_version} 已下载，在托盘菜单选择“重启并更新”即可安装。')
            return
        if self.busy:
            if manual:
                self.answer('正在检查或下载更新，请稍候。')
            return
        self.busy = True
        threading.Thread(target=self._run, args=(manual,), daemon=True).start()

    def _run(self, manual):
        try:
            result = self._fetch(manual)
        except Exception as exc:
            result = exc
        self.dispatch(lambda: self._finished(result, manual))

    def _fetch(self, manual):
        """None when current; (manager, info) once downloaded. A failing host hands over to the next."""
        errors = []
        for name, source in self.sources:
            try:
                info = self.manager(source, CHECK_TIMEOUT_MS).check_for_updates()
            except Exception as exc:
                logger.warning('update check via %s failed: %s', name, exc)
                errors.append(f'{name}：{exc}')
                continue
            if info is None:
                logger.info('update check via %s: current %s', name, __version__)
                return None
            version = info.TargetFullRelease.Version
            logger.info('update %s found via %s, deltas=%s', version, name, len(info.DeltasToTarget))
            if manual:
                self.dispatch(lambda: self.answer(f'发现新版本 {version}，正在后台下载。\n'
                                                  '下载完成后，托盘菜单会出现“重启并更新”。'))
            try:
                manager = self.manager(source, DOWNLOAD_TIMEOUT_MS)
                manager.download_updates(info)
            except Exception as exc:
                logger.warning('update download via %s failed: %s', name, exc)
                errors.append(f'{name}：{exc}')
                continue
            return manager, info
        raise RuntimeError('；'.join(errors)[:200])

    def _finished(self, result, manual):
        self.busy = False
        if isinstance(result, Exception):
            if manual:
                self.answer('检查更新失败：' + str(result)[:120])
            return
        if result is None:
            if manual:
                self.answer(f'已是最新版本 {__version__}。')
            return
        self.ready = result
        logger.info('update %s downloaded', self.ready_version)
        self.notify(f'新版本 {self.ready_version} 已下载。在托盘菜单选择“重启并更新”，或退出时自动安装。')
        if self.on_ready:
            self.on_ready()

    def restart(self):
        """Update.exe waits for this process to exit, installs, then starts the new version."""
        manager, info = self.ready
        self.ready = None
        manager.wait_exit_then_apply_updates(info, silent=False, restart=True)

    def apply_on_exit(self):
        if self.ready:
            manager, info = self.ready
            self.ready = None
            manager.wait_exit_then_apply_updates(info, silent=True, restart=False)
