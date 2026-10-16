"""Cached, clipped Pillow composites for the V2 motion handoff."""
from PIL import Image, ImageDraw


class RegionTransition:
    def __init__(self, old, new, regions, scale=1., shift=0., base='new', radius=0):
        self.old, self.new = old, new
        self.shift, self.base = shift * scale, base
        self.regions = []
        for x, y, width, height in regions:
            box = tuple(round(v * scale) for v in (x, y, x+width, y+height))
            before, after = old.crop(box), new.crop(box)
            mask = None
            if radius:
                mask = Image.new('L', before.size)
                ImageDraw.Draw(mask).rounded_rectangle((0,0,before.width-1,before.height-1),
                    radius=round(radius*scale), fill=255)
            self.regions.append((box, before, after, mask))
        self.progress = 0.

    def retarget(self, new):
        """Keep the current progress; later frames move toward the new picture."""
        self.new = new
        self.regions = [(box, before, new.crop(box), mask) for box, before, _, mask in self.regions]

    def frame(self, progress):
        self.progress = progress
        if progress >= 1:
            return self.new
        frame = (self.old if self.base == 'old' else self.new).copy()
        for box, before, after, mask in self.regions:
            offset = self.shift * (1-progress)
            if offset:
                layer = after.transform(after.size, Image.Transform.AFFINE,
                    (1,0,0,0,1,-offset), Image.Resampling.BICUBIC)
                # A translated canvas leaves the previous frame visible at its top.
                shifted = before.copy()
                shifted.paste(layer, (0,0), layer.getchannel('A'))
            else:
                shifted = after
            part = Image.blend(before, shifted, progress)
            frame.paste(part, box, mask)
        return frame


def dim_regions(old, new, regions, scale=1.):
    frame = new.copy()
    for x,y,w,h in regions:
        box = tuple(round(v*scale) for v in (x,y,x+w,y+h))
        before = old.crop(box).convert('RGBA')
        shade = Image.new('RGBA', before.size, '#191723')
        frame.paste(Image.blend(before,shade,.46),box)
    return frame


def visibility_image(image, amount, scale):
    """Scale about (W-32,H-32), where the bubble sits, then translate Y by at most 14 pixels."""
    factor = .86 + .14 * amount
    anchor_x, anchor_y = image.width-32*scale, image.height-32*scale
    dx, dy = anchor_x*(1-factor), anchor_y*(1-factor)+14*scale*(1-amount)
    return image.transform(image.size, Image.Transform.AFFINE,
        (1/factor,0,-dx/factor,0,1/factor,-dy/factor), Image.Resampling.BICUBIC,
        fillcolor=(1,2,3,255))
