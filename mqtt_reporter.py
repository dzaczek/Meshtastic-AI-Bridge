"""
mqtt_reporter.py - Publish our node's position to Meshtastic MQTT brokers
so the node appears on public maps like https://meshtastic.liamcottle.net/

Runs as a background thread. Publishes to two targets:
  1. liamcottle map server (32-bit precision) — for the liamcottle map
  2. public meshtastic.org (16-bit precision) — for other maps / MQTT mesh
"""
import json
import logging
import os
import threading
import time

logger = logging.getLogger("mqtt_reporter")

# How often to publish position (seconds)
_PUBLISH_INTERVAL = 60  # 1 min — keep node "online" on maps
_MQTT_ROOT = "msh"

# ---------------------------------------------------------------------------
# Broker definitions (host, port, user, pass, precision_bits)
# ---------------------------------------------------------------------------
_BROKERS = [
    {
        "host": "mqtt.meshtastic.liamcottle.net",
        "port": 1883,
        "user": "uplink",
        "password": "uplink",
        "precision_bits": 32,
        "label": "liamcottle",
    },
    {
        "host": "mqtt.meshtastic.org",
        "port": 1883,
        "user": "meshdev",
        "password": "large4cats",
        "precision_bits": 16,
        "label": "public",
    },
]


class MqttReporter:
    """Periodically publishes the bridge's own position to MQTT."""

    def __init__(self, get_position, get_node_id, get_online_nodes=None,
                 get_neighbors=None,
                 region="EU_868", channel_name="LongFast", hw_model="RAK11200",
                 node_name="MARVIN-GPP", short_name="MN"):
        self._get_position = get_position       # callable → dict or None
        self._get_node_id = get_node_id         # callable → int (node_num) or None
        self._get_online_nodes = get_online_nodes  # callable → int or None
        self._get_neighbors = get_neighbors     # callable → list of dicts or None
        self._region = region
        self._channel_name = channel_name
        self._hw_model = hw_model
        self._node_name = node_name
        self._short_name = short_name
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="mqtt-reporter")
        self._thread.start()
        logger.info("MqttReporter started — interval %ds", _PUBLISH_INTERVAL)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _loop(self):
        first = True
        while self._running:
            try:
                if first:
                    time.sleep(60)
                    first = False
                else:
                    time.sleep(_PUBLISH_INTERVAL)
                if not self._running:
                    break
                self._publish_all()
            except Exception:
                logger.exception("MqttReporter loop error")
                time.sleep(30)

    def _connect(self, broker):
        import paho.mqtt.client as mqtt
        client = mqtt.Client()
        client.username_pw_set(broker["user"], broker["password"])
        connected = threading.Event()

        def _on_connect(c, u, f, rc):
            if rc == 0:
                connected.set()
            else:
                logger.warning("MqttReporter: %s connect failed rc=%d",
                               broker["label"], rc)

        client.on_connect = _on_connect
        client.connect(broker["host"], broker["port"], keepalive=60)
        client.loop_start()
        if not connected.wait(timeout=10.0):
            logger.warning("MqttReporter: %s connect timed out", broker["label"])
        return client

    def _disconnect(self, client):
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

    def _publish_all(self):
        node_num = self._get_node_id()
        if node_num is None:
            logger.warning("MqttReporter: node_id not available — skipping")
            return

        position = self._get_position()
        if not position or position.get('lat') is None:
            logger.warning("MqttReporter: no position — skipping")
            return

        for broker in _BROKERS:
            try:
                self._publish_one(broker, node_num, position)
            except Exception:
                logger.exception("MqttReporter: %s publish error",
                                 broker["label"])

    def _publish_one(self, broker, node_num, position):
        node_id_hex = f"{node_num:x}"
        topic_e = (f"{_MQTT_ROOT}/{self._region}/2/e/"
                   f"{self._channel_name}/!{node_id_hex}")

        num_online = 1
        if self._get_online_nodes:
            try:
                num_online = self._get_online_nodes() or 1
            except Exception:
                pass

        precision = broker["precision_bits"]

        # MapReport
        map_env = _build_map_report_envelope(node_num, position,
                                             precision_bits=precision,
                                             num_online_nodes=num_online,
                                             hw_model=self._hw_model,
                                             region=self._region,
                                             long_name=self._node_name,
                                             short_name=self._short_name)

        # NeighborInfo — collect neighbor data from device
        neighbors = []
        if self._get_neighbors:
            try:
                neighbors = self._get_neighbors() or []
            except Exception:
                pass

        client = None
        try:
            client = self._connect(broker)
            # MapReport
            client.publish(topic_e, map_env.SerializeToString(), qos=1) \
                  .wait_for_publish(timeout=5.0)

            # NeighborInfo (separate packet)
            if neighbors:
                nei_env = _build_neighbor_info_envelope(node_num, neighbors,
                                                        hw_model=self._hw_model,
                                                        long_name=self._node_name,
                                                        short_name=self._short_name)
                client.publish(topic_e, nei_env.SerializeToString(), qos=1) \
                      .wait_for_publish(timeout=5.0)

            logger.info("MqttReporter: %s ← %.5f,%.5f [MapReport %db, %d neighbors]",
                        broker["label"], position['lat'], position['lon'],
                        precision, len(neighbors))
        finally:
            if client:
                self._disconnect(client)


# ---------------------------------------------------------------------------
# Protobuf / JSON builders
# ---------------------------------------------------------------------------

def _build_map_report_envelope(node_num, position, *,
                                precision_bits=32, num_online_nodes=1,
                                hw_model="RAK11200",
                                region="EU_868", long_name="", short_name=""):
    """Build a ServiceEnvelope wrapping a MeshPacket with MapReport payload."""
    from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2

    now = int(time.time())
    lat = float(position['lat'])
    lon = float(position['lon'])

    report = mqtt_pb2.MapReport()
    report.long_name = long_name or ""
    report.short_name = short_name or ""
    report.role = 0  # CLIENT
    report.hw_model = _hw_model_enum(hw_model)
    report.firmware_version = "2.5.0"
    report.region = _region_enum(region)
    report.modem_preset = 4  # MEDIUM_FAST
    report.has_default_channel = True
    report.latitude_i = int(lat * 1e7)
    report.longitude_i = int(lon * 1e7)
    if position.get('alt'):
        report.altitude = int(position['alt'])
    report.position_precision = precision_bits
    report.num_online_local_nodes = num_online_nodes
    report.has_opted_report_location = True

    mp = mesh_pb2.MeshPacket()
    mp.id = (now * 1000 + (node_num & 0xFFFF)) & 0xFFFFFFFF
    setattr(mp, 'from', node_num)
    mp.to = 0xFFFFFFFF
    mp.want_ack = False
    mp.decoded.portnum = portnums_pb2.MAP_REPORT_APP
    mp.decoded.payload = report.SerializeToString()
    mp.hop_start = 3
    mp.hop_limit = 3

    envelope = mqtt_pb2.ServiceEnvelope()
    envelope.channel_id = "LongFast"
    envelope.gateway_id = f"!{node_num:x}"
    envelope.packet.CopyFrom(mp)
    return envelope


def _build_neighbor_info_envelope(node_num, neighbors, *,
                                    hw_model="RAK11200",
                                    long_name="", short_name=""):
    """Build a ServiceEnvelope with NeighborInfo payload."""
    from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2

    now = int(time.time())

    info = mesh_pb2.NeighborInfo()
    info.node_id = node_num
    info.node_broadcast_interval_secs = 3600  # default broadcast interval

    for nb in neighbors:
        n = info.neighbors.add()
        n.node_id = nb.get('node_id', 0)
        snr = nb.get('snr', 0)
        if snr is not None:
            n.snr = float(snr)

    mp = mesh_pb2.MeshPacket()
    mp.id = (now * 1000 + (node_num & 0xFFFF)) & 0xFFFFFFFF
    setattr(mp, 'from', node_num)
    mp.to = 0xFFFFFFFF
    mp.want_ack = False
    mp.decoded.portnum = portnums_pb2.NEIGHBORINFO_APP
    mp.decoded.payload = info.SerializeToString()
    mp.hop_start = 3
    mp.hop_limit = 3

    envelope = mqtt_pb2.ServiceEnvelope()
    envelope.channel_id = "LongFast"
    envelope.gateway_id = f"!{node_num:x}"
    envelope.packet.CopyFrom(mp)
    return envelope


def _region_enum(region_str):
    from meshtastic.protobuf import config_pb2
    mapping = {
        "EU_868": config_pb2.Config.LoRaConfig.RegionCode.EU_868,
        "US": config_pb2.Config.LoRaConfig.RegionCode.US,
        "EU_433": config_pb2.Config.LoRaConfig.RegionCode.EU_433,
    }
    if region_str in mapping:
        return mapping[region_str]
    try:
        return getattr(config_pb2.Config.LoRaConfig.RegionCode, region_str)
    except (AttributeError, TypeError):
        return 0


def _hw_model_enum(hw_str):
    from meshtastic.protobuf import mesh_pb2
    mapping = {
        "RAK11200": mesh_pb2.HardwareModel.RAK11200,
        "RAK4631":  mesh_pb2.HardwareModel.RAK4631,
        "TBEAM":    mesh_pb2.HardwareModel.TBEAM,
        "HELTEC_V3": mesh_pb2.HardwareModel.HELTEC_V3,
        "HELTEC_V4": mesh_pb2.HardwareModel.HELTEC_V4,
    }
    if hw_str in mapping:
        return mapping[hw_str]
    try:
        return getattr(mesh_pb2.HardwareModel, hw_str)
    except (AttributeError, TypeError):
        pass
    return mesh_pb2.HardwareModel.RAK11200
