from __future__ import annotations

import asyncio
import threading
import time
import traceback

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

import proxy.tg_ws_proxy as tg_ws_proxy

DEFAULT_CONFIG = {
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
        self.config = dict(DEFAULT_CONFIG)

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

    def start(self) -> str:
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
            self._last_error = traceback.format_exc()
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

        apply_btn = Button(text="Apply")
        start_btn = Button(text="Start")
        stop_btn = Button(text="Stop")
        restart_btn = Button(text="Restart")

        apply_btn.bind(on_press=lambda *_: self.apply_config())
        start_btn.bind(on_press=lambda *_: self.set_message(self.controller.start()))
        stop_btn.bind(on_press=lambda *_: self.set_message(self.controller.stop()))
        restart_btn.bind(on_press=lambda *_: self.set_message(self.controller.restart()))

        root.add_widget(Label(text="TG WS Proxy (Android)", size_hint_y=None, height=dp(36)))
        root.add_widget(self.status_label)
        root.add_widget(self.message_label)
        root.add_widget(self.host_input)
        root.add_widget(self.port_input)
        root.add_widget(self.dc_input)
        root.add_widget(apply_btn)
        root.add_widget(start_btn)
        root.add_widget(stop_btn)
        root.add_widget(restart_btn)

        Clock.schedule_interval(self.refresh_status, 1)
        return root

    def apply_config(self) -> None:
        try:
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
            self.set_message("Config applied")
        except Exception as exc:
            self.set_message(f"Config error: {exc}")

    def set_message(self, text: str) -> None:
        self.message_label.text = text

    def refresh_status(self, *_args) -> None:
        state = "running" if self.controller.is_running else "stopped"
        self.status_label.text = f"Status: {state} | Uptime: {self.controller.uptime}s"

        runtime_error = self.controller.consume_last_error()
        if runtime_error:
            self.set_message("Proxy crashed; see logs")

    def on_stop(self) -> None:
        self.controller.stop()


if __name__ == "__main__":
    TgWsProxyAndroidApp().run()
