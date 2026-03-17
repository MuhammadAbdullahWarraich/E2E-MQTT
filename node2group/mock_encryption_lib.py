import json

def mock_encryption_algo(msg, key):
    if -1 == key.find("public_key_of"):
        return json.dumps({
            "key": key,
            "msg": msg 
        })
    else:
        return json.dumps({
            "key": key[len("public_key_of"):],
            "msg": msg 
        })

def mock_decryption_algo(msg, key):
    msg = json.loads(msg)
    if 0 == key.find("public_key_of"):
        key = key[len("public_key_of"):]
    if msg["key"] == key:
        return msg["key"]
    else:
        raise Exception("decryption failed!")