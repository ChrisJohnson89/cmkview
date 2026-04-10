"""Load and save cmkview configuration from ~/.cmkview.toml."""

import os
import tomllib


DEFAULT_PATH = os.path.expanduser("~/.cmkview.toml")

DEFAULTS = {
    "interval": 60,
    "notify": ["CRIT", "DOWN"],
    "alert_sound": "default",
}


def exists(path: str | None = None) -> bool:
    path = path or DEFAULT_PATH
    return os.path.exists(path)


def load(path: str | None = None) -> dict:
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        return {}

    with open(path, "rb") as f:
        cfg = tomllib.load(f)

    cfg["url"] = cfg.get("url", "").rstrip("/")

    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)

    return cfg


def save(
    url: str,
    username: str,
    password: str,
    interval: int = 60,
    notify: list[str] | None = None,
    alert_sound: str = "default",
    path: str | None = None,
):
    path = path or DEFAULT_PATH
    if notify is None:
        notify = DEFAULTS["notify"]
    notify_toml = "[" + ", ".join(f'"{s}"' for s in notify) + "]"
    content = (
        f'url = "{url.rstrip("/")}"\n'
        f'username = "{username}"\n'
        f'password = "{password}"\n'
        f'interval = {interval}\n'
        f"notify = {notify_toml}\n"
        f'alert_sound = "{alert_sound}"\n'
    )
    with open(path, "w") as f:
        f.write(content)


def save_full(cfg: dict, path: str | None = None):
    """Save a full config dict back to disk."""
    save(
        url=cfg.get("url", ""),
        username=cfg.get("username", ""),
        password=cfg.get("password", ""),
        interval=cfg.get("interval", 60),
        notify=cfg.get("notify", DEFAULTS["notify"]),
        alert_sound=cfg.get("alert_sound", "default"),
        path=path,
    )
