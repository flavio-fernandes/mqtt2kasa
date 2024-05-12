# Fork
This is a fork of https://github.com/flavio-fernandes/mqtt2kasa

# mqtt2kasa
#### Python-based project that provides wrapper to python-kasa for MQTT access

This repo provides an MQTT interface to the awesome [python-kasa](https://github.com/python-kasa/python-kasa) library.
With that, one can use MQTT clients to turn on/off any compatible TP-Link device. Conversely, by subscribing
to specific MQTT topics, users can be notified about state changes to any device configured.

The TP-Link / Kasa devices managed are kept in an easy to edit YAML file that looks like this:

```yaml
mqtt:
    # ip/dns for the mqtt broker
    host: 192.168.1.250
    username: <optional mqtt username>
    password: <optional mqtt password>
    # retain: false
    # qos: 0
globals:
    # every location will be managed using a unique mqtt topic
    # unless explicitly specified, this format will be used
    topic_format: /{}/switch
    # kasa will monitor the current state of the device every
    # poll interval, in seconds. You can override on a per device
    poll_interval: 11
    # if devices support metering (aka emeter), use this poll
    # interval to publish it. You can override on a per device
    # emeter_poll_interval: 600
locations:
    # coffee maker. To turn it on, use mqtt publish
    # topic: /coffee_maker/switch payload: on
    # subscribe to /coffee_maker/switch to know its state
    coffee_maker:
        host: 192.168.1.21
    # toaster is similar to the coffee maker, except it relies on
    # kasa discovery in order to locate the device via its alias.
    toaster:
        alias: toaster
    # example where topic is explicitly provided for a given device
    kitchen lights:
        host: 192.168.1.22
        topic: /kitchen/light_switch
    # example where we indicate a specific poll intervals
    pantry:
        alias: storage
        poll_interval: 120
        emeter_poll_interval: 1800
```

Devices are connected via **host** or discovered by Kasa via **alias**. There are more attributes
for further customizations, shown in the
[data/config.yaml](https://github.com/flavio-fernandes/mqtt2kasa/blob/main/data/config.yaml) file.

Starting this project can be done by setting up a service (see 
[mqtt2kasa.service](https://github.com/flavio-fernandes/mqtt2kasa/blob/main/mqtt2kasa/bin/mqtt2kasa.service.vagrant) as 
reference), or doing the following steps:
```shell script
$ ./mqtt2kasa/bin/create-env.sh && \
  source ./env/bin/activate && \
  export PYTHONPATH=${PWD}

$ python3 mqtt2kasa/main.py ./data/config.yaml
```

Granted the config properly refers to the TP-Link devices in the network, use regular MQTT tools for
controlling and monitoring. Example below.

Controlling the devices via MQTT via publish:
```shell script
$ MQTT=192.168.1.250 && \
  mosquitto_pub -h $MQTT -t /kitchen/light_switch -m off
```

Subscribe to see changes to devices, regardless on how they were controlled:
```shell script
$ MQTT=192.168.1.250 && \
  mosquitto_sub -F '@Y-@m-@dT@H:@M:@S@z : %q : %t : %p' -h $MQTT -t '/+/switch' -t /kitchen/light_switch

2021-02-18T10:16:19-0500 : 0 : /kitchen/light_switch : on
2021-02-18T10:16:26-0500 : 0 : /kitchen/light_switch : off
2021-01-30T21:43:03-0500 : 0 : /toaster/switch : on
```

**NOTE on Metering**: If metering is supported by device and `emeter_poll_interval` was provided, it will be published via topics that end with "emeter":

```
$ mosquitto_sub -h $MQTT -t '/+/switch/emeter' -t '/+/switch/emeter/#'
```

In order to damper endless on/off cycles, this implementation sets an 
[async throttle](https://pypi.org/project/asyncio-throttle/) for each device.
If there is a need to tweak that, the attributes are located in
[kasa_wrapper.py](https://github.com/flavio-fernandes/mqtt2kasa/blob/60e37a8e527a04eee54853d42366de314c10cefe/mqtt2kasa/kasa_wrapper.py#L30-L31).

**NOTE:** Use python 3.7 or newer, as this project requires a somewhat
recent implementation of [asyncio](https://realpython.com/async-io-python/).

# Docker
There is a docker image aderesh/mqtt2kasa. Please see `docker-compose.yaml` for usage examples.

### TODO

- Add support for the smart strip, so each 'child' can be controlled independently;
- Expose throttle config instead of hardcoded values;
- Improve documentation?!?
- Use strict yaml (https://hitchdev.com/strictyaml/)
