# Voice Pack Studio (web editor)

Modern browser editor for building custom voice packs on the Xiaomi X20 Max.

![Voice Pack Studio — custom vs original progress, per-file audio preview](docs/images/voice-pack-studio.png)

## Open the studio

```bash
./x20-voice-tool.sh --cli languages list --json
./x20-voice-tool.sh --cli download --language ru
./x20-voice-tool.sh --cli studio
```

Or from the TUI menu: **Step 2 — Voice Pack Studio (web editor)**

URL: `http://127.0.0.1:8765/` (local only — not exposed to the internet)

## Workflow

1. **Download** a base pack in any language (`./x20-voice-tool.sh --cli download --language ru` or in the Studio UI)
2. **Studio** — create a named pack, drag-and-drop MP3 replacements
3. **Build** — `./x20-voice-tool.sh --cli build` (syncs active pack automatically)
4. **Install** — `./x20-voice-tool.sh --cli install --all-devices --json`

## Persistence

Every upload is saved immediately to:

```text
workspace/packs/<your-pack-id>/audio/
workspace/packs/<your-pack-id>/pack.json
workspace/active_pack.json
```

You can close the browser or restart the computer — progress is kept in `workspace/packs/`.

## CLI pack commands

```bash
./x20-voice-tool.sh --cli pack list --json
./x20-voice-tool.sh --cli pack create --name "My Russian voice" --language ru --json
```

## Background server (for TUI / scripts)

```bash
./x20-voice-tool.sh --cli studio --background --json
./x20-voice-tool.sh --cli studio --stop --json
```

Returns the URL and process ID when starting. `--stop` terminates a background server started by this tool.

## File reference

Use [VOICE_FILE_MAP.md](VOICE_FILE_MAP.md) to see what each numbered MP3 means in English.
