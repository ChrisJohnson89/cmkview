"""CheckMK Multisite cookie-auth client.

Polls the nagstamon_hosts / nagstamon_svc views via output_format=python.
"""

from __future__ import annotations

import ast
import datetime as dt
import html as html_mod
import re
import time

import requests


# States that count as "problems"
HOST_PROBLEM_STATES = {"DOWN", "UNREACH", "UNREACHABLE"}
SVC_PROBLEM_STATES = {"WARN", "WARNING", "CRIT", "CRITICAL", "UNKN", "UNKNOWN"}
REQUEST_TIMEOUT = 15

# Display labels
STATEMAP = {
    "UNREACH": "UNREACHABLE",
    "CRIT": "CRITICAL",
    "WARN": "WARNING",
    "UNKN": "UNKNOWN",
    "PEND": "PENDING",
}

SHORT_LABEL_MAP = {
    "memory": "Memory",
    "swap usage": "Swap",
    "cpu load": "CPU Load",
    "cpu utilization": "CPU",
    "host status": "Host State",
    "systemd service summary": "Service Failures",
    "service summary": "Service Failures",
    "check mk": "CheckMK",
    "checkmk": "CheckMK",
    "uptime": "Uptime",
}

SERVICE_CATEGORY_RULES = (
    ("memory", ("memory", "swap", "ram", "mem used", "mem usage")),
    ("disk", ("filesystem", "disk", "inode", "mount", "storage", "volume", "raid", "zfs", "drbd", "nvme")),
    ("network", ("network", "interface", "nic", "bond", "ethernet", "latency", "packet", "ping", "dns", "tcp", "udp", "http", "https", "routing", "route", "firewall")),
    ("hardware", ("temperature", "fan", "power", "psu", "battery", "sensor", "voltage", "smart", "idrac", "ilo", "controller", "hardware")),
    ("services", ("systemd", "service", "daemon", "process", "sshd", "apache", "nginx", "mysql", "mariadb", "postgres", "postfix", "docker", "podman", "kube", "container")),
    ("system", ("cpu", "load", "uptime", "kernel", "agent", "checkmk", "check mk", "clock", "time", "ntp", "os", "host status", "users")),
)

STATE_TOKEN_RE = re.compile(r"(?:(?<=\d)|(?<=\)))(CRIT|WARN|UNKN|OK|UNKNOWN|WARNING|CRITICAL)\b", re.IGNORECASE)
SUMMARY_PREFIX_RE = re.compile(r"^(?:total|disabled|failed|running|stopped|enabled|ok):\s*\d+\b", re.IGNORECASE)
DURATION_PART_RE = re.compile(
    r"(\d+)\s*(w|week|weeks|d|day|days|h|hr|hrs|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds)\b",
    re.IGNORECASE,
)


def categorize_service(service_name: str) -> str:
    """Map a CheckMK service label to a coarse category."""
    normalized = _normalize_service_name(service_name)
    if not normalized or normalized == "host status":
        return "system"

    if normalized.startswith("filesystem ") or normalized.startswith("disk "):
        return "disk"

    for category, keywords in SERVICE_CATEGORY_RULES:
        if any(keyword in normalized for keyword in keywords):
            return category

    return "other"


def clean_status_text(text: str) -> str:
    """Trim noisy plugin output into a concise human-readable summary."""
    text = _clean_output(text)
    if not text:
        return ""

    text = STATE_TOKEN_RE.sub("", text)
    text = re.sub(r"\b(?:CRITICAL|WARNING|UNKNOWN|CRIT|WARN|UNKN|OK)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ,;:-")

    if not text:
        return "Problem detected"

    parts = [part.strip(" ,;:-") for part in re.split(r"\s*[;|]\s*", text) if part.strip(" ,;:-")]
    if len(parts) > 1:
        text = parts[-1]

    comma_parts = [part.strip(" ,;:-") for part in re.split(r",\s*", text) if part.strip(" ,;:-")]
    filtered_parts = [part for part in comma_parts if not SUMMARY_PREFIX_RE.match(part)]
    if filtered_parts:
        text = ", ".join(filtered_parts)

    service_match = re.search(
        r"(?:\b\d+\s+)?(?:static\s+)?service(?:s)? failed\s*\(([^)]+)\)",
        text,
        re.IGNORECASE,
    )
    if service_match:
        failed_service = service_match.group(1).strip()
        return f"Service failed: {failed_service}"

    failed_count_match = re.search(
        r"\b(\d+)\s+(?:static\s+)?services?\s+failed\b",
        text,
        re.IGNORECASE,
    )
    if failed_count_match:
        count = failed_count_match.group(1)
        return f"{count} services failed"

    unit_match = re.search(
        r"\b(?:service|unit)\s+([A-Za-z0-9_.@-]+)\s+failed\b",
        text,
        re.IGNORECASE,
    )
    if unit_match:
        return f"Service failed: {unit_match.group(1)}"

    text = re.sub(r"^(?:status information|state information|status|state)\s*[:=-]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ,;:-")
    return text or "Problem detected"


def shorten_label(label: str) -> str:
    """Convert verbose CheckMK service labels into compact UI labels."""
    cleaned = _clean_output(label)
    normalized = _normalize_service_name(cleaned)

    if not normalized:
        return "Host State"

    if normalized in SHORT_LABEL_MAP:
        return SHORT_LABEL_MAP[normalized]

    if normalized.startswith("filesystem "):
        suffix = cleaned.split(" ", 1)[1].strip() if " " in cleaned else ""
        return f"Disk {suffix}".strip()

    if "systemd" in normalized and "service" in normalized:
        return "Service Failures"

    if "memory" in normalized:
        return "Memory"

    if "swap" in normalized:
        return "Swap"

    if "cpu" in normalized and "load" in normalized:
        return "CPU Load"

    cleaned = cleaned.strip()
    if len(cleaned) <= 28:
        return cleaned
    return f"{cleaned[:25].rstrip()}..."


def format_duration(value: str) -> str:
    """Render an absolute timestamp or duration-like string as a compact age."""
    seconds = _duration_to_seconds(value)
    if seconds is None:
        return _clean_output(value)
    return _humanize_duration(seconds)


class CheckMKClient:
    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.session = self._build_session()
        self._logged_in = False

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.verify = True
        session.headers.update(
            {
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
            }
        )
        return session

    def reset_session(self):
        self.session.close()
        self.session = self._build_session()
        self._logged_in = False

    def login(self):
        r = self.session.post(
            f"{self.url}/check_mk/login.py",
            data={
                "_username": self.username,
                "_password": self.password,
                "_login": "1",
                "_origtarget": "",
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        cookies = self.session.cookies.get_dict()
        has_auth = any(k.startswith("auth_") or k == "sid" for k in cookies)
        if not has_auth and "_username" not in r.text:
            raise RuntimeError("Login failed - check credentials")
        self._logged_in = True

    def _ensure_login(self):
        if not self._logged_in:
            self.login()

    def _fetch_view(self, view_name: str, extra_params: dict | None = None) -> list[dict]:
        self._ensure_login()
        params = {
            "view_name": view_name,
            "output_format": "python",
            "lang": "",
            "limit": "hard",
            "_ts": str(time.time_ns()),
        }
        if extra_params:
            params.update(extra_params)

        r = self.session.get(
            f"{self.url}/check_mk/view.py",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 401 or "login" in r.url:
            self.login()
            params["_ts"] = str(time.time_ns())
            r = self.session.get(
                f"{self.url}/check_mk/view.py",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
        r.raise_for_status()

        try:
            rows = ast.literal_eval(r.text)
        except (ValueError, SyntaxError):
            rows = r.json()

        if not rows:
            return []
        headers = rows[0]
        return [dict(zip(headers, row)) for row in rows[1:]]

    def fetch_all_problems(self) -> list[dict]:
        """Return combined host + service problems with normalised fields."""
        problems = []

        # Built-in CheckMK views — no custom/Nagstamon views required
        for row in self._fetch_view("hostproblems"):
            state_raw = row.get("host_state", "")
            if state_raw.upper() not in HOST_PROBLEM_STATES:
                continue

            icons = row.get("host_icons", [])
            if isinstance(icons, str):
                icons = []

            problems.append(
                _build_problem(
                    host=row.get("host", ""),
                    service_name="Host Status",
                    state=STATEMAP.get(state_raw, state_raw),
                    last_check="",
                    duration_raw="",
                    attempt="",
                    message="",
                    acknowledged="ack" in icons,
                    downtime="downtime" in icons,
                    site=row.get("sitename_plain", ""),
                )
            )

        for row in self._fetch_view("svcproblems"):
            state_raw = row.get("service_state", row.get("state", ""))
            if state_raw.upper() not in SVC_PROBLEM_STATES:
                continue

            icons = row.get("service_icons", [])
            if isinstance(icons, str):
                icons = []
            ack_flag = "ack" in icons

            service_name = row.get("service_description", "")
            problems.append(
                _build_problem(
                    host=row.get("host", ""),
                    service_name=service_name,
                    state=STATEMAP.get(state_raw, state_raw),
                    last_check=row.get("svc_check_age", ""),
                    duration_raw=row.get("svc_state_age", ""),
                    attempt="",
                    message=row.get("svc_plugin_output", ""),
                    acknowledged=ack_flag,
                    downtime="downtime" in icons,
                    site=row.get("sitename_plain", ""),
                )
            )

        return problems


def _build_problem(
    *,
    host: str,
    service_name: str,
    state: str,
    last_check: str,
    duration_raw: str,
    attempt: str,
    message: str,
    acknowledged: bool,
    downtime: bool,
    site: str,
) -> dict:
    duration_seconds = _duration_to_seconds(duration_raw)
    cleaned_service = _clean_output(service_name)
    return {
        "host": _clean_output(host),
        "service": cleaned_service,
        "service_label": shorten_label(cleaned_service),
        "category": categorize_service(cleaned_service),
        "state": STATEMAP.get(state, state),
        "last_check": _clean_output(last_check),
        "duration": format_duration(duration_raw),
        "duration_raw": _clean_output(duration_raw),
        "duration_seconds": duration_seconds or 0,
        "attempt": _clean_output(attempt),
        "message": clean_status_text(message),
        "acknowledged": bool(acknowledged),
        "downtime": bool(downtime),
        "site": _clean_output(site),
    }


def _clean_output(text: str) -> str:
    """Unescape HTML entities and collapse whitespace in plugin output."""
    if not text:
        return ""
    text = html_mod.unescape(str(text))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_service_name(service_name: str) -> str:
    service_name = _clean_output(service_name).lower()
    service_name = re.sub(r"[_/]+", " ", service_name)
    service_name = re.sub(r"\s+", " ", service_name).strip()
    return service_name


def _duration_to_seconds(value: str | int | float | None) -> int | None:
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        return max(0, int(value))

    text = _clean_output(value)
    if not text:
        return None

    parsed_dt = _parse_absolute_datetime(text)
    if parsed_dt is not None:
        now = dt.datetime.now(parsed_dt.tzinfo) if parsed_dt.tzinfo else dt.datetime.now()
        return max(0, int((now - parsed_dt).total_seconds()))

    day_clock_match = re.fullmatch(r"(?:(\d+)\s+days?\s+)?(\d{1,2}):(\d{2}):(\d{2})", text, re.IGNORECASE)
    if day_clock_match:
        days = int(day_clock_match.group(1) or 0)
        hours = int(day_clock_match.group(2))
        minutes = int(day_clock_match.group(3))
        seconds = int(day_clock_match.group(4))
        return days * 86400 + hours * 3600 + minutes * 60 + seconds

    total = 0
    matched = False
    for amount, unit in DURATION_PART_RE.findall(text):
        matched = True
        amount_int = int(amount)
        unit_key = unit.lower()
        if unit_key.startswith("w"):
            total += amount_int * 604800
        elif unit_key.startswith("d"):
            total += amount_int * 86400
        elif unit_key.startswith("h"):
            total += amount_int * 3600
        elif unit_key.startswith("m"):
            total += amount_int * 60
        else:
            total += amount_int
    if matched:
        return total

    if text.isdigit():
        return int(text)

    return None


def _parse_absolute_datetime(text: str) -> dt.datetime | None:
    candidates = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    )
    for fmt in candidates:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def _humanize_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"

    units = (
        ("w", 604800),
        ("d", 86400),
        ("h", 3600),
        ("m", 60),
    )
    parts = []
    remainder = seconds
    for label, unit_seconds in units:
        if remainder >= unit_seconds:
            value, remainder = divmod(remainder, unit_seconds)
            parts.append(f"{value}{label}")
        if len(parts) == 2:
            break

    if not parts:
        return f"{seconds}s"
    return " ".join(parts)
