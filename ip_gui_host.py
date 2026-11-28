"""BL-11 GUI host controlled by the tray launcher.

Run by ip_tray.py, not normally launched directly.
Closing the window hides it; the tray can restore or exit it.
"""

import queue
import sys
import threading

from ip_diagnostic_gui import IPDiagnosticApp


def read_commands(commands):
    """Read tray commands without touching Tkinter from this thread."""
    try:
        for line in sys.stdin:
            command = line.strip().lower()
            if command in {"show", "hide", "quit"}:
                commands.put(command)
    finally:
        # Close the GUI if its controlling tray process disconnects.
        commands.put("quit")


def main():
    commands = queue.Queue()
    app = IPDiagnosticApp()

    def hide_window():
        app.withdraw()

    def show_window():
        app.deiconify()
        app.lift()

    def poll_commands():
        try:
            while True:
                command = commands.get_nowait()

                if command == "quit":
                    app._on_close()
                    return
                if command == "show":
                    show_window()
                elif command == "hide":
                    hide_window()

        except queue.Empty:
            pass

        if not app._closing:
            app.after(100, poll_commands)

    # The red close button hides the window instead of quitting.
    app.protocol("WM_DELETE_WINDOW", hide_window)

    threading.Thread(
        target=read_commands,
        args=(commands,),
        name="tray-command-reader",
        daemon=True,
    ).start()

    app.after(100, poll_commands)
    app.mainloop()


if __name__ == "__main__":
    main()