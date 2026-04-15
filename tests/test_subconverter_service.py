from unittest import mock

from deskvane.subconverter.service import (
    convert_subscription_source_to_provider_yaml,
    convert_subscription_source_to_yaml,
    load_subscription_proxies,
    load_subscription_source,
)


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def read(self) -> bytes:
        return self._body


def test_load_subscription_source_fetches_remote_url() -> None:
    with mock.patch(
        "urllib.request.urlopen",
        return_value=_FakeResponse(b"ss://YWVzLTI1Ni1nY206cHdkQDEyNy4wLjAuMTo4Mzg4#demo"),
    ) as open_mock:
        content = load_subscription_source("https://example.com/sub")

    assert "ss://" in content
    open_mock.assert_called_once()


def test_convert_subscription_source_to_yaml_from_inline_text() -> None:
    yaml_str = convert_subscription_source_to_yaml(
        "ss://YWVzLTI1Ni1nY206cHdkQDEyNy4wLjAuMTo4Mzg4#demo"
    )

    assert "proxies:" in yaml_str
    assert "demo" in yaml_str


def test_load_subscription_proxies_returns_proxy_list() -> None:
    proxies = load_subscription_proxies(
        "ss://YWVzLTI1Ni1nY206cHdkQDEyNy4wLjAuMTo4Mzg4#demo"
    )

    assert len(proxies) == 1
    assert proxies[0]["name"] == "demo"


def test_convert_subscription_source_to_provider_yaml_from_inline_text() -> None:
    yaml_str = convert_subscription_source_to_provider_yaml(
        "ss://YWVzLTI1Ni1nY206cHdkQDEyNy4wLjAuMTo4Mzg4#demo"
    )

    assert "proxies:" in yaml_str
    assert "demo" in yaml_str
