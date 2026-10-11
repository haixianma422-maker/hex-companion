import threading
import unicodedata
import re
import json
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

DEFAULT_REGIONS = [(0.22, 0.34, 0.39, 0.44), (0.415, 0.34, 0.585, 0.44), (0.61, 0.34, 0.78, 0.44)]
# Complete display-tag family extracted from the versioned Chinese game resource.
# Keep resource metadata and definitions together; the audit script checks this snapshot.
TAG_DEFINITIONS = json.loads((Path(__file__).resolve().parents[1] / 'data' /
                              'augment_display_tags.json').read_text(encoding='utf-8'))['tags']
TITLE_CATEGORY_CHIPS = frozenset(value.strip() for value in TAG_DEFINITIONS.values())
CHIP_LINE = re.compile('(?:' + '|'.join(re.escape(tag) for tag in
                                     sorted(TITLE_CATEGORY_CHIPS, key=len, reverse=True)) + ')+')


@dataclass(frozen=True)
class Match:
    slot: int
    text: str
    augment_id: int | None = None
    candidates: list[int] = field(default_factory=list)
    status: str = 'unknown'


def normalize(text):
    # Observed in a real OCR run of 魔法飞弹: the model emits the Japanese
    # variant 弾. Normalize this single verified variant, keeping other typos
    # uncertain and duplicate normalized titles ambiguous.
    visible = ''.join(c for c in unicodedata.normalize('NFKC', text).replace('弾', '弹').casefold()
                      if unicodedata.category(c)[0] not in ('Z', 'C'))
    letters = ''.join(c for c in visible if unicodedata.category(c)[0] != 'P')
    # "？？？" is an actual augment title. Preserve punctuation-only input
    # without letting a blank crop turn into that title.
    return letters or visible


def title_query(text, known_names=()):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    query = normalize(''.join(lines))
    # Preserve title fragments (e.g. "哎哟，" / "我的硬币！"). Only remove
    # complete trailing chip lines, never substrings from an augment's name.
    # Stop at the longest complete known title, including title fragments
    # such as "速度" that also happen to be display-tag words.
    while len(lines) > 1 and query not in known_names and CHIP_LINE.fullmatch(normalize(lines[-1])):
        lines.pop()
        query = normalize(''.join(lines))
    return query


def match_slots(texts, augments):
    names = {}
    for augment in augments:
        names.setdefault(normalize(augment.name), []).append(augment.id)
    result = []
    for slot in range(3):
        text = texts[slot] if slot < len(texts) else ''
        # An exact complete title wins even if its final OCR fragment looks
        # like a category. Never strip a word from an already known title.
        query = title_query(text, names)
        exact = names.get(query, []) if query else []
        if len(exact) == 1:
            result.append(Match(slot, text, exact[0], exact, 'matched'))
        elif exact:
            result.append(Match(slot, text, None, exact, 'ambiguous'))
        else:
            ranked = sorted(((SequenceMatcher(None, query, name).ratio(), aid)
                             for name, ids in names.items() for aid in ids), reverse=True) if query else []
            choices = [aid for score, aid in ranked[:3] if score >= 0.72]
            result.append(Match(slot, text, None, choices, 'ambiguous' if choices else 'unknown'))
    return result


class Recognizer:
    def __init__(self, regions=None):
        self.regions = regions or DEFAULT_REGIONS
        if len(self.regions) != 3:
            raise ValueError('需要左、中、右三个区域')
        for region in self.regions:
            if len(region) != 4 or not all(isinstance(x, (float, int)) for x in region):
                raise ValueError('区域必须包含四个数字')
            x1, y1, x2, y2 = region
            if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                raise ValueError('区域坐标需在 0～1 内，且右下角大于左上角')
        self._engine = None
        self._lock = threading.Lock()
        self._screen_lock = threading.Lock()
        self._slot_cache = [None] * 3

    def read_image(self, image):
        import numpy as np
        from rapidocr import RapidOCR
        with self._lock:
            if self._engine is None:
                # These are small, horizontal game titles. The default detector
                # enlarges their short side to 736px, doing several seconds of
                # unnecessary work. Keep their native scale (cap large crops)
                # and bound inference threads so OCR can coexist with the game.
                self._engine = RapidOCR(params={
                    'Det.limit_type': 'max', 'Det.limit_side_len': 736,
                    'Global.use_cls': False,
                    'EngineConfig.onnxruntime.intra_op_num_threads': 2,
                    'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                })
            output = self._engine(np.array(image.convert('RGB')))
            return '\n'.join(output.txts or [])

    def title_mask(self, crop):
        from PIL import ImageChops
        red, green, blue = crop.convert('RGB').split()
        low = ImageChops.darker(ImageChops.darker(red, green), blue)
        high = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        # Cream/white title strokes; ignore the animated dark card background.
        bright = low.point(lambda value: 255 if value > 145 else 0)
        neutral = ImageChops.subtract(high, low).point(lambda value: 255 if value < 90 else 0)
        return ImageChops.multiply(bright, neutral)

    def selection_visible(self, crops):
        from PIL import ImageChops
        likely = 0
        for crop in crops:
            sample = crop.resize((96, 48)).convert('RGB')
            red, green, blue = sample.split()
            high = ImageChops.lighter(ImageChops.lighter(red, green), blue)
            dark = sum(high.histogram()[:75]) / (96 * 48)
            ink = self.title_mask(sample).histogram()[255] / (96 * 48)
            likely += dark >= .65 and .003 <= ink <= .25
        # Two aligned dark cards with bright titles are stronger evidence than
        # isolated HUD text. Uses calibrated title regions at any resolution.
        return likely >= 2

    def read_screen(self, image, augments, force=False, automatic=False):
        from PIL import ImageChops
        width, height = image.size
        texts = []
        crops = [image.crop((round(x1 * width), round(y1 * height), round(x2 * width), round(y2 * height))).convert('RGB')
                 for x1, y1, x2, y2 in self.regions]
        with self._screen_lock:
            if automatic and not force and not self.selection_visible(crops):
                self._slot_cache = [None] * 3
                return None  # Cheap gate: do not import or initialize OCR.
            known = {normalize(a.name) for a in augments}
            now = time.monotonic()
            for slot, crop in enumerate(crops):
                pixels = (crop.size, crop.tobytes())
                cached = self._slot_cache[slot]
                mask = None
                same = cached is not None and cached[0] == pixels
                confirmed = cached is not None and title_query(cached[1], known) in known
                if confirmed and crop.size == cached[2].size and not same:
                    mask = self.title_mask(crop)
                    union = ImageChops.lighter(mask, cached[2]).histogram()[255]
                    changed = ImageChops.difference(mask, cached[2]).histogram()[255]
                    same = union >= 20 and changed / union <= .015
                # A transient miss must not require a hover/pixel change to
                # recover. Retry that slot soon while keeping good slots warm.
                cache_seconds = 10 if confirmed else .75
                if not force and cached is not None and now - cached[3] < cache_seconds and same:
                    text = cached[1]
                else:
                    text = self.read_image(crop)
                    if mask is None:
                        mask = self.title_mask(crop)
                    self._slot_cache[slot] = (pixels, text, mask, now)
                texts.append(text)
        # Cache text only: champion data may have changed since the last frame.
        return match_slots(texts, augments)

    def capture_and_read(self, augments):
        from PIL import ImageGrab
        return self.read_screen(ImageGrab.grab(), augments)
