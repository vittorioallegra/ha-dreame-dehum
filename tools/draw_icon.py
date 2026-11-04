"""Draw the integration icon: a dehumidifier with a water drop.

.venv/bin/python tools/draw_icon.py custom_components/dreame_dehum/brand
"""

import sys

from PIL import Image, ImageDraw

out = sys.argv[1]
N = 2048
img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
BODY = (14, 150, 160, 255)
DEEP = (10, 112, 122, 255)
LIGHT = (255, 255, 255, 255)
WATER = (125, 211, 252, 255)
cx = N // 2

# Body and top grille.
d.rounded_rectangle((424, 160, 1624, 1928), radius=240, fill=BODY)
for i in range(4):
    y = 300 + i * 110
    d.rounded_rectangle((cx - 420, y, cx + 420, y + 56), radius=28, fill=DEEP)
# Water drop: a circle with a triangle on top.
dy, r = 1180, 300
d.ellipse((cx - r, dy - r, cx + r, dy + r), fill=LIGHT)
d.polygon([(cx - 262, dy - 146), (cx, dy - 560), (cx + 262, dy - 146)], fill=LIGHT)
r2 = 230
d.ellipse((cx - r2, dy - r2 + 20, cx + r2, dy + r2 + 20), fill=WATER)
d.polygon([(cx - 196, dy - 100), (cx, dy - 440), (cx + 196, dy - 100)], fill=WATER)
# Tank.
d.rounded_rectangle((cx - 420, 1620, cx + 420, 1800), radius=40, fill=DEEP)

img = img.crop(img.getbbox())
side = int(max(img.size) * 1.04)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
for size, name in ((256, "icon.png"), (512, "icon@2x.png")):
    square.resize((size, size), Image.LANCZOS).save(f"{out}/{name}", optimize=True)
