import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import webbrowser

from .hotkeys import Hotkeys
from .lcu import LCUClient, live_champion_id
from .models import Augment, augment_label, sort_champions
from .overlay import Overlay
from .recognition import DEFAULT_REGIONS, Recognizer, match_slots
from .state import RequestContext, demo_candidates

BG, PANEL, CARD, TEXT, MUTED, GOLD = '#0b1220', '#111d30', '#19283f', '#e8eef8', '#93a5bd', '#e6b972'


class DemoApp:
    def __init__(self, root, store):
        self.root, self.store = root, store
        self.closed = False
        self.mode = 'demo'
        self.generation = 0
        self.selected_id = None
        self.game_id = None
        self.last_phase, self.last_match_id = 'Disconnected', None
        self.candidate_ids = demo_candidates()
        self.manual_ids = []
        self.champions = {c.id: c for c in store.champions()}
        self.hero_data = None
        self.augments = []
        self.events = queue.Queue()
        self.scanning = False
        self.client_pending = False
        self.settings = store.read('settings.json') or {}
        try:
            self.recognizer = Recognizer(self.settings.get('regions'))
        except ValueError:
            self.recognizer = Recognizer()
        self.hotkeys = Hotkeys(lambda: self.events.put(('key', self.scan)),
                               lambda: self.events.put(('key', self.refresh_client)),
                               lambda: self.events.put(('key', self.hide_overlay)))
        self.overlay = Overlay(root, lambda: self.hotkeys.set_overlay_visible(False))
        self._build()
        self._render_candidates()
        self.select_hero(222 if 222 in self.champions else next(iter(self.champions), None))
        self.hotkeys.start()
        self.root.after(80, self._pump)
        self.root.after(4000, self._poll)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.bind('<Escape>', lambda event: self.hide_overlay())

    def context(self):
        return RequestContext(self.mode, self.selected_id, self.generation)

    def _build(self):
        root = self.root
        root.title('海克斯随行 · OP.GG Demo')
        height = min(900, root.winfo_screenheight() - 90)
        width = min(1190, root.winfo_screenwidth() - 80)
        root.geometry(f'{width}x{height}+30+30')
        root.minsize(1000, 700)
        root.configure(bg=BG)
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', background=PANEL, foreground=TEXT, fieldbackground=CARD, bordercolor=PANEL)
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=TEXT)
        style.configure('TButton', background=CARD, foreground=TEXT, padding=(12, 8), borderwidth=0)
        style.map('TButton', background=[('active', '#2d4160')])
        style.configure('Gold.TButton', background=GOLD, foreground=BG)
        style.map('Gold.TButton', background=[('active', '#f5cc8e')])
        style.configure('TCombobox', fieldbackground=CARD, background=CARD, foreground=TEXT, padding=5)
        style.map('TCombobox', fieldbackground=[('readonly', CARD)], foreground=[('readonly', TEXT)])
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=34, borderwidth=0)
        style.configure('Treeview.Heading', background=CARD, foreground=MUTED, padding=8)
        style.map('Treeview', background=[('selected', '#30435d')])
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', background=CARD, foreground=MUTED, padding=(22, 10))
        style.map('TNotebook.Tab', background=[('selected', PANEL)], foreground=[('selected', GOLD)])

        top = tk.Frame(root, bg=BG)
        top.pack(fill='x', padx=26, pady=(20, 12))
        tk.Label(top, text='HEX  /  海克斯随行', bg=BG, fg=TEXT, font=('Microsoft YaHei UI', 22, 'bold')).pack(side='left')
        self.mode_var = tk.StringVar(value='演示模式')
        mode = ttk.Combobox(top, textvariable=self.mode_var, values=['演示模式', '客户端模式'], state='readonly', width=12)
        mode.pack(side='right')
        mode.bind('<<ComboboxSelected>>', lambda event: self.change_mode())
        tk.Label(root, text='选人看 T 档  ·  进局看出装  ·  三卡看评级', bg=BG, fg=MUTED, anchor='w').pack(fill='x', padx=28)

        self.status = tk.StringVar(value='模拟选人 · 数据来自 OP.GG 本地快照')
        tk.Label(root, textvariable=self.status, bg='#1c2b40', fg='#b8cbe4', anchor='w', padx=15, pady=9).pack(fill='x', padx=26, pady=14)
        main = tk.Frame(root, bg=BG)
        main.pack(fill='both', expand=True, padx=26)
        side = tk.Frame(main, bg=PANEL, width=290)
        side.pack(side='left', fill='y', padx=(0, 18))
        side.pack_propagate(False)
        tk.Label(side, text='可选英雄', bg=PANEL, fg=TEXT, font=('Microsoft YaHei UI', 14, 'bold'), anchor='w').pack(fill='x', padx=16, pady=(16, 3))
        self.candidate_note = tk.StringVar(value='模拟替补席 · 同档按 OP.GG 排名排序')
        tk.Label(side, textvariable=self.candidate_note, bg=PANEL, fg=MUTED, wraplength=255, justify='left').pack(fill='x', padx=16, pady=(0, 12))
        self.candidates = ttk.Treeview(side, columns=('tier', 'rank', 'name'), show='headings', height=3, selectmode='browse')
        for key, label, width in [('tier', '档位', 55), ('rank', '排名', 55), ('name', '英雄', 155)]:
            self.candidates.heading(key, text=label)
            self.candidates.column(key, width=width, anchor='center' if key != 'name' else 'w')
        self.candidates.pack(fill='x', padx=10)
        self.candidates.bind('<<TreeviewSelect>>', self._candidate_selected)
        ttk.Button(side, text='+ 手动补充候选', command=self.add_candidate).pack(fill='x', padx=16, pady=10)
        ttk.Separator(side).pack(fill='x', padx=16, pady=10)
        tk.Label(side, text='查询其他英雄', bg=PANEL, fg=MUTED, anchor='w').pack(fill='x', padx=16)
        self.hero_choice = tk.StringVar()
        self.hero_combo = ttk.Combobox(side, textvariable=self.hero_choice, state='readonly', width=20)
        self.hero_combo.pack(fill='x', padx=16, pady=8)
        self._update_hero_choices()
        self.hero_combo.bind('<<ComboboxSelected>>', self._chosen_hero)
        ttk.Button(side, text='刷新当前英雄数据', command=self.refresh_hero).pack(fill='x', padx=16, pady=(0, 7))
        ttk.Button(side, text='刷新英雄 T 档榜单', command=self.refresh_champions).pack(fill='x', padx=16, pady=(0, 7))
        ttk.Button(side, text='查看 OP.GG 原页面 ↗', command=self.open_source).pack(fill='x', padx=16)
        ttk.Button(side, text='客户端与识别设置', command=self.client_settings).pack(fill='x', padx=16, pady=(12, 0))
        tk.Label(side, text='已内置金克丝、拉克丝、盖伦快照\n其他英雄可联网按需获取', bg=PANEL, fg=MUTED, justify='left').pack(side='bottom', fill='x', padx=16, pady=18)

        content = tk.Frame(main, bg=BG)
        content.pack(side='left', fill='both', expand=True)
        head = tk.Frame(content, bg=PANEL)
        head.pack(fill='x', pady=(0, 12))
        self.hero_title = tk.StringVar()
        self.tier_title = tk.StringVar()
        self.metadata = tk.StringVar()
        tk.Label(head, textvariable=self.tier_title, bg=PANEL, fg=GOLD, font=('Microsoft YaHei UI', 30, 'bold')).pack(side='right', padx=22)
        tk.Label(head, textvariable=self.hero_title, bg=PANEL, fg=TEXT, font=('Microsoft YaHei UI', 21, 'bold'), anchor='w').pack(fill='x', padx=20, pady=(13, 4))
        tk.Label(head, textvariable=self.metadata, bg=PANEL, fg=MUTED, anchor='w').pack(fill='x', padx=20, pady=(0, 14))
        self.tabs = ttk.Notebook(content)
        self.tabs.pack(fill='both', expand=True)
        builds = tk.Frame(self.tabs, bg=PANEL)
        augments = tk.Frame(self.tabs, bg=PANEL)
        self.tabs.add(builds, text='出装建议')
        self.tabs.add(augments, text='海克斯数据库')
        tk.Label(builds, text='OP.GG 页面出装 · 模式口径待确认', bg=PANEL, fg=GOLD, anchor='w').pack(fill='x', padx=20, pady=(16, 6))
        self.build_text = tk.Text(builds, bg=PANEL, fg=TEXT, wrap='word', bd=0, padx=20, pady=12, font=('Microsoft YaHei UI', 12), spacing1=7, spacing3=9, height=10)
        build_scroll = ttk.Scrollbar(builds, command=self.build_text.yview)
        build_scroll.pack(side='right', fill='y', padx=(0, 8), pady=12)
        self.build_text.configure(yscrollcommand=build_scroll.set)
        self.build_text.pack(fill='both', expand=True)
        self.build_text.tag_configure('heading', foreground=GOLD, font=('Microsoft YaHei UI', 12, 'bold'))
        self.build_text.configure(state='disabled')
        aug_top = tk.Frame(augments, bg=PANEL)
        aug_top.pack(fill='x', padx=14, pady=14)
        tk.Label(aug_top, text='查找海克斯', bg=PANEL, fg=MUTED).pack(side='left')
        self.augment_query = tk.StringVar()
        ttk.Entry(aug_top, textvariable=self.augment_query).pack(side='left', fill='x', expand=True, padx=(10, 0))
        self.augment_query.trace_add('write', lambda *args: self._render_augments())
        self.augment_tree = ttk.Treeview(augments, columns=('name', 'tier', 'rarity'), show='headings', height=8)
        for key, label, width in [('name', '海克斯名称', 280), ('tier', 'OP.GG 评级', 110), ('rarity', '稀有度原值', 110)]:
            self.augment_tree.heading(key, text=label)
            self.augment_tree.column(key, width=width, anchor='w')
        scroll = ttk.Scrollbar(augments, command=self.augment_tree.yview)
        self.augment_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y', pady=(0, 12), padx=(0, 8))
        self.augment_tree.pack(fill='both', expand=True, padx=(14, 0), pady=(0, 12))
        self.augment_tree.bind('<Double-1>', self._use_augment)

        bottom = tk.Frame(content, bg=PANEL)
        bottom.pack(fill='x', pady=(12, 0), before=self.tabs)
        tk.Label(bottom, text='三卡模拟 / 手动修正', bg=PANEL, fg=TEXT, anchor='w', font=('Microsoft YaHei UI', 11, 'bold')).pack(fill='x', padx=16, pady=(12, 3))
        line = tk.Frame(bottom, bg=PANEL)
        line.pack(fill='x', padx=12, pady=8)
        self.card_vars, self.card_boxes = [], []
        for name in ('左侧', '中间', '右侧'):
            frame = tk.Frame(line, bg=PANEL)
            frame.pack(side='left', fill='x', expand=True, padx=4)
            tk.Label(frame, text=name, bg=PANEL, fg=MUTED, anchor='w').pack(fill='x')
            variable = tk.StringVar()
            box = ttk.Combobox(frame, textvariable=variable, width=18)
            box.pack(fill='x', pady=4)
            self.card_vars.append(variable)
            self.card_boxes.append(box)
        actions = tk.Frame(bottom, bg=PANEL)
        actions.pack(fill='x', padx=16, pady=(0, 14))
        ttk.Button(actions, text='展示三卡评级', style='Gold.TButton', command=self.show_manual).pack(side='left')
        ttk.Button(actions, text='识别屏幕  F6', command=self.scan).pack(side='left', padx=8)
        ttk.Button(actions, text='关闭浮窗', command=self.hide_overlay).pack(side='right')
        self.footer = tk.StringVar(value='OP.GG 本地快照 · 原始档位越小越靠前 · 国服对局尚未实测')
        tk.Label(root, textvariable=self.footer, bg=BG, fg=MUTED, anchor='w').pack(side='bottom', fill='x', padx=28, pady=12, before=main)

    def _update_hero_choices(self):
        self.choice_ids = [c.id for c in sorted(self.champions.values(), key=lambda c: c.slug)]
        self.hero_combo['values'] = [f'{self.champions[cid].name}  /  {self.champions[cid].slug}' for cid in self.choice_ids]

    def _chosen_hero(self, event=None):
        idx = self.hero_combo.current()
        if idx >= 0:
            self.select_hero(self.choice_ids[idx])

    def _render_candidates(self):
        self.candidates.delete(*self.candidates.get_children())
        ids = list(dict.fromkeys(self.candidate_ids + self.manual_ids))
        rows = sort_champions([self.champions[i] for i in ids if i in self.champions])
        for hero in rows:
            suffix = ' · 手动' if hero.id in self.manual_ids else ''
            self.candidates.insert('', 'end', iid=str(hero.id), values=(hero.tier_label, hero.rank or '—', hero.name + suffix))
        for cid in ids:
            if cid not in self.champions:
                self.candidates.insert('', 'end', iid=str(cid), values=('未知', '—', f'英雄 ID {cid}'))

    def _candidate_selected(self, event=None):
        selected = self.candidates.selection()
        if selected:
            self.select_hero(int(selected[0]))

    def select_hero(self, cid, fetch_missing=True):
        self.generation += 1
        self.selected_id = cid
        self.hide_overlay()
        hero = self.champions.get(cid)
        self.hero_data = self.store.hero(cid) if cid else None
        self.augments = [Augment(**a) for a in (self.hero_data or {}).get('augments', [])]
        prefix = '模拟当前英雄' if self.mode == 'demo' else '本局英雄' if cid == self.game_id and cid else '预览英雄'
        self.hero_title.set(f'{hero.name if hero else "未识别英雄"}  ·  {prefix}')
        self.tier_title.set(hero.tier_label if hero else '—')
        self.metadata.set(f'OP.GG 排名 #{hero.rank}' if hero and hero.rank else '暂无排名')
        self._render_details()
        if hero and cid in self.choice_ids:
            self.hero_combo.current(self.choice_ids.index(cid))
        if not self.hero_data and hero and fetch_missing:
            self.status.set('正在获取该英雄的 OP.GG 数据…')
            self._background(lambda: self.store.refresh(hero), lambda data: self.select_hero(cid, False))

    def _render_details(self):
        self.build_text.configure(state='normal')
        self.build_text.delete('1.0', 'end')
        builds = (self.hero_data or {}).get('builds', [])
        for category in ('核心装备', '出门装', '鞋子'):
            rows = [r for r in builds if r['category'] == category]
            if rows:
                self.build_text.insert('end', category + '\n', 'heading')
                for row in rows[:4]:
                    self.build_text.insert('end', '  →  '.join(i['name'] for i in row['items']) + '\n')
                self.build_text.insert('end', '\n')
        if not builds:
            self.build_text.insert('end', '暂无本地出装数据。可点击“刷新当前英雄数据”。')
        self.build_text.configure(state='disabled')
        data = self.hero_data or {}
        stamp = data.get('fetched_at', '')[:19].replace('T', ' ')
        self.footer.set(f'OP.GG · 资源版本 {data.get("patch") or "未知"} · 快照 {stamp or "暂无"} UTC · {len(self.augments)} 条海克斯')
        self._render_augments()
        names = [a.name for a in self.augments]
        for idx, box in enumerate(self.card_boxes):
            box['values'] = [''] + names
            chosen = next((a.name for a in self.augments if a.tier == (0, 2, 5)[idx]), names[idx] if idx < len(names) else '')
            self.card_vars[idx].set(chosen)
        if data:
            self.status.set('模拟选人 · 实际 OP.GG 数据快照' if self.mode == 'demo' else '客户端模式 · 当前展示 OP.GG 缓存数据')

    def _render_augments(self):
        if not hasattr(self, 'augment_tree'):
            return
        self.augment_tree.delete(*self.augment_tree.get_children())
        query = self.augment_query.get().strip()
        mapping = (self.hero_data or {}).get('tier_labels', {})
        for a in self.augments:
            if query and query not in a.name:
                continue
            self.augment_tree.insert('', 'end', iid=str(a.id), values=(a.name, augment_label(a.tier, mapping), a.rarity if a.rarity is not None else '—'))

    def _use_augment(self, event=None):
        selected = self.augment_tree.selection()
        if selected:
            aid = int(selected[0])
            self.card_vars[0].set(next(a.name for a in self.augments if a.id == aid))

    def _background(self, job, callback, done=None, context=None):
        context = context or self.context()
        def worker():
            try:
                result, error = job(), None
            except Exception as exc:
                result, error = None, f'{type(exc).__name__}: {exc}'
            self.events.put(('result', context, callback, result, error, done))
        threading.Thread(target=worker, daemon=True).start()

    def _pump(self):
        if self.closed:
            return
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'key':
                    event[1]()
                    continue
                _, context, callback, data, error, done = event
                if done:
                    done()
                if self.context().accepts(context):
                    if error:
                        self.status.set('本次操作未完成，保留已有数据 · ' + error)
                    else:
                        callback(data)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def refresh_hero(self):
        hero = self.champions.get(self.selected_id)
        if hero:
            cid = hero.id
            self.status.set('正在刷新当前英雄数据…')
            self._background(lambda: self.store.refresh(hero), lambda data: self.select_hero(cid, False))

    def refresh_champions(self):
        self.status.set('正在刷新 OP.GG 英雄榜…')
        def loaded(data):
            self.champions = {c.id: c for c in self.store.champions()}
            self._update_hero_choices()
            self._render_candidates()
            self.select_hero(self.selected_id, False)
        self._background(lambda: self.store.refresh(None), loaded)

    def show_manual(self):
        matches = match_slots([v.get() for v in self.card_vars], self.augments)
        self._show_matches(matches, True)

    def _show_matches(self, matches, simulated):
        hero = self.champions.get(self.selected_id)
        self.overlay.show(matches, hero.name if hero else '未知英雄', self.augments,
                          (self.hero_data or {}).get('tier_labels', {}), simulated)
        self.hotkeys.set_overlay_visible(True)

    def hide_overlay(self):
        self.overlay.hide()

    def scan(self):
        if self.mode == 'demo':
            self.show_manual()
            self.status.set('演示模式：显示模拟三卡。连接游戏后可用 F6 截屏识别。')
            return
        if not self.game_id:
            self.status.set('尚未识别本局英雄，请先连接 / 刷新客户端')
            return
        if self.selected_id != self.game_id:
            self.select_hero(self.game_id)
            self.status.set('已切回本局英雄，数据就绪后再次按 F6')
            return
        if self.scanning or not self.augments:
            self.status.set('正在识别或该英雄暂无缓存，请稍后重试')
            return
        self.scanning = True
        self.hide_overlay()
        self.root.iconify()
        augments = list(self.augments)
        recognizer = self.recognizer
        context = self.context()
        def run():
            self._background(lambda: recognizer.capture_and_read(augments), self._recognized,
                             lambda: setattr(self, 'scanning', False), context=context)
        self.root.after(250, run)

    def _recognized(self, matches):
        for match in matches:
            augment = next((a for a in self.augments if a.id == match.augment_id), None)
            self.card_vars[match.slot].set(augment.name if augment else match.text)
        self._show_matches(matches, False)
        self.status.set('识别完成；未确认卡片可在三卡输入框中修正')

    def change_mode(self):
        self.generation += 1
        self.mode = 'demo' if self.mode_var.get() == '演示模式' else 'client'
        self.game_id = None
        self.last_phase, self.last_match_id = 'Disconnected', None
        self.manual_ids = []
        self.candidate_ids = demo_candidates() if self.mode == 'demo' else []
        self._render_candidates()
        self.candidate_note.set('模拟替补席 · 同档按 OP.GG 排名排序' if self.mode == 'demo' else '客户端替补席 · 手动补充将单独标注')
        self.select_hero(self.selected_id, False)
        if self.mode == 'client':
            self.refresh_client()

    def refresh_client(self, force=True):
        if self.mode != 'client':
            self.status.set('当前为演示模式；可在右上角切换客户端模式')
            return
        if self.client_pending:
            return
        self.client_pending = True
        def read():
            state = LCUClient(self.settings.get('install_path')).read_state()
            cid = state.champion_id
            if not cid and state.phase in ('InProgress', 'GameStart', 'Reconnect'):
                cid = live_champion_id(list(self.champions.values()))
            return state, cid
        def loaded(result):
            state, cid = result
            self._apply_client_state(state, cid, force)
        self._background(read, loaded, lambda: setattr(self, 'client_pending', False))

    def _apply_client_state(self, state, cid, force):
        playing = ('InProgress', 'GameStart', 'Reconnect')
        same_match = not (self.last_match_id and state.match_id and self.last_match_id != state.match_id)
        continuing = state.phase in playing and self.last_phase in ('ChampSelect', *playing)
        retained = not cid and same_match and continuing and self.game_id is not None
        if retained:
            cid = self.game_id
        changed = cid != self.game_id
        self.game_id = cid
        self.last_phase = state.phase
        self.last_match_id = (state.match_id or self.last_match_id) if state.phase in playing and same_match else state.match_id
        self.candidate_ids = ([cid] if cid else []) + state.candidate_ids
        self._render_candidates()
        if cid and (changed or force):
            self.select_hero(cid)
        elif changed:
            self.select_hero(self.selected_id, False)
        suffix = ' · 沿用本局已确认英雄' if retained else ''
        self.status.set(f'{state.phase} · {state.message}{suffix}')

    def _poll(self):
        if self.closed:
            return
        if self.mode == 'client':
            self.refresh_client(False)
        self.root.after(4000, self._poll)

    def add_candidate(self):
        query = simpledialog.askstring('补充候选', '输入英雄中文称号、英文 key 或数字 ID：', parent=self.root)
        if not query:
            return
        query = query.strip().casefold()
        aliases = {'金克丝': 222, '拉克丝': 99, '盖伦': 86}
        found = next((c for c in self.champions.values() if query in (str(c.id), c.name.casefold(), c.slug.casefold())), None)
        if not found and query in aliases:
            found = self.champions.get(aliases[query])
        if not found:
            messagebox.showinfo('未找到英雄', '请使用英雄称号或英文 key，也可以从左侧下拉列表查询。')
            return
        if found.id not in self.manual_ids:
            self.manual_ids.append(found.id)
        self._render_candidates()

    def choose_install(self):
        path = filedialog.askdirectory(title='选择英雄联盟安装目录', parent=self.root)
        if path:
            self.settings['install_path'] = path
            self._save_settings()
            self.refresh_client()

    def client_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title('客户端与识别设置')
        dialog.configure(bg=PANEL)
        tk.Label(dialog, text='客户端模式每 4 秒读取一次状态\n游戏内 F6 识别，F7 刷新，Esc 关闭浮窗', bg=PANEL, fg=TEXT, justify='left').pack(padx=24, pady=20)
        for label, command in [('连接 / 刷新英雄  F7', self.refresh_client),
                               ('选择联盟安装目录', self.choose_install),
                               ('设置海克斯识别区域', self.configure_regions)]:
            ttk.Button(dialog, text=label, command=command).pack(fill='x', padx=24, pady=6)
        tk.Label(dialog, text=self.hotkeys.status, bg=PANEL, fg=MUTED).pack(padx=24, pady=16)

    def _save_settings(self):
        self.store._write('settings.json', self.settings)

    def configure_regions(self):
        dialog = tk.Toplevel(self.root)
        dialog.title('海克斯标题识别区域')
        dialog.configure(bg=PANEL)
        dialog.resizable(False, False)
        tk.Label(dialog, text='每行输入 x1, y1, x2, y2（0～1 屏幕比例）\n仅框选海克斯标题；首次使用请按实际分辨率校准。', bg=PANEL, fg=TEXT, justify='left').pack(padx=20, pady=16)
        entries = []
        for i, region in enumerate(self.recognizer.regions):
            frame = tk.Frame(dialog, bg=PANEL)
            frame.pack(fill='x', padx=20, pady=5)
            tk.Label(frame, text=('左侧', '中间', '右侧')[i], bg=PANEL, fg=MUTED).pack(side='left', padx=(0, 10))
            value = tk.StringVar(value=', '.join(map(str, region)))
            ttk.Entry(frame, textvariable=value, width=36).pack(side='left')
            entries.append(value)
        def preset():
            for value, region in zip(entries, DEFAULT_REGIONS):
                value.set(', '.join(map(str, region)))
        def save():
            try:
                regions = [tuple(float(x.strip()) for x in v.get().split(',')) for v in entries]
                self.recognizer = Recognizer(regions)
                self.settings['regions'] = regions
                self._save_settings()
                dialog.destroy()
            except ValueError as exc:
                messagebox.showerror('区域无效', str(exc), parent=dialog)
        ttk.Button(dialog, text='恢复 16:9 比例预设', command=preset).pack(pady=10)
        ttk.Button(dialog, text='保存区域', style='Gold.TButton', command=save).pack(pady=(0, 16))

    def open_source(self):
        hero = self.champions.get(self.selected_id)
        url = f'https://op.gg/zh-cn/lol/modes/aram-mayhem/{hero.slug}/augments' if hero else 'https://op.gg/zh-cn/lol/modes/aram-mayhem'
        webbrowser.open(url)

    def close(self):
        self.closed = True
        self.hotkeys.stop()
        self.hide_overlay()
        self.root.destroy()
