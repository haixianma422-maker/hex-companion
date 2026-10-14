import importlib.util
import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PIL import Image


GAREN = 'https://game.gtimg.cn/images/lol/act/img/spell/GarenE.png'
FLASH = 'https://game.gtimg.cn/images/lol/act/img/spell/Summoner_flash.png'
CDN = 'https://opgg-static.akamaized.net/meta/images/lol/16.20.1/spell/GarenE.png'


def png(color=(20, 80, 140), size=(64, 64)):
    output = io.BytesIO()
    Image.new('RGB', size, color).save(output, format='PNG')
    return output.getvalue()


class AdviceIconTests(unittest.TestCase):
    def test_offline_riot_spell_cache_is_shared_by_101_and_opgg_urls(self):
        official = 'https://ddragon.leagueoflegends.com/cdn/16.20.1/img/spell/GarenE.png'
        cache = self.cache()
        with patch.object(cache, '_download', return_value=png()):
            cache.ensure([official])
        restarted = self.cache()
        with patch.object(restarted, '_download', side_effect=AssertionError('Unexpected network')):
            self.assertIsNotNone(restarted.path(GAREN))
            self.assertEqual(restarted.path(GAREN), restarted.path(CDN))
            self.assertEqual(restarted.ensure([GAREN,CDN]), [])

    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('aram_demo.advice_icons'),
                             'Advice icon cache is not implemented')
        from aram_demo.advice_icons import AdviceIconCache
        self.cache_class = AdviceIconCache
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)

    def cache(self, root=None, seed=None):
        return self.cache_class(root or self.base / 'user', seed_root=seed)

    def test_download_persists_pixels_and_reuses_cache_after_restart(self):
        cache = self.cache()
        with patch.object(cache, '_download', return_value=png()):
            self.assertEqual(cache.ensure([GAREN, GAREN, FLASH]), [GAREN, FLASH])
        path = cache.path(GAREN)
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent.name, 'advice-icons')
        with Image.open(path) as image:
            self.assertEqual(image.getpixel((4, 4)), (20, 80, 140))
        restarted = self.cache()
        with patch.object(restarted, '_download', side_effect=AssertionError('Unexpected network')):
            self.assertEqual(restarted.path(GAREN), path)
            self.assertEqual(restarted.ensure([GAREN, FLASH]), [])

    def test_known_spell_aliases_share_cache_but_versions_and_unrelated_paths_remain_separate(self):
        urls = [GAREN, CDN, CDN.replace('16.20.1', '16.21.1')]
        cache = self.cache()
        with patch.object(cache, '_download', return_value=png()):
            self.assertEqual(cache.ensure(urls), [urls[0],urls[2]])
        self.assertEqual(cache.path(GAREN),cache.path(CDN))
        self.assertNotEqual(cache.path(CDN),cache.path(urls[2]))
        self.assertEqual(cache.urls('https://game.gtimg.cn/unrelated/GarenE.png'),
                         ['https://game.gtimg.cn/unrelated/GarenE.png'])

    def test_seed_cache_is_used_without_creating_writable_cache(self):
        seed = self.cache(self.base / 'seed')
        with patch.object(seed, '_download', return_value=png()):
            seed.ensure([GAREN])
        cache = self.cache(seed=self.base / 'seed')
        with patch.object(cache, '_download', side_effect=AssertionError('Unexpected network')):
            self.assertEqual(cache.path(GAREN), seed.path(GAREN))
            self.assertEqual(cache.ensure([GAREN]), [])
        self.assertFalse(cache.root.exists())

    def test_corrupt_user_image_falls_back_to_seed_and_corrupt_seed_is_repaired_locally(self):
        seed = self.cache(self.base / 'seed')
        with patch.object(seed, '_download', return_value=png()):
            seed.ensure([GAREN])
        cache = self.cache(seed=self.base / 'seed')
        user_path = cache.root / 'advice-icons' / seed.path(GAREN).name
        user_path.parent.mkdir(parents=True)
        user_path.write_bytes(b'corrupt')
        self.assertEqual(cache.path(GAREN), seed.path(GAREN))
        seed.path(GAREN).write_bytes(png()[:-12])
        self.assertIsNone(cache.path(GAREN))
        with patch.object(cache, '_download', return_value=png((50, 60, 70))):
            self.assertEqual(cache.ensure([GAREN]), [GAREN])
        self.assertEqual(cache.path(GAREN), user_path)
        with Image.open(user_path) as image:
            self.assertEqual(image.getpixel((0, 0)), (50, 60, 70))

    def test_invalid_urls_never_download_or_create_cache_directories(self):
        invalid = [None, 123, [], {}, '', '../x.png',
                   'http://game.gtimg.cn/x.png', 'https://evil.test/x.png',
                   'https://game.gtimg.cn.evil.test/x.png',
                   'https://user@game.gtimg.cn/x.png', 'https://game.gtimg.cn:443/x.png',
                   'https://game.gtimg.cn/x.png?q=1', 'https://game.gtimg.cn/x.png#part',
                   'https://game.gtimg.cn/x.jpg', ' https://game.gtimg.cn/x.png',
                   'https://game.gtimg.cn/x\n.png', 'https://game.gtimg.cn\\evil/x.png',
                   'https://game.gtimg.cn/\ud800.png']
        cache = self.cache()
        with patch.object(cache, '_download', side_effect=AssertionError('Unexpected network')):
            self.assertEqual(cache.ensure(invalid), [])
            for url in invalid:
                self.assertIsNone(cache.path(url))
        self.assertFalse(cache.root.exists())

    def test_bad_images_and_download_failures_are_throttled_then_retried(self):
        jpeg = io.BytesIO()
        Image.new('RGB', (64, 64)).save(jpeg, format='JPEG')
        for raw in [b'broken', png()[:-12], png(size=(7, 64)), png(size=(257, 64)),
                    jpeg.getvalue(), png() + bytes(256 * 1024)]:
            cache = self.cache()
            with patch('aram_demo.advice_icons.time.monotonic', return_value=100), \
                    patch.object(cache, '_download', return_value=raw):
                self.assertEqual(cache.ensure([GAREN]), [])
                self.assertIsNone(cache.path(GAREN))
            with patch('aram_demo.advice_icons.time.monotonic', return_value=159), \
                    patch.object(cache, '_download', side_effect=AssertionError('Retried too soon')):
                self.assertEqual(cache.ensure([GAREN]), [])
            with patch('aram_demo.advice_icons.time.monotonic', return_value=161), \
                    patch.object(cache, '_download', return_value=png()):
                self.assertEqual(cache.ensure([GAREN]), [GAREN])
            cache.path(GAREN).unlink()
        cache = self.cache()
        with patch.object(cache, '_download', side_effect=OSError('Offline')):
            self.assertEqual(cache.ensure([GAREN]), [])
        self.assertFalse(list(cache.root.rglob('*.tmp')))

    def test_concurrent_calls_leave_one_complete_valid_image(self):
        cache = self.cache()
        with patch.object(cache, '_download', return_value=png()):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: cache.ensure([GAREN]), range(8)))
        self.assertEqual(sum(len(result) for result in results), 1)
        self.assertIsNotNone(cache.path(GAREN))
        self.assertEqual(len(list(cache.root.rglob('*.*'))), 1)

    def test_network_response_rejects_untrusted_redirect_and_oversize_payload(self):
        class Response:
            def __init__(self, url, raw):
                self.url, self.raw = url, raw

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def geturl(self):
                return self.url

            def read(self, limit):
                return self.raw[:limit]

        cache = self.cache()
        for final_url, raw in [('https://evil.test/icon.png', png()),
                               (GAREN, png() + bytes(256 * 1024))]:
            with patch('urllib.request.urlopen', return_value=Response(final_url, raw)):
                self.assertEqual(cache.ensure([GAREN]), [])
                self.assertIsNone(cache.path(GAREN))
            cache.retry_after.clear()
        with patch('urllib.request.urlopen', return_value=Response(CDN, png())):
            self.assertEqual(cache.ensure([GAREN]), [GAREN])


if __name__ == '__main__':
    unittest.main()
