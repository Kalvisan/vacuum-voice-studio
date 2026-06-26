---
name: xiaomi-x20-voice-pack
description: >-
  Install and manage custom voice packs on Xiaomi Robot Vacuum X20 Max
  (xiaomi.vacuum.d109gl). Covers CLI workflow, session setup, MP3 file mapping,
  build, cloud install, multi-robot control, and status checks. Use when the user
  mentions X20, X20 Max, d109gl, voice pack, custom robot sounds, Mi Home
  vacuum voice, or x20-voice-tool.
---

# Xiaomi X20 voice pack tool

## Scope

- Robot: **Xiaomi Robot Vacuum X20 Max**, model `xiaomi.vacuum.d109gl`
- Repo entry: `./x20-voice-tool.sh` from project root
- Voice pack: exactly **101** numbered MP3 files; replace by file name only

## Before any install

```bash
./x20-voice-tool.sh --cli readiness --require-valid --json
```

If `state` is `expired` or `no_file`, configure session before other steps.

Never commit or expose `config/config.json` (tokens). Never run `source x20-voice-tool.sh`.

## Which MP3 to replace

Read [docs/VOICE_FILE_MAP.md](../../docs/VOICE_FILE_MAP.md) or parse [assets/d109gl_en_transcriptions.csv](../../assets/d109gl_en_transcriptions.csv).

User says a phrase → look up file (e.g. stuck → `720.mp3`). Replacement saved in `workspace/packs/<id>/audio/`.

## Standard workflow

```bash
# 1. Session
./x20-voice-tool.sh --cli configure --use-existing --json

# 2. Original pack + studio
./x20-voice-tool.sh --cli download --json
./x20-voice-tool.sh --cli studio --background --json

# 3. User/agent edits in Voice Pack Studio (auto-saved to workspace/packs/)

# 4. Build (syncs active pack → working_pack)
./x20-voice-tool.sh --cli build --json

# 5. Install
./x20-voice-tool.sh --cli install --all-devices --json

# 6. Verify
./x20-voice-tool.sh --cli status --all-devices --json
```

## Multi-robot

```bash
./x20-voice-tool.sh --cli configure ... --all-vacuums --json
./x20-voice-tool.sh --cli install --all-devices --language ru --json
./x20-voice-tool.sh --cli status --all-devices --json
```

Menu equivalent: **Choose which robot(s) to control**.

## Configure methods

| Method | When |
|---|---|
| `--use-existing` | Valid saved `config/config.json` |
| `--method qr --open-browser` | Human at keyboard |
| `--method cookies` + env vars | Automation with pasted session |
| `--method password` | Username/password |
| `--all-vacuums` / `--dids A,B` | Multiple robots (auto-scans all regions) |

`--all-vacuums` and `--dids` scan all Xiaomi cloud regions — no manual region guess. For discovery only: `devices list --all-regions --vacuums-only --json`.

## Robot control (CLI)

Same actions as TUI robot panel `[R]`:

```bash
./x20-voice-tool.sh --cli robot commands list --json
./x20-voice-tool.sh --cli robot snapshot --all-devices --json
./x20-voice-tool.sh --cli robot run dock --all-devices --json
```

Command IDs: `start_sweep`, `start_sweep_mop`, `start_mop`, `pause`, `continue`, `stop`, `dock`, `charge`, `identify`.

## Restore factory English

```bash
./x20-voice-tool.sh --cli official --language en --json
```

## Hard rules

- Do not add/remove/rename MP3 files in the pack (101 files, numeric names only)
- Do not publish tokens, `config.json`, or Xiaomi downloaded audio
- Use `--json` for machine-readable output in agent loops
- Install uploads to Xiaomi FDS; robot does not fetch from user's PC directly

## Errors

| Symptom | Action |
|---|---|
| Session expired | Re-run configure |
| Wrong file count on build | Re-run download, then fix files in Voice Pack Studio |
| Install not 100% | Check robot online; try official pack first |
| Terminal broken | User must run `./x20-voice-tool.sh` not `source` |

More: [docs/TROUBLESHOOTING.md](../../docs/TROUBLESHOOTING.md)

## Reference docs

- [docs/STUDIO.md](../../docs/STUDIO.md) — web editor
- [docs/CLI.md](../../docs/CLI.md) — all commands
- [docs/AI_ASSISTANT.md](../../docs/AI_ASSISTANT.md) — user-facing AI guide
- [docs/VOICE_FILE_MAP.md](../../docs/VOICE_FILE_MAP.md) — phrase → file table
