from pathlib import Path
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'public' / 'assets' / 'social' / 'RRGH-0001-Double_Rainbow_at_Eagles_Point_Buttress-SOCIAL-WM.jpg'
OUT = ROOT / 'public' / 'assets' / 'catalog' / 'RRGH-0001-Double_Rainbow_at_Eagles_Point_Buttress-PINTEREST-CATALOG.jpg'
W, H = 1200, 1800

img = Image.open(SRC).convert('RGB')

# Background uses only the approved photograph itself: enlarged, center-cropped,
# strongly blurred, and darkened. The sharp foreground is the complete uncropped
# approved watermarked image, preserving Ryan D. Lewis attribution/copyright.
scale_bg = max(W / img.width, H / img.height)
bg = img.resize((round(img.width * scale_bg), round(img.height * scale_bg)), Image.Resampling.LANCZOS)
left = (bg.width - W) // 2
top = (bg.height - H) // 2
bg = bg.crop((left, top, left + W, top + H))
bg = bg.filter(ImageFilter.GaussianBlur(radius=50))
bg = ImageEnhance.Brightness(bg).enhance(0.55)

max_fg_w = 1140
scale_fg = min(max_fg_w / img.width, 1)
fg = img.resize((round(img.width * scale_fg), round(img.height * scale_fg)), Image.Resampling.LANCZOS)

canvas = bg.copy().convert('RGBA')
x = (W - fg.width) // 2
y = (H - fg.height) // 2
shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
draw = ImageDraw.Draw(shadow)
pad = 18
draw.rounded_rectangle((x - pad, y - pad, x + fg.width + pad, y + fg.height + pad), radius=10, fill=(0, 0, 0, 110))
shadow = shadow.filter(ImageFilter.GaussianBlur(16))
canvas = Image.alpha_composite(canvas, shadow)
canvas.alpha_composite(fg.convert('RGBA'), (x, y))

OUT.parent.mkdir(parents=True, exist_ok=True)
canvas.convert('RGB').save(OUT, quality=92, optimize=True, progressive=True)

check = Image.open(OUT)
assert check.size == (W, H)
print(f'WROTE {OUT.relative_to(ROOT)} {check.width}x{check.height} {OUT.stat().st_size} bytes')
