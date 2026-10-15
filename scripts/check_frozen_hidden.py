"""Run the existing EXE self-test on a separate invisible Windows desktop."""
import ctypes
from ctypes import wintypes as W
from pathlib import Path
import subprocess
import sys
import os

if __name__=='__main__':
    exe,report=map(lambda value:Path(value).resolve(),sys.argv[1:3])
    user=ctypes.WinDLL('user32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.CreateDesktopW.argtypes=[W.LPCWSTR,W.LPCWSTR,ctypes.c_void_p,W.DWORD,W.DWORD,ctypes.c_void_p]
    user.CreateDesktopW.restype=W.HANDLE
    user.CloseDesktop.argtypes=[W.HANDLE]
    name='HexFrozenCheck-'+str(os.getpid())
    desktop=user.CreateDesktopW(name,None,None,0,0x01FF,None)
    if not desktop:raise ctypes.WinError(ctypes.get_last_error())
    class Startup(ctypes.Structure):
        _fields_=[('size',W.DWORD),('reserved',W.LPWSTR),('desktop',W.LPWSTR),('title',W.LPWSTR),
            ('x',W.DWORD),('y',W.DWORD),('width',W.DWORD),('height',W.DWORD),('chars_x',W.DWORD),
            ('chars_y',W.DWORD),('fill',W.DWORD),('flags',W.DWORD),('show',W.WORD),('reserved_size',W.WORD),
            ('reserved_bytes',ctypes.c_void_p),('stdin',W.HANDLE),('stdout',W.HANDLE),('stderr',W.HANDLE)]
    class Process(ctypes.Structure):
        _fields_=[('process',W.HANDLE),('thread',W.HANDLE),('pid',W.DWORD),('tid',W.DWORD)]
    kernel.CreateProcessW.argtypes=[W.LPCWSTR,W.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,W.BOOL,W.DWORD,
        ctypes.c_void_p,W.LPCWSTR,ctypes.POINTER(Startup),ctypes.POINTER(Process)]
    kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD]
    kernel.GetExitCodeProcess.argtypes=[W.HANDLE,ctypes.POINTER(W.DWORD)]
    kernel.CloseHandle.argtypes=[W.HANDLE]
    startup=Startup();startup.size=ctypes.sizeof(Startup);startup.desktop=name
    startup.flags=1;startup.show=0
    info=Process();command=ctypes.create_unicode_buffer(subprocess.list2cmdline([str(exe),'--self-test',str(report)]))
    try:
        if not kernel.CreateProcessW(str(exe),command,None,None,False,0,None,str(exe.parent),ctypes.byref(startup),ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        kernel.WaitForSingleObject(info.process,0xffffffff)
        code=W.DWORD();kernel.GetExitCodeProcess(info.process,ctypes.byref(code))
        print('Frozen self-test exit:',code.value)
        sys.exit(code.value)
    finally:
        if info.thread:kernel.CloseHandle(info.thread)
        if info.process:kernel.CloseHandle(info.process)
        user.CloseDesktop(desktop)
