import json

import pytest

from gminator.ai.openai_compat import OpenAICompatibleProvider
from gminator.ai.provider import Message, ProviderError
from llm_server import llm_server

MESSAGES = [Message("system", "Be brief."), Message("user", "Hello?")]


@pytest.fixture
def server():
    with llm_server() as server:
        yield server


def answer(content: str) -> dict:
    return {"choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]}


def test_complete_posts_chat_completions_and_returns_the_reply(server):
    server.reply_json(answer("Hi."))
    provider = OpenAICompatibleProvider("local-model", f"{server.url}/v1")

    assert provider.complete(MESSAGES) == "Hi."

    path, body, headers = server.requests[0]
    assert path == "/v1/chat/completions"
    assert body["model"] == "local-model"
    assert body["messages"][1] == {"role": "user", "content": "Hello?"}
    assert "response_format" not in body
    assert "Authorization" not in headers


def test_complete_forces_the_output_to_a_schema(server):
    schema = {"type": "object", "properties": {"kind": {"enum": ["look"]}}}
    server.reply_json(answer('{"kind": "look"}'))

    OpenAICompatibleProvider("m", server.url).complete(MESSAGES, schema=schema, temperature=0)

    body = server.requests[0][1]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == schema
    assert body["temperature"] == 0


def test_an_api_key_is_sent_as_a_bearer_token(server):
    server.reply_json(answer("Hi."))

    OpenAICompatibleProvider("m", server.url, api_key="sk-test").complete(MESSAGES)

    assert server.requests[0][2]["Authorization"] == "Bearer sk-test"


def test_stream_reads_server_sent_events(server):
    events = [
        {"choices": [{"index": 0, "delta": {"role": "assistant"}}]},
        {"choices": [{"index": 0, "delta": {"content": "Rain "}}]},
        {"choices": [{"index": 0, "delta": {"content": "falls."}}]},
    ]
    server.reply(
        *(f"data: {json.dumps(event)}\n\n" for event in events),
        "data: [DONE]\n\n",
        content_type="text/event-stream",
    )

    chunks = list(OpenAICompatibleProvider("m", server.url).stream(MESSAGES))

    assert chunks == ["Rain ", "falls."]
    assert server.requests[0][1]["stream"] is True


def test_an_error_response_is_a_provider_error(server):
    server.reply_json({"error": {"message": "no such model"}}, status=404)

    with pytest.raises(ProviderError, match="no such model"):
        OpenAICompatibleProvider("m", server.url).complete(MESSAGES)


def test_an_unreachable_server_is_a_provider_error(unused_url):
    with pytest.raises(ProviderError):
        list(OpenAICompatibleProvider("m", unused_url).stream(MESSAGES))


def test_a_reply_that_is_not_json_is_a_provider_error(server):
    server.reply("<html>Bad gateway</html>")

    with pytest.raises(ProviderError):
        OpenAICompatibleProvider("m", server.url).complete(MESSAGES)
