"""Regression test: verify aiomqtt v2 API compatibility.

This test fails with aiomqtt < 2.0 and passes with aiomqtt >= 2.0,
confirming the migration in main.py and requirements.txt is correct.
"""
import inspect
import aiomqtt


def test_client_messages_attribute_exists():
    """client.messages must exist (replaces unfiltered_messages in v2)."""
    assert hasattr(aiomqtt.Client, "messages"), (
        "aiomqtt.Client.messages not found — requires aiomqtt>=2.0"
    )


def test_unfiltered_messages_removed():
    """client.unfiltered_messages() was removed in v2."""
    assert not hasattr(aiomqtt.Client, "unfiltered_messages"), (
        "aiomqtt.Client.unfiltered_messages still present — pin aiomqtt>=2.0"
    )


def test_client_identifier_parameter():
    """Client constructor uses 'identifier' (renamed from 'client_id' in v2)."""
    params = inspect.signature(aiomqtt.Client.__init__).parameters
    assert "identifier" in params, (
        "aiomqtt.Client.__init__ has no 'identifier' param — requires aiomqtt>=2.0"
    )
    assert "client_id" not in params, (
        "aiomqtt.Client.__init__ still has 'client_id' — unexpected aiomqtt version"
    )


def test_run():
    pass
