"""Offline native motion/DPI/resize acceptance; stores screenshots and timings."""
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp
from aram_demo.lcu import ClientState
from aram_demo.recognition import match_slots
from aram_demo.ui_snapshot import snapshot
from aram_demo.windows import LeagueWindow


def run():
    from ctypes import wintypes as W
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.CreateDesktopW.argtypes=[W.LPCWSTR,W.LPCWSTR,ctypes.c_void_p,W.DWORD,W.DWORD,ctypes.c_void_p]
    user.CreateDesktopW.restype=W.HANDLE; user.SetThreadDesktop.argtypes=[W.HANDLE]
    desktop=user.CreateDesktopW('HexMotionCapture-'+str(os.getpid()),None,None,0,0x01FF,None)
    if not desktop or not user.SetThreadDesktop(desktop):raise ctypes.WinError(ctypes.get_last_error())
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except OSError:pass
    out=ROOT/'artifacts/motion-v2/native';out.mkdir(parents=True,exist_ok=True)
    report={'live_game_tested':False,'native_windows':True,'network_requests':0,'scales':[]}
    previews=[]
    for scale in (1.,1.25,1.5):
        root=tk.Tk();root.design_scale=scale
        errors=[];root.report_callback_exception=lambda kind,value,tb:errors.append(str(value))
        temporary=tempfile.TemporaryDirectory(dir=ROOT/'.build-cache')
        app=CompanionApp(root,DataStore(Path(temporary.name),ROOT/'data',source='qq101'),preview=True,services=False)
        app.locate=lambda:LeagueWindow(0,(100,100,1300,900),(0,0,2560,1440),True)
        app.panel.set_motion(False);app.bubble.set_motion(False)
        tag=str(round(scale*100));checks={}
        def capture(name,window=None):
            root.update_idletasks();root.update()
            picture=snapshot(window or app.panel.window)
            assert picture is not None,name
            picture.save(out/(tag+'-'+name+'.png'))
            return picture
        def settle():
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                root.update()
                jobs=list(app.panel.motion.jobs)+list(app.bubble.motion.jobs)
                if app.dialog and app.dialog.winfo_exists():jobs+=list(app._settings_notebook.motion.jobs)
                if not jobs:return
                time.sleep(.005)
            raise AssertionError('Animation did not settle')
        try:
            with patch('urllib.request.urlopen',side_effect=AssertionError('Network disabled')) as network:
                app.on_client_state(ClientState('ChampSelect',101,[101,222,99,17],queue_id=3270))
                capture('select')
                app.panel.set_motion(True)
                app.on_client_state(ClientState('ChampSelect',222,[101,222,99,17],queue_id=3270))
                settle();hero=capture('hero')
                app.on_client_state(ClientState('InProgress',101,queue_id=3270))
                app.accept_matches(match_slots(['虚幻武器','巫师式思考',''],app.augments));settle()
                old=app.panel._full_image.copy()
                app.accept_matches(match_slots(['虚幻武器','巫师式思考','有始有终'],app.augments));settle()
                game=capture('game')
                app.scanning=app.scan_feedback=True;app.present()
                wall=time.monotonic();cpu=time.process_time()
                while time.monotonic()-wall<.4:root.update();time.sleep(.005)
                checks['activity_cpu_ms_over_400ms']=round((time.process_time()-cpu)*1000,2)
                capture('scanning')
                app.scan_finished();settle()
                assert not app.panel.scan_button.motion.jobs
                app.panel.set_motion(True);app.bubble.set_motion(True)
                app.hide()
                assert app.bubble.visible and 'visibility' in app.panel.motion.jobs
                settle();capture('bubble',app.bubble.window)
                app.expand();settle()
                assert float(app.panel.window.attributes('-alpha'))==1.
                assert not app.panel._visibility_layer.winfo_manager()
                app.show_settings();root.update()
                app._settings_notebook.motion.set_enabled(True)
                for page in (1,2,0):app._settings_notebook.select(page)
                settle();settings=capture('settings',app.dialog)
                app.dialog.destroy();root.update()
                # Exercise the same right-corner gesture used by the product.
                panel=app.panel
                x,y=panel.window.winfo_rootx(),panel.window.winfo_rooty()
                start=SimpleNamespace(x=panel.width-4,y=panel.height-4,x_root=x+panel.width-4,y_root=y+panel.height-4)
                panel._press(start)
                panel._drag(SimpleNamespace(x_root=start.x_root+36*scale,y_root=start.y_root+58*scale))
                panel._release(SimpleNamespace(x_root=start.x_root+36*scale,y_root=start.y_root+58*scale))
                root.update();resized=capture('resized')
                assert abs(panel.zoom-1.1)<.002
                assert abs(app.store.read('settings.json')['panel_zoom']-panel.zoom)<.001
                assert panel.scan_button.scale==panel.scale
                checks['resized_px']=[panel.window.winfo_width(),panel.window.winfo_height()]
                checks['logical_zoom']=panel.zoom
                panel.set_motion(False);app.bubble.set_motion(False)
                app.hide();app.expand();root.update()
                assert not panel.motion.jobs and not app.bubble.motion.jobs
                assert not panel.scan_button.motion.jobs
                before=set(root.tk.call('after','info'))
                for _ in range(10):root.update();time.sleep(.01)
                assert set(root.tk.call('after','info'))==before
                checks['idle_motion_jobs']=0
                checks['callback_errors']=list(errors)
                assert not errors
                network.assert_not_called()
                report['scales'].append(dict(dpi_scale=scale,checks=checks))
                if scale==1.:previews=[('Hero',hero),('Game',game),('Settings',settings),('Resize 110%',resized)]
        finally:
            app.close();temporary.cleanup()
    sheet=Image.new('RGB',(1460,760),'#eeeeee');draw=ImageDraw.Draw(sheet)
    x=10
    for label,picture in previews:
        picture=picture.convert('RGB');picture.thumbnail((350,710))
        sheet.paste(picture,(x,35));draw.text((x,10),label,fill='black');x+=365
    sheet.save(out/'contact-sheet.png')
    report['status']='passed'
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':run()
