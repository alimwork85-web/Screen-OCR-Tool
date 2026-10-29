"""مجموعة أيقونات الواجهة: شبكة 24x24، خط بسماكة 2، أطراف وزوايا مستديرة.

مصدر واحد لكل أيقونة (قائمة أشكال) يُرسَم منه صور Pillow للواجهة وملفات SVG للتوثيق.
"""
from PIL import Image, ImageDraw

GRID = 24
STROKE = 2

# الأشكال: line / poly (مفتوح) / polyc (مغلق) / rect / circle / ellipse / dot
ICONS = {
    # أقواس التصوير مع سطري نص
    "capture": [
        ("poly", [(4, 9), (4, 4), (9, 4)]),
        ("poly", [(15, 4), (20, 4), (20, 9)]),
        ("poly", [(20, 15), (20, 20), (15, 20)]),
        ("poly", [(9, 20), (4, 20), (4, 15)]),
        ("line", 8.5, 10.5, 15.5, 10.5),
        ("line", 8.5, 14, 13, 14),
    ],
    "copy": [
        ("rect", 9, 9, 11, 11, 2.5),
        ("poly", [(15, 5), (6.5, 5), (5, 6.5), (5, 15), (6, 16)]),
    ],
    "check": [
        ("poly", [(5, 12.5), (10, 17.5), (19, 7)]),
    ],
    "alert": [
        ("polyc", [(12, 4), (21, 19.5), (3, 19.5)]),
        ("line", 12, 10, 12, 14),
        ("dot", 12, 17),
    ],
    "error": [
        ("circle", 12, 12, 9),
        ("line", 9, 9, 15, 15),
        ("line", 15, 9, 9, 15),
    ],
    "clock": [
        ("circle", 12, 12, 9),
        ("poly", [(12, 7), (12, 12), (15.5, 14)]),
    ],
    "history": [
        ("line", 9, 7, 20, 7),
        ("line", 9, 12, 20, 12),
        ("line", 9, 17, 20, 17),
        ("dot", 4.5, 7),
        ("dot", 4.5, 12),
        ("dot", 4.5, 17),
    ],
    "trash": [
        ("line", 4, 7, 20, 7),
        ("poly", [(9, 7), (9, 4.5), (15, 4.5), (15, 7)]),
        ("poly", [(6.5, 7), (7.5, 19.5), (16.5, 19.5), (17.5, 7)]),
        ("line", 10.5, 11, 10.5, 16),
        ("line", 13.5, 11, 13.5, 16),
    ],
    "search": [
        ("circle", 10.5, 10.5, 6.5),
        ("line", 15.5, 15.5, 20, 20),
    ],
    # سهما الطي: لليسار = إظهار المحتوى (في واجهة من اليمين)، لليمين = إخفاؤه
    "chevron_left": [
        ("poly", [(14.5, 6), (8.5, 12), (14.5, 18)]),
    ],
    "chevron_right": [
        ("poly", [(9.5, 6), (15.5, 12), (9.5, 18)]),
    ],
    "globe": [
        ("circle", 12, 12, 9),
        ("line", 3, 12, 21, 12),
        ("ellipse", 12, 12, 4, 9),
    ],
    # تبديل لغة الواجهة: سهمان متبادلان (والكرة الأرضية تبقى للترجمة)
    "language": [
        ("poly", [(4, 8), (19, 8)]),
        ("poly", [(15.5, 4.5), (19, 8), (15.5, 11.5)]),
        ("poly", [(20, 16), (5, 16)]),
        ("poly", [(8.5, 12.5), (5, 16), (8.5, 19.5)]),
    ],
    # لغات القراءة: فقاعة كلام بنقاط (حرفا A وع لا يقرآن بوضوح، وفقاعتان تشبهان أيقونة النسخ)
    "languages": [
        ("rect", 3, 5, 18, 12, 3),
        ("poly", [(7, 17), (7, 20.5), (10.5, 17)]),
        ("dot", 8.5, 11),
        ("dot", 12, 11),
        ("dot", 15.5, 11),
    ],
}

_SS = 16  # التكبير قبل التصغير لتنعيم الحواف


def render(name, size, color, stroke=STROKE):
    """يرسم الأيقونة بحجم size بكسل (مربع) باللون color ويعيد صورة RGBA."""
    k = size * _SS / GRID
    img = Image.new("RGBA", (size * _SS, size * _SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(1, round(stroke * k))
    r = w / 2

    def p(x, y):
        return (x * k, y * k)

    def cap(pt):
        d.ellipse((pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r), fill=color)

    def line(pts):
        pts = [p(*q) for q in pts]
        d.line(pts, fill=color, width=w)
        for q in pts:
            cap(q)

    for shape in ICONS[name]:
        kind = shape[0]
        if kind == "line":
            line([(shape[1], shape[2]), (shape[3], shape[4])])
        elif kind == "poly":
            line(shape[1])
        elif kind == "polyc":
            line(shape[1] + [shape[1][0], shape[1][1]])
        elif kind == "rect":
            x, y, rw, rh, rr = shape[1:]
            d.rounded_rectangle((x * k, y * k, (x + rw) * k, (y + rh) * k), radius=rr * k, outline=color, width=w)
        elif kind == "circle":
            cx, cy, cr = shape[1:]
            d.ellipse(((cx - cr) * k, (cy - cr) * k, (cx + cr) * k, (cy + cr) * k), outline=color, width=w)
        elif kind == "ellipse":
            cx, cy, rx, ry = shape[1:]
            d.ellipse(((cx - rx) * k, (cy - ry) * k, (cx + rx) * k, (cy + ry) * k), outline=color, width=w)
        elif kind == "dot":
            cap(p(shape[1], shape[2]))
    return img.resize((size, size), Image.LANCZOS)


def to_svg(name):
    """يعيد نص SVG للأيقونة، يتبع currentColor."""
    out = []
    for shape in ICONS[name]:
        kind = shape[0]
        if kind == "line":
            out.append(f'<line x1="{shape[1]}" y1="{shape[2]}" x2="{shape[3]}" y2="{shape[4]}"/>')
        elif kind in ("poly", "polyc"):
            pts = " ".join(f"{x},{y}" for x, y in shape[1])
            tag = "polyline" if kind == "poly" else "polygon"
            out.append(f'<{tag} points="{pts}"/>')
        elif kind == "rect":
            out.append(f'<rect x="{shape[1]}" y="{shape[2]}" width="{shape[3]}" height="{shape[4]}" rx="{shape[5]}"/>')
        elif kind == "circle":
            out.append(f'<circle cx="{shape[1]}" cy="{shape[2]}" r="{shape[3]}"/>')
        elif kind == "ellipse":
            out.append(f'<ellipse cx="{shape[1]}" cy="{shape[2]}" rx="{shape[3]}" ry="{shape[4]}"/>')
        elif kind == "dot":
            out.append(f'<circle cx="{shape[1]}" cy="{shape[2]}" r="1" fill="currentColor" stroke="none"/>')
    body = "\n  ".join(out)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}" width="{GRID}" height="{GRID}" '
        f'fill="none" stroke="currentColor" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round">\n'
        f"  {body}\n</svg>\n"
    )


_cache = {}


def tk_icon(name, size, color):
    """صورة Tk جاهزة للاستخدام؛ تُخزَّن حتى لا يجمعها مدقق الذاكرة."""
    from PIL import ImageTk
    key = (name, size, color)
    if key not in _cache:
        _cache[key] = ImageTk.PhotoImage(render(name, size, color))
    return _cache[key]
