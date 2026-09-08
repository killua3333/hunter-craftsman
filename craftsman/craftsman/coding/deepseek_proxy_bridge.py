from __future__ import annotations

import os
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator


_UPSTREAM = "https://api.deepseek.com"
_HOP_HEADERS = {"connection", "content-length", "host", "transfer-encoding"}


class _BridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in _HOP_HEADERS
        }
        request = urllib.request.Request(
            _UPSTREAM + self.path,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with self.server.upstream_opener.open(request, timeout=180) as response:  # type: ignore[attr-defined]
                payload = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in _HOP_HEADERS:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:
            payload = ('{"error":{"message":"local proxy bridge failed: %s"}}' % type(exc).__name__).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

    def log_message(self, _format: str, *args: object) -> None:
        return


@contextmanager
def deepseek_proxy_bridge() -> Iterator[str | None]:
    proxy = os.environ.get("HTTPS_PROXY", "").strip() or os.environ.get("HTTP_PROXY", "").strip()
    if not proxy:
        yield None
        return

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BridgeHandler)
    server.upstream_opener = opener  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
