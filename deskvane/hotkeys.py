from __future__ import annotations

import os
import threading
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

from .log import get_logger

_logger = get_logger("hotkeys")

if TYPE_CHECKING:
    from .app import DeskVaneApp


class IHotkeyBackend(ABC):
    @abstractmethod
    def start(self) -> None: pass
    
    @abstractmethod
    def stop(self) -> None: pass

    @abstractmethod
    def register(self, hotkey: str, callback: Callable) -> None: pass
    
    @abstractmethod
    def clear(self) -> None: pass


class PynputBackend(IHotkeyBackend):
    """Fallback backend using pure pynput (no key suppression)."""
    def __init__(self, app: DeskVaneApp) -> None:
        self.app = app
        self._listener = None
        self._bindings: dict[str, Callable] = {}

    def register(self, hotkey: str, callback: Callable) -> None:
        self._bindings[hotkey] = callback

    def start(self) -> None:
        if not self._bindings: return
        try:
            from pynput.keyboard import Listener, HotKey
        except ImportError:
            return

        def _make_dispatcher(fn: Callable):
            def _dispatch():
                self.app.dispatcher.call_soon(fn)
            return _dispatch

        parsed_bindings = []
        for k, v in self._bindings.items():
            keys = set(HotKey.parse(k))
            parsed_bindings.append((keys, _make_dispatcher(v)))
            
        parsed_bindings.sort(key=lambda x: len(x[0]), reverse=True)

        current_keys = set()
        
        def on_press(key):
            key = self._listener.canonical(key)
            current_keys.add(key)
            for keys, cb in parsed_bindings:
                if keys.issubset(current_keys):
                    cb()
                    current_keys.clear()
                    break

        def on_release(key):
            key = self._listener.canonical(key)
            try:
                current_keys.remove(key)
            except KeyError:
                pass

        self._listener = Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def clear(self) -> None:
        self._bindings.clear()


class KeyboardBackend(IHotkeyBackend):
    """Plan A backend using 'keyboard' module with native suppress=True, needs root on Linux."""
    def __init__(self, app: DeskVaneApp) -> None:
        import keyboard
        self.keyboard = keyboard
        self.app = app
        self._bindings: dict[str, Callable] = {}

    def _convert_hotkey(self, h: str) -> str:
        return h.replace("<", "").replace(">", "")

    def register(self, hotkey: str, callback: Callable) -> None:
        self._bindings[hotkey] = callback

    def start(self) -> None:
        for k, cb in self._bindings.items():
            parsed_hk = self._convert_hotkey(k)
            def _make_cb(fn=cb):
                return lambda: self.app.dispatcher.call_soon(fn)
            try:
                self.keyboard.add_hotkey(parsed_hk, _make_cb(), suppress=True)
                _logger.info("Grabbed hotkey (keyboard): %s", parsed_hk)
            except Exception as e:
                _logger.error("Failed to grab hotkey %s via keyboard: %s", parsed_hk, e)

    def stop(self) -> None:
        try:
            self.keyboard.unhook_all()
        except Exception:
            pass
            
    def clear(self) -> None:
        self._bindings.clear()


class X11Backend(IHotkeyBackend):
    """Plan B backend using XGrabKey natively (does not require root)."""
    def __init__(self, app: DeskVaneApp) -> None:
        from Xlib import display, X, XK
        self.X = X
        self.XK = XK
        self.display_module = display
        
        self.d = display.Display()
        self.root = self.d.screen().root

        self.app = app
        self._bindings: dict[str, Callable] = {}
        self._running = False
        self._thread = None
        self.grabbed_keys = {}

    def _parse_hotkey(self, hk: str):
        from pynput.keyboard import HotKey, Key, KeyCode
        keys = set(HotKey.parse(hk))
        modifiers = 0
        keycode = None
        
        for k in keys:
            if k == Key.ctrl or k == Key.ctrl_l or k == Key.ctrl_r:
                modifiers |= self.X.ControlMask
            elif k == Key.alt or k == Key.alt_l or k == Key.alt_r:
                modifiers |= self.X.Mod1Mask
            elif k == Key.shift or k == Key.shift_l or k == Key.shift_r:
                modifiers |= self.X.ShiftMask
            elif k == Key.cmd or k == Key.cmd_l or k == Key.cmd_r:
                modifiers |= self.X.Mod4Mask
            elif isinstance(k, KeyCode):
                if hasattr(k, "char") and k.char:
                    keysym = self.XK.string_to_keysym(k.char)
                    keycode = self.d.keysym_to_keycode(keysym)
                elif hasattr(k, "vk"):
                    keycode = self.d.keysym_to_keycode(k.vk)
            elif isinstance(k, Key):
                keysym_str = k.name.capitalize() if k.name.startswith('f') and k.name[1:].isdigit() else k.name
                keysym = self.XK.string_to_keysym(keysym_str)
                if keysym == self.X.NoSymbol and hasattr(k.value, "vk"):
                    keycode = self.d.keysym_to_keycode(k.value.vk)
                else:
                    keycode = self.d.keysym_to_keycode(keysym)
        return keycode, modifiers

    def register(self, hotkey: str, callback: Callable) -> None:
        self._bindings[hotkey] = callback

    def start(self) -> None:
        self.d = self.display_module.Display()
        self.root = self.d.screen().root
        
        self.grabbed_keys.clear()
        for hotkey, cb in self._bindings.items():
            try:
                keycode, modifiers = self._parse_hotkey(hotkey)
                if keycode:
                    for extra_mod in [0, self.X.Mod2Mask, self.X.LockMask, self.X.Mod2Mask | self.X.LockMask]:
                        self.root.grab_key(keycode, modifiers | extra_mod, True, self.X.GrabModeAsync, self.X.GrabModeAsync)
                    self.grabbed_keys[(keycode, modifiers)] = cb
                    _logger.info("Grabbed X11 key: %s (keycode=%s, modifiers=%s)", hotkey, keycode, modifiers)
            except Exception as e:
                _logger.error("Failed to grab X11 hotkey %s: %s", hotkey, e)

        self._running = True
        self._thread = threading.Thread(target=self._event_loop, daemon=True)
        self._thread.start()

    def _event_loop(self):
        while self._running:
            while self.d.pending_events():
                e = self.d.next_event()
                if e.type == self.X.KeyPress:
                    keycode = e.detail
                    modifiers = e.state & ~(self.X.LockMask | self.X.Mod2Mask | self.X.Mod5Mask)
                    cb = self.grabbed_keys.get((keycode, modifiers))
                    if cb:
                        self.app.dispatcher.call_soon(cb)
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
        except:
            pass

    def clear(self) -> None:
        self._bindings.clear()


class HotkeyManager:
    """Global hotkey listener switching between backends automatically."""

    def __init__(self, app: DeskVaneApp) -> None:
        self.app = app
        self._backend: IHotkeyBackend | None = None
        self._bindings: dict[str, Callable] = {}

    def _init_backend(self) -> None:
        # Avoid double initialization
        if self._backend is not None:
            return

        # 1. Try X11 native (Plan B)
        # Avoid X11 logic if explicitly not desired or failing
        try:
            from Xlib import display
            # test open output
            d = display.Display()
            d.close()
            self._backend = X11Backend(self.app)
            _logger.info("Using X11Backend for hotkeys (Plan B)")
            return
        except Exception as e:
            _logger.warning("X11Backend failed/not-available: %s", e)

        # 2. Try keyboard (Plan A)
        try:
            import keyboard
            keyboard.add_hotkey('ctrl+alt+shift+h', lambda: None, suppress=True)
            keyboard.remove_hotkey('ctrl+alt+shift+h')
            self._backend = KeyboardBackend(self.app)
            _logger.info("Using KeyboardBackend for hotkeys (Plan A)")
            return
        except Exception as e:
            _logger.error("KeyboardBackend failed (needs root?): %s", e)
            msg = "快捷键屏蔽注册失败。\n如果是在 Wayland 或无 X11 下，使用底层硬件捕获需要以管理员(sudo)运行 deskvane，或配置正确的 udev 读写权限。\n本次将回退到无屏蔽的默认监听。"
            self.app.dispatcher.call_soon(lambda: self.app.notifier.show("快捷键屏蔽警告", msg))

        # 3. Fallback Pynput (Plan C)
        self._backend = PynputBackend(self.app)
        _logger.info("Using PynputBackend for hotkeys (Fallback)")

    def register(self, hotkey: str, callback: Callable) -> None:
        self._bindings[hotkey] = callback
        if self._backend is not None:
            self._backend.register(hotkey, callback)

    def start(self) -> None:
        self._init_backend()
        self._backend.clear()
        for k, v in self._bindings.items():
            self._backend.register(k, v)
        self._backend.start()

    def stop(self) -> None:
        if self._backend is not None:
            self._backend.stop()

    def clear(self) -> None:
        self._bindings.clear()
        if self._backend is not None:
            self._backend.clear()

    def restart(self) -> None:
        self.stop()
        self.start()
