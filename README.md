# IRM Rules Lookup

Simple lookup for **Inventory Rules Management (IRM)** ad restrictions — who can and cannot run ads on specific content.

## Quick start

```powershell
cd c:\Users\syeda012\projects\rym-work\ifp-frequency-cap-tests\irm-rules

# Open for yourself
powershell -ExecutionPolicy Bypass -File open-lookup.ps1

# Share on office VPN / same Wi-Fi (gives you a link others can open)
powershell -ExecutionPolicy Bypass -File open-lookup.ps1 -Share
```

Browser URL (local): **http://localhost:8765/lookup.html**

## Share with others

`localhost` only works on your machine. Three options:

### Option 1 — Same network (fastest)

Run with `-Share` and send teammates the printed link, e.g. `http://10.x.x.x:8765/lookup.html`.

- They must be on the same VPN or office Wi-Fi
- Your PC must stay on with the server running
- Allow Python through Windows Firewall if prompted

### Option 2 — Send the folder (everyone runs locally)

Share the whole `irm-rules` folder (zip, Teams, SharePoint). Teammates need Python installed, then:

```powershell
powershell -ExecutionPolicy Bypass -File open-lookup.ps1
```

When the Excel export updates, run `build_lookup.py` and redistribute `irm-lookup.json` (or the whole folder).

### Option 3 — Host as a static site (best for many users)

Upload these files to internal static hosting (SharePoint document library with HTML, internal S3, GitHub Pages, etc.):

- `lookup.html`
- `irm-lookup.json`

No Python server needed if both files are served over HTTP/HTTPS from the same folder.

## CLI (no browser)

## Refresh when the Excel export changes

```powershell
py build_lookup.py "C:\Users\syeda012\Downloads\IRM_Rules.xlsx"
```

## How it works

Each IRM rule has two parts:

1. **Inventory target** — where the rule applies (sports league, genre, series, publisher, country, etc.)
2. **Ad restrictions** — brands/industries that are blocked (`exclude`) or allowed-only (`include`)

The spreadsheet is wide and hard to scan. This tool flattens it into a searchable index so you can ask questions like *"what can't run on NFL?"* in one command.

## Files

| File | Purpose |
|------|---------|
| `build_lookup.py` | Reads `IRM_Rules.xlsx` and generates `irm-lookup.json` |
| `irm_lookup.py` | CLI to query blocked brands/industries |
| `irm-lookup.json` | Consolidated index (regenerate after Excel updates) |

## NFL example (from current export)

**Blocked industries:** Government, Political Issues/Advocacy, Sexual Health, Sportsbooks

**Blocked brands (sample):** Coinbase, Crypto.com, Kalshi, IBM, Nicorette, Nicoderm, Bethesda, and others

**Source rule:** `ESPN | US | Football | NFL` (publishers: ABC, ESPN, Hulu, Disney+, Fubo TV)

Use `--search nfl` to also see NFL Flag Football and NFL Films content-partner rules.
