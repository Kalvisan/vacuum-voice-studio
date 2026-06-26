# Security Policy

## Who this is for

This tool is for people who want to **personalize voice prompts on their own Xiaomi Home robots** using **their own account**.

- Your session stays on your computer (`config/config.json` is gitignored).
- Install uses the **same official Xiaomi cloud path** as the Mi Home app.
- Source code is open — you can read it, scan it, and run it locally.

## Verify the code yourself

Before you trust any release, run the built-in repository scan:

```bash
python3 scripts/repo_virusscan.py
# optional antivirus pass if ClamAV is installed:
python3 scripts/repo_virusscan.py --clamav
```

Or:

```bash
./x20-voice-tool.sh --cli virusscan
```

GitHub Actions also runs this scan on every push (see `.github/workflows/virusscan.yml`).

## Sensitive data

The tool stores Xiaomi cloud session values locally in:

```text
config/config.json
```

Never publish this file. It is ignored by Git by default.

Public templates that **are** safe to commit and share:

- `config/config.example.json`

See also `config/README.md`.

Do not paste session values into public issues. If you need help, redact:

- `serviceToken`
- `ssecurity`
- `userId`
- `did`
- device tokens
- signed upload/download URLs

## Reporting issues

For security-sensitive bugs, do not include private account data or robot identifiers in public reports. Provide sanitized logs and exact steps to reproduce.
