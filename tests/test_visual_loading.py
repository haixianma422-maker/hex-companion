import io
import tempfile
import threading
import unittest
from pathlib import Path
from PIL import Image
from aram_demo.visual_assets import VisualAssetCache
from unittest.mock import patch

class VisualLoadingTests(unittest.TestCase):
    def test_splash_and_augment_can_use_validated_fallbacks_offline_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = VisualAssetCache(Path(folder))
            catalog = {'champions': {'101': {'splash': 'https://game.gtimg.cn/slow.jpg',
                       'splash_fallback': 'https://ddragon.leagueoflegends.com/fast.jpg'}},
                       'augments': {'1029': {'augment': 'https://game.gtimg.cn/large.png',
                       'augment_fallback': 'https://game.gtimg.cn/small.png'}}}
            cache._catalog = catalog
            buffer=io.BytesIO(); Image.new('RGB',(64,64)).save(buffer,'PNG')
            def download(url, *args):
                if 'slow' in url or 'large' in url: raise TimeoutError('slow CDN')
                return buffer.getvalue()
            with patch.object(cache, '_download', side_effect=download):
                report = cache.ensure([('splash',101),('augment',1029)])
            self.assertEqual(report['updated'],2)
            restarted=VisualAssetCache(Path(folder)); restarted._catalog=catalog
            with patch.object(restarted,'_download',side_effect=AssertionError('must stay offline')):
                self.assertIsNotNone(restarted.path('splash',101))
                self.assertIsNotNone(restarted.path('augment',1029))
                self.assertEqual(restarted.ensure([('splash',101),('augment',1029)])['updated'],0)

    def test_fast_image_is_published_while_another_download_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = VisualAssetCache(Path(folder))
            cache._catalog = {'champions': {'1': {'portrait': 'https://game.gtimg.cn/1.png'},
                                            '2': {'portrait': 'https://game.gtimg.cn/2.png'}}, 'augments': {}}
            buffer = io.BytesIO(); Image.new('RGB', (32,32)).save(buffer, 'PNG')
            fast_ready, slow_started, release = threading.Event(), threading.Event(), threading.Event()
            def download(url, kind, timeout):
                if url.endswith('/2.png'):
                    slow_started.set()
                    if not release.wait(3):
                        raise TimeoutError('test release timed out')
                return buffer.getvalue()
            cache._download = download
            errors, reports = [], []
            def run():
                try:
                    reports.append(cache.ensure([('portrait',1),('portrait',2)], on_progress=lambda: fast_ready.set()))
                except Exception as error:
                    errors.append(error)
            worker = threading.Thread(target=run)
            worker.start()
            try:
                self.assertTrue(slow_started.wait(1), str(errors))
                self.assertTrue(fast_ready.wait(1), str(errors))
                self.assertTrue(worker.is_alive())
                self.assertIsNotNone(cache.path('portrait',1))
            finally:
                release.set(); worker.join(4)
            self.assertEqual(errors, [])
            self.assertEqual(reports[0]['updated'], 2)

    def test_bad_image_is_throttled_without_blocking_other_images(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = VisualAssetCache(Path(folder))
            cache._catalog = {'champions': {'1': {'portrait': 'https://game.gtimg.cn/1.png'}}, 'augments': {}}
            calls = []
            cache._download = lambda *args: calls.append(args) or b'corrupt image'
            self.assertEqual(cache.ensure([('portrait',1)])['failed'], 1)
            self.assertEqual(cache.ensure([('portrait',1)])['failed'], 1)
            self.assertEqual(len(calls), 1)
            self.assertIsNone(cache.path('portrait',1))
