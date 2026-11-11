#!/usr/bin/env python3
"""Programmatic loopback TCP controller for Godot SceneTree runner."""
import json
import socket
import time


class GameDriver:
    """Python IPC client communicating over loopback TCP with scene_runner.gd."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9999, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None

    def connect(self, retries: int = 15, delay: float = 0.4) -> bool:
        for _ in range(retries):
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(self.timeout)
                self.sock.connect((self.host, self.port))
                return True
            except (ConnectionRefusedError, OSError):
                time.sleep(delay)
        raise TimeoutError(f"Could not connect to GameDriver TCP server at {self.host}:{self.port}")

    def send_command(self, cmd_dict: dict) -> dict:
        if not self.sock:
            raise RuntimeError("GameDriver is not connected")
        payload = (json.dumps(cmd_dict) + "\n").encode("utf-8")
        self.sock.sendall(payload)
        response_data = b""
        while b"\n" not in response_data:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            response_data += chunk
        if not response_data:
            return {"status": "error", "message": "Empty response from engine runner"}
        return json.loads(response_data.decode("utf-8").strip())

    def step(self, frames: int = 1) -> dict:
        return self.send_command({"cmd": "step", "frames": frames})

    def set_prop(self, target: str, prop: str, value) -> dict:
        return self.send_command({"cmd": "set_prop", "target": target, "property": prop, "value": value})

    def get_prop(self, target: str, prop: str) -> dict:
        return self.send_command({"cmd": "get_prop", "target": target, "property": prop})

    def click_node(self, target: str) -> dict:
        return self.send_command({"cmd": "click_node", "target": target})

    def capture(self, path: str) -> dict:
        return self.send_command({"cmd": "capture", "path": path})

    def close(self) -> None:
        if self.sock:
            try:
                self.send_command({"cmd": "quit"})
            except Exception:
                pass
            self.sock.close()
            self.sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
