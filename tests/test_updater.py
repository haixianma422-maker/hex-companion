import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aram_demo import updater
from aram_demo.updater import Updater


def release(version):
    return SimpleNamespace(TargetFullRelease=SimpleNamespace(Version=version), DeltasToTarget=[object()])


class FakeManager:
    def __init__(self, check=None, download=None):
        self.check_result, self.download_error = check, download
        self.applied = []

    def check_for_updates(self):
        if isinstance(self.check_result, Exception):
            raise self.check_result
        return self.check_result

    def download_updates(self, info):
        if self.download_error:
            raise self.download_error

    def wait_exit_then_apply_updates(self, info, silent=False, restart=True):
        self.applied.append((info.TargetFullRelease.Version, silent, restart))


class UpdaterTests(unittest.TestCase):
    def make(self, hosts, installed=True):
        """hosts: {source: FakeManager}; every call for a source returns the same fake."""
        self.calls, self.notes = [], []
        def manager(source, timeout_ms):
            if not installed:
                raise RuntimeError('This application is not properly installed')
            self.calls.append((source, timeout_ms))
            return hosts.get(source, FakeManager())
        sources = (('CNB', 'cnb'), ('GitHub', 'github'))
        result = Updater(lambda callback: callback(), self.notes.append, manager=manager, sources=sources)
        self.calls.clear()
        return result

    def run_check(self, item, manual=False):
        item.busy = True
        item._run(manual)

    def test_cnb_answer_is_used_without_contacting_github(self):
        cnb = FakeManager(check=release('0.8.1'))
        item = self.make({'cnb': cnb})
        self.run_check(item)
        self.assertEqual(item.ready_version, '0.8.1')
        self.assertEqual({source for source, _ in self.calls}, {'cnb'})
        self.assertEqual(self.calls[-1][1], updater.DOWNLOAD_TIMEOUT_MS)

    def test_current_version_on_cnb_ends_the_check(self):
        item = self.make({'cnb': FakeManager(check=None), 'github': FakeManager(check=release('0.8.1'))})
        self.run_check(item, manual=True)
        self.assertIsNone(item.ready)
        self.assertNotIn('github', [source for source, _ in self.calls])
        self.assertIn('已是最新版本', self.notes[-1])

    def test_unreachable_cnb_falls_back_to_github(self):
        item = self.make({'cnb': FakeManager(check=OSError('timed out')),
                          'github': FakeManager(check=release('0.8.1'))})
        self.run_check(item)
        self.assertEqual(item.ready_version, '0.8.1')

    def test_failed_cnb_download_falls_back_to_github(self):
        item = self.make({'cnb': FakeManager(check=release('0.8.1'), download=OSError('reset')),
                          'github': FakeManager(check=release('0.8.1'))})
        self.run_check(item)
        self.assertEqual(item.ready_version, '0.8.1')
        self.assertEqual([source for source, _ in self.calls], ['cnb', 'cnb', 'github', 'github'])

    def test_both_hosts_failing_reports_only_on_manual_check(self):
        hosts = {'cnb': FakeManager(check=OSError('a')), 'github': FakeManager(check=OSError('b'))}
        item = self.make(hosts)
        self.run_check(item)
        self.assertEqual(self.notes, [])
        self.assertFalse(item.busy)
        self.run_check(item, manual=True)
        self.assertIn('检查更新失败', self.notes[-1])
        self.assertIn('CNB', self.notes[-1])

    def test_copies_not_installed_by_velopack_never_check(self):
        item = self.make({}, installed=False)
        self.assertFalse(item.installed)
        item.check(manual=True)
        self.assertFalse(item.busy)
        self.assertIn('不是安装版', self.notes[-1])

    def test_downloaded_update_installs_once_on_exit(self):
        github = FakeManager(check=release('0.8.1'))
        item = self.make({'cnb': FakeManager(check=OSError('x')), 'github': github})
        self.run_check(item)
        item.apply_on_exit()
        item.apply_on_exit()
        self.assertEqual(github.applied, [('0.8.1', True, False)])

    def test_restart_hands_over_and_clears_the_pending_update(self):
        cnb = FakeManager(check=release('0.8.1'))
        item = self.make({'cnb': cnb})
        self.run_check(item)
        item.restart()
        item.apply_on_exit()
        self.assertEqual(cnb.applied, [('0.8.1', False, True)])
        self.assertIsNone(item.ready_version)

    def test_override_replaces_both_hosts(self):
        with patch.dict(updater.os.environ, {'HEX_COMPANION_UPDATE_URL': r'D:\feed'}):
            self.assertEqual(updater.feeds(), (('自定义', r'D:\feed'),))


if __name__ == '__main__':
    unittest.main()
