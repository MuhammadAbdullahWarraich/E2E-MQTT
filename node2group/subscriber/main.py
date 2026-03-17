import paho.mqtt.client as mqtt
from ..encryption import decrypt_data
import httpx
from ..globals import KEY_AUTHORITY_URL, SECURE_TOPIC

MAC_ADDRESS = "a1:b2:c3:d4:e5"

def on_subscribe(client, userdata, mid, reason_code_list, properties):
    # Since we subscribed only for a single channel, reason_code_list contains
    # a single entry
    if reason_code_list[0].is_failure:
        print(f"Broker rejected you subscription: {reason_code_list[0]}")
    else:
        print(f"Broker granted the following QoS: {reason_code_list[0].value}")

def on_unsubscribe(client, userdata, mid, reason_code_list, properties):
    # Be careful, the reason_code_list is only present in MQTTv5.
    # In MQTTv3 it will always be empty
    if len(reason_code_list) == 0 or not reason_code_list[0].is_failure:
        print("unsubscribe succeeded (if SUBACK is received in MQTTv3 it success)")
    else:
        print(f"Broker replied with failure: {reason_code_list[0]}")
    client.disconnect()

def get_private_key():
    res = httpx.post(f"{KEY_AUTHORITY_URL}/group-priv-key/", json=MAC_ADDRESS)
    if res.status_code == httpx.codes.OK:
        return res.json()
    else:
        raise Exception("invalid unique id(MAC_ADDRESS) provided!")

def on_message(client, userdata, message):
    # userdata is the structure we choose to provide, here it's a list()
    priv_key = get_private_key()
    message = decrypt_data(message.payload, priv_key)
    print("we got message: ", message)

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"Failed to connect: {reason_code}. loop_forever() will retry connection")
    else:
        # we should always subscribe from on_connect callback to be sure
        # our subscribed is persisted across reconnections.
        client.subscribe(SECURE_TOPIC)


def main():
    try:
        mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqttc.on_connect = on_connect
        mqttc.on_message = on_message
        mqttc.on_subscribe = on_subscribe
        mqttc.on_unsubscribe = on_unsubscribe
        mqttc.user_data_set([])
        mqttc.connect(host="127.0.0.1")
        mqttc.loop_forever()
    except KeyboardInterrupt:
        mqttc.disconnect()

 
if __name__ == "__main__":
    main()