"""Coverage for handle_main_event_kasa, which publishes a polled state change.

The handler now distinguishes the first announcement after a (re)start from a
real transition. Only the log line differs, but the KasaStateEvent it reads may
or may not carry old_state, so both shapes are exercised here.
"""

import asyncio
import json

from mqtt2kasa import log
from mqtt2kasa import main as main_module
from mqtt2kasa.config import Cfg
from mqtt2kasa.events import KasaStateEvent
from mqtt2kasa.kasa_wrapper import Kasa
from mqtt2kasa.main import RunState, handle_main_event_kasa


def _published(event):
    """Run the handler for one event and return the (topic, payload) pairs."""
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
        run_state = RunState()
        run_state.topics["/foo"] = "foo"
        run_state.kasas["foo"] = kasa

        async def go():
            q = asyncio.Queue()
            await handle_main_event_kasa(event, run_state, q)
            out = []
            while not q.empty():
                msg = q.get_nowait()
                out.append((msg.topic, msg.payload))
            return out

        return asyncio.run(go())
    finally:
        Cfg._info = saved_info
        main_module.logger = saved_logger


def test_first_announcement_publishes_state_and_status():
    published = _published(KasaStateEvent(name="foo", state=True, old_state=None))
    assert published[0] == ("/foo", "on")
    assert published[1][0] == "/foo/status"
    assert json.loads(published[1][1])["state"] == "on"


def test_real_transition_publishes_state_and_status():
    published = _published(KasaStateEvent(name="foo", state=False, old_state=True))
    assert published[0] == ("/foo", "off")
    assert published[1][0] == "/foo/status"
    assert json.loads(published[1][1])["state"] == "off"


def test_event_without_old_state_is_still_handled():
    """keep_alive and the mqtt handler build KasaStateEvent with no old_state."""
    published = _published(KasaStateEvent(name="foo", state=True))
    assert published[0] == ("/foo", "on")


def test_unknown_device_name_is_ignored():
    published = _published(KasaStateEvent(name="nope", state=True, old_state=None))
    assert published == []
