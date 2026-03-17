from __future__ import annotations

import asyncio
import faulthandler
import json
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

APP_NAME = "tg-ws-proxy-android"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
ERROR_LOG_FILE = CONFIG_DIR / "error.log"
LAST_ERROR_FILE = CONFIG_DIR / "last_error.txt"
_FATAL_LOG_FH = None


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _install_fault_handler() -> None:
    """Log native crashes (segfault/abort) to error.log when possible."""
    global _FATAL_LOG_FH
    _ensure_config_dir()
    try:
        _FATAL_LOG_FH = ERROR_LOG_FILE.open('a', encoding='utf-8')
        _FATAL_LOG_FH.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] App process started\n")
        _FATAL_LOG_FH.flush()
        faulthandler.enable(file=_FATAL_LOG_FH, all_threads=True)
    except Exception:
        _FATAL_LOG_FH = None


def _append_error_log(header: str, details: str) -> None:
    _ensure_config_dir()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    block = f"\n[{ts}] {header}\n{details}\n"
    ERROR_LOG_FILE.write_text(
        ERROR_LOG_FILE.read_text(encoding="utf-8") + block if ERROR_LOG_FILE.exists() else block,
        encoding="utf-8",
    )
    LAST_ERROR_FILE.write_text(f"{header}\n\n{details}", encoding="utf-8")


def _install_global_error_hooks() -> None:
    def _sys_hook(exc_type, exc, tb):
        details = "".join(traceback.format_exception(exc_type, exc, tb))
        _append_error_log("Unhandled exception", details)

    def _thread_hook(args):
        details = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        _append_error_log(f"Unhandled thread exception ({args.thread.name})", details)

    sys.excepthook = _sys_hook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_hook


_install_global_error_hooks()
_install_fault_handler()

try:
    import proxy.tg_ws_proxy as tg_ws_proxy
    TG_PROXY_IMPORT_ERROR: str | None = None
except Exception:
    TG_PROXY_IMPORT_ERROR = traceback.format_exc()
    _append_error_log("Import failure: proxy.tg_ws_proxy", TG_PROXY_IMPORT_ERROR)
    tg_ws_proxy = None


DEFAULT_CONFIG: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 1080,
    "dc_ip": ["2:149.154.167.220", "4:149.154.167.220"],
    "verbose": False,
}


class ProxyController:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_handle: tuple[asyncio.AbstractEventLoop, asyncio.Event] | None = None
        self._started_at: float | None = None
        self._lock = threading.Lock()
        self._last_error: str | None = None
        self.config = self.load_config()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def uptime(self) -> int:
        if not self._started_at:
            return 0
        return int(max(0.0, time.time() - self._started_at))

    def consume_last_error(self) -> str | None:
        err = self._last_error
        self._last_error = None
        return err

    def ensure_config_dir(self) -> None:
        _ensure_config_dir()

    def load_config(self) -> dict[str, Any]:
        self.ensure_config_dir()
        if not CONFIG_FILE.exists():
            return dict(DEFAULT_CONFIG)

        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for key, value in DEFAULT_CONFIG.items():
                data.setdefault(key, value)
            return data
        except Exception:
            return dict(DEFAULT_CONFIG)

    def save_config(self, config: dict[str, Any]) -> None:
        self.ensure_config_dir()
        CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    def start(self) -> str:
        if tg_ws_proxy is None:
            return "Proxy core import failed; open error popup/log"

        with self._lock:
            if self.is_running:
                return "Proxy already running"

            cfg = dict(self.config)
            dc_opt = tg_ws_proxy.parse_dc_ip_list(cfg["dc_ip"])
            self._thread = threading.Thread(
                target=self._run_proxy,
                args=(cfg["port"], cfg["host"], bool(cfg.get("verbose", False)), dc_opt),
                daemon=True,
                name="tg-proxy",
            )
            self._thread.start()
            self._started_at = time.time()
            return f"Started: {cfg['host']}:{cfg['port']}"

    def stop(self) -> str:
        with self._lock:
            if not self.is_running:
                return "Proxy already stopped"

            stop_handle = self._stop_handle
            if stop_handle:
                loop, stop_event = stop_handle
                loop.call_soon_threadsafe(stop_event.set)

            if self._thread:
                self._thread.join(timeout=3)

            self._thread = None
            self._stop_handle = None
            self._started_at = None
            return "Stopped"

    def restart(self) -> str:
        self.stop()
        return self.start()

    def _run_proxy(self, port: int, host: str, verbose: bool, dc_opt: dict[int, str]) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stop_event = asyncio.Event()
        self._stop_handle = (loop, stop_event)

        if verbose:
            import logging
            logging.getLogger().setLevel(logging.DEBUG)

        try:
            loop.run_until_complete(
                tg_ws_proxy._run(port=port, dc_opt=dc_opt, stop_event=stop_event, host=host)
            )
        except Exception:
            details = traceback.format_exc()
            self._last_error = details
            _append_error_log("Proxy runtime failure", details)
        finally:
            loop.close()
            self._stop_handle = None


class TgWsProxyAndroidApp(App):
    def build(self):
        self.controller = ProxyController()

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))

        self.status_label = Label(text="Status: stopped", size_hint_y=None, height=dp(32))
        self.message_label = Label(text="", size_hint_y=None, height=dp(30))

        self.host_input = TextInput(
            text=self.controller.config["host"],
            multiline=False,
            hint_text="Host",
            size_hint_y=None,
            height=dp(44),
        )
        self.port_input = TextInput(
            text=str(self.controller.config["port"]),
            multiline=False,
            input_filter="int",
            hint_text="Port (>1024)",
            size_hint_y=None,
            height=dp(44),
        )

        self.dc_input = TextInput(
            text="\n".join(self.controller.config["dc_ip"]),
            multiline=True,
            hint_text="DC:IP per line",
            size_hint_y=None,
            height=dp(130),
        )

        save_btn = Button(text="Save")
        start_btn = Button(text="Start")
        stop_btn = Button(text="Stop")
        restart_btn = Button(text="Restart")

        save_btn.bind(on_press=lambda *_: self.save_config())
        start_btn.bind(on_press=lambda *_: self.set_message(self.controller.start()))
        stop_btn.bind(on_press=lambda *_: self.set_message(self.controller.stop()))
        restart_btn.bind(on_press=lambda *_: self.set_message(self.controller.restart()))

        root.add_widget(Label(text="TG WS Proxy (Native Android)", size_hint_y=None, height=dp(36)))
        root.add_widget(self.status_label)
        root.add_widget(self.message_label)
        root.add_widget(self.host_input)
        root.add_widget(self.port_input)
        root.add_widget(self.dc_input)
        root.add_widget(save_btn)
        root.add_widget(start_btn)
        root.add_widget(stop_btn)
        root.add_widget(restart_btn)

        Clock.schedule_interval(self.refresh_status, 1)
        Clock.schedule_once(lambda *_: self.show_pending_errors(), 0.1)
        return root

    def _show_error_popup(self, title: str, details: str) -> None:
        content = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        lbl = Label(text=details, halign="left", valign="top", size_hint_y=None)
        lbl.bind(texture_size=lambda inst, size: setattr(inst, "height", size[1]))
        lbl.text_size = (dp(320), None)
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(lbl)
        content.add_widget(scroll)
        close_btn = Button(text="Close", size_hint_y=None, height=dp(44))
        popup = Popup(title=title, content=content, size_hint=(0.95, 0.9), auto_dismiss=False)
        close_btn.bind(on_press=popup.dismiss)
        content.add_widget(close_btn)
        popup.open()

    def show_pending_errors(self) -> None:
        if TG_PROXY_IMPORT_ERROR:
            self.set_message("Proxy core failed to load")
            self._show_error_popup("Startup error", TG_PROXY_IMPORT_ERROR)
            return

        if LAST_ERROR_FILE.exists():
            details = LAST_ERROR_FILE.read_text(encoding="utf-8").strip()
            if details:
                self.set_message("Previous crash detected")
                self._show_error_popup("Previous error", details)
            LAST_ERROR_FILE.write_text("", encoding="utf-8")

    def save_config(self) -> None:
        try:
            if tg_ws_proxy is None:
                raise RuntimeError("Proxy core import failed")
            host = self.host_input.text.strip() or "127.0.0.1"
            port = int(self.port_input.text.strip())
            if port < 1024:
                raise ValueError("Use a port > 1024 (no root)")
            dc_ip = [x.strip() for x in self.dc_input.text.splitlines() if x.strip()]
            tg_ws_proxy.parse_dc_ip_list(dc_ip)
            self.controller.config = {
                "host": host,
                "port": port,
                "dc_ip": dc_ip,
                "verbose": False,
            }
            self.controller.save_config(self.controller.config)
            self.set_message("Config saved")
        except Exception as exc:
            self.set_message(f"Config error: {exc}")

    def set_message(self, text: str) -> None:
        self.message_label.text = text

    def refresh_status(self, *_args) -> None:
        state = "running" if self.controller.is_running else "stopped"
        self.status_label.text = f"Status: {state} | Uptime: {self.controller.uptime}s"

        runtime_error = self.controller.consume_last_error()
        if runtime_error:
            self.set_message("Proxy crashed; check popup/log")
            self._show_error_popup("Proxy runtime error", runtime_error)

    def on_stop(self) -> None:
        self.controller.stop()
        global _FATAL_LOG_FH
        if _FATAL_LOG_FH is not None:
            try:
                _FATAL_LOG_FH.flush()
                _FATAL_LOG_FH.close()
            except Exception:
                pass
            _FATAL_LOG_FH = None


if __name__ == "__main__":
    try:
        TgWsProxyAndroidApp().run()
    except Exception:
        _append_error_log("App bootstrap failure", traceback.format_exc())
        raise
