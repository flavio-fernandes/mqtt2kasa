import asyncio

from mqtt2kasa import log
from mqtt2kasa.config import Cfg
from mqtt2kasa.events import MqttMsgEvent

logger = log.getLogger()


async def handle_mqtt_publish(client, mqtt_send_q: asyncio.Queue):
    c = Cfg()
    mqtt_qos = c.mqtt_qos
    mqtt_retain = c.mqtt_retain
    logger.info(
        f"handle_mqtt_publish task started. Using retain:{mqtt_retain} and qos:{mqtt_qos}"
    )
    while True:
        mqtt_msg = await mqtt_send_q.get()
        topic, payload = mqtt_msg.topic, mqtt_msg.payload
        # logger.debug(f"Publishing: {topic} {payload}")
        try:
            await client.publish(
                topic, payload, timeout=15, qos=mqtt_qos, retain=mqtt_retain
            )
            logger.debug(f"Published: {topic} {payload}")
        except Exception as e:
            logger.error("client failed publish mqtt %s %s : %s", topic, payload, e)
        mqtt_send_q.task_done()
        # Dampen publishes. This is a fail-safe and should not affect anything unless
        # there is a bug lurking somewhere
        await asyncio.sleep(1)


async def handle_mqtt_messages(messages, main_events_q: asyncio.Queue):
    async for message in messages:
        msg_topic = message.topic
        msg_payload = message.payload.decode()
        logger.debug(f"Received mqtt topic:{msg_topic} payload:{msg_payload}")
        await main_events_q.put(MqttMsgEvent(topic=msg_topic, payload=msg_payload))
