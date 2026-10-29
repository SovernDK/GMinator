import pytest

from gminator.ai.provider import FakeProvider, Message, ProviderError, Request

MESSAGES = [Message("user", "Hello?")]


def test_replies_are_given_in_order_and_requests_recorded():
    provider = FakeProvider(["One.", "Two."])

    assert provider.complete(MESSAGES, schema={"type": "object"}) == "One."
    assert "".join(provider.stream(MESSAGES)) == "Two."
    assert provider.requests == [
        Request(MESSAGES, schema={"type": "object"}, stream=False),
        Request(MESSAGES, schema=None, stream=True),
    ]


def test_stream_arrives_in_several_chunks():
    chunks = list(FakeProvider(["Rain falls on the roof."]).stream(MESSAGES))

    assert len(chunks) > 1
    assert "".join(chunks) == "Rain falls on the roof."


def test_a_reply_can_be_worked_out_from_the_request():
    provider = FakeProvider(lambda request: request.messages[-1].content.upper())

    assert provider.complete(MESSAGES) == "HELLO?"


def test_a_scripted_error_is_raised():
    provider = FakeProvider([ProviderError("down")])

    with pytest.raises(ProviderError, match="down"):
        provider.complete(MESSAGES)


def test_running_out_of_replies_is_a_provider_error():
    with pytest.raises(ProviderError):
        FakeProvider([]).complete(MESSAGES)
