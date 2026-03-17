import json

def mock_encryption_algo(msg, key):
    assert 0 == key.find("public_key_of_")
    return json.dumps({
        "key": key[len("public_key_of_"):],
        "msg": msg 
    })

def mock_decryption_algo(msg, key):
    assert -1 == key.find("public_key_of_")
    msg = json.loads(msg)
    if msg["key"] == key:
        return msg["msg"]
    else:
        raise Exception("decryption failed!")