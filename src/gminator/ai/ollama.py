"""The Ollama backend: the default, talking to a local Ollama server."""

import json
from collections.abc import Iterator, Mapping, Sequence

from gminator.ai.provider import Answers, Message, ProviderError, Schema, answering, post


class OllamaProvider:
    def __init__(self, model: str, url: str, timeout: float = 120) -> None:
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._decides: bool | None = None

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
        with post(url, body, timeout=self.timeout) as response, answering(url):
            return _content(json.load(response))

    def stream(
        self, messages: Sequence[Message], *, temperature: float | None = None
    ) -> Iterator[str]:
        body = self._body(messages, stream=True, temperature=temperature)
        url = f"{self.url}/api/chat"
        with post(url, body, timeout=self.timeout) as response, answering(url):
            for line in response:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if content := _content(chunk):
                    yield content
                if chunk.get("done"):
                    return

    def decides(self) -> bool:
        """Whether Ollama lists the model as a decision model. Asked once; a server that can't
        say is taken to serve a chat model."""
        if self._decides is None:
            url, body = f"{self.url}/api/show", {"model": self.model}
            try:
                with post(url, body, timeout=self.timeout) as response, answering(url):
                    capabilities = json.load(response).get("capabilities", [])
            except ProviderError:
                return False
            self._decides = "decision" in capabilities
        return self._decides

    def decide(self, state: str, questions: Mapping[str, object]) -> Answers:
        url = f"{self.url}/v1/systemone"
        body = {"model": self.model, "state": state, "questions": questions}
        with post(url, body, timeout=self.timeout) as response, answering(url):
            reply = json.load(response)
        if "error" in reply:
            raise ProviderError(str(reply["error"]))
        if not isinstance(reply.get("answers"), dict):
            raise ProviderError(f"unexpected reply: {reply}")
        return reply["answers"]

    def _body(
        self, messages: Sequence[Message], *, stream: bool, temperature: float | None
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "think": False,
        }
        if temperature is not None:
            body["options"] = {"temperature": temperature}
        return body


def _content(reply: dict) -> str:
    if "error" in reply:
        raise ProviderError(str(reply["error"]))
    return reply.get("message", {}).get("content", "")
