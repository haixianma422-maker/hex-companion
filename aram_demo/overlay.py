import tkinter as tk
from .models import augment_label

COLORS = ['#f3bd64', '#ee8e96', '#bb9cf7', '#7aaef5', '#67cab6', '#9aa7b9']


class Overlay:
    def __init__(self, root, on_hide=None):
        self.root = root
        self.window = None
        self.on_hide = on_hide or (lambda: None)

    def show(self, matches, champion_name, augments=None, mapping=None, simulated=False):
        self.hide()
        index = {a.id: a for a in augments or []}
        win = self.window = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        win.attributes('-alpha', 0.97)
        win.configure(bg='#e4ba75')
        width, height = min(930, win.winfo_screenwidth() - 60), 210
        x = (win.winfo_screenwidth() - width) // 2
        y = max(30, int(win.winfo_screenheight() * 0.52))
        win.geometry(f'{width}x{height}+{x}+{y}')
        inner = tk.Frame(win, bg='#121d30')
        inner.pack(fill='both', expand=True, padx=1, pady=1)
        bar = tk.Frame(inner, bg='#121d30')
        bar.pack(fill='x', padx=18, pady=(10, 4))
        title = f'{champion_name}  /  ' + ('模拟三卡' if simulated else '海克斯评级')
        tk.Label(bar, text=title, bg='#121d30', fg='#e7edf5', font=('Microsoft YaHei UI', 11, 'bold')).pack(side='left')
        tk.Button(bar, text='关闭 ×', command=self.hide, bg='#25334a', fg='white', bd=0, padx=10).pack(side='right')
        origin = [0, 0]
        def begin(event):
            origin[:] = [event.x_root - win.winfo_x(), event.y_root - win.winfo_y()]
        def drag(event):
            win.geometry(f'+{event.x_root - origin[0]}+{event.y_root - origin[1]}')
        for widget in (bar, *bar.winfo_children()[:1]):
            widget.bind('<ButtonPress-1>', begin)
            widget.bind('<B1-Motion>', drag)
        cards = tk.Frame(inner, bg='#121d30')
        cards.pack(fill='both', expand=True, padx=12, pady=6)
        for match in matches:
            card = tk.Frame(cards, bg='#1b2940')
            card.pack(side='left', fill='both', expand=True, padx=5)
            augment = index.get(match.augment_id)
            color = COLORS[min(augment.tier or 0, 5)] if augment else '#94a4b9'
            grade = augment_label(augment.tier, mapping) if augment else '待确认' if match.candidates else '未识别'
            tk.Label(card, text=('左侧', '中间', '右侧')[match.slot], bg='#1b2940', fg='#91a1b8', font=('Microsoft YaHei UI', 9)).pack(pady=(5, 0))
            tk.Label(card, text=grade, bg='#1b2940', fg=color, font=('Microsoft YaHei UI', 25, 'bold')).pack()
            tk.Label(card, text=augment.name if augment else match.text or '请手动选择', bg='#1b2940', fg='#e7edf5', wraplength=250, font=('Microsoft YaHei UI', 11)).pack(pady=(0, 5))
        tk.Label(inner, text='OP.GG · 原始档位越小越靠前  |  拖动标题栏移动  |  Esc 关闭', bg='#121d30', fg='#91a1b8', font=('Microsoft YaHei UI', 9)).pack(pady=(0, 8))
        win.bind('<Escape>', lambda event: self.hide())

    def hide(self):
        if self.window is not None:
            self.window.destroy()
            self.window = None
        self.on_hide()
