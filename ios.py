from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

import proxy.tg_ws_proxy as tg_ws_proxy

APP_NAME = "tg-ws-proxy-ios"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 1080,
    "verbose": False,
}


class ProxyController:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_handle: tuple[asyncio.AbstractEventLoop, asyncio.Event] | None = None
        self._started_at: float | None = None
        self._lock = threading.Lock()
        self.config = self.load_config()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def uptime(self) -> int:
        if not self._started_at:
            return 0
        return int(max(0.0, time.time() - self._started_at))

    def ensure_config_dir(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

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
        with self._lock:
            if self.is_running:
                return "Proxy already running"

            cfg = dict(self.config)
            dc_opt = tg_ws_proxy.default_dc_ip_map()
            self._thread = threading.Thread(
                target=self._run_proxy,
                args=(cfg["port"], cfg["host"], bool(cfg.get("verbose", False)), dc_opt),
                daemon=True,
                name="tg-proxy-ios",
            )
            self._thread.start()
            self._started_at = time.time()
            return f"Started: {cfg['host']}:{cfg['port']} (all DC enabled)"

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
            pass
        finally:
            loop.close()
            self._stop_handle = None


class TgWsProxyIosApp(App):
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
            hint_text="Port",
            size_hint_y=None,
            height=dp(44),
        )

        save_btn = Button(text="Save")
        start_btn = Button(text="Start")
        stop_btn = Button(text="Stop")
        restart_btn = Button(text="Restart")

        save_btn.bind(on_press=lambda *_: self.save_config())
        start_btn.bind(on_press=lambda *_: self.set_message(self.controller.start()))
        stop_btn.bind(on_press=lambda *_: self.set_message(self.controller.stop()))
        restart_btn.bind(on_press=lambda *_: self.set_message(self.controller.restart()))

        root.add_widget(Label(text="TG WS Proxy (iOS)", size_hint_y=None, height=dp(36)))
        root.add_widget(Label(text="All available DC are used automatically", size_hint_y=None, height=dp(24)))
        root.add_widget(self.status_label)
        root.add_widget(self.message_label)
        root.add_widget(self.host_input)
        root.add_widget(self.port_input)
        root.add_widget(save_btn)
        root.add_widget(start_btn)
        root.add_widget(stop_btn)
        root.add_widget(restart_btn)

        Clock.schedule_interval(self.refresh_status, 1)
        return root

    def save_config(self) -> None:
        try:
            host = self.host_input.text.strip() or "127.0.0.1"
            port = int(self.port_input.text.strip())
            if port < 1024:
                raise ValueError("Use a port > 1024")
            self.controller.config = {
                "host": host,
                "port": port,
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

    def on_stop(self) -> None:
        self.controller.stop()


if __name__ == "__main__":
    TgWsProxyIosApp().run()
