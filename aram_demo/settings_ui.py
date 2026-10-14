"""The 480×684 logical-pixel settings surface and its existing save boundary."""
import os
import tkinter as tk
from tkinter import filedialog

from .cache import SOURCE_NAMES
from .hotkeys import DEFAULT_HOTKEYS, normalize_bindings, parse_hotkey
from .lcu import validate_install_path
from .motion import Motion
from .recognition import DEFAULT_REGIONS, Recognizer
from .theme import ACCENT, BG, INK, LILAC, LINE, MUTED, RAISED, SURFACE, TEXT
from .ui_drawing import Artboard, Hint as Tooltip, position_window, ui_scale, work_area
from .ui_widgets import PixelButton, PixelChoice, PixelEntry, PixelToggle, SourceSwitch

ERROR = '#FFB7BE'
FOOTER = '#211C2D'
TRANSPARENT = '#010203'


class SettingsPage(tk.Frame):
    """T09 viewport; only the middle scrolls on a smaller desktop."""
    def __init__(self, parent, scale, viewport_height, painter):
        super().__init__(parent, bg=BG, bd=0, highlightthickness=0)
        self.scale, self.painter, self.error = scale, painter, ''
        self.viewport_height = viewport_height
        self.canvas = tk.Canvas(self, bg=BG, bd=0, highlightthickness=0,
                                width=round(440 * scale), height=round(viewport_height * scale),
                                yscrollincrement=max(1, round(20 * scale)))
        self.canvas.pack(fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=BG, bd=0, width=round(440 * scale),
                             height=round(488 * scale))
        self.item = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.content = tk.Frame(self.body, bg=BG, bd=0, width=round(440 * scale),
                                height=round(488 * scale))
        self.content.place(x=0, y=0)
        self.back = tk.Canvas(self.content, bg=BG, bd=0, highlightthickness=0)
        self.back.place(x=0, y=0, relwidth=1, relheight=1)
        self.error_canvas = tk.Canvas(self.body, bg=BG, bd=0, highlightthickness=0)
        self.error_hint = Tooltip(self.error_canvas, '')
        self.scroll = tk.Canvas(parent, bg=BG, bd=0, highlightthickness=0,
                                width=round(4 * scale), height=round(viewport_height * scale))
        self.canvas.configure(yscrollcommand=self._scroll_changed)
        self.scroll.bind('<Button-1>', self._scroll_to)
        self.scroll.bind('<B1-Motion>', self._scroll_to)
        self._photo = self._error_photo = self._scroll_photo = None
        self.repaint()
        self._sync()

    def repaint(self):
        board = Artboard(440, 488, scale=self.scale, bg=BG)
        self.painter(board)
        self._photo = board.photo(self.back)
        self.back.delete('all')
        self.back.create_image(0, 0, image=self._photo, anchor='nw')

    def set_error(self, message):
        self.error = message
        self.error_hint.text = message
        offset = 32 if message else 0
        self.body.configure(height=round((488 + offset) * self.scale))
        self.content.place_configure(y=round(offset * self.scale))
        if message:
            self.error_canvas.place(x=0, y=0, width=round(440 * self.scale), height=round(32 * self.scale))
            board = Artboard(440, 32, scale=self.scale, bg=BG)
            board.rect((0, 0, 440, 30), SURFACE, radius=8)
            board.text((10, 3, 420, 24), message, size=12, color=ERROR)
            self._error_photo = board.photo(self.error_canvas)
            self.error_canvas.delete('all')
            self.error_canvas.create_image(0, 0, image=self._error_photo, anchor='nw')
        else:
            self.error_canvas.place_forget()
        self._sync()

    def _sync(self):
        height = (488 + (32 if self.error else 0)) * self.scale
        self.canvas.configure(scrollregion=(0, 0, round(440 * self.scale), round(height)))
        self.canvas.update_idletasks()
        if height > self.viewport_height * self.scale + 1:
            self.scroll.place(x=round(468 * self.scale), y=round(124 * self.scale),
                              width=max(1, round(4 * self.scale)), height=round(self.viewport_height * self.scale))
        else:
            self.scroll.place_forget()

    def _scroll_changed(self, first, last):
        height = self.viewport_height
        board = Artboard(4, height, scale=self.scale, bg=BG)
        first, last = float(first), float(last)
        # 45% muted on the dark track, precomposited for a native opaque canvas.
        board.rect((0, first * height, 4, max(8, (last - first) * height)), '#60576F', radius=2)
        self._scroll_photo = board.photo(self.scroll)
        self.scroll.delete('all')
        self.scroll.create_image(0, 0, image=self._scroll_photo, anchor='nw')

    def _scroll_to(self, event):
        first, last = self.canvas.yview()
        self.canvas.yview_moveto(event.y / max(1, self.scroll.winfo_height()) - (last - first) / 2)

    def ensure_visible(self, widget):
        self.update_idletasks()
        if isinstance(getattr(widget, 'master', None), PixelEntry):
            widget = widget.master
        top = widget.winfo_rooty() - self.body.winfo_rooty()
        bottom = top + widget.winfo_height()
        height = (488 + (32 if self.error else 0)) * self.scale
        first, _ = self.canvas.yview()
        visible_top = first * height
        visible_height = self.canvas.winfo_height()
        if top < visible_top:
            self.canvas.yview_moveto(max(0, top - 4 * self.scale) / height)
        elif bottom > visible_top + visible_height:
            self.canvas.yview_moveto(max(0, bottom - visible_height + 4 * self.scale) / height)

    def bind_inputs(self):
        def wheel(event):
            if 488 + (32 if self.error else 0) > self.viewport_height:
                self.canvas.yview_scroll(-int(event.delta / 120), 'units')
            return 'break'
        def visit(widget):
            widget.bind('<MouseWheel>', wheel, add='+')
            widget.bind('<FocusIn>', lambda event: self.ensure_visible(event.widget), add='+')
            for child in widget.winfo_children():
                visit(child)
        visit(self.body)


class SettingsTabs(tk.Canvas):
    """T05–T08 and a small Notebook-compatible selection interface."""
    def __init__(self, parent, pages, scale, animations):
        super().__init__(parent, bg=BG, bd=0, highlightthickness=0,
                         width=round(480 * scale), height=round(56 * scale),
                         takefocus=True, cursor='hand2')
        self.pages, self.scale = pages, scale
        self.current, self.position, self._photo = 0, 22., None
        self.motion = Motion(self, animations)
        self.bind('<Button-1>', self._click)
        self.bind('<Left>', lambda _: self._step(-1))
        self.bind('<Right>', lambda _: self._step(1))
        self.bind('<FocusIn>', lambda _: self.paint())
        self.bind('<FocusOut>', lambda _: self.paint())
        self.bind('<Tab>', self._enter_page)
        self.select(0)

    def index(self, value):
        return value if isinstance(value, int) else self.pages.index(value)

    def select(self, value=None):
        if value is None:
            return self.pages[self.current]
        self.current = self.index(value)
        for index, page in enumerate(self.pages):
            if index == self.current:
                page.place(x=round(20 * self.scale), y=round(124 * self.scale),
                           width=round(440 * self.scale), height=round(page.viewport_height * self.scale))
                page._sync()
            else:
                page.place_forget()
                page.scroll.place_forget()
        self.motion.animate('tab', self.position, 22 + self.current * 147, self._move, 140)
        self.event_generate('<<NotebookTabChanged>>')

    def _move(self, position):
        self.position = position
        self.paint()

    def paint(self):
        board = Artboard(480, 56, scale=self.scale, bg=BG)
        board.rect((0, 0, 480, 56), LILAC, radius=12)
        board.rect((self.position, 9, 142, 38), BG, radius=19)
        for index, text in enumerate(('常用设置', '快捷键', '识别与连接')):
            board.text((22 + index * 147, 9, 142, 38), text, size=16,
                       bold=True, color=TEXT if index == self.current else INK, align='center')
        if self.focus_get() is self:
            board.rect((22 + self.current * 147, 9, 142, 38), None, radius=19,
                       outline=ACCENT, stroke=2)
        self._photo = board.photo(self)
        self.delete('all')
        self.create_image(0, 0, image=self._photo, anchor='nw')

    def _click(self, event):
        self.focus_set()
        self.select(min(2, max(0, round((event.x / self.scale - 93) / 147))))

    def _step(self, direction):
        self.select((self.current + direction) % 3)
        return 'break'

    def _enter_page(self, _):
        widget = self.pages[self.current].first_field
        widget.focus_set()
        return 'break'


def show_settings(app, slot=None):
    def focus_manual():
        if isinstance(slot, int) and 0 <= slot < 3:
            app._settings_notebook.select(app._settings_common)
            app._manual_widgets[slot].focus_set()
            app._settings_common.ensure_visible(app._manual_widgets[slot])

    if app.dialog is not None and app.dialog.winfo_exists():
        app.dialog.lift()
        focus_manual()
        return

    dialog = app.dialog = tk.Toplevel(app.root)
    dialog.withdraw()
    app.hotkeys.set_paused(True)
    dialog.title('海克斯随行 · 设置')
    dialog.configure(bg=TRANSPARENT if os.name == 'nt' else BG)
    dialog.overrideredirect(True)
    dialog.attributes('-topmost', True)
    if os.name == 'nt':
        dialog.attributes('-transparentcolor', TRANSPARENT)
    dialog.resizable(False, False)
    dialog.bind('<Escape>', lambda _: dialog.destroy())
    scale = ui_scale(app.root)
    dialog.design_scale = scale
    from .window_shadow import attach_shadow
    dialog.shadow = attach_shadow(dialog, scale, 16)
    left, top, right, bottom = work_area(app.root)
    width, height = round(480 * scale), min(round(684 * scale), bottom - top)
    logical_height = height / scale
    viewport_height = max(1, logical_height - 196)
    window_x, window_y = max(left, left + (right - left - width) // 2), top + (bottom - top - height) // 2
    position_window(dialog, window_x, window_y, width, height)
    shell = tk.Canvas(dialog, bg=TRANSPARENT if os.name == 'nt' else BG, bd=0, highlightthickness=0)
    shell.place(x=0, y=0, width=width, height=height)
    board = Artboard(480, logical_height, scale=scale,
                     bg=TRANSPARENT if os.name == 'nt' else BG)
    board.rect((0, 0, 480, logical_height), BG, radius=16)
    board.brand((20, 15, 24, 24))
    board.text((56, 12, 330, 28), '随行设置', size=18, bold=True)
    footer_y = logical_height - 66
    board.rect((0, footer_y, 480, 66), FOOTER, radius=16)
    board.rect((0, footer_y, 480, 20), FOOTER, radius=0)
    board.line((0, footer_y, 480, footer_y), LINE, width=1)
    shell._photo = board.photo(shell)
    shell.create_image(0, 0, image=shell._photo, anchor='nw')
    drag = {}
    def begin_drag(event):
        if event.y < 52 * scale:
            drag['offset'] = event.x_root - dialog.winfo_x(), event.y_root - dialog.winfo_y()
    def move_dialog(event):
        if 'offset' in drag:
            dx, dy = drag['offset']
            px = max(left, min(event.x_root - dx, right - width))
            py = max(top, min(event.y_root - dy, bottom - height))
            position_window(dialog, px, py, width, height)
    shell.bind('<ButtonPress-1>', begin_drag)
    shell.bind('<B1-Motion>', move_dialog)
    shell.bind('<ButtonRelease-1>', lambda _: drag.clear())
    close = PixelButton(dialog, '', dialog.destroy, 28, 28, kind='ghost', icon='close', scale=scale)
    close.place_logical(435, 10)
    Tooltip(close, '关闭设置')

    source_var = app.source_var = tk.StringVar(value=app.store.source_name)
    auto = tk.BooleanVar(value=app.auto)
    animations = tk.BooleanVar(value=app.settings.get('animations', True))
    choices, regions, shortcut_entries, region_entries = [], [], {}, []
    shortcut_error = tk.StringVar()
    initial_path = app.settings.get('install_path', '')
    install_path = tk.StringVar(value=initial_path)
    opened_revision, opened_source = app.state.revision, app.store

    def local(box):
        x, y, w, h = box
        return x - 20, y - 124, w, h

    def text(board, box, value, size=14, bold=False, color=TEXT, **kwargs):
        board.text(local(box), value, size=size, bold=bold, color=color, **kwargs)

    def divider(board, y):
        board.line((4, y - 124, 436, y - 124), LINE, width=1)

    def paint_common(board):
        text(board, (24, 129, 166, 26), '数据来源', 18, True)
        text(board, (208, 173, 248, 18), '101：S–C · OP.GG：S–E', 13, color=MUTED)
        text(board, (208, 192, 248, 34), '召唤师技能缺失时使用 OP.GG 补充', 12,
             color=MUTED, lines=2, line_height=17)
        for y in (228, 302, 376):
            divider(board, y)
        for title, detail, y in (('自动识别海克斯', '局内选择海克斯时自动识别', 241),
                                  ('动效', '展开、切换与结果更新', 315)):
            text(board, (24, y, 350, 26), title, 18, True)
            text(board, (24, y + 29, 350, 18), detail, 13, color=MUTED)
        text(board, (24, 390, 210, 26), '手动修正', 18, True)
        text(board, (298, 394, 158, 20), '仅当前英雄生效', 11, color=MUTED, align='right')
        for side, y in zip(('左侧', '中间', '右侧'), (438, 492, 546)):
            text(board, (24, y, 54, 24), side)
        text(board, (24, 590, 432, 18), f'{app.hotkeys.bindings["scan"]} 恢复自动识别', 12, color=MUTED)

    def paint_shortcuts(board):
        text(board, (24, 130, 432, 26), '全局快捷键', 18, True)
        text(board, (24, 166, 432, 18), '点击输入框后按下组合键', 13, color=MUTED)
        for title, y in zip(('重新识别', '刷新资料', '展开 / 收起'), (220, 282, 344)):
            text(board, (24, y, 158, 26), title, 17, True)
        text(board, (24, 387, 432, 22), shortcut_error.get(), 12, color=ERROR)
        divider(board, 416)
        board.icon('info', local((24, 448, 16, 16)), MUTED)
        board.icon('info', local((24, 488, 16, 16)), MUTED)
        text(board, (56, 445, 400, 22), 'Esc 将面板收起为浮标', 13, color=MUTED)
        text(board, (56, 485, 400, 36), '设置窗口打开时暂停全局快捷键', 13,
             color=MUTED, lines=2, line_height=18)

    def connection():
        raw = app.connection_text.get()
        phase = getattr(app.state, 'phase', 'Disconnected')
        if phase == 'Disconnected':
            return raw.splitlines()[0] or '等待客户端连接', MUTED
        if phase in ('Error', 'Failed'):
            return raw.splitlines()[0], ERROR
        return raw.splitlines()[0] or phase, ACCENT

    def paint_advanced(board):
        text(board, (24, 130, 180, 26), '标题识别区域', 18, True)
        text(board, (210, 134, 246, 20), '相对游戏窗口，坐标范围 0–1', 11,
             color=MUTED, align='right')
        board.rect(local((24, 172, 432, 146)), '#14121C', radius=10)
        for index, x in enumerate((32, 172, 312)):
            board.rect(local((x, 180, 128, 128)), '#252337', radius=6)
            # Fixed game-card composition, distinct from normalized OCR inputs.
            board.rect(local((x + 6, 204, 116, 98)), '#1C1A2B', radius=5)
            text(board, (x + 48, 182, 32, 18), ('左', '中', '右')[index], 13, color=MUTED, align='center')
            bx, by = x + 13, 211
            for sx in range(0, 102, 7):
                for yy in (by, by + 20):
                    board.line((bx + sx - 20, yy - 124, bx + min(sx + 4, 102) - 20, yy - 124), LILAC, width=1.5)
            for sy in range(0, 20, 7):
                for xx in (bx, bx + 102):
                    board.line((xx - 20, by + sy - 124, xx - 20, by + min(sy + 4, 20) - 124), LILAC, width=1.5)
            path = app.visual_assets.path('augment', (1401, 1214, 1133)[index])
            if path:
                board.image_at(local((x + 41, 241, 46, 46)), path, fit='contain', radius=0)
            else:
                board.icon('question', local((x + 41, 241, 46, 46)), MUTED)
        text(board, (24, 303, 432, 15), '区域示意 · 非实时画面', 10, color=MUTED, align='right')
        for name, x in zip(('x1', 'y1', 'x2', 'y2'), (84, 180, 276, 372)):
            text(board, (x, 338, 84, 18), name, 12, color=MUTED, align='center')
        for side, y in zip(('左侧', '中间', '右侧'), (368, 406, 444)):
            text(board, (24, y, 52, 20), side)
        divider(board, 514)
        text(board, (24, 530, 142, 26), '客户端连接', 18, True)
        status, color = connection()
        board.rect(local((168, 538, 8, 8)), color, radius=4)
        text(board, (184, 532, 250, 22), status, 13, color=color)

    common = app._settings_common = SettingsPage(dialog, scale, viewport_height, paint_common)
    shortcuts = SettingsPage(dialog, scale, viewport_height, paint_shortcuts)
    advanced = SettingsPage(dialog, scale, viewport_height, paint_advanced)
    notebook = app._settings_notebook = SettingsTabs(dialog, (common, shortcuts, advanced), scale, animations.get())
    notebook.place(x=0, y=round(52 * scale))

    def place(widget, x, y):
        widget.place_logical(x - 20, y - 124)
        return widget

    app.source_choice = place(SourceSwitch(common.content, variable=source_var,
        values={'OP.GG': SOURCE_NAMES['opgg'], '101': SOURCE_NAMES['qq101']}, width=248, height=38,
        separate=True, scale=scale), 208, 126)
    common.first_field = app.source_choice
    toggles = [place(PixelToggle(common.content, variable=var, scale=scale), 402, y)
               for var, y in ((auto, 248), (animations, 322))]
    app._manual_widgets = []
    def augment_icon(name):
        augment = next((item for item in app.augments if item.name == name), None)
        return app.visual_assets.path('augment', augment.id) if augment else None
    for index, y in enumerate((428, 482, 536)):
        current = next((a.name for a in app.augments
                        if any(m.slot == index and m.augment_id == a.id for m in app.matches)), '请选择')
        variable = tk.StringVar(value=current)
        choices.append(variable)
        choice = place(PixelChoice(common.content, variable=variable,
            values=['请选择'] + [a.name for a in app.augments], width=362, height=44,
            icon_lookup=augment_icon, scale=scale), 94, y)
        app._manual_widgets.append(choice)
    initial_choices = [variable.get() for variable in choices]

    app.hotkey_vars = {}
    for action, y in zip(DEFAULT_HOTKEYS, (210, 272, 334)):
        variable = app.hotkey_vars[action] = tk.StringVar(value=app.hotkeys.bindings[action])
        field = place(PixelEntry(shortcuts.content, variable=variable, width=264,
                                 height=46, font_size=18, scale=scale, inset=14), 192, y)
        shortcut_entries[action] = field
        field.error_hint = Tooltip(field.entry, '点击输入框后按下组合键')
        def capture(event, value=variable):
            if event.keysym in ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R'):
                return 'break'
            modifiers = [name for mask, name in ((4, 'Ctrl'), (0x20000, 'Alt'), (1, 'Shift')) if event.state & mask]
            if (event.keysym.startswith('F') and event.keysym[1:].isdigit()) or (modifiers and len(event.keysym) == 1):
                value.set('+'.join(modifiers + [event.keysym.upper()]))
                return 'break'
        field.entry.bind('<KeyPress>', capture)
    shortcuts.first_field = shortcut_entries['scan']
    def reset_hotkeys():
        for action, value in DEFAULT_HOTKEYS.items():
            app.hotkey_vars[action].set(value)
            shortcut_entries[action].set_error(False)
            shortcut_entries[action].error_hint.text = '点击输入框后按下组合键'
        shortcut_error.set('')
        shortcuts.repaint()
    restore_keys = place(PixelButton(shortcuts.content, '恢复默认快捷键', reset_hotkeys,
        220, 24, kind='ghost', font_size=13, bold=False, scale=scale,
        align='left', color=MUTED, underline=True), 24, 550)
    Tooltip(restore_keys, '恢复默认后，保存并应用才会生效')

    for row, (region, y) in enumerate(zip(app.recognizer.regions, (362, 400, 438))):
        variables, fields = [], []
        for value, x in zip(region, (84, 180, 276, 372)):
            variable = tk.StringVar(value=str(value))
            field = place(PixelEntry(advanced.content, variable=variable, width=84,
                height=32, font_size=13, scale=scale, center=True, radius=8), x, y)
            variables.append(variable)
            fields.append(field)
        regions.append(variables)
        region_entries.append(fields)
    advanced.first_field = region_entries[0][0]
    def reset_regions():
        for variables, fields, region in zip(regions, region_entries, DEFAULT_REGIONS):
            for variable, field, value in zip(variables, fields, region):
                variable.set(str(value))
                field.set_error(False)
        advanced.set_error('')
    place(PixelButton(advanced.content, '恢复 16:9 预设', reset_regions,
        220, 22, kind='ghost', font_size=12, bold=False, scale=scale,
        align='left', color=MUTED, underline=True), 24, 480)
    path_entry = place(PixelEntry(advanced.content, variable=install_path,
        width=296, height=38, font_size=13, scale=scale, fill=RAISED), 24, 568)
    def install():
        path = filedialog.askdirectory(parent=dialog, title='选择英雄联盟安装目录')
        if path:
            install_path.set(path)
            path_entry.set_error(False)
    place(PixelButton(advanced.content, '选择安装目录', install, 122, 38,
        kind='outline', font_size=13, bold=False, radius=14, scale=scale), 334, 568)

    def update_icons(*_):
        for choice in app._manual_widgets:
            choice.refresh()
        advanced.repaint()
    app._settings_refresh_icons = update_icons
    def update_motion(*_):
        enabled = animations.get()
        notebook.motion.set_enabled(enabled)
        def visit(widget):
            if hasattr(widget, 'set_motion'):
                widget.set_motion(enabled)
            for child in widget.winfo_children():
                visit(child)
        visit(dialog)
    animations.trace_add('write', update_motion)
    update_motion()
    connection_trace = app.connection_text.trace_add('write', lambda *_: advanced.repaint())
    def destroyed(event):
        if event.widget is dialog:
            app.hotkeys.set_paused(False)
            app._settings_refresh_icons = None
            app.connection_text.trace_remove('write', connection_trace)
    dialog.bind('<Destroy>', destroyed, add='+')

    def focus_error(page, field, reason):
        page.set_error(reason)
        notebook.select(page)
        field.set_error(True)
        field.focus_set()
        page.ensure_visible(field)

    def save():
        for page in (common, shortcuts, advanced):
            page.set_error('')
        for field in (*shortcut_entries.values(), path_entry,
                      *(field for fields in region_entries for field in fields)):
            field.set_error(False)
        shortcut_error.set('')
        shortcuts.repaint()
        selected_source = next((key for key, name in SOURCE_NAMES.items() if name == source_var.get()), None)
        if selected_source is None:
            common.set_error('请选择 OP.GG 或 101 数据站')
            notebook.select(common)
            app.source_choice.focus_set()
            return
        source_changed = selected_source != app.store.source
        parsed_regions = []
        for index, variables in enumerate(regions):
            try:
                region = tuple(float(variable.get().strip()) for variable in variables)
                x1, y1, x2, y2 = region
                if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                    raise ValueError('坐标需在 0–1 内，且 x1<x2、y1<y2')
            except ValueError as exc:
                for field in region_entries[index]:
                    field.set_error(True)
                focus_error(advanced, region_entries[index][0], ('左侧', '中间', '右侧')[index] + '区域：' + str(exc))
                return
            parsed_regions.append(region)
        recognizer = Recognizer(parsed_regions)
        path_changed = install_path.get() != initial_path
        if path_changed:
            try:
                validate_install_path(install_path.get())
            except ValueError as exc:
                focus_error(advanced, path_entry, str(exc))
                return
        old_bindings = dict(app.hotkeys.bindings)
        try:
            bindings = normalize_bindings({key: variable.get() for key, variable in app.hotkey_vars.items()})
            app.hotkeys.configure(bindings)
        except ValueError as exc:
            shortcut_error.set(str(exc))
            shortcuts.repaint()
            notebook.select(shortcuts)
            invalid = []
            parsed = {}
            for action, variable in app.hotkey_vars.items():
                try:
                    parsed[action] = parse_hotkey(variable.get())[0]
                except ValueError:
                    invalid.append(action)
            duplicates = [action for action, value in parsed.items() if list(parsed.values()).count(value) > 1]
            occupied = [action for action, value in parsed.items() if value in str(exc)]
            invalid = invalid or duplicates or occupied or list(shortcut_entries)
            for action in invalid:
                shortcut_entries[action].set_error(True)
                shortcut_entries[action].error_hint.text = str(exc)
            shortcut_entries[invalid[0]].focus_set()
            shortcuts.ensure_visible(shortcut_entries[invalid[0]])
            return
        settings = dict(app.settings, regions=recognizer.regions, auto_recognize=auto.get(),
                        animations=animations.get(), hotkeys=bindings, data_source=selected_source)
        if path_changed:
            settings['install_path'] = install_path.get()
        try:
            app.store._write('settings.json', settings)
        except OSError as exc:
            try:
                app.hotkeys.configure(old_bindings)
            except ValueError as rollback_error:
                common.set_error(f'设置未能保存：{exc}；快捷键恢复失败：{rollback_error}')
            else:
                common.set_error('设置未能保存：' + str(exc))
            notebook.select(common)
            common.canvas.yview_moveto(0)
            return
        app.settings, app.recognizer, app.auto = settings, recognizer, auto.get()
        app.panel.set_hotkeys(bindings)
        app.panel.set_motion(animations.get())
        app.bubble.set_motion(animations.get())
        app.bubble.set_hotkeys(bindings)
        app.ocr_epoch += 1
        selected_choices = [variable.get().strip() if variable.get() != '请选择' else '' for variable in choices]
        opened_choices = [value if value != '请选择' else '' for value in initial_choices]
        if (not source_changed and app.store is opened_source and
                selected_choices != opened_choices and opened_revision == app.state.revision):
            app.apply_manual(selected_choices)
        dialog.destroy()
        if source_changed:
            app.change_source(selected_source)
        app.status = app.cache_status()
        app.present()
        if path_changed:
            app.refresh()

    cancel = PixelButton(dialog, '取消', dialog.destroy, 184, 44, kind='outline',
                          font_size=16, bold=True, radius=22, scale=scale,
                          background=FOOTER, outline_color='#645A7A')
    cancel.place_logical(24, footer_y + 10)
    apply = PixelButton(dialog, '保存并应用', save, 232, 44, font_size=16,
                         scale=scale, background=FOOTER)
    apply.place_logical(224, footer_y + 10)
    update_motion()
    for page in (common, shortcuts, advanced):
        page.bind_inputs()
    dialog.deiconify()
    position_window(dialog, window_x, window_y, width, height)
    dialog.lift()
    if isinstance(slot, int) and 0 <= slot < 3:
        dialog.after_idle(focus_manual)
