"""Small mode-aware launcher; dragging never activates the game or expands it."""
import os
import tkinter as tk

from .theme import ACCENT, GOLD, BG, RAISED, SURFACE
from .windows import prepare_popup


class CompanionBubble:
    size = 48

    def __init__(self, root, on_expand):
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title('海克斯随行 · 单击展开，拖动移动')
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        transparent = '#010203'
        self.window.configure(bg=transparent)
        if os.name == 'nt':
            self.window.attributes('-transparentcolor', transparent)
        self.canvas = tk.Canvas(self.window, width=self.size, height=self.size,
                                bg=transparent, bd=0, highlightthickness=0, cursor='hand2')
        self.canvas.pack()
        self.shape = self.canvas.create_polygon(24, 2, 44, 13, 44, 35, 24, 46, 4, 35, 4, 13,
                                                fill=SURFACE, outline=GOLD, width=2)
        self.canvas.create_line(17, 15, 17, 33, 17, 24, 31, 24, 31, 15, 31, 33,
                                fill=ACCENT, width=3, capstyle='round')
        self.visible = False
        self.position = None
        self.work_area = (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
        self.on_expand = on_expand
        self.origin = None
        self.dragged = False
        self.canvas.bind('<Enter>', lambda _: self.canvas.itemconfigure(self.shape, fill=RAISED))
        self.canvas.bind('<Leave>', lambda _: self.canvas.itemconfigure(self.shape, fill=SURFACE))
        self.canvas.bind('<ButtonPress-1>', self._begin)
        self.canvas.bind('<B1-Motion>', self._drag)
        self.canvas.bind('<ButtonRelease-1>', self._release)
        prepare_popup(self.window)

    def _place(self, x, y):
        left, top, right, bottom = self.work_area
        position = (max(left, min(x, right - self.size)), max(top, min(y, bottom - self.size)))
        if position == self.position:
            return
        self.position = position
        x, y = self.position
        self.window.geometry(f'{self.size}x{self.size}{x:+d}{y:+d}')

    def show_at(self, anchor):
        self.work_area = anchor.work_area
        x, y = self.position or (self.work_area[2] - self.size - 16, self.work_area[1] + 16)
        self._place(x, y)
        if not self.visible:
            self.window.deiconify()
            self.visible = True

    def _begin(self, event):
        self.origin = (event.x_root, event.y_root, *self.position)
        self.dragged = False
        self.canvas.itemconfigure(self.shape, fill=BG)

    def _drag(self, event):
        if self.origin is None:
            return
        sx, sy, x, y = self.origin
        dx, dy = event.x_root - sx, event.y_root - sy
        self.dragged = self.dragged or max(abs(dx), abs(dy)) >= 5
        if self.dragged:
            self._place(x + dx, y + dy)

    def _release(self, event):
        if self.origin is None:
            return
        self._drag(event)
        self.origin = None
        self.canvas.itemconfigure(self.shape, fill=SURFACE)
        if not self.dragged:
            self.on_expand()

    def hide(self):
        if self.visible:
            self.window.withdraw()
            self.visible = False
