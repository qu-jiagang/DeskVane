from __future__ import annotations

from collections.abc import Callable
import ctypes
from ctypes import wintypes
import sys
import threading
import time

from ..log import get_logger
from .base import HotkeyBackend

_logger = get_logger("hotkeys")


class PynputBackend(HotkeyBackend):
    """Fallback backend using pure pynput (no key suppression)."""

    def __init__(self, app) -> None:
        self.app = app
        self._listener = None
        self._bindings: dict[str, Callable] = {}

    def register(self, hotkey: str, callback: Callable) -> None:
        self._bindings[hotkey] = callback

    def start(self) -> None:
        if not self._bindings:
            return
        try:
            from pynput.keyboard import HotKey, Listener
        except ImportError:
            return

        def _make_dispatcher(fn: Callable):
            def _dispatch():
                self.app.dispatcher.call_soon(fn)

            return _dispatch

        parsed_bindings = []
        for hotkey, callback in self._bindings.items():
            keys = set(HotKey.parse(hotkey))
            parsed_bindings.append((keys, _make_dispatcher(callback)))
        parsed_bindings.sort(key=lambda item: len(item[0]), reverse=True)

        current_keys = set()

        def on_press(key):
            key = self._listener.canonical(key)
            current_keys.add(key)
            for keys, callback in parsed_bindings:
                if keys.issubset(current_keys):
                    callback()
                    current_keys.clear()
                    break

        def on_release(key):
            key = self._listener.canonical(key)
            current_keys.discard(key)

        self._listener = Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def clear(self) -> None:
        self._bindings.clear()


class MacOSHotkeyBackend(PynputBackend):
    """macOS backend using pynput as the current maintained fallback."""


class KeyboardBackend(HotkeyBackend):
    """Linux backend using the `keyboard` package with suppression."""

    def __init__(self, app) -> None:
        import keyboard

        self.app = app
        self.keyboard = keyboard
        self._bindings: dict[str, Callable] = {}

    @staticmethod
    def _convert_hotkey(hotkey: str) -> str:
        return hotkey.replace("<", "").replace(">", "")

    def register(self, hotkey: str, callback: Callable) -> None:
        self._bindings[hotkey] = callback

    def start(self) -> None:
        for hotkey, callback in self._bindings.items():
            parsed_hk = self._convert_hotkey(hotkey)

            def _make_cb(fn=callback):
                return lambda: self.app.dispatcher.call_soon(fn)

            try:
                self.keyboard.add_hotkey(parsed_hk, _make_cb(), suppress=True)
                _logger.info("Grabbed hotkey (keyboard): %s", parsed_hk)
            except Exception as exc:
                _logger.error("Failed to grab hotkey %s via keyboard: %s", parsed_hk, exc)

    def stop(self) -> None:
        try:
            self.keyboard.unhook_all()
        except Exception:
            pass

    def clear(self) -> None:
        self._bindings.clear()


class X11Backend(HotkeyBackend):
    """Linux X11 backend using XGrabKey."""

    def __init__(self, app) -> None:
        from Xlib import X, XK, display

        self.app = app
        self.X = X
        self.XK = XK
        self.display_module = display
        self.d = display.Display()
        self.root = self.d.screen().root
        self._bindings: dict[str, Callable] = {}
        self._running = False
        self._thread = None
        self.grabbed_keys = {}

    def _parse_hotkey(self, hotkey: str):
        from pynput.keyboard import HotKey, Key, KeyCode

        keys = set(HotKey.parse(hotkey))
        modifiers = 0
        keycode = None

        for key in keys:
            if key in {Key.ctrl, Key.ctrl_l, Key.ctrl_r}:
                modifiers |= self.X.ControlMask
            elif key in {Key.alt, Key.alt_l, Key.alt_r}:
                modifiers |= self.X.Mod1Mask
            elif key in {Key.shift, Key.shift_l, Key.shift_r}:
                modifiers |= self.X.ShiftMask
            elif key in {Key.cmd, Key.cmd_l, Key.cmd_r}:
                modifiers |= self.X.Mod4Mask
            elif isinstance(key, KeyCode):
                if getattr(key, "char", None):
                    keysym = self.XK.string_to_keysym(key.char)
                    keycode = self.d.keysym_to_keycode(keysym)
                elif hasattr(key, "vk"):
                    keycode = self.d.keysym_to_keycode(key.vk)
            elif isinstance(key, Key):
                keysym_str = key.name.capitalize() if key.name.startswith("f") and key.name[1:].isdigit() else key.name
                keysym = self.XK.string_to_keysym(keysym_str)
                if keysym == self.X.NoSymbol and hasattr(key.value, "vk"):
                    keycode = self.d.keysym_to_keycode(key.value.vk)
                else:
                    keycode = self.d.keysym_to_keycode(keysym)
        return keycode, modifiers

    def register(self, hotkey: str, callback: Callable) -> None:
        self._bindings[hotkey] = callback

    def start(self) -> None:
        self.d = self.display_module.Display()
        self.root = self.d.screen().root
        self.grabbed_keys.clear()
        for hotkey, callback in self._bindings.items():
            try:
                keycode, modifiers = self._parse_hotkey(hotkey)
                if keycode:
                    for extra_mod in [0, self.X.Mod2Mask, self.X.LockMask, self.X.Mod2Mask | self.X.LockMask]:
                        self.root.grab_key(
                            keycode,
                            modifiers | extra_mod,
                            True,
                            self.X.GrabModeAsync,
                            self.X.GrabModeAsync,
                        )
                    self.grabbed_keys[(keycode, modifiers)] = callback
                    _logger.info("Grabbed X11 key: %s (keycode=%s, modifiers=%s)", hotkey, keycode, modifiers)
            except Exception as exc:
                _logger.error("Failed to grab X11 hotkey %s: %s", hotkey, exc)
        self._running = True
        self._thread = threading.Thread(target=self._event_loop, daemon=True)
        self._thread.start()

    def _event_loop(self):
        while self._running:
            while self.d.pending_events():
                event = self.d.next_event()
                if event.type == self.X.KeyPress:
                    keycode = event.detail
                    modifiers = event.state & ~(self.X.LockMask | self.X.Mod2Mask | self.X.Mod5Mask)
                    callback = self.grabbed_keys.get((keycode, modifiers))
                    if callback:
                        self.app.dispatcher.call_soon(callback)
            time.sleep(0.05)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        try:
            self.root.ungrab_key(self.X.AnyKey, self.X.AnyModifier)
            self.d.sync()
            self.d.close()
        except Exception:
            pass

    def clear(self) -> None:
        self._bindings.clear()


class WindowsHotkeyBackend(HotkeyBackend):
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008

    def __init__(self, app) -> None:
        self.app = app
        self._bindings: dict[str, Callable] = {}
        self._callbacks: dict[int, Callable] = {}
        self._thread = None
        self._thread_id: int | None = None
        self._running = False
        self._ready = threading.Event()

    def register(self, hotkey: str, callback: Callable) -> None:
        self._bindings[hotkey] = callback

    def start(self) -> None:
        if self._thread is not None or not self._bindings:
            return
        self._running = True
        self._ready.clear()
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=1.0)

    def stop(self) -> None:
        self._running = False
        user32 = getattr(ctypes, "windll", None)
        if self._thread_id is not None and user32 is not None:
            try:
                user32.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._thread_id = None
        self._callbacks.clear()

    def clear(self) -> None:
        self._bindings.clear()

    def _message_loop(self) -> None:
        try:
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
        except AttributeError:
            self._ready.set()
            return

        self._thread_id = int(kernel32.GetCurrentThreadId())
        self._callbacks.clear()
        registered_ids: list[int] = []
        next_id = 1
        for hotkey, callback in self._bindings.items():
            parsed = self._parse_hotkey(hotkey)
            if parsed is None:
                continue
            modifiers, virtual_key = parsed
            try:
                if user32.RegisterHotKey(None, next_id, modifiers, virtual_key):
                    self._callbacks[next_id] = callback
                    registered_ids.append(next_id)
                    next_id += 1
            except Exception as exc:
                _logger.warning("Failed to register Windows hotkey %s: %s", hotkey, exc)

        self._ready.set()
        message = wintypes.MSG()
        try:
            while self._running:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result in (0, -1):
                    break
                if message.message == self.WM_HOTKEY:
                    callback = self._callbacks.get(int(message.wParam))
                    if callback is not None:
                        self.app.dispatcher.call_soon(callback)
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            for hotkey_id in registered_ids:
                try:
                    user32.UnregisterHotKey(None, hotkey_id)
                except Exception:
                    continue

    @classmethod
    def _parse_hotkey(cls, hotkey: str) -> tuple[int, int] | None:
        modifiers = 0
        virtual_key = None
        for token in hotkey.split("+"):
            normalized = token.strip().strip("<>").lower()
            if not normalized:
                continue
            if normalized in {"ctrl", "control"}:
                modifiers |= cls.MOD_CONTROL
                continue
            if normalized == "alt":
                modifiers |= cls.MOD_ALT
                continue
            if normalized == "shift":
                modifiers |= cls.MOD_SHIFT
                continue
            if normalized in {"cmd", "win", "super"}:
                modifiers |= cls.MOD_WIN
                continue
            virtual_key = cls._virtual_key(normalized)
        if virtual_key is None:
            return None
        return modifiers, virtual_key

    @staticmethod
    def _virtual_key(token: str) -> int | None:
        if len(token) == 1 and token.isalnum():
            return ord(token.upper())
        if token.startswith("f") and token[1:].isdigit():
            index = int(token[1:])
            if 1 <= index <= 24:
                return 0x70 + index - 1
        special = {
            "tab": 0x09,
            "enter": 0x0D,
            "return": 0x0D,
            "esc": 0x1B,
            "escape": 0x1B,
            "space": 0x20,
            "left": 0x25,
            "up": 0x26,
            "right": 0x27,
            "down": 0x28,
            "insert": 0x2D,
            "delete": 0x2E,
            "home": 0x24,
            "end": 0x23,
            "pageup": 0x21,
            "pagedown": 0x22,
        }
        return special.get(token)


def create_hotkey_backend(app) -> HotkeyBackend:
    if sys.platform == "win32":
        try:
            _logger.info("Using WindowsHotkeyBackend for hotkeys")
            return WindowsHotkeyBackend(app)
        except Exception as exc:
            _logger.warning("WindowsHotkeyBackend failed/not-available: %s", exc)
            return PynputBackend(app)

    if sys.platform == "darwin":
        try:
            _logger.info("Using MacOSHotkeyBackend for hotkeys")
            return MacOSHotkeyBackend(app)
        except Exception as exc:
            _logger.warning("MacOSHotkeyBackend failed/not-available: %s", exc)
            return PynputBackend(app)

    if sys.platform != "linux":
        return PynputBackend(app)

    try:
        from Xlib import display

        d = display.Display()
        d.close()
        _logger.info("Using X11Backend for hotkeys")
        return X11Backend(app)
    except Exception as exc:
        _logger.warning("X11Backend failed/not-available: %s", exc)

    try:
        import keyboard

        keyboard.add_hotkey("ctrl+alt+shift+h", lambda: None, suppress=True)
        keyboard.remove_hotkey("ctrl+alt+shift+h")
        _logger.info("Using KeyboardBackend for hotkeys")
        return KeyboardBackend(app)
    except Exception as exc:
        _logger.error("KeyboardBackend failed: %s", exc)
        if hasattr(app, "dispatcher") and hasattr(app, "notifier"):
            msg = "快捷键屏蔽注册失败，将回退到无屏蔽监听。Wayland/X11 环境可能需要额外权限或不同后端。"
            app.dispatcher.call_soon(lambda: app.notifier.show("快捷键屏蔽警告", msg))

    _logger.info("Using PynputBackend for hotkeys")
    return PynputBackend(app)
