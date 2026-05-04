"""
MQTT-SN to MQTT Gateway
========================
Listens for MQTT-SN packets over UDP and forwards PUBLISH messages
to an MQTT broker using the paho-mqtt client.

Usage:
    pip install paho-mqtt
    python mqttsn_gateway.py

Configuration via environment variables or edit the CONFIG block below.

Supported MQTT-SN message types:
  - CONNECT / CONNACK
  - REGISTER / REGACK
  - PUBLISH / PUBACK
  - SUBSCRIBE / SUBACK
  - PINGREQ / PINGRESP
  - DISCONNECT
"""

import socket
import struct
import logging
import threading
import os
import time
from typing import Dict, Tuple

import paho.mqtt.client as mqtt
from ..globals import MQTTSN_GATEWAY_HOST, MQTTSN_GATEWAY_PORT
# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
CONFIG = {
    "MQTTSN_HOST":   MQTTSN_GATEWAY_HOST,
    "MQTTSN_PORT":   MQTTSN_GATEWAY_PORT,
    "MQTT_HOST":     os.getenv("MQTT_HOST",     "localhost"),
    "MQTT_PORT":     int(os.getenv("MQTT_PORT",    "1883")),
}

logging.basicConfig(
    level=getattr(logging, 'DEBUG'),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("mqttsn-gateway")

# ──────────────────────────────────────────────
# MQTT-SN message type constants
# ──────────────────────────────────────────────
MSG_ADVERTISE    = 0x00
MSG_SEARCHGW     = 0x01
MSG_GWINFO       = 0x02
MSG_CONNECT      = 0x04
MSG_CONNACK      = 0x05
MSG_WILLTOPICREQ = 0x06
MSG_WILLTOPIC    = 0x07
MSG_WILLMSGREQ   = 0x08
MSG_WILLMSG      = 0x09
MSG_REGISTER     = 0x0A
MSG_REGACK       = 0x0B
MSG_PUBLISH      = 0x0C
MSG_PUBACK       = 0x0D
MSG_PUBCOMP      = 0x0E
MSG_PUBREC       = 0x0F
MSG_PUBREL       = 0x10
MSG_SUBSCRIBE    = 0x12
MSG_SUBACK       = 0x13
MSG_UNSUBSCRIBE  = 0x14
MSG_UNSUBACK     = 0x15
MSG_PINGREQ      = 0x16
MSG_PINGRESP     = 0x17
MSG_DISCONNECT   = 0x18
MSG_WILLTOPICUPD = 0x1A
MSG_WILLTOPICRESP= 0x1B
MSG_WILLMSGUPD   = 0x1C
MSG_WILLMSGRESP  = 0x1D

# Return codes
RC_ACCEPTED            = 0x00
RC_REJECTED_CONGESTION = 0x01
RC_REJECTED_INVALID_ID = 0x02
RC_REJECTED_NOT_SUPPORTED = 0x03

# ──────────────────────────────────────────────
# Packet builders
# ──────────────────────────────────────────────

def build_connack(return_code: int = RC_ACCEPTED) -> bytes:
    # Length(1) + MsgType(1) + ReturnCode(1) = 3 bytes
    return struct.pack("BBB", 3, MSG_CONNACK, return_code)


def build_regack(topic_id: int, msg_id: int, return_code: int = RC_ACCEPTED) -> bytes:
    # Length(1) + MsgType(1) + TopicId(2) + MsgId(2) + ReturnCode(1) = 7 bytes
    return struct.pack("!BBHHB", 7, MSG_REGACK, topic_id, msg_id, return_code)


def build_puback(topic_id: int, msg_id: int, return_code: int = RC_ACCEPTED) -> bytes:
    # Length(1) + MsgType(1) + TopicId(2) + MsgId(2) + ReturnCode(1) = 7 bytes
    return struct.pack("!BBHHB", 7, MSG_PUBACK, topic_id, msg_id, return_code)


def build_suback(qos: int, topic_id: int, msg_id: int, return_code: int = RC_ACCEPTED) -> bytes:
    # Length(1) + MsgType(1) + Flags(1) + TopicId(2) + MsgId(2) + ReturnCode(1) = 8 bytes
    flags = (qos & 0x03) << 5
    return struct.pack("!BBBHhB", 8, MSG_SUBACK, flags, topic_id, msg_id, return_code)


def build_pingresp() -> bytes:
    return struct.pack("BB", 2, MSG_PINGRESP)


def build_disconnect(duration: int = 0) -> bytes:
    if duration:
        return struct.pack("!BBH", 4, MSG_DISCONNECT, duration)
    return struct.pack("BB", 2, MSG_DISCONNECT)


# ──────────────────────────────────────────────
# Packet parsers
# ──────────────────────────────────────────────

def parse_flags(flags_byte: int) -> dict:
    return {
        "dup":       bool(flags_byte & 0x80),
        "qos":       (flags_byte >> 5) & 0x03,
        "retain":    bool(flags_byte & 0x10),
        "will":      bool(flags_byte & 0x08),
        "clean_session": bool(flags_byte & 0x04),
        "topic_id_type": flags_byte & 0x03,
    }


def parse_connect(data: bytes) -> dict:
    """Parse CONNECT packet. data starts at byte 0 (length byte)."""
    # Byte 0: length, Byte 1: msg_type, Byte 2: flags, Byte 3: protocol_id,
    # Byte 4: duration_hi, Byte 5: duration_lo, Byte 6+: client_id
    flags = parse_flags(data[2])
    protocol_id = data[3]
    duration = struct.unpack("!H", data[4:6])[0]
    client_id = data[6:].decode("utf-8", errors="replace")
    return {"flags": flags, "protocol_id": protocol_id, "duration": duration, "client_id": client_id}


def parse_register(data: bytes) -> dict:
    """Parse REGISTER packet."""
    topic_id = struct.unpack("!H", data[2:4])[0]
    msg_id   = struct.unpack("!H", data[4:6])[0]
    topic_name = data[6:].decode("utf-8", errors="replace")
    return {"topic_id": topic_id, "msg_id": msg_id, "topic_name": topic_name}


def parse_publish(data: bytes) -> dict:
    """Parse PUBLISH packet."""
    flags    = parse_flags(data[2])
    topic_id = struct.unpack("!H", data[3:5])[0]
    msg_id   = struct.unpack("!H", data[5:7])[0]
    payload  = data[7:]
    return {"flags": flags, "topic_id": topic_id, "msg_id": msg_id, "payload": payload}


def parse_subscribe(data: bytes) -> dict:
    """Parse SUBSCRIBE packet."""
    flags  = parse_flags(data[2])
    msg_id = struct.unpack("!H", data[3:5])[0]
    # topic_id_type 0x00 = topic name, 0x01 = predefined id, 0x02 = short name
    topic_id_type = flags["topic_id_type"]
    if topic_id_type == 0x01:
        topic = struct.unpack("!H", data[5:7])[0]
    else:
        topic = data[5:].decode("utf-8", errors="replace")
    return {"flags": flags, "msg_id": msg_id, "topic": topic, "topic_id_type": topic_id_type}


# ──────────────────────────────────────────────
# Per-client session state
# ──────────────────────────────────────────────

class ClientSession:
    def __init__(self, addr: Tuple[str, int], client_id: str):
        self.addr = addr
        self.client_id = client_id
        # topic_id -> topic_name mapping (registered by the device)
        self.topic_map: Dict[int, str] = {}
        self.next_topic_id: int = 1
        self.connected_at = time.time()
        self.last_seen = time.time()

    def register_topic(self, topic_name: str) -> int:
        """Register a topic and return its ID (or existing ID if already known)."""
        for tid, tname in self.topic_map.items():
            if tname == topic_name:
                return tid
        tid = self.next_topic_id
        self.topic_map[tid] = topic_name
        self.next_topic_id += 1
        return tid

    def get_topic(self, topic_id: int) -> str | None:
        return self.topic_map.get(topic_id)

    def touch(self):
        self.last_seen = time.time()


# ──────────────────────────────────────────────
# Gateway
# ──────────────────────────────────────────────
def _on_mqtt_disconnect(client, userdata, disconnect_flags, reason_code, properties):
# def _on_mqtt_disconnect(self, client, userdata, rc):
    log.warning("Disconnected from MQTT broker (reason: \"%s\")", reason_code)
class MqttSnGateway:
    def __init__(self):
        self.sessions: Dict[Tuple[str, int], ClientSession] = {}
        self.lock = threading.Lock()

        # MQTT client (shared, thread-safe send)
        self.mqtt_client = mqtt.Client(client_id="mqttsn-gateway", clean_session=True)
        self.mqtt_client.on_connect    = self._on_mqtt_connect
        self.mqtt_client.on_disconnect = _on_mqtt_disconnect

        # UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.running = False

    # ── MQTT broker callbacks ──────────────────

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log.info("Connected to MQTT broker at %s:%d", CONFIG["MQTT_HOST"], CONFIG["MQTT_PORT"])
        else:
            log.error("MQTT broker connection failed, rc=%d", rc)
            


    # ── UDP receive loop ───────────────────────

    def start(self):
        self.sock.bind((CONFIG["MQTTSN_HOST"], CONFIG["MQTTSN_PORT"]))
        log.info("MQTT-SN gateway listening on UDP %s:%d", CONFIG["MQTTSN_HOST"], CONFIG["MQTTSN_PORT"])

        self.mqtt_client.connect(CONFIG["MQTT_HOST"], CONFIG["MQTT_PORT"], keepalive=60)
        self.mqtt_client.loop_start()

        self.running = True
        try:
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    print("udp is")
                    self._handle_packet(data, addr)
                    # threading.Thread(
                    #     target=self._handle_packet,
                    #     args=(data, addr),
                    #     daemon=True,
                    # ).start()
                except OSError as e:
                    print(f"got this error while handling MQTT-SN requests: {e}")
        finally:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.sock.close()
            log.info("Gateway stopped.")

    def stop(self):
        self.running = False
        self.sock.close()

    # ── Packet dispatch ────────────────────────

    def _handle_packet(self, data: bytes, addr: Tuple[str, int]):
        if len(data) < 2:
            log.warning("Packet too short from %s", addr)
            return

        length   = data[0]
        msg_type = data[1]

        if length != len(data):
            log.warning("Length mismatch from %s: header=%d actual=%d", addr, length, len(data))

        with self.lock:
            session = self.sessions.get(addr)
            if session:
                session.touch()

        dispatch = {
            MSG_CONNECT:     self._handle_connect,
            MSG_REGISTER:    self._handle_register,
            MSG_PUBLISH:     self._handle_publish,
            MSG_SUBSCRIBE:   self._handle_subscribe,
            MSG_PINGREQ:     self._handle_pingreq,
            MSG_DISCONNECT:  self._handle_disconnect,
        }

        handler = dispatch.get(msg_type)
        if handler:
            try:
                print("before handler")
                handler(data, addr, session)
            except Exception as exc:
                log.exception("Error handling msg_type=0x%02X from %s: %s", msg_type, addr, exc)
        else:
            log.debug("Unhandled msg_type=0x%02X from %s", msg_type, addr)

    # ── Individual message handlers ────────────

    def _handle_connect(self, data: bytes, addr, session):
        info = parse_connect(data)
        log.info("CONNECT from %s, client_id=%r, duration=%ds",
                 addr, info["client_id"], info["duration"])

        new_session = ClientSession(addr, info["client_id"])
        with self.lock:
            self.sessions[addr] = new_session

        self.sock.sendto(build_connack(RC_ACCEPTED), addr)
        log.debug("CONNACK → %s", addr)

    def _handle_register(self, data: bytes, addr, session):
        if session is None:
            log.warning("REGISTER from unknown client %s — ignoring", addr)
            return

        info = parse_register(data)
        topic_id = session.register_topic(info["topic_name"])
        log.info("REGISTER from %s: topic_name=%r → topic_id=%d",
                 addr, info["topic_name"], topic_id)

        self.sock.sendto(build_regack(topic_id, info["msg_id"], RC_ACCEPTED), addr)
        log.debug("REGACK → %s (topic_id=%d)", addr, topic_id)

    def _handle_publish(self, data: bytes, addr, session):
        if session is None:
            log.warning("PUBLISH from unknown client %s — ignoring", addr)
            return

        info = parse_publish(data)
        topic_id = info["topic_id"]
        topic_name = session.get_topic(topic_id)

        if topic_name is None:
            log.warning("PUBLISH from %s uses unregistered topic_id=%d", addr, topic_id)
            if info["flags"]["qos"] > 0:
                self.sock.sendto(
                    build_puback(topic_id, info["msg_id"], RC_REJECTED_INVALID_ID), addr
                )
            return

        qos    = info["flags"]["qos"]
        retain = info["flags"]["retain"]
        payload = info["payload"]

        log.info("PUBLISH from %s: topic=%r qos=%d retain=%s payload=%r",
                 addr, topic_name, qos, retain, payload)

        result = self.mqtt_client.publish(topic_name, payload, qos=qos, retain=retain)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            log.error("MQTT publish failed (rc=%d) for topic %r", result.rc, topic_name)
            if qos > 0:
                self.sock.sendto(
                    build_puback(topic_id, info["msg_id"], RC_REJECTED_CONGESTION), addr
                )
            return

        if qos == 1:
            self.sock.sendto(build_puback(topic_id, info["msg_id"], RC_ACCEPTED), addr)
            log.debug("PUBACK → %s", addr)
        # QoS 2 simplified: send PUBACK immediately (full QoS-2 handshake omitted)
        elif qos == 2:
            self.sock.sendto(build_puback(topic_id, info["msg_id"], RC_ACCEPTED), addr)

    def _handle_subscribe(self, data: bytes, addr, session):
        if session is None:
            log.warning("SUBSCRIBE from unknown client %s — ignoring", addr)
            return

        info = parse_subscribe(data)
        topic = info["topic"]
        qos   = info["flags"]["qos"]

        # If subscribing by name, register the topic locally
        if info["topic_id_type"] == 0x00 and isinstance(topic, str):
            topic_id = session.register_topic(topic)
            log.info("SUBSCRIBE from %s: topic=%r qos=%d → topic_id=%d",
                     addr, topic, qos, topic_id)
        else:
            topic_id = topic if isinstance(topic, int) else 0

        self.sock.sendto(
            build_suback(qos, topic_id, info["msg_id"], RC_ACCEPTED), addr
        )
        log.debug("SUBACK → %s (topic_id=%d)", addr, topic_id)

    def _handle_pingreq(self, data: bytes, addr, session):
        log.debug("PINGREQ from %s", addr)
        self.sock.sendto(build_pingresp(), addr)

    def _handle_disconnect(self, data: bytes, addr, session):
        log.info("DISCONNECT from %s", addr)
        with self.lock:
            self.sessions.pop(addr, None)
        self.sock.sendto(build_disconnect(), addr)


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import signal

    gw = MqttSnGateway()

    def _shutdown(sig, frame):
        log.info("Shutting down…")
        gw.stop()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    gw.start()