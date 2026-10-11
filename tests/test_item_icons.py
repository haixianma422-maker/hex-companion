import io
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image


class ItemIconTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('aram_demo.item_icons'), 'Item icon cache is not implemented')

    def cache(self, root, seed=None):
        from aram_demo.item_icons import ItemIconCache
        return ItemIconCache(Path(root), seed_root=seed, patch='16.20.1')

    def test_bundled_icon_works_offline_without_user_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            icon = base / 'seed/item-icons/16.20.1/3085.png'
            icon.parent.mkdir(parents=True)
            Image.new('RGB', (64, 64)).save(icon)
            cache = self.cache(base / 'user', base / 'seed')
            with patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network')):
                self.assertEqual(cache.path(3085), icon)
                cache.ensure([3085])

    def test_download_is_cached_and_invalid_images_are_not_saved(self):
        image = io.BytesIO()
        Image.new('RGB', (64, 64)).save(image, format='PNG')
        with tempfile.TemporaryDirectory() as folder:
            cache = self.cache(folder)
            with patch.object(cache, '_download', return_value=image.getvalue()) as download:
                cache.ensure([3085, 3085])
                cache.ensure([3085])
                self.assertEqual(download.call_count, 1)
                self.assertTrue(cache.path(3085).is_file())
            with patch.object(cache, '_download', return_value=b'not an image') as download:
                cache.ensure([9999])
                cache.ensure([9999])
                self.assertIsNone(cache.path(9999))
                self.assertEqual(download.call_count, 1, 'Failure must be throttled')

    def test_invalid_ids_never_reach_network_or_filesystem_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = self.cache(folder)
            with patch.object(cache, '_download') as download:
                cache.ensure(['../settings', 0, -1, None])
                self.assertIsNone(cache.path('../settings'))
                download.assert_not_called()
