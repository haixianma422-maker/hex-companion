import threading
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

from aram_demo import ocr
from aram_demo.ocr import TitleOcr, join_words, title_rows


class FakeWindows:
    def __init__(self, reads):
        self.reads, self.calls = list(reads), []

    def read(self, gray, height, margin):
        self.calls.append((height, margin))
        return self.reads.pop(0)


class FakeModel:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def read(self, crop, mask):
        self.calls += 1
        return self.text


def engines(windows=None, model=None):
    reader = TitleOcr()
    reader._started, reader._windows, reader._model = True, windows, model
    return reader


CROP, MASK = Image.new('RGB', (90, 30)), Image.new('L', (90, 30))


class TitleOcrTests(unittest.TestCase):
    def test_windows_passes_stop_at_the_first_read_naming_an_augment(self):
        windows, model = FakeWindows(['冫中', '冲锋', 'unused']), FakeModel('冲锋')
        text = engines(windows, model).read(CROP, MASK, lambda text: text == '冲锋')
        self.assertEqual(text, '冲锋')
        self.assertEqual(windows.calls, list(ocr.WINDOWS_PASSES[:2]))
        self.assertEqual(model.calls, 0)

    def test_model_rereads_when_no_windows_pass_matches(self):
        windows, model = FakeWindows(['质父', '质', '']), FakeModel('质变：混沌')
        self.assertEqual(engines(windows, model).read(CROP, MASK, lambda text: text == '质变：混沌'), '质变：混沌')
        self.assertEqual(len(windows.calls), len(ocr.WINDOWS_PASSES))

    def test_unmatched_reads_prefer_the_model_text_unless_it_is_empty(self):
        self.assertEqual(engines(FakeWindows(['a', 'b', 'c']), FakeModel('m')).read(CROP, MASK, lambda t: False), 'm')
        self.assertEqual(engines(FakeWindows(['a', 'b', 'c']), FakeModel('')).read(CROP, MASK, lambda t: False), 'a')

    def test_without_names_the_first_windows_read_is_final(self):
        windows, model = FakeWindows(['标题', 'x', 'y']), FakeModel('m')
        self.assertEqual(engines(windows, model).read(CROP, MASK), '标题')
        self.assertEqual((len(windows.calls), model.calls), (1, 0))

    def test_model_alone_serves_systems_without_the_chinese_ocr_component(self):
        self.assertEqual(engines(None, FakeModel('双刀流')).read(CROP, MASK, lambda t: True), '双刀流')

    def test_no_engine_names_the_windows_component_to_install(self):
        with self.assertRaises(RuntimeError) as error:
            engines().read(CROP, MASK)
        self.assertIn('光学字符识别', str(error.exception))

    def test_missing_engines_are_logged_not_raised_at_start(self):
        with patch.object(ocr, 'model_path', return_value=None), \
             patch.object(ocr, 'WindowsOcr', side_effect=RuntimeError(ocr.WINDOWS_MISSING)):
            reader = TitleOcr()
            with self.assertLogs(ocr.logger, 'WARNING'):
                reader._start()
        self.assertIsNone(reader._windows)
        self.assertIsNone(reader._model)


class HelperTests(unittest.TestCase):
    def test_spaces_stay_only_between_latin_words(self):
        self.assertEqual(join_words(['双', '刀', '流']), '双刀流')
        self.assertEqual(join_words(['ADAPt', 'Mode', '：', '开']), 'ADAPt Mode：开')

    def test_title_rows_split_lines_and_drop_background_specks(self):
        mask = Image.new('L', (200, 120))
        draw = ImageDraw.Draw(mask)
        draw.rectangle((10, 10, 150, 35), fill=255)    # first title line
        draw.rectangle((10, 50, 120, 75), fill=255)    # wrapped second line
        draw.rectangle((180, 100, 185, 102), fill=255)  # speck of the animated card
        self.assertEqual(title_rows(mask), [(5, 41), (45, 81)])


@unittest.skipUnless(ocr.model_path() and ocr.model_path().is_file(), 'recognition model not installed')
class RealEngineTests(unittest.TestCase):
    def test_both_engines_read_a_rendered_title(self):
        from aram_demo.recognition import Recognizer
        crop = Image.new('RGB', (450, 120), '#1d2a42')
        draw = ImageDraw.Draw(crop)
        draw.text((30, 25), '更万用的瞄准镜', font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 32), fill='white')
        draw.text((30, 80), '伤害', font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 18), fill='#c8aa6e')
        reader = TitleOcr()
        reader._start()   # the model before pywinrt, as the app does
        mask = Recognizer().title_mask(crop)
        self.assertEqual(reader._model.read(crop, mask), '更万用的瞄准镜')
        if reader._windows is None:
            return
        # Qt's GUI thread is a single-threaded apartment, where WinRT refuses blocking waits.
        result = {}
        def on_sta_thread():
            from winrt.runtime import STA, init_apartment
            init_apartment(STA)
            result['text'] = reader.read(crop, mask, lambda text: text.startswith('更万用的瞄准镜'))
        thread = threading.Thread(target=on_sta_thread)
        thread.start()
        thread.join()
        self.assertTrue(result.get('text', '').startswith('更万用的瞄准镜'), result)


if __name__ == '__main__':
    unittest.main()
