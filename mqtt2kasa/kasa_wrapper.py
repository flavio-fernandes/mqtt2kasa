#!/usr/bin/env python
import asyncio
import random
from typing import Optional

from asyncio_throttle import Throttler
from kasa import Discover, EmeterStatus
from kasa.smartdevice import SmartDevice, SmartDeviceException

from mqtt2kasa import log
from mqtt2kasa.config import Cfg
from mqtt2kasa.events import KasaStateEvent, KasaEmeterEvent

logger = log.getLogger()


class Kasa:
    STATE_ON = "on"
    STATE_OFF = "off"

    _discovered_devices = None

    def __init__(self, name: str, topic: str, config: dict):
        self.name = name
        self.topic = topic
        self.host = config.get("host")
        self.alias = config.get("alias")
        self.poll_interval = Cfg().poll_interval(name)
        self.emeter_poll_interval = Cfg().emeter_poll_interval(name)
        self.recv_q = asyncio.Queue(maxsize=4)
        self.throttler = Throttler(rate_limit=4, period=60)
        self.curr_state = None
        self._device = None
        assert self.host or self.alias

    async def _get_device(self) -> SmartDevice:
        if not self._device:
            if self.host:
                self._device = await Discover.discover_single(self.host)
                self.alias = self._device.alias
            else:
                self.host, self._device = await self._find_by_alias(
                    self.name, self.alias
                )
            logger.info(
                f"Discovered {self.host} alias:'{self._device.alias}'"
                f" model:{self._device.model}"
                f" mac:{self._device.mac}"
            )
        return self._device

    @property
    def started(self):
        return self._device and isinstance(self.curr_state, bool)

    @classmethod
    async def _find_by_alias(cls, name, alias, retry=0):
        if not cls._discovered_devices:
            cls._discovered_devices = await Discover.discover()
        try:
            for addr, device in cls._discovered_devices.items():
                await device.update()
                if device.alias == alias:
                    return addr, device
        except SmartDeviceException as e:
            logger.warning(
                f"Discovering device with alias {alias} did not go well: {e}"
            )

        if retry < 3:
            cls._discovered_devices = None
            return await cls._find_by_alias(name, alias, retry + 1)
        raise RuntimeError(f"Unable to locate {name} from alias {alias}")

    @property
    async def is_on(self) -> Optional[bool]:
        try:
            device = await self._get_device()
            await device.update()
            return device.is_on
        except SmartDeviceException as e:
            logger.error(f"{self.host} unable to fetch is_on: {e}")
        # implicit return None

    async def turn_on(self):
        async with self.throttler:
            try:
                device = await self._get_device()
                await device.turn_on()
                self.curr_state = True
            except SmartDeviceException as e:
                logger.error(f"{self.host} unable to turn_on: {e}")

    async def turn_off(self):
        async with self.throttler:
            try:
                device = await self._get_device()
                await device.turn_off()
                self.curr_state = False
            except SmartDeviceException as e:
                logger.error(f"{self.host} unable to turn_off: {e}")

    @property
    async def has_emeter(self) -> Optional[bool]:
        try:
            device = await self._get_device()
            await device.update()
            return device.has_emeter
        except SmartDeviceException as e:
            logger.error(f"{self.host} unable to get has_emeter: {e}")
        # implicit return None

    @property
    async def emeter_realtime(self) -> Optional[EmeterStatus]:
        try:
            device = await self._get_device()
            await device.update()
            return device.emeter_realtime
        except SmartDeviceException as e:
            logger.error(f"{self.host} unable to fetch emeter: {e}")
        # implicit return None

    @classmethod
    def state_from_name(cls, is_on: Optional[str]) -> bool:
        return is_on == cls.STATE_ON

    @classmethod
    def state_name(cls, is_on: Optional[bool]) -> str:
        if is_on is None:
            return "¯\\_(ツ)_/¯"
        return cls.STATE_ON if is_on else cls.STATE_OFF

    @staticmethod
    def state_is_toggle(is_toggle: str) -> bool:
        return is_toggle.lower() in ("toggle", "flip", "other", "change", "reverse")

    @classmethod
    def state_is_on(cls, is_on: str) -> bool:
        return is_on.lower() in (
            cls.STATE_ON,
            "yes",
            "1",
            "go",
            "yeah",
            "yay",
            "woot",
        )

    @classmethod
    def state_is_off(cls, is_off: str) -> bool:
        return is_off.lower() in (
            cls.STATE_OFF,
            "no",
            "0",
            "stop",
            "boo",
            "nay",
            "nuke",
        )

    def state_parse(self, payload: str) -> (str, bool):
        if payload in (self.STATE_ON, self.STATE_OFF):
            return None, self.state_from_name(payload)
        if self.state_is_toggle(payload):
            new_state = False if self.curr_state else True
            return self.state_name(new_state), new_state
        if self.state_is_on(payload):
            return self.STATE_ON, True
        if self.state_is_off(payload):
            return self.STATE_OFF, False
        raise ValueError(f"cannot translate {payload}")


async def handle_kasa_poller(kasa: Kasa, main_events_q: asyncio.Queue):
    fails = 0
    while True:
        # chatty
        # logger.debug(f"Polling {kasa.name} now. Interval is {kasa.poll_interval} seconds")
        new_state = await kasa.is_on
        if kasa.curr_state != new_state or fails:
            if new_state is None:
                fails += 1
                logger.error(f"Polling {kasa.name} ({kasa.host}) failed {fails} times")
            else:
                fails = 0
                await main_events_q.put(
                    KasaStateEvent(
                        name=kasa.name, state=new_state, old_state=kasa.curr_state
                    )
                )
                kasa.curr_state = new_state
        await _sleep_with_jitter(kasa.poll_interval)


async def handle_kasa_emeter_poller(kasa: Kasa, main_events_q: asyncio.Queue):
    fails = 0
    while True:
        # chatty
        # logger.debug(f"Polling {kasa.name} emeter now. Interval is {kasa.emeter_poll_interval} seconds")
        if await kasa.has_emeter == False:
            logger.info(f"{kasa.name} has no emeter. no emeter polling is needed")
            break

        emeter_status = await kasa.emeter_realtime
        if emeter_status is None:
            fails += 1
            logger.error(
                f"Polling {kasa.name} emeter ({kasa.host}) failed {fails} times"
            )
        else:
            fails = 0
            await main_events_q.put(
                KasaEmeterEvent(name=kasa.name, emeter_status=str(emeter_status))
            )
        await _sleep_with_jitter(kasa.emeter_poll_interval)


async def _sleep_with_jitter(interval):
    await asyncio.sleep(interval)

    # In order to avoid all processes sleeping and waking up at the same time,
    # add a little jitter. Pick a value between 0 and 1.2 seconds
    jitter = random.randint(99, 1201)
    jitterSleep = float(jitter) / 1000
    await asyncio.sleep(jitterSleep)


async def handle_kasa_requests(kasa: Kasa):
    while True:
        if not kasa.started:
            logger.debug(f"{kasa.name} waiting to get started by poller")
            await asyncio.sleep(3)
            continue

        kasa_state_event = await kasa.recv_q.get()
        wanted_state = kasa_state_event.state
        if wanted_state != kasa.curr_state:
            logger.info(
                f"{kasa.name} changing state to {kasa.state_name(wanted_state)}"
            )
            if wanted_state:
                await kasa.turn_on()
            else:
                await kasa.turn_off()
        else:
            logger.debug(
                f"{kasa.name} state unchanged as {kasa.state_name(wanted_state)}"
            )
        kasa.recv_q.task_done()
