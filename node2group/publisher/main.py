import httpx
import time
import paho.mqtt.client as mqtt
from ..encryption import encrypt_data
from ..globals import KEY_AUTHORITY_URL

def on_publish(client, userdata, mid, reason_code, properties):
    # reason_code and properties will only be present in MQTTv5. It's always unset in MQTTv3
    try:
        userdata.remove(mid)
    except KeyError:
        print("on_publish() is called with a mid not present in unacked_publish")
        print("This is due to an unavoidable race-condition:")
        print("* publish() return the mid of the message sent.")
        print("* mid from publish() is added to unacked_publish by the main thread")
        print("* on_publish() is called by the loop_start thread")
        print("While unlikely (because on_publish() will be called after a network round-trip),")
        print(" this is a race-condition that COULD happen")
        print("")
        print("The best solution to avoid race-condition is using the msg_info from publish()")
        print("We could also try using a list of acknowledged mid rather than removing from pending list,")
        print("but remember that mid could be re-used !")


def get_public_key(group_id):
    res = httpx.post(f"{KEY_AUTHORITY_URL}/group-pub-key", json=group_id)
    if res.status_code == httpx.codes.OK:
        return res.json()
    else:
        raise Exception("invalid group id provided!")


def main(unacked_publish, mqttc):
    while True:
        group_id = int(input("Please enter recepient group: "))
        topic = input("Please enter topic: ")
        msg = input("Please enter message: ")
        qos = int(input("please enter quality of service(QoS): "))

        public_key = get_public_key(group_id)
        msg = encrypt_data(msg, public_key)

        # Our application produce some messages
        msg_info = mqttc.publish(topic, msg, qos=qos)
        unacked_publish.add(msg_info.mid)

        # Wait for all message to be published
        while len(unacked_publish):
            time.sleep(0.1)

        # Due to race-condition described above, the following way to wait for all publish is safer
        msg_info.wait_for_publish()

if __name__ == "__main__":
    unacked_publish = set()
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqttc.on_publish = on_publish
    
    mqttc.user_data_set(unacked_publish)
    mqttc.tls_set()
    mqttc.connect(host="127.0.0.1", port=8883)
    mqttc.loop_start()
    try:
        main(unacked_publish, mqttc)
    except KeyboardInterrupt:
        pass
        # ctrl+c is an expected user action when they don't want to send anymore,
        # so we catch the exception
    finally:
        mqttc.disconnect()
        mqttc.loop_stop()
