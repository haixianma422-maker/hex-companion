import ctypes
import os
import queue
import re
import threading
from ctypes import wintypes


DEFAULT_HOTKEYS = {'scan': 'F6', 'refresh': 'F7', 'toggle': 'F8'}
ACTION_NAMES = {'scan': '识别海克斯', 'refresh': '刷新资料', 'toggle': '展开 / 收起'}


def parse_hotkey(text):
    if not isinstance(text, str):
        raise ValueError('快捷键需要填写 F1～F12 或 Ctrl/Alt/Shift 组合')
    parts = [part.strip().upper() for part in text.split('+')]
    key, modifiers = parts[-1], parts[:-1]
    flags = {'CTRL': 2, 'ALT': 1, 'SHIFT': 4}
    if any(part not in flags for part in modifiers) or len(set(modifiers)) != len(modifiers):
        raise ValueError(f'快捷键无效：{text}')
    mods = sum(flags[part] for part in modifiers)
    if re.fullmatch(r'F(?:[1-9]|1[0-2])', key):
        vk = 0x6f + int(key[1:])
    elif re.fullmatch(r'[A-Z0-9]', key) and mods:
        vk = ord(key)
    else:
        raise ValueError('使用 F1～F12，或 Ctrl/Alt/Shift 加字母、数字')
    if key == 'F4' and 'ALT' in modifiers:
        raise ValueError('Alt+F4 是系统关闭快捷键，请换一个组合')
    name = '+'.join([part.title() for part in ('CTRL', 'ALT', 'SHIFT') if part in modifiers] + [key])
    return name, mods, vk


def normalize_bindings(values=None):
    merged = {**DEFAULT_HOTKEYS, **(values or {})}
    result = {action: parse_hotkey(merged[action])[0] for action in DEFAULT_HOTKEYS}
    if len(set(result.values())) != len(result):
        raise ValueError('三个功能不能使用相同快捷键')
    return result


class Hotkeys:
    def __init__(self, on_scan, on_refresh, on_close, on_toggle=None, bindings=None):
        self.callbacks = {1: on_scan, 2: on_refresh, 3: on_toggle or on_close}
        self.on_close = on_close
        self.status = '快捷键未启动'
        self._stop = threading.Event()
        self._overlay_visible = False
        self._paused = False
        self.commands = queue.Queue()
        self.registered = set()
        try:
            self.bindings = normalize_bindings(bindings)
        except (ValueError, TypeError):
            self.bindings = dict(DEFAULT_HOTKEYS)
            self.status = '已恢复默认快捷键：保存的快捷键格式无效'

    def summary(self):
        return f'{self.bindings["scan"]} 识别 · {self.bindings["refresh"]} 刷新 · {self.bindings["toggle"]} 展开/收起'

    def set_paused(self, paused):
        self._paused = paused
        if getattr(self, 'thread', None) and self.thread.is_alive():
            self.commands.put((None, None, None))

    def configure(self, values):
        bindings = normalize_bindings({**self.bindings, **values})
        if not getattr(self, 'thread', None) or not self.thread.is_alive():
            self.bindings = bindings
            return
        done, result = threading.Event(), {'lock': threading.Lock()}
        self.commands.put((bindings, done, result))
        if not done.wait(2):
            with result['lock']:
                if not done.is_set():
                    result['cancelled'] = True
                    raise ValueError('快捷键服务暂未响应，请稍后再试')
        if 'error' in result:
            raise ValueError(result['error'])

    def _apply_command(self, native, bindings, done, result):
        # Registration and cancellation share a lock: a timed-out queued request
        # cannot subsequently change runtime bindings after the dialog rejects it.
        with result['lock']:
            if result.get('cancelled'):
                return
            try:
                self._register(native, bindings)
            except ValueError as exc:
                result['error'] = str(exc)
            finally:
                if self._paused:
                    for ident in self.registered:
                        native.UnregisterHotKey(None, ident)
                    self.registered.clear()
                done.set()

    def _register(self, native, bindings, strict=True):
        old, previous = self.bindings, set(self.registered)
        for ident in previous:
            native.UnregisterHotKey(None, ident)
        self.registered.clear()
        failed = []
        for ident, action in enumerate(DEFAULT_HOTKEYS, 1):
            _, mods, vk = parse_hotkey(bindings[action])
            if native.RegisterHotKey(None, ident, 0x4000 | mods, vk):
                self.registered.add(ident)
            else:
                failed.append(bindings[action])
        if failed and strict:
            for ident in self.registered:
                native.UnregisterHotKey(None, ident)
            self.registered.clear()
            for ident in previous:
                action = list(DEFAULT_HOTKEYS)[ident - 1]
                _, mods, vk = parse_hotkey(old[action])
                if native.RegisterHotKey(None, ident, 0x4000 | mods, vk):
                    self.registered.add(ident)
            self.status = self.summary() if len(self.registered) == 3 else '部分快捷键被占用，请使用界面按钮'
            raise ValueError('快捷键被其他程序占用：' + '、'.join(failed) + '；已保留原设置')
        self.bindings = dict(bindings)
        self.status = self.summary() if not failed else '快捷键被占用：' + '、'.join(failed)

    def set_overlay_visible(self, visible):
        self._overlay_visible = visible

    def start(self):
        if os.name != 'nt':
            self.status = '当前平台请使用界面按钮'
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        user32 = ctypes.windll.user32
        try:
            self._register(user32, self.bindings, strict=False)
            message = wintypes.MSG()
            esc_down = False
            while not self._stop.wait(0.035):
                while not self.commands.empty():
                    bindings, done, result = self.commands.get_nowait()
                    if bindings is None:
                        if self._paused:
                            for ident in self.registered:
                                user32.UnregisterHotKey(None, ident)
                            self.registered.clear()
                        else:
                            self._register(user32, self.bindings, strict=False)
                        continue
                    self._apply_command(user32, bindings, done, result)
                while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                    if not self._paused and message.message == 0x0312 and message.wParam in self.callbacks:
                        self.callbacks[message.wParam]()
                down = bool(user32.GetAsyncKeyState(0x1B) & 0x8000)
                if down and not esc_down and self._overlay_visible and not self._paused:
                    self.on_close()
                esc_down = down
        finally:
            for ident in self.registered:
                user32.UnregisterHotKey(None, ident)

    def stop(self):
        self._stop.set()
        if getattr(self, 'thread', None) and self.thread is not threading.current_thread():
            self.thread.join(timeout=.5)
