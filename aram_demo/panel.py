"""Compact, glanceable surfaces for champion selection and gameplay."""
import tkinter as tk
import os
from .builds import six_item_reference
from .models import augment_label, sort_champions
from .theme import (ACCENT, BG, GOLD, GRADES, GRADE_BACKGROUNDS, LINE, MUTED,
                    SURFACE, TEXT, TIER_BG, NEUTRAL_BG, Card, ScrollArea, button, configure_styles, label)
from .windows import panel_position, prepare_popup


class CompanionPanel:
    def __init__(self, root, on_scan, on_settings, on_hide, on_preview=None):
        configure_styles(root)
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title('海克斯随行 · 伴随浮窗')
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        transparent = '#010203'
        self.window.configure(bg=transparent)
        if os.name == 'nt':
            self.window.attributes('-transparentcolor', transparent)
        self.visible, self.signature = False, None
        self.context = None
        self._scroll_job = None
        self.window.bind('<Destroy>', lambda event: self._cancel_scroll() if event.widget == self.window else None)
        self.offset = self.base = (0, 0)
        self._geometry = None
        self.width, self.height = 304, 480
        self.on_scan, self.on_settings, self.on_hide = on_scan, on_settings, on_hide
        self.on_preview = on_preview
        self.shell = Card(self.window, color=BG, padding=8, radius=20)
        self.shell.pack(fill='both', expand=True)
        self.inner = self.shell.body
        prepare_popup(self.window)

    label = staticmethod(label)

    def button(self, parent, text, command, gold=False):
        return button(parent, text, command, primary=gold)

    def section(self, parent, title, detail=''):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill='x', pady=(10, 6))
        label(row, title, GOLD, 10, True).pack(side='left')
        caption = label(row, detail, MUTED, 9)
        caption.pack(side='right')
        return caption

    def badge(self, parent, text, color=GOLD, background=TIER_BG, large=False, compact=False):
        badge = Card(parent, color=background, padding=5 if compact else 6, radius=9)
        badge.caption = label(badge.body, text, color, (18 if compact else 20) if large else 11, True,
                              width=2 if large else 3)
        badge.caption.pack()
        return badge

    @staticmethod
    def _set(widget, **values):
        changed = {key: value for key, value in values.items() if str(widget.cget(key)) != str(value)}
        if changed:
            widget.configure(**changed)

    def render(self, state, champions, data, matches, status, preview=False, scanning=False):
        signature = (state.stage, state.champion_id, tuple(state.candidate_ids),
                     (data or {}).get('fetched_at'),
                     tuple((m.slot, m.augment_id, m.status, m.text if m.augment_id is None else '') for m in matches),
                     preview)
        if self.context and self.context[0] == state.stage:
            if self.context[1] != state.champion_id:
                self.content.canvas.yview_moveto(0)
            self.context = (state.stage, state.champion_id)
            self.signature = signature
            self._set(self.mode_label, text='模拟预览' if preview else '海克斯大乱斗')
            self._update_hero(champions.get(state.champion_id), state.champion_id)
            if state.stage == 'game':
                self._update_game(data, matches)
            else:
                self._update_candidates(state, champions)
            self._activity(status, scanning)
            return
        self._cancel_scroll()
        context = (state.stage, state.champion_id)
        scroll_position = self.content.canvas.yview()[0] if hasattr(self, 'content') and self.context == context else 0
        self.context = context
        self.signature = signature
        for child in self.inner.winfo_children():
            child.destroy()
        self.height = 780 if state.stage == 'game' else 480
        self._header(state, preview)
        self._hero(champions.get(state.champion_id), state.champion_id, compact=state.stage == 'game')
        foot = tk.Frame(self.inner, bg=BG)
        foot.pack(side='bottom', fill='x', padx=10, pady=(6, 4))
        actions = tk.Frame(foot, bg=BG)
        actions.pack(fill='x')
        self.scan_button = None
        if self.on_preview:
            caption = '查看选人预览' if state.stage == 'game' else '查看局内预览'
            button(actions, caption, self.on_preview, primary=True).pack(side='left')
        elif state.stage == 'game':
            self.scan_button = button(actions, '识别海克斯  F6', self.on_scan, primary=True)
            self.scan_button.pack(side='left')
        else:
            label(actions, '随客户端自动更新', MUTED, 9).pack(side='left', pady=8)
        button(actions, '设置', self.on_settings).pack(side='right')
        self.status_label = label(foot, '', MUTED, 9, wraplength=270, anchor='w', justify='left', height=2)
        self.status_label.pack(fill='x', pady=(7, 0))
        self.activity = None
        self._activity(status, scanning)
        self.content = ScrollArea(self.inner)
        self.content.pack(fill='both', expand=True, padx=10)
        if state.stage in ('select', 'lobby'):
            self._candidates(self.content.body, state, champions)
        elif state.stage == 'game':
            self._game(self.content.body, data, matches)
        self.content.bind_wheel()
        content = self.content
        def restore_scroll():
            self._scroll_job = None
            if content.winfo_exists():
                content.canvas.yview_moveto(scroll_position)
        self._scroll_job = self.window.after_idle(restore_scroll)

    def _activity(self, status, scanning):
        if (status, scanning) == self.activity:
            return
        self.activity = (status, scanning)
        self._set(self.status_label, text=status)
        # Background scans never blink the button or replace its caption.
        # CompanionApp.scan already rejects a second concurrent request.

    def _cancel_scroll(self):
        if self._scroll_job is not None:
            self.window.after_cancel(self._scroll_job)
            self._scroll_job = None

    def _header(self, state, preview):
        bar = tk.Frame(self.inner, bg=BG)
        bar.pack(fill='x', padx=10, pady=(4, 4))
        mark = tk.Canvas(bar, width=26, height=28, bg=BG, highlightthickness=0)
        mark.create_polygon(13, 2, 24, 8, 24, 20, 13, 26, 2, 20, 2, 8,
                            outline=GOLD, fill=BG, width=1.5)
        mark.create_line(9, 9, 9, 19, 9, 14, 17, 14, 17, 9, 17, 19, fill=ACCENT, width=2)
        mark.pack(side='left', padx=(0, 8))
        title = label(bar, '海克斯随行', GOLD, 11, True)
        title.pack(side='left')
        button(bar, '收起', self.on_hide).pack(side='right')
        origin = [0, 0]
        def begin(event):
            origin[:] = [event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y()]
        def drag(event):
            x, y = event.x_root - origin[0], event.y_root - origin[1]
            self.offset = (x - self.base[0], y - self.base[1])
            self.window.geometry(f'{x:+d}{y:+d}')
        for widget in (bar, mark, title):
            widget.bind('<ButtonPress-1>', begin)
            widget.bind('<B1-Motion>', drag)
        meta = tk.Frame(self.inner, bg=BG)
        meta.pack(fill='x', padx=10, pady=(0, 10))
        phase = {'lobby': '等待选人', 'select': '选人阶段', 'game': '对局中'}.get(state.stage, '')
        label(meta, phase, ACCENT, 9).pack(side='left')
        self.mode_label = label(meta, '模拟预览' if preview else '海克斯大乱斗', MUTED, 9)
        self.mode_label.pack(side='right')

    def _hero(self, hero, champion_id, compact=False):
        card = Card(self.inner, padding=12)
        card.pack(fill='x', padx=10)
        self.hero_badge = self.badge(card.body, '—', large=True)
        self.hero_badge.pack(side='right', padx=(8, 0))
        details = tk.Frame(card.body, bg=SURFACE)
        details.pack(side='left', fill='x', expand=True)
        if not compact:
            label(details, '当前英雄', MUTED, 9, anchor='w').pack(fill='x')
        self.hero_name = label(details, '', TEXT, 13, True, wraplength=180, justify='left', anchor='w')
        self.hero_name.pack(fill='x', pady=(3, 3))
        self.hero_meta = label(details, '', MUTED, 9, anchor='w')
        self.hero_meta.pack(fill='x')
        self._update_hero(hero, champion_id)

    def _update_hero(self, hero, champion_id):
        unknown = f'英雄 ID {champion_id}' if champion_id else '等待读取英雄'
        self._set(self.hero_name, text=hero.name if hero else unknown)
        self._set(self.hero_badge.caption, text=hero.tier_label if hero and hero.tier is not None else '—')
        meta = f'OP.GG  #{hero.rank}' if hero and hero.rank else '暂无排名'
        if not hero or hero.tier is None:
            meta = '暂无档位 · ' + meta
        self._set(self.hero_meta, text=meta)

    def _candidates(self, parent, state, champions):
        self.candidate_count = self.section(parent, '可选英雄')
        self.candidate_views = {}
        self.candidate_order = None
        self.candidate_empty = Card(parent)
        label(self.candidate_empty.body, '等待候选英雄', TEXT, 10, True, anchor='w').pack(fill='x')
        label(self.candidate_empty.body, '进入选人后，自动显示可选英雄的梯队。', MUTED, 9,
              wraplength=240, anchor='w', justify='left').pack(fill='x', pady=(6, 0))
        self._update_candidates(state, champions)

    def _update_candidates(self, state, champions):
        rows = sort_champions([champions[c] for c in state.candidate_ids if c in champions])
        unknown_ids = [c for c in state.candidate_ids if c not in champions]
        order = tuple([hero.id for hero in rows] + unknown_ids)
        self._set(self.candidate_count, text=f'{len(order)} 位 · 按梯队排序')
        for cid in order:
            hero = champions.get(cid)
            if cid not in self.candidate_views:
                row = Card(self.content.body, padding=9)
                badge = self.badge(row.body, '—')
                badge.pack(side='left', padx=(0, 9))
                rank = label(row.body, '', MUTED, 9)
                rank.pack(side='right')
                name = label(row.body, '', TEXT, 10, wraplength=144, anchor='w', justify='left')
                name.pack(side='left', fill='x', expand=True)
                self.candidate_views[cid] = (row, badge, rank, name)
            row, badge, rank, name = self.candidate_views[cid]
            self._set(name, text=hero.name if hero else f'英雄 ID {cid}')
            self._set(badge.caption, text=hero.tier_label if hero and hero.tier is not None else '—',
                      fg=GOLD if hero and hero.tier == 1 else TEXT)
            badge.set_color(TIER_BG if hero and hero.tier == 1 else NEUTRAL_BG)
            ranking = (f'#{hero.rank}' if hero.rank else '—') if hero and hero.tier is not None else ('暂无档位' if hero else '未知档位')
            self._set(rank, text=ranking)
        if order != self.candidate_order:
            self.candidate_empty.pack_forget()
            for row, *_ in self.candidate_views.values():
                row.pack_forget()
            for cid in order:
                self.candidate_views[cid][0].pack(fill='x', pady=(0, 6))
            if not order:
                self.candidate_empty.pack(fill='x')
            self.candidate_order = order
            self.content.bind_wheel()

    def _game(self, parent, data, matches):
        self.section(parent, '海克斯推荐', '当前英雄适配评级')
        self.augment_views = []
        for slot in range(3):
            card = Card(parent, padding=5)
            card.pack(fill='x', pady=(0, 4))
            badge = self.badge(card.body, '—', MUTED, NEUTRAL_BG, large=True, compact=True)
            badge.pack(side='left', padx=(0, 10))
            detail = tk.Frame(card.body, bg=SURFACE)
            detail.pack(side='left', fill='x', expand=True)
            name = label(detail, '', TEXT, 10, True, wraplength=186, anchor='w', justify='left', height=2)
            name.pack(fill='x')
            hint = label(detail, '', MUTED, 9, anchor='w')
            hint.pack(fill='x')
            self.augment_views.append((card, badge, name, hint))
        self.build_heading = self.section(parent, '推荐出装', '六件套 · 含鞋子')
        self.build_card = Card(parent, padding=0)
        self.build_card.pack(fill='x')
        self.build_views = []
        self.build_card.body.configure(bg=BG)
        self.build_card.back.place_forget()
        for index in range(6):
            row = Card(self.build_card.body, padding=7, radius=14)
            row.grid(row=index // 3, column=index % 3, sticky='nsew', padx=(0, 4) if index % 3 < 2 else (0, 0), pady=(0, 6))
            number = label(row.body, f'{index + 1:02}', ACCENT, 8, anchor='w')
            number.pack(fill='x')
            name = label(row.body, '', TEXT, 9, anchor='w', justify='left', wraplength=78, height=3)
            name.pack(fill='x', pady=(3, 0))
            self.build_views.append((row, name, number))
        for column in range(3):
            self.build_card.body.columnconfigure(column, weight=1, uniform='items')
        self.build_note = label(parent, '', MUTED, 9, wraplength=266, anchor='w', justify='left', height=2)
        self.build_note.pack(fill='x', pady=(2, 4))
        self._update_game(data, matches)

    def _update_game(self, data, matches):
        augment_index = {a['id']: a for a in (data or {}).get('augments', [])}
        for slot in range(3):
            match = next((m for m in matches if m.slot == slot), None)
            augment = augment_index.get(match.augment_id) if match else None
            tier = augment.get('tier') if augment else None
            grade = augment_label(tier, (data or {}).get('tier_labels')) if augment else '—'
            known = isinstance(tier, int) and 0 <= tier < 6
            if not known:
                grade = '—'
            color = GRADES[tier] if known else MUTED
            backdrop = GRADE_BACKGROUNDS[tier] if known else NEUTRAL_BG
            card, badge, name_label, hint_label = self.augment_views[slot]
            self._set(badge.caption, text=grade, fg=color)
            badge.set_color(backdrop)
            name = augment['name'] if augment else (match.text if match and match.text else '等待海克斯选项')
            self._set(name_label, text=name)
            hint = ('已匹配' if known else '暂无评级') if augment else ('待确认' if match and match.text else '等待识别')
            self._set(hint_label, text=('左侧', '中间', '右侧')[slot] + '  ·  ' + hint)
        items = six_item_reference(data)
        for index, (_, name, number) in enumerate(self.build_views):
            item = items[index] if index < len(items) else None
            self._set(name, text=item['name'] if item else '等待装备数据', fg=TEXT if item else MUTED)
            self._set(number, text=f'{index + 1:02}  {item["role"]}' if item else f'{index + 1:02}')
        caption = '六件套 · 含鞋子' if any(item['role'] == '鞋子' for item in items) else '六件套参考'
        self._set(self.build_heading, text=caption if len(items) == 6 else f'{len(items)}/6 已有数据')
        mode_verified = (data or {}).get('build_mode_verified') and (data or {}).get('build_mode') == 'aram-mayhem'
        self._set(self.build_note, text=('海克斯大乱斗 · OP.GG 模式出装\n核心＋鞋子＋后续装备参考' if mode_verified else
                                       'OP.GG 装备参考\n模式尚未校验 · 请刷新资料'))

    def show_at(self, anchor):
        work = anchor.work_area
        preferred_height = 780 if self.context and self.context[0] == 'game' else 480
        self.height = min(preferred_height, work[3] - work[1] - 24)
        self.base = panel_position(anchor.rect, work, self.width, self.height)
        x = max(work[0], min(self.base[0] + self.offset[0], work[2] - self.width))
        y = max(work[1], min(self.base[1] + self.offset[1], work[3] - self.height))
        geometry = f'{self.width}x{self.height}{x:+d}{y:+d}'
        if geometry != self._geometry:
            self.window.geometry(geometry)
            self._geometry = geometry
        if not self.visible:
            self.window.deiconify()
            self.visible = True

    def hide(self):
        if self.visible:
            self.window.withdraw()
            self.visible = False

    def content_text(self):
        def labels(widget):
            result = [str(widget.cget('text'))] if isinstance(widget, (tk.Label, tk.Button)) else []
            for child in widget.winfo_children():
                result.extend(labels(child))
            return result
        return '\n'.join(labels(self.inner))
