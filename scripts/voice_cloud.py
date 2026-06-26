"""Xiaomi cloud voice pack operations for the X20 voice tool."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import requests

try:
    from Crypto.Cipher import ARC4
except ModuleNotFoundError:
    from Cryptodome.Cipher import ARC4

VOICE_SIID = 15
VOICE_INSTALL_AIID = 1
VOICE_STATUS_AIID = 2


def signed_nonce(ssec: str, nonce: str) -> str:
    digest = hashlib.sha256(base64.b64decode(ssec) + base64.b64decode(nonce)).digest()
    return base64.b64encode(digest).decode()


def generate_nonce() -> str:
    nonce = os.urandom(8) + int(time.time() * 1000 / 60000).to_bytes(4, "big")
    return base64.b64encode(nonce).decode()


def encrypt_rc4(password_b64: str, payload: str) -> str:
    cipher = ARC4.new(base64.b64decode(password_b64))
    cipher.encrypt(bytes(1024))
    return base64.b64encode(cipher.encrypt(payload.encode())).decode()


def decrypt_rc4(password_b64: str, payload_b64: str) -> bytes:
    cipher = ARC4.new(base64.b64decode(password_b64))
    cipher.encrypt(bytes(1024))
    return cipher.encrypt(base64.b64decode(payload_b64))


def enc_signature(url: str, method: str, snonce: str, params: dict[str, str]) -> str:
    parts = [method.upper(), url.split("com", 1)[1].replace("/app/", "/")]
    for key, value in params.items():
        parts.append(f"{key}={value}")
    parts.append(snonce)
    return base64.b64encode(hashlib.sha1("&".join(parts).encode()).digest()).decode()


def enc_params(
    url: str, method: str, snonce: str, nonce: str, params: dict[str, str], ssec: str
) -> dict[str, str]:
    params = dict(params)
    params["rc4_hash__"] = enc_signature(url, method, snonce, params)
    for key in list(params):
        params[key] = encrypt_rc4(snonce, params[key])
    params["signature"] = enc_signature(url, method, snonce, params)
    params["ssecurity"] = ssec
    params["_nonce"] = nonce
    return params


class XiaomiCloud:
    def __init__(self, config: dict[str, str]):
        self.config = config
        self.did = str(config["did"])
        self.access_key = config.get("accessKey", "IOS00026747c5acafc2")
        self.host_root = config["endpoint"].split("/app/")[0] + "/app"

    def post(self, path: str, payload: dict, timeout: int = 30) -> dict:
        url = f"{self.host_root}/{path.lstrip('/')}"
        body = json.dumps(payload, separators=(",", ":"))
        nonce = generate_nonce()
        snonce = signed_nonce(self.config["ssecurity"], nonce)
        fields = enc_params(url, "POST", snonce, nonce, {"data": body}, self.config["ssecurity"])
        headers = {
            "Accept-Encoding": "identity",
            "User-Agent": "Android-7.1.1-1.0.0-ONEPLUS A3010-136-XXXXXXXXXXXX APP/xiaomi.smarthome APPV/10.5.201",
            "Content-Type": "application/x-www-form-urlencoded",
            "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
            "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        }
        cookies = {
            "userId": self.config["userId"],
            "serviceToken": self.config["serviceToken"],
            "yetAnotherServiceToken": self.config["serviceToken"],
            "locale": "en_GB",
            "channel": "MI_APP_STORE",
        }
        response = requests.post(
            url, headers=headers, cookies=cookies, params=fields, timeout=timeout
        )
        raw = response.text.strip()
        decrypted = None
        if response.status_code == 200 and raw:
            decrypted = decrypt_rc4(snonce, raw).decode("utf-8", "replace")
        try:
            body = json.loads(decrypted if decrypted is not None else raw)
        except Exception:
            body = {"raw": raw[:400], "decrypted": decrypted[:400] if decrypted else None}
        return {"http_status": response.status_code, "response": body}


def response_ok(result: dict) -> bool:
    body = result.get("response") or {}
    return result.get("http_status") == 200 and body.get("code") == 0


def file_info(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return hashlib.md5(data).hexdigest(), len(data)


def parse_status(result: dict) -> dict | None:
    out = (((result.get("response") or {}).get("result") or {}).get("out"))
    if isinstance(out, list) and len(out) >= 4:
        return {"target": out[0], "current": out[1], "status": out[2], "progress": out[3]}
    return None


def get_status(api: XiaomiCloud) -> dict:
    payload = {"params": {"did": api.did, "siid": VOICE_SIID, "aiid": VOICE_STATUS_AIID, "in": []}}
    return api.post("/miotspec/action", payload)


def send_install(api: XiaomiCloud, language: str, url: str, md5: str, size: int) -> dict:
    meta = json.dumps({"md5": md5, "size": size}, separators=(",", ":"))
    payload = {
        "params": {
            "did": api.did,
            "siid": VOICE_SIID,
            "aiid": VOICE_INSTALL_AIID,
            "in": [language, url, meta],
        }
    }
    return api.post("/miotspec/action", payload)


def wait_status(
    api: XiaomiCloud,
    target: str,
    seconds: int,
    *,
    on_update: Callable[[dict | None], None] | None = None,
) -> dict | None:
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        result = get_status(api)
        status = parse_status(result)
        if status != last:
            if on_update:
                on_update(status)
            last = status
        if status and status["current"] == target and status["status"] in (0, 4):
            return status
        if status and status["status"] in (3, 5):
            return status
        time.sleep(2)
    return last


def robot_voice_status(config: dict[str, str]) -> dict:
    api = XiaomiCloud(config)
    result = get_status(api)
    status = parse_status(result)
    if not response_ok(result) or not status:
        raise RuntimeError(
            "Could not read voice status. Session may be expired or DID/region may be wrong."
        )
    return status


def robot_voice_status_many(
    config_document: dict,
    *,
    all_enabled: bool = True,
) -> list[dict[str, object]]:
    from voice_tool_core import iter_target_configs

    results: list[dict[str, object]] = []
    for device_config, device in iter_target_configs(config_document, all_enabled=all_enabled):
        entry: dict[str, object] = {
            "did": device["did"],
            "name": device.get("name", ""),
            "model": device.get("model", ""),
        }
        try:
            entry["status"] = robot_voice_status(device_config)
            entry["ok"] = True
        except Exception as exc:
            entry["ok"] = False
            entry["error"] = str(exc)
        results.append(entry)
    return results


def install_custom_archive_many(
    config_document: dict,
    archive: Path,
    language: str,
    suffix: str,
    wait_seconds: int,
    *,
    all_enabled: bool = True,
    on_update: Callable[[dict | None], None] | None = None,
) -> list[dict[str, object]]:
    from voice_tool_core import iter_target_configs

    results: list[dict[str, object]] = []
    for device_config, device in iter_target_configs(config_document, all_enabled=all_enabled):
        entry: dict[str, object] = {
            "did": device["did"],
            "name": device.get("name", ""),
            "model": device.get("model", ""),
        }
        try:
            entry["result"] = install_custom_archive(
                device_config,
                archive,
                language,
                suffix,
                wait_seconds,
                on_update=on_update,
            )
            entry["ok"] = True
        except Exception as exc:
            entry["ok"] = False
            entry["error"] = str(exc)
        results.append(entry)
    return results


def install_custom_archive(
    config: dict[str, str],
    archive: Path,
    language: str,
    suffix: str,
    wait_seconds: int,
    *,
    on_update: Callable[[dict | None], None] | None = None,
) -> dict:
    if not archive.exists():
        raise FileNotFoundError(f"Archive not found: {archive}")

    api = XiaomiCloud(config)
    md5, size = file_info(archive)

    preflight = get_status(api)
    if not response_ok(preflight):
        raise RuntimeError("Robot rejected the preflight status request.")

    upload = api.post("/v2/home/genpresignedurl_v3", {"did": api.did, "suffix": suffix})
    entry = (((upload.get("response") or {}).get("result") or {}).get(suffix))
    if not response_ok(upload) or not isinstance(entry, dict) or not entry.get("url"):
        raise RuntimeError("Xiaomi did not return a presigned upload URL.")

    with archive.open("rb") as source:
        put = requests.put(
            entry["url"],
            data=source,
            headers={"Content-Type": "application/octet-stream"},
            timeout=180,
        )
    put.raise_for_status()

    get_result = api.post("/v2/home/getfileurl_v3", {"obj_name": entry["obj_name"]})
    get_url = (((get_result.get("response") or {}).get("result") or {}).get("url"))
    if not response_ok(get_result) or not get_url:
        raise RuntimeError("Xiaomi did not return a signed download URL.")

    digest = hashlib.md5()
    downloaded = 0
    with requests.get(get_url, stream=True, timeout=60) as response:
        response.raise_for_status()
        for chunk in response.iter_content(256 * 1024):
            digest.update(chunk)
            downloaded += len(chunk)
    if digest.hexdigest() != md5 or downloaded != size:
        raise RuntimeError("Signed download verification failed.")

    split = urlsplit(get_url)
    relative_variants = [
        split.path + ("?" + split.query if split.query else "") + f"#/{suffix}",
        split.path + ("?" + split.query if split.query else ""),
        get_url,
    ]

    final_status = None
    for relative in relative_variants:
        action = send_install(api, language, relative, md5, size)
        action_ok = response_ok(action) and (
            ((action.get("response") or {}).get("result") or {}).get("code") == 0
        )
        if not action_ok:
            continue
        final_status = wait_status(api, language, wait_seconds, on_update=on_update)
        if final_status and final_status["current"] == language and final_status["status"] in (0, 4):
            break

    if not final_status or final_status.get("current") != language or final_status.get("status") not in (
        0,
        4,
    ):
        raise RuntimeError("Robot did not confirm a successful install.")

    return {
        "archive": str(archive),
        "md5": md5,
        "size": size,
        "language": language,
        "final_status": final_status,
    }


def install_official_language(
    config: dict[str, str],
    language: str,
    relative_url: str,
    md5: str,
    size: int,
    wait_seconds: int,
    *,
    on_update: Callable[[dict | None], None] | None = None,
) -> dict:
    if not relative_url.startswith("/"):
        relative_url = "/" + relative_url

    api = XiaomiCloud(config)
    preflight = get_status(api)
    if not response_ok(preflight):
        raise RuntimeError("Robot rejected the preflight status request.")

    action = send_install(api, language, relative_url, md5, size)
    if not response_ok(action) or (
        ((action.get("response") or {}).get("result") or {}).get("code") != 0
    ):
        raise RuntimeError("Robot rejected the official voice install action.")

    final_status = wait_status(api, language, wait_seconds, on_update=on_update)
    if not final_status or final_status.get("current") != language or final_status.get("status") not in (
        0,
        4,
    ):
        raise RuntimeError("Robot did not confirm a successful official voice install.")

    return {
        "language": language,
        "relative_url": relative_url,
        "md5": md5,
        "size": size,
        "final_status": final_status,
    }
