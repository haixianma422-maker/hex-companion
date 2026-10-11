"""Small, persistent item-image cache. Network work belongs on a worker thread."""
import io
import json
import re
import time
import urllib.request
from pathlib import Path
from PIL import Image

ITEM_PATCH = json.loads((Path(__file__).resolve().parents[1] / 'data/item_catalog.json').read_text(encoding='utf-8'))['patch']


class ItemIconCache:
    def __init__(self, root, seed_root=None, patch=ITEM_PATCH):
        if not re.fullmatch(r'\d+\.\d+\.\d+', patch):
            raise ValueError('Invalid item icon patch')
        self.root, self.seed_root, self.patch = Path(root), Path(seed_root) if seed_root else None, patch
        self.retry_after = {}

    @staticmethod
    def valid_id(value):
        return isinstance(value, int) and not isinstance(value, bool) and 0 < value < 1000000

    def path(self, item_id):
        if not self.valid_id(item_id):
            return None
        relative = Path('item-icons') / self.patch / f'{item_id}.png'
        for base in (self.root, self.seed_root):
            if base is not None and (base / relative).is_file():
                return base / relative
        return None

    def _download(self, item_id):
        url = f'https://ddragon.leagueoflegends.com/cdn/{self.patch}/img/item/{item_id}.png'
        request = urllib.request.Request(url, headers={'User-Agent': 'HexCompanion/0.2'})
        with urllib.request.urlopen(request, timeout=4) as response:
            return response.read(256 * 1024)

    def ensure(self, item_ids):
        updated = []
        for item_id in dict.fromkeys(item_ids):
            if not self.valid_id(item_id) or self.path(item_id) or time.monotonic() < self.retry_after.get(item_id, 0):
                continue
            try:
                raw = self._download(item_id)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format != 'PNG' or not (8 <= image.width <= 256 and 8 <= image.height <= 256):
                        raise ValueError('Invalid item image')
                    image.verify()
                target = self.root / 'item-icons' / self.patch / f'{item_id}.png'
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix('.png.tmp')
                temporary.write_bytes(raw)
                temporary.replace(target)
                updated.append(item_id)
            except (OSError, ValueError):
                self.retry_after[item_id] = time.monotonic() + 60
        return updated
