"""Logical-pixel, antialiased drawing for the numbered UI V2 handoff."""
import ctypes
import functools
import math
import os
import re
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .tk_images import WidgetPhotoImage

BG = '#191723'
SURFACE = '#282333'
RAISED = '#393145'
TEXT = '#F7F3EB'
MUTED = '#B6A6D9'
LILAC = '#E9E2F7'
ACCENT = '#DFFF80'
INK = BG
INK_MUTED = '#55476C'
LINE = '#443A55'
UNKNOWN = '#AB9BC7'
ERROR = '#FFB7BE'
TRANSPARENT = '#010203'
FONT_FILES = {'regular': 'C:/Windows/Fonts/msyh.ttc', 'bold': 'C:/Windows/Fonts/msyhbd.ttc'}
SS = 4


def ui_scale(widget):
    root = widget._root()
    explicit = getattr(root, 'design_scale', None)
    return float(explicit) if explicit is not None else round(root.winfo_fpixels('1i') / 96, 3)


def work_area(widget):
    if os.name == 'nt':
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                        ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
        user = ctypes.windll.user32
        user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user.MonitorFromWindow.restype = wintypes.HANDLE
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        monitor = user.MonitorFromWindow(widget.winfo_id(), 2)
        user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        user.GetMonitorInfoW.restype = wintypes.BOOL
        if user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            r = info.work
            return r.left, r.top, r.right, r.bottom
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


@functools.lru_cache(maxsize=128)
def font(size, bold=False):
    return ImageFont.truetype(FONT_FILES['bold' if bold else 'regular'], max(1, round(size)), index=1)


def measure(text, size, bold=False):
    return font(size * SS, bold).getlength(str(text)) / SS


def ellipsize(text, width, size, bold=False):
    text = str(text)
    if measure(text, size, bold) <= width:
        return text
    while text and measure(text + '…', size, bold) > width:
        text = text[:-1]
    return text + '…'


def wrap(text, width, size, bold=False, lines=1, ellipsis=True):
    rows = []
    for paragraph in str(text).split('\n'):
        row = ''
        for character in paragraph:
            if row and measure(row + character, size, bold) > width:
                rows.append(row)
                row = character
            else:
                row += character
        rows.append(row)
    if len(rows) > lines:
        rows = rows[:lines]
        if ellipsis:
            rows[-1] = ellipsize(rows[-1] + '…', width, size, bold)
    return rows


@functools.lru_cache(maxsize=32)
def _art(path, stamp, width, height, fit, focus, hero):
    with Image.open(path) as source:
        image = source.convert('RGBA')
    if fit == 'contain':
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        target = Image.new('RGBA', (width, height))
        target.alpha_composite(image, ((width - image.width) // 2, (height - image.height) // 2))
        return target
    if hero:
        fx, fy = focus or (.72, .42)
        factor = max(width / image.width, height / image.height)
        sw, sh = max(width, round(image.width * factor)), max(height, round(image.height * factor))
        image = image.resize((sw, sh), Image.Resampling.LANCZOS)
        ox = max(0, min(sw - width, round(fx * sw - .77 * width)))
        oy = max(0, min(sh - height, round(fy * sh - .48 * height)))
        image = image.crop((ox, oy, ox + width, oy + height))
        gradient = Image.new('L', (width, 1))
        gradient.putdata([round(255 * max(0, min(1, (.66 - x / width) / .24))) for x in range(width)])
        image = Image.composite(Image.new('RGBA', (width, height), LILAC), image,
                                gradient.resize((width, height)))
        return image
    return ImageOps.fit(image, (width, height), Image.Resampling.LANCZOS)


_BRAND = '''M12 1 C14 1 14 6 15.5 7 L21 7 C24 7 22 10 19 12 L21 18
C22 21 18 21 15 18 L12 23 C10 25 8 21 8 17 L2 17 C-1 17 1 13 5 11
L2 7 C0 4 4 3 8 6 L10 2 C10.5 1 11 1 12 1 Z M7 9 L10 12 L7 15 L10 15 L13 12 L10 9 Z'''


def _brand_paths():
    tokens = re.findall(r'[MCLZ]|-?\d+(?:\.\d+)?', _BRAND)
    paths, points, current = [], [], (0, 0)
    index = 0
    while index < len(tokens):
        command = tokens[index]
        index += 1
        if command in ('M', 'L'):
            current = float(tokens[index]), float(tokens[index + 1])
            index += 2
            points.append(current)
        elif command == 'C':
            numbers = list(map(float, tokens[index:index + 6]))
            index += 6
            a, b, c, d = current, tuple(numbers[:2]), tuple(numbers[2:4]), tuple(numbers[4:6])
            for step in range(1, 17):
                t = step / 16
                points.append(tuple((1-t)**3*a[k] + 3*(1-t)**2*t*b[k] + 3*(1-t)*t*t*c[k] + t**3*d[k] for k in (0, 1)))
            current = d
        elif command == 'Z':
            paths.append(points)
            points = []
    return paths


class Artboard:
    def __init__(self, width, height, scale=1, bg=BG):
        self.scale, self.factor = float(scale), float(scale) * SS
        self.width, self.height = width, height
        self.image = Image.new('RGBA', (round(width * self.factor), round(height * self.factor)), bg)
        self.draw = ImageDraw.Draw(self.image)

    def box(self, box):
        x, y, w, h = box
        f = self.factor
        return tuple(round(v * f) for v in (x, y, x + w, y + h))

    def rect(self, box, fill, radius=0, outline=None, stroke=1):
        bounds = list(self.box(box))
        bounds[2] -= 1
        bounds[3] -= 1
        self.draw.rounded_rectangle(bounds, radius=round(radius * self.factor), fill=fill,
                                    outline=outline, width=max(1, round(stroke * self.factor)))

    def line(self, points, color=LINE, width=1):
        self.draw.line(tuple(round(v * self.factor) for v in points), fill=color,
                       width=max(1, round(width * self.factor)))

    def circle(self, box, fill, outline=None, stroke=1):
        self.draw.ellipse(self.box(box), fill=fill, outline=outline, width=max(1, round(stroke * self.factor)))

    def text(self, box, text, size=14, bold=False, color=TEXT, align='left', lines=1,
             line_height=None, ellipsis=True, optical=False):
        x, y, w, h = box
        rows = wrap(text, w, size, bold, lines, ellipsis)
        lh = line_height or size * 1.4
        face = font(size * self.factor, bold)
        ascent, descent = face.getmetrics()
        top = y + (h - lh * len(rows)) / 2
        for row_index, row in enumerate(rows):
            length = face.getlength(row)
            tx = x * self.factor
            if align == 'center':
                tx += (w * self.factor - length) / 2
            elif align == 'right':
                tx += w * self.factor - length
            baseline = (top + row_index * lh) * self.factor + (lh * self.factor - ascent - descent) / 2 + ascent
            if optical:
                bbox = self.draw.textbbox((0, 0), row, font=face, anchor='ls')
                baseline = (y + h / 2) * self.factor - (bbox[1] + bbox[3]) / 2
            self.draw.text((round(tx), round(baseline)), row, fill=color, font=face, anchor='ls')
        return '\n'.join(rows)

    def image_at(self, box, path, fit='cover', radius=6, border=None, focus=None, hero=False,round_bottom=True):
        if path is None:
            return False
        try:
            stat = Path(path).stat()
            bounds = self.box(box)
            w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
            image = _art(str(path), stat.st_mtime_ns, w, h, fit, tuple(focus) if focus else None, hero).copy()
            if radius:
                mask = Image.new('L', (w, h))
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=round(radius * self.factor), fill=255)
                if not round_bottom:
                    ImageDraw.Draw(mask).rectangle((0,h-round(radius*self.factor),w,h),fill=255)
                # Preserve the alpha of transparent augment artwork.
                from PIL import ImageChops
                image.putalpha(ImageChops.multiply(image.getchannel('A'), mask))
            self.image.alpha_composite(image, (bounds[0], bounds[1]))
            if border:
                self.rect(box, None, radius, border, 1)
            return True
        except (OSError, ValueError, SyntaxError):
            return False

    def brand(self, box, color=ACCENT):
        x, y, w, h = box
        layer = Image.new('RGBA', (round(w * self.factor), round(h * self.factor)))
        draw = ImageDraw.Draw(layer)
        for index, points in enumerate(_brand_paths()):
            draw.polygon([(round(px / 24 * layer.width), round(py / 24 * layer.height)) for px, py in points],
                         fill=color if index == 0 else (0, 0, 0, 0))
        self.image.alpha_composite(layer, (round(x * self.factor), round(y * self.factor)))

    def icon(self, name, box, color=TEXT, stroke=1.6):
        x, y, w, h = box
        def points(values):
            return [(round((x + a * w) * self.factor), round((y + b * h) * self.factor)) for a, b in values]
        def path(values, close=False):
            pts = points(values)
            if close:
                pts.append(pts[0])
            thickness = max(1, round(stroke * self.factor))
            self.draw.line(pts, fill=color, width=thickness, joint='curve')
            for px, py in pts:
                r = thickness / 2
                self.draw.ellipse((px-r, py-r, px+r, py+r), fill=color)
        if name == 'minus':
            path([(.08, .5), (.92, .5)])
        elif name in ('close', 'x'):
            path([(.12, .12), (.88, .88)])
            path([(.88, .12), (.12, .88)])
        elif name in ('chevron', 'down'):
            path([(.12, .3), (.5, .7), (.88, .3)])
        elif name == 'scan':
            for a, b, c in [((.35,.08),(.08,.08),(.08,.35)),((.65,.08),(.92,.08),(.92,.35)),
                            ((.08,.65),(.08,.92),(.35,.92)),((.65,.92),(.92,.92),(.92,.65))]:
                path([a,b,c])
        elif name == 'refresh':
            values = [(.5+.36*math.cos(a), .5+.36*math.sin(a)) for a in [math.radians(15+i*300/28) for i in range(29)]]
            path(values)
            path([(.58,.04),(.78,.19),(.58,.29)])
        elif name == 'settings':
            values=[]
            for i in range(64):
                angle=i*2*math.pi/64
                radius=.39 if i%8 in (2,3,4,5) else .49
                values.append((.5+radius*math.cos(angle),.5+radius*math.sin(angle)))
            path(values, True)
            self.circle((x+w*.34,y+h*.34,w*.32,h*.32),None,color,stroke)
        elif name in ('info', 'question'):
            self.circle((x+w*.06,y+h*.06,w*.88,h*.88),None,color,stroke)
            if name == 'info':
                path([(.5,.45),(.5,.72)])
                self.circle((x+w*.46,y+h*.26,w*.08,h*.08),color)
            else:
                path([(.33,.34),(.4,.25),(.57,.25),(.67,.34),(.65,.45),(.5,.54),(.5,.61)])
                self.circle((x+w*.46,y+h*.73,w*.08,h*.08),color)
        elif name == 'star':
            self.draw.polygon(points([(.5,0),(.62,.36),(1,.5),(.62,.64),(.5,1),(.38,.64),(0,.5),(.38,.36)]),fill=color)
        elif name == 'folder':
            path([(.06,.3),(.06,.85),(.94,.85),(.94,.26),(.48,.26),(.38,.12),(.06,.12),(.06,.3)],True)

    def finish(self):
        return self.image.resize((round(self.width * self.scale), round(self.height * self.scale)), Image.Resampling.LANCZOS)

    def photo(self, master):
        return WidgetPhotoImage(self.finish(), master=master)


def place(widget, x, y, w=None, h=None, scale=None):
    s = scale or ui_scale(widget)
    options = {'x':round(x*s),'y':round(y*s)}
    if w is not None:
        options['width']=round(w*s)
    if h is not None:
        options['height']=round(h*s)
    widget.place(**options)


def position_window(window, x, y, width=None, height=None):
    if width is not None:
        window.geometry(f'{round(width)}x{round(height)}')
    if os.name == 'nt':
        from ctypes import wintypes
        user = ctypes.windll.user32
        user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user.GetAncestor.restype = wintypes.HWND
        user.SetWindowPos.argtypes = [wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,
                                     ctypes.c_int,ctypes.c_int,wintypes.UINT]
        user.SetWindowPos.restype = wintypes.BOOL
        hwnd = user.GetAncestor(window.winfo_id(), 2)
        flags = 0x0004 | 0x0010 | (0x0001 if width is None else 0)
        user.SetWindowPos(hwnd, None, round(x), round(y), round(width or 0), round(height or 0), flags)
    else:
        window.geometry(f'{round(x):+d}{round(y):+d}')


class Hint:
    def __init__(self, widget, text):
        self.widget, self._text = widget, text
        self.popup = self.job = None
        for event in ('<Leave>','<ButtonPress>','<MouseWheel>','<Destroy>'):
            widget.bind(event, self.hide, add='+')
        widget.bind('<Enter>', self._enter, add='+')

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        if value != self._text:
            self.hide()
            self._text = value

    def _enter(self, _=None):
        if self._text and self.job is None and self.popup is None:
            self.job = self.widget.after(500, self._show)

    def _show(self):
        self.job = None
        if not self._text or not self.widget.winfo_exists():
            return
        s = ui_scale(self.widget)
        width = min(260, max(60, min(measure(line,12) for line in [self._text]) + 20))
        rows = wrap(self._text, width - 20,12,lines=20)
        height = 20 + len(rows)*18
        art = Artboard(width,height,s,bg=TRANSPARENT)
        art.rect((0,0,width,height),RAISED,8)
        art.text((10,10,width-20,height-20),self._text,12,lines=20,line_height=18)
        popup = self.popup = tk.Toplevel(self.widget)
        popup.withdraw(); popup.overrideredirect(True); popup.attributes('-topmost',True)
        popup.configure(bg=TRANSPARENT)
        if os.name == 'nt': popup.attributes('-transparentcolor',TRANSPARENT)
        canvas = tk.Canvas(popup,width=round(width*s),height=round(height*s),bg=TRANSPARENT,bd=0,highlightthickness=0)
        canvas.pack(); canvas.photo=art.photo(canvas); canvas.create_image(0,0,image=canvas.photo,anchor='nw')
        left,top,right,bottom=work_area(self.widget)
        x=max(left,min(self.widget.winfo_rootx(),right-round(width*s)))
        y=max(top,min(self.widget.winfo_rooty()+self.widget.winfo_height()+4,bottom-round(height*s)))
        from .windows import prepare_popup
        prepare_popup(popup); position_window(popup,x,y,round(width*s),round(height*s)); popup.deiconify()

    def hide(self, _=None):
        if self.job is not None:
            try: self.widget.after_cancel(self.job)
            except tk.TclError: pass
            self.job=None
        if self.popup is not None:
            try: self.popup.destroy()
            except tk.TclError: pass
            self.popup=None
