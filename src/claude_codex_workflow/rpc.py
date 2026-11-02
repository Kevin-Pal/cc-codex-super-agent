"""JSON-RPC on the existing native Codex Unix WebSocket control socket.

No second Codex runtime, public listener, authentication copy or third-party
dependency. Client frames are masked; partial/fragmented frames are supported.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
from concurrent.futures import Future
from pathlib import Path

from . import __version__


class RpcError(RuntimeError):
    pass


class NativeClient:
    def __init__(self, path: str | Path, on_event=None, timeout=15):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(timeout)
        self.socket.connect(str(path))
        key = base64.b64encode(os.urandom(16)).decode()
        request = ("GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
                   "Connection: Upgrade\r\nSec-WebSocket-Key: " + key +
                   "\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.socket.sendall(request.encode())
        header = bytearray()
        while not header.endswith(b"\r\n\r\n"):
            byte = self.socket.recv(1)
            if not byte:
                raise RpcError("Native control connection closed during handshake")
            header.extend(byte)
            if len(header) > 16384:
                raise RpcError("Oversized WebSocket handshake")
        accept = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if not header.startswith(b"HTTP/1.1 101 ") or accept not in header:
            raise RpcError("Native control socket rejected WebSocket handshake")
        self.socket.settimeout(None)
        self.on_event = on_event or (lambda event: None)
        self.pending: dict[int, Future] = {}
        self.lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.sequence = 0
        self.closed = False
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.server_info = self.request("initialize", {
            "clientInfo": {"name": "claude_codex_workflow", "title": "Claude Codex Workflow", "version": __version__},
            "capabilities": {"experimentalApi": True},
        }, timeout=timeout)
        self.notify("initialized", {})

    def _exact(self, size):
        data = bytearray()
        while len(data) < size:
            chunk = self.socket.recv(size - len(data))
            if not chunk:
                raise RpcError("Native control connection closed")
            data.extend(chunk)
        return bytes(data)

    def _send_frame(self, data: bytes, opcode=1):
        size = len(data)
        if size >= 16 * 1024 * 1024:
            raise RpcError("Message exceeds native control frame limit")
        header = bytes([0x80 | opcode])
        if size < 126:
            header += bytes([0x80 | size])
        elif size < 65536:
            header += b"\xfe" + struct.pack("!H", size)
        else:
            header += b"\xff" + struct.pack("!Q", size)
        mask = os.urandom(4)
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        with self.send_lock:
            self.socket.sendall(header + mask + payload)

    def _read(self):
        fragments = bytearray()
        try:
            while not self.closed:
                a, b = self._exact(2)
                size = b & 127
                if size == 126:
                    size = struct.unpack("!H", self._exact(2))[0]
                elif size == 127:
                    size = struct.unpack("!Q", self._exact(8))[0]
                if size > 32 * 1024 * 1024:
                    raise RpcError("Oversized native WebSocket frame")
                mask = self._exact(4) if b & 128 else None
                data = self._exact(size)
                if mask:
                    data = bytes(v ^ mask[i % 4] for i, v in enumerate(data))
                opcode = a & 15
                if opcode == 8:
                    raise RpcError("Native WebSocket closed")
                if opcode == 9:
                    self._send_frame(data, opcode=10)
                    continue
                if opcode == 10:
                    continue
                fragments.extend(data)
                if len(fragments) > 32 * 1024 * 1024:
                    raise RpcError("Oversized fragmented native message")
                if not a & 128:
                    continue
                message = json.loads(fragments)
                fragments.clear()
                if "id" in message and "method" not in message:
                    with self.lock:
                        future = self.pending.pop(message["id"], None)
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(RpcError(json.dumps(message["error"], ensure_ascii=False)))
                        else:
                            future.set_result(message.get("result", {}))
                else:
                    # The callback must not make a blocking RPC on this reader.
                    self.on_event(message)
        except Exception as error:
            already_closed = self.closed
            self.closed = True
            with self.lock:
                pending, self.pending = self.pending, {}
            for future in pending.values():
                if not future.done():
                    future.set_exception(RpcError(str(error)))
            if not already_closed:
                self.on_event({"method": "ccw/disconnected", "params": {"error": str(error)}})

    def request(self, method, params, timeout=20):
        if self.closed:
            raise RpcError("Native control connection is unavailable")
        with self.lock:
            self.sequence += 1
            request_id = self.sequence
            future = self.pending[request_id] = Future()
        self._send_frame(json.dumps({"id": request_id, "method": method, "params": params}, ensure_ascii=False).encode())
        try:
            return future.result(timeout=timeout)
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def notify(self, method, params):
        self._send_frame(json.dumps({"method": method, "params": params}).encode())

    def close(self):
        self.closed = True
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()
        if threading.current_thread() is not self.reader:
            self.reader.join(timeout=2)
