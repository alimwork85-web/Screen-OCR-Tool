"""يولّد أيقونة التطبيق (SVG وPNG وICO) وملفات SVG لأيقونات الواجهة داخل assets/.

التشغيل:  py -3.14 tools/make_assets.py
"""
import os
import sys

from PIL import Image, ImageChops, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ui_icons  # noqa: E402

ASSETS = os.path.join(ROOT, "assets")
TEAL_A, TEAL_B = (0x14, 0x9A, 0xA3), (0x0A, 0x45, 0x63)
WHITE, AMBER = (255, 255, 255), (0xF5, 0xB5, 0x44)
M = 1024  # مساحة الرسم الرئيسية

# الهندسة بوحدات 1024: أقواس تصوير في الزوايا وثلاثة أسطر نص تبدأ من اليمين (اتجاه العربية)
BRACKETS = [
    [(250, 400), (250, 250), (400, 250)],
    [(624, 250), (774, 250), (774, 400)],
    [(774, 624), (774, 774), (624, 774)],
    [(400, 774), (250, 774), (250, 624)],
]
LINES = [(648, 420, 264, AMBER), (648, 512, 200, WHITE), (648, 604, 130, WHITE)]  # (يمين، y، الطول، اللون)
STROKE_BRACKET, STROKE_LINE = 64, 58


def draw_master(bold=False):
    ramp = Image.linear_gradient("L").resize((M, M))
    diag = ImageChops.add(ramp, ramp.rotate(90).transpose(Image.FLIP_LEFT_RIGHT), scale=2)
    bg = Image.composite(Image.new("RGB", (M, M), TEAL_B), Image.new("RGB", (M, M), TEAL_A), diag)
    mask = Image.new("L", (M, M), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, M - 1, M - 1), radius=230, fill=255)
    img = bg.convert("RGBA")
    img.putalpha(mask)
    d = ImageDraw.Draw(img)

    def stroke(pts, w, color):
        d.line(pts, fill=color, width=w, joint="curve")
        for x, y in pts:
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color)

    extra = 28 if bold else 0  # نسخة أثخن للأحجام الصغيرة حتى تبقى الخطوط ظاهرة
    for pts in BRACKETS:
        stroke(pts, STROKE_BRACKET + extra, WHITE)
    for right, y, length, color in LINES:
        stroke([(right - length, y), (right, y)], STROKE_LINE + extra, color)
    return img


def app_icon_svg():
    def pts(p):
        return " ".join(f"{x},{y}" for x, y in p)
    brackets = "\n    ".join(f'<polyline points="{pts(b)}"/>' for b in BRACKETS)
    lines = "\n    ".join(
        f'<line x1="{r - l}" y1="{y}" x2="{r}" y2="{y}" stroke="#{c[0]:02X}{c[1]:02X}{c[2]:02X}" stroke-width="{STROKE_LINE}"/>'
        for r, y, l, c in LINES
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {M} {M}" width="{M}" height="{M}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#149AA3"/>
      <stop offset="1" stop-color="#0A4563"/>
    </linearGradient>
  </defs>
  <rect width="{M}" height="{M}" rx="230" fill="url(#bg)"/>
  <g fill="none" stroke="#FFFFFF" stroke-width="{STROKE_BRACKET}" stroke-linecap="round" stroke-linejoin="round">
    {brackets}
  </g>
  <g stroke-linecap="round">
    {lines}
  </g>
</svg>
'''


def main():
    os.makedirs(os.path.join(ASSETS, "icons"), exist_ok=True)
    master = draw_master()
    sizes = [16, 32, 48, 64, 128, 256, 512, 1024]
    bold = draw_master(bold=True)
    frames = {s: (bold if s <= 32 else master).resize((s, s), Image.LANCZOS) for s in sorted(set(sizes) | {24})}
    for s in sizes:
        frames[s].save(os.path.join(ASSETS, f"app_icon_{s}.png"))
    ico_sizes = (16, 24, 32, 48, 64, 128, 256)
    frames[256].save(
        os.path.join(ASSETS, "app_icon.ico"), format="ICO",
        sizes=[(s, s) for s in ico_sizes], append_images=[frames[s] for s in ico_sizes if s != 256],
    )
    with open(os.path.join(ASSETS, "app_icon.svg"), "w", encoding="utf-8") as f:
        f.write(app_icon_svg())
    for name in ui_icons.ICONS:
        with open(os.path.join(ASSETS, "icons", f"{name}.svg"), "w", encoding="utf-8") as f:
            f.write(ui_icons.to_svg(name))
    print("done:", len(sizes), "png,", len(ui_icons.ICONS), "svg icons, ico")


if __name__ == "__main__":
    main()
