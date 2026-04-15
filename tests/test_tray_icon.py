from io import BytesIO
from types import SimpleNamespace

from PIL import Image as PILImage
from PIL import ImageDraw as PILImageDraw

from deskvane.mihomo.api import MihomoProxyGroup, MihomoRuntimeState
from deskvane.tray import TrayController


class _FakeTray:
    Image = PILImage
    ImageDraw = PILImageDraw
    _SEGMENT_MAP = TrayController._SEGMENT_MAP
    _draw_centered = staticmethod(TrayController._draw_centered)
    _draw_digit = TrayController._draw_digit
    _draw_meter = staticmethod(TrayController._draw_meter)
    _draw_value_display = TrayController._draw_value_display

    def __init__(self, mode: str) -> None:
        self.app = SimpleNamespace(
            config=SimpleNamespace(
                general=SimpleNamespace(tray_display=mode),
            )
        )


class _Gpu:
    def __init__(self, usage_pct: float, temp_c: float = 67.0, mem_used_mb: int = 13163, mem_total_mb: int = 32607) -> None:
        self.usage_pct = usage_pct
        self.temp_c = temp_c
        self.mem_used_mb = mem_used_mb
        self.mem_total_mb = mem_total_mb


def _png_bytes(image) -> bytes:
    buf = BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def test_gpu_usage_icon_changes_when_value_changes() -> None:
    tray = _FakeTray("gpu_usage")

    icon_48 = TrayController._build_icon(tray, cpu=None, gpu=_Gpu(48.0))
    icon_53 = TrayController._build_icon(tray, cpu=None, gpu=_Gpu(53.0))

    assert _png_bytes(icon_48) != _png_bytes(icon_53)


def test_default_and_dynamic_icons_differ() -> None:
    default_tray = _FakeTray("default")
    gpu_tray = _FakeTray("gpu_usage")

    default_icon = TrayController._build_icon(default_tray, cpu=None, gpu=None)
    dynamic_icon = TrayController._build_icon(gpu_tray, cpu=None, gpu=_Gpu(54.0))

    assert _png_bytes(default_icon) != _png_bytes(dynamic_icon)


def test_build_label_for_gpu_usage() -> None:
    tray = _FakeTray("gpu_usage")

    label, guide = TrayController._build_label(tray, cpu=None, gpu=_Gpu(54.0))

    assert label == "54%"
    assert guide == "100%"


def test_build_label_for_default_mode_is_blank() -> None:
    tray = _FakeTray("default")

    label, guide = TrayController._build_label(tray, cpu=None, gpu=_Gpu(54.0))

    assert label == ""
    assert guide == ""


def test_mihomo_snapshot_uses_core_status_running_flag() -> None:
    runtime = MihomoRuntimeState(
        api_ready=True,
        controller="http://127.0.0.1:9090",
        mode="rule",
        mixed_port=7890,
        port=None,
        socks_port=7891,
        tun_enabled=True,
        groups=[],
    )
    tray = TrayController.__new__(TrayController)
    tray.app = SimpleNamespace(
        mihomo_manager=SimpleNamespace(
            backend="core",
            display_name="Mihomo Core",
            is_installed=lambda: True,
            is_running=lambda: False,
            get_core_status=lambda: SimpleNamespace(
                controller="http://127.0.0.1:9090",
                api_ready=True,
                running=True,
            ),
            get_runtime_state=lambda: runtime,
        ),
        config=SimpleNamespace(
            mihomo=SimpleNamespace(
                external_ui="",
                external_ui_name="",
                external_ui_url="",
            )
        ),
    )

    snapshot = TrayController._get_mihomo_snapshot(tray, use_cache=False)

    assert snapshot["running"] is True
    assert snapshot["runtime"].tun_enabled is True


def test_saved_subscription_urls_put_current_first_and_deduplicate() -> None:
    tray = TrayController.__new__(TrayController)
    tray.app = SimpleNamespace(
        config=SimpleNamespace(
            mihomo=SimpleNamespace(
                subscription_url="https://current.example/sub",
                saved_subscriptions=[
                    "https://old.example/sub",
                    "https://current.example/sub",
                ],
            )
        )
    )

    assert TrayController._saved_subscription_urls(tray) == [
        "https://current.example/sub",
        "https://old.example/sub",
    ]


def test_subscription_menu_label_prefers_host_and_service() -> None:
    label = TrayController._subscription_menu_label(
        "https://jmssub.net/members/getsub.php?service=1206392&id=a2e3eab7-38e1-4394-b71e-ef012e0abcab"
    )

    assert label == "jmssub.net · 1206392"


def test_mihomo_primary_group_prefers_proxy_in_rule_mode() -> None:
    runtime = MihomoRuntimeState(
        api_ready=True,
        controller="http://127.0.0.1:9090",
        mode="rule",
        mixed_port=7890,
        port=None,
        socks_port=7891,
        tun_enabled=True,
        groups=[
            MihomoProxyGroup(name="Auto", group_type="URLTest", current="Node-B", candidates=["Node-A", "Node-B"]),
            MihomoProxyGroup(name="PROXY", group_type="Selector", current="Auto", candidates=["Auto", "Node-A", "Node-B"]),
            MihomoProxyGroup(name="GLOBAL", group_type="Selector", current="Node-A", candidates=["Node-A", "Node-B"]),
        ],
    )

    group = TrayController._mihomo_primary_group(runtime)

    assert group is not None
    assert group.name == "PROXY"


def test_mihomo_visible_nodes_filter_nested_groups_and_builtins() -> None:
    runtime = MihomoRuntimeState(
        api_ready=True,
        controller="http://127.0.0.1:9090",
        mode="rule",
        mixed_port=7890,
        port=None,
        socks_port=7891,
        tun_enabled=True,
        groups=[
            MihomoProxyGroup(name="PROXY", group_type="Selector", current="Node-A", candidates=["Auto", "Direct", "Node-A", "Node-B", "DIRECT", "REJECT"]),
            MihomoProxyGroup(name="Auto", group_type="URLTest", current="Node-B", candidates=["Node-A", "Node-B"]),
            MihomoProxyGroup(name="Direct", group_type="Selector", current="DIRECT", candidates=["DIRECT"]),
        ],
    )
    group = runtime.groups[0]

    assert TrayController._mihomo_visible_nodes(group, runtime) == ["Node-A", "Node-B"]


def test_mihomo_leaf_node_name_resolves_nested_group_current() -> None:
    runtime = MihomoRuntimeState(
        api_ready=True,
        controller="http://127.0.0.1:9090",
        mode="rule",
        mixed_port=7890,
        port=None,
        socks_port=7891,
        tun_enabled=True,
        groups=[
            MihomoProxyGroup(name="Auto", group_type="URLTest", current="Node-B", candidates=["Node-A", "Node-B"]),
            MihomoProxyGroup(name="PROXY", group_type="Selector", current="Auto", candidates=["Auto", "Node-A", "Node-B"]),
        ],
    )

    assert TrayController._mihomo_leaf_node_name(runtime.groups[1], runtime) == "Node-B"


def test_compact_node_labels_prefers_host_token_when_unique() -> None:
    labels = TrayController._compact_node_labels(
        [
            "JMS-1206392@c82s1.portablesubmarines.com:19652",
            "JMS-1206392@c82s2.portablesubmarines.com:19652",
            "JMS-1206392@c82s801.portablesubmarines.com:19652",
        ]
    )

    assert labels == {
        "JMS-1206392@c82s1.portablesubmarines.com:19652": "c82s1",
        "JMS-1206392@c82s2.portablesubmarines.com:19652": "c82s2",
        "JMS-1206392@c82s801.portablesubmarines.com:19652": "c82s801",
    }


def test_build_mihomo_node_menu_label_includes_delay() -> None:
    runtime = MihomoRuntimeState(
        api_ready=True,
        controller="http://127.0.0.1:9090",
        mode="rule",
        mixed_port=7890,
        port=None,
        socks_port=7891,
        tun_enabled=True,
        groups=[
            MihomoProxyGroup(
                name="PROXY",
                group_type="Selector",
                current="Node-A",
                candidates=["Node-A", "Node-B"],
                candidate_delays={"Node-A": 123},
            ),
        ],
    )
    tray = TrayController.__new__(TrayController)
    tray._mihomo_manual_delay_results = {}

    label = TrayController._build_mihomo_node_menu_label(
        tray,
        "Node-A",
        {"Node-A": "c82s1"},
        runtime,
    )

    assert label == "c82s1 · 123ms"


def test_build_mihomo_node_menu_label_ignores_zero_delay() -> None:
    runtime = MihomoRuntimeState(
        api_ready=True,
        controller="http://127.0.0.1:9090",
        mode="rule",
        mixed_port=7890,
        port=None,
        socks_port=7891,
        tun_enabled=True,
        groups=[
            MihomoProxyGroup(
                name="PROXY",
                group_type="Selector",
                current="Node-A",
                candidates=["Node-A"],
                candidate_delays={"Node-A": 0},
            ),
        ],
    )
    tray = TrayController.__new__(TrayController)
    tray._mihomo_manual_delay_results = {}

    label = TrayController._build_mihomo_node_menu_label(
        tray,
        "Node-A",
        {"Node-A": "c82s1"},
        runtime,
    )

    assert label == "c82s1"
