"""Persistent custom voice pack projects for the web studio."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import voice_tool_core as core

PACKS_DIR = core.WORKSPACE_DIR / "packs"
ACTIVE_PACK_FILE = core.WORKSPACE_DIR / "active_pack.json"
PACK_META = "pack.json"
AUDIO_DIR = "audio"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(name: str) -> str:
    text = name.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text[:48] or "voice-pack"


def new_pack_id(name: str) -> str:
    return f"{_slugify(name)}-{uuid.uuid4().hex[:8]}"


def ensure_layout() -> None:
    core.ensure_dirs()
    PACKS_DIR.mkdir(parents=True, exist_ok=True)


def _pack_root(pack_id: str) -> Path:
    return PACKS_DIR / pack_id


def _meta_path(pack_id: str) -> Path:
    return _pack_root(pack_id) / PACK_META


def _audio_dir(pack_id: str) -> Path:
    return _pack_root(pack_id) / AUDIO_DIR


def load_transcripts() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with core.TRANSCRIPT_CSV.open(encoding="utf-8-sig", newline="") as handle:
        import csv

        for row in csv.DictReader(handle):
            text = str(row.get("original_text_whisper", "")).strip()
            rows.append(
                {
                    "file": row["file"],
                    "event_id": row.get("event_id", Path(row["file"]).stem),
                    "text": text,
                    "display_text": text or "(silent — no speech)",
                    "duration": row.get("duration_seconds", ""),
                }
            )
    return rows


def _read_meta(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_meta(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _file_is_custom(pack_id: str, file_name: str) -> bool:
    original = core.base_audio_dir() / file_name
    current = _audio_dir(pack_id) / file_name
    if not original.exists() or not current.exists():
        return False
    return original.read_bytes() != current.read_bytes()


def pack_stats(pack_id: str) -> dict[str, Any]:
    meta = _read_meta(_meta_path(pack_id))
    expected = core.expected_mp3_names()
    replaced = [name for name in expected if _file_is_custom(pack_id, name)]
    meta["replaced"] = replaced
    meta["updated_at"] = _now_iso()
    meta["replaced_count"] = len(replaced)
    meta["total_count"] = len(expected)
    _write_meta(_meta_path(pack_id), meta)
    return meta


def list_packs() -> list[dict[str, Any]]:
    ensure_layout()
    active = get_active_pack_id()
    packs: list[dict[str, Any]] = []
    if not PACKS_DIR.is_dir():
        return packs
    for path in sorted(PACKS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_dir():
            continue
        meta_file = path / PACK_META
        if not meta_file.exists():
            continue
        meta = pack_stats(path.name)
        meta["active"] = path.name == active
        packs.append(meta)
    return packs


def get_active_pack_id() -> str | None:
    if not ACTIVE_PACK_FILE.exists():
        return None
    try:
        data = json.loads(ACTIVE_PACK_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    pack_id = str(data.get("pack_id", "")).strip()
    if pack_id and _meta_path(pack_id).exists():
        return pack_id
    return None


def set_active_pack(pack_id: str) -> dict[str, Any]:
    if not _meta_path(pack_id).exists():
        raise FileNotFoundError(f"Voice pack not found: {pack_id}")
    ensure_layout()
    ACTIVE_PACK_FILE.write_text(
        json.dumps({"pack_id": pack_id, "updated_at": _now_iso()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return pack_stats(pack_id)


def create_pack(name: str, *, language: str = "en") -> dict[str, Any]:
    ensure_layout()
    from voice_catalog import validate_install_language

    install_language = validate_install_language(language)
    original = core.base_audio_dir()
    if not original.is_dir():
        raise FileNotFoundError(
            "Base voice pack is missing. Download one first: ./x20-voice-tool.sh --cli download --language en"
        )

    pack_id = new_pack_id(name)
    audio_dir = _audio_dir(pack_id)
    audio_dir.mkdir(parents=True, exist_ok=True)

    for mp3 in original.glob("*.mp3"):
        shutil.copy2(mp3, audio_dir / mp3.name)

    count = len(list(audio_dir.glob("*.mp3")))
    if count != core.EXPECTED_COUNT:
        shutil.rmtree(_pack_root(pack_id), ignore_errors=True)
        raise RuntimeError(f"Expected {core.EXPECTED_COUNT} files in original pack, found {count}.")

    meta = {
        "id": pack_id,
        "name": name.strip(),
        "language": install_language,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "replaced": [],
        "replaced_count": 0,
        "total_count": core.EXPECTED_COUNT,
    }
    _write_meta(_meta_path(pack_id), meta)
    set_active_pack(pack_id)
    return pack_stats(pack_id)


def get_pack(pack_id: str) -> dict[str, Any]:
    if not _meta_path(pack_id).exists():
        raise FileNotFoundError(f"Voice pack not found: {pack_id}")
    return pack_stats(pack_id)


def delete_pack(pack_id: str) -> None:
    root = _pack_root(pack_id)
    if not root.exists():
        raise FileNotFoundError(f"Voice pack not found: {pack_id}")
    shutil.rmtree(root)
    if get_active_pack_id() == pack_id:
        ACTIVE_PACK_FILE.unlink(missing_ok=True)


def list_pack_files(pack_id: str) -> list[dict[str, Any]]:
    if not _meta_path(pack_id).exists():
        raise FileNotFoundError(f"Voice pack not found: {pack_id}")
    files: list[dict[str, Any]] = []
    for row in load_transcripts():
        file_name = row["file"]
        custom = _file_is_custom(pack_id, file_name)
        files.append(
            {
                **row,
                "custom": custom,
                "has_audio": (_audio_dir(pack_id) / file_name).exists(),
                "text": row.get("display_text") or row.get("text") or "(silent — no speech)",
            }
        )
    return files


def replace_file(pack_id: str, file_name: str, data: bytes) -> dict[str, Any]:
    if file_name not in set(core.expected_mp3_names()):
        raise ValueError(f"Unknown voice file: {file_name}")
    if not data:
        raise ValueError("Empty upload.")
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("File too large (max 20 MB).")

    audio_path = _audio_dir(pack_id) / file_name
    if not _meta_path(pack_id).exists():
        raise FileNotFoundError(f"Voice pack not found: {pack_id}")
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(data)
    return pack_stats(pack_id)


def revert_file(pack_id: str, file_name: str) -> dict[str, Any]:
    if file_name not in set(core.expected_mp3_names()):
        raise ValueError(f"Unknown voice file: {file_name}")
    original = core.base_audio_dir() / file_name
    if not original.exists():
        raise FileNotFoundError(f"Original file missing: {file_name}")
    shutil.copy2(original, _audio_dir(pack_id) / file_name)
    return pack_stats(pack_id)


def sync_pack_to_working(pack_id: str | None = None) -> Path:
    """Copy pack audio into workspace/working_pack for build/install."""
    target_id = pack_id or get_active_pack_id()
    if not target_id:
        raise FileNotFoundError("No active voice pack. Create one in Voice Pack Studio first.")

    source = _audio_dir(target_id)
    if not source.is_dir():
        raise FileNotFoundError(f"Pack audio missing: {target_id}")

    working = core.WORKSPACE_DIR / "working_pack"
    if working.exists():
        shutil.rmtree(working)
    working.mkdir(parents=True)

    for mp3 in source.glob("*.mp3"):
        shutil.copy2(mp3, working / mp3.name)

    count = len(list(working.glob("*.mp3")))
    if count != core.EXPECTED_COUNT:
        raise RuntimeError(f"Pack {target_id} has {count} files, expected {core.EXPECTED_COUNT}.")

    set_active_pack(target_id)
    return working


def prepare_for_build(pack_id: str | None = None) -> dict[str, Any]:
    target_id = pack_id or get_active_pack_id()
    working = sync_pack_to_working(target_id)
    meta = get_pack(str(target_id))
    return {
        "pack_id": target_id,
        "pack_name": meta.get("name"),
        "working_dir": str(working),
        "replaced_count": meta.get("replaced_count", 0),
        "total_count": meta.get("total_count", core.EXPECTED_COUNT),
    }
