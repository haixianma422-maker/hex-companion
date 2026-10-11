"""Read League window geometry; only style this application's own windows."""
import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueWindow:
    hwnd: int
    rect: tuple[int, int, int, int]
    work_area: tuple[int, int, int, int]
    foreground: bool = False


def panel_position(anchor, work, width=300, height=560):
    left, top, right, bottom = work
    x = anchor[2] + 12
    if x + width > right:
        x = min(anchor[2], right) - width - 12
    return max(left, min(x, right - width)), max(top, min(anchor[1], bottom - height))


def _user32():
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    return user


def foreground_is_ours():
    if os.name != 'nt':
        return False
    user = _user32()
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(user.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value == os.getpid()


def find_league_window(stage):
    if os.name != 'nt':
        return None
    user = _user32()
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    names, found = {}, []
    wanted = 'league of legends.exe' if stage == 'game' else 'leagueclientux.exe'

    @callback_type
    def collect(hwnd, unused):
        if not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in names:
            names[pid.value] = ''
            handle = kernel.OpenProcess(0x1000, False, pid.value)
            if handle:
                try:
                    size = wintypes.DWORD(32768)
                    buffer = ctypes.create_unicode_buffer(size.value)
                    if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                        names[pid.value] = os.path.basename(buffer.value).casefold()
                finally:
                    kernel.CloseHandle(handle)
        if names[pid.value] == wanted:
            rect = wintypes.RECT()
            if user.GetWindowRect(hwnd, ctypes.byref(rect)) and rect.right - rect.left > 300 and rect.bottom - rect.top > 200:
                found.append((hwnd, (rect.left, rect.top, rect.right, rect.bottom)))
        return True
    user.EnumWindows(collect, 0)
    if not found:
        return None
    foreground = user.GetForegroundWindow()
    hwnd, rect = max(found, key=lambda row: (row[0] == foreground, (row[1][2] - row[1][0]) * (row[1][3] - row[1][1])))

    class MonitorInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]
    user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user.MonitorFromWindow.restype = wintypes.HANDLE
    user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    user.GetMonitorInfoW(user.MonitorFromWindow(hwnd, 2), ctypes.byref(info))
    work = info.rcWork
    return LeagueWindow(hwnd, rect, (work.left, work.top, work.right, work.bottom), hwnd == foreground)


def prepare_popup(window):
    if os.name != 'nt':
        return
    window.update_idletasks()
    user = _user32()
    hwnd = user.GetAncestor(window.winfo_id(), 2)
    get_style = user.GetWindowLongPtrW
    set_style = user.SetWindowLongPtrW
    get_style.argtypes, get_style.restype = [wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t
    set_style.argtypes, set_style.restype = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t
    set_style(hwnd, -20, get_style(hwnd, -20) | 0x08000000 | 0x00000080)


def single_instance():
    """Keep handle alive for process lifetime; no files or registry changes."""
    if os.name != 'nt':
        return True
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel.CreateMutexW(None, False, 'Local\\HexCompanionOPGG')
    return handle if ctypes.get_last_error() != 183 else None
