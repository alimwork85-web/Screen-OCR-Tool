"""أسماء الاختصارات: الحروف التي تقرأها المكتبة بلغة الكيبورد تُعرض بالمفتاح اللاتيني نفسه."""

import keyboard


def test_latin_combo_is_unchanged(app):
    assert app.latin_hotkey("ctrl+shift+x") == "ctrl+shift+x"


def test_arabic_letter_becomes_its_latin_key(app):
    if not keyboard.key_to_scan_codes("ن"):
        return  # لا توجد لوحة عربية على هذا الجهاز
    assert app.latin_hotkey("ctrl+alt+ن") == "ctrl+alt+k"
