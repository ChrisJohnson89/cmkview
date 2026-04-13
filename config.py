"""Load and save cmkview configuration from ~/.cmkview.toml."""

import os
import tomllib


DEFAULT_PATH = os.path.expanduser("~/.cmkview.toml")

DEFAULTS = {
    "interval": 60,
    "notify": ["CRIT", "DOWN"],
    "alert_sound": "default",
    "hide_acked": False,
    "font_size": 0,
    "view_mode": "grouped",
    "hidden_states": {},
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
    interval: int = 60,
    notify: list[str] | None = None,
    alert_sound: str = "default",
    hide_acked: bool = False,
    font_size: int = 0,
    view_mode: str = "grouped",
    hidden_states: dict | None = None,
    path: str | None = None,
):
    path = path or DEFAULT_PATH
    if notify is None:
        notify = DEFAULTS["notify"]
    if hidden_states is None:
        hidden_states = {}
    notify_toml = "[" + ", ".join(f'"{s}"' for s in notify) + "]"
    content = (
        f'url = "{url.rstrip("/")}"\n'
        f'username = "{username}"\n'
        f'interval = {interval}\n'
        f"notify = {notify_toml}\n"
        f'alert_sound = "{alert_sound}"\n'
        f"hide_acked = {'true' if hide_acked else 'false'}\n"
        f"font_size = {font_size}\n"
        f'view_mode = "{view_mode}"\n'
    )
    if hidden_states:
        entries = "\n".join(
            f'{k} = {"true" if v else "false"}' for k, v in hidden_states.items()
        )
        content += f"\n[hidden_states]\n{entries}\n"
    with open(path, "w") as f:
        f.write(content)


def save_full(cfg: dict, path: str | None = None):
    """Save a full config dict back to disk."""
    save(
        url=cfg.get("url", ""),
        username=cfg.get("username", ""),
        interval=cfg.get("interval", 60),
        notify=cfg.get("notify", DEFAULTS["notify"]),
        alert_sound=cfg.get("alert_sound", "default"),
        hide_acked=cfg.get("hide_acked", False),
        font_size=cfg.get("font_size", 0),
        view_mode=cfg.get("view_mode", "grouped"),
        hidden_states=cfg.get("hidden_states", {}),
        path=path,
    )
