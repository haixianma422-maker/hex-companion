"""Local production diagnostics without credentials or captured images."""
import ctypes
import json
import logging
import os
import threading
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure(root):
    logger = logging.getLogger('aram_demo')
    logger.setLevel(logging.INFO)
    path = Path(root) / 'logs' / 'runtime.log'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    except OSError:
        logger.warning('运行日志不可写')
        return None
    for old in list(logger.handlers):
        if getattr(old, '_hex_runtime', False):
            logger.removeHandler(old)
            old.close()
    handler._hex_runtime = True
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    logger.addHandler(handler)
    logger.propagate = False
    return path


def health():
    values = {'threads': threading.active_count()}
    if os.name == 'nt':
        class Memory(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD),
                        *[(name, ctypes.c_size_t) for name in
                          ('peak_rss', 'rss', 'peak_paged', 'paged', 'peak_nonpaged',
                           'nonpaged', 'pagefile', 'peak_pagefile')]]
        try:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            psapi = ctypes.WinDLL('psapi', use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            process = kernel.GetCurrentProcess()
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Memory), wintypes.DWORD]
            memory = Memory()
            memory.cb = ctypes.sizeof(memory)
            if psapi.GetProcessMemoryInfo(process, ctypes.byref(memory), memory.cb):
                values['rss_mb'] = round(memory.rss / 1024**2, 2)
            kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            handles = wintypes.DWORD()
            if kernel.GetProcessHandleCount(process, ctypes.byref(handles)):
                values['handles'] = handles.value
        except (OSError, AttributeError):
            pass
    logging.getLogger(__name__).info('health %s', json.dumps(values, sort_keys=True))
    return values
