# cmkview

A lightweight, native macOS app for monitoring [CheckMK](https://checkmk.com/) servers. Problems are grouped by category, filterable by severity, and updated live, giving you an at-a-glance incident dashboard without leaving your desktop.

Built from scratch for Mac. No Qt, no cross-platform frameworks, no bloat. Just a CheckMK login and you're in.

## Download

Grab the latest DMG from [Releases](https://github.com/ChrisJohnson89/cmkview/releases/latest), open it, and drag cmkview to Applications.

### First launch on macOS

Since the app isn't signed with an Apple Developer certificate, macOS will show a security warning the first time you open it:

1. Double-click **cmkview.app** - macOS will block it
2. Go to **System Settings > Privacy & Security**
3. Scroll down and click **"Open Anyway"** next to the cmkview message
4. You only need to do this once

## Features

- **Grouped incident dashboard** - problems organized by category (memory, disk, network, hardware, services, system)
- **Severity filters** - click DOWN / CRIT / WARN / UNKN badges to toggle visibility
- **Hide acknowledged** - one-click toggle to filter out acked problems
- **Collapse / expand** - drill into groups, hosts, and individual services
- **Menu bar indicator** - shows a problem count at a glance
- **First-launch setup** - connect to your CheckMK server through a simple login screen
- **Auto-refresh** - polls at a configurable interval, UI state persists across refreshes
- **Update notifications** - checks GitHub for new releases on startup

## Requirements

- macOS
- A CheckMK user account (any user that can see problems in the web UI)

## Configuration

On first launch you'll see a setup screen where you enter your CheckMK URL, username, and password. The password is stored in the macOS Keychain. App settings are saved to `~/.cmkview.toml`.

You can also create or edit the config file manually:

```toml
url = "https://mon.example.com/mysite"
username = "myuser"
interval = 60
```

Existing installs that still have `password` in `~/.cmkview.toml` are migrated automatically to Keychain on first launch after updating.

| Key        | Required | Default | Description                          |
|------------|----------|---------|--------------------------------------|
| `url`      | yes      |         | CheckMK site URL (no trailing slash) |
| `username` | yes      |         | CheckMK username                     |
| `interval` | no       | 60      | Poll interval in seconds             |

## How it works

1. Logs into CheckMK via cookie auth
2. Polls the built-in `hostproblems` and `svcproblems` Multisite views
3. Categorizes and groups problems, cleans up noisy status text
4. Renders a grouped incident view in a native macOS window

## Building from source

```bash
git clone https://github.com/ChrisJohnson89/cmkview.git
cd cmkview
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python cmkview.py
```

Requires Python 3.11+.

## Stack

- **PyObjC** (AppKit + WebKit) - native macOS window, menu bar, WKWebView
- **requests** - CheckMK HTTP polling
- **tomllib** - config parsing (stdlib, Python 3.11+)

## License

MIT
