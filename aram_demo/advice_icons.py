"""Persistent ability and summoner PNG cache; call ensure on a worker thread."""
import hashlib
import io
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import re
from pathlib import Path

from PIL import Image
from .item_icons import ITEM_PATCH


_HOSTS = frozenset(('game.gtimg.cn', 'opgg-static.akamaized.net',
                    'ddragon.leagueoflegends.com'))
_MAX_BYTES = 256 * 1024


class AdviceIconCache:
    def __init__(self, root, seed_root=None):
        self.root = Path(root)
        self.seed_root = Path(seed_root) if seed_root is not None else None
        self.retry_after = {}
        self._lock = threading.Lock()

    @staticmethod
    def valid_url(url):
        if not isinstance(url, str) or not url or not url.isascii() or '\\' in url:
            return False
        if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in url):
            return False
        try:
            parsed = urllib.parse.urlsplit(url)
            return (parsed.scheme == 'https' and parsed.netloc in _HOSTS
                    and parsed.path.endswith('.png')
                    and '?' not in url and '#' not in url)
        except ValueError:
            return False

    @staticmethod
    def _validate(raw):
        if len(raw) > _MAX_BYTES:
            raise ValueError('Advice image is too large')
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != 'PNG' or not (8 <= image.width <= 256 and 8 <= image.height <= 256):
                raise ValueError('Invalid advice image')
            image.verify()
        # verify checks container integrity; load also checks compressed pixel data.
        with Image.open(io.BytesIO(raw)) as image:
            image.load()

    @staticmethod
    def _relative(url):
        return Path('advice-icons') / (hashlib.sha256(url.encode('utf-8')).hexdigest() + '.png')

    @classmethod
    def urls(cls, url):
        """Share the same versioned Riot spell asset across trusted source URLs."""
        if not cls.valid_url(url):
            return []
        parsed = urllib.parse.urlsplit(url)
        match = re.fullmatch(r'/meta/images/lol/(\d+\.\d+\.\d+)/spell/([A-Za-z0-9_]+\.png)', parsed.path)
        if parsed.netloc == 'opgg-static.akamaized.net' and match:
            patch, filename = match.groups()
        elif parsed.netloc == 'game.gtimg.cn' and re.fullmatch(r'/images/lol/act/img/spell/[A-Za-z0-9_]+\.png', parsed.path):
            patch, filename = ITEM_PATCH, parsed.path.rsplit('/', 1)[-1]
        else:
            return [url]
        official = f'https://ddragon.leagueoflegends.com/cdn/{patch}/img/spell/{filename}'
        return list(dict.fromkeys((official, url)))

    def path(self, url):
        """Return a validated writable-cache or seed image, otherwise None."""
        urls = self.urls(url)
        if not urls:
            return None
        for base in (self.root, self.seed_root):
            if base is None:
                continue
            for candidate_url in dict.fromkeys((url, *urls)):
                candidate = base / self._relative(candidate_url)
                try:
                    with candidate.open('rb') as source:
                        self._validate(source.read(_MAX_BYTES + 1))
                    return candidate
                except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
                    continue
        return None

    def _download(self, url):
        request = urllib.request.Request(url, headers={'User-Agent': 'HexCompanion/0.2'})
        with urllib.request.urlopen(request, timeout=4) as response:
            if not self.valid_url(response.geturl()):
                raise ValueError('Untrusted advice image redirect')
            return response.read(_MAX_BYTES + 1)

    def ensure(self, urls, on_progress=None):
        """Download missing valid URLs and return those successfully saved."""
        updated = []
        with self._lock:
            seen = set()
            for url in urls:
                if not self.valid_url(url) or url in seen:
                    continue
                seen.add(url)
                if self.path(url) or time.monotonic() < self.retry_after.get(url, 0):
                    continue
                temporary = None
                try:
                    saved_url = None
                    for candidate_url in self.urls(url):
                        try:
                            raw = self._download(candidate_url)
                            self._validate(raw)
                            saved_url = candidate_url
                            break
                        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
                            continue
                    if saved_url is None:
                        self.retry_after[url] = time.monotonic() + 60
                        continue
                    target = self.root / self._relative(saved_url)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False) as output:
                        temporary = Path(output.name)
                        output.write(raw)
                    temporary.replace(target)
                    self.retry_after.pop(url, None)
                    updated.append(url)
                    if on_progress:
                        on_progress()
                except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
                    self.retry_after[url] = time.monotonic() + 60
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
        return updated
