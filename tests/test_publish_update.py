import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from aram_demo.updater import CNB_FEED_TAG, FEEDS
from scripts import publish_update
from scripts.publish_update import CNB


class FakeCNB(CNB):
    """Records API calls; releases maps tag -> release JSON as CNB would return it."""

    def __init__(self, releases=None, put_errors=0):
        super().__init__('token')
        self.releases = releases or {}
        self.put_errors = put_errors
        self.calls, self.puts = [], []

    def request(self, method, url, payload=None, missing_ok=False, optional=False):
        self.calls.append((method, url.removeprefix(self.base), payload))
        if method == 'GET':
            tag = url.rsplit('/', 1)[-1]
            return self.releases.get(tag) if missing_ok else {}
        if method == 'POST' and url == self.base:
            release = {'id': f'new-{payload["tag_name"]}', 'assets': []}
            self.releases[payload['tag_name']] = release
            return release
        return {}

    def put(self, release_id, path, size):
        if self.put_errors:
            self.put_errors -= 1
            raise ConnectionResetError('reset')
        self.puts.append((release_id, path.name))


class CNBPublishTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        def file(name, size):
            path = self.root / name
            path.write_bytes(b'x' * size)
            return path
        self.packages = [file('App-0.8.1-full.nupkg', 30), file('App-0.8.1-delta.nupkg', 5)]
        self.installers = [file('App-win-Setup.exe', 20), file('App-win-Portable.zip', 25)]
        self.feed = file('releases.win.json', 2)

    def publish(self, cnb):
        cnb.publish('v0.8.1', 'v0.8.1', 'notes', self.packages, self.installers, self.feed)

    def test_app_reads_cnb_feed_from_fixed_tag_not_latest(self):
        url = dict(FEEDS)['CNB']
        self.assertTrue(url.endswith(f'/-/releases/download/{CNB_FEED_TAG}'))
        self.assertNotIn('latest', url)

    def test_packages_and_feed_go_to_feed_release_installers_to_version_release(self):
        cnb = FakeCNB()
        self.publish(cnb)
        feed_id, version_id = f'new-{CNB_FEED_TAG}', 'new-v0.8.1'
        self.assertEqual(cnb.puts, [(feed_id, 'App-0.8.1-full.nupkg'), (feed_id, 'App-0.8.1-delta.nupkg'),
                                    (feed_id, 'releases.win.json'),
                                    (version_id, 'App-win-Setup.exe'), (version_id, 'App-win-Portable.zip')])
        patches = {url: payload for method, url, payload in cnb.calls if method == 'PATCH'}
        self.assertEqual((patches[f'/{feed_id}']['prerelease'], patches[f'/{feed_id}']['make_latest']), (True, 'false'))
        self.assertEqual((patches[f'/{version_id}']['draft'], patches[f'/{version_id}']['make_latest']), (False, 'true'))

    def test_rerun_skips_complete_uploads_but_always_replaces_the_feed(self):
        feed_release = {'id': 'feed', 'assets': [
            {'id': 1, 'name': 'App-0.8.1-full.nupkg', 'size': 30},
            {'id': 2, 'name': 'App-0.8.1-delta.nupkg', 'size': 3},    # interrupted, smaller than the file
            {'id': 3, 'name': 'releases.win.json', 'size': 2}]}
        cnb = FakeCNB({CNB_FEED_TAG: feed_release, 'v0.8.1': {'id': 'v', 'assets': []}})
        self.publish(cnb)
        self.assertEqual([name for release, name in cnb.puts if release == 'feed'],
                         ['App-0.8.1-delta.nupkg', 'releases.win.json'])

    def test_packages_the_new_feed_no_longer_lists_are_removed_after_it_is_up(self):
        feed_release = {'id': 'feed', 'assets': [{'id': 7, 'name': 'App-0.8.0-full.nupkg', 'size': 30},
                                                 {'id': 8, 'name': 'App-0.8.1-delta.nupkg', 'size': 5}]}
        cnb = FakeCNB({CNB_FEED_TAG: feed_release})
        self.publish(cnb)
        methods = [(method, url) for method, url, _ in cnb.calls]
        self.assertEqual([url for method, url in methods if method == 'DELETE'], ['/feed/assets/7'])
        self.assertLess(methods.index(('PATCH', '/feed')), methods.index(('DELETE', '/feed/assets/7')))

    def test_interrupted_upload_is_retried_then_reported(self):
        cnb = FakeCNB(put_errors=publish_update.UPLOAD_ATTEMPTS - 1)
        self.publish(cnb)
        self.assertEqual(cnb.puts[0][1], 'App-0.8.1-full.nupkg')
        with self.assertRaises(SystemExit):
            self.publish(FakeCNB(put_errors=publish_update.UPLOAD_ATTEMPTS))


class StageTests(unittest.TestCase):
    def test_stage_separates_feed_packages_from_installers(self):
        with tempfile.TemporaryDirectory() as directory:
            releases = Path(directory)
            assets = []
            for name, kind, version in (('App-0.8.0-full.nupkg', 'Full', '0.8.0'),
                                        ('App-0.8.1-full.nupkg', 'Full', '0.8.1'),
                                        ('App-0.8.1-delta.nupkg', 'Delta', '0.8.1')):
                (releases / name).write_bytes(name.encode())
                assets.append({'FileName': name, 'Type': kind, 'Version': version,
                               'SHA256': hashlib.sha256(name.encode()).hexdigest()})
            (releases / publish_update.FEED).write_text(json.dumps({'Assets': assets}), encoding='utf-8')
            for name in publish_update.INSTALLERS:
                (releases / name).write_bytes(b'installer')
            packages, installers, feed_path = publish_update.stage(releases, '0.8.1', keep_deltas=10)
            self.assertEqual([path.name for path in packages], ['App-0.8.1-full.nupkg', 'App-0.8.1-delta.nupkg'])
            # Published without the pack id (the author's name); the packages keep it for updates.
            self.assertEqual([path.name for path in installers],
                             ['HexCompanion-Windows-x64-Setup.exe', 'HexCompanion-Windows-x64.zip'])
            self.assertTrue(all(path.read_bytes() == b'installer' for path in installers))
            listed = json.loads(feed_path.read_text(encoding='utf-8'))['Assets']
            self.assertEqual([asset['FileName'] for asset in listed], [path.name for path in packages])


if __name__ == '__main__':
    unittest.main()
