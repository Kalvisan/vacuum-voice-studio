# Workspace (local only — not committed)

Everything here is gitignored except this file and `.gitkeep`. The tool creates subfolders on first use.

| Path | Purpose |
|---|---|
| `original/` | Official base MP3s (101 files) extracted from the downloaded ZIP |
| `base_<lang>.zip` | Cached official pack from Xiaomi (reused on re-download) |
| `base_pack.json` | Active base language, URL, MD5 |
| `working_pack/` | Staging copy synced from the active studio pack before build |
| `packs/<id>/` | Voice Pack Studio projects |
| `packs/<id>/pack.json` | Pack name, install language, replaced-file list |
| `packs/<id>/audio/` | All 101 MP3 files for that project |
| `active_pack.json` | Which pack Studio / build uses |
| `build_state.json` | Last built ZIP hash and pack id (TUI step markers) |
| `install_state.json` | Last installed ZIP hash and language (TUI step markers) |
| `official_<model>_<lang>.zip` | Cache when using **Restore official pack** |
| `.voice_catalog_cache.json` | Cached Xiaomi language list (refreshed daily) |

Build output goes to `output/` (also gitignored), not here.

Phrase labels in Studio still come from `assets/d109gl_en_transcriptions.csv`.
