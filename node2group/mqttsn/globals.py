from dotenv import load_dotenv
import os

load_dotenv()
KEY_AUTHORITY_URL = os.getenv("KEY_AUTHORITY_URL")
SECURE_TOPIC = "secret"

MQTTSN_GATEWAY_HOST = os.getenv("MQTTSN_GATEWAY_HOST", "127.0.0.1")
MQTTSN_GATEWAY_PORT = int(os.getenv("MQTTSN_GATEWAY_PORT", "10000"))
