"""Shared paths and file operations for the X20 voice tool."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_COUNT = 101
DEFAULT_MODEL = "d109gl"
DEFAULT_REGION = "de"
DEFAULT_BASE_LANGUAGE = "en"
DEFAULT_ACCESS_KEY = "IOS00026747c5acafc2"
CLOUD_VALIDATE_TIMEOUT_SECONDS = 45

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
CONFIG_DIR = ROOT_DIR / "config"
WORKSPACE_DIR = ROOT_DIR / "workspace"
OUTPUT_DIR = ROOT_DIR / "output"
CONFIG_FILE = CONFIG_DIR / "config.json"
CONNECTION_FILE = CONFIG_DIR / ".connection-ok"
BASE_PACK_META_FILE = WORKSPACE_DIR / "base_pack.json"
BUILD_STATE_FILE = WORKSPACE_DIR / "build_state.json"
INSTALL_STATE_FILE = WORKSPACE_DIR / "install_state.json"
DEFAULT_BUILD_ZIP = OUTPUT_DIR / "custom_voice_101.zip"
ORIGINAL_DIR = WORKSPACE_DIR / "original"
TRANSCRIPT_CSV = ASSETS_DIR / "d109gl_en_transcriptions.csv"

REQUIRED_CONFIG_KEYS = (
    "region",
    "did",
    "userId",
    "ssecurity",
    "serviceToken",
    "accessKey",
    "endpoint",
)

VACUUM_DEVICES_KEY = "vacuum_devices"

SESSION_STATE_NO_FILE = "no_file"
SESSION_STATE_VALID = "valid"
SESSION_STATE_EXPIRED = "expired"
SESSION_STATE_INVALID = "invalid"


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def shell_tools_available() -> bool:
    for tool in ("python3", "curl", "unzip", "zip"):
        if shutil.which(tool) is None:
            return False
    return True


def python_deps_available(include_tui: bool = False) -> bool:
    try:
        import requests  # noqa: F401
        from Crypto.Cipher import ARC4  # noqa: F401
        if include_tui:
            import textual  # noqa: F401
        return True
    except ModuleNotFoundError:
        return False


def install_python_deps(include_tui: bool = True) -> None:
    packages = ["requests", "pycryptodome"]
    if include_tui:
        packages.append("textual")
    subprocess.run(
        ["python3", "-m", "pip", "install", "--user", *packages],
        check=True,
    )


def config_shape_ok(path: Path = CONFIG_FILE) -> bool:
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    return all(str(data.get(key, "")).strip() for key in REQUIRED_CONFIG_KEYS)


def connection_marker_ok(path: Path = CONFIG_FILE, marker_path: Path = CONNECTION_FILE) -> bool:
    if not marker_path.exists():
        return False
    config_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    marker = marker_path.read_text(encoding="utf-8").strip().splitlines()[0]
    return marker == config_hash


def config_ready() -> bool:
    return config_shape_ok() and connection_marker_ok()


def workspace_ready() -> bool:
    if not base_pack_ready():
        return False
    try:
        import voice_pack_manager as vpm

        active = vpm.get_active_pack_id()
        if active and vpm._audio_dir(active).is_dir():
            return True
    except Exception:
        pass
    return False


def base_audio_dir() -> Path:
    return ORIGINAL_DIR


def load_base_pack_meta() -> dict[str, str] | None:
    if not BASE_PACK_META_FILE.exists():
        return None
    try:
        data = json.loads(BASE_PACK_META_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not str(data.get("language", "")).strip():
        return None
    return {key: str(data[key]) for key in data if data[key] is not None}


def save_base_pack_meta(meta: dict[str, object]) -> None:
    ensure_dirs()
    BASE_PACK_META_FILE.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def base_pack_ready() -> bool:
    meta = load_base_pack_meta()
    if not meta:
        return False
    return ORIGINAL_DIR.is_dir() and len(list(ORIGINAL_DIR.glob("*.mp3"))) == EXPECTED_COUNT


def build_zip_path(path: Path | None = None) -> Path:
    return path or DEFAULT_BUILD_ZIP


def zip_exists(path: Path | None = None) -> bool:
    return build_zip_path(path).exists()


def _read_json_state(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def load_build_state() -> dict[str, object] | None:
    return _read_json_state(BUILD_STATE_FILE)


def save_build_state(*, pack_id: str, zip_md5: str, replaced_count: int, zip_path: Path | None = None) -> None:
    ensure_dirs()
    BUILD_STATE_FILE.write_text(
        json.dumps(
            {
                "pack_id": pack_id,
                "zip_md5": zip_md5,
                "replaced_count": replaced_count,
                "zip_path": str(build_zip_path(zip_path)),
                "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def load_install_state() -> dict[str, object] | None:
    return _read_json_state(INSTALL_STATE_FILE)


def save_install_state(*, pack_id: str, zip_md5: str, language: str) -> None:
    ensure_dirs()
    INSTALL_STATE_FILE.write_text(
        json.dumps(
            {
                "pack_id": pack_id,
                "zip_md5": zip_md5,
                "language": language,
                "installed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def clear_install_state() -> None:
    INSTALL_STATE_FILE.unlink(missing_ok=True)


_install_backfill_attempted = False


def _maybe_backfill_install_state() -> None:
    _maybe_backfill_build_state()
    if load_install_state() or not zip_ready():
        return
    try:
        import voice_pack_manager as vpm
        import voice_cloud

        active_id = vpm.get_active_pack_id()
        if not active_id:
            return
        language = resolve_install_language()
        md5 = build_zip_md5()
        if not md5:
            return
        document = load_config_document()
        statuses = voice_cloud.robot_voice_status_many(document, all_enabled=True)
        enabled = [item for item in statuses if item.get("ok")]
        if not enabled:
            return
        for item in enabled:
            status = item.get("status") or {}
            if status.get("current") != language or status.get("status") not in (0, 4):
                return
        save_install_state(pack_id=active_id, zip_md5=md5, language=language)
    except Exception:
        return


def build_zip_md5(path: Path | None = None) -> str | None:
    target = build_zip_path(path)
    if not target.exists():
        return None
    return hashlib.md5(target.read_bytes()).hexdigest()


def _maybe_backfill_build_state() -> None:
    if load_build_state() or not zip_exists() or not workspace_ready():
        return
    try:
        import voice_pack_manager as vpm

        active_id = vpm.get_active_pack_id()
        if not active_id:
            return
        pack = vpm.get_pack(active_id)
        md5 = build_zip_md5()
        if not md5:
            return
        save_build_state(
            pack_id=active_id,
            zip_md5=md5,
            replaced_count=int(pack.get("replaced_count", 0)),
        )
    except Exception:
        return


def needs_build() -> bool:
    _maybe_backfill_build_state()
    if not workspace_ready():
        return False
    if not zip_exists():
        return True
    state = load_build_state()
    if not state:
        return True
    try:
        import voice_pack_manager as vpm

        active_id = vpm.get_active_pack_id()
        if not active_id:
            return True
        pack = vpm.get_pack(active_id)
    except Exception:
        return True
    current_md5 = build_zip_md5()
    if not current_md5:
        return True
    return (
        str(state.get("pack_id", "")) != active_id
        or int(state.get("replaced_count", -1)) != int(pack.get("replaced_count", -2))
        or str(state.get("zip_md5", "")) != current_md5
    )


def install_synced() -> bool:
    global _install_backfill_attempted
    if not _install_backfill_attempted:
        _install_backfill_attempted = True
        _maybe_backfill_install_state()
    if needs_build() or not zip_exists():
        return False
    marker = load_install_state()
    if not marker:
        return False
    try:
        import voice_pack_manager as vpm

        active_id = vpm.get_active_pack_id()
        if not active_id:
            return False
        language = resolve_install_language()
    except (ValueError, FileNotFoundError, OSError):
        return False
    current_md5 = build_zip_md5()
    if not current_md5:
        return False
    return (
        str(marker.get("pack_id", "")) == active_id
        and str(marker.get("zip_md5", "")) == current_md5
        and str(marker.get("language", "")).lower() == language.lower()
    )


def zip_ready(path: Path | None = None) -> bool:
    return zip_exists(path) and not needs_build()


def readiness(include_tui: bool = False) -> dict[str, bool]:
    return {
        "shell_tools": shell_tools_available(),
        "python_deps": python_deps_available(include_tui=include_tui),
        "config_shape": config_shape_ok(),
        "config_verified": connection_marker_ok(),
        "config_ready": config_ready(),
        "base_pack_ready": base_pack_ready(),
        "workspace_ready": workspace_ready(),
        "zip_exists": zip_exists(),
        "needs_build": needs_build(),
        "zip_ready": zip_ready(),
        "install_synced": install_synced(),
    }


def load_config_document(path: Path = CONFIG_FILE) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(path: Path = CONFIG_FILE) -> dict[str, str]:
    data = load_config_document(path)
    missing = [key for key in REQUIRED_CONFIG_KEYS if not str(data.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Config missing required keys: {', '.join(missing)}")
    return {key: str(data[key]) for key in REQUIRED_CONFIG_KEYS}


def save_config_document(data: dict, path: Path = CONFIG_FILE) -> None:
    ensure_dirs()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def normalize_config(data: dict) -> dict[str, str]:
    region = str(data.get("region", DEFAULT_REGION)).strip() or DEFAULT_REGION
    access_key = str(data.get("accessKey", DEFAULT_ACCESS_KEY)).strip() or DEFAULT_ACCESS_KEY
    endpoint = str(data.get("endpoint", "")).strip() or (
        f"https://{region}.core.api.io.mi.com/app/miotspec/action"
    )
    normalized = {
        "region": region,
        "did": str(data.get("did", "")).strip(),
        "userId": str(data.get("userId", "")).strip(),
        "ssecurity": str(data.get("ssecurity", "")).strip(),
        "serviceToken": str(data.get("serviceToken", "")).strip(),
        "accessKey": access_key,
        "endpoint": endpoint,
    }
    missing = [key for key in REQUIRED_CONFIG_KEYS if not normalized[key]]
    if missing:
        raise ValueError(f"Config missing required keys: {', '.join(missing)}")
    return normalized


def get_vacuum_devices(data: dict | None = None, path: Path = CONFIG_FILE) -> list[dict[str, str | bool]]:
    if data is None:
        if not path.exists():
            return []
        data = load_config_document(path)

    devices = data.get(VACUUM_DEVICES_KEY)
    if isinstance(devices, list) and devices:
        result: list[dict[str, str | bool]] = []
        for item in devices:
            if not isinstance(item, dict):
                continue
            did = str(item.get("did", "")).strip()
            if not did:
                continue
            result.append(
                {
                    "did": did,
                    "name": str(item.get("name", "")).strip(),
                    "model": str(item.get("model", "")).strip(),
                    "region": str(item.get("region", "")).strip(),
                    "enabled": bool(item.get("enabled", True)),
                }
            )
        return result

    did = str(data.get("did", "")).strip()
    if not did:
        return []
    return [
        {
            "did": did,
            "name": str(data.get("device_name", "")).strip(),
            "model": str(data.get("device_model", "")).strip(),
            "region": str(data.get("region", "")).strip(),
            "enabled": True,
        }
    ]


def get_enabled_vacuum_devices(data: dict | None = None, path: Path = CONFIG_FILE) -> list[dict[str, str | bool]]:
    return [device for device in get_vacuum_devices(data, path) if device.get("enabled", True)]


def config_for_did(base: dict[str, str], did: str, region: str | None = None) -> dict[str, str]:
    cfg = {**base, "did": str(did)}
    reg = (region or "").strip() or str(base.get("region", "")).strip()
    if reg:
        cfg["region"] = reg
        cfg["endpoint"] = f"https://{reg}.core.api.io.mi.com/app/miotspec/action"
    return cfg


def iter_target_configs(
    data: dict | None = None,
    *,
    all_enabled: bool = False,
    did: str = "",
) -> list[tuple[dict[str, str], dict[str, str | bool]]]:
    document = data if data is not None else load_config_document()
    base = normalize_config(document)
    devices = get_enabled_vacuum_devices(document) if all_enabled else get_vacuum_devices(document)
    if did:
        devices = [item for item in devices if str(item["did"]) == did]
        if not devices:
            devices = [{"did": did, "name": "", "model": "", "enabled": True}]
    if not devices:
        devices = [{"did": base["did"], "name": "", "model": "", "enabled": True}]
    return [
        (
            config_for_did(base, str(item["did"]), str(item.get("region") or "") or None),
            item,
        )
        for item in devices
        if item.get("enabled", True)
    ]


def clear_connection_marker(marker_path: Path = CONNECTION_FILE) -> None:
    if marker_path.exists():
        marker_path.unlink()


def validate_cloud_session(config: dict[str, str]) -> dict[str, object]:
    """Check whether saved Xiaomi tokens still work against the cloud API."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_validate_cloud_session_impl, config)
        try:
            return future.result(timeout=CLOUD_VALIDATE_TIMEOUT_SECONDS)
        except FuturesTimeoutError:
            return {
                "valid": False,
                "reason": SESSION_STATE_EXPIRED,
                "error": "Xiaomi cloud did not respond in time. Check your internet connection.",
                "token_ok": False,
            }


def _validate_cloud_session_impl(config: dict[str, str]) -> dict[str, object]:
    from xiaomi_cloud_login import (
        LoginResult,
        connector_from_login,
        discover_devices,
        find_vacuum_devices,
    )

    login = LoginResult(
        user_id=config["userId"],
        ssecurity=config["ssecurity"],
        service_token=config["serviceToken"],
        region=config["region"],
    )
    connector = connector_from_login(login)
    try:
        devices = discover_devices(connector, config["region"])
    except Exception as exc:
        return {
            "valid": False,
            "reason": SESSION_STATE_EXPIRED,
            "error": str(exc),
            "token_ok": False,
        }

    vacuums = find_vacuum_devices(devices)
    robot_status: dict[str, object] | None = None
    robot_error = ""
    try:
        import voice_cloud

        robot_status = voice_cloud.robot_voice_status(config)
    except Exception as exc:
        robot_error = str(exc)

    return {
        "valid": True,
        "reason": SESSION_STATE_VALID,
        "token_ok": True,
        "devices_found": len(devices),
        "vacuums_found": len(vacuums),
        "vacuums": [
            {"did": item.did, "name": item.name, "model": item.model}
            for item in vacuums
        ],
        "robot_status": robot_status,
        "robot_error": robot_error,
    }


def resolve_startup_session(*, test_connection: bool = True) -> dict[str, object]:
    """Decide whether to open setup wizard or go straight to the control panel."""
    ensure_dirs()
    if not CONFIG_FILE.exists():
        return {
            "state": SESSION_STATE_NO_FILE,
            "config_ready": False,
            "message": "No saved Xiaomi session yet.",
            "action": "first_run",
        }

    document = load_config_document()

    if not config_shape_ok():
        clear_connection_marker()
        return {
            "state": SESSION_STATE_INVALID,
            "config_ready": False,
            "message": "Session file exists but required fields are missing.",
            "action": "first_run",
        }

    config = normalize_config(document)
    vacuums = get_enabled_vacuum_devices(document)
    if not test_connection:
        ready = config_ready()
        return {
            "state": SESSION_STATE_VALID if ready else SESSION_STATE_INVALID,
            "config_ready": ready,
            "source": str(CONFIG_FILE),
            "vacuums": vacuums,
            "message": "Skipped live token validation.",
            "action": "control_panel" if ready else "first_run",
        }

    validation = validate_cloud_session(config)
    if not validation.get("valid"):
        clear_connection_marker()
        return {
            "state": SESSION_STATE_EXPIRED,
            "config_ready": False,
            "source": str(CONFIG_FILE),
            "vacuums": vacuums,
            "message": "Saved Xiaomi session expired. Please sign in again.",
            "action": "relogin",
            "error": validation.get("error", ""),
        }

    mark_config_verified()
    return {
        "state": SESSION_STATE_VALID,
        "config_ready": True,
        "source": str(CONFIG_FILE),
        "vacuums": vacuums,
        "devices_found": validation.get("devices_found", 0),
        "vacuums_found": validation.get("vacuums_found", len(vacuums)),
        "robot_status": validation.get("robot_status"),
        "robot_error": validation.get("robot_error", ""),
        "message": "Saved Xiaomi session is valid.",
        "action": "control_panel",
    }


def ensure_local_session(*, test_connection: bool = True) -> dict[str, object]:
    """Reuse an existing local session instead of asking the user to log in again."""
    ensure_dirs()
    result = resolve_startup_session(test_connection=test_connection)
    return {
        "source": result.get("source"),
        "config_path": str(CONFIG_FILE),
        "config_ready": bool(result.get("config_ready")),
        "verified": result.get("state") == SESSION_STATE_VALID,
        "state": result.get("state"),
        "action": result.get("action"),
        "vacuums": result.get("vacuums", []),
        "message": result.get("message", ""),
        "test_error": result.get("error") or result.get("robot_error") or "",
    }


def mark_config_verified(path: Path = CONFIG_FILE, marker_path: Path = CONNECTION_FILE) -> None:
    config_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    marker_path.write_text(config_hash + "\n", encoding="utf-8")


def resolve_install_language(explicit: str | None = None) -> str:
    if explicit and str(explicit).strip():
        from voice_catalog import validate_install_language

        return validate_install_language(str(explicit))

    try:
        import voice_pack_manager as vpm

        active_id = vpm.get_active_pack_id()
        if active_id:
            pack_lang = str(vpm.get_pack(active_id).get("language") or "").strip().lower()
            if pack_lang:
                from voice_catalog import get_voice_entry

                get_voice_entry(pack_lang)
                return pack_lang
    except (FileNotFoundError, OSError, ValueError):
        pass

    meta = load_base_pack_meta()
    if meta and meta.get("language"):
        return meta["language"]

    raise ValueError(
        "Install language is unknown. Pass --language or set the install language on your voice pack."
    )


def download_base_pack(language: str = DEFAULT_BASE_LANGUAGE, *, reset_working: bool = True) -> dict[str, str | int]:
    from voice_catalog import download_url, get_voice_entry

    entry = get_voice_entry(language)
    url = download_url(entry["url"])
    code = entry["code"]
    zip_path = WORKSPACE_DIR / f"base_{code}.zip"
    working_dir = WORKSPACE_DIR / "working_pack"

    subprocess.run(
        ["curl", "-fL", "--retry", "3", "--connect-timeout", "20", "-o", str(zip_path), url],
        check=True,
    )

    if ORIGINAL_DIR.exists():
        shutil.rmtree(ORIGINAL_DIR)
    if reset_working and working_dir.exists():
        shutil.rmtree(working_dir)
    ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
    if reset_working:
        working_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(["unzip", "-q", str(zip_path), "-d", str(ORIGINAL_DIR)], check=True)
    count = len(list(ORIGINAL_DIR.glob("*.mp3")))
    if count != EXPECTED_COUNT:
        raise RuntimeError(f"Expected {EXPECTED_COUNT} MP3 files, downloaded pack has {count}.")

    if reset_working:
        for mp3 in ORIGINAL_DIR.glob("*.mp3"):
            shutil.copy2(mp3, working_dir / mp3.name)

    save_base_pack_meta(
        {
            "language": code,
            "url": entry["url"],
            "download_url": url,
            "md5": entry["md5"],
            "file_count": count,
        }
    )

    return {
        "language": code,
        "url": url,
        "zip_path": str(zip_path),
        "original_dir": str(ORIGINAL_DIR),
        "working_dir": str(working_dir) if reset_working else "",
        "file_count": count,
        "md5": entry["md5"],
    }


def expected_mp3_names() -> list[str]:
    names: list[str] = []
    with TRANSCRIPT_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            names.append(row["file"])
    return names


def validate_working_pack(working_dir: Path) -> tuple[list[str], list[str]]:
    expected_set = set(expected_mp3_names())
    actual_set = {path.name for path in working_dir.glob("*.mp3")}
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    return missing, extra


def build_zip(
    output_path: Path | None = None,
    *,
    language_alias: str | None = None,
    write_language_alias: bool = True,
    working_dir: Path | None = None,
) -> dict[str, str | int]:
    target_dir = working_dir or (WORKSPACE_DIR / "working_pack")
    if not target_dir.is_dir():
        raise FileNotFoundError(f"No working pack found at {target_dir}")

    count = len(list(target_dir.glob("*.mp3")))
    if count != EXPECTED_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_COUNT} MP3 files in {target_dir}, found {count}."
        )

    missing, extra = validate_working_pack(target_dir)
    if missing or extra:
        details = []
        if missing:
            details.append("Missing files: " + ", ".join(missing))
        if extra:
            details.append("Extra files: " + ", ".join(extra))
        raise RuntimeError(" ".join(details))

    out_zip = output_path or (OUTPUT_DIR / "custom_voice_101.zip")
    if out_zip.exists():
        out_zip.unlink()

    mp3_names = sorted(path.name for path in target_dir.glob("*.mp3"))
    subprocess.run(
        ["zip", "-q", "-X", "-0", str(out_zip.resolve()), *mp3_names],
        cwd=str(target_dir),
        check=True,
    )

    with zipfile.ZipFile(out_zip) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP is corrupt at member: {bad}")
        names = archive.namelist()

    data = out_zip.read_bytes()
    result = {
        "path": str(out_zip),
        "files": len(names),
        "size": len(data),
        "md5": hashlib.md5(data).hexdigest(),
    }

    if language_alias is None and write_language_alias:
        meta = load_base_pack_meta()
        if meta:
            language_alias = meta.get("language")

    if language_alias:
        alias_zip = OUTPUT_DIR / f"{language_alias}.zip"
        shutil.copy2(out_zip, alias_zip)
        result["language_alias"] = str(alias_zip)

    return result

