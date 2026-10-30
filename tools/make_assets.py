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
INK, PAPER, RED, WHITE = (0x0F, 0x0F, 0x0F), (0xF5, 0xF5, 0xF2), (0xE5, 0x35, 0x2B), (255, 255, 255)  # حبر وورق وأحمر التحديد
M = 1024  # مساحة الرسم الرئيسية

# الهندسة بوحدات 1024: أقواس تصوير في الزوايا وثلاثة أسطر نص تبدأ من اليمين (اتجاه العربية)
BRACKETS = [
    [(250, 400), (250, 250), (400, 250)],
    [(624, 250), (774, 250), (774, 400)],
    [(774, 624), (774, 774), (624, 774)],
    [(400, 774), (250, 774), (250, 624)],
]
HILITE = (330, 358, 694, 470, 26)  # شريط النص المحدد بالأحمر (يسار، أعلى، يمين، أسفل، نصف القطر)
LINES = [(634, 414, 234, WHITE), (634, 552, 178, PAPER), (634, 640, 114, PAPER)]  # (يمين، y، الطول، اللون)
STROKE_BRACKET, STROKE_LINE = 64, 44


def draw_master(bold=False):
    mask = Image.new("L", (M, M), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, M - 1, M - 1), radius=230, fill=255)
    img = Image.new("RGBA", (M, M), INK + (255,))
    img.putalpha(mask)
    d = ImageDraw.Draw(img)

    def stroke(pts, w, color):
        d.line(pts, fill=color, width=w, joint="curve")
        for x, y in pts:
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color)

    extra = 28 if bold else 0  # نسخة أثخن للأحجام الصغيرة حتى تبقى الخطوط ظاهرة
    for pts in BRACKETS:
        stroke(pts, STROKE_BRACKET + extra, PAPER)
    l, t, r, b, rad = HILITE
    d.rounded_rectangle((l, t - extra // 2, r, b + extra // 2), radius=rad, fill=RED)
    for right, y, length, color in LINES[:1 if bold else 3]:
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
    l, t, r, b, rad = HILITE
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {M} {M}" width="{M}" height="{M}">
  <rect width="{M}" height="{M}" rx="230" fill="#0F0F0F"/>
  <g fill="none" stroke="#F5F5F2" stroke-width="{STROKE_BRACKET}" stroke-linecap="round" stroke-linejoin="round">
    {brackets}
  </g>
  <rect x="{l}" y="{t}" width="{r - l}" height="{b - t}" rx="{rad}" fill="#E5352B"/>
  <g stroke-linecap="round" stroke-width="{STROKE_LINE}">
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
