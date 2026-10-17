"""Capture the actual Qt windows from saved statistics, with network disabled."""
import ctypes, json, os, sys, tempfile, time
from ctypes import wintypes as W
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))

# Render on an invisible desktop; created before Qt so its windows land there.
user = ctypes.WinDLL('user32', use_last_error=True)
user.CreateDesktopW.argtypes = [W.LPCWSTR, W.LPCWSTR, ctypes.c_void_p, W.DWORD, W.DWORD, ctypes.c_void_p]
user.CreateDesktopW.restype = W.HANDLE
user.SetThreadDesktop.argtypes = [W.HANDLE]
desktop = user.CreateDesktopW('HexAssetsVerification-' + str(os.getpid()), None, None, 0, 0x00C7, None)
if not desktop or not user.SetThreadDesktop(desktop): raise ctypes.WinError(ctypes.get_last_error())

from PySide6.QtGui import QGuiApplication
from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp
from aram_demo.lcu import ClientState
from aram_demo.recognition import match_slots
from aram_demo.windows import LeagueWindow

qt = QGuiApplication(sys.argv[:1])
out = ROOT / 'docs/images'; out.mkdir(parents=True, exist_ok=True)
folder = tempfile.TemporaryDirectory(dir=ROOT / '.build-cache')
app = CompanionApp(DataStore(Path(folder.name), ROOT / 'data', source='qq101'), services=False)
app.locate = lambda: LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1080), True)
app.panel.set_motion(False); app.bubble.set_motion(False)


def settle(condition=lambda: True, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qt.processEvents()
        if condition() and not app.panel.assets.busy():
            break
        time.sleep(.01)
    for _ in range(30):      # let images decode and the 1 ms "motion off" animations finish
        qt.processEvents(); time.sleep(.01)


def screenshot(name, window):
    settle(window.isVisible)
    window.grabWindow().save(str(out / name))
    return {str(key): value for key, value in app.panel.assets_shown.items()}


try:
    with patch('urllib.request.urlopen', side_effect=AssertionError('Network is disabled')) as network:
        panel = app.overlay.window('panelWindow')
        app.on_client_state(ClientState('ChampSelect', 101, [101, 222, 99, 17], queue_id=3270))
        settle(); app.present()
        selection = screenshot('champion-select.png', panel)
        app.on_client_state(ClientState('InProgress', 101, queue_id=3270))
        app.accept_matches(match_slots(['虚幻武器', '巫师式思考', '有始有终'], app.augments))
        settle(); app.present()
        game = screenshot('in-game.png', panel)
        for key in ("('splash', 101)", "('skill', 'E')", "('augment', 1029)", "('augment', 1097)"):
            assert game.get(key), key
        assert selection.get("('splash', 101)")
        app.show_settings()
        app.dialog.select_tab(1)
        screenshot('hotkey-settings.png', app.dialog.window)
        app.dialog.close()
        app.hide()
        screenshot('collapsed-bubble.png', app.overlay.window('bubbleWindow'))
        network.assert_not_called()
    report = {'real_game_tested': False, 'native_windows': True, 'toolkit': 'Qt Quick',
              'client_state': 'controlled offline inputs', 'network_requests': 0,
              'selection_assets': selection, 'game_assets': game}
    (out / 'capture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
finally:
    app.close(); folder.cleanup()
