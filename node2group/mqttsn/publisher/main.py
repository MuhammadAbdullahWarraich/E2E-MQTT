import socket
import struct
import time
import httpx
import os
print(os.getcwd())
from ..encryption import encrypt_data
from ..globals import KEY_AUTHORITY_URL, MQTTSN_GATEWAY_HOST, MQTTSN_GATEWAY_PORT

MSG_CONNECT    = 0x04
MSG_CONNACK    = 0x05
MSG_REGISTER   = 0x0A
MSG_REGACK     = 0x0B
MSG_PUBLISH    = 0x0C
MSG_PUBACK     = 0x0D
MSG_DISCONNECT = 0x18

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


def build_register(topic_name: str, msg_id: int) -> bytes:
    topic_bytes = topic_name.encode()
    length = 6 + len(topic_bytes)
    return struct.pack("!BBHH", length, MSG_REGISTER, 0x0000, msg_id) + topic_bytes


def build_publish(topic_id: int, msg_id: int, payload: bytes, qos: int = 0) -> bytes:
    qos_flags = {0: 0x00, 1: 0x20, 2: 0x40}.get(qos, 0x00)
    length = 7 + len(payload)
    header = struct.pack("!BBBHH", length, MSG_PUBLISH, qos_flags, topic_id, msg_id)
    return header + payload


def build_disconnect() -> bytes:
    return bytes([2, MSG_DISCONNECT])


def parse_connack(data: bytes) -> bool:
    if len(data) >= 3 and data[1] == MSG_CONNACK:
        return data[2] == RETURN_CODE_OK
    return False


def parse_regack(data: bytes):
    if len(data) >= 7 and data[1] == MSG_REGACK:
        topic_id, msg_id, return_code = struct.unpack("!HHB", data[2:7])
        return topic_id, msg_id, return_code == RETURN_CODE_OK
    return 0, 0, False


def parse_puback(data: bytes) -> bool:
    if len(data) >= 7 and data[1] == MSG_PUBACK:
        return data[6] == RETURN_CODE_OK
    return False


def get_public_key(group_id: int) -> str:
    for attempt in range(3):
        try:
            res = httpx.post(f"{KEY_AUTHORITY_URL}/group-pub-key/", json=group_id, timeout=5.0)
            if res.status_code == 200:
                return res.read()
        except httpx.RequestError:
            pass
        time.sleep(0.5)
    raise Exception(f"Could not fetch public key for group {group_id}")


def mqttsn_publish_session(sock, gateway, client_id, topic_name, payload, qos=0):
    sock.settimeout(5.0)

    sock.sendto(build_connect(client_id), gateway)
    data, _ = sock.recvfrom(256)
    if not parse_connack(data):
        raise Exception("CONNACK failed")
    print(f"[CONNECT] Connected as '{client_id}'")

    msg_id = 1
    sock.sendto(build_register(topic_name, msg_id), gateway)
    print("here")
    data, _ = sock.recvfrom(256)
    print("here")
    topic_id, _, ok = parse_regack(data)
    print("here")
    if not ok:
        raise Exception(f"REGACK failed for topic '{topic_name}'")
    print(f"[REGISTER] Topic '{topic_name}' registered as topic_id={topic_id}")

    msg_id = 2
    sock.sendto(build_publish(topic_id, msg_id, payload, qos), gateway)
    if qos > 0:
        data, _ = sock.recvfrom(256)
        if not parse_puback(data):
            raise Exception("PUBACK failed")
    print(f"[PUBLISH] Message sent (QoS={qos})")

    sock.sendto(build_disconnect(), gateway)
    print("[DISCONNECT] Done")


def main():
    gateway = (MQTTSN_GATEWAY_HOST, MQTTSN_GATEWAY_PORT)
    client_id = "mqttsn-publisher-01"

    while True:
        try:
            group_id = int(input("Please enter recipient group: "))
            topic    = input("Please enter topic: ")
            msg      = input("Please enter message: ")
            qos      = int(input("Please enter quality of service (QoS 0/1/2): "))

            public_key    = get_public_key(group_id)
            msg = msg.encode('utf8')
            encrypted_msg = encrypt_data(msg, public_key)
            print(f"[INFO] encrypted message as bytes: {encrypted_msg}")
            
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                mqttsn_publish_session(sock, gateway, client_id, topic, encrypted_msg, qos)

        except KeyboardInterrupt:
            print("\nPublisher stopped.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")


if __name__ == "__main__":
    main()
