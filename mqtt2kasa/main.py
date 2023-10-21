#!/usr/bin/env python
import asyncio
import collections
from contextlib import AsyncExitStack
import re

from aiomqtt import Client, MqttError

from mqtt2kasa import log
from mqtt2kasa.config import Cfg
from mqtt2kasa.events import KasaStateEvent, KasaEmeterEvent, MqttMsgEvent
from mqtt2kasa.kasa_wrapper import (
    Kasa,
    handle_kasa_poller,
    handle_kasa_emeter_poller,
    handle_kasa_requests,
)
from mqtt2kasa.keep_alive import (
    KeepAlive,
    handle_keep_alives,
    handle_main_event_mqtt_ka,
)
from mqtt2kasa.mqtt import (
    handle_mqtt_publish,
    handle_mqtt_messages,
)


class RunState:
    def __init__(self):
        self.kasas: dict[str, Kasa] = {}
        self.topics: dict[str, str] = {}
        self.keep_alives: dict[str, KeepAlive] = {}
        self.keep_alive_topics: dict[str, str] = {}


async def handle_main_event_kasa(
    kasa_state: KasaStateEvent, run_state: RunState, mqtt_send_q: asyncio.Queue
):
    kasa = run_state.kasas.get(kasa_state.name)
    if not kasa:
        logger.warning(
            f"Unable to find device with name {kasa_state.name}. Ignoring kasa event"
        )
        return
    payload = kasa.state_name(kasa_state.state)
    logger.info(
        f"Kasa event requesting mqtt for {kasa_state.name} to publish"
        f" {kasa.topic} as {payload}"
    )
    await mqtt_send_q.put(MqttMsgEvent(topic=kasa.topic, payload=payload))


async def handle_emeter_event_kasa(
    kasa_emeter: KasaEmeterEvent, run_state: RunState, mqtt_send_q: asyncio.Queue
):
    kasa = run_state.kasas.get(kasa_emeter.name)
    if not kasa:
        logger.warning(
            f"Unable to find device with name {kasa_emeter.name}. Ignoring kasa emeter event"
        )
        return
    topic = f"{kasa.topic}/emeter"
    payload = kasa_emeter.emeter_status
    logger.info(
        f"Kasa emeter event requesting mqtt for {kasa_emeter.name} to publish"
        f" {topic} as {payload}"
    )
    await mqtt_send_q.put(MqttMsgEvent(topic=topic, payload=payload))

    # also publish each value as a topic
    # https://github.com/flavio-fernandes/mqtt2kasa/issues/10
    matches = re.findall(r"(\w+)=([^\s>]+)", payload)
    for key, value in matches:
        emeter_topic = f"{topic}/{key}"
        await mqtt_send_q.put(MqttMsgEvent(topic=emeter_topic, payload=value))


async def handle_main_event_mqtt(
    mqtt_msg: MqttMsgEvent, run_state: RunState, mqtt_send_q: asyncio.Queue
):
    name = run_state.topics.get(mqtt_msg.topic)
    is_ka = name is None
    if not name:
        # topic is not used directly for a kasa device. Check if it is a keep alive subscribe
        name = run_state.keep_alive_topics.get(mqtt_msg.topic)
        if not name:
            logger.warning(
                f"Unable to map device from topic {mqtt_msg.topic}. Ignoring mqtt event"
            )
            return
    kasa = run_state.kasas[name]
    if is_ka:
        ka = run_state.keep_alives[name]
        await handle_main_event_mqtt_ka(mqtt_msg, kasa, ka, mqtt_send_q)
        return
    if not mqtt_msg.payload:
        logger.debug(f"No payload for topic {mqtt_msg.topic}. Ignoring mqtt event")
        return
    try:
        translated, new_state = kasa.state_parse(mqtt_msg.payload)
        if translated:
            await mqtt_send_q.put(
                MqttMsgEvent(topic=mqtt_msg.topic, payload=translated)
            )
            return
    except ValueError as e:
        logger.warning(f"Unexpected payload for topic {mqtt_msg.topic}: {e}")
        return
    try:
        kasa.recv_q.put_nowait(KasaStateEvent(name=name, state=new_state))
    except asyncio.queues.QueueFull:
        logger.warning(
            f"Device {name} is too busy to take request to be set as "
            f"{kasa.state_name(new_state)}"
        )
        return
    msg = f"Mqtt event causing device {name} to be set as {kasa.state_name(new_state)}"
    if kasa.state_name(new_state) != mqtt_msg.payload:
        msg += f" ({mqtt_msg.payload})"
    logger.info(msg)


async def handle_main_events(
    run_state: RunState, mqtt_send_q: asyncio.Queue, main_events_q: asyncio.Queue
):
    handlers = {
        "KasaStateEvent": handle_main_event_kasa,
        "KasaEmeterEvent": handle_emeter_event_kasa,
        "MqttMsgEvent": handle_main_event_mqtt,
    }
    while True:
        main_event = await main_events_q.get()
        logger.debug(f"Handling {main_event.event}...")
        handler = handlers.get(main_event.event)
        if handler:
            await handler(main_event, run_state, mqtt_send_q)
        else:
            logger.error(f"No handler found for {main_event.event}")
        main_events_q.task_done()


async def cancel_tasks(tasks):
    logger.info("Cancelling all tasks")
    for task in tasks:
        if task.done():
            continue
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def main_loop():
    global stop_gracefully

    # used to be: https://pypi.org/project/asyncio-mqtt/
    # https://pypi.org/project/aiomqtt/
    logger.debug("Starting main event processing loop")
    cfg = Cfg()
    mqtt_broker_ip = cfg.mqtt_host
    mqtt_client_id = cfg.mqtt_client_id
    mqtt_username = cfg.mqtt_username
    mqtt_password = cfg.mqtt_password
    mqtt_send_q = asyncio.Queue(maxsize=256)
    main_events_q = asyncio.Queue(maxsize=256)

    # We 💛 context managers. Let's create a stack to help
    # us manage them.
    async with AsyncExitStack() as stack:
        # Keep track of the asyncio tasks that we create, so that
        # we can cancel them on exit
        tasks = set()
        stack.push_async_callback(cancel_tasks, tasks)

        client = Client(
            mqtt_broker_ip,
            username=mqtt_username,
            password=mqtt_password,
            client_id=mqtt_client_id,
        )
        await stack.enter_async_context(client)

        messages = await stack.enter_async_context(client.unfiltered_messages())
        task = asyncio.create_task(handle_mqtt_messages(messages, main_events_q))
        tasks.add(task)

        task = asyncio.create_task(handle_mqtt_publish(client, mqtt_send_q))
        tasks.add(task)

        run_state = RunState()
        for name, config in cfg.locations.items():
            topic = cfg.mqtt_topic(name)
            if topic in run_state.topics:
                raise RuntimeError(
                    f"Topic {topic} assigned to more than one device: "
                    f"{name} and {run_state.topics[topic]}"
                )
            run_state.topics[topic] = name
            await client.subscribe(topic)
            run_state.kasas[name] = Kasa(name, topic, config)

        for kasa in run_state.kasas.values():
            tasks.add(asyncio.create_task(handle_kasa_poller(kasa, main_events_q)))
            tasks.add(asyncio.create_task(handle_kasa_requests(kasa)))
            if kasa.emeter_poll_interval:
                tasks.add(
                    asyncio.create_task(handle_kasa_emeter_poller(kasa, main_events_q))
                )

        for name, config in cfg.keep_alives.items():
            if name not in run_state.kasas:
                raise RuntimeError(
                    f"Keep alive {name} must have a corresponding location entry"
                )
            config["location_name"] = name
            ka = KeepAlive(**config)
            topic = ka.subscribe_topic
            if topic in run_state.topics or topic in run_state.keep_alive_topics:
                raise RuntimeError(
                    f"Subscribe topic {topic} for keep alive {name} is not unique"
                )
            run_state.keep_alive_topics[topic] = name
            await client.subscribe(ka.subscribe_topic)
            run_state.keep_alives[name] = ka

        task = asyncio.create_task(
            handle_keep_alives(run_state.kasas, run_state.keep_alives, mqtt_send_q)
        )
        tasks.add(task)

        task = asyncio.create_task(
            handle_main_events(run_state, mqtt_send_q, main_events_q)
        )
        tasks.add(task)

        # Wait for everything to complete (or fail due to, e.g., network errors)
        await asyncio.gather(*tasks)

    logger.debug("all done!")


# cfg_globals
stop_gracefully = False
logger = None


async def main():
    global stop_gracefully

    # Run the advanced_example indefinitely. Reconnect automatically
    # if the connection is lost.
    reconnect_interval = Cfg().reconnect_interval
    while not stop_gracefully:
        try:
            await main_loop()
        except MqttError as error:
            logger.warning(
                f'MQTT error "{error}". Reconnecting in {reconnect_interval} seconds.'
            )
        except (KeyboardInterrupt, SystemExit):
            logger.info("got KeyboardInterrupt")
            stop_gracefully = True
            break
        await asyncio.sleep(reconnect_interval)


if __name__ == "__main__":
    logger = log.getLogger()
    log.initLogger()

    knobs = Cfg().knobs
    if isinstance(knobs, collections.abc.Mapping):
        if knobs.get("log_to_console"):
            log.log_to_console()
        if knobs.get("log_level_debug"):
            log.set_log_level_debug()

    logger.debug("mqtt2kasa process started")
    asyncio.run(main())
    if not stop_gracefully:
        raise RuntimeError("main is exiting")
