# Getting Started

This guide is for people who want to change robot voice sounds without reading technical docs.

## What this tool does

1. Connects to your Xiaomi account
2. Downloads an official base voice pack from Xiaomi (pick your language — `en`, `ru`, `de`, and more)
3. Lets you replace individual sounds with your own MP3 files
4. Uploads the new voice pack to your robot through Xiaomi cloud

You do **not** need to edit ZIP files by hand.

## Before you start

You need:

- A computer with Python 3
- Your Xiaomi robot added in the Xiaomi Home app
- MP3 files you are allowed to use

Install these once if your computer does not have them yet:

- `python3`
- `curl`
- `unzip`
- `zip`

## The easy way: menu mode

Open Terminal, go to this folder, and run:

```bash
chmod +x x20-voice-tool.sh
./x20-voice-tool.sh
```

Important: run `./x20-voice-tool.sh` — do **not** use `source` or `. ./x20-voice-tool.sh`.

![Terminal menu — status dashboard, guided flow, and Voice Pack Studio server bar](docs/images/voice-tool-tui.png)

### First launch

The tool checks whether you already signed in before.

| What happens | What you see |
|---|---|
| First time | A friendly sign-in helper opens automatically |
| Saved sign-in still works | You go straight to the main menu |
| Saved sign-in expired | The tool asks you to sign in again |

### Main menu steps

After you are connected:

1. **Download original voice sounds**
2. **Voice Pack Studio** — create a named pack and drag-and-drop replacements ([STUDIO.md](STUDIO.md))
3. Replace only the sounds you want — progress saves automatically
4. **Build your custom voice pack**
5. **Install on your robot(s)**

### Multiple robots

If your Xiaomi account has more than one vacuum robot:

1. Choose **Choose which robot(s) to control**
2. Load devices from Xiaomi cloud
3. Press Enter or Space on each robot you want to use
4. Continue and save

Install and status actions then apply to all selected robots.

## Sign-in options

Recommended: **QR code login** with the Xiaomi Home app.

Other options:

- Email and password
- Paste browser cookies (advanced)

Your sign-in is saved locally in `config/config.json`. This file stays on your computer and is never uploaded to GitHub.

## Restore the original voice

In the menu choose **Restore original Xiaomi voice pack**.

## If something goes wrong

| Problem | What to try |
|---|---|
| Terminal looks broken after the menu closes | Press Enter if asked, or run `./x20-voice-tool.sh` again |
| “Session expired” | Choose **Sign in to Xiaomi again** |
| Install fails | Make sure the robot is online in Xiaomi Home |
| Wrong number of sound files | Run **Download original voice sounds** again |

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for a longer fix list.

## Using an AI helper

If you prefer ChatGPT, Claude, or Cursor to run commands for you, read [AI_ASSISTANT.md](AI_ASSISTANT.md).

## More help

- [README.md](../README.md) — project overview and keywords
- [VOICE_FILE_MAP.md](VOICE_FILE_MAP.md) — what each numbered MP3 says
- [AI_ASSISTANT.md](AI_ASSISTANT.md) — use ChatGPT, Claude, or Cursor with this tool
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — fixes for common problems
- [CLI.md](CLI.md) — command line mode
- [config/README.md](../config/README.md) — saved sign-in file
