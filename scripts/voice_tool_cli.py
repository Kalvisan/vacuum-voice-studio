#!/usr/bin/env python3
"""Non-interactive CLI for the X20 voice tool. Use with --cli from x20-voice-tool.sh."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Callable

if "--json" in sys.argv:
    import warnings

    warnings.filterwarnings("ignore", module="urllib3")

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import voice_tool_core as core
import voice_cloud
import voice_pack_manager as vpm
import robot_control
from xiaomi_cloud_login import (
    DEFAULT_ACCESS_KEY,
    DeviceInfo,
    LoginResult,
    PasswordLogin,
    QrLogin,
    build_config_with_devices,
    connector_from_login,
    discover_devices,
    discover_devices_all_regions,
    discover_vacuum_robots,
    find_vacuum_devices,
)


class CliError(Exception):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def emit(
    ok: bool,
    command: str,
    *,
    json_mode: bool,
    data: dict[str, Any] | None = None,
    error: str = "",
    hint: str = "",
) -> None:
    if json_mode:
        payload = {"ok": ok, "command": command}
        if data is not None:
            payload["data"] = data
        if error:
            payload["error"] = error
        if hint:
            payload["hint"] = hint
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if ok:
        print(f"OK {command}")
        if data:
            for key, value in data.items():
                print(f"  {key}: {value}")
    else:
        print(f"ERROR {command}: {error}", file=sys.stderr)
        if hint:
            print(f"HINT: {hint}", file=sys.stderr)


def require_config_ready() -> None:
    state = core.readiness()
    if not state["config_ready"]:
        raise CliError(
            "Xiaomi session is not configured or not verified.",
            "Run: ./x20-voice-tool.sh --cli configure --help",
        )


def pick_devices(
    devices: list[DeviceInfo],
    did: str,
    dids: list[str],
    auto_vacuum: bool,
    all_vacuums: bool,
) -> list[DeviceInfo]:
    vacuums = find_vacuum_devices(devices)
    candidates = vacuums or devices
    if not candidates:
        raise CliError("No devices found in this region.", "Check region and account access.")

    if all_vacuums:
        if not vacuums:
            raise CliError("No vacuum robots found on this account.", "Check region and device list.")
        return vacuums

    requested = [item.strip() for item in dids if item.strip()]
    if did:
        requested.append(did.strip())
    if requested:
        selected: list[DeviceInfo] = []
        known = {item.did: item for item in candidates}
        for target in requested:
            device = known.get(target)
            if device is None:
                raise CliError(
                    f"No device with DID {target} found.",
                    "Run: ./x20-voice-tool.sh --cli devices list --all-regions --json",
                )
            selected.append(device)
        return selected

    if auto_vacuum and len(candidates) == 1:
        return [candidates[0]]
    if len(candidates) == 1:
        return [candidates[0]]

    lines = [f"{item.did} | {item.name} | {item.model} | {item.region}" for item in candidates]
    raise CliError(
        "Multiple devices found. Pass --did, --dids, or --all-vacuums.",
        "Available devices:\n  " + "\n  ".join(lines),
    )


def resolve_devices_for_configure(
    connector: Any,
    region: str,
    did: str,
    dids: list[str],
    auto_did: bool,
    all_vacuums: bool,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> list[DeviceInfo]:
    if all_vacuums:
        devices = discover_vacuum_robots(connector, on_progress=on_progress)
        return pick_devices(devices, did, dids, auto_did, all_vacuums=True)

    requested = [item.strip() for item in dids if item.strip()]
    if did:
        requested.append(did.strip())
    if requested:
        devices = discover_devices_all_regions(connector, on_progress=on_progress)
        return pick_devices(devices, did, dids, auto_did, all_vacuums=False)

    devices = discover_devices(connector, region)
    return pick_devices(devices, did, dids, auto_did, all_vacuums=False)


def login_with_password(username: str, password: str, region: str) -> LoginResult:
    session = PasswordLogin()
    session.login(username, password)
    return session.login_result(region)


def login_with_cookies(user_id: str, service_token: str, ssecurity: str, region: str) -> LoginResult:
    return LoginResult(
        user_id=user_id,
        ssecurity=ssecurity,
        service_token=service_token,
        region=region,
    )


def configure_and_save(
    login: LoginResult,
    did: str,
    dids: list[str],
    region: str,
    access_key: str,
    auto_did: bool,
    all_vacuums: bool,
    skip_test: bool,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    connector = connector_from_login(login)
    selected = resolve_devices_for_configure(
        connector,
        region,
        did,
        dids,
        auto_did,
        all_vacuums,
        on_progress=on_progress,
    )
    config_doc = build_config_with_devices(login, selected, access_key)
    config_doc["region"] = selected[0].region
    core.save_config_document(config_doc)

    test_results: list[dict[str, Any]] = []
    test_ok = skip_test
    if not skip_test:
        base = core.normalize_config(config_doc)
        for device in selected:
            device_config = core.config_for_did(base, device.did)
            entry: dict[str, Any] = {
                "did": device.did,
                "name": device.name,
                "model": device.model,
            }
            try:
                entry["voice_status"] = voice_cloud.robot_voice_status(device_config)
                entry["ok"] = True
                test_ok = True
            except Exception as exc:
                entry["ok"] = False
                entry["error"] = str(exc)
            test_results.append(entry)
        if test_ok:
            core.mark_config_verified()
    else:
        core.mark_config_verified()

    return {
        "config_path": str(core.CONFIG_FILE),
        "did": selected[0].did,
        "device_name": selected[0].name,
        "device_model": selected[0].model,
        "devices": [
            {"did": item.did, "name": item.name, "model": item.model, "region": item.region, "enabled": True}
            for item in selected
        ],
        "region": selected[0].region,
        "test_ok": test_ok,
        "test_results": test_results,
    }


def cmd_virusscan(args: argparse.Namespace) -> int:
    scan_py = SCRIPT_DIR / "repo_virusscan.py"
    cmd = [sys.executable, str(scan_py)]
    if args.clamav:
        cmd.append("--clamav")
    if args.json:
        cmd.append("--json")
        proc = subprocess.run(cmd, cwd=str(core.ROOT_DIR), capture_output=True, text=True)
        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else {"ok": False}
        except json.JSONDecodeError:
            data = {"ok": False, "raw_output": proc.stdout}
        if proc.returncode != 0:
            emit(False, "virusscan", json_mode=True, data=data, error="Repository scan failed.")
            return 1
        emit(True, "virusscan", json_mode=True, data=data)
        return 0

    proc = subprocess.run(cmd, cwd=str(core.ROOT_DIR))
    if proc.returncode != 0:
        raise CliError("Repository virusscan found blocking issues.")
    return 0


def cmd_readiness(args: argparse.Namespace) -> int:
    if not args.skip_bootstrap:
        bootstrap = core.ensure_local_session(test_connection=not args.skip_validate)
    else:
        bootstrap = {"skipped": True}
    state = core.readiness(include_tui=not args.no_tui)
    state["session_bootstrap"] = bootstrap
    emit(True, "readiness", json_mode=args.json, data=state)
    if bootstrap.get("state") == core.SESSION_STATE_EXPIRED and args.require_valid:
        raise CliError(
            "Saved Xiaomi session expired.",
            "Run ./x20-voice-tool.sh and sign in again, or use configure --method ...",
        )
    return 0


def cmd_deps(args: argparse.Namespace) -> int:
    if not core.shell_tools_available():
        raise CliError("Missing shell tools.", "Install python3, curl, unzip, and zip.")
    if not core.python_deps_available(include_tui=not args.no_tui):
        core.install_python_deps(include_tui=not args.no_tui)
    emit(
        True,
        "deps",
        json_mode=args.json,
        data={"python_deps": core.python_deps_available(include_tui=not args.no_tui)},
    )
    return 0


def cmd_configure(args: argparse.Namespace) -> int:
    core.ensure_dirs()

    if args.use_existing:
        result = core.ensure_local_session(test_connection=not args.skip_test)
        emit(True, "configure", json_mode=args.json, data=result)
        if not result.get("config_ready"):
            raise CliError(
                "No usable saved session was found.",
                "Run configure with --method cookies/password/qr once, or use --from-file.",
            )
        return 0

    if args.from_file:
        source = Path(args.from_file)
        document = core.load_config_document(source)
        core.save_config_document(document)
        config = core.normalize_config(document)
        result: dict[str, Any] = {"config_path": str(core.CONFIG_FILE), "source": str(source)}
        if not args.skip_test:
            statuses = voice_cloud.robot_voice_status_many(document, all_enabled=True)
            result["devices"] = statuses
            result["verified"] = any(item.get("ok") for item in statuses)
            if result["verified"]:
                core.mark_config_verified()
        else:
            core.mark_config_verified()
            result["verified"] = True
        emit(True, "configure", json_mode=args.json, data=result)
        return 0

    method = args.method
    region = args.region or core.DEFAULT_REGION
    access_key = args.access_key or DEFAULT_ACCESS_KEY

    expanded_dids: list[str] = []
    for value in args.dids or []:
        expanded_dids.extend(part.strip() for part in value.split(",") if part.strip())

    if method == "password":
        username = args.username or os.environ.get("XIAOMI_USERNAME", "")
        password = args.password or os.environ.get("XIAOMI_PASSWORD", "")
        if not username or not password:
            raise CliError(
                "Password login needs --username and --password.",
                "Or set XIAOMI_USERNAME and XIAOMI_PASSWORD environment variables.",
            )
        login = login_with_password(username, password, region)
    elif method == "cookies":
        user_id = args.user_id or os.environ.get("XIAOMI_USER_ID", "")
        service_token = args.service_token or os.environ.get("XIAOMI_SERVICE_TOKEN", "")
        ssecurity = args.ssecurity or os.environ.get("XIAOMI_SSECURITY", "")
        if not user_id or not service_token or not ssecurity:
            raise CliError(
                "Cookie login needs --user-id, --service-token, and --ssecurity.",
                "Or set XIAOMI_USER_ID, XIAOMI_SERVICE_TOKEN, and XIAOMI_SSECURITY.",
            )
        login = login_with_cookies(user_id, service_token, ssecurity, region)
    elif method == "qr":
        qr = QrLogin()
        qr.prepare()
        qr_file = Path(tempfile.gettempdir()) / "xiaomi_x20_qr.png"
        qr_file.write_bytes(qr.fetch_qr_bytes())
        info = {
            "login_url": qr.login_url,
            "qr_image": str(qr_file),
            "timeout_seconds": qr.timeout_seconds,
        }
        if not args.json:
            print("QR login URLs:")
            print(f"  login_url: {qr.login_url}")
            print(f"  qr_image: {qr_file}")
            print("Scan the QR code in Xiaomi Home, then wait...")
        if args.open_browser and qr.login_url:
            webbrowser.open(qr.login_url)
        if args.open_browser:
            if sys.platform == "darwin":
                subprocess.run(["open", str(qr_file)], check=False)
            elif sys.platform.startswith("linux"):
                subprocess.run(["xdg-open", str(qr_file)], check=False)

        def tick(message: str) -> None:
            if not args.json:
                print(message)

        qr.wait_for_scan(on_tick=tick if not args.json else None)
        login = qr.login_result(region)

        def progress(message: str) -> None:
            if not args.json:
                print(message)

        result = configure_and_save(
            login,
            args.did or "",
            expanded_dids,
            region,
            access_key,
            args.auto_did,
            args.all_vacuums,
            args.skip_test,
            on_progress=progress if (args.all_vacuums or expanded_dids or args.did) else None,
        )
        result["qr"] = info
        emit(True, "configure", json_mode=args.json, data=result)
        return 0
    else:
        raise CliError(f"Unknown configure method: {method}")

    def progress(message: str) -> None:
        if not args.json:
            print(message)

    result = configure_and_save(
        login,
        args.did or "",
        expanded_dids,
        region,
        access_key,
        args.auto_did,
        args.all_vacuums,
        args.skip_test,
        on_progress=progress if (args.all_vacuums or expanded_dids or args.did) else None,
    )
    emit(True, "configure", json_mode=args.json, data=result)
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    if args.from_config:
        require_config_ready()
        config = core.load_config()
        login = LoginResult(
            user_id=config["userId"],
            ssecurity=config["ssecurity"],
            service_token=config["serviceToken"],
            region=config["region"],
        )
    else:
        region = args.region or core.DEFAULT_REGION
        method = args.method
        if method == "password":
            username = args.username or os.environ.get("XIAOMI_USERNAME", "")
            password = args.password or os.environ.get("XIAOMI_PASSWORD", "")
            if not username or not password:
                raise CliError("Need username and password, or use --from-config.")
            login = login_with_password(username, password, region)
        elif method == "cookies":
            user_id = args.user_id or os.environ.get("XIAOMI_USER_ID", "")
            service_token = args.service_token or os.environ.get("XIAOMI_SERVICE_TOKEN", "")
            ssecurity = args.ssecurity or os.environ.get("XIAOMI_SSECURITY", "")
            if not user_id or not service_token or not ssecurity:
                raise CliError("Need cookie values, or use --from-config.")
            login = login_with_cookies(user_id, service_token, ssecurity, region)
        else:
            raise CliError("devices list needs --from-config or a login method.")

    region = args.region or login.region
    connector = connector_from_login(login)

    if args.all_regions:
        def progress(message: str) -> None:
            if not args.json:
                print(message)

        if args.vacuums_only:
            devices = discover_vacuum_robots(connector, on_progress=progress if not args.json else None)
            scan_mode = "all_regions_vacuums"
        else:
            devices = discover_devices_all_regions(connector, on_progress=progress if not args.json else None)
            scan_mode = "all_regions"
        regions_scanned = list({item.region for item in devices})
    else:
        devices = discover_devices(connector, region)
        if args.vacuums_only:
            devices = find_vacuum_devices(devices)
            scan_mode = "single_region_vacuums"
        else:
            scan_mode = "single_region"
        regions_scanned = [region]

    payload = [
        {"did": item.did, "name": item.name, "model": item.model, "region": item.region}
        for item in devices
    ]
    emit(
        True,
        "devices",
        json_mode=args.json,
        data={"region": region, "regions_scanned": regions_scanned, "scan_mode": scan_mode, "devices": payload},
    )
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    require_config_ready()
    language = (args.language or core.DEFAULT_BASE_LANGUAGE).strip().lower()
    result = core.download_base_pack(language, reset_working=not args.keep_working)
    emit(True, "download", json_mode=args.json, data=result)
    return 0


def cmd_languages(args: argparse.Namespace) -> int:
    from voice_catalog import fetch_voice_catalog

    languages = fetch_voice_catalog(force_refresh=args.refresh)
    meta = core.load_base_pack_meta()
    emit(
        True,
        "languages",
        json_mode=args.json,
        data={
            "languages": languages,
            "current": meta.get("language") if meta else None,
            "base_pack_ready": core.base_pack_ready(),
        },
    )
    return 0


def cmd_studio(args: argparse.Namespace) -> int:
    if args.stop:
        from voice_studio_server import stop_studio_server

        result = stop_studio_server()
        emit(True, "studio", json_mode=args.json, data=result)
        return 0

    vpm.ensure_layout()

    studio_py = SCRIPT_DIR / "voice_studio_server.py"
    url = f"http://{args.host}:{args.port}/"

    if args.background:
        proc = subprocess.Popen(
            [sys.executable, str(studio_py), "--host", args.host, "--port", str(args.port), "--no-open"],
            cwd=str(core.ROOT_DIR),
        )
        if not args.no_open:
            webbrowser.open(url)
        emit(
            True,
            "studio",
            json_mode=args.json,
            data={"url": url, "pid": proc.pid, "background": True},
        )
        return 0

    from voice_studio_server import run_server

    run_server(host=args.host, port=args.port, open_browser=not args.no_open)
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    if args.pack_command == "list":
        packs = vpm.list_packs()
        emit(True, "pack", json_mode=args.json, data={"packs": packs, "active": vpm.get_active_pack_id()})
        return 0
    if args.pack_command == "create":
        name = args.name.strip()
        if not name:
            raise CliError("Pack name is required.", "Example: --cli pack create --name 'My Russian voice'")
        pack = vpm.create_pack(name, language=args.language or core.load_base_pack_meta().get("language") or "en")
        emit(True, "pack", json_mode=args.json, data={"pack": pack})
        return 0
    raise CliError(f"Unknown pack subcommand: {args.pack_command}")


def cmd_robot(args: argparse.Namespace) -> int:
    require_config_ready()
    document = core.load_config_document()

    if args.robot_command == "commands":
        commands = [
            {"command_id": item.command_id, "label": item.label, "hint": item.hint}
            for item in robot_control.ROBOT_COMMANDS
        ]
        emit(True, "robot", json_mode=args.json, data={"commands": commands})
        return 0

    if args.robot_command == "snapshot":
        if args.all_devices:
            snapshots = robot_control.fetch_robot_snapshots(document, all_enabled=True)
        else:
            base = core.load_config()
            if args.did:
                base = core.config_for_did(base, args.did)
            snapshot = robot_control.fetch_robot_snapshot(base)
            snapshots = [
                {
                    "did": args.did or base.get("did", ""),
                    "ok": True,
                    **snapshot,
                }
            ]
        emit(True, "robot", json_mode=args.json, data={"snapshots": snapshots})
        return 0

    if args.robot_command == "run":
        command_id = args.command_id.strip()
        known = {item.command_id for item in robot_control.ROBOT_COMMANDS}
        if command_id not in known:
            raise CliError(
                f"Unknown robot command: {command_id}",
                "Run: ./x20-voice-tool.sh --cli robot commands list --json",
            )

        if args.all_devices:
            results = robot_control.run_robot_command_many(document, command_id, all_enabled=True)
            failed = [item for item in results if not item.get("ok")]
            if failed:
                raise CliError(
                    f"Command failed on {len(failed)} robot(s).",
                    "; ".join(f"{item.get('did')}: {item.get('error') or item.get('message')}" for item in failed),
                )
            emit(True, "robot", json_mode=args.json, data={"command_id": command_id, "devices": results})
            return 0

        base = core.load_config()
        if args.did:
            base = core.config_for_did(base, args.did)
        result = robot_control.run_robot_command(base, command_id)
        if not result.get("ok"):
            raise CliError(
                result.get("message") or f"Robot rejected command {command_id}.",
                "Check robot online status and try robot snapshot --json.",
            )
        emit(True, "robot", json_mode=args.json, data=result)
        return 0

    raise CliError(f"Unknown robot subcommand: {args.robot_command}")


def cmd_status(args: argparse.Namespace) -> int:
    require_config_ready()
    document = core.load_config_document()
    if args.all_devices:
        payload = voice_cloud.robot_voice_status_many(document, all_enabled=True)
        emit(True, "status", json_mode=args.json, data={"devices": payload})
        return 0

    config = core.load_config()
    if args.did:
        config = core.config_for_did(config, args.did)
    status = voice_cloud.robot_voice_status(config)
    emit(True, "status", json_mode=args.json, data=status)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    if not vpm.get_active_pack_id():
        raise CliError(
            "No voice pack to build.",
            "Create one in Voice Pack Studio: ./x20-voice-tool.sh --cli studio",
        )
    prep = vpm.prepare_for_build()

    output = Path(args.output) if args.output else None
    result = core.build_zip(
        output_path=output,
        write_language_alias=not args.no_lang_alias,
    )
    result["pack_id"] = prep.get("pack_id")
    result["pack_name"] = prep.get("pack_name")
    result["replaced_count"] = prep.get("replaced_count")
    core.save_build_state(
        pack_id=str(prep.get("pack_id") or ""),
        zip_md5=str(result.get("md5") or ""),
        replaced_count=int(prep.get("replaced_count") or 0),
    )
    core.clear_install_state()
    emit(True, "build", json_mode=args.json, data=result)
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    require_config_ready()
    if vpm.get_active_pack_id():
        vpm.prepare_for_build()

    archive = Path(args.archive) if args.archive else core.OUTPUT_DIR / "custom_voice_101.zip"
    try:
        language = core.resolve_install_language(args.language)
    except ValueError as exc:
        raise CliError(str(exc), "Example: ./x20-voice-tool.sh --cli install --language ru --json")
    suffix = args.suffix or f"{language}.zip"
    wait_seconds = args.wait_seconds

    def on_update(status: dict | None) -> None:
        if status and not args.json:
            print(f"Voice status: {status}")

    config = core.load_config()
    document = core.load_config_document()
    if args.all_devices:
        payload = voice_cloud.install_custom_archive_many(
            document,
            archive,
            language,
            suffix,
            wait_seconds,
            all_enabled=True,
            on_update=on_update,
        )
        failed = [item for item in payload if not item.get("ok")]
        if failed:
            raise CliError(
                f"Install failed on {len(failed)} robot(s).",
                "; ".join(f"{item.get('did')}: {item.get('error')}" for item in failed),
            )
        zip_md5 = core.build_zip_md5(archive)
        pack_id = vpm.get_active_pack_id() or ""
        if zip_md5 and pack_id:
            core.save_install_state(pack_id=pack_id, zip_md5=zip_md5, language=language)
        emit(True, "install", json_mode=args.json, data={"devices": payload})
        return 0

    if args.did:
        config = core.config_for_did(config, args.did)
    result = voice_cloud.install_custom_archive(
        config,
        archive,
        language,
        suffix,
        wait_seconds,
        on_update=on_update,
    )
    zip_md5 = core.build_zip_md5(archive)
    pack_id = vpm.get_active_pack_id() or ""
    if zip_md5 and pack_id:
        core.save_install_state(pack_id=pack_id, zip_md5=zip_md5, language=language)
    emit(True, "install", json_mode=args.json, data=result)
    return 0


def cmd_official(args: argparse.Namespace) -> int:
    require_config_ready()
    from voice_catalog import download_url, get_voice_entry

    language = args.language.strip().lower()
    entry = get_voice_entry(language)
    relative = entry["url"].lstrip("/")
    url = download_url(entry["url"])
    archive = core.WORKSPACE_DIR / f"official_{core.DEFAULT_MODEL}_{language}.zip"

    subprocess.run(
        ["curl", "-fL", "--retry", "3", "--connect-timeout", "20", "-o", str(archive), url],
        check=True,
    )
    md5 = entry["md5"]
    size = len(archive.read_bytes())

    def on_update(status: dict | None) -> None:
        if status and not args.json:
            print(f"Voice status: {status}")

    config = core.load_config()
    result = voice_cloud.install_official_language(
        config,
        language,
        relative,
        md5,
        size,
        args.wait_seconds,
        on_update=on_update,
    )
    result["archive"] = str(archive)
    result["url"] = url
    emit(True, "official", json_mode=args.json, data=result)
    return 0


def cmd_run_pipeline(args: argparse.Namespace) -> int:
    steps: list[tuple[str, Callable[[argparse.Namespace], int]]] = [
        ("deps", cmd_deps),
        ("configure", cmd_configure),
        ("download", cmd_download),
        ("build", cmd_build),
        ("install", cmd_install),
    ]

    if args.skip_configure:
        steps = [step for step in steps if step[0] != "configure"]
    if args.skip_download:
        steps = [step for step in steps if step[0] != "download"]

    results: dict[str, Any] = {}
    for name, handler in steps:
        if not args.json:
            print(f"Pipeline step: {name}")
        code = handler(args)
        results[name] = {"ok": code == 0}
        if code != 0:
            emit(False, "run", json_mode=args.json, data=results, error=f"Step failed: {name}")
            return code

    emit(True, "run", json_mode=args.json, data=results)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="x20-voice-tool",
        description="Xiaomi X20 voice pack tool (CLI mode). Voice pack flow, robot control, and session setup.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("virusscan", help="Scan repository source for suspicious code and secrets.")
    p.add_argument("--clamav", action="store_true", help="Also run ClamAV if installed.")
    p.set_defaults(handler=cmd_virusscan)

    p = sub.add_parser("readiness", help="Show dependency, config, workspace, and ZIP status.")
    p.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="Do not inspect or validate the saved session before reporting readiness.",
    )
    p.add_argument(
        "--skip-validate",
        action="store_true",
        help="Load saved session metadata without live Xiaomi API validation.",
    )
    p.add_argument(
        "--require-valid",
        action="store_true",
        help="Exit with error if the saved session is missing or expired.",
    )
    p.set_defaults(handler=cmd_readiness)

    p = sub.add_parser("deps", help="Install or verify Python and shell dependencies.")
    p.set_defaults(handler=cmd_deps)

    p = sub.add_parser("configure", help="Save and verify Xiaomi cloud session config.")
    p.add_argument(
        "--method",
        choices=["password", "cookies", "qr"],
        default="cookies",
        help="Login method. cookies is best for AI agents with pasted session values.",
    )
    p.add_argument("--from-file", help="Import an existing config JSON file.")
    p.add_argument(
        "--use-existing",
        action="store_true",
        help="Validate and reuse config/config.json without a new login.",
    )
    p.add_argument("--region", default=core.DEFAULT_REGION)
    p.add_argument("--did", help="Robot DID. Required if multiple devices exist.")
    p.add_argument(
        "--dids",
        action="append",
        help="Additional robot DID. Repeat or use comma-separated values.",
    )
    p.add_argument("--all-vacuums", action="store_true", help="Save all vacuum robots (scans all Xiaomi cloud regions).")
    p.add_argument("--auto-did", action="store_true", help="Pick the only vacuum/device automatically.")
    p.add_argument("--access-key", default=DEFAULT_ACCESS_KEY)
    p.add_argument("--username")
    p.add_argument("--password")
    p.add_argument("--user-id")
    p.add_argument("--service-token")
    p.add_argument("--ssecurity")
    p.add_argument("--skip-test", action="store_true", help="Save config without live robot status test.")
    p.add_argument("--open-browser", action="store_true", help="For QR login, open browser and QR image.")
    p.set_defaults(handler=cmd_configure)

    p = sub.add_parser("devices", help="List robots on your Xiaomi account.")
    devices_sub = p.add_subparsers(dest="devices_command", required=True)
    p_list = devices_sub.add_parser("list", help="List devices for one region or all regions.")
    p_list.add_argument("--region", default=core.DEFAULT_REGION)
    p_list.add_argument(
        "--all-regions",
        action="store_true",
        help="Scan all Xiaomi cloud regions (matches TUI robot discovery).",
    )
    p_list.add_argument(
        "--vacuums-only",
        action="store_true",
        help="With --all-regions, return vacuum robots only.",
    )
    p_list.add_argument("--from-config", action="store_true", help="Use saved config.json credentials.")
    p_list.add_argument("--method", choices=["password", "cookies"], default="cookies")
    p_list.add_argument("--username")
    p_list.add_argument("--password")
    p_list.add_argument("--user-id")
    p_list.add_argument("--service-token")
    p_list.add_argument("--ssecurity")
    p_list.set_defaults(handler=cmd_devices)

    p = sub.add_parser("download", help="Download official base voice pack from Xiaomi.")
    p.add_argument(
        "--language",
        default=core.DEFAULT_BASE_LANGUAGE,
        help="Language code from Xiaomi catalog (default: en).",
    )
    p.add_argument(
        "--keep-working",
        action="store_true",
        help="Do not reset workspace/working_pack when downloading.",
    )
    p.set_defaults(handler=cmd_download)

    p = sub.add_parser("languages", help="List voice pack languages available from Xiaomi.")
    lang_sub = p.add_subparsers(dest="languages_command", required=True)
    p_lang_list = lang_sub.add_parser("list", help="List available language codes and URLs.")
    p_lang_list.add_argument("--refresh", action="store_true", help="Refresh catalog from Xiaomi.")
    p_lang_list.set_defaults(handler=cmd_languages)

    p = sub.add_parser("studio", help="Open Voice Pack Studio web editor (drag-and-drop).")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-open", action="store_true", help="Do not open a browser window.")
    p.add_argument("--background", action="store_true", help="Start server in background and return.")
    p.add_argument("--stop", action="store_true", help="Stop a background Studio server started with --background.")
    p.set_defaults(handler=cmd_studio)

    p = sub.add_parser("pack", help="Manage saved voice pack projects.")
    pack_sub = p.add_subparsers(dest="pack_command", required=True)
    p_pack_list = pack_sub.add_parser("list", help="List saved voice packs.")
    p_pack_list.set_defaults(handler=cmd_pack)
    p_pack_create = pack_sub.add_parser("create", help="Create a new voice pack project.")
    p_pack_create.add_argument("--name", required=True)
    p_pack_create.add_argument("--language", help="Xiaomi install language code (e.g. ru, en).")
    p_pack_create.set_defaults(handler=cmd_pack)

    p = sub.add_parser("robot", help="Robot control panel actions (clean, dock, charge, locate).")
    robot_sub = p.add_subparsers(dest="robot_command", required=True)
    p_robot_cmds = robot_sub.add_parser("commands", help="List available robot commands.")
    robot_cmds_sub = p_robot_cmds.add_subparsers(dest="robot_commands_command", required=True)
    p_robot_cmds_list = robot_cmds_sub.add_parser("list", help="Show command IDs for robot run.")
    p_robot_cmds_list.set_defaults(handler=cmd_robot)
    p_robot_snapshot = robot_sub.add_parser("snapshot", help="Read live robot status (battery, task, voice).")
    p_robot_snapshot.add_argument("--did", help="Query one robot DID instead of the primary DID.")
    p_robot_snapshot.add_argument("--all-devices", action="store_true", help="Query all enabled vacuum robots.")
    p_robot_snapshot.set_defaults(handler=cmd_robot)
    p_robot_run = robot_sub.add_parser("run", help="Send a MIoT action to the robot.")
    p_robot_run.add_argument(
        "command_id",
        help="Command ID from 'robot commands list' (e.g. start_sweep, dock, identify).",
    )
    p_robot_run.add_argument("--did", help="Run on one robot DID only.")
    p_robot_run.add_argument("--all-devices", action="store_true", help="Run on all enabled vacuum robots.")
    p_robot_run.set_defaults(handler=cmd_robot)

    p = sub.add_parser("status", help="Show current robot voice status.")
    p.add_argument("--did", help="Query one robot DID instead of the primary DID.")
    p.add_argument("--all-devices", action="store_true", help="Query all enabled vacuum robots.")
    p.set_defaults(handler=cmd_status)

    p = sub.add_parser("build", help="Build custom voice ZIP from the active studio pack.")
    p.add_argument("--output", help="Output ZIP path. Default: output/custom_voice_101.zip")
    p.add_argument("--no-lang-alias", action="store_true", help="Do not also write output/<language>.zip")
    p.set_defaults(handler=cmd_build)

    p = sub.add_parser("install", help="Upload and install a custom voice ZIP on the robot.")
    p.add_argument("--archive", help="ZIP path. Default: output/custom_voice_101.zip")
    p.add_argument(
        "--language",
        help="Install language code. Defaults to active pack or downloaded base pack language.",
    )
    p.add_argument("--suffix", help="Upload suffix. Default: <language>.zip")
    p.add_argument("--did", help="Install on one robot DID only.")
    p.add_argument("--all-devices", action="store_true", help="Install on all enabled vacuum robots.")
    p.add_argument("--wait-seconds", type=int, default=180)
    p.set_defaults(handler=cmd_install)

    p = sub.add_parser("official", help="Install an official Xiaomi language pack.")
    p.add_argument("--language", default="en", help="Language code from Xiaomi catalog.")
    p.add_argument("--wait-seconds", type=int, default=180)
    p.set_defaults(handler=cmd_official)

    p = sub.add_parser(
        "run",
        help="Run a full non-interactive pipeline: deps, configure, download, build, install.",
    )
    p.add_argument("--method", choices=["password", "cookies", "qr"], default="cookies")
    p.add_argument("--region", default=core.DEFAULT_REGION)
    p.add_argument("--did")
    p.add_argument("--auto-did", action="store_true")
    p.add_argument("--username")
    p.add_argument("--password")
    p.add_argument("--user-id")
    p.add_argument("--service-token")
    p.add_argument("--ssecurity")
    p.add_argument("--archive")
    p.add_argument(
        "--language",
        help="Install language code. Defaults to active pack or downloaded base pack language.",
    )
    p.add_argument("--wait-seconds", type=int, default=180)
    p.add_argument("--skip-configure", action="store_true")
    p.add_argument("--skip-download", action="store_true")
    p.add_argument("--open-browser", action="store_true")
    p.set_defaults(handler=cmd_run_pipeline)

    return parser


def main(argv: list[str] | None = None) -> int:
    core.ensure_dirs()
    raw_argv = list(argv if argv is not None else sys.argv[1:])

    json_mode = False
    no_tui = False
    argv_clean: list[str] = []
    for arg in raw_argv:
        if arg == "--json":
            json_mode = True
        elif arg == "--no-tui":
            no_tui = True
        else:
            argv_clean.append(arg)

    parser = build_parser()
    if not argv_clean:
        parser.print_help()
        return 0

    args = parser.parse_args(argv_clean)
    args.json = json_mode
    args.no_tui = no_tui

    if getattr(args, "devices_command", None) and args.command == "devices":
        if args.devices_command != "list":
            parser.error("Unknown devices subcommand.")

    if getattr(args, "languages_command", None) and args.command == "languages":
        if args.languages_command != "list":
            parser.error("Unknown languages subcommand.")

    if getattr(args, "pack_command", None) and args.command == "pack":
        if args.pack_command not in ("list", "create"):
            parser.error("Unknown pack subcommand.")

    if getattr(args, "robot_command", None) and args.command == "robot":
        if args.robot_command == "commands" and args.robot_commands_command != "list":
            parser.error("Unknown robot commands subcommand.")
        if args.robot_command not in ("commands", "snapshot", "run"):
            parser.error("Unknown robot subcommand.")

    try:
        return args.handler(args)
    except CliError as exc:
        emit(False, args.command, json_mode=args.json, error=str(exc), hint=exc.hint)
        return 1
    except subprocess.CalledProcessError as exc:
        emit(
            False,
            args.command,
            json_mode=args.json,
            error=f"External command failed with exit code {exc.returncode}.",
            hint="Check network access and installed tools: curl, unzip, zip.",
        )
        return 1
    except Exception as exc:
        emit(
            False,
            args.command,
            json_mode=args.json,
            error=f"{type(exc).__name__}: {exc}",
            hint="Re-run with --json for structured output or check README CLI section.",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
