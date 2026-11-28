"""BL-11 tests with mocked tray, notifications, and GUI process."""

import subprocess
import threading
from unittest.mock import Mock, patch

import pytest

import ip_tray


@pytest.fixture
def tray():
    # Avoid creating a native tray icon during automated tests.
    with patch("ip_tray.pystray.Icon") as icon_class:
        app = ip_tray.TrayMonitor(interval=60)
        app.icon = icon_class.return_value
        yield app


def test_initial_status_is_stopped(tray):
    assert not tray.is_running()
    assert tray.status_text(None) == "Monitoring: stopped"


def test_status_distinguishes_running_and_stopping(tray):
    tray.worker = Mock()
    tray.worker.is_alive.return_value = True

    assert tray.status_text(None) == "Monitoring: running"

    tray.stop_event.set()
    assert tray.status_text(None) == "Monitoring: stopping..."


def test_start_prevents_duplicate_worker(tray):
    tray.worker = Mock()
    tray.worker.is_alive.return_value = True

    with patch("ip_tray.threading.Thread") as thread:
        tray.start()
        thread.assert_not_called()


def test_start_creates_monitor_worker(tray):
    with patch("ip_tray.threading.Thread") as thread:
        tray.start()

    thread.assert_called_once_with(
        target=tray.monitor_loop,
        name="ip-monitor",
        daemon=True,
    )
    thread.return_value.start.assert_called_once()
    assert not tray.stop_event.is_set()


def test_monitor_uses_change_callback_and_stop_event(tray):
    with patch("ip_tray.IPMonitor") as monitor:
        tray.monitor_loop()

    monitor.assert_called_once_with(on_change=tray.on_change)
    monitor.return_value.run.assert_called_once_with(
        interval=60,
        stop_event=tray.stop_event,
    )


def test_stop_sets_event_and_schedules_menu_refresh(tray):
    tray.worker = Mock()

    with patch("ip_tray.threading.Thread") as thread:
        tray.stop()

    assert tray.stop_event.is_set()
    thread.assert_called_once_with(
        target=tray._refresh_after_stop,
        args=(tray.worker,),
        daemon=True,
    )
    thread.return_value.start.assert_called_once()


def test_menu_refresh_waits_for_worker_exit(tray):
    worker = Mock()

    tray._refresh_after_stop(worker)

    worker.join.assert_called_once_with()
    tray.icon.update_menu.assert_called_once()


def test_change_notifies_only_while_active(tray):
    tray.notify = Mock()

    tray.on_change("ipv4", "192.0.2.1", "192.0.2.2")
    tray.notify.assert_called_once_with(
        "Public IP changed",
        "IPV4: 192.0.2.1 → 192.0.2.2",
    )

    tray.notify.reset_mock()
    tray.stop_event.set()
    tray.on_change("ipv4", "192.0.2.2", "192.0.2.3")
    tray.notify.assert_not_called()

    tray.stop_event.clear()
    tray.closing = True
    tray.on_change("ipv4", "192.0.2.2", "192.0.2.3")
    tray.notify.assert_not_called()


def test_macos_notification_passes_text_as_arguments(tray):
    with patch("ip_tray.sys.platform", "darwin"), \
         patch("ip_tray.subprocess.run") as run:
        tray.notify("Title", 'Message with "quotes"')

    args, kwargs = run.call_args
    assert args[0] == [
        "osascript", "-", "Title", 'Message with "quotes"'
    ]
    assert kwargs["check"] is True
    assert kwargs["timeout"] == 10
    assert "shell" not in kwargs


def test_notification_failure_is_handled(tray, caplog):
    with patch("ip_tray.sys.platform", "darwin"), \
         patch(
             "ip_tray.subprocess.run",
             side_effect=subprocess.TimeoutExpired("osascript", 10),
         ):
        tray.notify("Title", "Message")

    assert "Unable to deliver notification" in caplog.text


def test_show_starts_one_gui_then_restores_existing(tray):
    process = Mock()
    process.poll.return_value = None

    with patch(
        "ip_tray.subprocess.Popen",
        return_value=process,
    ) as launch:
        tray.show_window()
        tray.show_window()

    launch.assert_called_once()
    process.stdin.write.assert_called_once_with("show\n")
    process.stdin.flush.assert_called_once()


def test_hide_sends_command(tray):
    tray.gui_process = Mock()
    tray.gui_process.poll.return_value = None

    tray.hide_window()

    tray.gui_process.stdin.write.assert_called_once_with("hide\n")


def test_exit_requests_monitor_and_gui_shutdown(tray):
    tray.gui_process = Mock()
    tray.gui_process.poll.return_value = None

    tray.exit()

    assert tray.closing
    assert tray.stop_event.is_set()
    tray.gui_process.stdin.write.assert_called_once_with("quit\n")
    tray.icon.stop.assert_called_once()


def test_gui_cleanup_waits_for_exit(tray):
    process = Mock()
    process.poll.return_value = None
    tray.gui_process = process

    tray._cleanup_gui()

    process.stdin.close.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)
    process.terminate.assert_not_called()


def test_gui_cleanup_terminates_unresponsive_child(tray):
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = [
        subprocess.TimeoutExpired("gui", 5),
        0,
    ]
    tray.gui_process = process

    tray._cleanup_gui()

    process.terminate.assert_called_once()
    assert process.wait.call_count == 2