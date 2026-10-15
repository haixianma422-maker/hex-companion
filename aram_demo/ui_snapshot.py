"""Capture a mapped Tk surface once, including its native editable controls."""
import ctypes
import os
from ctypes import wintypes as W
from PIL import Image


def snapshot(widget):
    if os.name != 'nt' or not widget.winfo_ismapped():
        return None
    window = widget.winfo_toplevel()
    window.update_idletasks()
    user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    user.GetDC.argtypes=[W.HWND]; user.GetDC.restype=W.HDC
    user.ReleaseDC.argtypes=[W.HWND,W.HDC]
    user.PrintWindow.argtypes=[W.HWND,W.HDC,W.UINT]
    gdi.CreateCompatibleDC.argtypes=[W.HDC]; gdi.CreateCompatibleDC.restype=W.HDC
    gdi.CreateCompatibleBitmap.argtypes=[W.HDC,ctypes.c_int,ctypes.c_int]; gdi.CreateCompatibleBitmap.restype=W.HBITMAP
    gdi.SelectObject.argtypes=[W.HDC,W.HGDIOBJ]; gdi.SelectObject.restype=W.HGDIOBJ
    gdi.DeleteObject.argtypes=[W.HGDIOBJ]; gdi.DeleteDC.argtypes=[W.HDC]
    class Header(ctypes.Structure):
        _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),('bits',W.WORD),
            ('compression',W.DWORD),('image_size',W.DWORD),('xppm',W.LONG),('yppm',W.LONG),('used',W.DWORD),('important',W.DWORD)]
    class Info(ctypes.Structure):
        _fields_=[('header',Header),('colors',W.DWORD*3)]
    gdi.GetDIBits.argtypes=[W.HDC,W.HBITMAP,W.UINT,W.UINT,ctypes.c_void_p,ctypes.POINTER(Info),W.UINT]
    hwnd=window.winfo_id(); width,height=window.winfo_width(),window.winfo_height()
    source=user.GetDC(hwnd); target=gdi.CreateCompatibleDC(source)
    bitmap=gdi.CreateCompatibleBitmap(source,width,height); previous=gdi.SelectObject(target,bitmap)
    try:
        if not user.PrintWindow(hwnd,target,3):
            return None
        info=Info(); info.header=Header(ctypes.sizeof(Header),width,-height,1,32,0,width*height*4,0,0,0,0)
        raw=ctypes.create_string_buffer(width*height*4)
        if gdi.GetDIBits(target,bitmap,0,height,raw,ctypes.byref(info),0)!=height:
            return None
        image=Image.frombytes('RGB',(width,height),raw.raw,'raw','BGRX').convert('RGBA')
        x=widget.winfo_rootx()-window.winfo_rootx(); y=widget.winfo_rooty()-window.winfo_rooty()
        return image.crop((x,y,x+widget.winfo_width(),y+widget.winfo_height()))
    finally:
        gdi.SelectObject(target,previous); gdi.DeleteObject(bitmap); gdi.DeleteDC(target); user.ReleaseDC(hwnd,source)
