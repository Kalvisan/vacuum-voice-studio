#!/usr/bin/env python3
"""Main Textual menu for the X20 voice tool."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Log, OptionList, Static
from textual.widgets.option_list import Option

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import voice_tool_core as core

ROOT_DIR = core.ROOT_DIR
CLI_PY = ROOT_DIR / "scripts" / "voice_tool_cli.py"
SESSION_TUI_PY = ROOT_DIR / "scripts" / "xiaomi_session_setup.py"
STUDIO_PY = ROOT_DIR / "scripts" / "voice_studio_server.py"
STUDIO_URL = "http://127.0.0.1:8765/"


def _format_studio_bar(info: dict[str, Any]) -> str:
    if info.get("running"):
        url = str(info.get("url") or STUDIO_URL)
        if info.get("managed"):
            return f"Studio: RUNNING  {url}  |  o open in browser  |  x stop server"
        return f"Studio: RUNNING  {url}  |  o open in browser  (external process)"
    return "Studio: stopped  |  press 2 to start Voice Pack Studio"


def _studio_bar_class(info: dict[str, Any]) -> str:
    return "is-running" if info.get("running") else ""

APP_CSS = """
Screen {
    background: #0d1117;
}

Header {
    background: #161b22;
    color: #e6edf3;
}

Footer {
    background: #161b22;
    color: #8b949e;
}

#layout {
    height: 1fr;
}

#dashboard {
    height: auto;
    max-height: 7;
    padding: 0 2;
    background: #161b22;
    border: solid #30363d;
    margin: 0 1 1 1;
}

#flow-hint {
    height: auto;
    padding: 0 2;
    color: #58a6ff;
    margin: 0 1;
}

#studio-bar {
    height: auto;
    padding: 0 2;
    margin: 0 1 1 1;
    border: solid #30363d;
    background: #161b22;
    color: #8b949e;
}

#studio-bar.is-running {
    border: solid #238636;
    color: #3fb950;
}

OptionList {
    height: 1fr;
    padding: 0 1;
    background: #0d1117;
    border: none;
}

OptionList > .option-list--option {
    padding: 0 1;
}

OptionList > .option-list--option-highlighted {
    background: #21262d;
    color: #e6edf3;
}

#log-panel {
    height: 9;
    margin: 1 1 0 1;
    border: solid #30363d;
    background: #010409;
}

#log-panel Log {
    height: 1fr;
    background: #010409;
    color: #8b949e;
}

.section-label {
    color: #8b949e;
    padding: 1 2 0 2;
}

RobotPanelScreen {
    background: #0d1117;
}

RobotPanelScreen #robot-layout {
    height: 1fr;
}

RobotPanelScreen #robot-status-panel {
    height: auto;
    max-height: 4;
    margin: 0 1;
    padding: 0 1;
    border: solid #30363d;
    background: #161b22;
    color: #c9d1d9;
}

RobotPanelScreen #robot-scroll {
    height: 1fr;
    margin: 0 1;
    border: none;
    background: #0d1117;
}

RobotPanelScreen #robot-command-grid {
    height: auto;
    margin: 0;
    grid-size: 3;
    grid-gutter: 0 1;
    grid-columns: 1fr 1fr 1fr;
}

RobotPanelScreen #robot-voice-grid {
    height: auto;
    margin: 1 0 0 0;
    grid-size: 3;
    grid-gutter: 0 1;
    grid-columns: 1fr 1fr 1fr;
}

RobotPanelScreen #robot-toolbar {
    height: auto;
    margin: 0 0 1 0;
    padding: 0;
    grid-size: 2;
    grid-gutter: 0 1;
    grid-columns: 1fr 1fr;
}

RobotPanelScreen .robot-btn {
    width: 100%;
    min-width: 0;
    height: auto;
    min-height: 3;
    padding: 0;
    background: #21262d;
    border: solid #30363d;
    color: #e6edf3;
    content-align: center middle;
}

RobotPanelScreen .robot-btn:hover {
    background: #30363d;
}

RobotPanelScreen .robot-btn:focus {
    border: solid #58a6ff;
}

RobotPanelScreen .robot-btn.-state-ready {
    border: solid #3fb950;
}

RobotPanelScreen .robot-btn.-state-active {
    border: solid #d29922;
    background: #3d2e00;
}

RobotPanelScreen .robot-btn.-state-off {
    opacity: 0.45;
}

RobotPanelScreen .robot-btn.-primary {
    background: #238636;
    border: solid #2ea043;
}

RobotPanelScreen .robot-btn.-primary.-state-off {
    background: #21262d;
    border: solid #30363d;
}

RobotPanelScreen .robot-btn.-warn {
    background: #9e6a03;
    border: solid #bb8009;
}

#robot-log-panel {
    height: 5;
    margin: 0 1;
    border: solid #30363d;
    background: #010409;
}

RobotPanelScreen #robot-log-panel Log {
    height: 1fr;
    background: #010409;
    color: #8b949e;
}

RobotPanelScreen #robot-busy {
    height: auto;
    padding: 0 1;
    margin: 0 1;
    color: #58a6ff;
}

HelpScreen Static {
    padding: 1 2;
}
"""

ROBOT_BTN_STATE_CLASSES = ("-state-ready", "-state-active", "-state-idle", "-state-off")


@dataclass(frozen=True)
class MenuEntry:
    item_id: str
    label: str
    hint: str = ""


GUIDED_FLOW: tuple[MenuEntry, ...] = (
    MenuEntry("download", "[1] Download base sounds", "Official Xiaomi voice pack"),
    MenuEntry("studio", "[2] Edit in Studio", "Replace MP3 files in your browser"),
    MenuEntry("build", "[3] Build voice pack", "Create install-ready ZIP"),
    MenuEntry("install", "[4] Install on robot", "Upload via Xiaomi cloud"),
)

SETUP_FLOW: tuple[MenuEntry, ...] = (
    MenuEntry("deps", "[+] Install software", "Python, curl, zip tools"),
    MenuEntry("configure", "[+] Connect Xiaomi account", "Sign in and pick your robot"),
    MenuEntry("readiness", "[?] Check setup", "See what is still missing"),
)

ADVANCED_ITEMS: tuple[MenuEntry, ...] = (
    MenuEntry("status", "[*] Voice status", "Current pack on robot(s)"),
    MenuEntry("official", "[*] Restore official pack", "Install stock Xiaomi language"),
    MenuEntry("devices", "[*] Choose robots", "Multi-robot selection"),
    MenuEntry("configure", "[*] Refresh sign-in", "Renew Xiaomi session"),
    MenuEntry("virusscan", "[*] Scan repo safety", "Check source for issues"),
    MenuEntry("readiness", "[*] Full diagnostics", "Detailed readiness report"),
    MenuEntry("deps", "[*] Re-check software", "Verify dependencies"),
)

PANEL_ITEMS: tuple[MenuEntry, ...] = (
    MenuEntry("robot", "[R] Robot control panel", "Clean, dock, charge, voice commands"),
    MenuEntry("help", "[?] Help", "Keyboard shortcuts and tips"),
    MenuEntry("advanced_toggle", "[A] Advanced menu", "Show or hide extra tools"),
)


def _flag(ok: bool) -> str:
    return "OK" if ok else "--"


def _readiness_snapshot() -> dict[str, Any]:
    state = core.readiness(include_tui=True)
    vacuums = core.get_enabled_vacuum_devices()
    robot_names = ", ".join(
        str(item.get("name") or item.get("did") or "Robot") for item in vacuums[:2]
    )
    if len(vacuums) > 2:
        robot_names += f" +{len(vacuums) - 2}"
    state["robot_label"] = robot_names or "none"
    state["vacuum_count"] = len(vacuums)
    return state


def _next_guided_step(state: dict[str, Any]) -> str | None:
    if not state.get("config_ready"):
        return "configure"
    if not state.get("base_pack_ready"):
        return "download"
    if not state.get("workspace_ready"):
        return "studio"
    if state.get("needs_build"):
        return "build"
    if not state.get("install_synced"):
        return "install"
    return None


def _guided_step_marker(step_id: str, state: dict[str, Any]) -> str:
    next_id = _next_guided_step(state)
    done = {
        "download": state.get("base_pack_ready", False),
        "studio": state.get("workspace_ready", False),
        "build": state.get("zip_ready", False),
        "install": state.get("install_synced", False),
    }.get(step_id, False)
    if step_id == next_id:
        return ">>"
    if done:
        return "OK"
    return "  "


def _format_dashboard(state: dict[str, Any]) -> str:
    install_flag = _flag(state.get("install_synced", False))
    if state.get("needs_build") and state.get("zip_exists"):
        build_flag = "rebuild"
    else:
        build_flag = _flag(state.get("zip_ready", False))
    return (
        f" Account [{_flag(state.get('config_ready', False))}]   "
        f"Base pack [{_flag(state.get('base_pack_ready', False))}]   "
        f"Custom pack [{_flag(state.get('workspace_ready', False))}]   "
        f"Built ZIP [{build_flag}]   "
        f"Installed [{install_flag}]   "
        f"Robot(s): {state.get('robot_label', 'none')}"
    )


def _format_flow_hint(state: dict[str, Any]) -> str:
    if not state.get("config_ready"):
        return ">> Start here: connect your Xiaomi account, then follow steps 1-4."
    nxt = _next_guided_step(state)
    if nxt is None:
        return "All set. Edit in Studio (2), open Robot panel (R or menu), or reinstall (4)."
    labels = {
        "download": "Step 1 - download base sounds from Xiaomi",
        "studio": "Step 2 - open Studio and replace the MP3 files you want",
        "build": "Step 3 - build your custom voice pack",
        "install": "Step 4 - install the pack on your robot",
    }
    return f">> Next: {labels.get(nxt, 'Continue the guided flow')}"


class HelpScreen(Screen):
    BINDINGS = [Binding("escape", "pop", "Back"), Binding("q", "pop", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(
            "X20 Voice Pack — quick keys\n\n"
            "Guided flow (recommended)\n"
            "  1  Download base sounds\n"
            "  2  Edit in Studio (browser)\n"
            "  3  Build voice pack\n"
            "  4  Install on robot\n\n"
            "Voice Pack Studio\n"
            "  o          Open studio in browser (when running)\n"
            "  x          Stop studio web server\n\n"
            "Navigation\n"
            "  Up/Down/Left/Right  Move in menus and robot panel grid\n"
            "  Enter      Select / run highlighted item\n"
            "  q / Ctrl+Q Exit (always)\n"
            "  a          Toggle Advanced menu\n"
            "  r          Robot control panel (clean, dock, voice)\n"
            "  ?          This help\n"
            "  Esc        Back from a screen\n\n"
            "Tips\n"
            "  - Studio saves progress automatically in workspace/packs/\n"
            "  - Use Advanced mode only when you need extra tools\n"
            "  - CLI power users: ./x20-voice-tool.sh --cli --help",
            id="help-text",
        )
        yield Footer()

    def action_pop(self) -> None:
        self.app.pop_screen()


class RobotPanelScreen(Screen):
    BINDINGS = [
        Binding("escape", "pop", "Back", priority=True),
        Binding("q", "pop", "Back", priority=True),
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("up", "focus_up", "Up", show=False, priority=True),
        Binding("down", "focus_down", "Down", show=False, priority=True),
        Binding("left", "focus_left", "Left", show=False, priority=True),
        Binding("right", "focus_right", "Right", show=False, priority=True),
        Binding("enter", "activate_focused", "Run", show=False, priority=True),
    ]

    GRID_COLUMNS = 3

    def compose(self) -> ComposeResult:
        import robot_control

        with Vertical(id="robot-layout"):
            yield Static("Loading...", id="robot-status-panel")
            yield Static("", id="robot-busy")
            with ScrollableContainer(id="robot-scroll"):
                with Grid(id="robot-toolbar"):
                    yield Button(
                        robot_control.format_button_label_compact("@", "Refresh", "ready"),
                        id="cmd-refresh",
                        classes="robot-btn",
                    )
                    yield Button(
                        robot_control.format_button_label_compact("<-", "Back", "ready"),
                        id="cmd-back",
                        classes="robot-btn",
                    )
                with Grid(id="robot-command-grid"):
                    tone_classes = {
                        "start_sweep": "-primary",
                        "start_sweep_mop": "-primary",
                        "stop": "-warn",
                        "dock": "-warn",
                    }
                    for command in robot_control.ROBOT_COMMANDS:
                        classes = "robot-btn -state-idle"
                        tone = tone_classes.get(command.command_id)
                        if tone:
                            classes += f" {tone}"
                        yield Button(
                            robot_control.format_button_label_compact(
                                command.icon,
                                command.label,
                                "idle",
                            ),
                            id=f"cmd-{command.command_id}",
                            classes=classes,
                        )
                with Grid(id="robot-voice-grid"):
                    voice_tones = {"install-custom": "-primary"}
                    for action in robot_control.VOICE_ACTIONS:
                        classes = "robot-btn -state-idle"
                        tone = voice_tones.get(action.action_id)
                        if tone:
                            classes += f" {tone}"
                        yield Button(
                            robot_control.format_button_label_compact(
                                action.icon,
                                action.label,
                                "ready",
                            ),
                            id=f"cmd-{action.action_id}",
                            classes=classes,
                        )
            with Vertical(id="robot-log-panel"):
                yield Log(id="robot-log", highlight=True, max_lines=80)
        yield Footer()

    def on_mount(self) -> None:
        self._busy = False
        self._status_text = "Loading robot status..."
        self._snapshots: list[dict[str, Any]] = []
        self.refresh_panel()
        self._focus_at(0, 0)

    def _button_grid(self) -> list[list[str]]:
        import robot_control

        command_ids = [f"cmd-{command.command_id}" for command in robot_control.ROBOT_COMMANDS]
        voice_ids = [f"cmd-{action.action_id}" for action in robot_control.VOICE_ACTIONS]
        rows = [["cmd-refresh", "cmd-back"]]
        for index in range(0, len(command_ids), self.GRID_COLUMNS):
            rows.append(command_ids[index : index + self.GRID_COLUMNS])
        rows.append(voice_ids)
        return rows

    def _focus_coords(self) -> tuple[int, int] | None:
        focused = self.focused
        if focused is None or not focused.id:
            return None
        button_id = str(focused.id)
        for row_index, row in enumerate(self._button_grid()):
            for col_index, entry_id in enumerate(row):
                if entry_id == button_id:
                    return row_index, col_index
        return None

    def _focus_at(self, row: int, col: int) -> None:
        grid = self._button_grid()
        if not grid:
            return
        row = max(0, min(row, len(grid) - 1))
        col = max(0, min(col, len(grid[row]) - 1))
        try:
            self.query_one(f"#{grid[row][col]}", Button).focus()
        except Exception:
            pass

    def action_focus_up(self) -> None:
        coords = self._focus_coords()
        if coords is None:
            self._focus_at(0, 0)
            return
        row, col = coords
        self._focus_at(row - 1, col)

    def action_focus_down(self) -> None:
        coords = self._focus_coords()
        if coords is None:
            self._focus_at(0, 0)
            return
        row, col = coords
        self._focus_at(row + 1, col)

    def action_focus_left(self) -> None:
        coords = self._focus_coords()
        if coords is None:
            self._focus_at(0, 0)
            return
        row, col = coords
        self._focus_at(row, col - 1)

    def action_focus_right(self) -> None:
        coords = self._focus_coords()
        if coords is None:
            self._focus_at(0, 0)
            return
        row, col = coords
        self._focus_at(row, col + 1)

    def action_activate_focused(self) -> None:
        focused = self.focused
        if isinstance(focused, Button) and not focused.disabled:
            focused.press()

    def action_pop(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.refresh_panel()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        busy_line = self.query_one("#robot-busy", Static)
        if busy and message:
            busy_line.update(f">> {message}")
        else:
            busy_line.update("")
        for button in self.query(Button):
            button.disabled = busy and button.id != "cmd-back"

    def _render_status(self, text: str) -> None:
        self._status_text = text
        self.query_one("#robot-status-panel", Static).update(text)

    def _log(self, message: str) -> None:
        self.query_one("#robot-log", Log).write_line(message)

    def _ui(self, callback, *args, **kwargs) -> None:
        self.app.call_from_thread(callback, *args, **kwargs)

    @work(thread=True)
    def refresh_panel(self) -> None:
        self._ui(self._set_busy, True, "Refreshing robot status...")
        snapshots: list[dict[str, Any]] = []
        try:
            document = core.load_config_document()
            import robot_control

            snapshots = robot_control.fetch_robot_snapshots(document, all_enabled=True)
            text = robot_control.format_snapshot_panels_compact(snapshots)
        except Exception as exc:
            text = f"[!] Robot status error  |  {exc}"

        self._ui(self._apply_status, text, snapshots)

    def _apply_button_state(self, button: Button, label: str, state: str) -> None:
        for css_class in ROBOT_BTN_STATE_CLASSES:
            button.remove_class(css_class)
        button.add_class(f"-state-{state}")
        button.label = label

    def _update_button_states(self, snapshots: list[dict[str, Any]]) -> None:
        import robot_control

        states = robot_control.merge_command_states(snapshots)
        for command in robot_control.ROBOT_COMMANDS:
            try:
                button = self.query_one(f"#cmd-{command.command_id}", Button)
            except Exception:
                continue
            state = states.get(command.command_id, "idle")
            self._apply_button_state(
                button,
                robot_control.format_button_label_compact(command.icon, command.label, state),
                state,
            )

    def _apply_status(self, text: str, snapshots: list[dict[str, Any]]) -> None:
        self._snapshots = snapshots
        self._render_status(text)
        self._update_button_states(snapshots)
        self._set_busy(False, "")

    def _schedule_refresh(self) -> None:
        self.refresh_panel()

    @on(Button.Pressed, "#cmd-refresh")
    def refresh_pressed(self, _event: Button.Pressed) -> None:
        self.refresh_panel()

    @on(Button.Pressed, "#cmd-back")
    def back_pressed(self, _event: Button.Pressed) -> None:
        self.action_pop()

    @on(Button.Pressed, "#robot-command-grid Button")
    def command_pressed(self, event: Button.Pressed) -> None:
        if self._busy:
            return
        command_id = str(event.button.id or "").removeprefix("cmd-")
        if command_id:
            self.run_robot_command(command_id)

    @on(Button.Pressed, "#robot-voice-grid Button")
    def voice_pressed(self, event: Button.Pressed) -> None:
        if self._busy:
            return
        self._run_voice_action(str(event.button.id or ""))

    def _run_voice_action(self, button_id: str) -> None:
        app = self.app
        if not isinstance(app, VoiceToolApp):
            return
        if button_id == "cmd-devices":
            self._log("Opening robot picker...")
            app.run_session_setup("devices")
            self.refresh_panel()
            return
        if button_id == "cmd-voice-status":
            self._run_cli_to_log(["status", "--all-devices"])
            return
        if button_id == "cmd-install-custom":
            self._run_cli_to_log(["install", "--all-devices"])

    @work(thread=True)
    def _run_cli_to_log(self, command: list[str]) -> None:
        self._ui(self._log, f"> {' '.join(command)}")
        process = subprocess.Popen(
            [sys.executable, str(CLI_PY), *command],
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            stripped = line.rstrip()
            if not stripped:
                continue
            if stripped.startswith("{"):
                try:
                    payload = json.loads(stripped)
                    if payload.get("ok") and payload.get("data"):
                        pretty = json.dumps(payload["data"], ensure_ascii=False, indent=2)
                        for pretty_line in pretty.splitlines():
                            self._ui(self._log, pretty_line)
                        continue
                except json.JSONDecodeError:
                    pass
            self._ui(self._log, stripped)
        code = process.wait()
        if code == 0:
            self._ui(self._log, "Done.")
        else:
            self._ui(self._log, f"Failed (exit {code}).")
        self._ui(self._schedule_refresh)

    @work(thread=True)
    def run_robot_command(self, command_id: str) -> None:
        import robot_control

        self._ui(self._set_busy, True, f"Running: {command_id}...")
        self._ui(self._log, f"> {command_id}")
        try:
            document = core.load_config_document()
            results = robot_control.run_robot_command_many(document, command_id, all_enabled=True)
            for item in results:
                name = item.get("name") or item.get("did")
                if item.get("ok"):
                    self._ui(self._log, f"  {name}: OK")
                else:
                    detail = item.get("error") or item.get("message") or item.get("action_code")
                    self._ui(self._log, f"  {name}: failed - {detail}")
        except Exception as exc:
            self._ui(self._log, f"  ERROR: {exc}")
        self._ui(self._log, "Done.")
        self._ui(self._schedule_refresh)


class VoiceToolApp(App):
    CSS = APP_CSS
    TITLE = "X20 Voice Pack"
    SUB_TITLE = "Open source · your account · official cloud"

    BINDINGS = [
        Binding("q", "quit_app", "Exit", priority=True),
        Binding("ctrl+q", "quit_app", "Exit", show=False, priority=True),
        Binding("a", "toggle_advanced", "Advanced", priority=True),
        Binding("r", "open_robot_panel", "Robot", priority=True),
        Binding("question_mark", "open_help", "Help", priority=True),
        Binding("1", "run_step(1)", "Step 1", priority=True, show=False),
        Binding("2", "run_step(2)", "Step 2", priority=True, show=False),
        Binding("3", "run_step(3)", "Step 3", priority=True, show=False),
        Binding("4", "run_step(4)", "Step 4", priority=True, show=False),
        Binding("o", "open_studio_browser", "Open Studio", priority=True, show=False),
        Binding("x", "stop_studio", "Stop Studio", priority=True, show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.startup_done = False
        self.session_state = core.SESSION_STATE_NO_FILE
        self.advanced_mode = False
        self._state: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="layout"):
            yield Static("", id="dashboard")
            yield Static("", id="flow-hint")
            yield Static(_format_studio_bar({"running": False}), id="studio-bar")
            yield Label("GUIDED FLOW", classes="section-label", id="guided-label")
            yield OptionList(id="main-menu")
            with Vertical(id="log-panel"):
                yield Log(id="output-log", highlight=True, max_lines=200)
        yield Footer()

    def on_mount(self) -> None:
        self.log_line("Welcome. Press ? for help, q to exit.")
        self.set_interval(2.0, self.update_studio_bar)
        self.bootstrap_startup()

    def studio_info(self) -> dict[str, Any]:
        from voice_studio_server import studio_runtime_info

        return studio_runtime_info()

    def update_studio_bar(self) -> None:
        try:
            bar = self.query_one("#studio-bar", Static)
        except Exception:
            return
        info = self.studio_info()
        bar.update(_format_studio_bar(info))
        bar.remove_class("is-running")
        css_class = _studio_bar_class(info)
        if css_class:
            bar.add_class(css_class)

    def log_line(self, message: str) -> None:
        self.query_one("#output-log", Log).write_line(message)

    @work(thread=True)
    def bootstrap_startup(self) -> None:
        try:
            result = core.resolve_startup_session(test_connection=True)
        except Exception as exc:
            self.call_from_thread(self.log_line, f"Startup error: {exc}")
            self.call_from_thread(self.finish_startup, core.SESSION_STATE_INVALID, None)
            return
        self.call_from_thread(self.finish_startup, str(result.get("state", "")), result)

    def finish_startup(self, state: str, result: dict | None) -> None:
        self.session_state = state
        self.startup_done = True

        if not result:
            self.log_line("Could not determine session state.")
            self.call_later(self.refresh_menu)
            return

        message = str(result.get("message") or "")
        if message:
            self.log_line(message)

        vacuums = result.get("vacuums") or []
        if vacuums:
            self.log_line(f"Robots configured: {len(vacuums)}")

        test_error = str(result.get("error") or result.get("robot_error") or "")
        if test_error:
            self.log_line(f"Note: {test_error}")

        action = str(result.get("action") or "")
        if action == "first_run":
            self.log_line("Opening sign-in helper…")
            self.run_session_setup("first_run")
            return
        if action == "relogin":
            self.log_line("Session expired — sign in again…")
            self.run_session_setup("relogin")
            return

        if state == core.SESSION_STATE_VALID:
            self.log_line("Connected. Use keys 1-4 for the guided flow.")
        self.call_later(self.refresh_menu)

    async def refresh_menu(self) -> None:
        self._state = _readiness_snapshot()
        self.query_one("#dashboard", Static).update(_format_dashboard(self._state))
        self.query_one("#flow-hint", Static).update(_format_flow_hint(self._state))

        guided_label = self.query_one("#guided-label", Label)
        if self._state.get("config_ready"):
            guided_label.update("GUIDED FLOW")
        else:
            guided_label.update("SETUP - connect first")

        option_list = self.query_one("#main-menu", OptionList)
        option_list.clear_options()

        if not self._state.get("config_ready"):
            for entry in SETUP_FLOW:
                prefix = ">> " if entry.item_id == "configure" else "   "
                option_list.add_option(
                    Option(f"{prefix}{entry.label}  - {entry.hint}", id=f"menu-{entry.item_id}")
                )
        else:
            for entry in GUIDED_FLOW:
                marker = _guided_step_marker(entry.item_id, self._state)
                prefix = ">> " if marker == ">>" else ("OK " if marker == "OK" else "   ")
                option_list.add_option(
                    Option(f"{prefix}{entry.label}  - {entry.hint}", id=f"menu-{entry.item_id}")
                )

            option_list.add_option(Option("--- Panels ---", id="menu-separator-panels", disabled=True))
            for entry in PANEL_ITEMS:
                if entry.item_id == "advanced_toggle":
                    state_label = "ON" if self.advanced_mode else "OFF"
                    label = f"   {entry.label} ({state_label})  - {entry.hint}"
                else:
                    label = f"   {entry.label}  - {entry.hint}"
                option_list.add_option(Option(label, id=f"menu-{entry.item_id}"))

            if self.advanced_mode:
                option_list.add_option(Option("--- Advanced ---", id="menu-separator", disabled=True))
                for entry in ADVANCED_ITEMS:
                    option_list.add_option(
                        Option(f"   {entry.label}  - {entry.hint}", id=f"menu-{entry.item_id}")
                    )

        option_list.add_option(Option("   [Q] Exit", id="menu-quit"))
        option_list.focus()
        self.update_studio_bar()

    def schedule_refresh_menu(self) -> None:
        self.call_later(self.refresh_menu)

    def action_quit_app(self) -> None:
        if self.studio_info().get("running"):
            self.stop_studio(silent=True)
        self.log_line("Goodbye.")
        self.exit(0)

    def action_open_studio_browser(self) -> None:
        info = self.studio_info()
        if not info.get("running"):
            self.log_line("Studio is not running. Press 2 to start it.")
            return
        url = str(info.get("url") or STUDIO_URL)
        webbrowser.open(url)
        self.log_line(f"Opened {url}")

    def action_stop_studio(self) -> None:
        self.stop_studio()

    def stop_studio(self, *, silent: bool = False) -> None:
        from voice_studio_server import stop_studio_server

        info = self.studio_info()
        if not info.get("running"):
            if not silent:
                self.log_line("Studio is not running.")
            self.update_studio_bar()
            return
        if not info.get("managed"):
            if not silent:
                self.log_line("Studio was started outside this TUI. Stop that process manually.")
            self.update_studio_bar()
            return
        result = stop_studio_server()
        if not silent:
            if result.get("stopped"):
                self.log_line(f"Studio stopped ({result.get('url', STUDIO_URL)}).")
            elif result.get("was_running") and not result.get("managed", True):
                self.log_line("Studio port is in use by another process. Stop it manually.")
            else:
                self.log_line("Could not confirm studio shutdown.")
        self.update_studio_bar()
        self.schedule_refresh_menu()

    def action_toggle_advanced(self) -> None:
        if not core.config_ready():
            self.log_line("Complete setup first, then Advanced mode unlocks.")
            return
        self.advanced_mode = not self.advanced_mode
        self.log_line("Advanced mode ON." if self.advanced_mode else "Advanced mode OFF.")
        self.schedule_refresh_menu()

    def action_open_robot_panel(self) -> None:
        if not core.config_ready():
            self.log_line("Connect your Xiaomi account first (setup).")
            return
        self.push_screen(RobotPanelScreen())

    def action_open_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_run_step(self, step: int) -> None:
        mapping = {1: "download", 2: "studio", 3: "build", 4: "install"}
        item_id = mapping.get(step)
        if item_id:
            self.dispatch_action(item_id)

    @on(OptionList.OptionSelected, "#main-menu")
    def menu_selected(self, event: OptionList.OptionSelected) -> None:
        raw_id = str(event.option_id or "")
        if raw_id in {"menu-separator", "menu-separator-panels"}:
            return
        item_id = raw_id.removeprefix("menu-")
        if item_id == "quit":
            self.action_quit_app()
            return
        self.dispatch_action(item_id)

    def dispatch_action(self, item_id: str) -> None:
        if item_id == "robot":
            self.action_open_robot_panel()
            return
        if item_id == "help":
            self.action_open_help()
            return
        if item_id == "advanced_toggle":
            self.action_toggle_advanced()
            return
        if item_id == "configure":
            self.run_session_setup("relogin")
            return
        if item_id == "devices":
            self.run_session_setup("devices")
            return
        if item_id == "studio":
            self.run_studio()
            return

        command_map: dict[str, list[str]] = {
            "deps": ["deps"],
            "readiness": ["readiness"],
            "download": ["download", "--language", "en"],
            "status": ["status", "--all-devices"],
            "build": ["build"],
            "install": ["install", "--all-devices"],
            "official": ["official", "--language", "en"],
            "virusscan": ["virusscan"],
        }
        command = command_map.get(item_id)
        if command:
            self.run_cli_command(item_id, command)

    @work(thread=True)
    def run_studio(self) -> None:
        from voice_studio_server import studio_runtime_info

        info = studio_runtime_info()
        if info.get("running"):
            url = str(info.get("url") or STUDIO_URL)
            webbrowser.open(url)
            self.call_from_thread(self.log_line, f"Studio already running: {url}")
            self.call_from_thread(self.update_studio_bar)
            return

        self.call_from_thread(self.log_line, "Starting Voice Pack Studio...")
        try:
            proc = subprocess.Popen(
                [sys.executable, str(STUDIO_PY), "--no-open"],
                cwd=str(ROOT_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            self.call_from_thread(self.log_line, f"ERROR: {exc}")
            return

        url = STUDIO_URL
        for _ in range(30):
            info = studio_runtime_info()
            if info.get("running"):
                url = str(info.get("url") or STUDIO_URL)
                break
            if proc.poll() is not None:
                self.call_from_thread(self.log_line, "Studio process exited before the server was ready.")
                self.call_from_thread(self.update_studio_bar)
                return
            time.sleep(0.2)

        webbrowser.open(url)
        self.call_from_thread(self.log_line, f"Studio: {url}")
        self.call_from_thread(self.log_line, "Press x to stop the studio server when you are done.")
        self.call_from_thread(self.update_studio_bar)

    def run_session_setup(self, mode: str = "manual") -> None:
        self.log_line(f"Opening Xiaomi sign-in ({mode})…")
        env = os.environ.copy()
        env["X20_SESSION_MODE"] = mode
        env["X20_NESTED_SESSION"] = "1"
        with self.suspend():
            result = subprocess.run(
                [sys.executable, str(SESSION_TUI_PY)],
                cwd=str(ROOT_DIR),
                env=env,
            )
        if result.returncode == 0:
            self.log_line("Sign-in finished.")
            startup = core.resolve_startup_session(test_connection=True)
            self.session_state = str(startup.get("state") or "")
        else:
            self.log_line("Sign-in closed with an error.")
        self.schedule_refresh_menu()

    @work(thread=True)
    def run_cli_command(self, item_id: str, command: list[str]) -> None:
        self.call_from_thread(self.log_line, f"> {' '.join(command)}")
        process = subprocess.Popen(
            [sys.executable, str(CLI_PY), *command],
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            stripped = line.rstrip()
            if not stripped:
                continue
            if stripped.startswith("{") and item_id in {"readiness", "status", "virusscan"}:
                try:
                    payload = json.loads(stripped)
                    if payload.get("ok") and payload.get("data"):
                        pretty = json.dumps(payload["data"], ensure_ascii=False, indent=2)
                        for pretty_line in pretty.splitlines():
                            self.call_from_thread(self.log_line, pretty_line)
                        continue
                except json.JSONDecodeError:
                    pass
            self.call_from_thread(self.log_line, stripped)
        code = process.wait()
        if code == 0:
            self.call_from_thread(self.log_line, f"Done ({item_id}).")
        else:
            self.call_from_thread(self.log_line, f"Failed ({item_id}, code {code}).")
        self.call_from_thread(self.schedule_refresh_menu)


def main() -> int:
    from terminal_restore import restore_terminal

    code = 0
    try:
        VoiceToolApp().run()
    except KeyboardInterrupt:
        code = 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        code = 1
    finally:
        restore_terminal()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
