#!/usr/bin/env python
import logging
from logging.handlers import SysLogHandler
from os import path


def getLogger():
    return logging.getLogger("mqtt2kasa")


def initLogger(testing=False):
    logger = getLogger()
    logger.setLevel(logging.INFO)
    log_to_console()
    if testing:
        set_log_level_debug()


def log_to_console():
    consoleHandler = logging.StreamHandler()
    format = "%(asctime)s %(module)12s:%(lineno)-d %(levelname)-8s %(message)s"
    formatter = logging.Formatter(format)
    consoleHandler.setFormatter(formatter)
    getLogger().addHandler(consoleHandler)


def set_log_level_debug():
    getLogger().setLevel(logging.DEBUG)
