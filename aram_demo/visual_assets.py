"""Local champion/augment art lookup; invoke ensure only from a worker thread."""
import hashlib
import http.client
import io
import itertools
import json
import math
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image


_HOSTS = frozenset(('game.gtimg.cn', 'raw.communitydragon.org',
                    'ddragon.leagueoflegends.com'))
_KINDS = frozenset(('portrait', 'splash', 'augment'))
_MAX_BYTES = {'portrait': 1024 * 1024, 'splash': 6 * 1024 * 1024,
              'augment': 1024 * 1024}
_CATALOG_BYTES = 2 * 1024 * 1024


def _valid_url(url):
    if not isinstance(url, str) or not url.isascii() or '\\' in url:
        return False
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        return (parsed.scheme == 'https' and parsed.netloc in _HOSTS
                and parsed.path.lower().endswith(('.png', '.jpg', '.jpeg'))
                and '?' not in url and '#' not in url)
    except ValueError:
        return False


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _valid_url(newurl):
            raise ValueError('Untrusted visual asset redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class VisualAssetCache:
    """Read bundled metadata offline and cache requested public art atomically.

    root and seed_root are data directories, matching DataStore. No constructor,
    path, state, or champion_info call performs network access or writes files.
    """

    def __init__(self, root, seed_root=None, download_timeout=6):
        self.root = Path(root)
        self.seed_root = Path(seed_root) if seed_root is not None else None
        self._lock = threading.RLock()
        self._download_lock = threading.Lock()
        self._validated = {}
        self._failed = set()
        self._retry_after = {}
        self.download_timeout = max(1, min(20, float(download_timeout)))
        self._catalog = self._read_catalog()

    def _read_catalog(self):
        bundled = Path(__file__).resolve().parent.parent / 'data'
        for base in (self.root, self.seed_root, bundled):
            if base is None:
                continue
            try:
                with (base / 'visual_catalog.json').open('rb') as source:
                    raw = source.read(_CATALOG_BYTES + 1)
                if len(raw) > _CATALOG_BYTES:
                    continue
                value = json.loads(raw.decode('utf-8-sig'))
                if (isinstance(value, dict) and value.get('schema_version') == 1
                        and isinstance(value.get('champions'), dict)
                        and isinstance(value.get('augments'), dict)):
                    return value
            except (OSError, ValueError, UnicodeError):
                continue
        return {'champions': {}, 'augments': {}}

    @staticmethod
    def _key(kind, key):
        if kind not in _KINDS or isinstance(key, bool):
            return None
        try:
            # IDs are decimal integers; floats must not truncate into valid IDs.
            if not isinstance(key, (int, str)):
                return None
            number = int(key)
            return (kind, str(number)) if 0 < number < 1000000 else None
        except (TypeError, ValueError, OverflowError):
            return None

    def _url(self, identity):
        kind, key = identity
        group = 'augments' if kind == 'augment' else 'champions'
        entry = self._catalog[group].get(key, {})
        url = entry.get(kind) if isinstance(entry, dict) else None
        return url if _valid_url(url) else None

    @staticmethod
    def _relative(identity, url):
        kind, key = identity
        extension = '.png' if urllib.parse.urlsplit(url).path.lower().endswith('.png') else '.jpg'
        digest = hashlib.sha256(url.encode('ascii')).hexdigest()[:16]
        return Path('visual-assets') / kind / (key + '-' + digest + extension)

    @staticmethod
    def _validate(raw, kind):
        if len(raw) > _MAX_BYTES[kind]:
            raise ValueError('Visual asset is too large')
        with Image.open(io.BytesIO(raw)) as picture:
            limit = 4096 if kind == 'splash' else 2048
            if (picture.format not in ('PNG', 'JPEG')
                    or not (16 <= picture.width <= limit and 16 <= picture.height <= limit)
                    or picture.width * picture.height > 8000000):
                raise ValueError('Invalid visual asset format or dimensions')
            picture.verify()
        with Image.open(io.BytesIO(raw)) as picture:
            picture.load()

    def _cached_path(self, identity, url):
        kind, _key = identity
        relative = self._relative(identity, url)
        with self._lock:
            for base in (self.root, self.seed_root):
                if base is None:
                    continue
                candidate = base / relative
                try:
                    stat = candidate.stat()
                    signature = (stat.st_mtime_ns, stat.st_size)
                    if self._validated.get(candidate) != signature:
                        with candidate.open('rb') as source:
                            self._validate(source.read(_MAX_BYTES[kind] + 1), kind)
                        self._validated[candidate] = signature
                    return candidate
                except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
                    self._validated.pop(candidate, None)
            return None

    def path(self, kind, key):
        """Return validated art, retaining this champion's original cached portrait."""
        identity = self._key(kind, key)
        if identity is None:
            return None
        for url in self._urls(identity):
            cached = self._cached_path(identity, url)
            if cached is not None:
                return cached
        return None

    def _urls(self, identity):
        kind, key = identity
        group = 'augments' if kind == 'augment' else 'champions'
        entry = self._catalog[group].get(key, {})
        if not isinstance(entry, dict):
            return []
        return list(dict.fromkeys(url for url in (entry.get(kind), entry.get(kind + '_fallback'))
                                  if _valid_url(url)))

    def state(self, kind, key):
        """Return cached, missing, or failed without starting a download."""
        if self.path(kind, key) is not None:
            return 'cached'
        with self._lock:
            return 'failed' if self._key(kind, key) in self._failed else 'missing'

    def champion_info(self, cid):
        identity = self._key('portrait', cid)
        entry = self._catalog['champions'].get(identity[1], {}) if identity else {}
        if not isinstance(entry, dict):
            entry = {}
        return {field: str(entry.get(field, '')) for field in ('name', 'title')}

    def champion_skill_icons(self, cid):
        identity = self._key('portrait', cid)
        entry = self._catalog['champions'].get(identity[1], {}) if identity else {}
        icons = entry.get('skill_icons', {}) if isinstance(entry, dict) else {}
        return {key: url for key, url in icons.items() if key in ('Q', 'W', 'E') and _valid_url(url)} if isinstance(icons, dict) else {}

    def champion_focus(self, cid):
        """Return the normalized splash focal point; unspecified art uses the default."""
        identity = self._key('splash', cid)
        entry = self._catalog['champions'].get(identity[1], {}) if identity else {}
        focus = entry.get('focus') if isinstance(entry, dict) else None
        if (isinstance(focus, (list, tuple)) and len(focus) == 2
                and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                        and math.isfinite(value) and 0 <= value <= 1 for value in focus)):
            return tuple(float(value) for value in focus)
        return (.72, .42)

    def _download(self, url, kind, timeout):
        request = urllib.request.Request(url, headers={'User-Agent': 'HexCompanion/1.0'})
        opener = urllib.request.build_opener(_SafeRedirect())
        deadline = time.monotonic() + timeout
        with opener.open(request, timeout=timeout) as response:
            if not _valid_url(response.geturl()):
                raise ValueError('Untrusted visual asset response')
            chunks, total = [], 0
            while total <= _MAX_BYTES[kind]:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Visual asset download timed out')
                chunk = response.read1(min(64 * 1024, _MAX_BYTES[kind] + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            return b''.join(chunks)

    def ensure(self, requests, on_progress=None):
        """Fetch up to 64 unique entries on a worker; failures stay retryable.

        Counts cover accepted unique requests. A 20-second scheduling budget
        reports further entries as deferred. Network failures are throttled for
        60s. Each response has byte, redirect, and finite socket/time limits.
        """
        report = {'updated': 0, 'missing': 0, 'failed': 0, 'deferred': 0}
        with self._download_lock:
            deadline = time.monotonic() + 20
            seen, pending = set(), []
            for request in itertools.islice(requests, 64):
                try:
                    kind, key = request
                    identity = self._key(kind, key)
                except (TypeError, ValueError):
                    identity = None
                if identity is None:
                    report['missing'] += 1
                    continue
                if identity in seen:
                    continue
                seen.add(identity)
                url = self._url(identity)
                if url is None:
                    report['missing'] += 1
                    continue
                if self.path(kind, key) is not None:
                    continue
                if time.monotonic() >= deadline:
                    report['deferred'] += 1
                    continue
                with self._lock:
                    retry_after = self._retry_after.get(identity, 0)
                if time.monotonic() < retry_after:
                    report['failed'] += 1
                    continue
                pending.append((identity, url))
            # Four finite workers preserve request priority without letting one
            # slow image block every later image or the next UI refresh.
            with ThreadPoolExecutor(max_workers=4, thread_name_prefix='visual') as pool:
                futures = [pool.submit(self._ensure_one, identity, url, deadline)
                           for identity, url in pending]
                for future in as_completed(futures):
                    result = future.result()
                    report[result] += 1
                    if result == 'updated' and on_progress:
                        on_progress()
        return report

    def _ensure_one(self, identity, url, deadline):
        if time.monotonic() >= deadline:
            return 'deferred'
        kind, key = identity
        urls = self._urls(identity)
        image_deadline = min(deadline, time.monotonic() + self.download_timeout)
        for candidate in urls:
            temporary = None
            remaining = image_deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                raw = self._download(candidate, kind, min(self.download_timeout / len(urls), remaining))
                self._validate(raw, kind)
                target = self.root / self._relative(identity, candidate)
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False) as output:
                    temporary = Path(output.name)
                    output.write(raw)
                temporary.replace(target)
                with self._lock:
                    self._failed.discard(identity)
                    self._retry_after.pop(identity, None)
                return 'updated'
            except (OSError, ValueError, SyntaxError, http.client.HTTPException,
                    Image.DecompressionBombError):
                pass
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
        with self._lock:
            self._failed.add(identity)
            self._retry_after[identity] = time.monotonic() + 60
        return 'failed'
