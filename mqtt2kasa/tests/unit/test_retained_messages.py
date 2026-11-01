"""Regression tests: a retained message is a snapshot, not a request.

The broker sets the retain flag on a delivery only when the message comes from
its retained store because of a new subscription (MQTT 3.1.1 ss 3.3.1.3). A live
publish is always delivered with the flag clear, however the publisher set it.

So a message arriving with retain set on a topic we publish our own state to
with retain is our own last state being handed back to us at subscribe time.
Treating it as a command drives the device to whatever was stored, which is
wrong whenever it was changed out of band while we were disconnected.
"""

import asyncio
import inspect

import aiomqtt

from mqtt2kasa import mqtt as mqtt_module
from mqtt2kasa.config import Cfg


class FakeMessage:
    """Shaped like aiomqtt.Message for the fields handle_mqtt_messages reads."""

    def __init__(self, topic, payload, retain):
        self.topic = topic
        self.payload = payload
        self.retain = retain


def _delivered(messages, mqtt_cfg):
    """Feed messages through handle_mqtt_messages; return the events it queued."""

    async def go():
        async def message_stream():
            for message in messages:
                yield message

        q = asyncio.Queue()
        await mqtt_module.handle_mqtt_messages(message_stream(), q)
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        return events

    saved_info = Cfg._info
    Cfg._parse_raw_cfg({"mqtt": mqtt_cfg, "locations": {}})
    try:
        return asyncio.run(go())
    finally:
        Cfg._info = saved_info


def test_aiomqtt_message_still_exposes_retain():
    """handle_mqtt_messages reads message.retain; fail loudly if it moves."""
    params = inspect.signature(aiomqtt.Message.__init__).parameters
    assert "retain" in params, "aiomqtt.Message has no 'retain' field"


def test_retained_is_dropped_when_we_publish_retained():
    events = _delivered(
        [FakeMessage("/foo", b"off", True), FakeMessage("/foo", b"on", False)],
        {"retain": True},
    )
    assert [e.payload for e in events] == ["on"]


def test_retained_is_honored_by_default():
    """retain defaults to false, so existing configs behave exactly as before."""
    events = _delivered(
        [FakeMessage("/foo", b"off", True), FakeMessage("/foo", b"on", False)],
        {},
    )
    assert [e.payload for e in events] == ["off", "on"]


def test_no_mqtt_section_at_all_behaves_as_before():
    events = _delivered([FakeMessage("/foo", b"off", True)], None)
    assert [e.payload for e in events] == ["off"]


def test_ignore_retained_can_be_forced_off():
    events = _delivered(
        [FakeMessage("/foo", b"off", True)],
        {"retain": True, "ignore_retained": False},
    )
    assert [e.payload for e in events] == ["off"]


def test_ignore_retained_can_be_forced_on_without_retain():
    events = _delivered([FakeMessage("/foo", b"off", True)], {"ignore_retained": True})
    assert events == []


def test_live_messages_are_never_dropped():
    """Only the retain flag matters, not the payload or topic."""
    events = _delivered(
        [
            FakeMessage("/foo", b"on", False),
            FakeMessage("/foo/brightness", b"42", False),
            FakeMessage("/bar", b"toggle", False),
        ],
        {"retain": True},
    )
    assert [e.payload for e in events] == ["on", "42", "toggle"]


def test_mqtt_ignore_retained_defaults_to_the_retain_setting():
    saved_info = Cfg._info
    try:
        for mqtt_cfg, expected in (
            ({"retain": True}, True),
            ({"retain": False}, False),
            ({}, False),
            (None, False),
            ({"retain": True, "ignore_retained": False}, False),
            ({"retain": False, "ignore_retained": True}, True),
        ):
            Cfg._parse_raw_cfg({"mqtt": mqtt_cfg, "locations": {}})
            assert Cfg().mqtt_ignore_retained == expected, mqtt_cfg
    finally:
        Cfg._info = saved_info


def test_retained_off_is_not_turned_into_a_request_for_a_device_that_is_on():
    """The path that actually mattered, end to end.

    Device is on. We reconnect, the broker replays the retained "off" it has
    been holding, and the whole pipeline runs. Nothing may reach the device's
    request queue: the plug was switched out of band and the stored value is
    stale, so acting on it would switch the light off by itself.
    """
    from mqtt2kasa import log
    from mqtt2kasa import main as main_module
    from mqtt2kasa.kasa_wrapper import Kasa
    from mqtt2kasa.main import RunState, handle_main_event_mqtt

    # main.py binds its module logger in its __main__ block, which does not run
    # when it is imported. Without this the handler dies on logger.info() and
    # the test would pass for the wrong reason.
    saved_logger = main_module.logger
    if main_module.logger is None:
        main_module.logger = log.getLogger()
    saved_info = Cfg._info
    Cfg._parse_raw_cfg(
        {
            "mqtt": {"retain": True},
            "locations": {"foo": {"topic": "/foo", "host": "192.0.2.1"}},
        }
    )
    try:
        kasa = Kasa("foo", "/foo", {"host": "192.0.2.1"})
        kasa.curr_state = True  # what the poller found on the device itself
        run_state = RunState()
        run_state.topics["/foo"] = "foo"
        run_state.kasas["foo"] = kasa

        async def go():
            main_events_q = asyncio.Queue()
            mqtt_send_q = asyncio.Queue()

            async def message_stream():
                yield FakeMessage("/foo", b"off", True)

            await mqtt_module.handle_mqtt_messages(message_stream(), main_events_q)
            while not main_events_q.empty():
                await handle_main_event_mqtt(
                    main_events_q.get_nowait(), run_state, mqtt_send_q
                )
            return kasa.recv_q.qsize()

        assert asyncio.run(go()) == 0, "a stale retained value became a device request"
        assert kasa.curr_state is True
    finally:
        Cfg._info = saved_info
        main_module.logger = saved_logger
