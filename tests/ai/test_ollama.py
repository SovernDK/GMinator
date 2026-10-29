import json

import pytest

from gminator.ai.ollama import OllamaProvider
from gminator.ai.provider import Message, ProviderError
from llm_server import llm_server

MESSAGES = [Message("system", "Be brief."), Message("user", "Hello?")]


@pytest.fixture
def server():
    with llm_server() as server:
        yield server


def test_complete_posts_the_chat_and_returns_the_reply(server):
    server.reply_json({"message": {"role": "assistant", "content": "Hi."}, "done": True})
    provider = OllamaProvider("granite4.1:3b", server.url)

    assert provider.complete(MESSAGES) == "Hi."

    path, body, _ = server.requests[0]
    assert path == "/api/chat"
    assert body["model"] == "granite4.1:3b"
    assert body["stream"] is False
    assert body["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Hello?"},
    ]
    assert "format" not in body


def test_complete_forces_the_output_to_a_schema(server):
    schema = {"type": "object", "properties": {"kind": {"enum": ["look"]}}}
    server.reply_json({"message": {"content": '{"kind": "look"}'}, "done": True})

    OllamaProvider("m", server.url).complete(MESSAGES, schema=schema)

    assert server.requests[0][1]["format"] == schema


def test_temperature_is_passed_as_an_option(server):
    server.reply_json({"message": {"content": "x"}, "done": True})

    OllamaProvider("m", server.url).complete(MESSAGES, temperature=0)

    assert server.requests[0][1]["options"] == {"temperature": 0}


def test_stream_yields_the_reply_as_it_arrives(server):
    lines = [
        {"message": {"content": "Rain "}, "done": False},
        {"message": {"content": "falls."}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    server.reply(*(json.dumps(line) + "\n" for line in lines), content_type="application/x-ndjson")

    chunks = list(OllamaProvider("m", server.url).stream(MESSAGES))

    assert chunks == ["Rain ", "falls."]
    assert server.requests[0][1]["stream"] is True


def test_an_error_from_ollama_is_a_provider_error(server):
    server.reply_json({"error": "model 'm' not found"}, status=404)

    with pytest.raises(ProviderError, match="model 'm' not found"):
        OllamaProvider("m", server.url).complete(MESSAGES)


def test_an_error_while_streaming_is_a_provider_error(server):
    server.reply(json.dumps({"error": "out of memory"}) + "\n")

    with pytest.raises(ProviderError, match="out of memory"):
        list(OllamaProvider("m", server.url).stream(MESSAGES))


def test_an_unreachable_server_is_a_provider_error(unused_url):
    with pytest.raises(ProviderError):
        OllamaProvider("m", unused_url).complete(MESSAGES)


def test_a_reply_cut_off_mid_stream_is_a_provider_error(server):
    server.reply('{"message": {"content": "Rain"}, "done": false}\n{"mess')

    with pytest.raises(ProviderError):
        list(OllamaProvider("m", server.url).stream(MESSAGES))
