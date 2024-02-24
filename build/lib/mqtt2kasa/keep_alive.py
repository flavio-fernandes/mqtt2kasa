#!/usr/bin/env python
import asyncio
from collections import namedtuple
from datetime import datetime
from typing import Dict

from mqtt2kasa import log
from mqtt2kasa.config import Cfg
from mqtt2kasa.events import MqttMsgEvent, KasaStateEvent
from mqtt2kasa.kasa_wrapper import Kasa

logger = log.getLogger()


class KeepAlive:
    def __init__(self, **attrs):
        self.attrs = self._dict_to_attrs(attrs)
        self._check_expected_attrs()
        self.keep_alives_counter = 0
        self.last_send_ts = datetime.now()
        self.last_receive_ts = datetime.now()
        self.last_receive_value = None

    def __getattr__(self, attr):
        try:
            return getattr(self.attrs, attr)
        except AttributeError as e:
            raise AttributeError(f"KeepAlive object is missing {attr} attribute") from e

    def _check_expected_attrs(self):
        expected_attrs = [
            ("location_name", str),
            ("interval", int),
            ("timeout", int),
            ("publish_topic", str),
            ("subscribe_topic", str),
        ]
        for attr, attr_type in expected_attrs:
            val = getattr(self, attr)
            if not isinstance(val, attr_type):
                raise AttributeError(f"{attr} attribute is not type {attr_type}")

    @staticmethod
    def _dict_to_attrs(params_dict):
        cls = namedtuple("Attrs", params_dict)
        cls.__new__.__defaults__ = tuple(params_dict.values())
        return cls()


async def handle_main_event_mqtt_ka(
    mqtt_msg: MqttMsgEvent, kasa: Kasa, ka: KeepAlive, mqtt_send_q: asyncio.Queue
):
    ka.last_receive_ts = datetime.now()
    if mqtt_msg.payload:
        ka.last_receive_value = mqtt_msg.payload

    if kasa.curr_state:
        logger.debug(f"Received keep alive from {ka.location_name}")
        return

    logger.info(
        f"Received keep alive for {ka.location_name} triggering device to be turned on"
    )
    try:
        kasa.recv_q.put_nowait(KasaStateEvent(name=ka.location_name, state=True))
        await mqtt_send_q.put(
            MqttMsgEvent(topic=kasa.topic, payload=kasa.state_name(True))
        )
    except asyncio.queues.QueueFull:
        logger.warning(
            f"Device {ka.location_name} is too busy to take request to be set as "
            f"{kasa.state_name(True)}"
        )


async def handle_keep_alives(
    kasas: Dict[str, Kasa], kas: Dict[str, KeepAlive], mqtt_send_q: asyncio.Queue
):
    if not kas:
        logger.info(
            "No keep alives to monitor based on config: handle_keep_alives is done."
        )
        return

    ka_task_interval = Cfg().keep_alive_task_interval
    while True:
        await asyncio.sleep(ka_task_interval)

        for name, ka in kas.items():
            kasa = kasas[name]
            if not kasa.curr_state:
                # if device is not on, we are not interested in it
                ka.keep_alives_counter = 0
                continue

            now = datetime.now()
            # see if it is time to poke keep alive watchdog topic
            tdelta = now - ka.last_send_ts
            tdeltaSecs = int(tdelta.total_seconds())
            interval = max(ka_task_interval * 2, ka.interval)
            if tdeltaSecs >= interval:
                if ka.publish_topic:
                    await mqtt_send_q.put(
                        MqttMsgEvent(
                            topic=ka.publish_topic, payload=ka.last_receive_value
                        )
                    )
                ka.last_send_ts = datetime.now()
                # reset last_send_ts on the first ka send after activation
                if not ka.keep_alives_counter:
                    ka.last_receive_ts = ka.last_send_ts
                ka.keep_alives_counter += 1
                continue

            # see if it has been too long w/out an answer
            tdelta = now - ka.last_receive_ts
            tdeltaSecs = int(tdelta.total_seconds())
            if tdeltaSecs >= ka.timeout and ka.keep_alives_counter:
                logger.info(f"Keep alive for {name} expired after {tdeltaSecs} seconds")
                try:
                    kasa.recv_q.put_nowait(KasaStateEvent(name=name, state=False))
                    await mqtt_send_q.put(
                        MqttMsgEvent(topic=kasa.topic, payload=kasa.state_name(False))
                    )
                except asyncio.queues.QueueFull:
                    logger.warning(
                        f"Device {name} is too busy to take request to be set as "
                        f"{kasa.state_name(False)}"
                    )
