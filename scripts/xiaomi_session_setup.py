#!/usr/bin/env python3
"""Interactive Xiaomi session setup for the X20 voice tool."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

from textual.binding import Binding
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Log, Static

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from xiaomi_cloud_login import (  # noqa: E402
    ACCOUNT_LOGIN_URL,
    DEFAULT_ACCESS_KEY,
    HOME_MI_URL,
    DeviceInfo,
    LoginResult,
    PasswordLogin,
    QrLogin,
    build_config_with_devices,
    connector_from_login,
    discover_vacuum_robots,
)

import voice_tool_core as core  # noqa: E402

CONFIG_FILE = core.CONFIG_FILE
CONNECTION_FILE = core.CONNECTION_FILE

KEYBOARD_HINT = "Up/Down move  |  Enter select  |  Tab next field  |  Esc back  |  q quit"


class FirstRunScreen(Screen):
    BINDINGS = [Binding("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(
            "Welcome. This is your first run.\n\n"
            "This tool needs a Xiaomi account session token to talk to your robot(s).\n"
            "We will help you sign in, list your Xiaomi Home devices, and pick your vacuum robot(s).\n\n"
            f"{KEYBOARD_HINT}\n\n"
            "Recommended: QR code login with the Xiaomi Home app.",
            id="intro",
        )
        yield ListView(
            ListItem(Label("Start Xiaomi login"), id="start-login"),
            id="nav-list",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#nav-list", ListView).focus()

    @on(ListView.Selected, "#nav-list")
    def start_login(self, _event: ListView.Selected) -> None:
        self.app.pop_screen()
        self.app.push_screen(MethodScreen())

    def action_quit(self) -> None:
        self.app.exit(1)


class ReloginScreen(Screen):
    BINDINGS = [Binding("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(
            "Your saved Xiaomi session expired or no longer works.\n\n"
            "Sign in again to refresh the token. Your local audio workspace is kept.\n"
            "After login you can re-select one or more vacuum robots.\n\n"
            f"{KEYBOARD_HINT}",
            id="intro",
        )
        yield ListView(
            ListItem(Label("Sign in again"), id="start-login"),
            id="nav-list",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#nav-list", ListView).focus()

    @on(ListView.Selected, "#nav-list")
    def start_login(self, _event: ListView.Selected) -> None:
        self.app.pop_screen()
        self.app.push_screen(MethodScreen())

    def action_quit(self) -> None:
        self.app.exit(1)


class MethodScreen(Screen):
    BINDINGS = [Binding("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(
            "Connect your Xiaomi account to this tool.\n"
            "Pick one login method below. QR code login is the easiest option.\n\n"
            f"{KEYBOARD_HINT}",
            id="intro",
        )
        yield ListView(
            ListItem(Label("QR code login (recommended)"), id="method-qr"),
            ListItem(Label("Email and password login"), id="method-password"),
            ListItem(Label("Paste cookies from browser (advanced)"), id="method-browser"),
            id="method-list",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#method-list", ListView).focus()

    @on(ListView.Selected, "#method-list")
    def method_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id == "method-qr":
            self.app.push_screen(QrScreen())
        elif item_id == "method-password":
            self.app.push_screen(PasswordScreen())
        elif item_id == "method-browser":
            self.app.push_screen(BrowserScreen())

    def action_quit(self) -> None:
        self.app.exit(1)


class QrScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(
            "Step 1: Open the login page on your phone or computer.\n"
            "Step 2: Scan the QR code in the Xiaomi Home app or browser.\n"
            "Step 3: Confirm the login on your phone.\n\n"
            f"{KEYBOARD_HINT}",
            id="qr-help",
        )
        yield ListView(
            ListItem(Label("Open login page in browser"), id="open-login"),
            ListItem(Label("Open QR image file"), id="open-qr"),
            ListItem(Label("Start waiting for login"), id="start-qr"),
            id="nav-list",
        )
        yield Static("Status: ready", id="qr-status")
        yield Log(id="qr-log", highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        self.qr_session = QrLogin()
        self.qr_image_path: Path | None = None
        self.qr_ready_flag = False
        self.waiting_for_qr = False
        self.query_one("#nav-list", ListView).focus()
        self.query_one("#qr-log", Log).write_line("Preparing QR login...")
        self.prepare_qr()

    @work(thread=True)
    def prepare_qr(self) -> None:
        try:
            self.qr_session.prepare()
            qr_bytes = self.qr_session.fetch_qr_bytes()
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            temp_file.write(qr_bytes)
            temp_file.close()
            self.qr_image_path = Path(temp_file.name)
            self.app.call_from_thread(self.qr_ready)
        except Exception as exc:
            self.app.call_from_thread(self.qr_failed, str(exc))

    def qr_ready(self) -> None:
        self.qr_ready_flag = True
        log = self.query_one("#qr-log", Log)
        log.write_line("QR code is ready.")
        if self.qr_session.login_url:
            log.write_line(f"Login URL: {self.qr_session.login_url}")
        if self.qr_image_path:
            log.write_line(f"QR image file: {self.qr_image_path}")
        self.query_one("#qr-status", Static).update("Status: QR ready. Open the page and scan the code.")
        self.query_one("#nav-list", ListView).focus()

    def qr_failed(self, message: str) -> None:
        self.query_one("#qr-log", Log).write_line(f"ERROR: {message}")
        self.query_one("#qr-status", Static).update("Status: failed to prepare QR login")

    @on(ListView.Selected, "#nav-list")
    def nav_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id == "open-login":
            self.open_login()
        elif item_id == "open-qr":
            self.open_qr()
        elif item_id == "start-qr":
            self.start_qr()

    def open_login(self) -> None:
        url = self.qr_session.login_url or ACCOUNT_LOGIN_URL
        webbrowser.open(url)
        self.query_one("#qr-log", Log).write_line(f"Opened browser: {url}")

    def open_qr(self) -> None:
        if not self.qr_image_path:
            self.query_one("#qr-log", Log).write_line("QR image is not ready yet.")
            return
        if sys.platform == "darwin":
            subprocess.run(["open", str(self.qr_image_path)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(self.qr_image_path)], check=False)
        else:
            os.startfile(str(self.qr_image_path))  # type: ignore[attr-defined]
        self.query_one("#qr-log", Log).write_line(f"Opened QR image: {self.qr_image_path}")

    def start_qr(self) -> None:
        if not self.qr_ready_flag:
            self.query_one("#qr-log", Log).write_line("Wait until the QR code is ready.")
            return
        self.waiting_for_qr = True
        self.wait_for_qr()

    @work(thread=True)
    def wait_for_qr(self) -> None:
        try:
            self.qr_session.wait_for_scan(
                on_tick=lambda message: self.app.call_from_thread(self.update_qr_status, message)
            )
            self.app.call_from_thread(self.login_success, self.qr_session.login_result("de"))
        except Exception as exc:
            self.app.call_from_thread(self.qr_wait_failed, str(exc))

    def update_qr_status(self, message: str) -> None:
        self.query_one("#qr-status", Static).update(f"Status: {message}")
        self.query_one("#qr-log", Log).write_line(message)

    def qr_wait_failed(self, message: str) -> None:
        self.waiting_for_qr = False
        self.query_one("#qr-status", Static).update("Status: login failed or timed out")
        self.query_one("#qr-log", Log).write_line(f"ERROR: {message}")

    def login_success(self, login: LoginResult) -> None:
        self.waiting_for_qr = False
        self.app.login_result = login
        self.app.pop_screen()
        self.app.push_screen(DeviceScreen())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit(1)


class PasswordScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(
            "Sign in with your Xiaomi account email or phone number.\n\n"
            f"{KEYBOARD_HINT}",
            id="password-help",
        )
        yield Input(placeholder="Email or phone number", id="username")
        yield Input(placeholder="Password", password=True, id="password")
        yield ListView(
            ListItem(Label("Sign in"), id="password-login"),
            id="nav-list",
        )
        yield Log(id="password-log", highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        self.logging_in = False
        self.query_one("#username", Input).focus()

    @on(Input.Submitted, "#password")
    @on(Input.Submitted, "#username")
    def input_submitted(self, _event: Input.Submitted) -> None:
        self.login()

    @on(ListView.Selected, "#nav-list")
    def nav_selected(self, _event: ListView.Selected) -> None:
        self.login()

    def login(self) -> None:
        username = self.query_one("#username", Input).value.strip()
        password = self.query_one("#password", Input).value
        if not username or not password:
            self.query_one("#password-log", Log).write_line("Enter both username and password.")
            return
        self.logging_in = True
        self.run_password_login(username, password)

    @work(thread=True)
    def run_password_login(self, username: str, password: str) -> None:
        log = self.query_one("#password-log", Log)
        try:
            self.app.call_from_thread(log.write_line, "Signing in...")
            session = PasswordLogin()
            session.login(username, password)
            login = session.login_result("de")
            self.app.call_from_thread(self.finish_password_login, login)
        except Exception as exc:
            self.app.call_from_thread(self.password_failed, str(exc))

    def finish_password_login(self, login: LoginResult) -> None:
        self.app.login_result = login
        self.app.pop_screen()
        self.app.push_screen(DeviceScreen())

    def password_failed(self, message: str) -> None:
        self.logging_in = False
        self.query_one("#password-log", Log).write_line(f"ERROR: {message}")

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit(1)


class BrowserScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield ScrollableContainer(
            Static(
                "Advanced browser login\n\n"
                "1. Open the Xiaomi login page.\n"
                "2. Sign in to your Xiaomi account.\n"
                "3. Open browser DevTools -> Application -> Cookies.\n"
                "4. Copy userId, serviceToken, and ssecurity.\n"
                "5. Tab to the fields below and paste them.\n"
                "6. Select 'Use pasted cookies'.\n\n"
                f"{KEYBOARD_HINT}",
                id="browser-help",
            ),
            ListView(
                ListItem(Label("Open Xiaomi login page"), id="open-account"),
                ListItem(Label("Open Xiaomi Home web"), id="open-home"),
                ListItem(Label("Use pasted cookies"), id="use-cookies"),
                id="nav-list",
            ),
            Input(placeholder="userId", id="cookie-user-id"),
            Input(placeholder="serviceToken", id="cookie-service-token", password=True),
            Input(placeholder="ssecurity", id="cookie-ssecurity", password=True),
            Log(id="browser-log", highlight=True),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#nav-list", ListView).focus()

    @on(ListView.Selected, "#nav-list")
    def nav_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id == "open-account":
            self.open_account()
        elif item_id == "open-home":
            self.open_home()
        elif item_id == "use-cookies":
            self.use_cookies()

    def open_account(self) -> None:
        webbrowser.open(ACCOUNT_LOGIN_URL)
        self.query_one("#browser-log", Log).write_line(f"Opened browser: {ACCOUNT_LOGIN_URL}")

    def open_home(self) -> None:
        webbrowser.open(HOME_MI_URL)
        self.query_one("#browser-log", Log).write_line(f"Opened browser: {HOME_MI_URL}")

    def use_cookies(self) -> None:
        values = {
            "userId": self.query_one("#cookie-user-id", Input).value.strip(),
            "serviceToken": self.query_one("#cookie-service-token", Input).value.strip(),
            "ssecurity": self.query_one("#cookie-ssecurity", Input).value.strip(),
        }
        missing = [key for key, value in values.items() if not value]
        if missing:
            self.query_one("#browser-log", Log).write_line(
                f"Missing values: {', '.join(missing)}"
            )
            return
        login = LoginResult(
            user_id=values["userId"],
            ssecurity=values["ssecurity"],
            service_token=values["serviceToken"],
            region="de",
        )
        self.app.login_result = login
        self.app.pop_screen()
        self.app.push_screen(DeviceScreen())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit(1)


class DeviceScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("space", "toggle", "Toggle"),
        Binding("s", "save", "Save"),
        Binding("r", "rescan", "Rescan"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(
            "Scanning Xiaomi cloud for vacuum robots in all regions.\n"
            "Select robot(s), then Save. Empty regions are skipped automatically.\n\n"
            f"{KEYBOARD_HINT}  |  Space toggle robot  |  s save  |  r rescan",
            id="device-help",
        )
        yield Static("Status: preparing scan", id="device-status")
        yield ListView(id="device-list")
        yield ListView(
            ListItem(Label("Rescan robots"), id="action-rescan"),
            ListItem(Label("Save and return"), id="action-save"),
            id="action-list",
        )
        yield Log(id="device-log", highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        self.devices: list[DeviceInfo] = []
        self.selected_dids: set[str] = set()
        self.device_labels: dict[str, str] = {}
        self.scanning = False
        saved = core.get_enabled_vacuum_devices()
        if saved:
            self.selected_dids = {str(item["did"]) for item in saved}
        if getattr(self.app, "login_result", None) is not None:
            self.call_later(self.start_scan)

    def device_label(self, device: DeviceInfo, selected: bool) -> str:
        mark = "[x]" if selected else "[ ]"
        return f"{mark} {device.name} | {device.model} | {device.region} | DID {device.did}"

    def start_scan(self) -> None:
        if self.scanning:
            return
        self.scanning = True
        self._set_save_enabled(False)
        self.query_one("#device-status", Static).update("Status: scanning all regions...")
        self.query_one("#device-list", ListView).clear()
        self.scan_all_regions()

    def _set_save_enabled(self, enabled: bool) -> None:
        action_list = self.query_one("#action-list", ListView)
        for item in action_list.children:
            if getattr(item, "id", None) == "action-save":
                item.disabled = not enabled

    @on(ListView.Selected, "#action-list")
    def action_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id == "action-rescan":
            self.start_scan()
        elif item_id == "action-save":
            self.continue_device()

    def action_rescan(self) -> None:
        self.start_scan()

    def action_save(self) -> None:
        self.continue_device()

    @work(thread=True)
    def scan_all_regions(self) -> None:
        log = self.query_one("#device-log", Log)

        def progress(message: str) -> None:
            self.app.call_from_thread(log.write_line, message)
            self.app.call_from_thread(
                self.query_one("#device-status", Static).update,
                f"Status: {message}",
            )

        try:
            connector = connector_from_login(self.app.login_result)
            devices = discover_vacuum_robots(connector, on_progress=progress)
            self.app.call_from_thread(self.show_devices, devices)
        except Exception as exc:
            self.app.call_from_thread(self.scan_failed, str(exc))

    def show_devices(self, devices: list[DeviceInfo]) -> None:
        self.scanning = False
        self.devices = devices
        device_list = self.query_one("#device-list", ListView)
        device_list.clear()

        if not devices:
            self.query_one("#device-status", Static).update("Status: no vacuum robots found on this account")
            self.query_one("#device-log", Log).write_line(
                "No robots found. Check that your robot is online in Xiaomi Home, then rescan."
            )
            self._set_save_enabled(False)
            return

        known_dids = {device.did for device in devices}
        self.selected_dids = {did for did in self.selected_dids if did in known_dids}
        if not self.selected_dids and len(devices) == 1:
            self.selected_dids.add(devices[0].did)

        regions = sorted({device.region for device in devices})
        self.app.login_result.region = regions[0] if len(regions) == 1 else devices[0].region

        self.device_labels = {}
        for device in devices:
            selected = device.did in self.selected_dids
            label = self.device_label(device, selected)
            self.device_labels[device.did] = label
            device_list.append(ListItem(Label(label), id=f"device-{device.did}"))

        selected_count = len(self.selected_dids)
        self.query_one("#device-status", Static).update(
            f"Status: found {len(devices)} robot(s) in {', '.join(regions)}"
        )
        self.query_one("#device-log", Log).write_line(
            f"Found {len(devices)} robot(s). Selected: {selected_count}."
        )
        self._set_save_enabled(selected_count > 0)
        device_list.focus()

    def scan_failed(self, message: str) -> None:
        self.scanning = False
        self.query_one("#device-status", Static).update("Status: scan failed")
        self.query_one("#device-log", Log).write_line(f"ERROR: {message}")
        self._set_save_enabled(False)

    @on(ListView.Selected, "#device-list")
    def device_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if not item_id.startswith("device-"):
            return
        did = item_id.removeprefix("device-")
        if did in self.selected_dids:
            self.selected_dids.remove(did)
        else:
            self.selected_dids.add(did)
        selected = did in self.selected_dids
        device = next((entry for entry in self.devices if entry.did == did), None)
        if device is not None:
            label = self.device_label(device, selected)
            self.device_labels[did] = label
            event.item.query_one(Label).update(label)
        self.query_one("#device-log", Log).write_line(
            f"{'Selected' if selected else 'Deselected'} DID: {did}. Total selected: {len(self.selected_dids)}"
        )
        self._set_save_enabled(len(self.selected_dids) > 0)

    def action_toggle(self) -> None:
        device_list = self.query_one("#device-list", ListView)
        if device_list.highlighted_child is not None:
            device_list.action_select_cursor()

    def continue_device(self) -> None:
        if self.scanning:
            return
        if not self.selected_dids:
            self.query_one("#device-log", Log).write_line("Select at least one robot first.")
            return
        selected = [device for device in self.devices if device.did in self.selected_dids]
        if not selected:
            self.query_one("#device-log", Log).write_line("Selected robots are missing from the scan results.")
            return
        self._set_save_enabled(False)
        self.query_one("#action-list", ListView).disabled = True
        self.app.login_result.region = selected[0].region
        config_doc = build_config_with_devices(self.app.login_result, selected, DEFAULT_ACCESS_KEY)
        self.save_session(config_doc)

    @work(thread=True)
    def save_session(self, config_doc: dict) -> None:
        import voice_cloud

        log = self.query_one("#device-log", Log)
        try:
            self.app.call_from_thread(log.write_line, "Saving session...")
            self.app.call_from_thread(
                self.query_one("#device-status", Static).update,
                "Status: saving and testing connection",
            )
            core.save_config_document(config_doc, CONFIG_FILE)
            core.mark_config_verified()
            base = core.normalize_config(config_doc)
            for device in config_doc.get("vacuum_devices") or []:
                did = str(device.get("did", ""))
                region = str(device.get("region") or config_doc.get("region") or "")
                self.app.call_from_thread(log.write_line, f"Testing DID {did} ({region})...")
                try:
                    status = voice_cloud.robot_voice_status(core.config_for_did(base, did, region))
                    self.app.call_from_thread(
                        log.write_line,
                        f"DID {did}: current={status.get('current')} progress={status.get('progress')}",
                    )
                except Exception as exc:
                    self.app.call_from_thread(
                        log.write_line,
                        f"Saved, but voice status test failed for DID {did}: {exc}",
                    )
            self.app.call_from_thread(self.save_done, config_doc)
        except Exception as exc:
            self.app.call_from_thread(self.save_failed, str(exc))

    def save_done(self, config: dict) -> None:
        log = self.query_one("#device-log", Log)
        log.write_line(f"Session saved to {CONFIG_FILE}")
        for device in config.get("vacuum_devices") or []:
            log.write_line(
                f"Robot: {device.get('name', '')} | {device.get('model', '')} | "
                f"{device.get('region', '')} | DID {device.get('did', '')}"
            )
        log.write_line("Returning to main menu...")
        self.app.exit(0)

    def save_failed(self, message: str) -> None:
        self.query_one("#action-list", ListView).disabled = False
        self._set_save_enabled(len(self.selected_dids) > 0)
        self.query_one("#device-status", Static).update("Status: save failed")
        self.query_one("#device-log", Log).write_line(f"ERROR: {message}")

    def action_back(self) -> None:
        if self.scanning:
            return
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit(1)


class XiaomiSessionApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #intro, #qr-help, #password-help, #browser-help, #device-help {
        padding: 1 2;
    }

    #method-list, #device-list, #nav-list, #action-list {
        height: 1fr;
        margin: 1 2;
        border: solid green;
    }

    #action-list {
        height: auto;
        max-height: 5;
    }

    #qr-log, #password-log, #browser-log, #device-log {
        height: 10;
        margin: 1 2;
        border: solid cyan;
    }

    Input {
        margin: 0 2;
    }
    """

    BINDINGS = [Binding("q", "quit", "Quit")]

    TITLE = "Xiaomi Session Setup"
    SUB_TITLE = "X20 Voice Pack Tool"

    def __init__(self) -> None:
        super().__init__()
        self.login_result: LoginResult | None = None

    def on_mount(self) -> None:
        mode = os.environ.get("X20_SESSION_MODE", "manual").strip().lower()
        if mode == "first_run":
            self.push_screen(FirstRunScreen())
        elif mode == "relogin":
            self.push_screen(ReloginScreen())
        elif mode == "devices":
            self.open_device_manager()
        else:
            self.push_screen(MethodScreen())

    def open_device_manager(self) -> None:
        try:
            config = core.load_config()
            self.login_result = LoginResult(
                user_id=config["userId"],
                ssecurity=config["ssecurity"],
                service_token=config["serviceToken"],
                region=config["region"],
            )
            self.push_screen(DeviceScreen())
        except Exception:
            self.push_screen(ReloginScreen())

    def action_quit(self) -> None:
        self.exit(1)


def main() -> int:
    from terminal_restore import restore_terminal

    nested = os.environ.get("X20_NESTED_SESSION") == "1"
    code = 0
    try:
        XiaomiSessionApp().run()
    except KeyboardInterrupt:
        code = 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        code = 1
    finally:
        if not nested:
            restore_terminal()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
