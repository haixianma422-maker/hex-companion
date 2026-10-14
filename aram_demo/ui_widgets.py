"""Pixel-sized interactive controls for the UI V2 handoff.

The four-pixel canvas gutter holds the external keyboard-focus ring. Public
logical coordinates always refer to the control's visible body, not that gutter.
Editing remains native Tk; rounded surfaces, labels and icons share Artboard.
"""
import ctypes
import os
import tkinter as tk
from ctypes import wintypes

from .motion import Motion, blend
from .theme import BG, SURFACE, RAISED, TEXT, MUTED, ACCENT, LILAC, INK, LINE, FONT
from .ui_drawing import Artboard, ui_scale, measure, font as drawing_font, SS

ERROR = '#FFB7BE'
INK_MUTED = '#55476C'
DISABLED_FILL = '#C7BED5'
ACCENT_HOVER = '#E8FFAA'
ACCENT_PRESSED = '#CBE96E'
SURFACE_HOVER = '#342D43'
SURFACE_PRESSED = '#40364F'
GUTTER = 4


def _work_area(widget):
    """Nearest monitor work area, retaining signed desktop coordinates."""
    if os.name == 'nt':
        try:
            class MonitorInfo(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.DWORD), ('monitor', wintypes.RECT),
                            ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
            user = ctypes.WinDLL('user32', use_last_error=True)
            user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            user.MonitorFromWindow.restype = wintypes.HANDLE
            user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(info)
            monitor = user.MonitorFromWindow(widget.winfo_id(), 2)
            if user.GetMonitorInfoW(monitor, ctypes.byref(info)):
                r = info.work
                return r.left, r.top, r.right, r.bottom
        except (OSError, AttributeError, tk.TclError):
            pass
    x, y = widget.winfo_vrootx(), widget.winfo_vrooty()
    return x, y, x + widget.winfo_vrootwidth(), y + widget.winfo_vrootheight()


def _position_popup(window, x, y, width, height):
    window.geometry(f'{width}x{height}{x:+d}{y:+d}')
    window.update_idletasks()
    if os.name == 'nt':
        # Tk interprets a minus offset relative to the screen's right/bottom.
        # SetWindowPos gives the intended absolute position on left monitors.
        try:
            user = ctypes.WinDLL('user32', use_last_error=True)
            user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user.GetAncestor.restype = wintypes.HWND
            user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         wintypes.UINT]
            hwnd = user.GetAncestor(window.winfo_id(), 2)
            user.SetWindowPos(hwnd, None, x, y, width, height, 0x0014)
        except (OSError, AttributeError):
            pass


class _PixelCanvas(tk.Canvas):
    def __init__(self, parent, width, height, scale=None, background=BG, focusable=True):
        self.scale = float(scale if scale is not None else ui_scale(parent))
        self.logical_width, self.logical_height = width, height
        self.background = background
        self._focusable = focusable
        self._state = 'normal'
        self._keyboard_focus = False
        self._pointer_focus = False
        self._focused = False
        self._photo = None
        self._image_item = None
        super().__init__(parent, width=round((width + 8) * self.scale),
                         height=round((height + 8) * self.scale), bg=background,
                         bd=0, highlightthickness=0, takefocus=focusable)
        self.motion = Motion(self)
        tk.Canvas.bind(self, '<FocusIn>', self._focus_in, add='+')
        tk.Canvas.bind(self, '<FocusOut>', self._focus_out, add='+')
        tk.Canvas.bind(self, '<KeyPress>', self._keyboard, add='+')

    def _focus_in(self, _=None):
        self._focused = True
        self._keyboard_focus = not self._pointer_focus
        self._pointer_focus = False
        self._paint()

    def _focus_out(self, _=None):
        self._focused = self._keyboard_focus = False
        self._paint()

    def _keyboard(self, _=None):
        self._keyboard_focus = True
        self._paint()

    def _mouse_focus(self):
        self._keyboard_focus = False
        already_focused = self.focus_get() is self
        self._pointer_focus = True
        self.focus_set()
        # Already focused widgets receive no FocusIn event.
        if already_focused:
            self._pointer_focus = False

    def _inside(self, event):
        x, y = event.x / self.scale - GUTTER, event.y / self.scale - GUTTER
        return 0 <= x < self.logical_width and 0 <= y < self.logical_height

    def _board(self):
        board=Artboard(self.logical_width + 8,self.logical_height + 8,scale=self.scale,bg=self.background)
        position=getattr(self,'_logical_position',None)
        backdrop=getattr(self.master,'control_backdrop',None)
        if position is not None and backdrop:
            picture=backdrop(position[0]-4,position[1]-4,self.logical_width+8,self.logical_height+8)
            if picture is not None:
                from PIL import Image
                board.image=picture.resize(board.image.size,Image.Resampling.LANCZOS)
                from PIL import ImageDraw
                board.draw=ImageDraw.Draw(board.image)
        return board

    def _focus_ring(self, board, radius):
        if self._focused and self._keyboard_focus and self._state != 'disabled':
            board.rect((1, 1, self.logical_width + 6, self.logical_height + 6),
                       fill=None, radius=radius + 3, outline=ACCENT, stroke=2)

    def _show(self, board):
        self._photo = board.photo(self)
        if self._image_item is None:
            self._image_item = self.create_image(0, 0, image=self._photo, anchor='nw')
        else:
            self.itemconfigure(self._image_item, image=self._photo)

    def place_logical(self, x, y):
        self._logical_position=(x,y)
        self.place(x=round((x - GUTTER) * self.scale),
                   y=round((y - GUTTER) * self.scale),
                   width=round((self.logical_width + 8) * self.scale),
                   height=round((self.logical_height + 8) * self.scale))
        self._paint()
        return self

    def set_motion(self, enabled):
        self.motion.set_enabled(enabled)

    def cget(self, key):
        if key == 'state':
            return self._state
        return super().cget(key)

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = dict(cnf, **kwargs)
            cnf = None
        redraw = False
        if 'state' in kwargs:
            self._state = kwargs.pop('state')
            self.motion.cancel_all(finish=True)
            super().configure(takefocus=self._focusable and self._state != 'disabled')
            redraw = True
        if 'background' in kwargs or 'bg' in kwargs:
            self.background = kwargs.get('background', kwargs.get('bg'))
            redraw = True
        result = super().configure(cnf, **kwargs) if kwargs or cnf is not None else None
        if redraw:
            self._paint()
        return result

    config = configure


class PixelButton(_PixelCanvas):
    """Whole-area mouse and keyboard button with finite color transitions."""
    def __init__(self, parent, text, command, width, height, kind='primary', icon=None,
                 font_size=14, bold=True, scale=None, background=BG, radius=None,
                 align='center', color=None, underline=False, outline_color=None,
                 icon_box=None, text_box=None, icon_color=None):
        self.text, self.command, self.kind, self.icon = text, command, kind, icon
        self.font_size, self.bold = font_size, bold
        self.align, self.color, self.underline = align, color, underline
        self.outline_color = outline_color
        self.icon_box, self.text_box, self.icon_color = icon_box, text_box, icon_color
        self._auto_radius = radius is None
        self.radius = height / 2 if radius is None else radius
        self._hover = self._pressed = False
        self._fill = self._normal_color(background)
        super().__init__(parent, width, height, scale, background)
        self.configure(cursor='hand2')
        self.bind('<Enter>', self._enter)
        self.bind('<Leave>', self._leave)
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<KeyPress-space>', self._key_press)
        self.bind('<KeyRelease-space>', self._key_release)
        self.bind('<Return>', self._return)
        self._paint()

    def _focus_out(self, event=None):
        self._pressed = False
        super()._focus_out(event)
        self._tint(immediate=True)

    def _normal_color(self, background=None):
        return ACCENT if self.kind == 'primary' else RAISED if self.kind == 'secondary' else (background or self.background)

    def _color(self):
        if self._state == 'disabled':
            return RAISED
        if self.kind == 'primary':
            return ACCENT_PRESSED if self._pressed else ACCENT_HOVER if self._hover else ACCENT
        if self._pressed:
            return SURFACE_PRESSED
        if self._hover:
            return SURFACE_HOVER
        return self._normal_color()

    def _tint(self, immediate=False):
        start, end = self._fill, self._color()
        duration = 70 if self._pressed else 100
        def update(progress):
            self._fill = blend(start, end, progress)
            self._paint()
        if immediate:
            self.motion.cancel('color')
            update(1)
        else:
            self.motion.animate('color', 0, 1, update, duration)

    def _enter(self, _):
        self._hover = True
        self._tint()

    def _leave(self, _):
        self._hover = self._pressed = False
        self._tint()

    def _press(self, event):
        if self._state != 'disabled' and self._inside(event):
            self._mouse_focus()
            self._pressed = True
            self._tint()
        return 'break'

    def _release(self, event):
        activate = self._pressed and self._inside(event)
        self._pressed = False
        self._tint(immediate=True)
        if activate:
            self.invoke()
        return 'break'

    def _key_press(self, _):
        if self._state != 'disabled':
            self._pressed = self._keyboard_focus = True
            self._tint()
        return 'break'

    def _key_release(self, _):
        activate = self._pressed
        self._pressed = False
        self._tint(immediate=True)
        if activate:
            self.invoke()
        return 'break'

    def _return(self, _):
        self._keyboard_focus = True
        self._paint()
        self.invoke()
        return 'break'

    def invoke(self):
        if self._state != 'disabled' and self.command:
            return self.command()

    def set_size(self, width, height):
        """Resize the visible body, preserving its logical top-left position."""
        self.logical_width, self.logical_height = width, height
        if self._auto_radius:
            self.radius = height / 2
        dimensions = dict(width=round((width + 8) * self.scale),
                          height=round((height + 8) * self.scale))
        tk.Canvas.configure(self, **dimensions)
        if self.winfo_manager() == 'place':
            self.place_configure(**dimensions)
        self._paint()
        return self

    def _paint(self):
        if not hasattr(self, 'motion'):
            return
        board = self._board()
        color = self._color() if self._state == 'disabled' else self._fill
        foreground = MUTED if self._state == 'disabled' else self.color or (INK if self.kind == 'primary' else TEXT)
        board.rect((4, 4, self.logical_width, self.logical_height), color, self.radius,
                   outline=(self.outline_color or MUTED) if self.kind == 'outline' else None,
                   stroke=1)
        text_width = measure(self.text, self.font_size, self.bold)
        icon_space = 24 if self.icon and self.text else 16 if self.icon else 0
        group_width = min(self.logical_width - 16, text_width + icon_space)
        left = 4 if self.align == 'left' else 4 + (self.logical_width - group_width) / 2
        if self.align == 'right':
            left = 4 + self.logical_width - group_width
        if self.icon and not self.text:
            left = 4 + (self.logical_width - 16) / 2
        if self.icon:
            icon_box = ((self.icon_box[0] + 4, self.icon_box[1] + 4,
                         self.icon_box[2], self.icon_box[3]) if self.icon_box is not None else
                        (left, 4 + (self.logical_height - 16) / 2, 16, 16))
            board.icon(self.icon, icon_box,
                       color=MUTED if self._state == 'disabled' else self.icon_color or foreground,
                       stroke=1.4 if icon_box[2] <= 14 else 1.6)
            left += 24
        text_box = ((self.text_box[0] + 4, self.text_box[1] + 4,
                     self.text_box[2], self.text_box[3]) if self.text_box is not None else
                    (left, 4, max(1, group_width - icon_space), self.logical_height))
        displayed = board.text(text_box, self.text, size=self.font_size,
                               bold=self.bold, color=foreground,
                               align=self.align if self.text_box is not None else 'left')
        if self.underline and displayed:
            ascent, descent = drawing_font(self.font_size * SS, self.bold).getmetrics()
            baseline = text_box[1] + (text_box[3] + (ascent - descent) / SS) / 2
            length = measure(displayed, self.font_size, self.bold)
            underline_left = text_box[0]
            if self.text_box is not None and self.align == 'center':
                underline_left += (text_box[2] - length) / 2
            elif self.text_box is not None and self.align == 'right':
                underline_left += text_box[2] - length
            board.line((underline_left, baseline + 1, underline_left + length,
                        baseline + 1), foreground, 1)
        self._focus_ring(board, self.radius)
        self._show(board)

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = dict(cnf, **kwargs)
            cnf = None
        changed = False
        for key in ('text', 'command', 'icon', 'align', 'color', 'underline', 'outline_color',
                    'font_size', 'bold', 'icon_box', 'text_box', 'icon_color'):
            if key in kwargs:
                setattr(self, key, kwargs.pop(key))
                changed = True
        result = super().configure(cnf, **kwargs)
        if hasattr(self, 'motion') and ('state' in kwargs or changed):
            self._tint(immediate=True)
        return result

    config = configure


class PixelEntry(_PixelCanvas):
    """Rounded editable field; the inset native Entry has no native border."""
    def __init__(self, parent, variable, width, height, font_size=14, scale=None,
                 center=False, background=BG, fill=LILAC, color=None, radius=10,
                 inset=None):
        self.variable, self.fill, self.radius = variable, fill, radius
        self.color = color or (INK if fill.lower() in (LILAC.lower(), DISABLED_FILL.lower()) else TEXT)
        self._error = False
        self.center = center
        self.inset = (4 if center else 12) if inset is None else inset
        super().__init__(parent, width, height, scale, background, focusable=False)
        self.entry = tk.Entry(self, textvariable=variable, bg=fill, fg=self.color,
                              insertbackground=self.color, selectbackground=RAISED,
                              selectforeground=TEXT, relief='flat', bd=0,
                              highlightthickness=0, exportselection=False,
                              justify='center' if center else 'left',
                              font=(FONT, -round(font_size * self.scale)))
        self.entry.place(x=round((4 + self.inset) * self.scale),
                         y=round((4 + (height - font_size - 8) / 2) * self.scale),
                         width=round((width - 2 * self.inset) * self.scale),
                         height=round((font_size + 8) * self.scale))
        self.entry.bind('<FocusIn>', self._entry_focus, add='+')
        self.entry.bind('<FocusOut>', self._focus_out, add='+')
        tk.Canvas.bind(self, '<Button-1>', lambda _: self.focus_set())
        self._paint()

    def _entry_focus(self, _=None):
        self._focused = True
        self._paint()

    def focus_set(self):
        self.entry.focus_set()

    def bind(self, sequence=None, func=None, add=None):
        if hasattr(self, 'entry'):
            return self.entry.bind(sequence, func, add)
        return super().bind(sequence, func, add)

    def set_error(self, error):
        self._error = bool(error)
        self._paint()

    def _paint(self):
        if not hasattr(self, 'entry'):
            return
        board = self._board()
        disabled = self._state == 'disabled'
        fill = DISABLED_FILL if disabled else self.fill
        border = ERROR if self._error else ACCENT if self._focused else None
        board.rect((4, 4, self.logical_width, self.logical_height), fill,
                   self.radius, outline=border, stroke=2)
        self.entry.configure(bg=fill, fg=INK_MUTED if disabled else self.color,
                             disabledbackground=DISABLED_FILL,
                             disabledforeground=INK_MUTED,
                             readonlybackground=fill)
        self._show(board)
        self.entry.lift()

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = dict(cnf, **kwargs)
            cnf = None
        state = kwargs.get('state')
        result = super().configure(cnf, **kwargs)
        if state is not None and hasattr(self, 'entry'):
            self.entry.configure(state=state)
            self._paint()
        return result

    config = configure


class PixelToggle(_PixelCanvas):
    def __init__(self, parent, variable, scale=None):
        self.variable = variable
        self.position = 1.0 if variable.get() else 0.0
        super().__init__(parent, 54, 32, scale)
        self.configure(cursor='hand2')
        self._trace = variable.trace_add('write', self._changed)
        self.bind('<Button-1>', self._toggle)
        self.bind('<space>', self._toggle)
        self.bind('<Return>', self._toggle)
        self.bind('<Destroy>', self._destroy_trace, add='+')
        self._paint()

    def _destroy_trace(self, event):
        if event.widget is self:
            try:
                self.variable.trace_remove('write', self._trace)
            except tk.TclError:
                pass

    def _changed(self, *_):
        self.motion.animate('knob', self.position, 1.0 if self.variable.get() else 0.0,
                            self._move, 140)

    def _move(self, value):
        self.position = value
        self._paint()

    def _toggle(self, event=None):
        if self._state == 'disabled':
            return 'break'
        if event is not None and event.type == tk.EventType.ButtonPress:
            if not self._inside(event):
                return 'break'
            self._mouse_focus()
        else:
            self._keyboard_focus = True
        self.variable.set(not self.variable.get())
        return 'break'

    def _paint(self):
        if not hasattr(self, 'motion'):
            return
        board = self._board()
        board.rect((4, 4, 54, 32), blend(RAISED, ACCENT, self.position)
                   if self._state != 'disabled' else RAISED, 16)
        board.rect((8 + 22 * self.position, 8, 24, 24), TEXT, 12)
        self._focus_ring(board, 16)
        self._show(board)


class SourceSwitch(_PixelCanvas):
    """A variable change synchronizes drawing; only user actions emit a choice."""
    def __init__(self, parent, variable, values, width=110, height=24, scale=None,
                 on_change=None, separate=False, background=BG):
        self.variable, self.values = variable, dict(values)
        self.on_change, self.separate = on_change, separate
        self.position = float(self._index())
        self._hover_index = None
        self._pressed_index = None
        self._shade_color = ACCENT
        super().__init__(parent, width, height, scale, background)
        self.configure(cursor='hand2')
        self._trace = variable.trace_add('write', self._changed)
        self.bind('<Button-1>', self._click)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Motion>', self._hover)
        self.bind('<Leave>', self._leave)
        self.bind('<Left>', lambda _: self._key(-1))
        self.bind('<Right>', lambda _: self._key(1))
        self.bind('<space>', lambda _: self._key(1))
        self.bind('<Destroy>', self._destroy_trace, add='+')
        self._paint()

    def _index(self):
        values = list(self.values.values())
        return values.index(self.variable.get()) if self.variable.get() in values else 0

    def _destroy_trace(self, event):
        if event.widget is self:
            try:
                self.variable.trace_remove('write', self._trace)
            except tk.TclError:
                pass

    def _changed(self, *_):
        self.motion.animate('selection', self.position, float(self._index()), self._move, 140)
        self._shade()

    def _shade(self, immediate=False):
        start = self._shade_color
        end = (ACCENT_PRESSED if self._pressed_index == self._index() else
               ACCENT_HOVER if self._hover_index == self._index() else ACCENT)
        def update(progress):
            self._shade_color = blend(start, end, progress)
            self._paint()
        if immediate:
            self.motion.cancel('shade')
            update(1)
        else:
            self.motion.animate('shade', 0, 1, update, 70 if self._pressed_index is not None else 100)

    def _move(self, value):
        self.position = value
        self._paint()

    def _boxes(self):
        if self.separate:
            return [(4, 4, 116, 38), (136, 4, 116, 38)]
        count = max(1, len(self.values))
        return [(4 + i * self.logical_width / count, 4,
                 self.logical_width / count, self.logical_height) for i in range(count)]

    def _hit(self, event):
        x, y = event.x / self.scale, event.y / self.scale
        for i, (left, top, width, height) in enumerate(self._boxes()):
            if left <= x < left + width and top <= y < top + height:
                return i
        return None

    def _hover(self, event):
        value = self._hit(event)
        if value != self._hover_index:
            self._hover_index = value
            self._shade()

    def _leave(self, _):
        self._hover_index = None
        self._pressed_index = None
        self._shade()

    def _click(self, event):
        index = self._hit(event)
        if index is not None and self._state != 'disabled':
            self._mouse_focus()
            self._pressed_index = index
            self._choose(index)
            self._shade()
        return 'break'

    def _release(self, _):
        self._pressed_index = None
        self._shade(immediate=True)
        return 'break'

    def _key(self, delta):
        self._keyboard_focus = True
        self._choose((self._index() + delta) % max(1, len(self.values)))
        return 'break'

    def _choose(self, index):
        if self._state == 'disabled' or not self.values:
            return
        value = list(self.values.values())[index]
        if value == self.variable.get():
            self._paint()
            return
        self.variable.set(value)
        if self.on_change:
            self.on_change(value)
        if self.winfo_exists():
            self.event_generate('<<ComboboxSelected>>')

    def _paint(self):
        if not hasattr(self, 'motion'):
            return
        board = self._board()
        selected = self._index()
        boxes = self._boxes()
        if not self.separate:
            board.rect((4, 4, self.logical_width, self.logical_height), RAISED,
                       self.logical_height / 2, outline=LINE, stroke=1)
            cell = self.logical_width / max(1, len(self.values))
            color = self._shade_color
            board.rect((5 + self.position * cell, 5, cell - 2, self.logical_height - 2),
                       color if self._state != 'disabled' else RAISED,
                       (self.logical_height - 2) / 2)
        for i, (name, box) in enumerate(zip(self.values, boxes)):
            x, y, w, h = box
            if self.separate:
                weight = max(0., 1 - abs(self.position - i))
                color = blend(SURFACE_HOVER if self._hover_index == i else RAISED,
                              self._shade_color, weight)
                if self._state == 'disabled':
                    color = RAISED
                board.rect(box, color, h / 2)
            color = INK if i == selected and self._state != 'disabled' else MUTED
            board.text((x, y, w, h), name, size=16 if self.separate else 12,
                       bold=True, color=color, align='center')
        if self.separate and self._focused and self._keyboard_focus:
            x, y, w, h = boxes[selected]
            board.rect((x - 3, y - 3, w + 6, h + 6), None, h / 2 + 3,
                       outline=ACCENT, stroke=2)
        elif not self.separate:
            self._focus_ring(board, self.logical_height / 2)
        self._show(board)


class PixelChoice(_PixelCanvas):
    """Read-only local icon picker with a six-row custom rounded popup."""
    def __init__(self, parent, variable, values, width, height, icon_lookup=None, scale=None):
        self.variable, self.values = variable, list(values)
        self.icon_lookup = icon_lookup
        self._error = False
        self._popup = None
        self._popup_canvas = None
        self._popup_photo = None
        self._popup_focus_job = None
        self._dragging_scroll = False
        self._popup_keyboard = False
        self._active = self._scroll = 0
        self._visible = 6
        self._icon_cache = {}
        super().__init__(parent, width, height, scale)
        self.configure(cursor='hand2')
        self._trace = variable.trace_add('write', lambda *_: self.refresh())
        self.bind('<Button-1>', self._click)
        for key in ('space', 'Return', 'Down', 'Up'):
            self.bind(f'<{key}>', self._key_open)
        self.bind('<Escape>', lambda _: self._dismiss())
        self.bind('<Destroy>', self._destroy_choice, add='+')
        self._paint()

    def _destroy_choice(self, event):
        if event.widget is self:
            self._dismiss(restore=False)
            try:
                self.variable.trace_remove('write', self._trace)
            except tk.TclError:
                pass

    def _icon_path(self, value):
        if not value or not self.icon_lookup:
            return None
        if value not in self._icon_cache:
            try:
                self._icon_cache[value] = self.icon_lookup(value)
            except (OSError, KeyError, ValueError):
                self._icon_cache[value] = None
        return self._icon_cache[value]

    def _draw_icon(self, board, value, box, color=INK):
        path = self._icon_path(value)
        if not path or not board.image_at(box, path, fit='contain', radius=0):
            board.icon('question', box, color=color)

    def refresh(self):
        if self.winfo_exists():
            self._paint()
            if self._popup is not None:
                self._paint_popup()

    def set_values(self, values):
        self._dismiss(restore=False)
        self.values = list(values)
        self._icon_cache.clear()
        self._paint()

    def set_error(self, error):
        self._error = bool(error)
        self._paint()

    def _paint(self):
        if not hasattr(self, 'motion'):
            return
        board = self._board()
        disabled = self._state == 'disabled'
        color = INK_MUTED if disabled else INK
        border = ERROR if self._error else ACCENT if self._focused else None
        board.rect((4, 4, self.logical_width, self.logical_height),
                   DISABLED_FILL if disabled else LILAC, 10, outline=border, stroke=2)
        value = self.variable.get()
        self._draw_icon(board, value, (14, 4 + (self.logical_height - 28) / 2, 28, 28), color)
        board.text((52, 4, max(1, self.logical_width - 84), self.logical_height),
                   value or '请选择', size=14, bold=True, color=color)
        board.icon('chevron', (4 + self.logical_width - 24,
                              4 + (self.logical_height - 12) / 2, 12, 12), color=color)
        self._show(board)

    def _click(self, event):
        if self._state != 'disabled' and self._inside(event):
            self._mouse_focus()
            if self._popup is None:
                self._open()
            else:
                self._dismiss()
        return 'break'

    def _key_open(self, _):
        self._keyboard_focus = True
        self._paint()
        self._open()
        return 'break'

    def _open(self):
        if self._popup is not None or not self.values or self._state == 'disabled':
            return
        self._popup_keyboard = self._keyboard_focus
        value = self.variable.get()
        self._active = self.values.index(value) if value in self.values else 0
        left, top, right, bottom = _work_area(self)
        available = max(1, bottom - top)
        self._visible = min(6, len(self.values), max(1, int((available / self.scale - 8) // 40)))
        self._scroll = min(max(0, self._active - self._visible + 1), len(self.values) - self._visible)
        self._popup = tk.Toplevel(self)
        self._popup.withdraw()
        self._popup.overrideredirect(True)
        self._popup.configure(bg=BG)
        self._popup.transient(self.winfo_toplevel())
        self._popup.attributes('-topmost', True)
        if os.name == 'nt':
            self._popup.attributes('-transparentcolor', '#010203')
        width = round(self.logical_width * self.scale)
        height = round((self._visible * 40 + 8) * self.scale)
        x = self.winfo_rootx() + round(4 * self.scale)
        below = self.winfo_rooty() + round((self.logical_height + 4) * self.scale) + round(4 * self.scale)
        above = self.winfo_rooty() + round(4 * self.scale) - height - round(4 * self.scale)
        y = below if below + height <= bottom else above
        x, y = max(left, min(x, right - width)), max(top, min(y, bottom - height))
        self._popup_canvas = tk.Canvas(self._popup, width=width, height=height,
                                       bd=0, highlightthickness=0, bg=BG, takefocus=True)
        self._popup_canvas.pack()
        self._popup_canvas.bind('<Motion>', self._popup_hover)
        self._popup_canvas.bind('<ButtonPress-1>', self._scroll_press)
        self._popup_canvas.bind('<B1-Motion>', self._scroll_drag)
        self._popup_canvas.bind('<ButtonRelease-1>', self._popup_pick)
        self._popup_canvas.bind('<MouseWheel>', self._wheel)
        self._popup_canvas.bind('<Button-4>', lambda _: self._scroll_by(-1))
        self._popup_canvas.bind('<Button-5>', lambda _: self._scroll_by(1))
        for key, delta in (('Up', -1), ('Down', 1), ('Prior', -self._visible), ('Next', self._visible)):
            self._popup_canvas.bind(f'<{key}>', lambda _, n=delta: self._navigate(n))
        self._popup_canvas.bind('<Home>', lambda _: self._go(0))
        self._popup_canvas.bind('<End>', lambda _: self._go(len(self.values) - 1))
        self._popup_canvas.bind('<Return>', lambda _: self._select(self._active))
        self._popup_canvas.bind('<space>', lambda _: self._select(self._active))
        self._popup_canvas.bind('<Escape>', lambda _: self._dismiss())
        self._popup_canvas.bind('<Tab>', self._tab_dismiss)
        self._popup_canvas.bind('<Shift-Tab>', lambda _: self._tab_dismiss(backward=True))
        self._popup_canvas.bind('<ISO_Left_Tab>', lambda _: self._tab_dismiss(backward=True))
        self._popup.bind('<FocusOut>', self._popup_focus_out, add='+')
        self._popup.bind('<ButtonPress-1>', self._popup_outside, add='+')
        self._paint_popup()
        _position_popup(self._popup, x, y, width, height)
        self._popup.deiconify()
        _position_popup(self._popup, x, y, width, height)
        self._popup_canvas.focus_set()
        self._popup.grab_set()

    def _paint_popup(self):
        if self._popup_canvas is None:
            return
        width, height = self.logical_width, self._visible * 40 + 8
        board = Artboard(width, height, scale=self.scale,
                         bg='#010203' if os.name == 'nt' else BG)
        board.rect((0, 0, width, height), SURFACE, 10)
        overflow = len(self.values) > self._visible
        for row in range(self._visible):
            index = self._scroll + row
            value = self.values[index]
            y = 4 + row * 40
            chosen = index == self._active or value == self.variable.get()
            color = INK if chosen else TEXT
            if chosen:
                board.rect((4, y, width - (14 if overflow else 8), 40), LILAC, 6)
            self._draw_icon(board, value, (10, y + 6, 28, 28), color)
            board.text((48, y, max(1, width - (68 if overflow else 60)), 40),
                       value or '请选择', size=14, bold=True, color=color)
        if overflow:
            viewport = height - 16
            thumb = max(20, viewport * self._visible / len(self.values))
            offset = (viewport - thumb) * self._scroll / (len(self.values) - self._visible)
            board.rect((width - 8, 8, 6, viewport), RAISED, 3)
            board.rect((width - 8, 8 + offset, 6, thumb), MUTED, 3)
        self._popup_photo = board.photo(self._popup_canvas)
        self._popup_canvas.delete('all')
        self._popup_canvas.create_image(0, 0, image=self._popup_photo, anchor='nw')

    def _popup_index(self, event):
        x, y = event.x / self.scale, event.y / self.scale
        if not (4 <= y < self._visible * 40 + 4 and 0 <= x < self.logical_width - 10):
            return None
        return self._scroll + int((y - 4) // 40)

    def _popup_hover(self, event):
        index = self._popup_index(event)
        if index is not None and index != self._active:
            self._active = index
            self._paint_popup()

    def _popup_pick(self, event):
        if self._dragging_scroll:
            self._dragging_scroll = False
            return 'break'
        index = self._popup_index(event)
        if index is not None:
            return self._select(index)
        return 'break'

    def _scroll_press(self, event):
        if len(self.values) > self._visible and event.x / self.scale >= self.logical_width - 10:
            self._dragging_scroll = True
            return self._scroll_drag(event)

    def _scroll_drag(self, event):
        if self._dragging_scroll:
            viewport = self._visible * 40 - 8
            thumb = max(20, viewport * self._visible / len(self.values))
            ratio = (event.y / self.scale - 8 - thumb / 2) / max(1, viewport - thumb)
            self._scroll = round(max(0., min(1., ratio)) * (len(self.values) - self._visible))
            self._paint_popup()
            return 'break'

    def _popup_outside(self, event):
        popup = self._popup
        if popup and not (popup.winfo_rootx() <= event.x_root < popup.winfo_rootx() + popup.winfo_width()
                          and popup.winfo_rooty() <= event.y_root < popup.winfo_rooty() + popup.winfo_height()):
            self._dismiss()
            return 'break'

    def _navigate(self, delta):
        return self._go(max(0, min(len(self.values) - 1, self._active + delta)))

    def _go(self, index):
        self._active = index
        if index < self._scroll:
            self._scroll = index
        elif index >= self._scroll + self._visible:
            self._scroll = index - self._visible + 1
        self._paint_popup()
        return 'break'

    def _scroll_by(self, delta):
        self._scroll = max(0, min(len(self.values) - self._visible, self._scroll + delta))
        self._paint_popup()
        return 'break'

    def _wheel(self, event):
        return self._scroll_by(-1 if event.delta > 0 else 1)

    def _select(self, index):
        self.variable.set(self.values[index])
        self._dismiss()
        self.event_generate('<<ComboboxSelected>>')
        return 'break'

    def _tab_dismiss(self, _=None, backward=False):
        self._dismiss()
        target = self.tk_focusPrev() if backward else self.tk_focusNext()
        if target:
            target.focus_set()
        return 'break'

    def _popup_focus_out(self, _):
        popup = self._popup
        if popup:
            if self._popup_focus_job:
                popup.after_cancel(self._popup_focus_job)
            self._popup_focus_job = popup.after_idle(lambda: self._check_popup_focus(popup))

    def _check_popup_focus(self, popup):
        self._popup_focus_job = None
        if popup is not self._popup:
            return
        try:
            focused = self.focus_get()
            if focused is None or focused.winfo_toplevel() is not popup:
                self._dismiss(restore=False)
        except tk.TclError:
            self._dismiss(restore=False)

    def _dismiss(self, restore=True):
        popup = self._popup
        self._popup = self._popup_canvas = self._popup_photo = None
        if popup:
            try:
                if self._popup_focus_job:
                    popup.after_cancel(self._popup_focus_job)
                self._popup_focus_job = None
                popup.grab_release()
                popup.destroy()
            except tk.TclError:
                pass
            if restore:
                try:
                    self._pointer_focus = not self._popup_keyboard
                    self.focus_set()
                except tk.TclError:
                    pass
        return 'break'

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = dict(cnf, **kwargs)
            cnf = None
        if kwargs.get('state') == 'disabled':
            self._dismiss(restore=False)
        return super().configure(cnf, **kwargs)

    config = configure
