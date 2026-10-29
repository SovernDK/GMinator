"""The Ollama backend: the default, talking to a local Ollama server."""

import json
from collections.abc import Iterator, Sequence

from gminator.ai.provider import Message, ProviderError, Schema, answering, post

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "granite4.1:3b"


class OllamaProvider:
    def __init__(self, model: str = DEFAULT_MODEL, url: str = DEFAULT_URL) -> None:
        self.model = model
        self.url = url.rstrip("/")

    def complete(
        self,
        messages: Sequence[Message],
        *,
        schema: Schema | None = None,
        temperature: float | None = None,
    ) -> str:
        body = self._body(messages, stream=False, temperature=temperature)
        if schema is not None:
            body["format"] = schema
        url = f"{self.url}/api/chat"
        with post(url, body) as response, answering(url):
            return _content(json.load(response))

    def stream(
        self, messages: Sequence[Message], *, temperature: float | None = None
    ) -> Iterator[str]:
        body = self._body(messages, stream=True, temperature=temperature)
        url = f"{self.url}/api/chat"
        with post(url, body) as response, answering(url):
            for line in response:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if content := _content(chunk):
                    yield content
                if chunk.get("done"):
                    return

    def _body(
        self, messages: Sequence[Message], *, stream: bool, temperature: float | None
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
        }
        if temperature is not None:
            body["options"] = {"temperature": temperature}
        return body


def _content(reply: dict) -> str:
    if "error" in reply:
        raise ProviderError(str(reply["error"]))
    return reply.get("message", {}).get("content", "")
