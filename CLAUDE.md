# cmkview

macOS app for monitoring CheckMK servers. Lightweight, single-backend alternative focused solely on CheckMK.

## Stack

- **PyObjC** (AppKit + WebKit) — native macOS window, menu bar icon, WKWebView for dashboard and setup
- **requests** — HTTP session for CheckMK polling
- **tomllib** (stdlib, Python 3.11+) — config parsing

## Architecture

- `cmkview.py` — main app: AppDelegate, window management, setup/dashboard modes, grouped payload builder
- `checkmk.py` — CheckMK client: cookie auth, view polling, service categorization, status text cleanup
- `config.py` — load/save `~/.cmkview.toml`
- `popup.html` — dashboard UI: grouped incident view, severity filters, ack toggle, collapse/expand
- `setup.html` — first-launch login form, tests credentials before saving

## CheckMK integration

- Cookie-based auth: `POST /check_mk/login.py` with `_username`, `_password`, `_login=1`
- Poll two built-in Multisite views with `output_format=python`:
  - `view.py?view_name=hostproblems` — DOWN/UNREACHABLE hosts
  - `view.py?view_name=svcproblems` — CRIT/WARN/UNKNOWN services
- No REST API key needed — regular user login
- No custom views required — uses CheckMK's built-in views

## UI behaviour

- First launch (no config) → setup screen with URL/username/password form
- After connect → grouped incident dashboard
- Menu bar icon: ✓ when clear, ⚠ N when problems exist
- Problems grouped by category (memory, disk, network, hardware, services, system)
- DOWN hosts get their own top-level group
- Clickable state badges (DOWN/CRIT/WARN/UNKN) to filter severity
- Hide Ack toggle, Collapse All / Expand All
- UI state (filters, collapsed groups, expanded hosts) persists across poll refreshes
- Data pushed via JS evaluation — HTML loaded once, not reloaded on each poll

## Config

`~/.cmkview.toml` — created by setup screen or manually:

```toml
url = "https://mon.example.com/mysite"
username = "myuser"
password = "mypassword"
interval = 60
```

## Packaging

- `py2app` to build a standalone `.app` bundle
- Distribute as a zipped `.app` via GitHub Releases

## What we are NOT doing

- No Qt / PyQt
- No other monitoring backends
- No cross-platform support
- No sound alerts, RDP/VNC launchers, or settings GUI (yet)
