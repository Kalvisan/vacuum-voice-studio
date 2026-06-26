"""Remote robot control for xiaomi.vacuum.d109gl via Xiaomi cloud MIoT API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voice_cloud
from voice_cloud import XiaomiCloud, response_ok

VACUUM_SIID = 2
BATTERY_SIID = 3
IDENTIFY_SIID = 6

VACUUM_STATUS_LABELS: dict[int, str] = {
    1: "Idle",
    2: "Charging",
    3: "Break charging",
    4: "Sweeping",
    5: "Paused",
    6: "Going to dock",
    7: "Going to wash",
    8: "Remote control",
    9: "Charged",
    10: "Building map",
    11: "Updating",
    12: "Station working",
    13: "Recharging (multi-task)",
    14: "Station working",
    15: "Error",
    16: "Sweep + mop",
    17: "Mopping",
    18: "Mapping paused",
    19: "Dock break",
    20: "Wash break",
    21: "Dock + mapping",
}

MODE_LABELS: dict[int, str] = {
    1: "Silent",
    2: "Standard",
    3: "Strong",
    4: "Turbo",
}

CHARGING_LABELS: dict[int, str] = {
    1: "Charging",
    2: "Not charging",
    3: "Not chargeable",
}


@dataclass(frozen=True)
class RobotCommand:
    command_id: str
    icon: str
    label: str
    hint: str
    siid: int
    aiid: int
    args: tuple[Any, ...] = ()


@dataclass(frozen=True)
class VoiceAction:
    action_id: str
    icon: str
    label: str
    hint: str


ROBOT_COMMANDS: tuple[RobotCommand, ...] = (
    RobotCommand("start_sweep", ">", "Start clean", "Full home sweep", VACUUM_SIID, 1),
    RobotCommand("start_sweep_mop", ">+", "Sweep + mop", "Vacuum and mop", VACUUM_SIID, 6),
    RobotCommand("start_mop", "~>", "Mop only", "Mop without vacuum", VACUUM_SIID, 5),
    RobotCommand("pause", "||", "Pause", "Pause current task", VACUUM_SIID, 7),
    RobotCommand("continue", "|>", "Continue", "Resume paused task", VACUUM_SIID, 8),
    RobotCommand("stop", "#", "Stop", "Stop cleaning", VACUUM_SIID, 2),
    RobotCommand("dock", "<~", "Return home", "Stop and go to dock", VACUUM_SIID, 3),
    RobotCommand("charge", "+", "Charge", "Send robot to charge", BATTERY_SIID, 1),
    RobotCommand("identify", "?", "Locate", "Play sound on robot", IDENTIFY_SIID, 1),
)

VOICE_ACTIONS: tuple[VoiceAction, ...] = (
    VoiceAction("voice-status", "i", "Voice status", "Read pack on robot"),
    VoiceAction("install-custom", "^", "Install pack", "Upload custom voice"),
    VoiceAction("devices", "@", "Pick robots", "Choose targets"),
)

STATE_MARKERS = {
    "ready": ">>",
    "active": "**",
    "idle": "  ",
    "off": "--",
}

CLEANING_STATUSES = {4, 16, 17}
PAUSED_STATUSES = {5}
DOCKING_STATUSES = {6, 7, 13, 19, 21}
CHARGING_STATUSES = {2, 9}
IDLE_STATUSES = {1}
ERROR_STATUSES = {15}

STATUS_ICONS = {
    1: "[ ]",
    2: "[+]",
    4: "[>]",
    5: "[||]",
    6: "[<~]",
    9: "[=]",
    15: "[!]",
    16: "[>+]",
    17: "[~]",
}


def _battery_bar(level: Any, width: int = 10) -> str:
    try:
        pct = max(0, min(100, int(level)))
    except (TypeError, ValueError):
        return "[----------] --"
    filled = round(pct / 100 * width)
    return f"[{'=' * filled}{'-' * (width - filled)}] {pct}%"


def derive_command_states(snapshot: dict[str, Any]) -> dict[str, str]:
    states = {command.command_id: "idle" for command in ROBOT_COMMANDS}
    if not snapshot.get("ok"):
        return {command.command_id: "off" for command in ROBOT_COMMANDS}

    code = snapshot.get("status_code")
    if code in ERROR_STATUSES:
        states["stop"] = "ready"
        states["dock"] = "ready"
        states["identify"] = "ready"
        for command_id in ("start_sweep", "start_sweep_mop", "start_mop", "pause", "continue", "charge"):
            states[command_id] = "off"
        return states

    if code in IDLE_STATUSES:
        for command_id in ("start_sweep", "start_sweep_mop", "start_mop"):
            states[command_id] = "ready"
        for command_id in ("pause", "continue", "stop"):
            states[command_id] = "off"
        states["dock"] = "idle"
        states["charge"] = "idle"
        states["identify"] = "idle"
        return states

    if code in CLEANING_STATUSES:
        states["pause"] = "ready"
        states["stop"] = "ready"
        for command_id in ("start_sweep", "start_sweep_mop", "start_mop", "continue"):
            states[command_id] = "off"
        states["dock"] = "idle"
        states["charge"] = "idle"
        states["identify"] = "idle"
        return states

    if code in PAUSED_STATUSES:
        states["continue"] = "ready"
        states["pause"] = "active"
        states["stop"] = "ready"
        for command_id in ("start_sweep", "start_sweep_mop", "start_mop"):
            states[command_id] = "off"
        states["identify"] = "idle"
        return states

    if code in CHARGING_STATUSES | DOCKING_STATUSES:
        states["dock"] = "active"
        states["charge"] = "active"
        for command_id in ("start_sweep", "start_sweep_mop", "start_mop"):
            states[command_id] = "idle"
        for command_id in ("pause", "continue", "stop"):
            states[command_id] = "off"
        states["identify"] = "idle"
        return states

    states["identify"] = "idle"
    return states


def merge_command_states(snapshots: list[dict[str, Any]]) -> dict[str, str]:
    merged = {command.command_id: "off" for command in ROBOT_COMMANDS}
    priority = {"active": 4, "ready": 3, "idle": 2, "off": 1}
    ok_snapshots = [item for item in snapshots if item.get("ok")]
    if not ok_snapshots:
        return merged
    for snapshot in ok_snapshots:
        current = derive_command_states(snapshot)
        for command_id, state in current.items():
            if priority.get(state, 0) > priority.get(merged.get(command_id, "off"), 0):
                merged[command_id] = state
    return merged


def format_button_label(icon: str, title: str, hint: str, state: str = "idle") -> str:
    marker = STATE_MARKERS.get(state, "  ")
    return f"[{icon}] {title}\n{marker} {hint}"


def format_button_label_compact(icon: str, title: str, state: str = "idle") -> str:
    marker = STATE_MARKERS.get(state, "  ")
    return f"{marker}[{icon}] {title}"


def format_command_option_line(icon: str, title: str, hint: str, state: str = "idle") -> str:
    marker = STATE_MARKERS.get(state, "  ")
    return f"{marker} [{icon}] {title}  -  {hint}"


def format_snapshot_panel(snapshot: dict[str, Any]) -> str:
    name = str(snapshot.get("name") or snapshot.get("did") or "Robot")
    if not snapshot.get("ok"):
        return (
            "+-- ROBOT STATUS -----------------------------------+\n"
            f"| [!] {name}\n"
            f"| ERR  {snapshot.get('error', 'Unavailable')}\n"
            "+--------------------------------------------------+"
        )

    code = snapshot.get("status_code") or 0
    status_icon = STATUS_ICONS.get(code, "[*]")
    status_label = snapshot.get("status_label", "-")
    battery = _battery_bar(snapshot.get("battery"))
    mode = snapshot.get("mode_label", "-")
    area = snapshot.get("cleaning_area", "-")
    runtime = snapshot.get("cleaning_time", "-")
    voice = snapshot.get("voice") or {}
    voice_current = voice.get("current") or "-"
    voice_progress = voice.get("progress")
    voice_text = f"{voice_current}"
    if voice_progress is not None:
        voice_text += f" ({voice_progress}%)"

    return (
        "+-- ROBOT STATUS -----------------------------------+\n"
        f"| {status_icon} {name}\n"
        f"| STATE {status_label:<16} BATT {battery}\n"
        f"| MODE  {mode:<16} AREA {area}\n"
        f"| TIME  {runtime:<16} VOIC {voice_text}\n"
        "+--------------------------------------------------+"
    )


def format_snapshot_panels(snapshots: list[dict[str, Any]]) -> str:
    blocks = [format_snapshot_panel(item) for item in snapshots]
    return "\n\n".join(blocks) if blocks else "No robots configured."


def format_snapshot_line(snapshot: dict[str, Any]) -> str:
    name = str(snapshot.get("name") or snapshot.get("did") or "Robot")
    if not snapshot.get("ok"):
        return f"[!] {name}  |  {snapshot.get('error', 'Unavailable')}"

    code = snapshot.get("status_code") or 0
    status_icon = STATUS_ICONS.get(code, "[*]")
    status_label = snapshot.get("status_label", "-")
    battery = snapshot.get("battery")
    if isinstance(battery, int):
        batt_text = f"{battery}%"
    else:
        batt_text = _battery_bar(battery, width=6)
    mode = snapshot.get("mode_label", "-")
    voice = snapshot.get("voice") or {}
    voice_current = voice.get("current") or "-"
    voice_progress = voice.get("progress")
    voice_text = voice_current if voice_progress is None else f"{voice_current} {voice_progress}%"

    return (
        f"{status_icon} {name}  |  {status_label}  |  {batt_text}  |  {mode}  |  Voice {voice_text}"
    )


def format_snapshot_panels_compact(snapshots: list[dict[str, Any]]) -> str:
    if not snapshots:
        return "No robots configured."
    return "\n".join(format_snapshot_line(item) for item in snapshots)


def _prop_value(result: dict, siid: int, piid: int) -> Any:
    body = result.get("response") or {}
    items = body.get("result")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("siid") == siid and item.get("piid") == piid:
            if item.get("code", 0) != 0:
                return None
            return item.get("value")
    return None


def get_properties(api: XiaomiCloud, specs: list[tuple[int, int]]) -> dict[tuple[int, int], Any]:
    payload = {"params": [{"did": api.did, "siid": siid, "piid": piid} for siid, piid in specs]}
    result = api.post("/miotspec/prop/get", payload)
    values: dict[tuple[int, int], Any] = {}
    for siid, piid in specs:
        values[(siid, piid)] = _prop_value(result, siid, piid)
    return values


def call_robot_action(api: XiaomiCloud, siid: int, aiid: int, args: list[Any] | None = None) -> dict:
    payload = {"params": {"did": api.did, "siid": siid, "aiid": aiid, "in": args or []}}
    return api.post("/miotspec/action", payload)


def _format_duration(seconds: Any) -> str:
    try:
        total = int(seconds or 0)
    except (TypeError, ValueError):
        return "-"
    minutes, secs = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _format_area(value: Any) -> str:
    try:
        area = int(value or 0)
    except (TypeError, ValueError):
        return "-"
    if area <= 0:
        return "-"
    return f"{area / 1000000:.1f} m²" if area > 1000 else f"{area} dm²"


def fetch_robot_snapshot(config: dict[str, str]) -> dict[str, Any]:
    api = XiaomiCloud(config)
    props = get_properties(
        api,
        [
            (VACUUM_SIID, 2),
            (VACUUM_SIID, 6),
            (VACUUM_SIID, 7),
            (VACUUM_SIID, 9),
            (BATTERY_SIID, 1),
            (BATTERY_SIID, 2),
        ],
    )
    status_code = props.get((VACUUM_SIID, 2))
    try:
        status_num = int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        status_num = None
    mode_code = props.get((VACUUM_SIID, 9))
    try:
        mode_num = int(mode_code) if mode_code is not None else None
    except (TypeError, ValueError):
        mode_num = None
    battery = props.get((BATTERY_SIID, 1))
    charging = props.get((BATTERY_SIID, 2))
    try:
        charging_num = int(charging) if charging is not None else None
    except (TypeError, ValueError):
        charging_num = None

    voice: dict[str, Any] | None = None
    voice_error = ""
    try:
        voice = voice_cloud.robot_voice_status(config)
    except Exception as exc:
        voice_error = str(exc)

    return {
        "did": config.get("did"),
        "status_code": status_num,
        "status_label": VACUUM_STATUS_LABELS.get(status_num or 0, "Unknown"),
        "mode_label": MODE_LABELS.get(mode_num or 0, "-"),
        "battery": battery,
        "charging_label": CHARGING_LABELS.get(charging_num or 0, "-"),
        "cleaning_area": _format_area(props.get((VACUUM_SIID, 6))),
        "cleaning_time": _format_duration(props.get((VACUUM_SIID, 7))),
        "voice": voice,
        "voice_error": voice_error,
    }


def fetch_robot_snapshots(
    config_document: dict,
    *,
    all_enabled: bool = True,
) -> list[dict[str, Any]]:
    from voice_tool_core import iter_target_configs

    snapshots: list[dict[str, Any]] = []
    for device_config, device in iter_target_configs(config_document, all_enabled=all_enabled):
        entry: dict[str, Any] = {
            "did": device["did"],
            "name": device.get("name") or device.get("did"),
            "model": device.get("model", ""),
        }
        try:
            entry.update(fetch_robot_snapshot(device_config))
            entry["ok"] = True
        except Exception as exc:
            entry["ok"] = False
            entry["error"] = str(exc)
        snapshots.append(entry)
    return snapshots


def run_robot_command(config: dict[str, str], command_id: str) -> dict[str, Any]:
    command = next((item for item in ROBOT_COMMANDS if item.command_id == command_id), None)
    if not command:
        raise ValueError(f"Unknown robot command: {command_id}")

    api = XiaomiCloud(config)
    result = call_robot_action(api, command.siid, command.aiid, list(command.args))
    body = result.get("response") or {}
    action_code = None
    if isinstance(body.get("result"), dict):
        action_code = body["result"].get("code")
    ok = response_ok(result) and (action_code in (None, 0))
    return {
        "command_id": command_id,
        "label": command.label,
        "ok": ok,
        "http_status": result.get("http_status"),
        "code": body.get("code"),
        "action_code": action_code,
        "message": body.get("message", ""),
    }


def run_robot_command_many(
    config_document: dict,
    command_id: str,
    *,
    all_enabled: bool = True,
) -> list[dict[str, Any]]:
    from voice_tool_core import iter_target_configs

    results: list[dict[str, Any]] = []
    for device_config, device in iter_target_configs(config_document, all_enabled=all_enabled):
        entry: dict[str, Any] = {
            "did": device["did"],
            "name": device.get("name") or device.get("did"),
        }
        try:
            outcome = run_robot_command(device_config, command_id)
            entry.update(outcome)
            entry["ok"] = bool(outcome.get("ok"))
        except Exception as exc:
            entry["ok"] = False
            entry["error"] = str(exc)
        results.append(entry)
    return results
