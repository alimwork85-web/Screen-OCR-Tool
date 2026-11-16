"""الأزرار المستديرة (RoundButton): تتصرف كأزرار Tk التي حلّت محلها."""
import tkinter as tk

import pytest


@pytest.fixture
def top(app):
    """نافذة ظاهرة: Tk لا يوصل أحداث الفأرة لعنصر في نافذة مخفية (والنافذة الرئيسية مخفية في الاختبارات)."""
    window = tk.Toplevel(app.root)
    yield window
    window.destroy()


def click(button, x=2, y=2):
    button.update()
    button.event_generate("<Enter>")
    button.event_generate("<ButtonPress-1>", x=2, y=2)
    button.event_generate("<ButtonRelease-1>", x=x, y=y)
    button.update()


def test_click_runs_command_unless_disabled(app, top):
    calls = []
    button = app.RoundButton(top, "x", lambda: calls.append(1))
    button.pack()
    click(button)
    assert calls == [1]
    button.config(state="disabled")
    click(button)
    assert calls == [1]


def test_release_outside_does_not_run(app, top):
    calls = []
    button = app.RoundButton(top, "x", lambda: calls.append(1))
    button.pack()
    click(button, x=500, y=500)
    assert calls == []


def test_text_change_resizes(app, top):
    chip = app.RoundButton(top, "Esc", kind="key")
    narrow = chip.winfo_reqwidth()
    chip.config(text="Ctrl+Shift+Alt+X")
    assert chip.winfo_reqwidth() > narrow


def test_language_option_sets_reading_language(app, monkeypatch):
    monkeypatch.setattr(app, "save_settings", lambda: None)  # لا نكتب في إعدادات المستخدم الحقيقية
    before = app.lang_var.get()
    try:
        for option, value in zip(app._lang_options, app.LANG_VALUES):
            option.invoke()
            assert app.lang_var.get() == value
    finally:
        app.lang_var.set(before)


def test_theme_switch_redraws_everything(app):
    current = app.theme_mode
    for mode in ("light", "dark", current):
        app.apply_theme(mode)
    app.set_status("ok", "ok")
    app.set_status("plain", "info")
