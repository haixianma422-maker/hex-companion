import importlib
import unittest
import json
from unittest.mock import patch
from itertools import product
from pathlib import Path
from aram_demo.models import Augment


class RecognitionTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('aram_demo.recognition')
        except ImportError:
            self.fail('Missing implementation: recognition')

    def test_blank_middle_keeps_left_and_right_in_place(self):
        rows = self.module().match_slots(['暴击飞弹', '', '双刀流'], [
            Augment(1356, '暴击飞弹', 0, 4), Augment(20, '双刀流', 1, 2)])
        self.assertEqual([r.slot for r in rows], [0, 1, 2])
        self.assertEqual([r.augment_id for r in rows], [1356, None, 20])

    def test_chinese_spaces_and_punctuation_are_normalized(self):
        rows = self.module().match_slots(['升级 : 无尽之刃', '', ''], [Augment(3, '升级：无尽之刃', 1, 2)])
        self.assertEqual(rows[0].augment_id, 3)

    def test_magic_missile_ocr_variant_matches_without_accepting_other_typos(self):
        rows = self.module().match_slots(['魔法飞弾\n伤害', '魔法飞蛋', ''], [
            Augment(1133, '魔法飞弹', 1, 4)])
        self.assertEqual(rows[0].augment_id, 1133)
        self.assertEqual(rows[0].status, 'matched')
        self.assertIsNone(rows[1].augment_id)
        duplicate = self.module().match_slots(['魔法飞弾', '', ''], [
            Augment(1133, '魔法飞弹', 1, 4), Augment(2, '魔法飞弾', 2, 4)])
        self.assertIsNone(duplicate[0].augment_id)
        self.assertEqual(duplicate[0].status, 'ambiguous')

    def test_ambiguous_names_do_not_become_certain_ratings(self):
        rows = self.module().match_slots(['魔法飞弹', '不存在的海克斯', ''], [
            Augment(1, '魔法飞弹', 1, 1), Augment(2, '魔法 飞弹', 2, 2)])
        self.assertIsNone(rows[0].augment_id)
        self.assertEqual(rows[0].status, 'ambiguous')
        self.assertIsNone(rows[1].augment_id)

    def test_out_of_bounds_and_reversed_regions_are_rejected(self):
        cls = self.module().Recognizer
        with self.assertRaises(ValueError):
            cls([(0, 0, 1.1, 0.5)] * 3)
        with self.assertRaises(ValueError):
            cls([(0.8, 0.4, 0.2, 0.6)] * 3)

    def test_real_capture_title_fragments_and_category_chips_match_without_fuzzy_guess(self):
        rows = self.module().match_slots(['哎哟，\n我的硬币！\n经济', '循环往复\n速度', '缩小引擎\n功能\n速度'], [
            Augment(2089, '哎哟，我的硬币！', 3, 4), Augment(1068, '循环往复', 0, 4),
            Augment(1373, '缩小引擎', 0, 4)])
        self.assertEqual([r.augment_id for r in rows], [2089, 1068, 1373])
        self.assertTrue(all(r.status == 'matched' for r in rows))

    def test_split_long_title_does_not_match_shorter_title_within_it(self):
        rows = self.module().match_slots(['无限\n循环往复\n速度'], [
            Augment(1068, '循环往复', 0, 4), Augment(1388, '无限循环往复', 1, 8)])
        self.assertEqual(rows[0].augment_id, 1388)

    def test_description_or_two_titles_are_not_treated_as_one_certain_title(self):
        rows = self.module().match_slots(['获得循环往复效果\n速度', '循环往复\n缩小引擎\n速度'], [
            Augment(1068, '循环往复', 0, 4), Augment(1373, '缩小引擎', 0, 4)])
        self.assertEqual([r.augment_id for r in rows], [None, None, None])

    def test_leblanc_capture_damage_and_quest_chips_are_not_part_of_titles(self):
        augments = [Augment(1084, '穿针引线', 1, 4), Augment(1098, '急急小子', 2, 4),
                    Augment(2116, '威能之追求', 1, 4)]
        for suffix in ('伤害\n任务', '伤害 任务', '伤害任务'):
            with self.subTest(suffix=suffix):
                rows = self.module().match_slots(['穿针引线\n伤害', '急急小子\n速度', '威能之追求\n'+suffix], augments)
                self.assertEqual([row.augment_id for row in rows], [1084, 1098, 2116])
                self.assertTrue(all(row.status == 'matched' for row in rows))

    def test_complete_known_title_takes_precedence_over_category_removal(self):
        rows = self.module().match_slots(['穿针引线\n伤害'], [
            Augment(1084, '穿针引线', 1, 4), Augment(9001, '穿针引线伤害', 2, 4)])
        self.assertEqual(rows[0].augment_id, 9001)

    def test_category_words_with_description_text_are_not_silently_removed(self):
        rows = self.module().match_slots(['穿针引线\n伤害提升', '威能之追求\n完成任务'], [
            Augment(1084, '穿针引线', 1, 4), Augment(2116, '威能之追求', 1, 4)])
        self.assertTrue(all(row.augment_id is None for row in rows))

    def test_all_resource_display_tags_and_pairs_are_removed(self):
        # Full cherry_augmentdisplaytag_ family in the 16.20 zh_CN resource.
        tags = ('伤害', '功能', '速度', '经济', '复原力', '综合', '任务',
                '任务线', '己方', '经典模式版', '属性锻造器')
        augments = [Augment(1053, '科学狂人', 1, 8)]
        self.assertEqual(self.module().TITLE_CATEGORY_CHIPS, frozenset(tags))
        for first, second in product(tags, repeat=2):
            for separator in ('\n', ' ', ''):
                with self.subTest(first=first, second=second, separator=separator):
                    row = self.module().match_slots(['科学狂人\n' + first + separator + second], augments)[0]
                    self.assertEqual(row.augment_id, 1053)

    def test_tag_like_title_fragment_survives_when_another_tag_follows_it(self):
        rows = self.module().match_slots(['追求\n速度\n经济'], [
            Augment(10, '追求', 1, 4), Augment(11, '追求速度', 2, 4)])
        self.assertEqual(rows[0].augment_id, 11)

    def test_latest_cropped_capture_titles_match_all_three_slots(self):
        rows = self.module().match_slots(['科学狂人\n综合', '质变：\n混沌\n功能', '尊我为王\n功能'], [
            Augment(1053, '科学狂人', None, 8), Augment(1243, '质变：混沌', None, 8),
            Augment(1337, '尊我为王', None, 8)])
        self.assertEqual([row.augment_id for row in rows], [1053, 1243, 1337])

    def test_unverified_label_remains_unknown_instead_of_guessing_from_prefix(self):
        row = self.module().match_slots(['科学狂人\n未来分类'], [Augment(1053, '科学狂人', 1, 8)])[0]
        self.assertIsNone(row.augment_id)

    def test_punctuation_only_augment_is_distinct_from_blank(self):
        rows = self.module().match_slots(['？？？\n综合', '', '???'], [Augment(1424, '？？？', 5, 8)])
        self.assertEqual([row.augment_id for row in rows], [1424, None, 1424])

    def test_every_cached_title_matches_with_each_resource_tag(self):
        root = Path(__file__).resolve().parents[1]
        rows = {}
        for path in (root / 'data/heroes').glob('*.json'):
            for row in json.loads(path.read_text(encoding='utf-8'))['augments']:
                rows[(row['id'], row['name'])] = Augment(**row)
        self.assertGreater(len(rows), 150)
        catalog = list(rows.values())
        for augment in rows.values():
            for tag in ('伤害', '功能', '速度', '经济', '复原力', '综合', '任务',
                        '任务线', '己方', '经典模式版', '属性锻造器'):
                with self.subTest(augment=augment.name, tag=tag):
                    match = self.module().match_slots([augment.name + '\n' + tag], catalog)[0]
                    self.assertEqual(match.augment_id, augment.id)

    def test_identical_title_pixels_skip_ocr_and_single_reroll_reads_only_changed_slot(self):
        from PIL import Image, ImageDraw
        recognizer = self.module().Recognizer([(0, 0, 1/3, 1), (1/3, 0, 2/3, 1), (2/3, 0, 1, 1)])
        augments = [Augment(i, name, 0, 4) for i, name in enumerate(('左侧旧', '中间', '右侧', '左侧新'), 1)]
        image = Image.new('RGB', (90, 30), 'black')
        with patch.object(recognizer, 'read_image', side_effect=['左侧旧', '中间', '右侧', '左侧新']) as ocr:
            first = recognizer.read_screen(image, augments)
            repeated = recognizer.read_screen(image.copy(), augments)
            self.assertEqual(ocr.call_count, 3)
            self.assertEqual(first, repeated)
            changed = image.copy()
            ImageDraw.Draw(changed).rectangle((0, 0, 29, 29), fill='white')
            rerolled = recognizer.read_screen(changed, augments)
            self.assertEqual(ocr.call_count, 4)
            self.assertEqual([row.augment_id for row in rerolled], [4, 2, 3])

    def test_force_scan_bypasses_pixel_cache_and_cached_text_rematches_new_hero_data(self):
        from PIL import Image
        recognizer = self.module().Recognizer()
        image = Image.new('RGB', (90, 30), 'black')
        with patch.object(recognizer, 'read_image', return_value='同名海克斯') as ocr:
            recognizer.read_screen(image, [Augment(1, '同名海克斯', 0, 4)])
            updated = recognizer.read_screen(image, [Augment(2, '同名海克斯', 1, 4)])
            self.assertEqual([row.augment_id for row in updated], [2, 2, 2])
            self.assertEqual(ocr.call_count, 3)
            recognizer.read_screen(image, [Augment(2, '同名海克斯', 1, 4)], force=True)
            self.assertEqual(ocr.call_count, 6)

    def test_automatic_scan_rejects_non_card_frames_without_loading_ocr(self):
        from PIL import Image, ImageDraw
        recognizer = self.module().Recognizer()
        frame = Image.new('RGB', (600, 360), '#283c56')
        ImageDraw.Draw(frame).text((300, 145), 'HUD text', fill='white')
        with patch.object(recognizer, 'read_image', return_value='海克斯') as ocr:
            self.assertIsNone(recognizer.read_screen(frame, [], automatic=True))
            ocr.assert_not_called()
            recognizer.read_screen(frame, [], automatic=True, force=True)
            self.assertEqual(ocr.call_count, 3, 'F6 must bypass the visual gate')

    def test_background_brightness_noise_reuses_title_but_changed_letters_do_not(self):
        from PIL import Image, ImageDraw, ImageChops
        regions = [(0, 0, 1/3, 1), (1/3, 0, 2/3, 1), (2/3, 0, 1, 1)]
        recognizer = self.module().Recognizer(regions)
        image = Image.new('RGB', (300, 80), '#08151c')
        draw = ImageDraw.Draw(image)
        for offset in (0, 100, 200):
            draw.text((offset + 25, 30), 'TITLE', fill='#e8e0c8')
        augments = [Augment(1, '旧标题', 0, 4), Augment(2, '新标题', 1, 4)]
        with patch.object(recognizer, 'read_image', return_value='旧标题') as ocr:
            recognizer.read_screen(image, augments)
            noisy = ImageChops.add(image, Image.new('RGB', image.size, (3, 3, 3)))
            recognizer.read_screen(noisy, augments)
            self.assertEqual(ocr.call_count, 3)
            changed = noisy.copy()
            ImageDraw.Draw(changed).rectangle((25, 30, 60, 39), fill='#08151c')
            ImageDraw.Draw(changed).text((25, 30), 'OTHER', fill='#e8e0c8')
            ocr.return_value = '新标题'
            rows = recognizer.read_screen(changed, augments)
            self.assertEqual(ocr.call_count, 4)
            self.assertEqual([row.augment_id for row in rows], [2, 1, 1])

    def test_title_cache_expires_without_extending_on_each_hit(self):
        from PIL import Image
        recognizer = self.module().Recognizer()
        frame = Image.new('RGB', (90, 30), 'black')
        with patch.object(recognizer, 'read_image', return_value='标题') as ocr, \
             patch('aram_demo.recognition.time.monotonic', side_effect=[20, 29, 30.1]):
            for _ in range(3):
                recognizer.read_screen(frame, [Augment(1, '标题', 0, 4)])
            self.assertEqual(ocr.call_count, 6)

    def test_unread_right_title_retries_without_hover_while_known_slots_stay_cached(self):
        from PIL import Image
        recognizer = self.module().Recognizer()
        frame = Image.new('RGB', (600, 360), 'black')
        augments = [Augment(1, '左侧', 0, 4), Augment(2, '中间', 1, 4), Augment(3, '魔法飞弹', 1, 4)]
        with patch.object(recognizer, 'read_image', side_effect=['左侧', '中间', '', '魔法飞弹']) as ocr, \
             patch('aram_demo.recognition.time.monotonic', side_effect=[20, 20.4, 20.9]):
            self.assertIsNone(recognizer.read_screen(frame, augments)[2].augment_id)
            recognizer.read_screen(frame, augments)
            self.assertEqual(ocr.call_count, 3)
            matches = recognizer.read_screen(frame, augments)
            self.assertEqual([m.augment_id for m in matches], [1, 2, 3])
            self.assertEqual(ocr.call_count, 4)


if __name__ == '__main__':
    unittest.main()
