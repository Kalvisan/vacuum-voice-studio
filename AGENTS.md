# Agent instructions — Vacuum Voice Studio

Instructions for any AI coding agent (Claude, ChatGPT, Cursor, Copilot, Gemini, etc.) working in this repository.

## Project scope

- **Product:** Vacuum Voice Studio — custom robot vacuum voice packs and remote control
- **Entry point:** `./x20-voice-tool.sh` from the repository root
- **Supported today:** Xiaomi Robot Vacuum X20 Max, model `xiaomi.vacuum.d109gl` (hardware ID `d109gl`)
- **Planned:** support for additional robot models; do not hard-code X20-only assumptions in new code unless required by the current API surface
- **Voice pack format (d109gl):** exactly **101** numbered MP3 files; replace by file name only

## Before any install or cloud action

```bash
./x20-voice-tool.sh --cli readiness --require-valid --json
```

If `state` is `expired` or `no_file`, run configure before other steps.

**Never** commit or expose `config/config.json` (session tokens).  
**Never** run `source x20-voice-tool.sh` — always execute `./x20-voice-tool.sh` directly.

Use `--json` on CLI commands for machine-readable output in agent loops.

## Which MP3 to replace

Read `docs/VOICE_FILE_MAP.md` or parse `assets/d109gl_en_transcriptions.csv`.

When the user names a phrase, look up the file (e.g. stuck → `720.mp3`). Replacements are stored under `workspace/packs/<id>/audio/`.

## Standard voice pack workflow

```bash
# 1. Session
./x20-voice-tool.sh --cli configure --use-existing --json

# 2. Original pack + studio
./x20-voice-tool.sh --cli download --json
./x20-voice-tool.sh --cli studio --background --json

# 3. User or agent edits in Voice Pack Studio (auto-saved to workspace/packs/)

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

## Session configure methods

| Method | When |
|---|---|
| `--use-existing` | Valid saved `config/config.json` |
| `--method qr --open-browser` | Human at keyboard |
| `--method cookies` + env vars | Automation with pasted session |
| `--method password` | Username/password |
| `--all-vacuums` / `--dids A,B` | Multiple robots (auto-scans all regions) |

`--all-vacuums` and `--dids` scan all Xiaomi cloud regions — no manual region guess.  
For discovery only: `./x20-voice-tool.sh --cli devices list --all-regions --vacuums-only --json`.

## Robot control (CLI)

Same actions as the TUI robot panel `[R]`:

```bash
./x20-voice-tool.sh --cli robot commands list --json
./x20-voice-tool.sh --cli robot snapshot --all-devices --json
./x20-voice-tool.sh --cli robot run dock --all-devices --json
```

Command IDs: `start_sweep`, `start_sweep_mop`, `start_mop`, `pause`, `continue`, `stop`, `dock`, `charge`, `identify`.

## Restore factory voice pack

```bash
./x20-voice-tool.sh --cli official --language en --json
```

## Hard rules

- Do not add, remove, or rename MP3 files in a pack (101 files, numeric names only)
- Do not publish tokens, `config/config.json`, signed URLs, or Xiaomi downloaded audio
- Install uploads to Xiaomi FDS; the robot does not fetch packs from the user's PC directly
- Keep user-facing docs in English unless the task is explicit localization
- Run `python3 scripts/repo_virusscan.py` before changing install or cloud auth logic

## Common errors

| Symptom | Action |
|---|---|
| Session expired | Re-run `configure` |
| Wrong file count on build | Re-run `download`, then fix files in Voice Pack Studio |
| Install not 100% | Check robot online; try an official pack first |
| Terminal broken after exit | User must run `./x20-voice-tool.sh`, not `source` |

More: `docs/TROUBLESHOOTING.md`

## Reference docs

| File | Purpose |
|---|---|
| `docs/CLI.md` | All CLI commands and flags |
| `docs/STUDIO.md` | Voice Pack Studio web editor |
| `docs/VOICE_FILE_MAP.md` | Phrase → MP3 file table |
| `docs/AI_ASSISTANT.md` | Copy-paste prompts for end users |
| `docs/GETTING_STARTED.md` | Human onboarding |
| `docs/TROUBLESHOOTING.md` | Fixes for common issues |
| `config/README.md` | Config file fields |

## Repository layout

| Path | Purpose |
|---|---|
| `scripts/` | Python CLI, TUI, cloud API, voice pack logic |
| `web/` | Voice Pack Studio frontend |
| `assets/` | Model catalogs and transcription CSV |
| `config/` | Local session (`config.json` is gitignored) |
| `workspace/` | Downloads, studio projects, builds (gitignored) |
