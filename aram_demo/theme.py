"""Shared desktop tokens and lightweight, local-only rounded surfaces."""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

BG = '#010a13'
SURFACE = '#091428'
RAISED = '#0a323c'
LINE = '#233442'
TEXT = '#f0e6d2'
MUTED = '#a09b8c'
ACCENT = '#0ac8b9'
INK = BG
GOLD = '#c8aa6e'
TIER_BG = '#0a323c'
NEUTRAL_BG = '#1b2430'
FONT = 'Microsoft YaHei UI'
GRADES = [GOLD, ACCENT, '#a0c9e8', '#c0a8e0', '#b6b0a1', '#9aa8ba']
GRADE_BACKGROUNDS = ['#302619', TIER_BG, '#10243b', '#211b30', '#25231f', NEUTRAL_BG]


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
    base, hover = (RAISED, '#103f49') if primary else (SURFACE, '#12283d')
    fg = GOLD if primary else TEXT
    surface = Card(parent, color=base, padding=5, radius=12)
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
        photo = ImageTk.PhotoImage(image.resize(size, Image.Resampling.LANCZOS), master=self)
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
    style.configure('Hex.TNotebook.Tab', background=BG, foreground=MUTED,
                    padding=(14, 8), borderwidth=0, font=(FONT, 10),
                    lightcolor=BG, darkcolor=BG, bordercolor=BG, focuscolor=ACCENT)
    style.map('Hex.TNotebook.Tab', background=[('selected', RAISED)],
              foreground=[('selected', ACCENT), ('active', TEXT)])
    for name in ('Hex.TEntry', 'Hex.TCombobox'):
        style.configure(name, fieldbackground=BG, foreground=TEXT, background=RAISED,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                        arrowcolor=MUTED, padding=6, insertcolor=TEXT)
        style.map(name, bordercolor=[('focus', ACCENT)],
                  fieldbackground=[('readonly', BG)], foreground=[('readonly', TEXT)])
    root.option_add('*TCombobox*Listbox.background', SURFACE)
    root.option_add('*TCombobox*Listbox.foreground', TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground', RAISED)
    root.option_add('*TCombobox*Listbox.selectForeground', ACCENT)
    root.option_add('*TCombobox*Listbox.font', (FONT, 10))
