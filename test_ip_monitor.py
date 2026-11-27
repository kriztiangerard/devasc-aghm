"""Offline tests for BL-06 monitoring; no live API calls."""

from threading import Event
from unittest.mock import Mock

import pytest

from ip_monitor import IPMonitor, main


def test_first_address_sets_baseline_without_alert():
    callback = Mock()
    monitor = IPMonitor(
        fetch=lambda: {"ipv4": "8.8.8.8"},
        on_change=callback,
    )

    assert monitor.check_once() == []
    assert monitor.last_valid == {"ipv4": "8.8.8.8"}
    callback.assert_not_called()


def test_unchanged_address_does_not_alert():
    callback = Mock()
    monitor = IPMonitor(
        fetch=lambda: {"ipv4": "8.8.8.8"},
        on_change=callback,
    )

    monitor.check_once()
    assert monitor.check_once() == []
    callback.assert_not_called()


def test_change_alerts_once():
    callback = Mock()
    fetch = Mock(side_effect=[
        {"ipv4": "8.8.8.8"},
        {"ipv4": "1.1.1.1"},
        {"ipv4": "1.1.1.1"},
    ])
    monitor = IPMonitor(fetch=fetch, on_change=callback)

    monitor.check_once()
    assert monitor.check_once() == [{
        "field": "ipv4",
        "previous": "8.8.8.8",
        "current": "1.1.1.1",
    }]
    assert monitor.check_once() == []

    callback.assert_called_once_with(
        "ipv4", "8.8.8.8", "1.1.1.1"
    )


def test_failure_preserves_baseline_and_recovery_detects_change():
    fetch = Mock(side_effect=[
        {"ipv4": "8.8.8.8"},
        RuntimeError("Connection failed"),
        {"ipv4": "Unavailable"},
        {"ipv4": "1.1.1.1"},
    ])
    monitor = IPMonitor(fetch=fetch)

    monitor.check_once()
    assert monitor.check_once() == []
    assert monitor.check_once() == []
    assert monitor.last_valid["ipv4"] == "8.8.8.8"

    assert monitor.check_once()[0]["current"] == "1.1.1.1"


def test_ipv4_and_ipv6_are_tracked_independently():
    fetch = Mock(side_effect=[
        {"ipv4": "8.8.8.8", "ipv6": "2001:db8::1"},
        {"ipv4": "Unavailable", "ipv6": "2001:db8::2"},
    ])
    monitor = IPMonitor(fetch=fetch)

    monitor.check_once()
    changes = monitor.check_once()

    assert changes == [{
        "field": "ipv6",
        "previous": "2001:db8::1",
        "current": "2001:db8::2",
    }]
    assert monitor.last_valid["ipv4"] == "8.8.8.8"


@pytest.mark.parametrize("value", [
    None, "", "Unknown", "invalid", 123, "2001:db8::1",
])
def test_invalid_ipv4_does_not_set_baseline(value):
    monitor = IPMonitor(fetch=lambda: {"ipv4": value})

    assert monitor.check_once() == []
    assert monitor.last_valid == {}


def test_equivalent_ipv6_forms_do_not_trigger_change():
    fetch = Mock(side_effect=[
        {"ipv6": "2001:0db8:0000:0000:0000:0000:0000:0001"},
        {"ipv6": "2001:db8::1"},
    ])
    monitor = IPMonitor(fetch=fetch)

    monitor.check_once()
    assert monitor.check_once() == []


def test_invalid_backend_result_preserves_baseline():
    fetch = Mock(side_effect=[
        {"ipv4": "8.8.8.8"},
        None,
    ])
    monitor = IPMonitor(fetch=fetch)

    monitor.check_once()
    assert monitor.check_once() == []
    assert monitor.last_valid["ipv4"] == "8.8.8.8"


def test_callback_failure_does_not_stop_other_changes():
    callback = Mock(side_effect=RuntimeError("Notification failed"))
    fetch = Mock(side_effect=[
        {"ipv4": "8.8.8.8", "ipv6": "2001:db8::1"},
        {"ipv4": "1.1.1.1", "ipv6": "2001:db8::2"},
    ])
    monitor = IPMonitor(fetch=fetch, on_change=callback)

    monitor.check_once()
    assert len(monitor.check_once()) == 2
    assert callback.call_count == 2


@pytest.mark.parametrize("interval", [0, -1, float("nan"), float("inf")])
def test_invalid_interval_rejected(interval):
    monitor = IPMonitor(fetch=Mock())

    with pytest.raises(ValueError):
        monitor.run(interval=interval)


def test_stopped_monitor_does_not_fetch():
    stop = Event()
    stop.set()
    fetch = Mock()

    IPMonitor(fetch=fetch).run(stop_event=stop)
    fetch.assert_not_called()


def test_run_checks_immediately_and_waits_configured_interval():
    fetch = Mock(return_value={"ipv4": "8.8.8.8"})
    stop = Mock()
    stop.is_set.return_value = False
    stop.wait.return_value = True

    IPMonitor(fetch=fetch).run(interval=30, stop_event=stop)

    fetch.assert_called_once_with()
    stop.wait.assert_called_once_with(30)


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "abc"])
def test_cli_rejects_invalid_interval(value):
    with pytest.raises(SystemExit) as exc:
        main(["--interval", value])

    assert exc.value.code == 2


def test_main_stops_cleanly_on_keyboard_interrupt(monkeypatch):
    def interrupt(self, interval):
        raise KeyboardInterrupt

    monkeypatch.setattr(IPMonitor, "run", interrupt)
    assert main(["--interval", "30"]) == 0