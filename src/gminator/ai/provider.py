"""The interface to a language model backend, and the fake backend used by tests."""

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Schema = dict[str, object]
Answers = dict[str, dict]


class ProviderError(Exception):
    """The model could not be reached or did not answer."""


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


class LLMProvider(Protocol):
    def complete(
        self,
        messages: Sequence[Message],
        *,
        schema: Schema | None = None,
        temperature: float | None = None,
    ) -> str:
        """The whole reply. With a `schema`, the reply is JSON forced to match it."""
        ...

    def stream(
        self, messages: Sequence[Message], *, temperature: float | None = None
    ) -> Iterator[str]:
        """The reply, chunk by chunk as the model writes it."""
        ...


@runtime_checkable
class DecisionProvider(Protocol):
    """A backend that may serve a decision model: one that picks from named options in a
    single pass instead of writing text."""

    def decides(self) -> bool:
        """Whether the model is a decision model, which answers `decide` and not chat."""
        ...

    def decide(self, state: str, questions: Mapping[str, object]) -> Answers:
        """Each question's answer, by name, about `state`."""
        ...


@dataclass(frozen=True)
class Providers:
    """A provider for each AI task, so each task can have the model that does it best."""

    classify: LLMProvider
    narrate: LLMProvider
    voice: LLMProvider

    @classmethod
    def one(cls, provider: LLMProvider) -> "Providers":
        """The same provider for every task."""
        return cls(provider, provider, provider)


@dataclass(frozen=True)
class Request:
    messages: Sequence[Message]
    schema: Schema | None = None
    stream: bool = False


Script = Iterable[str | ProviderError] | Callable[[Request], str]


class FakeProvider:
    """A scripted backend: replies in order, or worked out from each request."""

    def __init__(self, script: Script) -> None:
        self._respond = script if callable(script) else None
        self._replies = [] if callable(script) else list(script)
        self.requests: list[Request] = []

    def complete(
        self,
        messages: Sequence[Message],
        *,
        schema: Schema | None = None,
        temperature: float | None = None,
    ) -> str:
        return self._reply(Request(list(messages), schema=schema))

    def stream(
        self, messages: Sequence[Message], *, temperature: float | None = None
    ) -> Iterator[str]:
        reply = self._reply(Request(list(messages), stream=True))
        yield from re.findall(r"\S+\s*|\s+", reply)

    def _reply(self, request: Request) -> str:
        self.requests.append(request)
        if self._respond is not None:
            return self._respond(request)
        if not self._replies:
            raise ProviderError("the fake provider has no replies left")
        reply = self._replies.pop(0)
        if isinstance(reply, ProviderError):
            raise reply
        return reply


def post(url: str, body: object, headers: dict[str, str] | None = None, timeout: float = 120):
    """POST `body` as JSON; the open response. Failures become `ProviderError`s."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        with error:
            raise ProviderError(f"{url}: {_error_message(error.read())}") from error
    except OSError as error:
        raise ProviderError(f"{url}: {error}") from error


@contextmanager
def answering(url: str) -> Iterator[None]:
    """Turns a broken connection or a reply that is not JSON into a `ProviderError`."""
    try:
        yield
    except (OSError, ValueError) as error:
        raise ProviderError(f"{url}: {error}") from error


def _error_message(body: bytes) -> str:
    try:
        error = json.loads(body).get("error")
    except (ValueError, AttributeError):
        return body.decode(errors="replace")
    if isinstance(error, dict):
        return str(error.get("message", error))
    return str(error)
