"""Hidden background app, one mode-aware panel, optional small settings dialog."""
import queue
import threading
import time
import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

from .companion_state import MAYHEM_QUEUES, PLAYING, SessionTracker
from .bubble import CompanionBubble
from .hotkeys import Hotkeys
from .lcu import ClientState, LCUClient, live_champion_id, validate_install_path
from .models import Augment
from .panel import CompanionPanel
from .theme import ACCENT, BG, FONT, MUTED, TEXT, Card, ScrollArea, button, label
from .recognition import DEFAULT_REGIONS, Recognizer, match_slots
from .windows import LeagueWindow, find_league_window, foreground_is_ours

AUTO_SCAN_INTERVAL = .25
IDLE_SCAN_INTERVAL = 1.5
WINDOW_CHECK_INTERVAL = .5
UI_TICK_MS = 150


class CompanionApp:
    def __init__(self, root, store, preview=False, services=True):
        self.root, self.store, self.preview, self.services = root, store, preview, services
        root.withdraw()
        root.title('海克斯随行 · 后台')
        self.closed = False
        self.tracker = SessionTracker()
        self.state = self.tracker.state
        self.connection_text = tk.StringVar(value='等待客户端连接')
        self.champions = {c.id: c for c in store.champions()}
        self.settings = store.read('settings.json') or {}
        try:
            self.recognizer = Recognizer(self.settings.get('regions'))
        except ValueError:
            self.recognizer = Recognizer()
        self.auto = self.settings.get('auto_recognize', True)
        self.events = queue.Queue()
        self.data, self.augments, self.matches = None, [], []
        self.status = '等待海克斯大乱斗'
        self.collapsed = self.scanning = self.poll_pending = False
        self.ocr_epoch = 0
        self.manual_override = False
        self.index_pending = self.index_requested = False
        self.last_scan = 0
        self.scan_interval = IDLE_SCAN_INTERVAL
        self.missing_frames = 0
        self.last_window_check = float('-inf')
        self.fetching = set()
        self.dialog = None
        self.anchor = None
        self.tray = None
        self.panel = CompanionPanel(root, self.scan, self.show_settings, self.hide,
                                    self.preview_next if preview else None)
        self.bubble = CompanionBubble(root, self.expand)
        self.hotkeys = Hotkeys(lambda: self.dispatch(self.scan), lambda: self.dispatch(self.refresh),
                               lambda: self.dispatch(self.hide))
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        if services:
            from .tray import Tray
            self.tray = Tray(self.dispatch, self.toggle, self.show_settings, self.refresh, self.close, self.tray_failed)
            self.tray.start()
            self.hotkeys.start()
            root.after(80, self._pump)
            root.after(500, self._tick)
            if not preview:
                root.after(100, self.poll)

    def dispatch(self, callback):
        self.events.put(('call', callback))

    def ocr_ticket(self):
        return self.state.revision, self.ocr_epoch

    def deliver(self, ticket, callback, result, error):
        if self.closed or (ticket is not None and ticket != self.ocr_ticket()):
            return
        if error:
            self.status = '操作未完成，保留缓存 · ' + error
            self.present()
        else:
            callback(result)

    def background(self, job, callback, ticket=None, done=None):
        def worker():
            try:
                result, error = job(), None
            except Exception as exc:
                result, error = None, str(exc)[:160]
            self.events.put(('result', ticket, callback, result, error, done))
        threading.Thread(target=worker, daemon=True).start()

    def _pump(self):
        if self.closed:
            return
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'call':
                    event[1]()
                else:
                    _, ticket, callback, result, error, done = event
                    if done:
                        done()
                    self.deliver(ticket, callback, result, error)
        except queue.Empty:
            pass
        if not self.closed:
            self.root.after(80, self._pump)

    def tray_failed(self, detail):
        if not self.closed:
            messagebox.showerror('海克斯随行', '系统托盘启动失败，程序将退出。\n' + detail, parent=self.root)
            self.close()

    def poll(self):
        if self.closed:
            return
        if not self.poll_pending and not self.preview:
            self.poll_pending = True
            install_path, champions, known_queue = self.settings.get('install_path'), list(self.champions.values()), self.state.queue_id
            def read():
                raw = LCUClient(install_path).read_state()
                if not raw.champion_id and raw.phase in PLAYING and (raw.queue_id in MAYHEM_QUEUES or raw.queue_id is None and known_queue in MAYHEM_QUEUES):
                    raw = replace(raw, champion_id=live_champion_id(champions))
                return raw
            self.background(read, self.on_client_state, done=lambda: setattr(self, 'poll_pending', False))
        self.root.after(2000, self.poll)

    def on_client_state(self, raw):
        old = self.state
        self.state = self.tracker.update(raw)
        queue_label = str(self.state.queue_id) if self.state.queue_id is not None else '尚未读取'
        reason = raw.message
        if self.state.stage == 'hidden' and raw.phase != 'Disconnected':
            reason = '浮窗隐藏：模式未匹配（当前识别队列 2400、3270）；其他自定义房间需核对实际模式字段。'
        self.connection_text.set(f'{raw.phase} · 队列 {queue_label}\n{reason}')
        if self.state.revision != old.revision:
            self.matches = []
            self.manual_override = False
            self.ocr_epoch += 1
            self.scan_interval = IDLE_SCAN_INTERVAL
            self.missing_frames = 0
        if self.state.stage == 'hidden':
            self.collapsed = False
        if self.state.champion_id != old.champion_id:
            self.load_data()
        if self.state.stage != 'hidden' and self.services and not self.preview and not self.index_requested:
            self.index_requested = True
            self.refresh_index()
        self.present()

    def load_data(self):
        cid = self.state.champion_id
        self.data = self.store.hero(cid) if cid else None
        self.augments = [Augment(**a) for a in (self.data or {}).get('augments', [])]
        self.status = self.cache_status()
        if cid in self.champions and self.services and not self.preview:
            self.fetch_hero(cid)

    def cache_status(self):
        stamp = (self.data or {}).get('fetched_at', '')[:16].replace('T', ' ')
        return f'OP.GG 快照 · {stamp} UTC' if stamp else '等待英雄数据'

    def fetch_hero(self, cid):
        if cid in self.fetching:
            return
        hero = self.champions.get(cid)
        if not hero:
            return
        self.fetching.add(cid)
        def loaded(data):
            if self.state.champion_id == cid:
                self.data = data
                self.augments = [Augment(**a) for a in data.get('augments', [])]
                self.status = self.cache_status()
                self.present()
        self.background(lambda: self.store.refresh(hero), loaded, done=lambda: self.fetching.discard(cid))

    def refresh_index(self):
        if self.index_pending:
            return
        self.index_pending = True
        def loaded(data):
            self.champions = {c.id: c for c in self.store.champions()}
            self.panel.signature = None
            if self.data is None and self.state.champion_id:
                self.load_data()
            self.present()
        self.background(lambda: self.store.refresh(None), loaded,
                        done=lambda: setattr(self, 'index_pending', False))

    def locate(self):
        if self.preview:
            width, height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            return LeagueWindow(0, (max(0, width - 1100), 100, width - 350, height - 120), (0, 0, width, height - 48), True)
        return find_league_window(self.state.stage)

    def present(self):
        if self.closed:
            return
        if self.state.stage == 'hidden':
            self.panel.hide()
            self.bubble.hide()
            self.hotkeys.set_overlay_visible(False)
            return
        self.anchor = self.locate()
        if self.anchor is None or not (self.preview or self.anchor.foreground or foreground_is_ours()):
            self.panel.hide()
            self.bubble.hide()
            self.hotkeys.set_overlay_visible(False)
            return
        if self.collapsed:
            self.panel.hide()
            self.bubble.show_at(self.anchor)
            self.hotkeys.set_overlay_visible(False)
            return
        self.bubble.hide()
        self.panel.render(self.state, self.champions, self.data, self.matches, self.status,
                          self.preview, self.scanning)
        self.panel.show_at(self.anchor)
        self.hotkeys.set_overlay_visible(True)

    def _tick(self):
        if self.closed:
            return
        now = time.monotonic()
        if now - self.last_window_check >= WINDOW_CHECK_INTERVAL:
            self.last_window_check = now
            self.present()
        if self.auto and not self.preview and self.state.stage == 'game' and self.panel.visible and now - self.last_scan >= self.scan_interval:
            self.scan(force=False)
        self.root.after(UI_TICK_MS, self._tick)

    def scan(self, force=True):
        if self.state.stage != 'game' or not self.augments or self.scanning:
            return
        if self.manual_override and not force:
            return
        if force:
            self.manual_override = False
        if self.preview:
            self.accept_matches(match_slots(['暴击飞弹', '魔法飞弹', '纯粹主义者 - 术师'], self.augments))
            return
        anchor = find_league_window('game')
        if anchor is None or not (anchor.foreground or foreground_is_ours()):
            return
        # OCR consumes only title regions. Leave our windows mapped and check
        # for overlap rather than hiding them before every screenshot.
        self.root.update_idletasks()
        left, top, right, bottom = anchor.rect
        titles = [(left + round(x1 * (right-left)), top + round(y1 * (bottom-top)),
                   left + round(x2 * (right-left)), top + round(y2 * (bottom-top)))
                  for x1, y1, x2, y2 in self.recognizer.regions]
        for overlay in (self.panel, self.bubble):
            if not overlay.visible:
                continue
            win = overlay.window
            ox, oy = win.winfo_rootx(), win.winfo_rooty()
            if any(ox < x2 and ox + win.winfo_width() > x1 and
                   oy < y2 and oy + win.winfo_height() > y1 for x1, y1, x2, y2 in titles):
                self.last_scan = time.monotonic()
                self.matches = []
                self.status = '浮窗遮挡标题 · 请拖开后识别'
                self.present()
                return
        self.scanning, self.last_scan = True, time.monotonic()
        ticket, augments, recognizer = self.ocr_ticket(), list(self.augments), self.recognizer
        # The game screenshot stays in memory; OCR reads the three title crops.
        def capture():
            if self.closed:
                return
            if ticket != self.ocr_ticket():
                self.scanning = False
                self.present()
                return
            from PIL import ImageGrab
            try:
                image = ImageGrab.grab(bbox=anchor.rect, all_screens=True)
            except OSError as exc:
                self.scanning = False
                self.status = f'截图失败 · {exc}'
                self.present()
                return
            self.background(lambda: recognizer.read_screen(image, augments, force=force, automatic=not force), self.accept_matches,
                            ticket, lambda: setattr(self, 'scanning', False))
        capture()

    def accept_matches(self, matches):
        if self.state.stage != 'game':
            return
        # Ordinary play uses a cheap, low-frequency gate. Only confirmed choices
        # need rapid checks. A single reroll animation frame preserves results.
        self.last_scan = time.monotonic()
        if matches is None:
            self.missing_frames += 1
            if self.matches and self.missing_frames < 2:
                return
            self.scan_interval = IDLE_SCAN_INTERVAL
            if not self.matches:
                return
            matches = []
        else:
            self.missing_frames = 0
        self.matches = matches
        recognized = sum(m.augment_id is not None for m in matches)
        self.scan_interval = AUTO_SCAN_INTERVAL if recognized else IDLE_SCAN_INTERVAL
        if recognized == 3:
            self.status = '模拟预览 · 海克斯已识别' if self.preview else '海克斯已识别 · F6 重新识别'
        elif recognized:
            self.status = ('模拟预览 · ' if self.preview else '') + f'已匹配 {recognized}/3 · 其余待确认 · F6 重试'
        else:
            self.status = ('模拟预览 · ' if self.preview else '') + '等待海克斯选项 · 设置中可手动修正'
        self.present()

    def apply_manual(self, texts):
        if self.state.stage != 'game':
            return
        self.ocr_epoch += 1
        self.manual_override = True
        self.matches = match_slots(texts, self.augments)
        self.status = '手动修正已保留 · F6 恢复识别'
        self.present()

    def hide(self):
        self.collapsed = True
        self.present()

    def expand(self):
        self.collapsed = False
        self.present()

    def toggle(self):
        self.collapsed = not self.collapsed
        self.present()

    def refresh(self):
        self.refresh_index()
        if self.state.champion_id:
            self.fetch_hero(self.state.champion_id)
        if not self.preview and not self.poll_pending:
            # The scheduled poll remains the only repeating poll chain.
            self.poll_pending = True
            self.background(lambda: LCUClient(self.settings.get('install_path')).read_state(), self.on_client_state,
                            done=lambda: setattr(self, 'poll_pending', False))

    def preview_next(self):
        if self.state.stage == 'hidden':
            self.on_client_state(ClientState('ChampSelect', 222, [99, 86], queue_id=2400))
        elif self.state.stage == 'select':
            self.on_client_state(ClientState('InProgress', 222, queue_id=2400, match_id=1))
            self.scan()
        else:
            self.on_client_state(ClientState('ChampSelect', 222, [99, 86], queue_id=2400))

    def show_settings(self):
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        dialog = self.dialog = tk.Toplevel(self.root)
        dialog.title('海克斯随行 · 设置')
        dialog.configure(bg=BG)
        dialog.attributes('-topmost', True)
        dialog.resizable(False, False)
        dialog.bind('<Escape>', lambda _: dialog.destroy())
        height = min(600, dialog.winfo_screenheight() - 100)
        dialog.geometry(f'440x{height}')
        header = tk.Frame(dialog, bg=BG)
        header.pack(fill='x', padx=20, pady=(20, 14))
        label(header, '随行设置', TEXT, 16, True, anchor='w').pack(fill='x')
        label(header, '调整识别方式与当前三张海克斯', MUTED, 10, anchor='w').pack(fill='x', pady=(4, 0))

        # Fixed actions stay visible while the content tabs scroll independently.
        footer = tk.Frame(dialog, bg=BG)
        footer.pack(side='bottom', fill='x', padx=20, pady=(10, 16))
        label(footer, self.hotkeys.status, MUTED, 9, wraplength=400,
              anchor='w', justify='left').pack(fill='x', pady=(0, 10))
        actions = tk.Frame(footer, bg=BG)
        actions.pack(fill='x')
        notebook = ttk.Notebook(dialog, style='Hex.TNotebook')
        notebook.pack(fill='both', expand=True, padx=20)
        common, advanced = ScrollArea(notebook), ScrollArea(notebook)
        notebook.add(common, text='常用设置')
        notebook.add(advanced, text='识别与连接')
        connection = Card(common.body)
        connection.pack(fill='x', pady=(4, 10))
        phase = {'ChampSelect': '选人阶段', 'InProgress': '对局中', 'Lobby': '大厅',
                 'Disconnected': '等待客户端连接'}.get(self.state.phase, self.state.phase)
        label(connection.body, '模拟预览' if self.preview else phase, ACCENT, 11, True, anchor='w').pack(fill='x')
        label(connection.body, 'F6 立即识别 · F7 刷新资料', MUTED, 9, anchor='w').pack(fill='x', pady=(5, 0))
        auto = tk.BooleanVar(value=self.auto)
        tk.Checkbutton(common.body, text='局内自动识别海克斯', variable=auto, bg=BG, fg=TEXT,
                       selectcolor=BG, activebackground=BG, activeforeground=ACCENT,
                       font=(FONT, 10), highlightcolor=ACCENT, cursor='hand2',
                       takefocus=True).pack(anchor='w')
        label(common.body, '快速跟随海克斯刷新，F6 可立即重新识别。', MUTED, 9, anchor='w').pack(fill='x', pady=(2, 14))

        manual = Card(common.body)
        manual.pack(fill='x')
        label(manual.body, '手动修正三张海克斯', TEXT, 11, True, anchor='w').pack(fill='x')
        label(manual.body, '只应用于当前英雄；按 F6 恢复自动识别。', MUTED, 9,
              anchor='w', justify='left', wraplength=350).pack(fill='x', pady=(6, 10))
        choices = []
        for slot, name in enumerate(('左侧', '中间', '右侧')):
            row = tk.Frame(manual.body, bg=manual.body.cget('bg'))
            row.pack(fill='x', pady=4)
            label(row, name, MUTED, 10, width=4, anchor='w').pack(side='left', padx=(0, 8))
            current = next((a.name for a in self.augments if any(m.slot == slot and m.augment_id == a.id for m in self.matches)), '')
            var = tk.StringVar(value=current)
            ttk.Combobox(row, textvariable=var, values=[''] + [a.name for a in self.augments],
                         width=25, style='Hex.TCombobox', font=(FONT, 10)).pack(side='left', fill='x', expand=True)
            choices.append(var)
        initial_choices = [v.get() for v in choices]
        initial_path = self.settings.get('install_path', '')
        install_path = tk.StringVar(value=initial_path)

        calibration = Card(advanced.body, padding=10)
        calibration.pack(fill='x', pady=(4, 10))
        label(calibration.body, '海克斯标题区域', TEXT, 11, True, anchor='w').pack(fill='x')
        label(calibration.body, '相对于游戏窗口填写 x1, y1, x2, y2，范围 0～1。', MUTED, 9,
              wraplength=350, anchor='w', justify='left').pack(fill='x', pady=(6, 10))
        regions = []
        for name, region in zip(('左侧', '中间', '右侧'), self.recognizer.regions):
            row = tk.Frame(calibration.body, bg=calibration.body.cget('bg'))
            row.pack(fill='x', pady=3)
            label(row, name, MUTED, 10, width=4, anchor='w').pack(side='left', padx=(0, 8))
            var = tk.StringVar(value=', '.join(map(str, region)))
            ttk.Entry(row, textvariable=var, width=29, style='Hex.TEntry',
                      font=(FONT, 10)).pack(side='left', fill='x', expand=True)
            regions.append(var)
        def reset_regions():
            for var, region in zip(regions, DEFAULT_REGIONS):
                var.set(', '.join(map(str, region)))
        button(calibration.body, '恢复 16:9 预设', reset_regions).pack(anchor='w', pady=(8, 0))
        opened_revision = self.state.revision
        def save():
            try:
                recognizer = Recognizer([tuple(float(x.strip()) for x in var.get().split(',')) for var in regions])
            except ValueError as exc:
                messagebox.showerror('区域无效', str(exc), parent=dialog)
                return
            path_changed = install_path.get() != initial_path
            if path_changed:
                try:
                    validate_install_path(install_path.get())
                except ValueError as exc:
                    messagebox.showerror('安装目录无效', str(exc), parent=dialog)
                    return
            self.recognizer, self.auto = recognizer, auto.get()
            self.settings.update(regions=recognizer.regions, auto_recognize=self.auto)
            if path_changed:
                self.settings['install_path'] = install_path.get()
            self.store._write('settings.json', self.settings)
            self.ocr_epoch += 1
            selected_choices = [v.get().strip() for v in choices]
            if selected_choices != initial_choices and opened_revision == self.state.revision:
                self.apply_manual(selected_choices)
            dialog.destroy()
            if path_changed:
                self.refresh()
        def install():
            path = filedialog.askdirectory(parent=dialog, title='选择英雄联盟安装目录')
            if path:
                install_path.set(path)
                if not path_hint.winfo_manager():
                    path_hint.pack(fill='x', pady=(6, 0))
        client = Card(advanced.body, padding=10)
        client.pack(fill='x')
        label(client.body, '客户端连接', TEXT, 11, True, anchor='w').pack(fill='x')
        label(client.body, '', textvariable=self.connection_text, wraplength=350,
              color=MUTED, size=9, anchor='w', justify='left').pack(fill='x', pady=(6, 8))
        button(client.body, '选择联盟安装目录', install).pack(anchor='w')
        path_hint = label(client.body, '', MUTED, 9, textvariable=install_path,
                          wraplength=350, anchor='w', justify='left')
        if initial_path:
            path_hint.pack(fill='x', pady=(6, 0))
        button(actions, '取消', dialog.destroy).pack(side='left')
        button(actions, '保存并应用', save, primary=True).pack(side='right')
        common.bind_wheel()
        advanced.bind_wheel()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.hotkeys.stop()
        if self.tray:
            self.tray.stop()
        self.root.destroy()
