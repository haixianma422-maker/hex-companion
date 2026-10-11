"""Controlled offline screenshot; this is not a real game capture."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFont
from aram_demo.cache import DataStore
from aram_demo.models import Augment
from aram_demo.recognition import Recognizer

out = ROOT / 'artifacts'
out.mkdir(exist_ok=True)
image = Image.new('RGB', (1500, 600), '#0d1524')
draw = ImageDraw.Draw(image)
font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 32)
names = ['暴击飞弹', '更万用的瞄准镜', '双刀流']
regions = [(0.02, 0.3, 0.32, 0.5), (0.35, 0.3, 0.65, 0.5), (0.68, 0.3, 0.98, 0.5)]
for i, name in enumerate(names):
    draw.rounded_rectangle((i * 500 + 20, 100, i * 500 + 480, 500), radius=18, fill='#1d2a42', outline='#58708d', width=2)
    draw.text((i * 500 + 50, 205), name, font=font, fill='white')
draw.text((40, 25), '离线受控 OCR 样本', font=font, fill='#91a7bc')
image.save(out / 'ocr_sample.png')
data = DataStore(ROOT / 'data').hero(222)
augments = [Augment(**a) for a in data['augments']]
matches = Recognizer(regions).read_screen(image, augments)
result = [{'slot': m.slot, 'text': m.text, 'augment_id': m.augment_id, 'status': m.status} for m in matches]
(out / 'ocr_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
assert [m.text for m in matches] == names, 'OCR text mismatch'
assert all(m.status == 'matched' for m in matches), 'Unmatched controlled card'
