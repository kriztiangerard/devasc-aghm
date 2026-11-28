"""BL-09 interactive CLI and GUI target lookup tests."""

import queue
from unittest.mock import Mock, patch, call

import pytest

import ip_diagnostic as cli
import ip_diagnostic_gui as gui


def target_result(target="8.8.8.8", ip="8.8.8.8"):
    return {
        "target": target,
        "ip": ip,
        "isp": "Example ISP",
        "asn": "AS15169",
        "city": "Example City",
        "region": "Example Region",
        "country": "United States",
        "country_code": "US",
        "errors": [],
    }


def failed_result(target, error):
    result = {
        key: "Unknown"
        for key in target_result()
    }
    result["target"] = target
    result["errors"] = [error]
    return result


def fake_app(mode="target"):
    """Create a GUI test double without opening a Tk window."""
    app = Mock()
    app._busy = False
    app._closing = False
    app._mode = mode
    app._failed = False
    app._warnings = []
    app.last_updated = None
    app._results = queue.Queue()
    return app


# CLI-01 to CLI-04: repeated IPv4, IPv6 and hostname lookups.

def test_interactive_multiple_targets(capsys):
    targets = [
        "8.8.8.8",
        "2001:4860:4860::8888",
        "example.com",
    ]

    results = [
        target_result(targets[0], targets[0]),
        target_result(targets[1], targets[1]),
        target_result(targets[2], "93.184.216.34"),
    ]

    with patch("builtins.input", side_effect=targets + ["exit"]), \
         patch.object(cli, "lookup_ip", side_effect=results) as lookup, \
         patch.object(cli, "get_public_ip_info") as self_lookup:

        assert cli.main(["--interactive"]) == 0

    assert [call.args[0] for call in lookup.call_args_list] == targets
    self_lookup.assert_not_called()

    output = capsys.readouterr().out

    assert output.count("TARGET IP & NETWORK LOOKUP") == 3
    assert "IPv4" in output
    assert "IPv6" in output
    assert "example.com" in output
    assert "93.184.216.34" in output


# CLI-05: empty input.

@pytest.mark.parametrize("empty", ["", "   "])
def test_interactive_empty_input(empty, capsys):
    with patch("builtins.input", side_effect=[empty, "exit"]), \
         patch.object(cli, "lookup_ip") as lookup:

        assert cli.main(["--interactive"]) == 0

    lookup.assert_not_called()
    assert "Target must not be empty" in capsys.readouterr().out


# CLI-06 and CLI-07: failed lookup followed by success.

@pytest.mark.parametrize(
    "target,error",
    [
        ("999.999.999.999", "Invalid IP address."),
        ("nonexistent.invalid", "could not resolve"),
    ],
)
def test_interactive_recovers_after_failure(target, error, capsys):
    with patch(
        "builtins.input",
        side_effect=[target, "8.8.8.8", "exit"],
    ), patch.object(
        cli,
        "lookup_ip",
        side_effect=[
            failed_result(target, error),
            target_result(),
        ],
    ) as lookup:

        assert cli.main(["--interactive"]) == 0

    assert lookup.call_count == 2

    output = capsys.readouterr().out
    assert "Target lookup failed" in output
    assert error in output
    assert "Example ISP" in output


# CLI-08: partial metadata failure.

def test_interactive_partial_metadata(capsys):
    result = target_result()
    result["isp"] = "Unknown"
    result["errors"] = ["Metadata provider unavailable"]

    with patch("builtins.input", side_effect=["8.8.8.8", "exit"]), \
         patch.object(cli, "lookup_ip", return_value=result):

        assert cli.main(["--interactive"]) == 0

    output = capsys.readouterr().out

    assert "8.8.8.8" in output
    assert "Warning: Metadata provider unavailable" in output
    assert "Target lookup failed" not in output


# CLI-09: unexpected exception and recovery.

def test_interactive_recovers_after_exception(capsys):
    with patch(
        "builtins.input",
        side_effect=["8.8.8.8", "1.1.1.1", "exit"],
    ), patch.object(
        cli,
        "lookup_ip",
        side_effect=[
            RuntimeError("Test backend failure"),
            target_result("1.1.1.1", "1.1.1.1"),
        ],
    ) as lookup:

        assert cli.main(["--interactive"]) == 0

    assert lookup.call_count == 2

    output = capsys.readouterr().out
    assert "Test backend failure" in output
    assert "Example ISP" in output


# CLI-10: explicit exit commands.

@pytest.mark.parametrize("command", ["exit", "quit", "EXIT", " Quit "])
def test_interactive_exit_commands(command, capsys):
    with patch("builtins.input", return_value=command), \
         patch.object(cli, "lookup_ip") as lookup:

        assert cli.main(["--interactive"]) == 0

    lookup.assert_not_called()
    assert "Interactive lookup ended" in capsys.readouterr().out


# CLI-11: graceful interruption.

@pytest.mark.parametrize("exception", [EOFError, KeyboardInterrupt])
def test_interactive_graceful_interruption(exception, capsys):
    with patch("builtins.input", side_effect=exception), \
         patch.object(cli, "lookup_ip") as lookup:

        assert cli.main(["--interactive"]) == 0

    lookup.assert_not_called()
    assert "Interactive lookup ended" in capsys.readouterr().out


# CLI-12: incompatible arguments.

@pytest.mark.parametrize(
    "arguments",
    [
        ["--interactive", "--json"],
        ["--interactive", "--csv"],
        ["--interactive", "--target", "8.8.8.8"],
    ],
)
def test_interactive_incompatible_arguments(arguments, capsys):
    with patch.object(cli, "lookup_ip") as lookup, \
         patch.object(cli, "get_public_ip_info") as self_lookup:

        with pytest.raises(SystemExit) as exc:
            cli.main(arguments)

    assert exc.value.code == 2
    lookup.assert_not_called()
    self_lookup.assert_not_called()

    assert "cannot be combined" in capsys.readouterr().err


# CLI-13: help.

def test_interactive_help(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    assert "--interactive" in capsys.readouterr().out


# GUI-01 to GUI-03: target result adaptation.

@pytest.mark.parametrize(
    "target,ip,version",
    [
        ("8.8.8.8", "8.8.8.8", "IPv4"),
        (
            "2001:4860:4860::8888",
            "2001:4860:4860::8888",
            "IPv6",
        ),
        ("example.com", "93.184.216.34", "IPv4"),
    ],
)
def test_gui_target_adapter(target, ip, version):
    with patch.object(
        gui,
        "lookup_ip",
        return_value=target_result(target, ip),
    ) as lookup:

        data, warnings, failed = gui.fetch_target_data(target)

    lookup.assert_called_once_with(target)

    assert data["target"] == target
    assert data["ip"] == ip
    assert data["version"] == version
    assert data["isp"] == "Example ISP"
    assert data["asn"] == "AS15169"
    assert data["country_code"] == "US"
    assert data["location"] == (
        "Example City, Example Region, United States"
    )
    assert warnings == []
    assert failed is False


# GUI-04: invalid target and DNS failure.

@pytest.mark.parametrize(
    "target,error",
    [
        ("999.999.999.999", "Invalid IP address."),
        ("nonexistent.invalid", "could not resolve"),
    ],
)
def test_gui_failed_target(target, error):
    with patch.object(
        gui,
        "lookup_ip",
        return_value=failed_result(target, error),
    ):
        data, warnings, failed = gui.fetch_target_data(target)

    assert data["target"] == target
    assert data["ip"] == "Unknown"
    assert data["version"] == "Unknown"
    assert error in warnings
    assert failed is True


# GUI-05: missing metadata.

def test_gui_partial_metadata():
    result = target_result()

    for key in ("isp", "asn", "city", "region",
                "country", "country_code"):
        result[key] = "Unknown"

    with patch.object(gui, "lookup_ip", return_value=result):
        data, warnings, failed = gui.fetch_target_data("8.8.8.8")

    assert data["ip"] == "8.8.8.8"
    assert data["version"] == "IPv4"
    assert data["isp"] == "Unknown"
    assert data["location"] == "Unknown"
    assert failed is False
    assert any("Unavailable metadata" in item for item in warnings)


# GUI-06: empty search input.

def test_gui_empty_search():
    app = fake_app()
    app.target_var.get.return_value = "   "

    gui.IPDiagnosticApp.search_target(app)

    app._start_request.assert_not_called()
    app._set_status.assert_called_once_with(
        "Target must not be empty.",
        gui.COLORS["error"],
    )
    app.target_entry.focus_set.assert_called_once()


# GUI-07: search submission.

def test_gui_search_submission():
    app = fake_app()
    app.target_var.get.return_value = "  example.com  "

    gui.IPDiagnosticApp.search_target(app)

    app._start_request.assert_called_once_with(
        "target", "example.com"
    )


# GUI-08: Enter key submission.

def test_gui_enter_submission():
    app = fake_app()

    result = gui.IPDiagnosticApp._on_search_enter(app, Mock())

    assert result == "break"
    app.search_target.assert_called_once()


# GUI-09: concurrent request prevention.

@pytest.mark.parametrize("method", ["search_target", "refresh_data"])
def test_gui_busy_request_protection(method):
    app = fake_app()
    app._busy = True

    getattr(gui.IPDiagnosticApp, method)(app)

    app._start_request.assert_not_called()


# GUI-10: background worker routing.

def test_gui_target_worker():
    app = fake_app()
    expected = ({"ip": "8.8.8.8"}, [], False)

    with patch.object(
        gui, "fetch_target_data", return_value=expected
    ) as fetch, patch.object(
        gui, "fetch_network_data"
    ) as self_fetch:

        gui.IPDiagnosticApp._worker(app, "target", "8.8.8.8")

    fetch.assert_called_once_with("8.8.8.8")
    self_fetch.assert_not_called()

    assert app._results.get_nowait() == expected
    app._update_ui.assert_not_called()


def test_gui_self_worker():
    app = fake_app("self")
    data = {"ipv4": "203.0.113.10", "ipv6": "Not Detected"}

    with patch.object(
        gui, "fetch_network_data", return_value=(data, [])
    ) as fetch:

        gui.IPDiagnosticApp._worker(app, "self")

    fetch.assert_called_once()
    assert app._results.get_nowait() == (data, [], False)


# GUI-11: unexpected worker failure.

def test_gui_worker_exception():
    app = fake_app()

    with patch.object(
        gui,
        "fetch_target_data",
        side_effect=RuntimeError("Test failure"),
    ):
        gui.IPDiagnosticApp._worker(app, "target", "example.com")

    data, warnings, failed = app._results.get_nowait()

    assert data["target"] == "example.com"
    assert data["ip"] == "Unknown"
    assert failed is True
    assert "Test failure" in warnings[0]


# GUI-12: queue processing.

def test_gui_poll_results():
    app = fake_app()
    data = {"ip": "8.8.8.8"}

    app._results.put((data, [], False))

    gui.IPDiagnosticApp._poll_results(app)

    app._update_ui.assert_called_once_with(data, [], False)
    app.after.assert_called_once_with(100, app._poll_results)


# GUI-13: return to self-diagnostic mode.

def test_gui_restore_self():
    app = fake_app()

    gui.IPDiagnosticApp.refresh_data(app)

    app.target_var.set.assert_called_once_with("")
    app._start_request.assert_called_once_with("self")


# GUI-14 and GUI-15: report content.

@pytest.mark.parametrize("mode", ["target", "self"])
def test_gui_report_content(mode):
    app = fake_app(mode)

    definitions = (
        gui.TARGET_FIELD_DEFINITIONS
        if mode == "target"
        else gui.FIELD_DEFINITIONS
    )

    app.fields = {}

    for _, key in definitions:
        widget = Mock()
        widget.cget.return_value = f"sample-{key}"
        app.fields[key] = widget

    report = gui.IPDiagnosticApp.build_report(app)

    expected_title = (
        "TARGET IP DIAGNOSTIC REPORT"
        if mode == "target"
        else "PUBLIC IP DIAGNOSTIC REPORT"
    )

    assert expected_title in report

    for _, key in definitions:
        assert f"sample-{key}" in report

    if mode == "target":
        assert "sample-ipv4" not in report
    else:
        assert "sample-target" not in report


def test_gui_report_includes_errors():
    app = fake_app()
    app._failed = True
    app._warnings = ["Invalid IP address."]

    app.fields = {}

    for _, key in gui.TARGET_FIELD_DEFINITIONS:
        widget = Mock()
        widget.cget.return_value = "Unknown"
        app.fields[key] = widget

    report = gui.IPDiagnosticApp.build_report(app)

    assert "Status: Failed" in report
    assert "Invalid IP address." in report


# GUI-16: status colors and result handling.

@pytest.mark.parametrize(
    "warnings,failed,color",
    [
        ([], False, "ok"),
        (["Metadata unavailable"], False, "warn"),
        (["Invalid IP address"], True, "error"),
    ],
)
def test_gui_status_colors(warnings, failed, color):
    app = fake_app()
    app.fields = {"ip": Mock()}

    gui.IPDiagnosticApp._update_ui(
        app, {"ip": "8.8.8.8"}, warnings, failed
    )

    app.fields["ip"].config.assert_called_once_with(
        text="8.8.8.8"
    )
    app._set_busy.assert_called_once_with(False)

    assert app._set_status.call_args.args[1] == gui.COLORS[color]
    assert app._failed == failed
    assert app._warnings == warnings


# GUI-17: control states.

@pytest.mark.parametrize(
    "busy,state",
    [(True, "disabled"), (False, "normal")],
)
def test_gui_request_control_states(busy, state):
    app = fake_app()

    gui.IPDiagnosticApp._set_busy(app, busy)

    assert app._busy == busy

    for widget in (
        app.target_entry,
        app.search_btn,
        app.refresh_btn,
        app.copy_btn,
    ):
        widget.config.assert_called_once_with(state=state)


# GUI-18: original Activity 3 palette.

def test_gui_original_palette():
    assert gui.COLORS == {
        "bg": "#F4F6F8",
        "card": "#FFFFFF",
        "border": "#D5DCE3",
        "title": "#1A2530",
        "muted": "#5A6B7C",
        "label": "#3A5A7C",
        "value": "#2A3439",
        "ok": "#1E7B3A",
        "warn": "#B26A00",
        "error": "#B3261E",
    }


# GUI-19: status footer regression tests.

@pytest.mark.parametrize(
    "message,color",
    [
        ("Querying network endpoints...", "muted"),
        ("Network details updated successfully.", "ok"),
        ("Metadata unavailable. " * 30, "warn"),
        ("Target lookup failed. " * 30, "error"),
    ],
)
def test_gui_scrollable_status(message, color):
    app = fake_app()

    gui.IPDiagnosticApp._set_status(
        app, message, gui.COLORS[color]
    )

    assert app.status_text.method_calls == [
        call.configure(
            state="normal", foreground=gui.COLORS[color]
        ),
        call.delete(
            "1.0", "end"
        ),
        call.insert(
            "1.0", message, "status"
        ),
        call.configure(
            state="disabled"
        ),
        call.yview_moveto(0),
    ]


# GUI-20: preserve complete warnings and errors in both modes.

@pytest.mark.parametrize("mode", ["self", "target"])
@pytest.mark.parametrize("failed", [False, True])
def test_gui_long_status_preserved(mode, failed):
    app = fake_app(mode)
    app.fields = {}

    warnings = [
        "Metadata provider unavailable. " * 20,
        "Secondary provider request timed out. " * 20,
    ]

    gui.IPDiagnosticApp._update_ui(
        app, {}, warnings, failed
    )

    message, color = app._set_status.call_args.args

    assert "; ".join(warnings) in message
    assert app._warnings == warnings
    assert color == gui.COLORS[
        "error" if failed else "warn"
    ]

    if failed:
        expected = (
            "Target lookup failed"
            if mode == "target"
            else "Network diagnostic failed"
        )
        assert message.startswith(expected)


# GUI-21: field wrapping during window resizing.

@pytest.mark.parametrize("width", [580, 900])
def test_gui_resize_field_wrapping(width):
    app = fake_app()
    app.fields = {"ip": Mock(), "location": Mock()}

    event = Mock()
    event.widget = app
    event.width = width

    gui.IPDiagnosticApp._on_resize(app, event)

    for field in app.fields.values():
        field.config.assert_called_once_with(
            wraplength=max(180, width - 280)
        )


# GUI-24: conditional status scrollbar.

@pytest.mark.parametrize(
    "first,last,visible,expected",
    [
        ("0.0", "1.0", False, "hidden"),
        ("0.0", "0.4", False, "show"),
        ("0.0", "1.0", True, "hide"),
        ("0.0", "0.4", True, "unchanged"),
        ("0.6", "1.0", True, "unchanged"),
    ],
)
def test_gui_conditional_status_scrollbar(
    first, last, visible, expected
):
    app = fake_app()

    app.status_scrollbar.winfo_manager.return_value = (
        "pack" if visible else ""
    )

    gui.IPDiagnosticApp._update_status_scrollbar(
        app, first, last
    )

    app.status_scrollbar.set.assert_called_once_with(
        first, last
    )

    if expected == "show":
        app.status_scrollbar.pack.assert_called_once_with(
            side="right",
            fill="y",
            before=app.status_text,
        )
        app.status_scrollbar.pack_forget.assert_not_called()

    elif expected == "hide":
        app.status_scrollbar.pack_forget.assert_called_once()
        app.status_scrollbar.pack.assert_not_called()

    else:
        app.status_scrollbar.pack.assert_not_called()
        app.status_scrollbar.pack_forget.assert_not_called()
