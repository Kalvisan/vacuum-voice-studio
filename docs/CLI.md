# CLI mode

Use CLI mode for scripts, automation, and AI agents.

## Enable CLI mode

```bash
./x20-voice-tool.sh --cli <command> [options]
./x20-voice-tool.sh status --json          # subcommands also work
export X20_VOICE_CLI=1
./x20-voice-tool.sh status
```

Global flags (work with any command):

| Flag | Purpose |
|---|---|
| `--json` | Machine-readable JSON output |
| `--no-tui` | Skip Textual UI dependency checks in `readiness` and `deps` |

Notes:

- `./x20-voice-tool.sh` with no arguments starts the menu (TUI)
- Any explicit subcommand runs in CLI mode
- Add `--json` for machine-readable output

## JSON output shape

Success:

```json
{
  "ok": true,
  "command": "status",
  "data": {
    "devices": [
      {
        "did": "123456789",
        "name": "Living room",
        "model": "dreame.vacuum.p2187",
        "status": {
          "target": "ru",
          "current": "ru",
          "status": 4,
          "progress": 100
        },
        "ok": true
      }
    ]
  }
}
```

Failure:

```json
{
  "ok": false,
  "command": "install",
  "error": "Robot did not confirm a successful install.",
  "hint": "Check robot online status and session values in config/config.json"
}
```

## Command reference

| Command | Purpose |
|---|---|
| `readiness` | Check deps, saved session, workspace, ZIP |
| `virusscan` | Scan repo source for suspicious code and secrets |
| `deps` | Install Python dependencies |
| `configure` | Save and validate Xiaomi session |
| `devices list` | List robots on your account |
| `download` | Download official base pack (`--language ru`) |
| `languages list` | List Xiaomi voice pack languages |
| `studio` | Voice Pack Studio (web editor) |
| `pack list` / `pack create` | Manage saved voice pack projects |
| `robot commands list` | List robot control command IDs |
| `robot snapshot` | Live robot status (battery, task, voice) |
| `robot run <id>` | Send MIoT action (clean, dock, charge, …) |
| `status` | Read robot voice status |
| `build` | Build ZIP from the active studio pack |
| `install` | Upload and install custom ZIP (language from pack/base if omitted) |
| `official` | Install stock Xiaomi language pack |
| `run` | Pipeline: deps, configure, download, build, install |

**Voice file numbers:** [VOICE_FILE_MAP.md](VOICE_FILE_MAP.md) — which MP3 matches which robot phrase.

## Flag reference

### `readiness`

| Flag | Purpose |
|---|---|
| `--skip-bootstrap` | Skip session inspection before reporting |
| `--skip-validate` | Load session metadata without live API check |
| `--require-valid` | Exit with error if session missing or expired |

### `virusscan`

| Flag | Purpose |
|---|---|
| `--clamav` | Also run ClamAV if installed |

### `configure`

| Flag | Purpose |
|---|---|
| `--method password\|cookies\|qr` | Login method (default: cookies) |
| `--from-file PATH` | Import existing config JSON |
| `--use-existing` | Validate saved `config/config.json` |
| `--region REGION` | Primary cloud region (default: `de`) |
| `--did DID` | Primary robot DID (searches all regions) |
| `--dids DID` | Additional DID (repeat or comma-separated; searches all regions) |
| `--all-vacuums` | Save all vacuum robots (scans all regions) |
| `--auto-did` | Pick automatically when only one device matches |
| `--skip-test` | Save without live robot status test |
| `--open-browser` | For QR login, open browser and QR image |
| `--access-key KEY` | Advanced: Xiaomi access key override |

Environment variables for login (alternative to flags):

| Variable | Used by |
|---|---|
| `XIAOMI_USERNAME` | `--method password` |
| `XIAOMI_PASSWORD` | `--method password` |
| `XIAOMI_USER_ID` | `--method cookies` |
| `XIAOMI_SERVICE_TOKEN` | `--method cookies` |
| `XIAOMI_SSECURITY` | `--method cookies` |

### `devices list`

| Flag | Purpose |
|---|---|
| `--region REGION` | Single-region scan (default: `de`) |
| `--all-regions` | Scan all Xiaomi cloud regions (matches TUI discovery) |
| `--vacuums-only` | Return vacuum robots only |
| `--from-config` | Use saved `config/config.json` credentials |
| `--method cookies\|password` | Login method when not using `--from-config` |

### `download`

| Flag | Purpose |
|---|---|
| `--language CODE` | Language code (default: `en`) |
| `--keep-working` | Do not reset `workspace/working_pack` |

### `languages list`

| Flag | Purpose |
|---|---|
| `--refresh` | Refresh catalog from Xiaomi |

### `studio`

| Flag | Purpose |
|---|---|
| `--host HOST` | Bind address (default: `127.0.0.1`) |
| `--port PORT` | Port (default: `8765`) |
| `--no-open` | Do not open a browser window |
| `--background` | Start server in background and return PID |
| `--stop` | Stop a background Studio server |

### `pack`

| Subcommand | Flags |
|---|---|
| `list` | — |
| `create` | `--name NAME` (required), `--language CODE` |

### `robot`

| Subcommand | Flags |
|---|---|
| `commands list` | — |
| `snapshot` | `--did DID`, `--all-devices` |
| `run COMMAND_ID` | `--did DID`, `--all-devices` |

Robot command IDs (same as TUI robot panel):

| ID | Action |
|---|---|
| `start_sweep` | Start clean |
| `start_sweep_mop` | Sweep + mop |
| `start_mop` | Mop only |
| `pause` | Pause |
| `continue` | Continue |
| `stop` | Stop |
| `dock` | Return home |
| `charge` | Charge |
| `identify` | Locate (play sound) |

### `status` / `install`

| Flag | Purpose |
|---|---|
| `--did DID` | Target one robot |
| `--all-devices` | All enabled vacuum robots |

### `build`

| Flag | Purpose |
|---|---|
| `--output PATH` | Output ZIP path |
| `--no-lang-alias` | Do not also write `output/<language>.zip` |

### `install`

| Flag | Purpose |
|---|---|
| `--archive PATH` | ZIP path (default: `output/custom_voice_101.zip`) |
| `--language CODE` | Install language (defaults from active pack) |
| `--suffix NAME` | Upload suffix (default: `<language>.zip`) |
| `--wait-seconds N` | Wait for robot confirmation (default: 180) |

### `official`

| Flag | Purpose |
|---|---|
| `--language CODE` | Language code (default: `en`) |
| `--wait-seconds N` | Wait for confirmation (default: 180) |

### `run` (pipeline)

| Flag | Purpose |
|---|---|
| `--skip-configure` | Skip configure step |
| `--skip-download` | Skip download step |
| `--archive PATH` | ZIP for install step |
| `--language CODE` | Install language |
| `--open-browser` | For QR configure in pipeline |

## Session handling

```bash
# Validate saved session against Xiaomi cloud
./x20-voice-tool.sh --cli configure --use-existing --json

# Readiness also validates by default
./x20-voice-tool.sh --cli readiness --json

# Skip live validation for a fast local check
./x20-voice-tool.sh --cli readiness --skip-validate --json

# Fail if session is missing or expired
./x20-voice-tool.sh --cli readiness --require-valid --json
```

Session states returned in bootstrap data:

| State | Meaning |
|---|---|
| `no_file` | No saved sign-in yet |
| `valid` | Saved sign-in works |
| `expired` | Saved sign-in must be refreshed |
| `invalid` | Config file is incomplete |

## Multiple robots

```bash
# Discover all vacuum robots (all regions — no manual region guess)
./x20-voice-tool.sh --cli devices list --all-regions --vacuums-only --json

# Save all vacuum robots on the account
./x20-voice-tool.sh --cli configure \
  --method cookies \
  --user-id ... \
  --service-token ... \
  --ssecurity ... \
  --all-vacuums \
  --json

# Save specific robots by DID (region resolved automatically)
./x20-voice-tool.sh --cli configure \
  --method cookies \
  ... \
  --dids 111111,222222 \
  --json

# Query, control, or install on all enabled robots
./x20-voice-tool.sh --cli status --all-devices --json
./x20-voice-tool.sh --cli robot snapshot --all-devices --json
./x20-voice-tool.sh --cli robot run start_sweep --all-devices --json
./x20-voice-tool.sh --cli install --all-devices --json
```

## Typical workflows

### Human CLI

```bash
./x20-voice-tool.sh --cli deps
./x20-voice-tool.sh --cli configure --method qr --open-browser --auto-did
./x20-voice-tool.sh --cli languages list --json
./x20-voice-tool.sh --cli download --language ru
./x20-voice-tool.sh --cli pack create --name "My Russian voice" --language ru
./x20-voice-tool.sh --cli studio --background --json
./x20-voice-tool.sh --cli build
./x20-voice-tool.sh --cli install --language ru --json
./x20-voice-tool.sh --cli studio --stop --json
```

### AI agent

```bash
./x20-voice-tool.sh --cli readiness --require-valid --json
./x20-voice-tool.sh --cli install --archive output/ru.zip --language ru --json
```

## Configure methods

### Reuse saved config

```bash
./x20-voice-tool.sh --cli configure --use-existing --json
./x20-voice-tool.sh --cli configure --from-file config/config.json --json
```

### Cookie values

```bash
./x20-voice-tool.sh --cli configure \
  --method cookies \
  --user-id "..." \
  --service-token "..." \
  --ssecurity "..." \
  --did "..." \
  --json
```

### Password login

```bash
./x20-voice-tool.sh --cli configure \
  --method password \
  --username "..." \
  --password "..." \
  --region de \
  --auto-did \
  --json
```

### QR login

```bash
./x20-voice-tool.sh --cli configure \
  --method qr \
  --open-browser \
  --auto-did \
  --json
```

## Pipeline command

```bash
./x20-voice-tool.sh --cli run \
  --skip-configure \
  --skip-download \
  --archive output/ru.zip \
  --language ru \
  --json
```

Useful flags:

- `--skip-configure` when `config/config.json` is already valid
- `--skip-download` when the base pack is already downloaded

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Command failed |

## Private vs public files

Public in git:

- `config/config.example.json`

Private on your machine:

- `config/config.json`
- `config/.connection-ok`

See [config/README.md](../config/README.md).
