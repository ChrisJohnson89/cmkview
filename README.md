# cmkview

A lightweight macOS app for monitoring [CheckMK](https://checkmk.com/) servers. Problems are grouped by category, filterable by severity, and updated live — giving you an at-a-glance incident dashboard without leaving your desktop.

No custom CheckMK views required. No API keys. Just a regular CheckMK login.

## Features

- **Grouped incident dashboard** — problems organized by category (memory, disk, network, hardware, services, system)
- **Severity filters** — click DOWN / CRIT / WARN / UNKN badges to toggle visibility
- **Hide acknowledged** — one-click toggle to filter out acked problems
- **Collapse / expand** — drill into groups → hosts → individual services
- **Menu bar indicator** — shows ✓ when clear, ⚠ N when problems exist
- **First-launch setup** — connect to your CheckMK server through a simple login screen
- **Auto-refresh** — polls at a configurable interval, UI state persists across refreshes

## Requirements

- macOS
- Python 3.11+
- A CheckMK user account (any user that can see problems in the web UI)

## Quick start

```bash
git clone https://github.com/ChrisJohnson89/cmkview.git
cd cmkview
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python cmkview.py
```

On first launch you'll see a setup screen — enter your CheckMK URL, username, and password. Config is saved to `~/.cmkview.toml`.

## Configuration

`~/.cmkview.toml` is created automatically by the setup screen, or you can write it by hand:

```toml
url = "https://mon.example.com/mysite"
username = "myuser"
password = "mypassword"
interval = 60
```

| Key        | Required | Default | Description                          |
|------------|----------|---------|--------------------------------------|
| `url`      | yes      |         | CheckMK site URL (no trailing slash) |
| `username` | yes      |         | CheckMK username                     |
| `password` | yes      |         | CheckMK password                     |
| `interval` | no       | 60      | Poll interval in seconds             |

## Build the .app

```bash
pip install -r requirements.txt
python setup.py py2app
```

The app bundle is created at `dist/cmkview.app`. Drag it to `/Applications` and add it to **System Settings → General → Login Items** to start on boot.

## How it works

1. Logs into CheckMK via cookie auth (`/check_mk/login.py`)
2. Polls the built-in `hostproblems` and `svcproblems` Multisite views
3. Categorizes and groups problems, cleans up noisy status text
4. Renders a grouped incident view in a native macOS window via WKWebView

## Stack

- **PyObjC** (AppKit + WebKit) — native macOS window, menu bar, WKWebView
- **requests** — CheckMK HTTP polling
- **tomllib** — config parsing (stdlib, Python 3.11+)

## License

MIT
