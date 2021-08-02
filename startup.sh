#!/bin/bash

export MQTT=$(nslookup mosquitto | grep "Address: " | cut -d' ' -f 2)
python3 -m mqtt2kasa.main
