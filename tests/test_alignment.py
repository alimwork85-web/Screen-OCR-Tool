"""محاذاة مربع النص الأصلي: النص العربي يأخذ وسم rtl، والنص الإنجليزي لا يأخذه."""


def test_arabic_text_gets_rtl_tag(app):
    app.show_original("قراءة النص العربي من الشاشة")
    assert app.original_text_area.tag_ranges("rtl")


def test_english_text_has_no_rtl_tag(app):
    app.show_original("English sample text")
    assert not app.original_text_area.tag_ranges("rtl")


def test_switching_back_to_arabic_restores_tag(app):
    app.show_original("English sample text")
    app.show_original("السعر 45 SAR شامل الضريبة")
    assert app.original_text_area.tag_ranges("rtl")
