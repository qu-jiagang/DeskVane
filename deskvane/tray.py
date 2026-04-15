from __future__ import annotations

from io import BytesIO
import os
import threading
import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from .log import get_logger
from .mihomo.api import DEFAULT_DELAY_TEST_URL, MihomoRuntimeState

if TYPE_CHECKING:
    from .app import DeskVaneApp

_logger = get_logger("tray")


class TrayController:
    """System tray icon and menu for DeskVane."""

    _SEGMENT_MAP = {
        "0": ("a", "b", "c", "d", "e", "f"),
        "1": ("b", "c"),
        "2": ("a", "b", "d", "e", "g"),
        "3": ("a", "b", "c", "d", "g"),
        "4": ("b", "c", "f", "g"),
        "5": ("a", "c", "d", "f", "g"),
        "6": ("a", "c", "d", "e", "f", "g"),
        "7": ("a", "b", "c"),
        "8": ("a", "b", "c", "d", "e", "f", "g"),
        "9": ("a", "b", "c", "d", "f", "g"),
        "-": ("g",),
        " ": (),
    }

    def __init__(self, app: DeskVaneApp) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError as exc:
            raise RuntimeError(
                "缺少 pystray 或 Pillow。请执行 `pip install -e .`。"
            ) from exc
        self.app = app
        self.pystray = pystray
        self.Image = Image
        self.ImageDraw = ImageDraw
        self._status_refresh_interval_seconds = 2.0
        self._refresh_lock = threading.Lock()
        self._menu_open = False
        self._last_icon_payload: bytes | None = None
        self._last_label_payload: tuple[str, str] | None = None
        self._pending_label_payload: tuple[str, str] | None = None
        self._observed_menu_handle = None
        self._appindicator_label_setter = self._build_label_setter()
        self._mihomo_manual_delay_results: dict[str, int] = {}
        self._mihomo_delay_test_running = False
        cpu, gpu = self._get_status_snapshot()
        initial_icon = self._build_icon(cpu=cpu, gpu=gpu)
        self._last_icon_payload = self._icon_to_png_bytes(initial_icon)
        self.icon = pystray.Icon(
            "deskvane",
            initial_icon,
            "DeskVane",
            self._build_menu(cpu=cpu, gpu=gpu),
        )
        self._last_label_payload = self._build_label(cpu=cpu, gpu=gpu)
        self.supports_menu = bool(getattr(self.icon, "HAS_MENU", True))
        self._thread: threading.Thread | None = None
        self._refresh_thread: threading.Thread | None = None

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()
        # Auto-refresh only tray visuals. Menus are never rebuilt in background.
        self._refresh_timer_running = True
        self._refresh_thread = threading.Thread(target=self._auto_refresh, daemon=True)
        self._refresh_thread.start()

    def stop(self) -> None:
        self._refresh_timer_running = False
        self.icon.stop()

    def refresh(self) -> None:
        self._refresh_display(force_icon=True)

    def rebuild_menu(self) -> None:
        self._refresh_display(force_menu=True)

    def _auto_refresh(self) -> None:
        """Periodically refresh tray visuals without rebuilding menus."""
        while getattr(self, "_refresh_timer_running", False):
            time.sleep(self._status_refresh_interval_seconds)
            try:
                self._refresh_display()
            except Exception as exc:
                _logger.debug("tray auto refresh failed: %s", exc)

    @staticmethod
    def _noop(icon=None, item=None) -> None:
        return

    def _get_status_snapshot(self):
        from .sysmon import get_cpu_status, get_gpu_status

        return get_cpu_status(), get_gpu_status()

    def _build_label_setter(self):
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            from gi.repository import GObject, Gtk
        except Exception:
            return None

        def setter(indicator, label: str, guide: str) -> None:
            def callback():
                try:
                    indicator.set_label(label, guide)
                except Exception as exc:
                    _logger.debug("tray label refresh failed: %s", exc)
                return False

            GObject.idle_add(callback)

        self._gtk_menu_type = Gtk.Menu
        return setter

    def _refresh_display(self, force_menu: bool = False, force_icon: bool = False) -> None:
        cpu, gpu = self._get_status_snapshot()
        with self._refresh_lock:
            self._bind_menu_observers()
            self._maybe_refresh_menu(cpu=cpu, gpu=gpu, force=force_menu)
            self._maybe_refresh_icon(cpu=cpu, gpu=gpu, force=force_icon)
            self._maybe_refresh_label(cpu=cpu, gpu=gpu)

    def _maybe_refresh_menu(self, cpu=None, gpu=None, force: bool = False) -> None:
        if not force:
            return
        if self._menu_open:
            return

        try:
            self.icon.menu = self._build_menu(cpu=cpu, gpu=gpu)
            self.icon.update_menu()
            self._bind_menu_observers()
        except Exception as exc:
            _logger.debug("tray menu refresh failed: %s", exc)

    def _maybe_refresh_icon(self, cpu=None, gpu=None, force: bool = False) -> None:
        mode = getattr(self.app.config.general, "tray_display", "default")
        if not force and getattr(self.icon, "_appindicator", None) is not None and mode != "default":
            return

        image = self._build_icon(cpu=cpu, gpu=gpu)
        payload = self._icon_to_png_bytes(image)
        if not force and payload == self._last_icon_payload:
            return
        if not force and self._menu_open:
            return

        try:
            self.icon.icon = image
            self._last_icon_payload = payload
        except Exception as exc:
            _logger.debug("tray icon refresh failed: %s", exc)

    def _maybe_refresh_label(self, cpu=None, gpu=None) -> None:
        indicator = getattr(self.icon, "_appindicator", None)
        if indicator is None or self._appindicator_label_setter is None:
            return

        label, guide = self._build_label(cpu=cpu, gpu=gpu)
        if (label, guide) == self._last_label_payload:
            return
        if self._menu_open:
            self._pending_label_payload = (label, guide)
            return
        self._appindicator_label_setter(indicator, label, guide)
        self._last_label_payload = (label, guide)
        self._pending_label_payload = None

    @staticmethod
    def _build_system_status_payload(cpu=None, gpu=None) -> tuple:
        cpu_payload = None
        gpu_payload = None
        if cpu:
            cpu_payload = (round(cpu.usage_pct), round(cpu.temp_c) if cpu.temp_c is not None else None)
        if gpu:
            gpu_payload = (
                round(gpu.usage_pct),
                round(gpu.temp_c),
                gpu.mem_used_mb,
                gpu.mem_total_mb,
            )
        return cpu_payload, gpu_payload

    @staticmethod
    def _icon_to_png_bytes(image) -> bytes:
        buf = BytesIO()
        image.save(buf, "PNG")
        return buf.getvalue()

    def _bind_menu_observers(self) -> None:
        menu_handle = getattr(self.icon, "_menu_handle", None)
        gtk_menu_type = getattr(self, "_gtk_menu_type", None)
        if menu_handle is None or gtk_menu_type is None:
            return
        if menu_handle is self._observed_menu_handle:
            return
        if not isinstance(menu_handle, gtk_menu_type):
            return

        def on_show(*_args) -> None:
            self._menu_open = True

        def on_hide(*_args) -> None:
            self._menu_open = False
            self._flush_pending_label()

        for signal_name, handler in (
            ("show", on_show),
            ("hide", on_hide),
            ("selection-done", on_hide),
            ("deactivate", on_hide),
        ):
            try:
                menu_handle.connect(signal_name, handler)
            except Exception:
                continue
        self._observed_menu_handle = menu_handle

    def _flush_pending_label(self) -> None:
        indicator = getattr(self.icon, "_appindicator", None)
        if indicator is None or self._appindicator_label_setter is None:
            return
        if not self._pending_label_payload:
            return
        label, guide = self._pending_label_payload
        if (label, guide) == self._last_label_payload:
            self._pending_label_payload = None
            return
        self._appindicator_label_setter(indicator, label, guide)
        self._last_label_payload = (label, guide)
        self._pending_label_payload = None

    def _build_label(self, cpu=None, gpu=None) -> tuple[str, str]:
        mode = getattr(self.app.config.general, "tray_display", "default")
        if mode == "default":
            return "", ""

        if mode == "cpu_usage" and cpu:
            return f"{round(cpu.usage_pct)}%", "100%"
        if mode == "cpu_temp" and cpu and cpu.temp_c is not None:
            return f"{round(cpu.temp_c)}°", "100°"
        if mode == "gpu_usage" and gpu:
            return f"{round(gpu.usage_pct)}%", "100%"
        if mode == "gpu_temp" and gpu:
            return f"{round(gpu.temp_c)}°", "100°"
        if mode == "gpu_mem" and gpu and gpu.mem_total_mb > 0:
            mem_pct = round(gpu.mem_used_mb / gpu.mem_total_mb * 100)
            return f"{mem_pct}%", "100%"

        return "--", "100%"

    @staticmethod
    def _empty_mihomo_runtime(controller: str) -> MihomoRuntimeState:
        return MihomoRuntimeState(
            api_ready=False,
            controller=controller,
            mode="",
            mixed_port=None,
            port=None,
            socks_port=None,
            tun_enabled=False,
            groups=[],
        )

    def _get_mihomo_snapshot(self, use_cache: bool = True) -> dict:
        now = time.monotonic()
        cached = getattr(self, "_mihomo_snapshot_cache", None)
        cache_at = getattr(self, "_mihomo_snapshot_at", 0.0)
        if use_cache and cached is not None and (now - cache_at) < 0.4:
            return cached

        mihomo = self.app.mihomo_manager
        core_status = mihomo.get_core_status()
        runtime = self._empty_mihomo_runtime(core_status.controller)
        if mihomo.backend == "core" and core_status.api_ready:
            try:
                runtime = mihomo.get_runtime_state()
            except Exception as exc:
                _logger.debug("read mihomo runtime failed: %s", exc)

        running = core_status.running if mihomo.backend == "core" else mihomo.is_running()

        snapshot = {
            "installed": mihomo.is_installed(),
            "running": running,
            "backend": mihomo.backend,
            "title": mihomo.display_name,
            "core_status": core_status,
            "runtime": runtime,
            "has_external_ui": bool(
                self.app.config.mihomo.external_ui.strip()
                or self.app.config.mihomo.external_ui_name.strip()
                or self.app.config.mihomo.external_ui_url.strip()
            ),
        }
        self._mihomo_snapshot_cache = snapshot
        self._mihomo_snapshot_at = now
        return snapshot

    @staticmethod
    def _format_mihomo_mode(mode: str) -> str:
        mapping = {
            "rule": "Rule",
            "global": "Global",
            "direct": "Direct",
        }
        return mapping.get(mode, mode or "-")

    @staticmethod
    def _truncate_text(text: str, limit: int = 72) -> str:
        text = " ".join(text.split())
        if len(text) <= limit:
            return text
        return f"{text[:limit - 1]}…"

    def _build_mihomo_root_label(self) -> str:
        snapshot = self._get_mihomo_snapshot()
        title = snapshot["title"]
        if not snapshot["installed"]:
            return f"{title} · 未安装"
        if snapshot["backend"] == "party":
            return f"{title} · {'运行中' if snapshot['running'] else '已停止'}"
        if not snapshot["running"]:
            return f"{title} · 已停止"
        if not snapshot["core_status"].api_ready:
            return f"{title} · 启动中"
        runtime = snapshot["runtime"]
        tun_tag = " · TUN" if runtime.tun_enabled else ""
        pac_tag = " · PAC" if getattr(self.app.config.mihomo, "pac_enabled", False) else ""
        return f"{title} · {self._format_mihomo_mode(runtime.mode)}{tun_tag}{pac_tag}"

    def _build_mihomo_status_line(self) -> str:
        snapshot = self._get_mihomo_snapshot()
        title = snapshot["title"]
        if not snapshot["installed"]:
            return f"状态: {title} 未安装"
        if snapshot["backend"] == "party":
            return f"状态: {'运行中' if snapshot['running'] else '已停止'}"

        status = snapshot["core_status"]
        runtime = snapshot["runtime"]
        if status.api_ready:
            port = runtime.mixed_port or runtime.port or "-"
            return f"端口: {port} | {len(runtime.groups)} 个代理组"
        if snapshot["running"]:
            return "等待 API 就绪…"
        return "已停止"

    def _build_mihomo_error_line(self) -> str:
        snapshot = self._get_mihomo_snapshot()
        status = snapshot["core_status"]
        errors = [msg for msg in (status.last_error, status.config_error) if msg]
        if not errors:
            return ""
        return f"错误: {self._truncate_text(' | '.join(errors), 32)}"

    def _mihomo_api_ready(self) -> bool:
        return bool(self._get_mihomo_snapshot()["core_status"].api_ready)

    def _mihomo_current_mode(self) -> str:
        return str(self._get_mihomo_snapshot()["runtime"].mode)

    def _mihomo_tun_enabled(self) -> bool:
        return bool(self._get_mihomo_snapshot()["runtime"].tun_enabled)

    def _build_mihomo_open_label(self) -> str:
        snapshot = self._get_mihomo_snapshot()
        if snapshot["backend"] != "core":
            return "打开控制台"
        return "打开 Web UI" if snapshot["has_external_ui"] else "打开 API 地址"

    def _mihomo_has_saved_subscription(self) -> bool:
        return bool(self._saved_subscription_urls())

    @staticmethod
    def _mihomo_group_map(runtime: MihomoRuntimeState) -> dict[str, object]:
        return {group.name: group for group in runtime.groups}

    @staticmethod
    def _mihomo_active_group_name(runtime: MihomoRuntimeState) -> str:
        available = {group.name for group in runtime.groups}
        mode = str(runtime.mode).strip().lower()
        if mode == "global":
            return "GLOBAL" if "GLOBAL" in available else ""
        if mode == "rule":
            if "PROXY" in available:
                return "PROXY"
            if "DESKVANE-PROXY" in available:
                return "DESKVANE-PROXY"
            return ""
        if mode == "direct":
            return "Direct" if "Direct" in available else ""
        return ""

    @staticmethod
    def _mihomo_primary_group(runtime: MihomoRuntimeState):
        if not runtime.groups:
            return None
        group_map = TrayController._mihomo_group_map(runtime)
        preferred = []
        active = TrayController._mihomo_active_group_name(runtime)
        if active:
            preferred.append(active)
        preferred.extend(["PROXY", "DESKVANE-PROXY", "GLOBAL", "Auto", "Direct"])
        for name in preferred:
            group = group_map.get(name)
            if group is not None:
                return group
        return runtime.groups[0]

    @staticmethod
    def _mihomo_visible_nodes(group, runtime: MihomoRuntimeState) -> list[str]:
        group_names = {item.name for item in runtime.groups}
        visible: list[str] = []
        for candidate in group.candidates:
            normalized = str(candidate).strip()
            if not normalized:
                continue
            if normalized in group_names:
                continue
            if normalized.upper() in {"DIRECT", "REJECT"}:
                continue
            visible.append(normalized)
        return visible

    @staticmethod
    def _mihomo_leaf_node_name(group, runtime: MihomoRuntimeState) -> str:
        group_map = TrayController._mihomo_group_map(runtime)
        current = str(group.current).strip()
        seen: set[str] = set()
        while current and current in group_map and current not in seen:
            seen.add(current)
            current = str(group_map[current].current).strip()
        return current or str(group.current).strip()

    @staticmethod
    def _compact_node_labels(nodes: list[str]) -> dict[str, str]:
        host_labels: dict[str, str] = {}
        for node in nodes:
            host_token = TrayController._node_host_token(node)
            if not host_token:
                host_labels = {}
                break
            host_labels[node] = host_token
        if host_labels and len(set(host_labels.values())) == len(nodes):
            return host_labels

        if not nodes:
            return {}

        prefix = os.path.commonprefix(nodes)
        reversed_nodes = [node[::-1] for node in nodes]
        suffix = os.path.commonprefix(reversed_nodes)[::-1]
        if len(prefix) + len(suffix) >= min(len(node) for node in nodes):
            suffix = ""

        labels: dict[str, str] = {}
        used: set[str] = set()
        for node in nodes:
            core = node[len(prefix):] if prefix else node
            if suffix and core.endswith(suffix):
                core = core[:-len(suffix)]
            compact = core.strip(" -_@.:/|") or node
            if compact in used:
                compact = TrayController._truncate_text(node, 40)
            used.add(compact)
            labels[node] = compact
        return labels

    @staticmethod
    def _node_host_token(node: str) -> str:
        if "@" not in node:
            return ""
        host = node.rsplit("@", 1)[-1].strip()
        if not host:
            return ""
        for sep in ("/", ":", "."):
            if sep in host:
                host = host.split(sep, 1)[0]
        return host.strip()

    def _mihomo_delay_ms_for_node(self, node: str, runtime: MihomoRuntimeState) -> int | None:
        cached = self._mihomo_manual_delay_results.get(node)
        if cached is not None and cached > 0:
            return cached
        for group in runtime.groups:
            delay = group.candidate_delays.get(node)
            if delay is not None and delay > 0:
                return delay
        return None

    def _build_mihomo_node_menu_label(
        self,
        node: str,
        compact_labels: dict[str, str],
        runtime: MihomoRuntimeState,
    ) -> str:
        label = compact_labels.get(node, node)
        delay = self._mihomo_delay_ms_for_node(node, runtime)
        if delay is None:
            return label
        return f"{label} · {delay}ms"

    def _start_mihomo_node_delay_test(self) -> None:
        if self._mihomo_delay_test_running:
            return
        snapshot = self._get_mihomo_snapshot(use_cache=False)
        runtime = snapshot["runtime"]
        if not snapshot["core_status"].api_ready:
            return
        group = self._mihomo_primary_group(runtime)
        if group is None:
            return
        nodes = self._mihomo_visible_nodes(group, runtime)
        if not nodes:
            return
        test_url = group.test_url.strip() or DEFAULT_DELAY_TEST_URL
        self._mihomo_delay_test_running = True
        self.rebuild_menu()

        def worker() -> None:
            results: dict[str, int] = {}
            for node in nodes:
                try:
                    delay = self.app.mihomo_test_proxy_delay(node, test_url)
                except Exception:
                    delay = None
                if delay is not None:
                    results[node] = delay
            self.app.dispatcher.call_soon(
                self._finish_mihomo_node_delay_test,
                results,
                len(nodes),
                test_url,
            )

        threading.Thread(target=worker, daemon=True).start()

    def _finish_mihomo_node_delay_test(
        self,
        results: dict[str, int],
        total: int,
        test_url: str,
    ) -> None:
        self._mihomo_delay_test_running = False
        self._mihomo_manual_delay_results.update(results)
        self._mihomo_snapshot_cache = None
        self._mihomo_snapshot_at = 0.0
        self.rebuild_menu()
        if getattr(self.app.config.general, "notifications_enabled", True):
            ok = len(results)
            body = f"{ok}/{total} 个节点完成测速"
            if test_url:
                host = urlparse(test_url).netloc or test_url
                body = f"{body} · {host}"
            title = "Mihomo 节点延迟测试完成" if ok else "Mihomo 节点延迟测试失败"
            self.app.notifier.show(title, body)

    def _saved_subscription_urls(self) -> list[str]:
        current = str(getattr(self.app.config.mihomo, "subscription_url", "")).strip()
        saved = getattr(self.app.config.mihomo, "saved_subscriptions", []) or []
        urls: list[str] = []
        seen: set[str] = set()
        for raw in [current, *saved]:
            normalized = str(raw).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            urls.append(normalized)
        return urls

    @staticmethod
    def _subscription_menu_label(url: str) -> str:
        normalized = url.strip()
        if not normalized:
            return "未命名订阅"
        try:
            parsed = urlparse(normalized)
        except Exception:
            return TrayController._truncate_text(normalized, 36)
        host = parsed.netloc or "本地订阅"
        query = parse_qs(parsed.query)
        service = (query.get("service") or [""])[0].strip()
        sub_id = (query.get("id") or [""])[0].strip()
        if service:
            return f"{host} · {service}"
        if sub_id:
            return f"{host} · …{sub_id[-6:]}"
        tail = parsed.path.rstrip("/").rsplit("/", 1)[-1].strip()
        if tail and tail not in {"", "getsub.php"}:
            return f"{host} · {TrayController._truncate_text(tail, 14)}"
        return host

    def _translator_status_line(self) -> str:
        return f"状态: {'已暂停' if self.app.translator.paused else '运行中'}"

    def _clipboard_history_enabled(self) -> bool:
        return bool(getattr(self.app.config.general, "clipboard_history_enabled", True))

    def _build_tools_menu_items(self):
        item = self.pystray.MenuItem
        menu = self.pystray.Menu
        return menu(
            item("截图并钉住", self._dispatch("do_screenshot_and_pin"), default=True),
            item("纯 OCR", self._dispatch("do_pure_ocr")),
            item(
                "剪贴板历史",
                self._dispatch("show_clipboard_history"),
                enabled=lambda _item: self._clipboard_history_enabled(),
            ),
            item("订阅转换…", self._dispatch("show_subconverter")),
        )

    def _build_mihomo_menu_items(self):
        item = self.pystray.MenuItem
        menu = self.pystray.Menu
        snapshot = self._get_mihomo_snapshot(use_cache=False)
        title = snapshot["title"]
        backend = snapshot["backend"]
        installed = snapshot["installed"]
        running = snapshot["running"]

        items = []
        if not installed:
            items.append(item(f"{title} 未安装", self._noop, enabled=False))
            return tuple(items)
        else:
            items.append(
                item(
                    "停止" if running else "启动",
                    self._dispatch("toggle_mihomo"),
                )
            )
        items.append(item(lambda _: self._build_mihomo_status_line(), self._noop, enabled=False))

        error_line = self._build_mihomo_error_line()
        if error_line:
            items.append(item(lambda _: self._build_mihomo_error_line(), self._noop, enabled=False))

        if backend == "core":
            mode_sub = menu(
                item(
                    "Rule",
                    self._dispatch_call(self.app.mihomo_set_mode, "rule"),
                    radio=True,
                    checked=lambda _item: self._mihomo_current_mode() == "rule",
                    enabled=lambda _item: self._mihomo_api_ready(),
                ),
                item(
                    "Global",
                    self._dispatch_call(self.app.mihomo_set_mode, "global"),
                    radio=True,
                    checked=lambda _item: self._mihomo_current_mode() == "global",
                    enabled=lambda _item: self._mihomo_api_ready(),
                ),
                item(
                    "Direct",
                    self._dispatch_call(self.app.mihomo_set_mode, "direct"),
                    radio=True,
                    checked=lambda _item: self._mihomo_current_mode() == "direct",
                    enabled=lambda _item: self._mihomo_api_ready(),
                ),
            )
            advanced_sub = menu(
                item("重载配置", self._dispatch("mihomo_reload_core_config")),
                item(
                    lambda _item: self._build_mihomo_open_label(),
                    self._dispatch("open_mihomo_controller"),
                    enabled=lambda _item: self._mihomo_api_ready(),
                ),
                item("打开配置", self._dispatch("open_mihomo_core_config")),
                item("打开日志", self._dispatch("open_mihomo_logs")),
            )
            subscription_urls = self._saved_subscription_urls()
            if subscription_urls:
                subscription_switch_sub = menu(
                    *[
                        item(
                            lambda _item, url=url: self._subscription_menu_label(url),
                            self._dispatch_call(self.app.mihomo_switch_subscription, url),
                            radio=True,
                            checked=lambda _item, url=url: str(self.app.config.mihomo.subscription_url).strip() == url,
                        )
                        for url in subscription_urls
                    ]
                )
            else:
                subscription_switch_sub = menu(
                    item("暂无已保存订阅", self._noop, enabled=False),
                )
            quick_group = self._mihomo_primary_group(snapshot["runtime"])
            quick_group_name = quick_group.name if quick_group is not None else ""
            quick_nodes = (
                self._mihomo_visible_nodes(quick_group, snapshot["runtime"])
                if quick_group is not None
                else []
            )
            current_node = (
                self._mihomo_leaf_node_name(quick_group, snapshot["runtime"])
                if quick_group is not None
                else ""
            )
            compact_node_labels = self._compact_node_labels(quick_nodes)
            if quick_group is not None and quick_nodes:
                node_switch_sub = menu(
                    item(
                        lambda _item, group_name=quick_group_name: f"当前组: {group_name}",
                        self._noop,
                        enabled=False,
                    ),
                    self.pystray.Menu.SEPARATOR,
                    item(
                        "测试节点延迟（进行中）" if self._mihomo_delay_test_running else "测试节点延迟",
                        self._dispatch_call(self._start_mihomo_node_delay_test),
                        enabled=lambda _item: self._mihomo_api_ready() and not self._mihomo_delay_test_running,
                    ),
                    self.pystray.Menu.SEPARATOR,
                    *[
                        item(
                            self._build_mihomo_node_menu_label(
                                node,
                                compact_node_labels,
                                snapshot["runtime"],
                            ),
                            self._dispatch_call(self.app.mihomo_switch_proxy, quick_group_name, node),
                            radio=True,
                            checked=lambda _item, node=node: current_node == node,
                            enabled=lambda _item: self._mihomo_api_ready(),
                        )
                        for node in quick_nodes
                    ],
                )
            else:
                node_switch_sub = menu(
                    item("当前模式下没有可切换节点", self._noop, enabled=False),
                )

            items.append(
                item(
                    "模式",
                    mode_sub,
                    enabled=lambda _item: self._mihomo_api_ready(),
                )
            )
            items.append(
                item(
                    "TUN 模式",
                    self._dispatch("mihomo_toggle_tun"),
                    checked=lambda _item: self._mihomo_tun_enabled(),
                    enabled=lambda _item: self._mihomo_api_ready(),
                )
            )
            items.append(
                item(
                    "PAC 模式",
                    self._dispatch("mihomo_toggle_pac"),
                    checked=lambda _item: bool(self.app.config.mihomo.pac_enabled),
                    enabled=lambda _item: self._mihomo_api_ready(),
                )
            )
            items.append(
                item(
                    "复制 PAC 地址",
                    self._dispatch("mihomo_copy_pac_url"),
                    enabled=lambda _item: bool(self.app.config.mihomo.pac_enabled),
                )
            )
            items.append(self.pystray.Menu.SEPARATOR)
            items.append(item("打开面板…", self._dispatch("show_mihomo_window")))
            items.append(
                item(
                    "节点快切",
                    node_switch_sub,
                    enabled=lambda _item: self._mihomo_api_ready(),
                )
            )
            items.append(
                item(
                    "订阅",
                    menu(
                        item(
                            "更新当前订阅",
                            self._dispatch("mihomo_update_subscription"),
                            enabled=lambda _item: self._mihomo_has_saved_subscription(),
                        ),
                        item(
                            "快速切换",
                            subscription_switch_sub,
                            enabled=lambda _item: self._mihomo_has_saved_subscription(),
                        ),
                    ),
                )
            )
            items.append(item("高级与诊断", advanced_sub))
        elif running:
            items.append(item("打开控制台", self._dispatch("show_mihomo_window")))
        return tuple(items)

    # ---------------------------------------------------------------
    # Menu
    # ---------------------------------------------------------------

    def _dispatch(self, fn_name: str):
        def callback(icon, item) -> None:
            self.app.dispatcher.call_soon(getattr(self.app, fn_name))
        return callback

    def _dispatch_call(self, fn, *args):
        def callback(icon, item) -> None:
            self.app.dispatcher.call_soon(fn, *args)
        return callback

    def _build_menu(self, cpu=None, gpu=None):
        item = self.pystray.MenuItem
        menu = self.pystray.Menu
        t = self.app.translator

        # --- Proxy control submenu ---
        proxy_sub = menu(
            item(
                "终端代理",
                self._dispatch("toggle_terminal_proxy"),
                checked=lambda _: self.app.is_terminal_proxy_enabled,
            ),
            item(
                "Git 代理",
                self._dispatch("toggle_git_proxy"),
                checked=lambda _: self.app.is_git_proxy_enabled,
            ),
        )

        # --- Translator submenu ---
        translator_sub = menu(
            item(
                lambda _: self._translator_status_line(),
                self._noop,
                enabled=False,
            ),
            item(
                "复制最近译文",
                self._dispatch("translator_copy_last"),
                default=True,
                enabled=lambda _: bool(t.last_translation),
            ),
            item(
                "恢复监控" if t.paused else "暂停监控",
                self._dispatch("translator_toggle_pause"),
            ),
        )

        # --- Mihomo submenu (core-first, Party-compatible) ---
        mihomo_sub = menu(self._build_mihomo_menu_items)
        tools_sub = self._build_tools_menu_items()

        # --- Top-level menu ---
        menu_items = [
            item("工具", tools_sub),
            item(lambda _: self._build_mihomo_root_label(), mihomo_sub),
            item("代理", proxy_sub),
            item("翻译", translator_sub),
            self.pystray.Menu.SEPARATOR,
            item("设置…", self._dispatch("show_settings")),
            item("帮助", self._dispatch("show_help")),
            self.pystray.Menu.SEPARATOR,
            item("退出", self._dispatch("quit")),
        ]

        return menu(*menu_items)

    # ---------------------------------------------------------------
    # Icon
    # ---------------------------------------------------------------

    def _build_icon(self, cpu=None, gpu=None):
        mode = getattr(self.app.config.general, "tray_display", "default")
        image = self.Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = self.ImageDraw.Draw(image)
        
        if mode == "default":
            # Brand icon: rounded square with a forward vane mark.
            draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill="#5b61f6")
            draw.rounded_rectangle((5, 5, 59, 59), radius=13, outline="#93c5fd", width=1)
            mark = [
                (19, 15),
                (26, 15),
                (45, 32),
                (26, 49),
                (19, 49),
                (19, 40),
                (33, 32),
                (19, 24),
            ]
            draw.polygon(mark, fill="white")
            return image
        
        display_value: int | None = None
        meter_pct = 0
        family_color = "#6366f1"
        value_color = "#e0e0e0"
        accent = "#6366f1"

        if mode.startswith("cpu"):
            family_color = "#a6e3a1"
            accent = "#a6e3a1"
            if cpu:
                if mode == "cpu_usage":
                    display_value = round(cpu.usage_pct)
                    meter_pct = int(max(0, min(100, cpu.usage_pct)))
                    value_color = "#a6e3a1" if cpu.usage_pct < 80 else "#f38ba8"
                elif mode == "cpu_temp":
                    accent = "#fab387"
                    family_color = "#fab387"
                    if cpu.temp_c is not None:
                        display_value = round(cpu.temp_c)
                        meter_pct = int(max(0, min(100, cpu.temp_c)))
                    value_color = "#fab387" if cpu.temp_c and cpu.temp_c > 75 else "#e0e0e0"
        elif mode.startswith("gpu"):
            family_color = "#89b4fa"
            accent = "#89b4fa"
            if gpu:
                if mode == "gpu_usage":
                    display_value = round(gpu.usage_pct)
                    meter_pct = int(max(0, min(100, gpu.usage_pct)))
                    value_color = "#89b4fa" if gpu.usage_pct < 80 else "#cba6f7"
                elif mode == "gpu_temp":
                    accent = "#fab387"
                    family_color = "#fab387"
                    display_value = round(gpu.temp_c)
                    meter_pct = int(max(0, min(100, gpu.temp_c)))
                    value_color = "#fab387" if gpu.temp_c and gpu.temp_c > 80 else "#e0e0e0"
                elif mode == "gpu_mem":
                    if gpu.mem_total_mb > 0:
                        mem_pct = gpu.mem_used_mb / gpu.mem_total_mb * 100
                        display_value = round(mem_pct)
                        meter_pct = int(max(0, min(100, mem_pct)))
                        value_color = "#89b4fa" if mem_pct < 80 else "#f38ba8"
                    else:
                        display_value = None
                        meter_pct = 0
                    family_color = "#cba6f7"
                    accent = "#cba6f7"
        
        # Visible dark background (not pure black, stands out on all tray themes)
        draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill="#2d2d3f", outline="#4a4a5e", width=1)
        # Metric family chip in the top-left corner.
        draw.rounded_rectangle((8, 8, 20, 14), radius=3, fill=family_color)
        # Colored accent bar at bottom.
        draw.rounded_rectangle((4, 50, 60, 60), radius=6, fill=accent)
        draw.rectangle((4, 50, 60, 54), fill=accent)
        # Right-hand meter makes small changes visible even when digits are tiny.
        self._draw_meter(draw, 47, 12, 55, 46, meter_pct, fill=value_color)
        # Two-digit seven-segment display is more reliable than font rendering
        # under small tray icon scaling on GNOME.
        self._draw_value_display(draw, 10, 13, display_value, fill=value_color)
        
        return image

    @staticmethod
    def _draw_centered(draw, cx: int, cy: int, text: str, fill: str, font) -> None:
        """Draw text centered at (cx, cy), compatible with all font types."""
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text((cx - tw // 2, cy - th // 2), text, fill=fill, font=font)
        except Exception:
            # Ultimate fallback
            draw.text((cx - 10, cy - 5), text, fill=fill, font=font)

    def _draw_value_display(self, draw, x: int, y: int, value: int | None, fill: str) -> None:
        if value is None:
            text = "--"
        else:
            text = f"{max(0, min(99, value)):02d}"

        off_fill = "#53586f"
        self._draw_digit(draw, x, y, text[0], fill=fill, off_fill=off_fill)
        self._draw_digit(draw, x + 18, y, text[1], fill=fill, off_fill=off_fill)

    def _draw_digit(self, draw, x: int, y: int, digit: str, fill: str, off_fill: str) -> None:
        width = 14
        height = 24
        thickness = 3
        mid = y + height // 2
        segments = {
            "a": (x + thickness, y, x + width - thickness, y + thickness),
            "d": (x + thickness, y + height - thickness, x + width - thickness, y + height),
            "g": (x + thickness, mid - 1, x + width - thickness, mid + 2),
            "f": (x, y + thickness, x + thickness, mid - 1),
            "e": (x, mid + 1, x + thickness, y + height - thickness),
            "b": (x + width - thickness, y + thickness, x + width, mid - 1),
            "c": (x + width - thickness, mid + 1, x + width, y + height - thickness),
        }
        active = set(self._SEGMENT_MAP.get(digit, self._SEGMENT_MAP["-"]))
        for name, box in segments.items():
            draw.rounded_rectangle(box, radius=1, fill=fill if name in active else off_fill)

    @staticmethod
    def _draw_meter(draw, x1: int, y1: int, x2: int, y2: int, pct: int, fill: str) -> None:
        pct = max(0, min(100, pct))
        draw.rounded_rectangle((x1, y1, x2, y2), radius=3, fill="#1f2333", outline="#4a4a5e", width=1)
        inner_top = y1 + 2
        inner_bottom = y2 - 2
        inner_left = x1 + 2
        inner_right = x2 - 2
        inner_height = max(inner_bottom - inner_top, 1)
        fill_height = max(1, round(inner_height * pct / 100)) if pct > 0 else 0
        if fill_height:
            draw.rounded_rectangle(
                (inner_left, inner_bottom - fill_height, inner_right, inner_bottom),
                radius=2,
                fill=fill,
            )
