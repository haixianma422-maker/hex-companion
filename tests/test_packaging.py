import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aram_demo.cache import DataStore


class PackagingTests(unittest.TestCase):
    def test_normal_executable_launch_requests_admin_before_starting_services(self):
        import app
        def launch_admin(*args):
            self.assertEqual(app.os.environ.get('PYINSTALLER_RESET_ENVIRONMENT'), '1')
            return 42
        with patch.object(app.sys, 'frozen', True, create=True), \
             patch.object(app.sys, 'argv', ['HexCompanion.exe']), \
             patch.dict(app.os.environ, {'PYINSTALLER_RESET_ENVIRONMENT': '0'}), \
             patch.object(app.ctypes.windll.shell32, 'IsUserAnAdmin', return_value=0), \
             patch.object(app.ctypes.windll.shell32, 'ShellExecuteW', side_effect=launch_admin) as launch, \
             patch.object(app, 'single_instance', side_effect=AssertionError('Unelevated services started')):
            app.main()
        self.assertEqual(launch.call_args.args[1:3], ('runas', app.sys.executable))

    def test_bundled_snapshot_is_fallback_and_settings_remain_private(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            seed, user = base / 'bundle', base / 'user'
            seed.mkdir()
            (seed / 'champions.json').write_text('{"champions": []}', encoding='utf-8')
            (seed / 'settings.json').write_text('{"install_path": "another PC"}', encoding='utf-8')
            store = DataStore(user, seed_root=seed)
            self.assertEqual(store.read('champions.json'), {'champions': []})
            self.assertIsNone(store.read('settings.json'))
            store._write('champions.json', {'champions': [1]})
            self.assertEqual(store.read('champions.json'), {'champions': [1]})
            self.assertEqual(json.loads((seed / 'champions.json').read_text()), {'champions': []})

    def test_broken_user_snapshot_falls_back_to_bundled_data(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            seed, user = base / 'bundle', base / 'user'
            seed.mkdir()
            user.mkdir()
            (seed / 'champions.json').write_text('{"champions": []}', encoding='utf-8')
            (user / 'champions.json').write_text('incomplete download', encoding='utf-8')
            store = DataStore(user, seed_root=seed)
            self.assertEqual(store.read('champions.json'), {'champions': []})
            self.assertIn('champions.json', store.last_error)


if __name__ == '__main__':
    unittest.main()
