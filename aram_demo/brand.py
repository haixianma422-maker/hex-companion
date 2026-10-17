"""The 海克斯随行 mark as a Pillow image, for the tray icon and the EXE icon."""
import re

from PIL import Image, ImageDraw

ACCENT = '#DFFF80'
BG = '#191723'
SUPERSAMPLE = 4
# A 24-unit path: the outer mark, then the inner cut-out.
BRAND = '''M12 1 C14 1 14 6 15.5 7 L21 7 C24 7 22 10 19 12 L21 18
C22 21 18 21 15 18 L12 23 C10 25 8 21 8 17 L2 17 C-1 17 1 13 5 11
L2 7 C0 4 4 3 8 6 L10 2 C10.5 1 11 1 12 1 Z M7 9 L10 12 L7 15 L10 15 L13 12 L10 9 Z'''


def brand_paths():
    """Flatten the cubic path into polygons (16 steps per curve)."""
    tokens = re.findall(r'[MCLZ]|-?\d+(?:\.\d+)?', BRAND)
    paths, points, current, index = [], [], (0, 0), 0
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


def brand_image(size=64):
    """The mark on a dark disc, antialiased by drawing at 4× and downsampling."""
    big = size * SUPERSAMPLE
    image = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((0, 0, (size - 1) * SUPERSAMPLE, (size - 1) * SUPERSAMPLE), fill=BG)
    mark = round(size * .55 * SUPERSAMPLE)
    layer = Image.new('RGBA', (mark, mark))
    draw = ImageDraw.Draw(layer)
    for index, points in enumerate(brand_paths()):
        draw.polygon([(round(px / 24 * mark), round(py / 24 * mark)) for px, py in points],
                     fill=ACCENT if index == 0 else (0, 0, 0, 0))
    inset = round(size * .225 * SUPERSAMPLE)
    image.alpha_composite(layer, (inset, inset))
    return image.resize((size, size), Image.Resampling.LANCZOS)
