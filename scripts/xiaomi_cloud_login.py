"""Xiaomi cloud login helpers for the X20 voice tool."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, urlparse

import requests

try:
    from Crypto.Cipher import ARC4
except ModuleNotFoundError:
    from Cryptodome.Cipher import ARC4

DEFAULT_ACCESS_KEY = "IOS00026747c5acafc2"
ACCOUNT_LOGIN_URL = (
    "https://account.xiaomi.com/fe/service/login?sid=xiaomiio&_locale=en_GB&_snsNone=true"
)
HOME_MI_URL = "https://home.mi.com/"


@dataclass
class LoginResult:
    user_id: str
    ssecurity: str
    service_token: str
    region: str = "de"


@dataclass
class DeviceInfo:
    did: str
    name: str
    model: str
    region: str


class XiaomiCloudConnector:
    def __init__(self) -> None:
        self._agent = self.generate_agent()
        self._device_id = self.generate_device_id()
        self._session = requests.session()
        self._ssecurity: str | None = None
        self.user_id: str | None = None
        self._service_token: str | None = None

    @staticmethod
    def generate_agent() -> str:
        agent_id = "".join(chr(random.randint(65, 69)) for _ in range(13))
        random_text = "".join(chr(random.randint(97, 122)) for _ in range(18))
        return f"{random_text}-{agent_id} APP/com.xiaomi.mihome APPV/10.5.201"

    @staticmethod
    def generate_device_id() -> str:
        return "".join(chr(random.randint(97, 122)) for _ in range(6))

    @staticmethod
    def get_api_url(country: str) -> str:
        prefix = "" if country == "cn" else f"{country}."
        return f"https://{prefix}api.io.mi.com/app"

    @staticmethod
    def to_json(response_text: str) -> dict:
        return json.loads(response_text.replace("&&&START&&&", ""))

    @staticmethod
    def encrypt_rc4(password: str, payload: str) -> str:
        cipher = ARC4.new(base64.b64decode(password))
        cipher.encrypt(bytes(1024))
        return base64.b64encode(cipher.encrypt(payload.encode())).decode()

    @staticmethod
    def decrypt_rc4(password: str, payload: str) -> str:
        cipher = ARC4.new(base64.b64decode(password))
        cipher.encrypt(bytes(1024))
        return cipher.encrypt(base64.b64decode(payload)).decode()

    def signed_nonce(self, nonce: str) -> str:
        digest = hashlib.sha256(base64.b64decode(self._ssecurity) + base64.b64decode(nonce)).digest()
        return base64.b64encode(digest).decode()

    @staticmethod
    def generate_nonce(millis: int | None = None) -> str:
        millis = millis or round(time.time() * 1000)
        nonce_bytes = os.urandom(8) + int(millis / 60000).to_bytes(4, byteorder="big")
        return base64.b64encode(nonce_bytes).decode()

    def generate_enc_signature(self, url: str, method: str, signed_nonce: str, params: dict[str, str]) -> str:
        parts = [method.upper(), url.split("com", 1)[1].replace("/app/", "/")]
        for key, value in params.items():
            parts.append(f"{key}={value}")
        parts.append(signed_nonce)
        return base64.b64encode(hashlib.sha1("&".join(parts).encode()).digest()).decode()

    def generate_enc_params(
        self, url: str, method: str, signed_nonce: str, nonce: str, params: dict[str, str]
    ) -> dict[str, str]:
        params = dict(params)
        params["rc4_hash__"] = self.generate_enc_signature(url, method, signed_nonce, params)
        for key in list(params):
            params[key] = self.encrypt_rc4(signed_nonce, params[key])
        params.update(
            {
                "signature": self.generate_enc_signature(url, method, signed_nonce, params),
                "ssecurity": self._ssecurity,
                "_nonce": nonce,
            }
        )
        return params

    def execute_api_call_encrypted(self, url: str, params: dict[str, str]) -> dict | None:
        headers = {
            "Accept-Encoding": "identity",
            "User-Agent": self._agent,
            "Content-Type": "application/x-www-form-urlencoded",
            "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
            "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        }
        cookies = {
            "userId": str(self.user_id),
            "yetAnotherServiceToken": str(self._service_token),
            "serviceToken": str(self._service_token),
            "locale": "en_GB",
            "timezone": "GMT+00:00",
            "channel": "MI_APP_STORE",
        }
        millis = round(time.time() * 1000)
        nonce = self.generate_nonce(millis)
        signed = self.signed_nonce(nonce)
        fields = self.generate_enc_params(url, "POST", signed, nonce, params)
        response = self._session.post(url, headers=headers, cookies=cookies, params=fields, timeout=30)
        if response.status_code != 200:
            return None
        decoded = self.decrypt_rc4(self.signed_nonce(fields["_nonce"]), response.text)
        return json.loads(decoded)

    def get_homes(self, country: str) -> dict | None:
        url = self.get_api_url(country) + "/v2/homeroom/gethome"
        params = {"data": '{"fg": true, "fetch_share": true, "fetch_share_dev": true, "limit": 300, "app_ver": 7}'}
        return self.execute_api_call_encrypted(url, params)

    def get_devices(self, country: str, home_id: int, owner_id: str) -> dict | None:
        url = self.get_api_url(country) + "/v2/home/home_device_list"
        params = {
            "data": json.dumps(
                {
                    "home_owner": owner_id,
                    "home_id": home_id,
                    "limit": 200,
                    "get_split_device": True,
                    "support_smart_home": True,
                },
                separators=(",", ":"),
            )
        }
        return self.execute_api_call_encrypted(url, params)

    def get_dev_cnt(self, country: str) -> dict | None:
        url = self.get_api_url(country) + "/v2/user/get_device_cnt"
        params = {"data": '{"fetch_own": true, "fetch_share": true}'}
        return self.execute_api_call_encrypted(url, params)

    def install_service_token_cookies(self, token: str) -> None:
        for domain in [".api.io.mi.com", ".io.mi.com", ".mi.com"]:
            self._session.cookies.set("serviceToken", token, domain=domain)
            self._session.cookies.set("yetAnotherServiceToken", token, domain=domain)

    def login_result(self, region: str) -> LoginResult:
        if not self.user_id or not self._ssecurity or not self._service_token:
            raise RuntimeError("Login is incomplete.")
        return LoginResult(
            user_id=str(self.user_id),
            ssecurity=str(self._ssecurity),
            service_token=str(self._service_token),
            region=region,
        )


class QrLogin(XiaomiCloudConnector):
    def __init__(self) -> None:
        super().__init__()
        self.qr_image_url: str | None = None
        self.login_url: str | None = None
        self.long_polling_url: str | None = None
        self.timeout_seconds: int = 120

    def prepare(self) -> None:
        url = "https://account.xiaomi.com/longPolling/loginUrl"
        params = {
            "_qrsize": "480",
            "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "callback": "https://sts.api.io.mi.com/sts",
            "_hasLogo": "false",
            "sid": "xiaomiio",
            "serviceParam": "",
            "_locale": "en_GB",
            "_dc": str(int(time.time() * 1000)),
        }
        response = self._session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = self.to_json(response.text)
        self.qr_image_url = data["qr"]
        self.login_url = data["loginUrl"]
        self.long_polling_url = data["lp"]
        self.timeout_seconds = int(data.get("timeout", 120))

    def fetch_qr_bytes(self) -> bytes:
        if not self.qr_image_url:
            raise RuntimeError("QR login was not prepared.")
        response = self._session.get(self.qr_image_url, timeout=30)
        response.raise_for_status()
        return response.content

    def wait_for_scan(self, on_tick: Callable[[str], None] | None = None) -> None:
        if not self.long_polling_url:
            raise RuntimeError("QR login was not prepared.")
        started = time.time()
        while time.time() - started < self.timeout_seconds:
            if on_tick:
                remaining = max(0, int(self.timeout_seconds - (time.time() - started)))
                on_tick(f"Waiting for phone confirmation... {remaining}s left")
            try:
                response = self._session.get(self.long_polling_url, timeout=15)
            except requests.exceptions.Timeout:
                continue
            if response.status_code != 200:
                time.sleep(1)
                continue
            data = self.to_json(response.text)
            self.user_id = data["userId"]
            self._ssecurity = data["ssecurity"]
            self._pass_token = data.get("passToken")
            location = data["location"]
            token_response = self._session.get(location, timeout=30)
            token_response.raise_for_status()
            self._service_token = token_response.cookies.get("serviceToken")
            if not self._service_token:
                raise RuntimeError("Login succeeded but serviceToken cookie was missing.")
            self.install_service_token_cookies(self._service_token)
            return
        raise TimeoutError("QR login timed out. Scan the code and confirm on your phone.")


class PasswordLogin(XiaomiCloudConnector):
    def login(self, username: str, password: str) -> None:
        self._session.cookies.set("sdkVersion", "accountsdk-18.8.15", domain="mi.com")
        self._session.cookies.set("deviceId", self._device_id, domain="mi.com")

        url = "https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true"
        response = self._session.get(url, headers={"User-Agent": self._agent}, cookies={"userId": username}, timeout=30)
        step1 = self.to_json(response.text)
        sign = step1.get("_sign")
        if not sign and "ssecurity" in step1:
            self._ssecurity = step1["ssecurity"]
            self.user_id = step1["userId"]
            location = step1["location"]
        else:
            auth_url = "https://account.xiaomi.com/pass/serviceLoginAuth2"
            fields = {
                "sid": "xiaomiio",
                "hash": hashlib.md5(password.encode()).hexdigest().upper(),
                "callback": "https://sts.api.io.mi.com/sts",
                "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
                "user": username,
                "_sign": sign,
                "_json": "true",
            }
            response = self._session.post(auth_url, headers={"User-Agent": self._agent}, params=fields, timeout=30)
            auth = self.to_json(response.text)
            if "notificationUrl" in auth:
                raise RuntimeError("Two-factor authentication is required. Use QR login instead.")
            if "ssecurity" not in auth:
                raise RuntimeError("Invalid username or password.")
            self._ssecurity = auth["ssecurity"]
            self.user_id = auth.get("userId")
            location = auth.get("location")

        if not location:
            raise RuntimeError("Login did not return a token location.")

        token_response = self._session.get(location, headers={"User-Agent": self._agent}, timeout=30)
        token_response.raise_for_status()
        self._service_token = token_response.cookies.get("serviceToken")
        if not self._service_token:
            raise RuntimeError("Login succeeded but serviceToken cookie was missing.")
        self.install_service_token_cookies(self._service_token)


def discover_devices(connector: XiaomiCloudConnector, region: str) -> list[DeviceInfo]:
    devices: list[DeviceInfo] = []
    homes: list[dict] = []

    homes_response = connector.get_homes(region)
    if homes_response and homes_response.get("result", {}).get("homelist"):
        for home in homes_response["result"]["homelist"]:
            homes.append({"home_id": home["id"], "home_owner": connector.user_id})

    dev_cnt = connector.get_dev_cnt(region)
    if dev_cnt and dev_cnt.get("result", {}).get("share", {}).get("share_family"):
        for home in dev_cnt["result"]["share"]["share_family"]:
            homes.append({"home_id": home["home_id"], "home_owner": home["home_owner"]})

    seen: set[str] = set()
    for home in homes:
        response = connector.get_devices(region, home["home_id"], str(home["home_owner"]))
        if not response or not response.get("result", {}).get("device_info"):
            continue
        for device in response["result"]["device_info"]:
            did = str(device.get("did", ""))
            if not did or did in seen:
                continue
            seen.add(did)
            devices.append(
                DeviceInfo(
                    did=did,
                    name=str(device.get("name", "Unknown device")),
                    model=str(device.get("model", "unknown")),
                    region=region,
                )
            )
    return devices


def find_vacuum_devices(devices: list[DeviceInfo]) -> list[DeviceInfo]:
    return [device for device in devices if "vacuum" in device.model.lower()]


XIAOMI_CLOUD_REGIONS = ("de", "us", "ru", "sg", "in", "tw", "cn", "i2")


def _looks_like_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("429", "rate", "too many", "limit", "频率"))


def discover_vacuum_robots(
    connector: XiaomiCloudConnector,
    *,
    regions: tuple[str, ...] = XIAOMI_CLOUD_REGIONS,
    delay_seconds: float = 0.75,
    on_progress: Callable[[str], None] | None = None,
) -> list[DeviceInfo]:
    """Scan Xiaomi cloud regions and return vacuum robots (skips empty regions)."""
    found: list[DeviceInfo] = []
    seen: set[str] = set()
    total = len(regions)

    for index, region in enumerate(regions, start=1):
        if on_progress:
            on_progress(f"Scanning region {region} ({index}/{total})...")

        def load_region() -> list[DeviceInfo]:
            devices = discover_devices(connector, region)
            return find_vacuum_devices(devices)

        try:
            vacuums = load_region()
        except Exception as exc:
            if _looks_like_rate_limit(exc):
                if on_progress:
                    on_progress(f"Rate limited on {region}, retrying in 2s...")
                time.sleep(2.0)
                try:
                    vacuums = load_region()
                except Exception:
                    vacuums = []
            else:
                vacuums = []

        added = 0
        for device in vacuums:
            if device.did in seen:
                continue
            seen.add(device.did)
            found.append(device)
            added += 1

        if on_progress and added:
            on_progress(f"Found {added} robot(s) in {region}.")

        if index < total:
            time.sleep(delay_seconds)

    return found


def discover_devices_all_regions(
    connector: XiaomiCloudConnector,
    *,
    regions: tuple[str, ...] = XIAOMI_CLOUD_REGIONS,
    delay_seconds: float = 0.75,
    on_progress: Callable[[str], None] | None = None,
) -> list[DeviceInfo]:
    """Scan Xiaomi cloud regions and return all devices (deduplicated by DID)."""
    found: list[DeviceInfo] = []
    seen: set[str] = set()
    total = len(regions)

    for index, region in enumerate(regions, start=1):
        if on_progress:
            on_progress(f"Scanning region {region} ({index}/{total})...")

        def load_region() -> list[DeviceInfo]:
            return discover_devices(connector, region)

        try:
            devices = load_region()
        except Exception as exc:
            if _looks_like_rate_limit(exc):
                if on_progress:
                    on_progress(f"Rate limited on {region}, retrying in 2s...")
                time.sleep(2.0)
                try:
                    devices = load_region()
                except Exception:
                    devices = []
            else:
                devices = []

        added = 0
        for device in devices:
            if device.did in seen:
                continue
            seen.add(device.did)
            found.append(device)
            added += 1

        if on_progress and added:
            on_progress(f"Found {added} device(s) in {region}.")

        if index < total:
            time.sleep(delay_seconds)

    return found


def build_config(login: LoginResult, did: str, access_key: str = DEFAULT_ACCESS_KEY) -> dict[str, str]:
    return {
        "region": login.region,
        "did": did,
        "userId": login.user_id,
        "ssecurity": login.ssecurity,
        "serviceToken": login.service_token,
        "accessKey": access_key,
        "endpoint": f"https://{login.region}.core.api.io.mi.com/app/miotspec/action",
    }


def build_config_with_devices(
    login: LoginResult,
    devices: list[DeviceInfo],
    access_key: str = DEFAULT_ACCESS_KEY,
) -> dict:
    if not devices:
        raise ValueError("At least one vacuum robot must be selected.")
    primary = devices[0]
    login.region = primary.region
    config = build_config(login, primary.did, access_key)
    config["vacuum_devices"] = [
        {
            "did": device.did,
            "name": device.name,
            "model": device.model,
            "region": device.region,
            "enabled": True,
        }
        for device in devices
    ]
    return config


def connector_from_login(login: LoginResult) -> XiaomiCloudConnector:
    connector = XiaomiCloudConnector()
    connector.user_id = login.user_id
    connector._ssecurity = login.ssecurity
    connector._service_token = login.service_token
    connector.install_service_token_cookies(login.service_token)
    return connector
