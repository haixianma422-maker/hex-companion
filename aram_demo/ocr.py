"""Two OCR engines for augment titles.

Windows' own OCR reads first: a few milliseconds and nothing to ship. It sometimes drops a
character or splits one into its radicals, so the PP-OCRv6 recognition model rereads titles
Windows could not match. The game draws titles on fixed regions in one cream colour, so the
title lines are cut by a row projection of the title mask; no text detector is needed.
"""
import importlib.util
import logging
import math
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODEL_NAME = 'PP-OCRv6_rec_small.onnx'
# Each pass scales the crop to a height and adds a white margin, as dark text on light. Windows
# OCR misreads differently at each scale, so the next pass runs only while no title matched.
WINDOWS_PASSES = ((144, 64), (216, 0), (288, 64))
MODEL_HEIGHT, MODEL_MIN_WIDTH = 48, 320   # RapidOCR's rec_img_shape for this model
WINDOWS_MISSING = '未找到 Windows 简体中文文字识别组件'
NO_ENGINE = ('没有可用的文字识别：请在“设置 → 时间和语言 → 语言和区域”添加“中文(简体)”，'
             '并在其语言选项中安装“光学字符识别”，然后重启海克斯随行。')

logger = logging.getLogger(__name__)


def join_words(words):
    """Windows OCR returns each Chinese character as a word; keep spaces only between Latin words."""
    text = ''
    for word in words:
        if text and text[-1].isascii() and text[-1].isalnum() and word[:1].isascii() and word[:1].isalnum():
            text += ' '
        text += word
    return text


def _multithreaded_apartment():
    from winrt.runtime import MTA, init_apartment
    init_apartment(MTA)


class WindowsOcr:
    """WinRT refuses blocking waits on single-threaded apartments such as Qt's GUI thread, so every
    call runs on one thread of this engine in the multithreaded apartment."""

    def __init__(self):
        self._thread = ThreadPoolExecutor(1, 'windows-ocr', initializer=_multithreaded_apartment)
        try:
            self.engine, self.max_side = self._thread.submit(self._create).result()
        except BaseException:
            self._thread.shutdown(wait=False)
            raise

    @staticmethod
    def _create():
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
        tag = next((language.language_tag for language in OcrEngine.available_recognizer_languages
                    if language.language_tag.lower().startswith(('zh-hans', 'zh-cn'))), None)
        engine = tag and OcrEngine.try_create_from_language(Language(tag))
        if not engine:
            raise RuntimeError(WINDOWS_MISSING)
        return engine, OcrEngine.max_image_dimension

    def read(self, gray, height, margin):
        """gray: dark text on light. Returns the lines joined by newlines."""
        from PIL import Image, ImageOps
        scale = min(height / gray.height, (self.max_side - 2 * margin) / max(gray.size))
        gray = gray.resize((max(1, round(gray.width * scale)), max(1, round(gray.height * scale))), Image.LANCZOS)
        pixels = ImageOps.expand(gray, margin, fill=255).convert('RGBA')
        return self._thread.submit(self._recognize, pixels.tobytes(), pixels.size).result()

    def _recognize(self, rgba, size):
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        bitmap = SoftwareBitmap.create_copy_from_buffer(rgba, BitmapPixelFormat.RGBA8, *size)
        result = self.engine.recognize_async(bitmap).get()
        return '\n'.join(join_words([word.text for word in line.words]) for line in result.lines)


def model_path():
    """Bundled beside the app when frozen; from the installed rapidocr package in a source checkout."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'models' / MODEL_NAME
    spec = importlib.util.find_spec('rapidocr')   # locates the package without importing OpenCV
    return Path(spec.submodule_search_locations[0]) / 'models' / MODEL_NAME if spec else None


def title_rows(mask, gap=3, pad=5):
    """(top, bottom) of each title line: rows holding title pixels, short gaps bridged."""
    width, height = mask.size
    data = mask.tobytes()
    inked = [data[row * width:(row + 1) * width].count(255) >= 2 for row in range(height)]
    spans = []
    for row, ink in enumerate(inked):
        if not ink:
            continue
        if spans and row - spans[-1][1] <= gap:
            spans[-1][1] = row + 1
        else:
            spans.append([row, row + 1])
    tallest = max((bottom - top for top, bottom in spans), default=0)
    # Specks of the animated card background are far thinner than a line of title text.
    return [(max(0, top - pad), min(height, bottom + pad)) for top, bottom in spans if bottom - top >= tallest * .4]


class ModelOcr:
    """The PP-OCRv6 recognition model on onnxruntime, without RapidOCR and OpenCV."""

    def __init__(self, path):
        import onnxruntime
        options = onnxruntime.SessionOptions()
        # Bounded threads so the reread can coexist with the game.
        options.intra_op_num_threads, options.inter_op_num_threads = 2, 1
        self.session = onnxruntime.InferenceSession(str(path), options, providers=['CPUExecutionProvider'])
        metadata = self.session.get_modelmeta().custom_metadata_map
        self.characters = ['blank', *metadata['character'].splitlines(), ' ']
        self.input = self.session.get_inputs()[0].name

    def read(self, crop, mask):
        lines = []
        for top, bottom in title_rows(mask):
            box = mask.crop((0, top, mask.width, bottom)).getbbox()
            if box:
                left, right = max(0, box[0] - 6), min(crop.width, box[2] + 6)
                lines.append(self.read_line(crop.crop((left, top, right, bottom))))
        return '\n'.join(line for line in lines if line)

    def read_line(self, line):
        import numpy as np
        from PIL import Image
        width = max(1, math.ceil(MODEL_HEIGHT * line.width / line.height))
        pixels = np.asarray(line.convert('RGB').resize((width, MODEL_HEIGHT), Image.BILINEAR), dtype=np.float32)
        tensor = np.zeros((1, 3, MODEL_HEIGHT, max(width, MODEL_MIN_WIDTH)), dtype=np.float32)
        tensor[0, :, :, :width] = (pixels[:, :, ::-1].transpose(2, 0, 1) / 255 - .5) / .5   # BGR, as RapidOCR feeds it
        best = self.session.run(None, {self.input: tensor})[0][0].argmax(axis=1)
        text, previous = [], 0
        for index in best:
            if index and index != previous:
                text.append(self.characters[index])
            previous = index
        return ''.join(text)


class TitleOcr:
    """Windows OCR first, the recognition model for titles it could not match. Either engine
    may be missing (no Chinese OCR component, a source checkout without the model)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._windows = self._model = None
        self._started = False

    def _start(self):
        self._started = True
        # The model first: pywinrt ships an older msvcp140.dll (14.29), and onnxruntime crashes
        # when it loads after that one. In the app Qt has already loaded a newer copy.
        path = model_path()
        if path and path.is_file():
            try:
                self._model = ModelOcr(path)
            except Exception:
                logger.exception('recognition model unavailable')
        else:
            logger.warning('recognition model not found: %s', path)
        try:
            self._windows = WindowsOcr()
        except Exception as exc:
            logger.warning('Windows OCR unavailable: %s', exc)

    def read(self, crop, mask, matches=None):
        """crop: RGB title region; mask: its title pixels. matches(text) tells a read that names an
        augment; without it the first Windows read is final."""
        from PIL import ImageOps
        with self._lock:
            if not self._started:
                self._start()
            if self._windows is None and self._model is None:
                raise RuntimeError(NO_ENGINE)
            first = None
            if self._windows is not None:
                gray = ImageOps.invert(ImageOps.autocontrast(crop.convert('L')))
                for height, margin in WINDOWS_PASSES:
                    text = self._windows.read(gray, height, margin)
                    first = text if first is None else first
                    if matches is None or matches(text):
                        return text
            if self._model is None:
                return first
            text = self._model.read(crop, mask)
            # Neither matched: the model's read is the likelier one to come close.
            return text or first or ''
