"""cmkview - macOS app for monitoring CheckMK problems."""

from __future__ import annotations

import json
import os
import threading

import AppKit
import Foundation
import WebKit
import objc

import checkmk
import config
import updater


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POPUP_HTML_PATH = os.path.join(BASE_DIR, "popup.html")
SETUP_HTML_PATH = os.path.join(BASE_DIR, "setup.html")
__version__ = "0.1.0"

STATE_PRIORITY = {
    "DOWN": 0,
    "UNREACHABLE": 0,
    "CRITICAL": 1,
    "WARNING": 2,
    "UNKNOWN": 3,
    "PENDING": 4,
}

STATE_BADGES = {
    "CRITICAL": "CRIT",
    "DOWN": "DOWN",
    "WARNING": "WARN",
    "UNKNOWN": "UNKN",
    "UNREACHABLE": "DOWN",
    "PENDING": "PEND",
}

CATEGORY_META = {
    "host-down": {"label": "Hosts Down", "icon": "DOWN"},
    "memory": {"label": "Memory", "icon": "MEM"},
    "disk": {"label": "Disk", "icon": "DSK"},
    "network": {"label": "Network", "icon": "NET"},
    "hardware": {"label": "Hardware", "icon": "HW"},
    "services": {"label": "Services", "icon": "SVC"},
    "system": {"label": "System", "icon": "SYS"},
    "other": {"label": "Other", "icon": "ETC"},
}


class SetupMessageHandler(AppKit.NSObject):
    """Receives login form submissions from the setup WebView."""

    _app_delegate = objc.ivar()

    def initWithDelegate_(self, delegate):
        self = objc.super(SetupMessageHandler, self).init()
        if self is None:
            return None
        self._app_delegate = delegate
        return self

    def userContentController_didReceiveScriptMessage_(self, controller, message):
        try:
            data = json.loads(message.body())
            url = data.get("url", "").strip()
            username = data.get("username", "").strip()
            password = data.get("password", "")

            # Test login in background
            threading.Thread(
                target=self._app_delegate._test_and_save_login,
                args=(url, username, password),
                daemon=True,
            ).start()
        except Exception as e:
            self._app_delegate._send_setup_result(False, str(e))


class AppDelegate(AppKit.NSObject):
    def init(self):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self._problems = []
        self._main_window = None
        self._wk_view = None
        self._bar_item = None
        self._bar_menu = None
        self._cmk_client = None
        self._app_cfg = None
        self._page_loaded = False
        self._pending_payload = None
        self._poll_timer = None
        self._mode = None  # "setup" or "dashboard"
        self._update_info = None
        self._update_menu_item = None
        self._update_check_started = False
        return self

    def applicationDidFinishLaunching_(self, notification):
        # --- App menu bar with Edit menu (enables Cmd+C/V/X/A) ---
        main_menu = AppKit.NSMenu.alloc().init()

        edit_menu = AppKit.NSMenu.alloc().initWithTitle_("Edit")
        for title, action, key in [
            ("Cut", "cut:", "x"),
            ("Copy", "copy:", "c"),
            ("Paste", "paste:", "v"),
            ("Select All", "selectAll:", "a"),
            ("Undo", "undo:", "z"),
            ("Redo", "redo:", "Z"),
        ]:
            item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
            edit_menu.addItem_(item)

        edit_item = AppKit.NSMenuItem.alloc().init()
        edit_item.setSubmenu_(edit_menu)
        main_menu.addItem_(edit_item)
        AppKit.NSApp.setMainMenu_(main_menu)

        # --- Menu bar status item ---
        self._bar_item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(
            AppKit.NSVariableStatusItemLength
        )
        self._bar_item.button().setTitle_("cmkview")

        bar_menu = AppKit.NSMenu.alloc().init()
        for label, sel in [
            ("Show Dashboard", self.cmdShowDash_),
            ("Refresh Now", self.cmdRefresh_),
        ]:
            mi = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, sel, "")
            mi.setTarget_(self)
            bar_menu.addItem_(mi)
        bar_menu.addItem_(AppKit.NSMenuItem.separatorItem())
        qi = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", self.cmdQuit_, "q")
        qi.setTarget_(self)
        bar_menu.addItem_(qi)
        self._bar_menu = bar_menu
        self._bar_item.setMenu_(bar_menu)

        # --- Create window ---
        self._setup_main_window()

        # --- Decide: setup or dashboard ---
        self._app_cfg = config.load()
        if self._app_cfg.get("url") and self._app_cfg.get("username") and self._app_cfg.get("password"):
            self._start_dashboard()
            self._begin_update_check()
        else:
            self._show_setup()

        # Set Dock icon
        icon_path = os.path.join(BASE_DIR, "cmkview.icns")
        if os.path.exists(icon_path):
            icon = AppKit.NSImage.alloc().initWithContentsOfFile_(icon_path)
            if icon:
                AppKit.NSApp.setApplicationIconImage_(icon)

    def _setup_main_window(self):
        screen = AppKit.NSScreen.mainScreen().frame()
        w, h = 440, 720
        x = (screen.size.width - w) / 2
        y = (screen.size.height - h) / 2
        rect = Foundation.NSMakeRect(x, y, w, h)

        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSResizableWindowMask
            | AppKit.NSMiniaturizableWindowMask
        )
        self._main_window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, AppKit.NSBackingStoreBuffered, False
        )
        self._main_window.setTitle_("cmkview")
        self._main_window.setMinSize_(Foundation.NSMakeSize(360, 360))
        self._main_window.setReleasedWhenClosed_(False)

        self._main_window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def _create_webview(self, with_setup_handler=False):
        """Create a fresh WKWebView, optionally with the setup message handler."""
        wk_conf = WebKit.WKWebViewConfiguration.alloc().init()
        if with_setup_handler:
            handler = SetupMessageHandler.alloc().initWithDelegate_(self)
            wk_conf.userContentController().addScriptMessageHandler_name_(handler, "cmksetup")

        frame = self._main_window.contentView().bounds()
        wk_view = WebKit.WKWebView.alloc().initWithFrame_configuration_(frame, wk_conf)
        wk_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        return wk_view

    def _swap_webview(self, new_view):
        """Replace the current WebView in the window."""
        if self._wk_view:
            self._wk_view.removeFromSuperview()
        self._wk_view = new_view
        self._main_window.contentView().addSubview_(self._wk_view)

    # ── Setup flow ──

    def _show_setup(self):
        self._mode = "setup"
        self._page_loaded = False
        self._main_window.setTitle_("cmkview — Setup")
        self._bar_item.button().setTitle_("cmkview")

        wk_view = self._create_webview(with_setup_handler=True)
        self._swap_webview(wk_view)

        with open(SETUP_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
        base_url = Foundation.NSURL.fileURLWithPath_(BASE_DIR + "/")
        self._wk_view.loadHTMLString_baseURL_(html, base_url)

    def _test_and_save_login(self, url, username, password):
        """Test CheckMK login, save config if successful. Runs in background thread."""
        try:
            client = checkmk.CheckMKClient(url, username, password)
            client.login()
            # Login succeeded — save config
            config.save(url, username, password)
            self._app_cfg = config.load()
            self._send_setup_result(True, "")
            # Switch to dashboard on main thread
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                self.onSetupComplete_, None, False
            )
        except Exception as e:
            error_msg = str(e)
            if "Login failed" in error_msg:
                error_msg = "Invalid username or password"
            elif "ConnectionError" in type(e).__name__ or "connection" in error_msg.lower():
                error_msg = "Could not reach server — check the URL"
            elif "SSLError" in type(e).__name__:
                error_msg = "SSL certificate error — check the URL"
            self._send_setup_result(False, error_msg)

    def _send_setup_result(self, success, error):
        """Send result back to the setup form JS."""
        result = json.dumps({"success": success, "error": error})

        def do_send():
            js = f"window.onSetupResult({result})"
            self._wk_view.evaluateJavaScript_completionHandler_(js, None)

        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            self.onSendSetupResult_, result, False
        )

    @objc.typedSelector(b"v@:@")
    def onSendSetupResult_(self, result_json):
        js = f"window.onSetupResult({result_json})"
        self._wk_view.evaluateJavaScript_completionHandler_(js, None)

    @objc.typedSelector(b"v@:@")
    def onSetupComplete_(self, _obj):
        """Transition from setup to dashboard after successful login."""
        # Small delay so user sees "Connected!" message
        Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, self.onStartDashboardTimer_, None, False
        )

    @objc.typedSelector(b"v@:@")
    def onStartDashboardTimer_(self, timer):
        self._start_dashboard()
        self._begin_update_check()

    # ── Dashboard flow ──

    def _start_dashboard(self):
        self._mode = "dashboard"
        self._page_loaded = False
        self._pending_payload = None
        self._main_window.setTitle_("cmkview — CheckMK Monitor")

        self._cmk_client = checkmk.CheckMKClient(
            self._app_cfg["url"], self._app_cfg["username"], self._app_cfg["password"]
        )

        wk_view = self._create_webview(with_setup_handler=False)
        self._swap_webview(wk_view)

        # Load dashboard HTML
        with open(POPUP_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
        base_url = Foundation.NSURL.fileURLWithPath_(BASE_DIR + "/")
        self._wk_view.loadHTMLString_baseURL_(html, base_url)

        # Wait for page ready
        Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.3, self, self.checkPageReady_, None, True
        )

        # Start poll timer
        if self._poll_timer:
            self._poll_timer.invalidate()
        interval = self._app_cfg.get("interval", 60)
        self._poll_timer = Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            interval, self, self.onPollTimer_, None, True
        )
        threading.Thread(target=self._do_poll, daemon=True).start()

    @objc.typedSelector(b"v@:@")
    def checkPageReady_(self, timer):
        def callback(result, error):
            if result and not self._page_loaded:
                self._page_loaded = True
                timer.invalidate()
                if self._pending_payload is not None:
                    self._push_payload(self._pending_payload)
                if self._update_info is not None:
                    self._push_update_banner(self._update_info)
        self._wk_view.evaluateJavaScript_completionHandler_(
            "typeof updateProblems === 'function'", callback
        )

    def _push_payload(self, payload):
        data_json = json.dumps(payload).replace("</", "<\\/")
        js = f"updateProblems({data_json})"
        self._wk_view.evaluateJavaScript_completionHandler_(js, None)

    def _push_update_banner(self, update_info):
        data_json = json.dumps(update_info).replace("</", "<\\/")
        js = (
            "if (typeof window.showUpdateBanner === 'function') "
            f"window.showUpdateBanner({data_json})"
        )
        self._wk_view.evaluateJavaScript_completionHandler_(js, None)

    def _begin_update_check(self):
        if self._update_check_started:
            return
        self._update_check_started = True
        threading.Thread(target=self._check_for_updates, daemon=True).start()

    def _check_for_updates(self):
        update_info = updater.check_for_update(__version__)
        if update_info is None:
            return
        self._update_info = update_info
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            self.onUpdateCheckComplete_, None, False
        )

    def _ensure_update_menu_item(self):
        if self._bar_menu is None or self._update_info is None:
            return
        title = f"Update Available (v{self._update_info['version']})"
        if self._update_menu_item is None:
            item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, self.cmdOpenUpdate_, ""
            )
            item.setTarget_(self)
            self._bar_menu.insertItem_atIndex_(item, 2)
            self._update_menu_item = item
            return
        self._update_menu_item.setTitle_(title)

    # ── Menu actions ──

    @objc.typedSelector(b"v@:@")
    def cmdShowDash_(self, sender):
        self._main_window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    @objc.typedSelector(b"v@:@")
    def cmdRefresh_(self, sender):
        if self._mode == "dashboard":
            threading.Thread(target=self._do_poll, daemon=True).start()

    @objc.typedSelector(b"v@:@")
    def cmdOpenUpdate_(self, sender):
        if not self._update_info:
            return
        url = self._update_info.get("url", "").strip()
        if not url:
            return
        ns_url = Foundation.NSURL.URLWithString_(url)
        if ns_url is not None:
            AppKit.NSWorkspace.sharedWorkspace().openURL_(ns_url)

    @objc.typedSelector(b"v@:@")
    def cmdQuit_(self, sender):
        AppKit.NSApp.terminate_(None)

    @objc.typedSelector(b"v@:@")
    def onPollTimer_(self, timer):
        threading.Thread(target=self._do_poll, daemon=True).start()

    # ── Polling ──

    def _do_poll(self):
        try:
            self._problems = self._cmk_client.fetch_all_problems()
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                self.onPollSuccess_, None, False
            )
        except Exception as e:
            print(f"Poll error: {e}")
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                self.onPollError_, None, False
            )

    @objc.typedSelector(b"v@:@")
    def onPollSuccess_(self, _obj):
        problem_count = len(self._problems)
        self._bar_item.button().setTitle_(
            "cmkview ✓" if problem_count == 0 else f"cmkview ⚠ {problem_count}"
        )
        payload = build_popup_payload(self._problems)
        if self._page_loaded:
            self._push_payload(payload)
        else:
            self._pending_payload = payload

    @objc.typedSelector(b"v@:@")
    def onPollError_(self, _obj):
        self._bar_item.button().setTitle_("cmkview ✗")

    @objc.typedSelector(b"v@:@")
    def onUpdateCheckComplete_(self, _obj):
        if self._update_info is None:
            return
        self._ensure_update_menu_item()
        if self._mode == "dashboard" and self._page_loaded and self._wk_view is not None:
            self._push_update_banner(self._update_info)


def build_popup_payload(problems: list[dict]) -> dict:
    groups_by_key = {}
    unique_hosts = set()
    state_totals = {"DOWN": 0, "CRIT": 0, "WARN": 0, "UNKN": 0, "PEND": 0}

    for problem in problems:
        category = problem.get("category") or "other"
        state = problem.get("state") or "UNKNOWN"
        badge = STATE_BADGES.get(state, state[:4].upper())

        if state in ("DOWN", "UNREACHABLE"):
            category = "host-down"

        meta = CATEGORY_META.get(category, CATEGORY_META["other"])
        group_key = (category, state)
        unique_hosts.add((problem.get("site", ""), problem.get("host", "")))
        state_totals[badge] = state_totals.get(badge, 0) + 1

        group = groups_by_key.setdefault(
            group_key,
            {
                "id": f"{category}-{state.lower()}",
                "category": category,
                "category_label": meta["label"],
                "category_icon": meta["icon"],
                "state": state,
                "state_badge": badge,
                "problem_count": 0,
                "host_count": 0,
                "worst_duration": "0s",
                "worst_duration_seconds": 0,
                "hosts": {},
            },
        )

        host_key = (problem.get("site", ""), problem.get("host", ""))
        host_entry = group["hosts"].setdefault(
            host_key,
            {
                "host": problem.get("host", ""),
                "site": problem.get("site", ""),
                "problem_count": 0,
                "worst_duration": "0s",
                "worst_duration_seconds": 0,
                "acknowledged_count": 0,
                "downtime_count": 0,
                "items": [],
            },
        )

        item = {
            "host": problem.get("host", ""),
            "site": problem.get("site", ""),
            "service": problem.get("service", ""),
            "service_label": problem.get("service_label") or problem.get("service") or "Host State",
            "state": state,
            "state_badge": badge,
            "message": problem.get("message", ""),
            "duration": problem.get("duration", ""),
            "duration_raw": problem.get("duration_raw", ""),
            "duration_seconds": int(problem.get("duration_seconds", 0) or 0),
            "last_check": problem.get("last_check", ""),
            "attempt": problem.get("attempt", ""),
            "acknowledged": bool(problem.get("acknowledged")),
            "downtime": bool(problem.get("downtime")),
        }

        host_entry["items"].append(item)
        host_entry["problem_count"] += 1
        host_entry["acknowledged_count"] += int(item["acknowledged"])
        host_entry["downtime_count"] += int(item["downtime"])
        if item["duration_seconds"] >= host_entry["worst_duration_seconds"]:
            host_entry["worst_duration_seconds"] = item["duration_seconds"]
            host_entry["worst_duration"] = item["duration"] or host_entry["worst_duration"]

        group["problem_count"] += 1
        if item["duration_seconds"] >= group["worst_duration_seconds"]:
            group["worst_duration_seconds"] = item["duration_seconds"]
            group["worst_duration"] = item["duration"] or group["worst_duration"]

    groups = []
    for group in groups_by_key.values():
        hosts = []
        for host_entry in group["hosts"].values():
            host_entry["items"].sort(
                key=lambda item: (
                    -item["duration_seconds"],
                    item["service_label"].lower(),
                    item["message"].lower(),
                )
            )
            hosts.append(host_entry)

        hosts.sort(
            key=lambda host: (
                -host["worst_duration_seconds"],
                host["host"].lower(),
            )
        )

        group["hosts"] = hosts
        group["host_count"] = len(hosts)
        groups.append(group)

    groups.sort(
        key=lambda group: (
            STATE_PRIORITY.get(group["state"], 9),
            -group["host_count"],
            -group["worst_duration_seconds"],
            group["category_label"].lower(),
        )
    )

    return {
        "summary": {
            "problem_count": len(problems),
            "group_count": len(groups),
            "host_count": len(unique_hosts),
            "down_count": state_totals.get("DOWN", 0),
            "critical_count": state_totals.get("CRIT", 0),
            "warning_count": state_totals.get("WARN", 0),
            "unknown_count": state_totals.get("UNKN", 0),
        },
        "groups": groups,
    }


def main():
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
