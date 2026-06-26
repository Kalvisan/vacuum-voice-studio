"""Official Xiaomi voice pack catalog for d109gl (from voice.config)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

import voice_tool_core as core

VOICE_CONFIG_URL = (
    "https://awsde0-fusion.fds.api.xiaomi.com"
    "/xiaomi-d109gl/0Cloud_Management/voice_config/voice.config"
)
FDS_BASE_URL = "https://awsde0-fusion.fds.api.xiaomi.com"
CATALOG_CACHE = core.WORKSPACE_DIR / ".voice_catalog_cache.json"
FALLBACK_CATALOG = core.ASSETS_DIR / "d109gl_voice_catalog.json"
CACHE_TTL_SECONDS = 86400

LANGUAGE_LABELS: dict[str, str] = {
    "ar": "Arabic",
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "he": "Hebrew",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese (Brazil)",
    "pt_pt": "Portuguese (Portugal)",
    "ru": "Russian",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "zh": "Chinese (Simplified)",
    "zh_hk": "Chinese (Hong Kong)",
    "zh_tw": "Chinese (Traditional, Taiwan)",
}


def language_label(code: str) -> str:
    normalized = code.strip().lower()
    return LANGUAGE_LABELS.get(normalized, normalized.replace("_", " ").title())


def enrich_languages(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{**entry, "label": language_label(entry["code"])} for entry in entries]


def validate_install_language(language: str) -> str:
    code = str(language or "").strip().lower()
    if not code:
        raise ValueError("Install language is required.")
    get_voice_entry(code)
    return code


def _normalize_entry(item: dict[str, Any]) -> dict[str, str]:
    code = str(item.get("code", "")).strip()
    url = str(item.get("url", "")).strip()
    md5 = str(item.get("md5", "")).strip().lower()
    if not code or not url:
        raise ValueError("Invalid voice catalog entry.")
    return {"code": code, "url": url, "md5": md5}


def _parse_catalog_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for key in ("voiceList",):
        for item in payload.get(key) or []:
            if isinstance(item, dict) and item.get("code"):
                entry = _normalize_entry(item)
                entries[entry["code"]] = entry
    for block in payload.get("whiteList") or []:
        if not isinstance(block, dict):
            continue
        for item in block.get("voiceList") or []:
            if isinstance(item, dict) and item.get("code"):
                entry = _normalize_entry(item)
                entries[entry["code"]] = entry
    return sorted(entries.values(), key=lambda item: item["code"])


def fetch_voice_catalog(*, force_refresh: bool = False) -> list[dict[str, str]]:
    core.ensure_dirs()
    now = time.time()

    if not force_refresh and CATALOG_CACHE.exists():
        try:
            cached = json.loads(CATALOG_CACHE.read_text(encoding="utf-8"))
            if now - float(cached.get("fetched_at", 0)) < CACHE_TTL_SECONDS:
                return list(cached.get("languages") or [])
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    try:
        response = requests.get(VOICE_CONFIG_URL, timeout=30)
        response.raise_for_status()
        languages = _parse_catalog_payload(response.json())
        CATALOG_CACHE.write_text(
            json.dumps({"fetched_at": now, "languages": languages}, indent=2) + "\n",
            encoding="utf-8",
        )
        return languages
    except Exception:
        if FALLBACK_CATALOG.exists():
            payload = json.loads(FALLBACK_CATALOG.read_text(encoding="utf-8"))
            return _parse_catalog_payload(payload)
        raise


def get_voice_entry(language: str) -> dict[str, str]:
    code = language.strip().lower()
    for entry in fetch_voice_catalog():
        if entry["code"] == code:
            return entry
    available = ", ".join(item["code"] for item in fetch_voice_catalog())
    raise ValueError(f"Language '{language}' is not available. Choose from: {available}")


def download_url(relative_path: str) -> str:
    path = relative_path if relative_path.startswith("/") else f"/{relative_path}"
    return f"{FDS_BASE_URL}{path}"
