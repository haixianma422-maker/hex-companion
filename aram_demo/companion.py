"""Hidden background app, one mode-aware panel, optional small settings dialog."""
import queue
import threading
import time
import tkinter as tk
import logging
from dataclasses import replace
from tkinter import messagebox

from .companion_state import MAYHEM_QUEUES, PLAYING, SessionTracker
from .cache import DataStore, SOURCE_NAMES, is_fresh
from .advice_icons import AdviceIconCache
from .bubble import CompanionBubble
from .builds import recommended_items
from .hotkeys import Hotkeys
from .item_icons import ItemIconCache
from .lcu import ClientState, LCUClient, live_champion_id
from .models import Augment
from .panel import CompanionPanel
from .settings_ui import show_settings
from .visual_assets import VisualAssetCache
from .runtime_log import health as log_health
from .recognition import Recognizer, match_slots
from .windows import LeagueWindow, find_league_window, foreground_is_ours

AUTO_SCAN_INTERVAL = .25
IDLE_SCAN_INTERVAL = 1.5
WINDOW_CHECK_INTERVAL = .5
UI_TICK_MS = 150
POLL_MS = 2000
# Each disconnected poll runs PowerShell process discovery.
DISCONNECTED_POLL_MS = 6000


class CompanionApp:
    def __init__(self, root, store, preview=False, services=True):
        self.root, self.store, self.preview, self.services = root, store, preview, services
        root.withdraw()
        root.title('海克斯随行 · 后台')
        self.closed = self.startup_failed = False
        self.tracker = SessionTracker()
        self.state = self.tracker.state
        self.connection_text = tk.StringVar(value='等待客户端连接')
        self.champions = {c.id: c for c in store.champions()}
        self.settings = store.read('settings.json') or {}
        self.client = LCUClient()
        try:
            self.recognizer = Recognizer(self.settings.get('regions'))
        except ValueError:
            self.recognizer = Recognizer()
        self.auto = self.settings.get('auto_recognize', True)
        self.events = queue.Queue()
        self.data, self.augments, self.matches = None, [], []
        self.status = '等待海克斯大乱斗'
        self.collapsed = self.scanning = self.poll_pending = False
        self.scan_feedback = False
        self.ocr_epoch = 0
        self.manual_override = False
        self.index_pending = self.index_requested = False
        self.last_scan = 0
        self.scan_interval = IDLE_SCAN_INTERVAL
        self.missing_frames = 0
        self.last_window_check = float('-inf')
        self.last_health_check = float('-inf')
        self.logged_client_state = None
        self.fetching = set()
        self.source_errors = {}
        self.dialog = None
        self.anchor = None
        self.tray = None
        self.item_icons = ItemIconCache(store.root, store.seed_root)
        self.advice_icons = AdviceIconCache(store.root, store.seed_root)
        self.visual_assets = VisualAssetCache(store.root, store.seed_root)
        self.visual_pending = False
        self.visual_requested = None
        self.visual_retry_at = None
        self.advice_pending = False
        self.advice_requested = None
        self.advice_retry_at = None
        self.icons_pending = False
        self.icons_requested = None
        self.panel = CompanionPanel(root, self.scan, self.show_settings, self.hide,
                                    self.preview_next if preview else None, on_source=self.select_source)
        self.bubble = CompanionBubble(root, self.expand)
        self.hotkeys = Hotkeys(lambda: self.dispatch(self.scan), lambda: self.dispatch(self.refresh),
                               lambda: self.dispatch(self.hide), on_toggle=lambda: self.dispatch(self.toggle),
                               bindings=self.settings.get('hotkeys'))
        self.panel.item_icons = self.item_icons
        self.panel.advice_icons = self.advice_icons
        self.panel.visual_assets = self.visual_assets
        self.panel.on_correct = lambda slot: self.show_settings(slot)
        self.panel.on_refresh = self.refresh
        self.panel.data_loading = False
        self.panel.network_error = ''
        self.panel.images_loading = False
        self.panel.images_error = ''
        self.panel.source_name = store.source_name
        self.panel.set_hotkeys(self.hotkeys.bindings)
        self.panel.set_motion(self.settings.get('animations', True))
        self.panel.on_resize=self.save_panel_zoom
        self.panel.set_zoom(self.settings.get('panel_zoom',1.))
        self.bubble.set_motion(self.settings.get('animations', True))
        self.bubble.set_hotkeys(self.hotkeys.bindings)
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
        if ticket and ticket[0] == 'source':
            expected = ('source', id(self.store))
        elif ticket and ticket[0] == 'hero':
            expected = ('hero', id(self.store), self.state.champion_id)
        else:
            expected = self.ocr_ticket()
        if self.closed or (ticket is not None and ticket != expected):
            return
        source_request = ticket and ticket[0] in ('source', 'hero')
        error_key = ('index', ticket[1]) if source_request and ticket[0] == 'source' else ticket
        if error:
            logging.getLogger(__name__).warning('background operation failed: %s', error)
            if source_request:
                self.source_errors[error_key] = error
                self.update_source_error()
            self.status = '操作未完成，保留缓存 · ' + error
            self.present()
        else:
            if source_request:
                self.source_errors.pop(error_key, None)
                self.update_source_error()
            callback(result)

    def update_source_error(self):
        identity = id(self.store)
        self.panel.network_error = (self.source_errors.get(('hero', identity, self.state.champion_id))
                                    or self.source_errors.get(('index', identity), ''))

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
            self.startup_failed = True
            # A fatal startup dialog must not leave an apparently usable
            # companion running behind it, even inside Tk's modal event loop.
            self.panel.hide()
            self.bubble.hide()
            if self.dialog is not None and self.dialog.winfo_exists():
                self.dialog.destroy()
            self.hotkeys.set_paused(True)
            try:
                messagebox.showerror('海克斯随行', '系统托盘启动失败，程序将退出。\n' + detail, parent=self.root)
            finally:
                self.close()

    def poll(self):
        if self.closed:
            return
        if not self.poll_pending and not self.preview:
            self.poll_pending = True
            champions, known_queue = list(self.champions.values()), self.state.queue_id
            def read():
                raw = self.read_client()
                if not raw.champion_id and raw.phase in PLAYING and (raw.queue_id in MAYHEM_QUEUES or raw.queue_id is None and known_queue in MAYHEM_QUEUES):
                    raw = replace(raw, champion_id=live_champion_id(champions))
                return raw
            self.background(read, self.on_client_state, done=lambda: setattr(self, 'poll_pending', False))
        self.root.after(DISCONNECTED_POLL_MS if self.state.phase == 'Disconnected' else POLL_MS, self.poll)

    def read_client(self):
        # Callers keep a single read in flight (poll_pending), so the shared
        # client's cached credentials are never used by two threads at once.
        self.client.install_path = self.settings.get('install_path')
        return self.client.read_state()

    def on_client_state(self, raw):
        old = self.state
        self.state = self.tracker.update(raw)
        diagnostic = (raw.phase, self.state.champion_id, self.state.queue_id, raw.message)
        if diagnostic != self.logged_client_state:
            self.logged_client_state = diagnostic
            logging.getLogger(__name__).info('client phase=%s hero=%s queue=%s detail=%s', *diagnostic)
        queue_label = str(self.state.queue_id) if self.state.queue_id is not None else '尚未读取'
        reason = raw.message
        if self.state.stage == 'hidden' and raw.phase != 'Disconnected':
            queues = '、'.join(map(str, sorted(MAYHEM_QUEUES)))
            reason = f'浮窗隐藏：模式未匹配（当前识别队列 {queues}）；其他自定义房间需核对实际模式字段。'
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
        elif self.state.stage != old.stage:
            self.refresh_advice_icons()
        if self.state.candidate_ids != old.candidate_ids or self.state.stage != old.stage:
            self.refresh_visual_assets()
        if self.state.stage != 'hidden' and self.services and not self.preview and not self.index_requested:
            self.index_requested = True
            self.refresh_index()
        self.present()

    def load_data(self):
        cid = self.state.champion_id
        self.data = self.store.hero(cid) if cid else None
        self.augments = [Augment(**a) for a in (self.data or {}).get('augments', [])]
        self.status = self.cache_status()
        self.update_source_error()
        self.update_data_loading()
        self.refresh_icons()
        self.refresh_visual_assets()
        # Champion changes are frequent in select; refresh() still forces a fetch.
        if cid in self.champions and self.services and not self.preview and not is_fresh(self.data):
            self.fetch_hero(cid)

    def cache_status(self):
        stamp = (self.data or {}).get('fetched_at', '')[:16].replace('T', ' ')
        return f'{self.store.source_name} 快照 · {stamp} UTC' if stamp else f'{self.store.source_name} · 等待英雄数据'

    def change_source(self, source):
        if source == self.store.source:
            return
        self.store.retire()
        self.store = DataStore(self.store.root, self.store.seed_root, source=source)
        logging.getLogger(__name__).info('source switched to %s', source)
        self.panel.source_name = self.store.source_name
        self.source_errors.clear()
        self.update_source_error()
        self.ocr_epoch += 1
        self.matches = []
        self.manual_override = False
        self.fetching.clear()
        self.index_pending = self.index_requested = False
        self.update_data_loading()
        # Champion identity is shared; source-specific ranks are not. Keeping
        # identity allows a cold source to fetch this hero alongside its index.
        identities = {cid: replace(hero, tier=None, rank=None) for cid, hero in self.champions.items()}
        identities.update({c.id: c for c in self.store.champions()})
        self.champions = identities
        self.icons_requested = self.advice_requested = None
        self.visual_requested = None
        self.load_data()
        if self.services and not self.preview:
            self.index_requested = True
            self.refresh_index()
        self.present()

    def update_data_loading(self):
        """Hero and index requests may overlap; neither can hide the other."""
        self.panel.data_loading = self.index_pending or (id(self.store), self.state.champion_id) in self.fetching

    def update_image_loading(self):
        self.panel.images_loading = self.visual_pending or self.advice_pending or self.icons_pending

    def refresh_visual_assets(self):
        requests = []
        cid = self.state.champion_id
        if cid in self.champions:
            requests.extend((('portrait', cid), ('splash', cid)))
        requests.extend(('portrait', candidate) for candidate in self.state.candidate_ids if candidate in self.champions)
        known_augments = {augment.id for augment in self.augments}
        requests.extend(('augment', match.augment_id) for match in self.matches
                        if match.augment_id in known_augments)
        requests = tuple(dict.fromkeys(requests))
        if not self.services or self.preview or self.visual_pending or not requests or requests == self.visual_requested:
            return
        self.visual_pending, self.visual_requested = True, requests
        self.update_image_loading()
        def finished():
            self.visual_pending = False
            self.update_image_loading()
            self.refresh_visual_assets()
        def loaded(result):
            self.panel.images_error = '部分图片暂不可用' if result.get('failed') else ''
            if result.get('failed'):
                self.visual_retry_at = time.monotonic() + 60
            self.panel.signature = None
            if self.dialog is not None and self.dialog.winfo_exists():
                refresh = getattr(self, '_settings_refresh_icons', None)
                if refresh:
                    refresh()
            self.present()
            if result.get('deferred'):
                self.visual_requested = None
                self.refresh_visual_assets()
        # Visual IDs are shared between sources. A source change can reuse an
        # image downloaded by an earlier request without changing source data.
        def download():
            try:
                return self.visual_assets.ensure(requests, on_progress=lambda: self.dispatch(self.images_loaded))
            except Exception:
                return {'failed': len(requests)}
        self.background(download, loaded, done=finished)

    def select_source(self, source_name):
        source = next((key for key, name in SOURCE_NAMES.items() if name == source_name), None)
        if source is None or source == self.store.source:
            self.present()
            return
        settings = dict(self.settings, data_source=source)
        try:
            self.store._write('settings.json', settings)
        except OSError as exc:
            self.status = '来源未切换 · 设置未能保存：' + str(exc)
            self.panel.quick_source_var.set(self.store.source_name)
            self.present()
            return
        self.settings = settings
        if self.dialog is not None and self.dialog.winfo_exists():
            self.source_var.set(source_name)
        self.change_source(source)

    def images_loaded(self):
        self.panel.signature = None
        self.present()

    def refresh_icons(self):
        self.refresh_advice_icons()
        if not self.services or self.preview or self.icons_pending:
            return
        ids = tuple(item['id'] for item in recommended_items(self.data))
        if not ids or ids == self.icons_requested:
            return
        self.icons_pending, self.icons_requested = True, ids
        self.update_image_loading()
        def finished():
            self.icons_pending = False
            self.update_image_loading()
            self.refresh_icons()
        self.background(lambda: self.item_icons.ensure(ids), lambda _: self.images_loaded(), done=finished)

    def refresh_advice_icons(self):
        if not self.services or self.preview or self.advice_pending:
            return
        data = self.data or {}
        skills = self.visual_assets.champion_skill_icons(self.state.champion_id) if self.state.stage == 'game' else {}
        if self.state.stage == 'game':
            skills.update(data.get('skill_icons', {}))
        spells = data.get('summoner_spells', []) if self.state.stage == 'select' else []
        urls = tuple(dict.fromkeys([url for url in skills.values() if url] +
                                  [s.get('icon_url') for s in spells if s.get('icon_url')]))
        if not urls or urls == self.advice_requested:
            return
        self.advice_pending, self.advice_requested = True, urls
        self.update_image_loading()
        def finished():
            self.advice_pending = False
            self.update_image_loading()
            self.refresh_advice_icons()
        def loaded(_):
            if any(self.advice_icons.path(url) is None for url in urls):
                self.advice_retry_at = time.monotonic() + 60
            self.images_loaded()
        self.background(lambda: self.advice_icons.ensure(urls, on_progress=lambda: self.dispatch(self.images_loaded)),
                        loaded, done=finished)

    def fetch_hero(self, cid):
        store = self.store
        key = (id(store), cid)
        if key in self.fetching:
            return
        hero = self.champions.get(cid)
        if not hero:
            return
        self.fetching.add(key)
        started = time.monotonic()
        self.update_data_loading()
        def loaded(data):
            if self.store is store and self.state.champion_id == cid:
                logging.getLogger(__name__).info('hero data loaded source=%s hero=%s augments=%s verified_build=%s elapsed=%.2fs',
                                                store.source, cid, len(data.get('augments', [])), data.get('build_mode_verified'),
                                                time.monotonic() - started)
                self.data = data
                self.augments = [Augment(**a) for a in data.get('augments', [])]
                self.status = self.cache_status()
                self.refresh_icons()
                self.refresh_visual_assets()
                self.present()
        def finished():
            self.fetching.discard(key)
            self.update_data_loading()
        ticket = ('hero', id(store), cid)
        def ready(data):
            self.events.put(('result', ticket, loaded, data, None, None))
        self.background(lambda: store.refresh(hero, on_ready=ready), loaded, ticket=ticket,
                        done=finished)

    def refresh_index(self):
        if self.index_pending:
            return
        self.index_pending = True
        self.update_data_loading()
        store = self.store
        def loaded(data):
            self.champions = {c.id: c for c in store.champions()}
            self.panel.signature = None
            if self.data is None and self.state.champion_id:
                self.load_data()
            self.refresh_visual_assets()
            self.present()
        def finished():
            if self.store is store:
                self.index_pending = False
            self.update_data_loading()
        self.background(lambda: store.refresh(None), loaded, ticket=('source', id(store)),
                        done=finished)

    def locate(self):
        if self.preview:
            width, height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            return LeagueWindow(0, (max(0, width - 1100), 100, width - 350, height - 120), (0, 0, width, height - 48), True)
        return find_league_window(self.state.stage)

    def present(self):
        if self.closed or self.startup_failed:
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
            rectangle = (self.panel.window.winfo_rootx(), self.panel.window.winfo_rooty(), self.panel.width, self.panel.height)
            self.bubble.show_at(self.anchor,rectangle)
            self.panel.hide(animate=True)
            self.hotkeys.set_overlay_visible(False)
            return
        self.bubble.hide(animate=True)
        self.panel.manual_override = self.manual_override
        self.panel.render(self.state, self.champions, self.data, self.matches, self.status,
                          self.preview, self.scanning and self.scan_feedback)
        self.panel.show_at(self.anchor)
        self.hotkeys.set_overlay_visible(True)

    def save_panel_zoom(self, zoom):
        settings=dict(self.settings,panel_zoom=zoom)
        try:
            self.store._write('settings.json',settings)
        except OSError as exc:
            self.status='浮窗已缩放，大小未能保存：'+str(exc)
            self.present()
            return
        self.settings=settings

    def _tick(self):
        if self.closed:
            return
        now = time.monotonic()
        if now - self.last_health_check >= 60:
            self.last_health_check = now
            log_health()
        if now - self.last_window_check >= WINDOW_CHECK_INTERVAL:
            self.last_window_check = now
            self.present()
        if (self.visual_retry_at is not None and now >= self.visual_retry_at
                and not self.visual_pending and self.state.stage != 'hidden'):
            self.visual_retry_at = None
            self.visual_requested = None
            self.refresh_visual_assets()
        if (self.advice_retry_at is not None and now >= self.advice_retry_at
                and not self.advice_pending and self.state.stage != 'hidden'):
            self.advice_retry_at = None
            self.advice_requested = None
            self.refresh_advice_icons()
        if self.auto and not self.preview and self.state.stage == 'game' and self.panel.visible and now - self.last_scan >= self.scan_interval:
            self.scan(force=False)
        self.root.after(UI_TICK_MS, self._tick)

    def scan(self, force=True):
        if self.state.stage != 'game' or not self.augments:
            return
        if self.scanning:
            if force:
                self.scan_feedback = True
                self.present()
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
        self.scan_feedback = bool(force)
        if force:
            self.present()
        ticket, augments, recognizer = self.ocr_ticket(), list(self.augments), self.recognizer
        # The game screenshot stays in memory; OCR reads the three title crops.
        from PIL import ImageGrab
        try:
            image = ImageGrab.grab(bbox=anchor.rect, all_screens=True)
        except OSError as exc:
            self.scanning = False
            self.status = f'截图失败 · {exc}'
            self.present()
            return
        self.background(lambda: recognizer.read_screen(image, augments, force=force, automatic=not force), self.accept_matches,
                        ticket, self.scan_finished)

    def scan_finished(self):
        show_completion = self.scan_feedback
        self.scanning = self.scan_feedback = False
        if show_completion:
            self.present()

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
        previous = [(m.slot, m.augment_id, m.status) for m in self.matches]
        current = [(m.slot, m.augment_id, m.status) for m in matches]
        if previous != current:
            logging.getLogger(__name__).info('recognition slots=%s manual=%s', current, self.manual_override)
        self.matches = matches
        recognized = sum(m.augment_id is not None for m in matches)
        self.scan_interval = AUTO_SCAN_INTERVAL if recognized else IDLE_SCAN_INTERVAL
        if recognized == 3:
            self.status = '模拟预览 · 海克斯已识别' if self.preview else f'海克斯已识别 · {self.hotkeys.bindings["scan"]} 重新识别'
        elif recognized:
            self.status = ('模拟预览 · ' if self.preview else '') + f'已匹配 {recognized}/3 · 其余待确认 · {self.hotkeys.bindings["scan"]} 重试'
        else:
            self.status = ('模拟预览 · ' if self.preview else '') + '未能确认选项，请重试或手动修正'
        self.refresh_visual_assets()
        self.present()

    def apply_manual(self, texts):
        if self.state.stage != 'game':
            return
        self.ocr_epoch += 1
        self.manual_override = True
        self.matches = match_slots(texts, self.augments)
        self.status = f'手动修正已保留 · {self.hotkeys.bindings["scan"]} 恢复识别'
        self.refresh_visual_assets()
        self.present()

    def hide(self):
        self.collapsed = True
        self.present()

    def expand(self):
        self.collapsed = False
        self.present()

    def toggle(self):
        if self.state.stage == 'hidden':
            return
        self.collapsed = not self.collapsed
        self.present()

    def refresh(self):
        self.icons_requested = None
        self.advice_requested = None
        self.visual_requested = None
        self.refresh_icons()
        self.refresh_visual_assets()
        self.refresh_index()
        if self.state.champion_id:
            self.fetch_hero(self.state.champion_id)
        if not self.preview and not self.poll_pending:
            # The scheduled poll remains the only repeating poll chain.
            self.poll_pending = True
            self.background(self.read_client, self.on_client_state,
                            done=lambda: setattr(self, 'poll_pending', False))

    def preview_next(self):
        if self.state.stage == 'hidden':
            self.on_client_state(ClientState('ChampSelect', 222, [90, 99, 222, 201, 86, 17], queue_id=2400))
        elif self.state.stage == 'select':
            self.on_client_state(ClientState('InProgress', 222, queue_id=2400, match_id=1))
            self.scan()
        else:
            self.on_client_state(ClientState('ChampSelect', 222, [90, 99, 222, 201, 86, 17], queue_id=2400))

    def show_settings(self, slot=None):
        show_settings(self, slot)

    def close(self):
        if self.closed:
            return
        self.closed = True
        logging.getLogger(__name__).info('shutdown requested')
        try:
            try:
                self.hotkeys.stop()
            finally:
                if self.tray:
                    self.tray.stop()
        except Exception:
            logging.getLogger(__name__).exception('关闭后台服务失败')
        finally:
            self.panel.hide()
            self.bubble.hide()
            self.root.destroy()
