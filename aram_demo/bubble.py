"""40px branded launcher, with click and drag treated separately."""
import os
import tkinter as tk
from .motion import Motion
from .ui_drawing import Artboard, Hint, ui_scale, position_window, TRANSPARENT, SURFACE, RAISED, BG, ACCENT
from .windows import prepare_popup

class CompanionBubble:
    def __init__(self, root, on_expand):
        self.scale=ui_scale(root); self.size=round(40*self.scale)
        self.window=tk.Toplevel(root); self.window.withdraw()
        self.window.title('海克斯随行 · 浮标'); self.window.overrideredirect(True)
        self.window.attributes('-topmost', True); self.window.configure(bg=TRANSPARENT)
        if os.name=='nt':self.window.attributes('-transparentcolor',TRANSPARENT)
        self.canvas=tk.Canvas(self.window,width=self.size,height=self.size,bg=TRANSPARENT,bd=0,highlightthickness=0,cursor='hand2',takefocus=True)
        self.canvas.pack(); self.motion=Motion(self.window)
        self.visible=False; self.position=None; self.work_area=(0,0,root.winfo_screenwidth(),root.winfo_screenheight())
        self.on_expand=on_expand; self.origin=None; self.dragged=False; self._hover=False; self._pressed=False
        self._keyboard_focus=False
        self.canvas.bind('<FocusIn>',lambda _:self._focus(True))
        self.canvas.bind('<FocusOut>',lambda _:self._focus(False))
        self._user_position=False; self.tip=Hint(self.canvas,'单击展开，拖动移动 · F8 展开/收起')
        self.canvas.bind('<Enter>',lambda _:self._tint(True))
        self.canvas.bind('<Leave>',lambda _:self._tint(False))
        self.canvas.bind('<ButtonPress-1>',self._begin)
        self.canvas.bind('<B1-Motion>',self._drag)
        self.canvas.bind('<ButtonRelease-1>',self._release)
        self.canvas.bind('<Return>',lambda _:self.on_expand())
        self.canvas.bind('<space>',lambda _:self.on_expand())
        self._paint(); prepare_popup(self.window)

    def _paint(self):
        art=Artboard(40,40,self.scale,bg=TRANSPARENT)
        art.circle((0,0,39.8,39.8),BG if self._pressed else RAISED if self._hover else SURFACE)
        art.brand((9,9,22,22),ACCENT)
        if self._keyboard_focus:art.circle((2,2,35,35),None,ACCENT,2)
        self.photo=art.photo(self.canvas); self.canvas.delete('all'); self.canvas.create_image(0,0,image=self.photo,anchor='nw')

    def _focus(self,focused):self._keyboard_focus=focused; self._paint()
    def _tint(self,hover):self._hover=hover; self._paint()
    def set_hotkeys(self,bindings):self.tip.text='单击展开，拖动移动 · '+bindings.get('toggle','F8')+' 展开/收起'
    def set_motion(self,enabled):self.motion.set_enabled(enabled); self.window.attributes('-alpha',1.)
    def _place(self,x,y):
        l,t,r,b=self.work_area
        self.position=(max(l,min(round(x),r-self.size)),max(t,min(round(y),b-self.size)))
        position_window(self.window,*self.position,self.size,self.size)
    def show_at(self,anchor,rectangle=None,animate=True):
        self.work_area=anchor.work_area
        if not self._user_position and rectangle:
            x,y,w,h=rectangle; self.position=(x+w-self.size-12*self.scale,y+h-self.size-12*self.scale)
        if self.visible and 'visibility' in self.motion.jobs:return  # the reveal places the window each frame
        x,y=self.position or (self.work_area[2]-self.size-16,self.work_area[1]+16)
        self._place(x,y)
        if not self.visible:
            self.motion.cancel('visibility',finish=True); self.visible=True
            self.window.attributes('-alpha',0. if self.motion.enabled else 1.); self.window.deiconify(); self._place(*self.position)
            rise=12*self.scale
            def update(v):
                # Rise into place while fading in; the end frame is the resting position.
                self.window.attributes('-alpha',v)
                position_window(self.window,self.position[0],round(self.position[1]+rise*(1-v)),self.size,self.size)
            self.motion.animate('visibility',0.,1.,update,280 if animate else 0)
    def _begin(self,event):
        self.tip.hide(); self.origin=(event.x_root,event.y_root,*self.position); self.dragged=False; self._pressed=True; self._paint()
    def _drag(self,event):
        if self.origin is None:return
        sx,sy,x,y=self.origin; dx,dy=event.x_root-sx,event.y_root-sy
        self.dragged=self.dragged or max(abs(dx),abs(dy))>4*self.scale
        if self.dragged:self._user_position=True; self._place(x+dx,y+dy)
    def _release(self,event):
        if self.origin is None:return
        self._drag(event); self.origin=None; self._pressed=False; self._paint()
        if not self.dragged:self.on_expand()
    def hide(self,animate=False):
        self.tip.hide()
        if self.visible:
            self.motion.cancel('visibility',finish=True)
            self.visible=False; self.motion.cancel_all()
            def finish():
                self.window.withdraw(); self.window.attributes('-alpha',1.)
            if animate and self.motion.enabled:self.motion.animate('visibility',1.,0.,lambda v:self.window.attributes('-alpha',v),220,done=finish)
            else:self.window.withdraw(); self.window.attributes('-alpha',1.)
        elif not animate:self.motion.cancel_all(); self.window.withdraw(); self.window.attributes('-alpha',1.)
