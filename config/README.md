# Config files in this repository

## Public files (safe to commit and share)

| File | Purpose |
|---|---|
| `config.example.json` | Example shape for your live session file |
| `README.md` | This document |

## Private files (never commit — created on your machine)

| File | Purpose |
|---|---|
| `config.json` | Your live Xiaomi cloud session (tokens, robot DID) |
| `.connection-ok` | Hash marker that `config.json` was tested successfully |

Both private files are in `.gitignore` and saved with restrictive permissions (`600`).

## How sign-in works

The menu or `./x20-voice-tool.sh --cli configure` saves everything into **`config.json`**.

You do **not** need any other config file for normal use.

After a successful login test, the tool writes **`.connection-ok`** containing a SHA-256 hash of `config.json`. TUI “Account [OK]” and `config_ready()` require both files to match. If you edit `config.json` by hand, sign in again or run configure to refresh the marker.

## Required fields in `config.json`

| Field | Meaning |
|---|---|
| `region` | Xiaomi cloud region, for example `de` |
| `did` | Primary robot device ID |
| `userId` | Your Xiaomi account user ID |
| `ssecurity` | Session security value from Xiaomi login |
| `serviceToken` | Session token from Xiaomi login |
| `accessKey` | Usually `IOS00026747c5acafc2` |
| `endpoint` | `https://<region>.core.api.io.mi.com/app/miotspec/action` |

## Optional: multiple robots

When you select more than one vacuum, the tool also saves:

```json
"vacuum_devices": [
  {
    "did": "123456789",
    "name": "Living room robot",
    "model": "dreame.vacuum.p2187",
    "enabled": true
  }
]
```

## CLI automation (advanced)

For scripts, pass credentials via environment variables (`XIAOMI_USER_ID`, `XIAOMI_SERVICE_TOKEN`, …) or CLI flags — see [CLI.md](../docs/CLI.md). No extra file in `config/` is required.
