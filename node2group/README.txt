# MQTT-SN Project — Run Instructions

## STEP 0 — Install requirements (one time only)
pip install -r requirements.txt

## STEP 1 — Start Docker containers (Terminal 1)
docker run -d --name emqx -p 1883:1883 -p 18083:18083 emqx/emqx-enterprise:latest
docker ps   <-- should show emqx

## STEP 2 — Start Key Authority (Terminal 1)
cd mqttsn/mock-key-authority/
fastapi dev main.py

## STEP 3 — Start Subscriber (Terminal 2, stay in THIS folder)
python -m mqttsn.subscriber.main

## STEP 4 — Start Gateway (Terminal 3, stay in THIS folder)
python -m mqttsn.gateway.main

## STEP 5 — Publish a message (Terminal 4, stay in THIS folder)
python -m mqttsn.publisher.main


When prompted:
  group   -> 0
  topic   -> /secret
  message -> hello world
  QoS     -> 2


## IMPORTANT
All commands must be run from THIS folder
NOT from inside the mqttsn subfolder
