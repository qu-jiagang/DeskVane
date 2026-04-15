import ast
import inspect
import textwrap
from types import SimpleNamespace
from unittest import mock

from deskvane.mihomo.api import DEFAULT_DELAY_TEST_URL, MihomoProxyGroup, MihomoRuntimeState
from deskvane.mihomo.panel import _MihomoPanel, open_mihomo_panel


class _FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def _group(name: str, current: str, *, test_url: str = "", last_delay_ms: int | None = None, candidate_delays=None):
    return MihomoProxyGroup(
        name=name,
        group_type="Selector",
        current=current,
        candidates=[current, "Node-B"],
        test_url=test_url,
        last_delay_ms=last_delay_ms,
        candidate_delays=candidate_delays or {},
    )


def test_prime_delay_results_prefers_runtime_snapshot_but_keeps_manual_results() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    panel._delay_results = {"Node-A": "900 ms", "Stale": "999 ms"}
    panel._manual_delay_results = {"Node-A": "120 ms"}

    panel._prime_delay_results(
        [
            _group(
                "PROXY",
                "Node-A",
                last_delay_ms=320,
                candidate_delays={"Node-A": 240, "Node-B": 260},
            )
        ]
    )

    assert panel._delay_results["PROXY"] == "320 ms"
    assert panel._delay_results["Node-A"] == "120 ms"
    assert panel._delay_results["Node-B"] == "260 ms"
    assert "Stale" not in panel._delay_results


def test_snapshot_signature_tracks_visible_core_fields() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    runtime = MihomoRuntimeState(
        api_ready=True,
        controller="http://127.0.0.1:9090",
        mode="rule",
        mixed_port=7890,
        port=None,
        socks_port=7891,
        tun_enabled=False,
        groups=[],
    )
    base_status = SimpleNamespace(
        running=True,
        api_ready=True,
        controller="http://127.0.0.1:9090",
        last_error="",
        config_exists=True,
        config_error="",
        provider_exists=True,
        stdout_log_path="/tmp/stdout.log",
        stderr_log_path="/tmp/stderr.log",
        subscription_updated_at="",
        subscription_proxy_count=0,
    )
    changed_status = SimpleNamespace(**{**base_status.__dict__, "stdout_log_path": "/tmp/other.log"})

    assert panel._snapshot_signature(base_status, runtime) != panel._snapshot_signature(changed_status, runtime)


def test_active_group_name_is_neutral_for_custom_group_layout() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    panel._runtime_mode = "rule"
    panel.groups = []

    assert panel._active_group_name([_group("CUSTOM", "Node-A")]) == ""


def test_primary_group_prefers_proxy_in_rule_mode() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    panel._runtime_mode = "rule"
    groups = [
        MihomoProxyGroup(name="Auto", group_type="URLTest", current="Node-B", candidates=["Node-A", "Node-B"]),
        MihomoProxyGroup(name="PROXY", group_type="Selector", current="Auto", candidates=["Auto", "Node-A", "Node-B"]),
        MihomoProxyGroup(name="GLOBAL", group_type="Selector", current="Node-A", candidates=["Node-A", "Node-B"]),
    ]

    assert panel._primary_group_name(groups) == "PROXY"


def test_visible_candidates_filter_out_nested_groups_and_builtins() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    groups = [
        MihomoProxyGroup(name="PROXY", group_type="Selector", current="Node-A", candidates=["Auto", "Direct", "Node-A", "Node-B"]),
        MihomoProxyGroup(name="Auto", group_type="URLTest", current="Node-B", candidates=["Node-A", "Node-B"]),
        MihomoProxyGroup(name="Direct", group_type="Selector", current="DIRECT", candidates=["DIRECT"]),
    ]

    assert panel._visible_candidates(groups[0], groups) == ["Node-A", "Node-B"]


def test_leaf_candidate_resolves_nested_auto_group() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    groups = [
        MihomoProxyGroup(name="Auto", group_type="URLTest", current="Node-B", candidates=["Node-A", "Node-B"]),
        MihomoProxyGroup(name="PROXY", group_type="Selector", current="Auto", candidates=["Auto", "Node-A", "Node-B"]),
    ]

    assert panel._leaf_candidate_name(groups[1], groups) == "Node-B"


def test_advanced_groups_exclude_primary_group() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    panel._runtime_mode = "rule"
    groups = [
        MihomoProxyGroup(name="PROXY", group_type="Selector", current="Node-A", candidates=["Node-A"]),
        MihomoProxyGroup(name="Auto", group_type="URLTest", current="Node-A", candidates=["Node-A"]),
        MihomoProxyGroup(name="Direct", group_type="Selector", current="DIRECT", candidates=["DIRECT"]),
    ]

    assert [group.name for group in panel._advanced_groups_for_display(groups)] == ["Auto", "Direct"]


def test_group_test_url_tracks_group_until_user_overrides() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    panel.delay_url_var = _FakeVar(DEFAULT_DELAY_TEST_URL)
    panel._delay_url_user_override = False
    panel._delay_url_trace_suspended = False
    panel._auto_delay_url = DEFAULT_DELAY_TEST_URL

    first = _group("PROXY", "Node-A", test_url="https://first.test")
    second = _group("PROXY", "Node-A", test_url="https://second.test")

    panel._maybe_adopt_group_test_url(first)
    assert panel.delay_url_var.get() == "https://first.test"

    panel.delay_url_var.set("https://custom.test")
    panel._on_delay_url_var_changed()
    panel._maybe_adopt_group_test_url(second)
    assert panel.delay_url_var.get() == "https://custom.test"


def test_subscription_source_label_prefers_url_host() -> None:
    assert _MihomoPanel._subscription_source_label("https://jmssub.net/members/getsub.php?id=1") == "jmssub.net"


def test_dispatch_ui_uses_app_dispatcher_when_available() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    panel.app = SimpleNamespace(dispatcher=SimpleNamespace(call_soon=mock.Mock()))
    panel.win = SimpleNamespace(after=mock.Mock())
    callback = mock.Mock()

    panel._dispatch_ui(callback, 1, "x")

    panel.app.dispatcher.call_soon.assert_called_once_with(callback, 1, "x")
    panel.win.after.assert_not_called()


def test_on_async_done_skips_closed_window() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    panel._set_busy_state = mock.Mock()
    panel._ui_alive = mock.Mock(return_value=False)
    callback = mock.Mock()

    panel._on_async_done(callback, object(), "refresh")

    panel._set_busy_state.assert_called_once_with("refresh", False)
    callback.assert_not_called()


def test_on_async_error_skips_closed_window() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    panel._set_busy_state = mock.Mock()
    panel._ui_alive = mock.Mock(return_value=False)
    panel.win = SimpleNamespace()

    with mock.patch("deskvane.mihomo.panel.messagebox.showerror") as showerror:
        panel._on_async_error(RuntimeError("boom"), "refresh")

    panel._set_busy_state.assert_called_once_with("refresh", False)
    showerror.assert_not_called()


def test_refresh_initial_applies_snapshot_synchronously() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    snapshot = object()
    panel._fetch_snapshot = mock.Mock(return_value=snapshot)
    panel._apply_snapshot = mock.Mock()
    panel.refresh = mock.Mock()

    panel._refresh_initial()

    panel._fetch_snapshot.assert_called_once_with()
    panel._apply_snapshot.assert_called_once_with(snapshot)
    panel.refresh.assert_not_called()


def test_refresh_initial_falls_back_to_async_refresh_on_error() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    panel._fetch_snapshot = mock.Mock(side_effect=RuntimeError("boom"))
    panel._apply_snapshot = mock.Mock()
    panel.refresh = mock.Mock()

    panel._refresh_initial()

    panel.refresh.assert_called_once_with()


def test_build_does_not_reference_free_app_variable() -> None:
    source = textwrap.dedent(inspect.getsource(_MihomoPanel._build))
    tree = ast.parse(source)
    free_app_loads = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "app" and isinstance(node.ctx, ast.Load)
    ]

    assert free_app_loads == []


def test_sync_from_config_updates_subscription_and_bypass_inputs() -> None:
    panel = _MihomoPanel.__new__(_MihomoPanel)
    panel.app = SimpleNamespace(
        config=SimpleNamespace(
            mihomo=SimpleNamespace(
                subscription_url="https://example.com/sub",
                tun_direct_processes="ToDesk",
                pac_enabled=False,
                pac_port=7893,
                pac_remote_url="",
                pac_proxy_domains="google.com",
                pac_direct_domains="baidu.com",
                pac_default_action="PROXY",
            )
        )
    )
    panel.manager = SimpleNamespace(
        pac_url="http://127.0.0.1:7893/pac",
        is_pac_running=lambda: False,
    )
    panel.subscription_var = _FakeVar("")
    panel.tun_bypass_var = _FakeVar("")
    panel.tun_bypass_state_var = _FakeVar("")
    panel.pac_remote_url_var = _FakeVar("")
    panel.pac_proxy_domains_var = _FakeVar("")
    panel.pac_direct_domains_var = _FakeVar("")
    panel.pac_default_action_var = _FakeVar("")
    panel.pac_port_var = _FakeVar("")
    panel.pac_url_var = _FakeVar("")
    panel.pac_state_var = _FakeVar("")
    panel.pac_btn = SimpleNamespace(configure=mock.Mock())
    panel.pac_action_buttons = {
        "PROXY": SimpleNamespace(configure=mock.Mock()),
        "DIRECT": SimpleNamespace(configure=mock.Mock()),
    }

    panel.sync_from_config()

    assert panel.subscription_var.get() == "https://example.com/sub"
    assert panel.tun_bypass_var.get() == "ToDesk"
    assert panel.tun_bypass_state_var.get() == "当前直连程序: ToDesk"
    assert panel.pac_proxy_domains_var.get() == "google.com"
    assert panel.pac_direct_domains_var.get() == "baidu.com"
    assert panel.pac_default_action_var.get() == "PROXY"
    assert panel.pac_port_var.get() == "7893"


def test_open_existing_panel_refreshes_and_syncs_before_focus() -> None:
    import deskvane.mihomo.panel as panel_module

    calls: list[str] = []

    class _ExistingPanel:
        def sync_from_config(self) -> None:
            calls.append("sync")

        def refresh(self) -> None:
            calls.append("refresh")

        def lift(self) -> None:
            calls.append("lift")

        def focus_force(self) -> None:
            calls.append("focus")

    existing = _ExistingPanel()
    previous = panel_module._active_panel
    panel_module._active_panel = existing
    try:
        open_mihomo_panel(SimpleNamespace())
    finally:
        panel_module._active_panel = previous

    assert calls == ["sync", "refresh", "lift", "focus"]
