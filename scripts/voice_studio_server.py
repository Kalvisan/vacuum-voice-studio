#!/usr/bin/env python3
"""Local web server for Voice Pack Studio."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import signal
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import voice_pack_manager as packs
import voice_tool_core as core

WEB_DIR = core.ROOT_DIR / "web"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
STUDIO_RUNTIME_FILE = core.WORKSPACE_DIR / ".studio_server.json"


def studio_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}/"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def port_is_open(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.35):
            return True
    except OSError:
        return False


def load_studio_runtime() -> dict[str, Any] | None:
    if not STUDIO_RUNTIME_FILE.exists():
        return None
    try:
        data = json.loads(STUDIO_RUNTIME_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def write_studio_runtime(host: str, port: int, pid: int) -> None:
    core.ensure_dirs()
    STUDIO_RUNTIME_FILE.write_text(
        json.dumps(
            {
                "pid": pid,
                "host": host,
                "port": port,
                "url": studio_url(host, port),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def clear_studio_runtime() -> None:
    STUDIO_RUNTIME_FILE.unlink(missing_ok=True)


def studio_runtime_info(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> dict[str, Any]:
    runtime = load_studio_runtime()
    runtime_host = str(runtime.get("host", host)) if runtime else host
    runtime_port = int(runtime.get("port", port)) if runtime else port
    runtime_url = studio_url(runtime_host, runtime_port)
    pid = int(runtime.get("pid", 0)) if runtime else 0
    port_open = port_is_open(runtime_host, runtime_port)
    pid_ok = _pid_alive(pid) if pid else False

    if not port_open:
        if runtime and not pid_ok:
            clear_studio_runtime()
        return {
            "running": False,
            "url": studio_url(host, port),
            "host": host,
            "port": port,
            "pid": None,
            "managed": False,
            "port_open": False,
        }

    return {
        "running": True,
        "url": str(runtime.get("url", runtime_url)) if runtime else runtime_url,
        "host": runtime_host,
        "port": runtime_port,
        "pid": pid if pid_ok else None,
        "managed": pid_ok,
        "port_open": True,
    }


def stop_studio_server(timeout_seconds: float = 3.0) -> dict[str, Any]:
    info = studio_runtime_info()
    if not info.get("running"):
        clear_studio_runtime()
        return {"stopped": True, "was_running": False, "managed": False}

    pid = info.get("pid")
    managed = bool(info.get("managed"))
    if pid and _pid_alive(int(pid)):
        os.kill(int(pid), signal.SIGTERM)
        deadline = timeout_seconds
        while deadline > 0 and _pid_alive(int(pid)):
            threading.Event().wait(0.1)
            deadline -= 0.1
        if _pid_alive(int(pid)):
            os.kill(int(pid), signal.SIGKILL)
    clear_studio_runtime()
    host = str(info.get("host", DEFAULT_HOST))
    port = int(info.get("port", DEFAULT_PORT))
    return {
        "stopped": not port_is_open(host, port),
        "was_running": True,
        "managed": managed,
        "url": info.get("url"),
    }


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return b""
    return handler.rfile.read(length)


def _serve_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    if not path.is_file():
        handler.send_error(404)
        return
    data = path.read_bytes()
    mime, _ = mimetypes.guess_type(str(path))
    handler.send_response(200)
    handler.send_header("Content-Type", mime or "application/octet-stream")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _base_pack_payload() -> dict[str, Any]:
    meta = core.load_base_pack_meta() or {}
    return {
        "ready": core.base_pack_ready(),
        "language": meta.get("language"),
        "url": meta.get("url"),
        "file_count": meta.get("file_count"),
    }


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "X20VoiceStudio/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        try:
            self._route_get()
        except FileNotFoundError as exc:
            _json_response(self, 404, {"ok": False, "error": str(exc)})
        except Exception as exc:
            _json_response(self, 500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:
        try:
            self._route_post()
        except FileNotFoundError as exc:
            _json_response(self, 404, {"ok": False, "error": str(exc)})
        except ValueError as exc:
            _json_response(self, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            _json_response(self, 500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def do_PUT(self) -> None:
        try:
            self._route_put()
        except FileNotFoundError as exc:
            _json_response(self, 404, {"ok": False, "error": str(exc)})
        except ValueError as exc:
            _json_response(self, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            _json_response(self, 500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def do_DELETE(self) -> None:
        try:
            self._route_delete()
        except FileNotFoundError as exc:
            _json_response(self, 404, {"ok": False, "error": str(exc)})
        except ValueError as exc:
            _json_response(self, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            _json_response(self, 500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _route_get(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return _serve_file(self, WEB_DIR / "index.html")
        if path == "/app.js":
            return _serve_file(self, WEB_DIR / "app.js")
        if path == "/styles.css":
            return _serve_file(self, WEB_DIR / "styles.css")

        if path == "/api/languages":
            from voice_catalog import enrich_languages, fetch_voice_catalog

            return _json_response(
                self,
                200,
                {
                    "ok": True,
                    "languages": enrich_languages(fetch_voice_catalog()),
                    "base_pack": _base_pack_payload(),
                },
            )

        if path == "/api/packs":
            return _json_response(self, 200, {"ok": True, "packs": packs.list_packs()})

        m = re.fullmatch(r"/api/packs/([^/]+)/files", path)
        if m:
            pack_id = unquote(m.group(1))
            return _json_response(
                self,
                200,
                {"ok": True, "pack": packs.get_pack(pack_id), "files": packs.list_pack_files(pack_id)},
            )

        m = re.fullmatch(r"/api/packs/([^/]+)", path)
        if m:
            pack_id = unquote(m.group(1))
            return _json_response(self, 200, {"ok": True, "pack": packs.get_pack(pack_id)})

        m = re.fullmatch(r"/api/packs/([^/]+)/audio/([^/]+)", path)
        if m:
            pack_id = unquote(m.group(1))
            file_name = unquote(m.group(2))
            audio = packs._audio_dir(pack_id) / file_name
            return _serve_file(self, audio)

        m = re.fullmatch(r"/api/original/([^/]+)", path)
        if m:
            file_name = unquote(m.group(1))
            original = core.base_audio_dir() / file_name
            return _serve_file(self, original)

        self.send_error(404)

    def _route_post(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/download-base":
            body = _read_json(self)
            language = str(body.get("language", core.DEFAULT_BASE_LANGUAGE)).strip().lower()
            reset_working = bool(body.get("reset_working", True))
            result = core.download_base_pack(language, reset_working=reset_working)
            return _json_response(self, 200, {"ok": True, "data": result, "base_pack": _base_pack_payload()})

        if path == "/api/packs":
            body = _read_json(self)
            name = str(body.get("name", "")).strip()
            if not name:
                raise ValueError("Pack name is required.")
            from voice_catalog import validate_install_language

            language = validate_install_language(str(body.get("language", "")))
            pack = packs.create_pack(name, language=language)
            return _json_response(self, 201, {"ok": True, "pack": pack})

        m = re.fullmatch(r"/api/packs/([^/]+)/activate", path)
        if m:
            pack_id = unquote(m.group(1))
            pack = packs.set_active_pack(pack_id)
            return _json_response(self, 200, {"ok": True, "pack": pack})

        self.send_error(404)

    def _route_put(self) -> None:
        path = urlparse(self.path).path
        m = re.fullmatch(r"/api/packs/([^/]+)/files/([^/]+)", path)
        if not m:
            self.send_error(404)
            return
        pack_id = unquote(m.group(1))
        file_name = unquote(m.group(2))
        data = _read_body(self)
        pack = packs.replace_file(pack_id, file_name, data)
        _json_response(self, 200, {"ok": True, "pack": pack, "file": file_name})

    def _route_delete(self) -> None:
        path = urlparse(self.path).path
        m = re.fullmatch(r"/api/packs/([^/]+)/files/([^/]+)", path)
        if m:
            pack_id = unquote(m.group(1))
            file_name = unquote(m.group(2))
            pack = packs.revert_file(pack_id, file_name)
            _json_response(self, 200, {"ok": True, "pack": pack, "file": file_name})
            return

        m = re.fullmatch(r"/api/packs/([^/]+)", path)
        if m:
            pack_id = unquote(m.group(1))
            packs.delete_pack(pack_id)
            _json_response(self, 200, {"ok": True, "deleted": pack_id})
            return

        self.send_error(404)


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    packs.ensure_layout()

    def _handle_stop(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _handle_stop)

    httpd = ThreadingHTTPServer((host, port), StudioHandler)
    url = studio_url(host, port)
    write_studio_runtime(host, port, os.getpid())
    print(f"Voice Pack Studio running at {url}")
    if core.base_pack_ready():
        meta = core.load_base_pack_meta() or {}
        print(f"Base pack: {meta.get('language', 'unknown')} ({core.EXPECTED_COUNT} files)")
    else:
        print("No base pack yet — choose a language in the browser and download.")
    print("Press Ctrl+C to stop. Your progress is saved after each file upload.")

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStudio stopped.")
    finally:
        clear_studio_runtime()
        httpd.server_close()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Xiaomi X20 Voice Pack Studio web server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
