GROUP_KEY_PAIRS = [
    ("some_private_key_1", "public_key_of_some_private_key_1"),
    ("some_private_key_2", "public_key_of_some_private_key_2")
]
ID_TO_GROUP = {
        "a1:b2:c3:d4:e5": 0,
        "a1:b2:c3:d4:e4": 1,
        "a1:b2:c3:d4:e3": 1,
        "a1:b2:c3:d4:e2": 0
}
from fastapi import FastAPI, Body
from typing import Annotated

app = FastAPI()

@app.post("/group-pub-key/")
def get_group_public_key(group_id: Annotated[int, Body()]):
    if group_id >= 0 and group_id < len(GROUP_KEY_PAIRS):
        _, pub = GROUP_KEY_PAIRS[group_id]
        return pub

@app.post("/group-priv-key/")
def get_group_private_key(id: Annotated[str, Body()]):
    if (group_id := ID_TO_GROUP.get(id)) != None:
        priv, _ = GROUP_KEY_PAIRS[group_id]
        return priv
    
