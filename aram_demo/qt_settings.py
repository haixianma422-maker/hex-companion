"""The settings dialog: a Python form model with the Tk dialog's save rules, drawn by Settings.qml."""
from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtQml import QQmlComponent, QQmlEngine

from .cache import SOURCE_NAMES
from .hotkeys import DEFAULT_HOTKEYS, normalize_bindings, parse_hotkey
from .lcu import validate_install_path
from .qt_overlay import QML_DIR
from .recognition import DEFAULT_REGIONS, Recognizer

PAGES = ('common', 'shortcuts', 'advanced')
SIDES = ('左侧', '中间', '右侧')
EMPTY = '请选择'
PREVIEW_AUGMENTS = (1401, 1214, 1133)   # icons for the fixed region sketch


class SettingsDialog(QObject):
    """One open dialog. Edits stay in this form until save(); closing discards them."""
    changed = Signal()
    focusRequested = Signal(str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.source = app.store.source
        self.auto = bool(app.auto)
        self.animations = bool(app.settings.get('animations', True))
        self.choices = [next((a.name for a in app.augments
                              if any(m.slot == slot and m.augment_id == a.id for m in app.matches)), EMPTY)
                        for slot in range(3)]
        self.initial_choices = list(self.choices)
        self.hotkeys = dict(app.hotkeys.bindings)
        self.regions = [[str(value) for value in region] for region in app.recognizer.regions]
        self.initial_path = self.install_path = app.settings.get('install_path', '')
        self.opened_revision, self.opened_store = app.state.revision, app.store
        self.page_errors = dict.fromkeys(PAGES, '')
        self.field_errors = {}
        self.tab = 0
        self.applied = False
        self.window = None
        app.panel.assets.resolved.connect(self.changed)

    # ---- CompanionApp interface -------------------------------------------
    def open(self, slot=None):
        self.app.hotkeys.set_paused(True)
        engine = self.app.overlay.engine
        engine.rootContext().setContextProperty('settings', self)
        self.component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / 'Settings.qml')))
        self.window = self.component.create()
        if self.window is None:
            self.app.hotkeys.set_paused(False)
            raise RuntimeError('设置界面加载失败：' + self.component.errorString())
        # Without this the QML garbage collector may delete a window nothing in QML refers to.
        QQmlEngine.setObjectOwnership(self.window, QQmlEngine.CppOwnership)
        self.focus_manual(slot)

    def focus_manual(self, slot):
        if isinstance(slot, int) and 0 <= slot < 3:
            self.select_tab(0)
            self.focusRequested.emit(f'choice.{slot}')
        if self.window is not None:
            self.window.raise_()
            self.window.requestActivate()

    def close(self):
        if self.window is not None:
            window, self.window = self.window, None
            window.close()
            window.deleteLater()
        if self.app.dialog is self:
            self.app.dialog = None
            self.app.panel.assets.resolved.disconnect(self.changed)
        self.app.hotkeys.set_paused(False)

    def connection_changed(self):
        self.changed.emit()

    def refresh_icons(self):
        self.changed.emit()

    def set_source(self, source):
        self.source = source
        self.changed.emit()

    # ---- form ------------------------------------------------------------------
    def set_value(self, key, value):
        if key == 'source':
            self.source = value
        elif key in ('auto', 'animations'):
            setattr(self, key, bool(value))
        elif key.startswith('choice.'):
            self.choices[int(key[7:])] = value
        elif key.startswith('hotkey.'):
            self.hotkeys[key[7:]] = value
        elif key.startswith('region.'):
            row, column = map(int, key[7:].split('.'))
            self.regions[row][column] = value
        elif key == 'path':
            self.install_path = value
            self.field_errors.pop('path', None)
        self.applied = False
        self.changed.emit()

    def reset_hotkeys(self):
        """Restores the defaults in the form; save() applies them."""
        self.hotkeys = dict(DEFAULT_HOTKEYS)
        self.page_errors['shortcuts'] = ''
        for action in DEFAULT_HOTKEYS:
            self.field_errors.pop('hotkey.' + action, None)
        self.changed.emit()

    def reset_regions(self):
        self.regions = [[str(value) for value in region] for region in DEFAULT_REGIONS]
        self.page_errors['advanced'] = ''
        for row in range(3):
            self.field_errors.pop(f'region.{row}', None)
        self.changed.emit()

    def select_tab(self, index):
        self.tab = index
        self.changed.emit()

    def _fail(self, page, field, message, fields=()):
        self.page_errors[page] = message
        for name in fields or (field,):
            self.field_errors[name] = message
        self.select_tab(PAGES.index(page))
        self.focusRequested.emit(field)

    def save(self):
        """The Tk dialog's save boundary: validate everything, then write once."""
        app = self.app
        self.page_errors = dict.fromkeys(PAGES, '')
        self.field_errors = {}
        self.changed.emit()
        if self.source not in SOURCE_NAMES:
            self._fail('common', 'source', '请选择 OP.GG 或 101 数据站')
            return False
        source_changed = self.source != app.store.source
        parsed_regions = []
        for index, values in enumerate(self.regions):
            try:
                region = tuple(float(value.strip()) for value in values)
                x1, y1, x2, y2 = region
                if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                    raise ValueError('坐标需在 0–1 内，且 x1<x2、y1<y2')
            except ValueError as exc:
                self._fail('advanced', f'region.{index}.0', SIDES[index] + '区域：' + str(exc), [f'region.{index}'])
                return False
            parsed_regions.append(region)
        recognizer = Recognizer(parsed_regions)
        path_changed = self.install_path != self.initial_path
        if path_changed:
            try:
                validate_install_path(self.install_path)
            except ValueError as exc:
                self._fail('advanced', 'path', str(exc))
                return False
        old_bindings = dict(app.hotkeys.bindings)
        try:
            bindings = normalize_bindings(dict(self.hotkeys))
            app.hotkeys.configure(bindings)
        except ValueError as exc:
            invalid, parsed = [], {}
            for action, value in self.hotkeys.items():
                try:
                    parsed[action] = parse_hotkey(value)[0]
                except ValueError:
                    invalid.append(action)
            duplicates = [action for action, value in parsed.items() if list(parsed.values()).count(value) > 1]
            occupied = [action for action, value in parsed.items() if value in str(exc)]
            invalid = invalid or duplicates or occupied or list(DEFAULT_HOTKEYS)
            self._fail('shortcuts', 'hotkey.' + invalid[0], str(exc), ['hotkey.' + action for action in invalid])
            return False
        settings = dict(app.settings, regions=recognizer.regions, auto_recognize=self.auto,
                        animations=self.animations, hotkeys=bindings, data_source=self.source)
        if path_changed:
            settings['install_path'] = self.install_path
        try:
            app.store._write('settings.json', settings)
        except OSError as exc:
            try:
                app.hotkeys.configure(old_bindings)
            except ValueError as rollback_error:
                self._fail('common', 'source', f'设置未能保存：{exc}；快捷键恢复失败：{rollback_error}')
            else:
                self._fail('common', 'source', '设置未能保存：' + str(exc))
            return False
        app.settings, app.recognizer, app.auto = settings, recognizer, self.auto
        app.panel.set_hotkeys(bindings)
        app.panel.set_motion(self.animations)
        app.bubble.set_motion(self.animations)
        app.bubble.set_hotkeys(bindings)
        app.ocr_epoch += 1
        selected = [value.strip() if value != EMPTY else '' for value in self.choices]
        opened = [value if value != EMPTY else '' for value in self.initial_choices]
        if (not source_changed and app.store is self.opened_store and
                selected != opened and self.opened_revision == app.state.revision):
            app.apply_manual(selected)
        if source_changed:
            app.change_source(self.source)
        app.status = app.cache_status()
        app.present()
        if path_changed:
            app.refresh()
        self.hotkeys = dict(bindings)
        self.applied = True
        self.changed.emit()
        return True

    # ---- QML interface -----------------------------------------------------
    @Property('QVariantMap', notify=changed)
    def form(self):
        app = self.app
        phase = getattr(app.state, 'phase', 'Disconnected')
        first = app.connection_text.splitlines()[0] if app.connection_text else ''
        if phase == 'Disconnected':
            connection, tone = first or '等待客户端连接', 'muted'
        elif phase in ('Error', 'Failed'):
            connection, tone = first, 'error'
        else:
            connection, tone = first or phase, 'accent'
        icons = {a.name: self._icon(a.id) for a in app.augments}
        return {
            'tab': self.tab, 'source': self.source, 'auto': self.auto, 'animations': self.animations,
            'choices': self.choices, 'choiceIcons': [icons.get(name, '') for name in self.choices],
            'options': [EMPTY] + [a.name for a in app.augments],
            'optionIcons': [''] + [icons.get(a.name, '') for a in app.augments],
            'hotkeys': [self.hotkeys[action] for action in DEFAULT_HOTKEYS],
            'scanKey': app.hotkeys.bindings['scan'],
            'regions': self.regions,
            'regionIcons': [self._icon(aid) for aid in PREVIEW_AUGMENTS],
            'path': self.install_path,
            'errors': [self.page_errors[page] for page in PAGES],
            'fieldErrors': dict(self.field_errors),
            'connection': connection, 'connectionTone': tone,
            'applied': self.applied,
        }

    def _icon(self, augment_id):
        # Validated off the GUI thread by the panel's resolver; '' until it answers.
        assets = self.app.visual_assets
        return self.app.panel.assets.url(('augment', augment_id), lambda: assets.path('augment', augment_id))

    @Slot(str, 'QVariant')
    def setValue(self, key, value):
        self.set_value(key, value)

    @Slot(QUrl)
    def choosePath(self, url):
        self.set_value('path', url.toLocalFile())

    @Slot(int)
    def selectTab(self, index):
        self.select_tab(index)

    @Slot()
    def resetHotkeys(self):
        self.reset_hotkeys()

    @Slot()
    def resetRegions(self):
        self.reset_regions()

    @Slot()
    def apply(self):
        self.save()

    @Slot()
    def dismiss(self):
        self.close()


def show_settings(app, slot=None):
    if app.dialog is not None:
        app.dialog.focus_manual(slot)
        return
    app.dialog = SettingsDialog(app)
    app.dialog.open(slot)
