"""BL-04 offline tests. All HTTP requests are mocked."""

from unittest.mock import Mock, patch

import pytest
import requests

from ip_privacy import check_privacy, main


TARGET = "8.8.8.8"
KEY = "test-key-only"


def response(data, status=200):
    result = Mock()
    result.status_code = status
    result.json.return_value = data
    return result


def valid_data(target=TARGET):
    return {
        "ip": target,
        "security": {
            "vpn": False,
            "proxy": False,
            "tor": False,
            "relay": False,
        },
    }


def test_missing_key_does_not_request(monkeypatch):
    monkeypatch.delenv("VPNAPI_KEY", raising=False)

    with patch("ip_privacy.requests.get") as get:
        result = check_privacy(TARGET)

    get.assert_not_called()
    assert result["vpn"] == "Unknown"
    assert result["status"] == "unavailable"


@pytest.mark.parametrize("target", [
    None, 123, "", "invalid", "https://example.com",
    "192.168.1.1", "127.0.0.1", "::1", "fe80::1%en0",
])
def test_invalid_or_nonpublic_target_does_not_request(target):
    with patch("ip_privacy.requests.get") as get:
        result = check_privacy(target, api_key=KEY)

    get.assert_not_called()
    assert result["errors"]
    assert result["status"] == "unavailable"


def test_explicit_false_flags_are_no():
    with patch(
        "ip_privacy.requests.get",
        return_value=response(valid_data()),
    ):
        result = check_privacy(TARGET, api_key=KEY)

    assert result["status"] == "complete"
    for field in ("vpn", "proxy", "tor", "relay"):
        assert result[field] == "No"
    assert result["hosting"] == "Unknown"


@pytest.mark.parametrize("field", ["vpn", "proxy", "tor", "relay"])
def test_explicit_true_flag_is_yes(field):
    data = valid_data()
    data["security"][field] = True

    with patch(
        "ip_privacy.requests.get",
        return_value=response(data),
    ):
        result = check_privacy(TARGET, api_key=KEY)

    assert result[field] == "Yes"


def test_missing_field_stays_unknown():
    data = valid_data()
    del data["security"]["tor"]

    with patch(
        "ip_privacy.requests.get",
        return_value=response(data),
    ):
        result = check_privacy(TARGET, api_key=KEY)

    assert result["tor"] == "Unknown"
    assert result["status"] == "partial"


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_nonboolean_flags_are_not_coerced(value):
    data = valid_data()
    data["security"]["vpn"] = value

    with patch(
        "ip_privacy.requests.get",
        return_value=response(data),
    ):
        result = check_privacy(TARGET, api_key=KEY)

    assert result["vpn"] == "Unknown"
    assert result["status"] == "partial"


@pytest.mark.parametrize("data", [
    None,
    [],
    "invalid",
    {},
    {"ip": "1.1.1.1", "security": {}},
    {"ip": TARGET, "security": None},
    {"ip": TARGET, "security": []},
])
def test_malformed_response_is_handled(data):
    with patch(
        "ip_privacy.requests.get",
        return_value=response(data),
    ):
        result = check_privacy(TARGET, api_key=KEY)

    assert result["status"] == "unavailable"
    assert result["errors"]


def test_invalid_json_is_handled():
    resp = response(None)
    resp.json.side_effect = ValueError("invalid JSON")

    with patch("ip_privacy.requests.get", return_value=resp):
        result = check_privacy(TARGET, api_key=KEY)

    assert result["status"] == "unavailable"
    assert "invalid JSON" in result["errors"][0]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_failure_is_handled(status):
    with patch(
        "ip_privacy.requests.get",
        return_value=response({}, status=status),
    ):
        result = check_privacy(TARGET, api_key=KEY)

    assert result["status"] == "unavailable"
    assert result["errors"]
    assert result["vpn"] == "Unknown"


@pytest.mark.parametrize("failure", [
    requests.Timeout("secret-key-in-error"),
    requests.ConnectionError("secret-key-in-error"),
])
def test_network_failure_does_not_leak_details(failure):
    with patch(
        "ip_privacy.requests.get",
        side_effect=failure,
    ):
        result = check_privacy(TARGET, api_key=KEY)

    assert result["status"] == "unavailable"
    assert "secret-key-in-error" not in str(result)
    assert KEY not in str(result)


def test_ipv6_target():
    target = "2001:4860:4860::8888"

    with patch(
        "ip_privacy.requests.get",
        return_value=response(valid_data(target)),
    ):
        result = check_privacy(target, api_key=KEY)

    assert result["ip"] == target
    assert result["status"] == "complete"


def test_environment_key_and_request_timeout(monkeypatch):
    monkeypatch.setenv("VPNAPI_KEY", KEY)

    with patch(
        "ip_privacy.requests.get",
        return_value=response(valid_data()),
    ) as get:
        check_privacy(TARGET)

    get.assert_called_once_with(
        "https://vpnapi.io/api/8.8.8.8",
        params={"key": KEY},
        timeout=5,
    )


def test_cli_returns_failure_without_key(monkeypatch, capsys):
    monkeypatch.delenv("VPNAPI_KEY", raising=False)

    with patch("ip_privacy.requests.get") as get:
        assert main(["--target", TARGET]) == 1

    get.assert_not_called()
    assert "VPNAPI_KEY is not configured" in capsys.readouterr().out

# Hosting provider and combined CLI tests.

from ip_privacy import check_hosting


@pytest.mark.parametrize("flag,expected", [
    (True, "Yes"),
    (False, "No"),
])
def test_hosting_explicit_boolean(flag, expected):
    with patch(
        "ip_privacy.requests.get",
        return_value=response({
            "ip": TARGET,
            "is_datacenter": flag,
        }),
    ):
        result = check_hosting(TARGET, api_key=KEY)

    assert result["hosting"] == expected
    assert result["source"] == "ipapi.is"
    assert result["errors"] == []


@pytest.mark.parametrize("flag", [None, "false", 0, 1])
def test_hosting_nonboolean_stays_unknown(flag):
    with patch(
        "ip_privacy.requests.get",
        return_value=response({
            "ip": TARGET,
            "is_datacenter": flag,
        }),
    ):
        result = check_hosting(TARGET, api_key=KEY)

    assert result["hosting"] == "Unknown"
    assert result["errors"]


def test_hosting_missing_key(monkeypatch):
    monkeypatch.delenv("IPAPI_IS_KEY", raising=False)

    with patch("ip_privacy.requests.get") as get:
        result = check_hosting(TARGET)

    get.assert_not_called()
    assert result["hosting"] == "Unknown"
    assert "IPAPI_IS_KEY" in result["errors"][0]


@pytest.mark.parametrize("data", [
    None,
    [],
    {"ip": "1.1.1.1", "is_datacenter": True},
    {"ip": TARGET},
    {"error": "Service error"},
])
def test_hosting_malformed_response(data):
    with patch(
        "ip_privacy.requests.get",
        return_value=response(data),
    ):
        result = check_hosting(TARGET, api_key=KEY)

    assert result["hosting"] == "Unknown"
    assert result["errors"]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_hosting_http_errors(status):
    with patch(
        "ip_privacy.requests.get",
        return_value=response({}, status=status),
    ):
        result = check_hosting(TARGET, api_key=KEY)

    assert result["hosting"] == "Unknown"
    assert result["errors"]


@pytest.mark.parametrize("failure", [
    requests.Timeout("secret-key"),
    requests.ConnectionError("secret-key"),
])
def test_hosting_network_errors_do_not_leak_key(failure):
    with patch(
        "ip_privacy.requests.get",
        side_effect=failure,
    ):
        result = check_hosting(TARGET, api_key=KEY)

    assert result["hosting"] == "Unknown"
    assert "secret-key" not in str(result)


def test_hosting_invalid_json():
    resp = response(None)
    resp.json.side_effect = ValueError("Invalid JSON")

    with patch("ip_privacy.requests.get", return_value=resp):
        result = check_hosting(TARGET, api_key=KEY)

    assert result["hosting"] == "Unknown"
    assert result["errors"]


@pytest.mark.parametrize("target", [
    None, "invalid", "192.168.1.1", "fe80::1%en0",
])
def test_hosting_rejects_invalid_targets(target):
    with patch("ip_privacy.requests.get") as get:
        result = check_hosting(target, api_key=KEY)

    get.assert_not_called()
    assert result["errors"]


def test_hosting_ipv6():
    target = "2001:4860:4860::8888"

    with patch(
        "ip_privacy.requests.get",
        return_value=response({
            "ip": target,
            "is_datacenter": True,
        }),
    ):
        result = check_hosting(target, api_key=KEY)

    assert result["hosting"] == "Yes"


def test_combined_cli_complete(monkeypatch, capsys):
    monkeypatch.setenv("VPNAPI_KEY", KEY)
    monkeypatch.setenv("IPAPI_IS_KEY", KEY)

    with patch(
        "ip_privacy.requests.get",
        side_effect=[
            response(valid_data()),
            response({"ip": TARGET, "is_datacenter": True}),
        ],
    ):
        assert main(["--target", TARGET]) == 0

    import json
    result = json.loads(capsys.readouterr().out)
    assert result["hosting"] == "Yes"
    assert result["hosting_source"] == "ipapi.is"
    assert result["status"] == "complete"


def test_combined_cli_partial_when_hosting_unavailable(
    monkeypatch, capsys
):
    monkeypatch.setenv("VPNAPI_KEY", KEY)
    monkeypatch.delenv("IPAPI_IS_KEY", raising=False)

    with patch(
        "ip_privacy.requests.get",
        return_value=response(valid_data()),
    ):
        assert main(["--target", TARGET]) == 1

    import json
    result = json.loads(capsys.readouterr().out)
    assert result["vpn"] == "No"
    assert result["hosting"] == "Unknown"
    assert result["status"] == "partial"