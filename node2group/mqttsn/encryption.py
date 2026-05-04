import rsa
import pickle
from rsa.pkcs1 import common, transform, _pad_for_signing, core
    
def encrypt_data(msg, key) -> bytes:
    priv_key = pickle.loads(key)
    keylength = common.byte_size(priv_key.n)
    padded = _pad_for_signing(msg, keylength)
    print("got till here")

    payload = transform.bytes2int(padded)
    encrypted = priv_key.blinded_encrypt(payload)
    block = transform.int2bytes(encrypted, keylength)
    return block



def encrypt_data_old(msg, key):
    msg = msg.encode('utf8')
    key = pickle.loads(key)
    return rsa.encrypt(msg, key)

def decrypt_data(msg, key):
    pub_key = pickle.loads(key)

    keylength = common.byte_size(pub_key.n)
    encrypted = transform.bytes2int(msg)
    decrypted = core.decrypt_int(encrypted, pub_key.e, pub_key.n)
    msg = transform.int2bytes(decrypted, keylength)
    if msg[0:2] != b'\x00\x01':
        raise ValueError("Invalid padding")
    sep = msg.index(b'\x00', 2)
    return msg[sep + 1:]

def decrypt_data_old(msg, key):
    key = pickle.loads(key)
    msg = rsa.decrypt(msg, key)
    return msg.decode('utf8')