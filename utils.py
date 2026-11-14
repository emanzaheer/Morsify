import json
import uuid
import time

PACKET_SIZE = 600

def make_message_id():
    return str(uuid.uuid4())

def chunk_bytes(data: bytes, chunk_size: int = PACKET_SIZE):
    return [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]

def packet_msg(message_id, packet_no, total, sender, room, payload_b64):
    return json.dumps({
        "type": "packet",
        "message_id": message_id,
        "packet_no": packet_no,
        "total_packets": total,
        "sender": sender,
        "room": room,
        "timestamp": time.time(),
        "payload": payload_b64
    })

def build_control(t, **kwargs):
    obj = {"type": t}
    obj.update(kwargs)
    return json.dumps(obj)

def heartbeat():
    return json.dumps({"type": "heartbeat", "ts": time.time()})
