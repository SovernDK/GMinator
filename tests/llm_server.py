"""A local HTTP server standing in for a model backend, for provider tests."""

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass
class Reply:
    """What the server answers: a status, a content type and the body, sent in `chunks`."""

    chunks: list[str]
    status: int = 200
    content_type: str = "application/json"


@dataclass
class LlmServer:
    url: str
    replies: list[Reply] = field(default_factory=list)
    requests: list[tuple[str, dict, dict[str, str]]] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=lambda: ["completion"])
    """What Ollama's /api/show says the model can do. Asking is not a request: it neither
    takes a reply nor is recorded."""

    def reply(self, *chunks: str, status: int = 200, content_type: str = "application/json"):
        self.replies.append(Reply(list(chunks), status, content_type))

    def reply_json(self, body: object, status: int = 200) -> None:
        self.reply(json.dumps(body), status=status)


@contextmanager
def llm_server() -> Iterator[LlmServer]:
    server_state: LlmServer

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/api/show":
                shown = json.dumps({"capabilities": server_state.capabilities}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(shown)
                return
            server_state.requests.append((self.path, body, dict(self.headers)))
            reply = server_state.replies.pop(0)
            self.send_response(reply.status)
            self.send_header("Content-Type", reply.content_type)
            self.end_headers()
            for chunk in reply.chunks:
                self.wfile.write(chunk.encode())
                self.wfile.flush()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_state = LlmServer(url=f"http://127.0.0.1:{server.server_address[1]}")
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        yield server_state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
