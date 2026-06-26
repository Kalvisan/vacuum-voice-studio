# Troubleshooting

Plain fixes for common problems when changing the voice pack on a Xiaomi X20 Max (`xiaomi.vacuum.d109gl`).

## Before anything else

Run:

```bash
./x20-voice-tool.sh --cli readiness --json
```

This shows what is missing: tools, sign-in, downloaded sounds, or built pack.

## Sign-in and connection

### "Session expired" or "Not connected yet"

Your saved Xiaomi sign-in no longer works.

**Fix:** Open the menu and choose **Sign in to Xiaomi again**, or run:

```bash
./x20-voice-tool.sh --cli configure --method qr --open-browser --region de --auto-did --json
```

Pick the cloud region where your robot appears in the Xiaomi Home app (often `de` for Europe).

### Tool hangs on startup

The tool checks Xiaomi cloud when it opens. Slow internet can take up to about 45 seconds.

**Fix:** Wait once. If it keeps failing, check your network and try again.

### Wrong robot selected

**Fix:** Menu → **Choose which robot(s) to control**, reload devices, select the correct vacuum, save.

## Terminal problems

### Terminal looks broken or empty after the menu closes

**Fix:** Do not run `source x20-voice-tool.sh`. Always run:

```bash
./x20-voice-tool.sh
```

Press Enter if the tool asks you to return to the shell.

### "Do not source this script"

You ran `. ./x20-voice-tool.sh` by mistake.

**Fix:** Close the tab or open a new terminal, then run `./x20-voice-tool.sh` normally.

## Voice pack build errors

### Wrong file count (not 101 files)

The X20 Max pack must contain exactly **101** MP3 files with the original numeric names.

**Fix:**

```bash
./x20-voice-tool.sh --cli download --json
```

Then replace only the files you need in Voice Pack Studio and build again.

### Extra or missing file names

**Fix:** Compare your folder to [docs/VOICE_FILE_MAP.md](VOICE_FILE_MAP.md). Do not invent new numbers like `607.mp3`.

## Install problems

### Install fails or progress stops below 100%

Checklist:

1. Robot is online in Xiaomi Home app
2. Robot is on the charging station
3. Session is valid: `./x20-voice-tool.sh --cli configure --use-existing --json`
4. Pack built successfully: `./x20-voice-tool.sh --cli build --json`

Try official pack first to confirm the robot accepts cloud installs:

```bash
./x20-voice-tool.sh --cli official --language en --json
```

Then retry your custom pack.

### Status shows old language after install

Wait up to three minutes. Check status:

```bash
./x20-voice-tool.sh --cli status --all-devices --json
```

Success looks like `"current": "ru"` and `"progress": 100`.

## Missing software

| Missing | Install |
|---|---|
| python3 | Python 3 from python.org or your system package manager |
| curl, unzip, zip | macOS: Xcode CLI tools; Linux: `apt install curl unzip zip` |
| Python packages | `./x20-voice-tool.sh --cli deps` |

## Still stuck?

1. Read [docs/GETTING_STARTED.md](GETTING_STARTED.md)
2. Use [docs/AI_ASSISTANT.md](AI_ASSISTANT.md) with your AI agent
3. Open an issue without pasting tokens or `config/config.json`
