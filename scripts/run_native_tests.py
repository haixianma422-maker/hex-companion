"""Run native UI tests on an invisible Windows desktop without stealing focus."""
import ctypes
import faulthandler
import gc
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


class NativeTestResult(unittest.TextTestResult):
    def stopTest(self, test):
        super().stopTest(test)
        # Collect finished fixtures on their owning thread before a
        # subsequent cache test starts a worker thread.
        gc.collect()

if __name__=='__main__':
    if os.name=='nt':
        from ctypes import wintypes as W
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.CreateDesktopW.argtypes=[W.LPCWSTR,W.LPCWSTR,ctypes.c_void_p,W.DWORD,W.DWORD,ctypes.c_void_p]
        user.CreateDesktopW.restype=W.HANDLE
        user.SetThreadDesktop.argtypes=[W.HANDLE]
        desktop=user.CreateDesktopW('HexMotionTests-'+str(os.getpid()),None,None,0,0x01FF,None)
        if not desktop or not user.SetThreadDesktop(desktop):
            raise ctypes.WinError(ctypes.get_last_error())
    faulthandler.dump_traceback_later(90,repeat=True)
    pattern=sys.argv[1] if len(sys.argv)>1 else 'test_*.py'
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=pattern)
    result=unittest.TextTestRunner(verbosity=2,resultclass=NativeTestResult).run(suite)
    faulthandler.cancel_dump_traceback_later()
    sys.exit(not result.wasSuccessful())
