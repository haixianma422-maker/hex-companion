"""Measure real OCR and a simulated single-card reroll through the native popup."""
import argparse
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp, AUTO_SCAN_INTERVAL, UI_TICK_MS
from aram_demo.lcu import ClientState
from aram_demo.models import Augment
from aram_demo.recognition import Recognizer, DEFAULT_REGIONS
from aram_demo.windows import LeagueWindow

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('image', type=Path)
parser.add_argument('--champion-id', type=int, required=True)
parser.add_argument('--alternate', type=Path, required=True)
parser.add_argument('--alternate-left-id', type=int, required=True)
parser.add_argument('--expected-ids', required=True)
args = parser.parse_args()
image = Image.open(args.image).convert('RGB')
alternate = Image.open(args.alternate).convert('RGB').resize(image.size)
store = DataStore(ROOT / 'data')
augments = [Augment(**row) for row in store.hero(args.champion_id)['augments']]
assert args.alternate_left_id in {row.id for row in augments}, 'Alternate must be available to this champion'
expected = [int(value) for value in args.expected_ids.split(',')]
r = Recognizer()
results = []
for name, force in [('cold', False), ('warm_1', True), ('warm_2', True), ('warm_3', True), ('unchanged', False)]:
    started = time.perf_counter()
    matches = r.read_screen(image, augments, force=force)
    ids = [row.augment_id for row in matches]
    assert ids == expected, (name, ids)
    results.append({'case': name, 'seconds': round(time.perf_counter() - started, 4), 'ids': ids})

x1, y1, x2, y2 = DEFAULT_REGIONS[0]
box = (round(x1 * image.width), round(y1 * image.height), round(x2 * image.width), round(y2 * image.height))
rerolled = image.copy()
rerolled.paste(alternate.crop(box), box)
rerolled_ids = [args.alternate_left_id, *expected[1:]]
with patch.object(r, 'read_image', wraps=r.read_image) as calls:
    started = time.perf_counter()
    matches = r.read_screen(rerolled, augments)
    assert [row.augment_id for row in matches] == rerolled_ids
    assert calls.call_count == 1, 'Unchanged slots must not run OCR'
    results.append({'case': 'one_card_reroll', 'seconds': round(time.perf_counter() - started, 4),
                    'ocr_calls': calls.call_count, 'ids': rerolled_ids})

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
qt = QGuiApplication(sys.argv)
app = CompanionApp(store, preview=True, services=False)
app.on_client_state(ClientState('InProgress', args.champion_id, queue_id=3270))
app.preview = False
app.recognizer = r
screen = qt.primaryScreen()
width = round(screen.geometry().width() * screen.devicePixelRatio())
height = round(screen.geometry().height() * screen.devicePixelRatio())
anchor = LeagueWindow(0, (0, 0, image.width, image.height), (0, 0, width, height - 48), True)
app.locate = lambda: anchor
frame = image
hidden, rebuilt = [], []
app.overlay.window('panelWindow').visibleChanged.connect(lambda visible: hidden.append(True) if not visible else None)
app.panel.cards.rowsRemoved.connect(lambda *_: rebuilt.append(True))

def until(ids):
    deadline = time.perf_counter() + 8
    while time.perf_counter() < deadline:
        qt.processEvents()
        if [row.augment_id for row in app.matches] == ids:
            return
        time.sleep(.005)
    raise AssertionError('Timed out waiting for result')

try:
    with patch('aram_demo.companion.find_league_window', return_value=anchor),          patch('PIL.ImageGrab.grab', side_effect=lambda **kwargs: frame):
        QTimer.singleShot(0, app._pump)
        QTimer.singleShot(0, app._tick)
        until(expected)
        qt.processEvents()
        place = dict(app.panel.place)
        started = time.perf_counter()
        frame = rerolled
        until(rerolled_ids)
        latency = round(time.perf_counter() - started, 4)
        assert app.panel.place == place
        assert not hidden and not rebuilt
        assert latency < 2.5, latency
        results.append({'case': 'native_auto_reroll_to_visible_result', 'seconds': latency,
                        'ids': rerolled_ids, 'window_hidden': 0, 'cards_rebuilt': 0})
finally:
    app.close()

report = {'status': 'passed', 'auto_cooldown_seconds': AUTO_SCAN_INTERVAL, 'ui_tick_ms': UI_TICK_MS,
          'samples': results, 'live_game_tested': False,
          'verification': 'User screenshot replay, real OCR and the Qt overlay; game capture supplied by fixture'}
(ROOT / 'artifacts/recognition_latency_after.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
