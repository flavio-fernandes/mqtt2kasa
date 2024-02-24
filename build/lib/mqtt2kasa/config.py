#!/usr/bin/env python
import collections
import os
import sys
from collections import namedtuple

import yaml

from mqtt2kasa import const
from mqtt2kasa import log

CFG_FILENAME = os.path.dirname(os.path.abspath(const.__file__)) + "/../data/config.yaml"
Info = namedtuple("Info", "mqtt knobs cfg_globals locations keep_alives raw_cfg")


class Cfg:
    _info = None  # class (or static) variable

    def __init__(self):
        pass

    @property
    def mqtt_host(self):
        attr = self._get_info().mqtt
        if isinstance(attr, collections.abc.Mapping):
            return attr.get("host", const.MQTT_DEFAULT_BROKER_IP)
        return const.MQTT_DEFAULT_BROKER_IP

    @property
    def mqtt_client_id(self):
        attr = self._get_info().mqtt
        if isinstance(attr, collections.abc.Mapping):
            return attr.get("client_id", const.MQTT_DEFAULT_CLIENT_ID)
        return const.MQTT_DEFAULT_CLIENT_ID

    @property
    def mqtt_username(self):
        attr = self._get_info().mqtt
        if isinstance(attr, collections.abc.Mapping):
            return attr.get("username", None)
        return None

    @property
    def mqtt_password(self):
        attr = self._get_info().mqtt
        if isinstance(attr, collections.abc.Mapping):
            return attr.get("password", None)
        return None

    @property
    def mqtt_retain(self):
        attr = self._get_info().mqtt
        if isinstance(attr, collections.abc.Mapping):
            return attr.get("retain", False)
        return False

    @property
    def mqtt_qos(self):
        attr = self._get_info().mqtt
        if isinstance(attr, collections.abc.Mapping):
            return attr.get("qos", 0)
        return 0

    @property
    def reconnect_interval(self):
        attr = self._get_info().mqtt
        if isinstance(attr, collections.abc.Mapping):
            return attr.get("reconnect_interval", const.MQTT_DEFAULT_RECONNECT_INTERVAL)
        return const.MQTT_DEFAULT_RECONNECT_INTERVAL

    @property
    def knobs(self):
        return self._get_info().knobs

    def mqtt_topic(self, location_name):
        locations = self._get_info().locations
        if isinstance(locations, collections.abc.Mapping):
            location_attributes = locations.get(location_name, {})
            if location_attributes.get("topic"):
                return location_attributes["topic"].format(location_name)
        cfg_globals = self._get_info().cfg_globals
        topic_format = cfg_globals.get("topic_format")
        return (
            topic_format.format(location_name)
            if topic_format
            else const.MQTT_DEFAULT_CLIENT_TOPIC_FORMAT.format(location_name)
        )

    @property
    def keep_alive_task_interval(self):
        cfg_globals = self._get_info().cfg_globals
        return float(
            cfg_globals.get("keep_alive_task_interval")
            or const.KEEP_ALIVE_DEFAULT_TASK_INTERVAL
        )

    def poll_interval(self, location_name):
        locations = self._get_info().locations
        if isinstance(locations, collections.abc.Mapping):
            location_attributes = locations.get(location_name, {})
            if location_attributes.get("poll_interval"):
                return float(location_attributes["poll_interval"])
        cfg_globals = self._get_info().cfg_globals
        return float(
            cfg_globals.get("poll_interval") or const.KASA_DEFAULT_POLL_INTERVAL
        )

    def emeter_poll_interval(self, location_name):
        locations = self._get_info().locations
        if isinstance(locations, collections.abc.Mapping):
            location_attributes = locations.get(location_name, {})
            if location_attributes.get("emeter_poll_interval"):
                return float(location_attributes["emeter_poll_interval"])
        cfg_globals = self._get_info().cfg_globals
        return float(
            cfg_globals.get("emeter_poll_interval")
            or const.KASA_DEFAULT_EMETER_POLL_INTERVAL
        )

    @property
    def locations(self):
        return self._get_info().locations

    @property
    def keep_alives(self):
        return self._get_info().keep_alives

    @classmethod
    def _get_config_filename(cls):
        if len(sys.argv) > 1:
            return sys.argv[1]
        return CFG_FILENAME

    @classmethod
    def _get_info(cls):
        if not cls._info:
            config_filename = cls._get_config_filename()
            logger.info("loading yaml config file %s", config_filename)
            with open(config_filename, "r") as ymlfile:
                raw_cfg = yaml.safe_load(ymlfile)
                cls._parse_raw_cfg(raw_cfg)
        return cls._info

    @classmethod
    def _parse_raw_cfg(cls, raw_cfg):
        cfg_globals = raw_cfg.get("globals", {})
        assert isinstance(cfg_globals, dict)
        locations = raw_cfg.get("locations")
        assert isinstance(locations, dict)
        keep_alives = raw_cfg.get("keep_alives", {})
        assert isinstance(keep_alives, dict)

        cls._info = Info(
            raw_cfg.get("mqtt"),
            raw_cfg.get("knobs", {}),
            cfg_globals,
            locations,
            keep_alives,
            raw_cfg,
        )


# =============================================================================


logger = log.getLogger()
if __name__ == "__main__":
    log.initLogger()
    c = Cfg()
    logger.info("c.knobs: {}".format(c.knobs))
    logger.info("c.mqtt_host: {}".format(c.mqtt_host))
    logger.info("c.cfg_globals: {}".format(c.cfg_globals))
    logger.info("c.locations: {}".format(c.locations))
    logger.info("c.keep_alives: {}".format(c.keep_alives))
