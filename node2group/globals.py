from dotenv import load_dotenv
import os

load_dotenv()
KEY_AUTHORITY_URL = os.getenv("KEY_AUTHORITY_URL")
SECURE_TOPIC = os.getenv("SECURE_TOPIC")