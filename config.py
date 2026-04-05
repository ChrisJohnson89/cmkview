"""Load and save cmkview configuration from ~/.cmkview.toml."""

import os
import tomllib


DEFAULT_PATH = os.path.expanduser("~/.cmkview.toml")

DEFAULTS = {
    "interval": 60,
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


def save(url: str, username: str, password: str, interval: int = 60, path: str | None = None):
    path = path or DEFAULT_PATH
    content = (
        f'url = "{url.rstrip("/")}"\n'
        f'username = "{username}"\n'
        f'password = "{password}"\n'
        f'interval = {interval}\n'
    )
    with open(path, "w") as f:
        f.write(content)
