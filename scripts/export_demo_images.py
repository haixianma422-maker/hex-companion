"""Capture actual native windows from saved statistics, with network disabled."""
import ctypes,json,sys,tempfile,tkinter as tk
from ctypes import wintypes as W
from pathlib import Path
from unittest.mock import patch
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp
from aram_demo.lcu import ClientState
from aram_demo.recognition import match_slots
from aram_demo.windows import LeagueWindow
user=ctypes.WinDLL('user32',use_last_error=True)
user.CreateDesktopW.argtypes=[W.LPCWSTR,W.LPCWSTR,ctypes.c_void_p,W.DWORD,W.DWORD,ctypes.c_void_p]
user.CreateDesktopW.restype=W.HANDLE
user.SetThreadDesktop.argtypes=[W.HANDLE]
desktop=user.CreateDesktopW('HexAssetsVerification-'+str(__import__('os').getpid()),None,None,0,0x00C7,None)
if not desktop or not user.SetThreadDesktop(desktop):raise ctypes.WinError(ctypes.get_last_error())
try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
except OSError:pass
out=ROOT/'docs/images';out.mkdir(parents=True,exist_ok=True)
root=tk.Tk();root.design_scale=1
folder=tempfile.TemporaryDirectory(dir=ROOT/'.build-cache')
app=CompanionApp(root,DataStore(Path(folder.name),ROOT/'data',source='qq101'),services=False)
app.locate=lambda:LeagueWindow(0,(100,100,1300,900),(0,0,1920,1080),True)
app.panel.set_motion(False);app.bubble.set_motion(False)

def screenshot(name,win=None):
    root.update_idletasks();root.update();root.update_idletasks()
    win=win or app.panel.window;width,height=win.winfo_width(),win.winfo_height()
    user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
    hwnd=user.GetAncestor(win.winfo_id(),2)
    user.GetDC.argtypes=[W.HWND];user.GetDC.restype=W.HDC
    user.ReleaseDC.argtypes=[W.HWND,W.HDC]
    user.PrintWindow.argtypes=[W.HWND,W.HDC,W.UINT]
    gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    gdi.CreateCompatibleDC.argtypes=[W.HDC];gdi.CreateCompatibleDC.restype=W.HDC
    gdi.CreateCompatibleBitmap.argtypes=[W.HDC,ctypes.c_int,ctypes.c_int];gdi.CreateCompatibleBitmap.restype=W.HBITMAP
    gdi.SelectObject.argtypes=[W.HDC,W.HGDIOBJ];gdi.SelectObject.restype=W.HGDIOBJ
    gdi.DeleteObject.argtypes=[W.HGDIOBJ];gdi.DeleteDC.argtypes=[W.HDC]
    class Header(ctypes.Structure):
        _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),('bits',W.WORD),
                  ('compression',W.DWORD),('image_size',W.DWORD),('xppm',W.LONG),('yppm',W.LONG),('used',W.DWORD),('important',W.DWORD)]
    class Info(ctypes.Structure):_fields_=[('header',Header),('colors',W.DWORD*3)]
    gdi.GetDIBits.argtypes=[W.HDC,W.HBITMAP,W.UINT,W.UINT,ctypes.c_void_p,ctypes.POINTER(Info),W.UINT]
    source=user.GetDC(hwnd);target=gdi.CreateCompatibleDC(source)
    bitmap=gdi.CreateCompatibleBitmap(source,width,height);previous=gdi.SelectObject(target,bitmap)
    try:
        if not user.PrintWindow(hwnd,target,2):raise ctypes.WinError(ctypes.get_last_error())
        info=Info();info.header=Header(ctypes.sizeof(Header),width,-height,1,32,0,width*height*4,0,0,0,0)
        raw=ctypes.create_string_buffer(width*height*4)
        if gdi.GetDIBits(target,bitmap,0,height,raw,ctypes.byref(info),0)!=height:raise RuntimeError('Capture failed')
        image=Image.frombytes('RGB',(width,height),raw.raw,'raw','BGRX')
        image.save(out/name)
        return {str(key):value for key,value in app.panel.assets_shown.items()}
    finally:
        gdi.SelectObject(target,previous);gdi.DeleteObject(bitmap);gdi.DeleteDC(target);user.ReleaseDC(hwnd,source)

try:
    with patch('urllib.request.urlopen',side_effect=AssertionError('Network is disabled')) as network:
        app.on_client_state(ClientState('ChampSelect',101,[101,222,99,17],queue_id=3270))
        selection=screenshot('champion-select.png')
        app.on_client_state(ClientState('InProgress',101,queue_id=3270))
        app.accept_matches(match_slots(['虚幻武器','巫师式思考','有始有终'],app.augments))
        game=screenshot('in-game.png')
        for key in ("('splash', 101)","('skill', 'E')","('augment', 1029)","('augment', 1097)"):
            assert game.get(key),key
        assert selection.get("('splash', 101)")
        app.show_settings();root.update()
        app._settings_notebook.motion.set_enabled(False)
        app._settings_notebook.select(1);root.update()
        screenshot('hotkey-settings.png',app.dialog)
        app.dialog.destroy();root.update()
        app.hide();root.update()
        screenshot('collapsed-bubble.png',app.bubble.window)
        network.assert_not_called()
    report={'real_game_tested':False,'native_windows':True,'client_state':'controlled offline inputs',
            'network_requests':0,'selection_assets':selection,'game_assets':game}
    (out/'capture.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
finally:
    app.close();folder.cleanup()
