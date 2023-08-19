#!/usr/bin/env python
from collections import namedtuple


class BaseEvent:
    def __init__(self, expected_attrs, attrs):
        self.event = self.__class__.__name__
        self.attrs = self._dict_to_attrs(attrs)
        self._check_expected_attrs(expected_attrs)

    def __getattr__(self, attr):
        try:
            return getattr(self.attrs, attr)
        except AttributeError as e:
            raise AttributeError(
                f"{self.event} object is missing {attr} attribute"
            ) from e

    def _check_expected_attrs(self, expected_attrs):
        if expected_attrs:
            for attr in expected_attrs:
                getattr(self, attr)

    @staticmethod
    def _dict_to_attrs(params_dict):
        cls = namedtuple("Attrs", params_dict)
        cls.__new__.__defaults__ = tuple(params_dict.values())
        return cls()


class MqttMsgEvent(BaseEvent):
    def __init__(self, **attrs):
        expected_attrs = "topic", "payload"
        super().__init__(expected_attrs, attrs)


class KasaStateEvent(BaseEvent):
    def __init__(self, **attrs):
        expected_attrs = "name", "state"
        super().__init__(expected_attrs, attrs)


class KasaEmeterEvent(BaseEvent):
    def __init__(self, **attrs):
        expected_attrs = "name", "emeter_status"
        super().__init__(expected_attrs, attrs)
