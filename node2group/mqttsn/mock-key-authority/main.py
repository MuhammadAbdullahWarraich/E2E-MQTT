import rsa
import pickle
KEYSIZE = 512
GROUP_KEY_PAIRS = [rsa.newkeys(KEYSIZE), rsa.newkeys(KEYSIZE)]
ID_TO_GROUP = {
        "a1:b2:c3:d4:e5": 0,
        "a1:b2:c3:d4:e4": 1,
        "a1:b2:c3:d4:e3": 1,
        "a1:b2:c3:d4:e2": 0
}
from fastapi import FastAPI, Body, Response
from typing import Annotated

app = FastAPI()

@app.post("/group-pub-key/")
def get_group_public_key(group_id: Annotated[int, Body()]):
    if group_id >= 0 and group_id < len(GROUP_KEY_PAIRS):
        _, pub = GROUP_KEY_PAIRS[group_id]
        return Response(content=pickle.dumps(pub), media_type="application/octet-stream")

@app.post("/group-priv-key/")
def get_group_private_key(id: Annotated[str, Body()]):
    if (group_id := ID_TO_GROUP.get(id)) != None:
        priv, _ = GROUP_KEY_PAIRS[group_id]
        return Response(content=pickle.dumps(priv), media_type="application/octet-stream")
    
@app.post("/register-group/")
def create_group(members: list[str]):
    global GROUP_KEY_PAIRS
    global ID_TO_GROUP
    id = len(GROUP_KEY_PAIRS)
    GROUP_KEY_PAIRS.append(rsa.newkeys(KEYSIZE))
    for m in members:
        ID_TO_GROUP[m] = id
    return {"id": id}
