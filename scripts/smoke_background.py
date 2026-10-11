"""Check a real Windows tray, hidden root, then cleanly stop this test instance."""
import json
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp

root = tk.Tk()
app = CompanionApp(root, DataStore(ROOT / 'data'))
try:
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        root.update()
        time.sleep(.08)
    result = {'root_hidden': root.state() == 'withdrawn', 'panel_hidden': not app.panel.visible,
              'tray_visible': app.tray.icon.visible, 'client_phase': app.state.phase,
              'hotkeys': app.hotkeys.status, 'real_game_tested': False}
    print(json.dumps(result, ensure_ascii=True))
    assert all(result[k] for k in ('root_hidden', 'panel_hidden', 'tray_visible'))
    (ROOT / 'artifacts/background_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
finally:
    app.close()
assert not app.tray.icon.visible
print('Tray stopped; application closed.')
