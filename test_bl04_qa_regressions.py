"""Offline regression checks for BL-04-QA-001 and BL-04-QA-002."""

import json
from unittest.mock import Mock

import pytest
import requests

import ip_privacy


MULTICAST = ["224.0.0.1", "239.255.255.250", "ff02::1", "ff0e::1"]


def response(payload, status=200):
    return Mock(status_code=status, json=Mock(return_value=payload))


@pytest.mark.parametrize("failure", [
    "missing_key", "timeout", "connection", "401", "403", "429", "500", "null",
])
def test_hosting_runs_when_privacy_fails(monkeypatch, capsys, failure):
    monkeypatch.setenv("IPAPI_IS_KEY", "test-hosting-key")
    if failure == "missing_key":
        monkeypatch.delenv("VPNAPI_KEY", raising=False)
    else:
        monkeypatch.setenv("VPNAPI_KEY", "test-privacy-key")

    def get(url, **kwargs):
        if url == "https://api.ipapi.is/":
            return response({"ip": "8.8.8.8", "is_datacenter": True})
        if failure == "timeout":
            raise requests.Timeout()
        if failure == "connection":
            raise requests.ConnectionError()
        if failure == "null":
            return response(None)
        return response({}, int(failure))

    fetch = Mock(side_effect=get)
    monkeypatch.setattr(ip_privacy.requests, "get", fetch)
    assert ip_privacy.main(["--target", "8.8.8.8"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["hosting"] == "Yes"
    assert result["hosting_source"] == "ipapi.is"
    assert result["status"] == "partial"
    assert result["errors"]
    assert all(result[k] == "Unknown" for k in ("vpn", "proxy", "tor", "relay"))
    assert any(call.args[0] == "https://api.ipapi.is/" for call in fetch.call_args_list)


def test_both_providers_fail_remains_unavailable(monkeypatch, capsys):
    monkeypatch.setenv("VPNAPI_KEY", "test-key")
    monkeypatch.setenv("IPAPI_IS_KEY", "test-key")
    fetch = Mock(side_effect=requests.Timeout())
    monkeypatch.setattr(ip_privacy.requests, "get", fetch)
    assert ip_privacy.main(["--target", "8.8.8.8"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "unavailable"
    assert result["hosting"] == "Unknown"
    assert fetch.call_count == 2


@pytest.mark.parametrize("target", MULTICAST)
@pytest.mark.parametrize("lookup", [ip_privacy.check_privacy, ip_privacy.check_hosting])
def test_multicast_helpers_make_no_request(monkeypatch, target, lookup):
    fetch = Mock()
    monkeypatch.setattr(ip_privacy.requests, "get", fetch)
    result = lookup(target, api_key="test-key")
    assert result["errors"]
    assert result["hosting"] == "Unknown"
    fetch.assert_not_called()


@pytest.mark.parametrize("target", MULTICAST)
def test_explicit_multicast_makes_no_request(monkeypatch, capsys, target):
    monkeypatch.setenv("VPNAPI_KEY", "test-key")
    monkeypatch.setenv("IPAPI_IS_KEY", "test-key")
    fetch = Mock()
    monkeypatch.setattr(ip_privacy.requests, "get", fetch)
    assert ip_privacy.main(["--target", target]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"
    fetch.assert_not_called()


@pytest.mark.parametrize("target", MULTICAST)
def test_self_detection_skips_multicast_and_uses_valid_fallback(monkeypatch, capsys, target):
    import ip_core

    monkeypatch.setattr(ip_core, "get_public_ip_info", lambda: {
        "ipv4": target, "ipv6": "2001:4860:4860::8888",
    })
    privacy = Mock(return_value={
        "ip": "2001:4860:4860::8888", "vpn": "No", "proxy": "No",
        "tor": "No", "relay": "No", "hosting": "Unknown",
        "source": "vpnapi.io", "status": "complete", "errors": [],
    })
    hosting = Mock(return_value={"hosting": "No", "source": "ipapi.is", "errors": []})
    monkeypatch.setattr(ip_privacy, "check_privacy", privacy)
    monkeypatch.setattr(ip_privacy, "check_hosting", hosting)
    assert ip_privacy.main([]) == 0
    capsys.readouterr()
    privacy.assert_called_once_with("2001:4860:4860::8888")
    hosting.assert_called_once_with("2001:4860:4860::8888")


def test_self_detection_rejects_only_multicast_results(monkeypatch, capsys):
    import ip_core

    monkeypatch.setattr(ip_core, "get_public_ip_info", lambda: {
        "ipv4": "224.0.0.1", "ipv6": "ff02::1",
    })
    fetch = Mock()
    monkeypatch.setattr(ip_privacy.requests, "get", fetch)
    assert ip_privacy.main([]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"
    fetch.assert_not_called()
