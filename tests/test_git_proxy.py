from __future__ import annotations

from unittest import mock

import pytest

from deskvane.git_proxy import GitProxyManager, ProxyStatus


class TestProxyStatus:
    def test_disabled_when_none(self):
        s = ProxyStatus()
        assert not s.enabled
        assert s.display == "未设置"

    def test_enabled_with_http(self):
        s = ProxyStatus(http_proxy="http://127.0.0.1:7890")
        assert s.enabled
        assert "http: http://127.0.0.1:7890" in s.display

    def test_enabled_with_both(self):
        s = ProxyStatus(
            http_proxy="http://127.0.0.1:7890",
            https_proxy="http://127.0.0.1:7890",
        )
        assert s.enabled
        assert "http:" in s.display
        assert "https:" in s.display


class TestGitProxyManager:
    @mock.patch("deskvane.git_proxy.subprocess.run")
    def test_get_status_no_proxy(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=1, stdout="")
        status = GitProxyManager.get_status()
        assert not status.enabled
        assert mock_run.call_count == 2

    @mock.patch("deskvane.git_proxy.subprocess.run")
    def test_get_status_with_proxy(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "http.proxy" in cmd:
                return mock.Mock(returncode=0, stdout="http://127.0.0.1:7890\n")
            return mock.Mock(returncode=0, stdout="http://127.0.0.1:7890\n")
        mock_run.side_effect = side_effect
        status = GitProxyManager.get_status()
        assert status.enabled
        assert status.http_proxy == "http://127.0.0.1:7890"

    @mock.patch("deskvane.git_proxy.subprocess.run")
    def test_enable(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0)
        GitProxyManager.enable("http://127.0.0.1:7890")
        assert mock_run.call_count == 2
        calls = mock_run.call_args_list
        assert "http.proxy" in calls[0][0][0]
        assert "https.proxy" in calls[1][0][0]

    @mock.patch("deskvane.git_proxy.subprocess.run")
    def test_disable(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0)
        GitProxyManager.disable()
        assert mock_run.call_count == 2
        calls = mock_run.call_args_list
        assert "--unset" in calls[0][0][0]
        assert "--unset" in calls[1][0][0]
