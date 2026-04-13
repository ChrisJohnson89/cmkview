"""macOS Keychain helpers for cmkview credentials."""

from __future__ import annotations

import subprocess

SERVICE_NAME = "com.cmkview.app"


class KeychainError(RuntimeError):
    """Raised when a Keychain operation fails."""


def _account_name(url: str, username: str) -> str:
    return f"{username.strip()}|{url.rstrip('/').strip()}"


def save_password(url: str, username: str, password: str):
    account = _account_name(url, username)
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-a",
            account,
            "-s",
            SERVICE_NAME,
            "-w",
            password,
            "-U",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise KeychainError((result.stderr or result.stdout).strip() or "Failed to save password to Keychain")


def get_password(url: str, username: str) -> str | None:
    account = _account_name(url, username)
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            account,
            "-s",
            SERVICE_NAME,
            "-w",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.rstrip("\n")


def delete_password(url: str, username: str):
    account = _account_name(url, username)
    subprocess.run(
        [
            "security",
            "delete-generic-password",
            "-a",
            account,
            "-s",
            SERVICE_NAME,
        ],
        capture_output=True,
        text=True,
    )
