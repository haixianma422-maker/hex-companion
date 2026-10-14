"""Event-driven, click-through Win32 outer shadows for borderless Tk windows."""
import ctypes
import os
import tkinter as tk
from ctypes import wintypes as W
from PIL import Image, ImageDraw, ImageFilter

_KEEP=[]
_CLASS=None

def _api():
    global _CLASS
    u=ctypes.WinDLL('user32',use_last_error=True); g=ctypes.WinDLL('gdi32',use_last_error=True)
    proto=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
    class WC(ctypes.Structure):
        _fields_=[('style',W.UINT),('proc',proto),('cls',ctypes.c_int),('wnd',ctypes.c_int),('instance',W.HINSTANCE),('icon',W.HICON),('cursor',W.HANDLE),('brush',W.HBRUSH),('menu',W.LPCWSTR),('name',W.LPCWSTR)]
    u.DefWindowProcW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.DefWindowProcW.restype=ctypes.c_ssize_t
    if _CLASS is None:
        callback=proto(lambda hwnd,msg,wp,lp:u.DefWindowProcW(hwnd,msg,wp,lp))
        wc=WC();wc.proc=callback;wc.name='HexCompanionShadow'+str(os.getpid())
        u.RegisterClassW.argtypes=[ctypes.POINTER(WC)];u.RegisterClassW.restype=W.ATOM
        if not u.RegisterClassW(ctypes.byref(wc)):raise ctypes.WinError(ctypes.get_last_error())
        _CLASS=wc.name;_KEEP.extend([callback,wc])
    u.CreateWindowExW.argtypes=[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.HWND,W.HMENU,W.HINSTANCE,ctypes.c_void_p]
    u.CreateWindowExW.restype=W.HWND
    u.GetAncestor.argtypes=[W.HWND,W.UINT];u.GetAncestor.restype=W.HWND
    u.SetWindowPos.argtypes=[W.HWND,W.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.UINT]
    u.DestroyWindow.argtypes=[W.HWND];u.ShowWindow.argtypes=[W.HWND,ctypes.c_int]
    u.GetDC.argtypes=[W.HWND];u.GetDC.restype=W.HDC
    u.ReleaseDC.argtypes=[W.HWND,W.HDC]
    g.CreateCompatibleDC.argtypes=[W.HDC];g.CreateCompatibleDC.restype=W.HDC
    g.SelectObject.argtypes=[W.HDC,W.HANDLE];g.SelectObject.restype=W.HANDLE
    g.DeleteObject.argtypes=[W.HANDLE];g.DeleteDC.argtypes=[W.HDC]
    return u,g

class Shadow:
    def __init__(self,window,scale,radius):
        self.window,self.scale,self.radius=window,scale,radius
        self.hwnd=None;self.job=None;self.error='';self._size=None;self._pixels=None
        if os.name!='nt':return
        try:
            self.u,self.g=_api()
            # LAYERED | TRANSPARENT | NOACTIVATE | TOOLWINDOW | TOPMOST.
            self.hwnd=self.u.CreateWindowExW(0x080800A8,_CLASS,'',0x80000000,0,0,1,1,None,None,None,None)
            if not self.hwnd:raise ctypes.WinError(ctypes.get_last_error())
            for event in ('<Configure>','<Map>'):
                window.bind(event,self._schedule,add='+')
            window.bind('<Unmap>',self._unmap,add='+');window.bind('<Destroy>',self._destroy,add='+')
            self._schedule()
        except (OSError,AttributeError,TypeError) as exc:self.error=str(exc);self.destroy()
    def _schedule(self,event=None):
        if event is not None and event.widget is not self.window:return
        if self.hwnd and self.job is None:self.job=self.window.after_idle(self.sync)
    def _unmap(self,event):
        if event.widget is self.window:self.hide()
    def _destroy(self,event):
        if event.widget is self.window:self.destroy()
    def sync(self):
        self.job=None
        if not self.hwnd:return
        try:
            if not self.window.winfo_ismapped():self.hide();return
            w,h=self.window.winfo_width(),self.window.winfo_height()
            if min(w,h)<2:return
            pad=round(36*self.scale);dy=round(6*self.scale)
            size=(w,h)
            if size!=self._size:
                mask=Image.new('L',(w+2*pad,h+2*pad));d=ImageDraw.Draw(mask)
                d.rounded_rectangle((pad,pad+dy,pad+w-1,pad+h-1+dy),radius=round(self.radius*self.scale),fill=36)
                mask=mask.filter(ImageFilter.GaussianBlur(18*self.scale))
                # Opaque owner interior does not need an overlapping shadow surface.
                ImageDraw.Draw(mask).rounded_rectangle((pad,pad,pad+w-1,pad+h-1),radius=round(self.radius*self.scale),fill=0)
                art=Image.new('RGBA',mask.size,(0,0,0,0));art.putalpha(mask)
                self._pixels=(art.size,art.tobytes('raw','BGRA'));self._size=size
            x,y=self.window.winfo_rootx()-pad,self.window.winfo_rooty()-pad
            self._upload(x,y)
            owner=self.u.GetAncestor(self.window.winfo_id(),2)
            self.u.SetWindowPos(self.hwnd,owner,x,y,w+2*pad,h+2*pad,0x0010|0x0040)
        except (OSError,AttributeError,tk.TclError,ValueError) as exc:self.error=str(exc);self.hide()
    def _upload(self,x,y):
        class Header(ctypes.Structure):
            _fields_=[('size',W.DWORD),('w',W.LONG),('h',W.LONG),('planes',W.WORD),('bits',W.WORD),('compression',W.DWORD),('image',W.DWORD),('xp',W.LONG),('yp',W.LONG),('used',W.DWORD),('important',W.DWORD)]
        class Info(ctypes.Structure):_fields_=[('header',Header),('colors',W.DWORD*3)]
        class Blend(ctypes.Structure):_fields_=[('op',ctypes.c_ubyte),('flags',ctypes.c_ubyte),('alpha',ctypes.c_ubyte),('format',ctypes.c_ubyte)]
        (w,h),raw=self._pixels
        info=Info();info.header=Header(ctypes.sizeof(Header),w,-h,1,32,0,len(raw),0,0,0,0)
        bits=ctypes.c_void_p();screen=self.u.GetDC(None);memory=self.g.CreateCompatibleDC(screen)
        self.g.CreateDIBSection.argtypes=[W.HDC,ctypes.POINTER(Info),W.UINT,ctypes.POINTER(ctypes.c_void_p),W.HANDLE,W.DWORD];self.g.CreateDIBSection.restype=W.HBITMAP
        bitmap=None;old=None
        try:
            bitmap=self.g.CreateDIBSection(screen,ctypes.byref(info),0,ctypes.byref(bits),None,0)
            if not bitmap or not bits.value:raise ctypes.WinError(ctypes.get_last_error())
            ctypes.memmove(bits,raw,len(raw));old=self.g.SelectObject(memory,bitmap)
            dest=W.POINT(x,y);source=W.POINT(0,0);size=W.SIZE(w,h);blend=Blend(0,0,255,1)
            self.u.UpdateLayeredWindow.argtypes=[W.HWND,W.HDC,ctypes.POINTER(W.POINT),ctypes.POINTER(W.SIZE),W.HDC,ctypes.POINTER(W.POINT),W.DWORD,ctypes.POINTER(Blend),W.DWORD]
            if not self.u.UpdateLayeredWindow(self.hwnd,screen,ctypes.byref(dest),ctypes.byref(size),memory,ctypes.byref(source),0,ctypes.byref(blend),2):raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if old:self.g.SelectObject(memory,old)
            if bitmap:self.g.DeleteObject(bitmap)
            self.g.DeleteDC(memory);self.u.ReleaseDC(None,screen)
    def hide(self):
        if self.hwnd:self.u.ShowWindow(self.hwnd,0)
    def destroy(self):
        if self.job:
            try:self.window.after_cancel(self.job)
            except tk.TclError:pass
            self.job=None
        if self.hwnd:self.u.DestroyWindow(self.hwnd);self.hwnd=None

def attach_shadow(window,scale=1,radius=14):
    return Shadow(window,scale,radius)
