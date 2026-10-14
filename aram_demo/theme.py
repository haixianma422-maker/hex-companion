"""Shared desktop tokens and lightweight, local-only rounded surfaces."""
import tkinter as tk
from tkinter import ttk
import math
from PIL import Image, ImageDraw
from .tk_images import WidgetPhotoImage
from .motion import Motion

BG = '#191723'
SURFACE = '#282333'
RAISED = '#393145'
LINE = '#443a55'
TEXT = '#f7f3eb'
MUTED = '#b6a6d9'
ACCENT = '#dfff80'
LILAC = '#e9e2f7'
INK = BG
GOLD = ACCENT
TIER_BG = '#4a405c'
NEUTRAL_BG = '#332c42'
FONT = 'Microsoft YaHei UI'
GRADES = [INK] * 6
GRADE_BACKGROUNDS = [ACCENT, LILAC, '#d6c8ed', '#c4b3dd', '#b3a3c9', '#a796ba']


def label(parent, text, color=TEXT, size=10, bold=False, **kwargs):
    widget = tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                      font=(FONT, size, 'bold' if bold else 'normal'), bd=0, **kwargs)
    maximum = kwargs.get('wraplength')
    if maximum:
        def reflow(event):
            width = min(maximum, max(1, event.width - 2))
            if int(widget.cget('wraplength')) != width:
                widget.configure(wraplength=width)
        widget.bind('<Configure>', reflow)
    return widget


def button(parent, text, command, primary=False):
    base, hover = (ACCENT, '#eaffad') if primary else (RAISED, '#4b405c')
    fg = INK if primary else TEXT
    surface = Card(parent, color=base, padding=3, radius=18)
    widget = tk.Button(surface.body, text=text, command=command, bg=base, fg=fg,
                       activebackground=hover, activeforeground=fg, disabledforeground=MUTED,
                       relief='flat', bd=0, padx=9, pady=3, cursor='hand2', takefocus=True,
                       highlightthickness=0, highlightbackground=GOLD if primary else LINE,
                       highlightcolor=ACCENT, font=(FONT, 9))
    widget.pack(fill='both', expand=True)
    widget.pack = surface.pack
    widget.pack_forget = surface.pack_forget
    def tint(color):
        surface.set_color(color)
        widget.configure(bg=color)
    widget.bind('<Enter>', lambda _: tint(hover) if widget.cget('state') != 'disabled' else None)
    widget.bind('<Leave>', lambda _: tint(base))
    def focus(border):
        surface.border = border
        surface._size = None
        surface._paint()
    widget.bind('<FocusIn>', lambda _: focus(ACCENT))
    widget.bind('<FocusOut>', lambda _: focus(None))
    return widget


class Card(tk.Frame):
    """Rounded background with ordinary native widgets inside."""
    def __init__(self, parent, color=SURFACE, padding=12, radius=16, border=None):
        super().__init__(parent, bg=parent.cget('bg'), bd=0)
        self.color, self.radius, self.border = color, radius, border
        self.back = tk.Canvas(self, bg=self.cget('bg'), highlightthickness=0, bd=0)
        self.back.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = tk.Frame(self, bg=color, bd=0)
        self.body.pack(fill='both', expand=True, padx=padding, pady=padding)
        self.back.bind('<Configure>', self._paint)
        self._photo = self._size = self._image_item = None

    def set_color(self, color):
        if color == self.color:
            return
        old = self.color
        self.color = color
        self.body.configure(bg=color)
        for child in self.body.winfo_children():
            if child.cget('bg') == old:
                child.configure(bg=color)
        self._size = None
        self._paint()

    def _paint(self, event=None):
        size = (event.width, event.height) if event else (self.back.winfo_width(), self.back.winfo_height())
        if size == self._size or min(size) < 2:
            return
        self._size = size
        scale = 3
        image = Image.new('RGB', (size[0] * scale, size[1] * scale), self.cget('bg'))
        ImageDraw.Draw(image).rounded_rectangle(
            (0, 0, image.width - 1, image.height - 1), radius=self.radius * scale,
            fill=self.color, outline=self.border or self.color, width=scale)
        photo = WidgetPhotoImage(image.resize(size, Image.Resampling.LANCZOS), master=self)
        if self._image_item is None:
            self._image_item = self.back.create_image(0, 0, image=photo, anchor='nw', tags='surface')
        else:
            self.back.itemconfigure(self._image_item, image=photo)
        self._photo = photo


class ScrollArea(tk.Frame):
    """Scrollbar appears only when the desktop work area cannot fit the content."""
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=self.cget('bg'), bd=0, highlightthickness=0,
                                width=260, height=80, yscrollincrement=20)
        self.scroll = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview,
                                    style='Hex.Vertical.TScrollbar')
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=self.cget('bg'))
        self.item = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.canvas.bind('<Configure>', self._resize)
        self.body.bind('<Configure>', self._sync)

    def _resize(self, event):
        self.canvas.itemconfigure(self.item, width=event.width)
        self._sync()

    def _sync(self, _=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        overflow = self.body.winfo_reqheight() > self.canvas.winfo_height() + 2
        if overflow and not self.scroll.winfo_manager():
            self.scroll.pack(side='right', fill='y', padx=(4, 0))
        elif not overflow and self.scroll.winfo_manager():
            self.scroll.pack_forget()

    def bind_wheel(self):
        def wheel(event):
            self.canvas.yview_scroll(-int(event.delta / 120), 'units')
            return 'break'
        def visit(widget):
            widget.bind('<MouseWheel>', wheel)
            for child in widget.winfo_children():
                visit(child)
        visit(self)


def configure_styles(root):
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('Hex.Vertical.TScrollbar', background=LINE, troughcolor=BG,
                    borderwidth=0, arrowsize=0, width=7, lightcolor=LINE, darkcolor=LINE)
    style.map('Hex.Vertical.TScrollbar', background=[('active', MUTED)])
    style.configure('Hex.TNotebook', background=BG, borderwidth=0, tabmargins=(0, 0, 0, 8),
                    lightcolor=BG, darkcolor=BG, bordercolor=BG)
    style.configure('Hex.TNotebook.Tab', background=LILAC, foreground=INK,
                    padding=(14, 8), borderwidth=0, font=(FONT, 10),
                    lightcolor=BG, darkcolor=BG, bordercolor=BG, focuscolor=ACCENT)
    style.map('Hex.TNotebook.Tab', background=[('selected', RAISED), ('active', '#d6c8ed')],
              foreground=[('selected', TEXT), ('active', INK)])
    for name in ('Hex.TEntry', 'Hex.TCombobox'):
        style.configure(name, fieldbackground=LILAC, foreground=INK, background=LILAC,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                        arrowcolor=INK, padding=6, insertcolor=INK)
        style.map(name, bordercolor=[('focus', ACCENT)],
                  fieldbackground=[('readonly', LILAC)], foreground=[('readonly', INK)])
    root.option_add('*TCombobox*Listbox.background', LILAC)
    root.option_add('*TCombobox*Listbox.foreground', INK)
    root.option_add('*TCombobox*Listbox.selectBackground', RAISED)
    root.option_add('*TCombobox*Listbox.selectForeground', ACCENT)
    root.option_add('*TCombobox*Listbox.font', (FONT, 10))


def _brand_points(x, y, size):
    points = []
    for step in range(100):
        angle = step * 2 * math.pi / 100 - math.pi / 2
        radius = size * .5 * (.72 + .28 * math.cos(5 * (angle + math.pi / 2)))
        points.extend((x + radius * math.cos(angle), y + radius * math.sin(angle)))
    return points


def draw_brand(canvas, x, y, size=24, color=ACCENT):
    from .ui_drawing import Artboard
    art=Artboard(size,size,bg=(0,0,0,0)); art.brand((0,0,size,size),color)
    photo=art.photo(canvas)
    if not hasattr(canvas,'_brand_photos'):canvas._brand_photos=[]
    canvas._brand_photos.append(photo)
    return canvas.create_image(x,y,image=photo)


def brand_image(size=64):
    from .ui_drawing import Artboard
    art=Artboard(size,size,bg=(0,0,0,0)); art.circle((0,0,size-1,size-1),BG)
    inset=size*.225; art.brand((inset,inset,size*.55,size*.55))
    return art.finish()


def _pill(canvas, left, top, right, bottom, fill, tag):
    radius = min((bottom - top) / 2, (right - left) / 2)
    return canvas.create_polygon(left + radius, top, right - radius, top, right, top,
                                 right, top + radius, right, bottom - radius, right, bottom,
                                 right - radius, bottom, left + radius, bottom, left, bottom,
                                 left, bottom - radius, left, top + radius, left, top,
                                 smooth=True, splinesteps=20, fill=fill, outline='', tags=tag)


class SegmentedControl(tk.Frame):
    """A saved-value selector; changing its variable never invokes the action."""
    def __init__(self, parent, variable, values, on_change=None):
        super().__init__(parent, bg=parent.cget('bg'), takefocus=True)
        self.variable, self.values, self.on_change = variable, dict(values), on_change
        self.canvas = tk.Canvas(self, height=32, width=180, bg=self.cget('bg'), bd=0,
                                highlightthickness=0, cursor='hand2')
        self.canvas.pack(fill='x', expand=True)
        self.motion = Motion(self)
        self.position = self._index()
        self.trace = variable.trace_add('write', self._changed)
        self.canvas.bind('<Configure>', lambda _: self._paint())
        self.canvas.bind('<Button-1>', self._click)
        self.bind('<Left>', lambda _: self._choose((self._index() - 1) % len(self.values)))
        self.bind('<Right>', lambda _: self._choose((self._index() + 1) % len(self.values)))
        self.bind('<Destroy>', self._destroy_trace, add='+')
        self._paint()

    def _index(self):
        values = list(self.values.values())
        return values.index(self.variable.get()) if self.variable.get() in values else 0

    def _destroy_trace(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self.trace)

    def _changed(self, *_):
        self.motion.animate('selection', self.position, self._index(), self._move, 140)

    def _move(self, value):
        self.position = value
        self._paint()

    def _paint(self):
        width = max(self.canvas.winfo_width(), int(self.canvas.cget('width')))
        cell = width / max(1, len(self.values))
        self.canvas.delete('all')
        _pill(self.canvas, 0, 0, width, 32, RAISED, 'track')
        _pill(self.canvas, self.position * cell + 2, 2,
              (self.position + 1) * cell - 2, 30, ACCENT, 'selection')
        for index, name in enumerate(self.values):
            self.canvas.create_text((index + .5) * cell, 16, text=name,
                                    fill=INK if index == self._index() else MUTED,
                                    font=(FONT, 9, 'bold'))

    def _click(self, event):
        self.focus_set()
        self._choose(min(len(self.values) - 1, int(event.x * len(self.values) / max(1, self.canvas.winfo_width()))))

    def _choose(self, index):
        self.variable.set(list(self.values.values())[index])
        if self.on_change:
            self.on_change(self.variable.get())
        self.event_generate('<<ComboboxSelected>>')


class BooleanToggle(tk.Canvas):
    def __init__(self, parent, variable, command=None):
        super().__init__(parent, width=44, height=26, bg=parent.cget('bg'), bd=0,
                         highlightthickness=0, cursor='hand2', takefocus=True)
        self.variable, self.command = variable, command
        self.trace = variable.trace_add('write', lambda *_: self._paint())
        self.bind('<Button-1>', self._toggle)
        self.bind('<space>', self._toggle)
        self.bind('<Return>', self._toggle)
        self.bind('<Destroy>', self._destroy_trace)
        self._paint()

    def _destroy_trace(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self.trace)

    def _paint(self):
        self.delete('all')
        on = bool(self.variable.get())
        _pill(self, 0, 1, 44, 25, ACCENT if on else RAISED, 'track')
        left = 22 if on else 3
        self.create_oval(left, 4, left + 18, 22, fill=TEXT, outline='')

    def _toggle(self, _=None):
        self.focus_set()
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()
        return 'break'


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.popup, self.job = widget, text, None, None
        widget.bind('<Enter>', self._enter, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')
        widget.bind('<Destroy>', self.hide, add='+')

    def _enter(self, _):
        self.job = self.widget.after(450, self._show)

    def _show(self):
        self.job = None
        if not self.text or not self.widget.winfo_exists():
            return
        self.popup = tk.Toplevel(self.widget)
        self.popup.withdraw()
        self.popup.configure(bg=SURFACE)
        self.popup.overrideredirect(True)
        self.popup.attributes('-topmost', True)
        label(self.popup, self.text, TEXT, 9, wraplength=280, justify='left', padx=9, pady=6).pack()
        self.popup.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.popup.winfo_screenwidth() - self.popup.winfo_reqwidth() - 8)
        y = min(self.widget.winfo_rooty() + self.widget.winfo_height() + 4,
                self.popup.winfo_screenheight() - self.popup.winfo_reqheight() - 8)
        self.popup.geometry(f'+{max(0, x)}+{max(0, y)}')
        self.popup.deiconify()
        from .windows import prepare_popup
        prepare_popup(self.popup)

    def hide(self, _=None):
        if self.job is not None:
            try:
                self.widget.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.popup is not None:
            try:
                self.popup.destroy()
            except tk.TclError:
                pass
            self.popup = None

# All V2 surfaces share the pixel-font, rounded handoff tooltip.
from .ui_drawing import Hint as Tooltip
