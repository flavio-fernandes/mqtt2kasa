import asyncio
import json

from mqtt2kasa import log
from mqtt2kasa.config import Cfg
from mqtt2kasa.events import KasaAvailabilityEvent, KasaStateEvent
from mqtt2kasa import kasa_wrapper
from mqtt2kasa.kasa_wrapper import Kasa
from mqtt2kasa import main


class FakeKasa:
    topic = "/foo"
    curr_state = True
    online = None
    state_name = staticmethod(Kasa.state_name)
    availability_name = staticmethod(Kasa.availability_name)


class StartupOfflineKasa:
    name = "foo"
    host = "127.0.0.1"
    curr_state = None
    curr_brightness = None
    online = None
    offline_after_failures = 1
    poll_interval = 1

    @property
    async def is_on(self):
        return None

    @property
    async def is_dimmable(self):
        return False


def setup_module():
    main.logger = log.getLogger()


def test_offline_after_failures_defaults_to_three():
    previous_info = Cfg._info
    try:
        Cfg._parse_raw_cfg(
            {
                "mqtt": {},
                "globals": {},
                "locations": {"foo": {"host": "127.0.0.1"}},
            }
        )

        assert Cfg().offline_after_failures("foo") == 3
    finally:
        Cfg._info = previous_info


def test_offline_after_failures_uses_global_value():
    previous_info = Cfg._info
    try:
        Cfg._parse_raw_cfg(
            {
                "mqtt": {},
                "globals": {"offline_after_failures": 4},
                "locations": {"foo": {"host": "127.0.0.1"}},
            }
        )

        assert Cfg().offline_after_failures("foo") == 4
    finally:
        Cfg._info = previous_info


def test_offline_after_failures_location_overrides_global_value():
    previous_info = Cfg._info
    try:
        Cfg._parse_raw_cfg(
            {
                "mqtt": {},
                "globals": {"offline_after_failures": 4},
                "locations": {
                    "foo": {
                        "host": "127.0.0.1",
                        "offline_after_failures": 1,
                    }
                },
            }
        )

        assert Cfg().offline_after_failures("foo") == 1
    finally:
        Cfg._info = previous_info


def test_availability_name():
    assert Kasa.availability_name(True) == "online"
    assert Kasa.availability_name(False) == "offline"
    assert Kasa.availability_name(None) == "unknown"


def test_availability_event_publishes_availability_and_status():
    async def run_test():
        run_state = main.RunState()
        run_state.kasas["foo"] = FakeKasa()
        mqtt_send_q = asyncio.Queue()

        await main.handle_availability_event_kasa(
            KasaAvailabilityEvent(name="foo", online=False),
            run_state,
            mqtt_send_q,
        )

        availability_msg = await mqtt_send_q.get()
        status_msg = await mqtt_send_q.get()
        status = json.loads(status_msg.payload)

        assert availability_msg.topic == "/foo/availability"
        assert availability_msg.payload == "offline"
        assert status_msg.topic == "/foo/status"
        assert status["name"] == "foo"
        assert status["state"] == "on"
        assert status["availability"] == "offline"

    asyncio.run(run_test())


def test_state_event_status_includes_availability():
    async def run_test():
        run_state = main.RunState()
        fake_kasa = FakeKasa()
        fake_kasa.online = True
        run_state.kasas["foo"] = fake_kasa
        mqtt_send_q = asyncio.Queue()

        await main.handle_main_event_kasa(
            KasaStateEvent(name="foo", state=True),
            run_state,
            mqtt_send_q,
        )

        state_msg = await mqtt_send_q.get()
        status_msg = await mqtt_send_q.get()
        status = json.loads(status_msg.payload)

        assert state_msg.topic == "/foo"
        assert state_msg.payload == "on"
        assert status["availability"] == "online"

    asyncio.run(run_test())


def test_poller_publishes_offline_when_startup_poll_fails():
    async def run_test():
        async def stop_after_first_poll(interval):
            raise RuntimeError("stop poller")

        previous_sleep = kasa_wrapper._sleep_with_jitter
        kasa_wrapper._sleep_with_jitter = stop_after_first_poll
        try:
            main_events_q = asyncio.Queue()
            kasa = StartupOfflineKasa()

            try:
                await kasa_wrapper.handle_kasa_poller(kasa, main_events_q)
            except RuntimeError as e:
                assert str(e) == "stop poller"

            availability_event = await main_events_q.get()
            assert availability_event.event == "KasaAvailabilityEvent"
            assert availability_event.name == "foo"
            assert availability_event.online is False
            assert kasa.online is False
        finally:
            kasa_wrapper._sleep_with_jitter = previous_sleep

    asyncio.run(run_test())
