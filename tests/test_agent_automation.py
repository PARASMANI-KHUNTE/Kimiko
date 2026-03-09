"""Tests for OS automation executor with mocked pywinauto symbols."""

from kimiko.os import automation_executor as ae


def test_execute_returns_error_when_pywinauto_missing(monkeypatch):
    monkeypatch.setattr(ae, "Application", None)
    executor = ae.AutomationExecutor()
    result = executor.execute("app_open", {"path": "notepad.exe"})
    assert "not supported or installed" in result


def test_app_open_starts_process_with_args(monkeypatch):
    calls = []

    class FakeApp:
        def __init__(self, backend):
            self.backend = backend

        def start(self, command):
            calls.append(command)
            return self

    monkeypatch.setattr(ae, "Application", FakeApp)
    monkeypatch.setattr(ae.time, "sleep", lambda *_args, **_kwargs: None)

    executor = ae.AutomationExecutor()
    result = executor.execute("app_open", {"path": "notepad.exe", "args": "README.md"})

    assert result == "Successfully started 'notepad.exe'."
    assert calls == ['"notepad.exe" README.md']


def test_app_focus_sets_target_window(monkeypatch):
    class FakeWindow:
        def __init__(self):
            self.focused = False

        def set_focus(self):
            self.focused = True

        def window_text(self):
            return "Untitled - Notepad"

    fake_window = FakeWindow()

    class FakeDesktop:
        def __init__(self, backend):
            self.backend = backend

        def windows(self, title_re, visible_only):
            assert "Notepad" in title_re
            assert visible_only is True
            return [fake_window]

    monkeypatch.setattr(ae, "Application", object())
    monkeypatch.setattr(ae, "Desktop", FakeDesktop)

    executor = ae.AutomationExecutor()
    result = executor.execute("app_focus", {"title": "Notepad"})

    assert fake_window.focused is True
    assert "Successfully focused window 'Untitled - Notepad'." == result


def test_app_type_uses_send_keys(monkeypatch):
    sent = {}

    def fake_send_keys(keys, with_spaces):
        sent["keys"] = keys
        sent["with_spaces"] = with_spaces

    monkeypatch.setattr(ae, "Application", object())
    monkeypatch.setattr(ae, "send_keys", fake_send_keys)

    executor = ae.AutomationExecutor()
    result = executor.execute("app_type", {"keys": "Hello World"})

    assert result == "Successfully typed 'Hello World' into the active window."
    assert sent == {"keys": "Hello World", "with_spaces": True}


def test_app_click_targets_control_and_clicks(monkeypatch):
    capture = {"clicked": False, "kwargs": None}

    class FakeElement:
        def click_input(self):
            capture["clicked"] = True

    class FakeWindow:
        def set_focus(self):
            return None

        def window_text(self):
            return "Calculator"

        def child_window(self, **kwargs):
            capture["kwargs"] = kwargs
            return FakeElement()

    class FakeDesktop:
        def __init__(self, backend):
            self.backend = backend

        def windows(self, title_re, visible_only):
            assert "Calculator" in title_re
            assert visible_only is True
            return [FakeWindow()]

    monkeypatch.setattr(ae, "Application", object())
    monkeypatch.setattr(ae, "Desktop", FakeDesktop)

    executor = ae.AutomationExecutor()
    result = executor.execute(
        "app_click",
        {"title": "Calculator", "control_type": "Button", "title_re": "Equals"},
    )

    assert result == "Successfully clicked element in 'Calculator'."
    assert capture["clicked"] is True
    assert capture["kwargs"] == {"title_re": "Equals", "control_type": "Button"}


def test_unsupported_action_returns_error(monkeypatch):
    monkeypatch.setattr(ae, "Application", object())
    executor = ae.AutomationExecutor()
    result = executor.execute("unknown_action", {})
    assert "Unsupported automation action" in result
