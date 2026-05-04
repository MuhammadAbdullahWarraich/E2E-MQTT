import socket
import struct
import httpx
import signal
import sys
from ..encryption import decrypt_data
from ..globals import KEY_AUTHORITY_URL, SECURE_TOPIC, MQTTSN_GATEWAY_HOST, MQTTSN_GATEWAY_PORT

MAC_ADDRESS = "a1:b2:c3:d4:e5"

MSG_CONNECT    = 0x04
MSG_CONNACK    = 0x05
MSG_SUBSCRIBE  = 0x12
MSG_SUBACK     = 0x13
MSG_PUBLISH    = 0x0C
MSG_PUBACK     = 0x0D
MSG_DISCONNECT = 0x18
MSG_PINGREQ    = 0x16
MSG_PINGRESP   = 0x17

RETURN_CODE_OK = 0x00
PROTOCOL_ID    = 0x01
KEEP_ALIVE     = 60


def build_connect(client_id: str) -> bytes:
    client_id_bytes = client_id.encode()
    flags = 0x04
    duration_hi = (KEEP_ALIVE >> 8) & 0xFF
    duration_lo = KEEP_ALIVE & 0xFF
    header = bytes([6 + len(client_id_bytes), MSG_CONNECT, flags, PROTOCOL_ID, duration_hi, duration_lo])
    return header + client_id_bytes


def build_subscribe(topic_name: str, msg_id: int, qos: int = 0) -> bytes:
    topic_bytes = topic_name.encode()
    qos_flags = {0: 0x00, 1: 0x20, 2: 0x40}.get(qos, 0x00)
    length = 5 + len(topic_bytes)
    header = struct.pack("!BBBH", length, MSG_SUBSCRIBE, qos_flags, msg_id)
    return header + topic_bytes


def build_puback(topic_id: int, msg_id: int) -> bytes:
    return struct.pack("!BBHHB", 7, MSG_PUBACK, topic_id, msg_id, RETURN_CODE_OK)


def build_disconnect() -> bytes:
    return bytes([2, MSG_DISCONNECT])


def build_pingreq() -> bytes:
    return bytes([2, MSG_PINGREQ])


def parse_connack(data: bytes) -> bool:
    if len(data) >= 3 and data[1] == MSG_CONNACK:
        return data[2] == RETURN_CODE_OK
    return False


def parse_suback(data: bytes):
    if len(data) >= 8 and data[1] == MSG_SUBACK:
        topic_id = struct.unpack("!H", data[3:5])[0]
        return_code = data[7]
        return topic_id, return_code == RETURN_CODE_OK
    return 0, False


def parse_publish(data: bytes):
    if len(data) >= 7 and data[1] == MSG_PUBLISH:
        flags    = data[2]
        qos      = (flags >> 5) & 0x03
        topic_id, msg_id = struct.unpack("!HH", data[3:7])
        payload  = data[7:]
        return qos, topic_id, msg_id, payload
    return 0, 0, 0, b""


def get_private_key() -> str:
    res = httpx.post(f"{KEY_AUTHORITY_URL}/group-priv-key/", json=MAC_ADDRESS, timeout=5.0)
    if res.status_code == 200:
        return res.json()
    raise Exception("Key authority rejected this device MAC address")


def main():
    gateway   = (MQTTSN_GATEWAY_HOST, MQTTSN_GATEWAY_PORT)
    client_id = f"mqttsn-subscriber-{MAC_ADDRESS.replace(':', '')}"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print("socket connected")
    sock.settimeout(KEEP_ALIVE)

    def shutdown(sig=None, frame=None):
        print("\n[DISCONNECT] Disconnecting...")
        try:
            sock.sendto(build_disconnect(), gateway)
        except Exception:
            pass
        sock.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)

    try:
        sock.sendto(build_connect(client_id), gateway)
        data, _ = sock.recvfrom(256)
        if not parse_connack(data):
            raise Exception("CONNACK failed")
        print(f"[CONNECT] Connected as '{client_id}'")

        msg_id = 1
        sock.sendto(build_subscribe(SECURE_TOPIC, msg_id, qos=1), gateway)
        data, _ = sock.recvfrom(256)
        topic_id, ok = parse_suback(data)
        if not ok:
            raise Exception(f"SUBACK failed for topic '{SECURE_TOPIC}'")
        print(f"[SUBSCRIBE] Subscribed to '{SECURE_TOPIC}' (topic_id={topic_id})")
        print("[WAITING] Listening for incoming messages...\n")

        while True:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                sock.sendto(build_pingreq(), gateway)
                print("[PING] Sent PINGREQ")
                continue

            if data[1] == MSG_PUBLISH:
                qos, recv_topic_id, recv_msg_id, payload = parse_publish(data)
                if qos == 1:
                    sock.sendto(build_puback(recv_topic_id, recv_msg_id), gateway)
                try:
                    priv_key  = get_private_key()
                    decrypted = decrypt_data(payload.decode(), priv_key)
                    print(f"[MESSAGE] topic_id={recv_topic_id} | {decrypted}")
                except Exception as e:
                    print(f"[ERROR] Decryption failed: {e}")

            elif data[1] == MSG_PINGRESP:
                print("[PING] PINGRESP received")

            elif data[1] == MSG_DISCONNECT:
                print("[DISCONNECT] Gateway disconnected")
                break

    except Exception as e:
        print(f"[FATAL] {e}")
    finally:
        shutdown()


if __name__ == "__main__":
    main()
