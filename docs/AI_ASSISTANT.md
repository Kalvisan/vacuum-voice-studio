# Using your AI assistant with this tool

You can use ChatGPT, Claude, Cursor, or any other AI agent to help you change the voice pack on your Xiaomi X20 Max robot.

This project is built for that. The menu is for humans; the `--cli` commands and JSON output are for AI.

## What to tell your AI

Copy this into your chat:

```text
Help me change the voice pack on my Xiaomi Robot Vacuum X20 Max (model xiaomi.vacuum.d109gl).

I have the x20-voice-tool in this folder. Please:
1. Run readiness checks with JSON output
2. Guide me through sign-in if needed
3. Tell me which numbered MP3 files to replace for the phrases I want to change
4. Build and install the new pack on my robot

Use ./x20-voice-tool.sh --cli ... --json for all commands.
Never commit config/config.json (it contains my private session).
Read docs/VOICE_FILE_MAP.md to map file numbers to English phrases.
```

## Files your AI should read first

| File | Why |
|---|---|
| [docs/VOICE_FILE_MAP.md](VOICE_FILE_MAP.md) | Which numbered MP3 matches which robot phrase |
| [docs/CLI.md](CLI.md) | All commands and flags |
| [assets/d109gl_en_transcriptions.csv](../assets/d109gl_en_transcriptions.csv) | Same map in CSV for parsing |
| [.cursor/skills/xiaomi-x20-voice-pack/SKILL.md](../.cursor/skills/xiaomi-x20-voice-pack/SKILL.md) | Cursor skill for this workflow |

## Typical AI workflow

```bash
# 1. Check state
./x20-voice-tool.sh --cli readiness --require-valid --json

# 2. If session missing or expired, configure (QR, password, or cookies)
./x20-voice-tool.sh --cli configure --use-existing --json

# 3. Download original sounds (once)
./x20-voice-tool.sh --cli download --json

# 4. User replaces MP3 files in Voice Pack Studio
#    AI uses VOICE_FILE_MAP.md to pick the right file numbers

# 5. Build pack
./x20-voice-tool.sh --cli build --json

# 6. Install on robot(s)
./x20-voice-tool.sh --cli install --language ru --all-devices --json

# 7. Confirm
./x20-voice-tool.sh --cli status --all-devices --json
```

## Example prompts

**Find which file to change**

```text
My robot says "The robot vacuum is stuck, please move it to a new location to start."
Which MP3 file is that, and where do I put my replacement?
```

**Replace specific phrases**

```text
I want to replace these robot phrases with Russian audio:
- "Start cleanup"
- "Paused"
- "The robot vacuum is stuck..."
Use VOICE_FILE_MAP.md, tell me the exact file names, then build and install when I confirm the MP3s are ready.
```

**Multiple robots**

```text
I have two X20 Max robots on one Xiaomi account. Configure both and install the same custom pack on each.
```

## What the AI must not do

- Commit or paste `config/config.json`, tokens, or passwords into public chats
- Run `source x20-voice-tool.sh` (it can break the terminal session)
- Add or remove MP3 files from the pack (must stay at exactly 101 files)
- Rename files (keep numeric names like `720.mp3`)

## Cursor users

If you use Cursor, install the project skill from:

`.cursor/skills/xiaomi-x20-voice-pack/SKILL.md`

Then ask: *"Use the xiaomi-x20-voice-pack skill to install my custom voice pack."*

## Restore original voice

```bash
./x20-voice-tool.sh --cli official --language en --json
```

Or ask your AI to run that after you want to go back to the factory English pack.
