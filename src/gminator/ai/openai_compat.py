"""The backend for OpenAI-compatible servers: LM Studio, llama-server, vLLM."""

import json
from collections.abc import Iterator, Sequence

from gminator.ai.provider import Message, ProviderError, Schema, answering, post


class OpenAICompatibleProvider:
    def __init__(
        self, model: str, url: str, api_key: str | None = None, timeout: float = 120
    ) -> None:
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def complete(
        self,
        messages: Sequence[Message],
        *,
        schema: Schema | None = None,
        temperature: float | None = None,
    ) -> str:
        body = self._body(messages, stream=False, temperature=temperature)
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": schema},
            }
        url = f"{self.url}/chat/completions"
        with post(url, body, self._headers, self.timeout) as response, answering(url):
            reply = json.load(response)
        try:
            return reply["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError(f"unexpected reply: {reply}") from error

    def stream(
        self, messages: Sequence[Message], *, temperature: float | None = None
    ) -> Iterator[str]:
        body = self._body(messages, stream=True, temperature=temperature)
        url = f"{self.url}/chat/completions"
        with post(url, body, self._headers, self.timeout) as response, answering(url):
            for raw in response:
                line = raw.decode().strip()
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    return
                event = json.loads(data)
                if "error" in event:
                    raise ProviderError(str(event["error"]))
                for choice in event.get("choices", []):
                    if content := choice.get("delta", {}).get("content"):
                        yield content

    def _body(
        self, messages: Sequence[Message], *, stream: bool, temperature: float | None
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
        }
        if temperature is not None:
            body["temperature"] = temperature
        return body
