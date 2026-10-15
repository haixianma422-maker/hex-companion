"""Finite native UI transitions; no timers run when the UI is idle."""
import ctypes
import os
import time
import tkinter as tk


def ease_out_cubic(progress):
    p = min(1., max(0., progress))
    return 1. - (1. - p) ** 3


def system_motion_enabled():
    if os.name != 'nt':
        return True
    try:
        enabled = ctypes.c_int(1)
        # SPI_GETCLIENTAREAANIMATION, documented by Microsoft SystemParametersInfoW.
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(enabled.value) if ok else False
    except (OSError, AttributeError):
        return False


class Motion:
    def __init__(self, widget, enabled=True):
        self.widget = widget
        self.enabled = enabled and system_motion_enabled()
        self.jobs = {}
        self.ends = {}
        widget.bind('<Destroy>', self._destroy, add='+')

    def _destroy(self, event):
        if event.widget is self.widget:
            self.cancel_all()

    def cancel(self, name, finish=False):
        job = self.jobs.pop(name, None)
        if job is not None:
            try:
                self.widget.after_cancel(job)
            except tk.TclError:
                pass
        end = self.ends.pop(name, None)
        if finish and end is not None:
            end()

    def cancel_all(self, finish=False):
        for name in list(set(self.jobs) | set(self.ends)):
            self.cancel(name, finish)

    def set_enabled(self, enabled):
        self.enabled = bool(enabled) and system_motion_enabled()
        if not self.enabled:
            self.cancel_all(finish=True)

    def animate(self, name, start, end, update, duration=180, done=None, easing=ease_out_cubic):
        self.cancel(name, finish=True)
        def finish():
            update(end)
            if done:
                done()
        if not self.enabled or not system_motion_enabled() or start == end or duration <= 0:
            finish()
            return
        self.ends[name] = finish
        began = time.monotonic()
        def step():
            self.jobs.pop(name, None)
            try:
                if not self.widget.winfo_exists():
                    self.ends.pop(name, None)
                    return
                if not system_motion_enabled():
                    self.cancel(name, finish=True)
                    return
                progress = min(1., max(0., (time.monotonic() - began) * 1000 / duration))
                eased = easing(progress)
                update(start + (end - start) * eased)
                if progress < 1:
                    self.jobs[name] = self.widget.after(16, step)
                else:
                    self.ends.pop(name, None)
                    if done:
                        done()
            except tk.TclError:
                self.ends.pop(name, None)
        step()

    def activity(self, name, update, period=1400):
        """Linear task feedback. Cancellation never completes a business task."""
        self.cancel(name)
        began = time.monotonic()
        def step():
            self.jobs.pop(name, None)
            try:
                if not self.widget.winfo_exists():
                    return
                if not self.enabled or not system_motion_enabled():
                    update(0.)
                    return
                update((time.monotonic() - began) * 1000 / period)
                self.jobs[name] = self.widget.after(16, step)
            except tk.TclError:
                pass
        step()


def blend(start, end, progress):
    a = [int(start[n:n + 2], 16) for n in (1, 3, 5)]
    b = [int(end[n:n + 2], 16) for n in (1, 3, 5)]
    return '#' + ''.join(f'{round(x + (y - x) * progress):02x}' for x, y in zip(a, b))
