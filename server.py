import socket
import threading
import json
import base64
import time
import signal
import sys
from cryptography.fernet import Fernet
from utils import build_control

HOST = "0.0.0.0"
PORT = 9010

shutdown_flag = threading.Event()

clients_lock = threading.Lock()
conn_to_info = {}
name_to_conn = {}

rooms = {}  
KEY_ROTATION_SECONDS = 300 

def signal_handler(sig, frame):
    print("\n[Server] Shutting down gracefully...")
    shutdown_flag.set()
    sys.exit(0)

def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except:
        return "127.0.0.1"


def ensure_main_room():
    """Create main room once."""
    if "main" not in rooms:
        key = Fernet.generate_key()
        rooms["main"] = {
            "clients": set(),
            "key": key,
            "key_obj": Fernet(key),
            "members": set()
        }
        t = threading.Thread(target=main_room_key_rotator, daemon=True)
        rooms["main"]["rot_thread"] = t
        t.start()


def main_room_key_rotator():
    """Rotate the main room key automatically."""
    while not shutdown_flag.is_set():
        time.sleep(KEY_ROTATION_SECONDS)
        if shutdown_flag.is_set():
            break

        try:
            key = Fernet.generate_key()
            rooms["main"]["key"] = key
            rooms["main"]["key_obj"] = Fernet(key)

            announce = build_control("key_rotated", room="main",
                                     key=base64.b64encode(key).decode())

            with clients_lock:
                for c in list(rooms["main"]["clients"]):
                    try:
                        c.sendall(announce.encode() + b"\n")
                    except:
                        pass

            print("[Server] Rotated key for main room")

        except Exception as e:
            print("main rotator error", e)


def add_user_to_main(username):
    """Put a connected user into the main broadcast room."""
    with clients_lock:
        if username in name_to_conn:
            conn = name_to_conn[username]
            rooms["main"]["clients"].add(conn)
            rooms["main"]["members"].add(username)
            conn_to_info[conn]["room"] = "main"

            key_b64 = base64.b64encode(rooms["main"]["key"]).decode()
            try:
                conn.sendall(build_control("key", room="main", key=key_b64).encode() + b"\n")
            except:
                pass

            return True
    return False


def handle_client(conn, addr):
    print(f"[+] Connection from {addr[0]}:{addr[1]}")
    buffer = b""

    try:
        while not shutdown_flag.is_set():
            try:
                conn.settimeout(1.0)
                data = conn.recv(8192)
                if not data:
                    break
                buffer += data

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)

                    try:
                        msg = json.loads(line.decode())
                    except:
                        continue

                    mtype = msg.get("type")

                    if mtype == "join":
                        username = msg.get("username")
                        with clients_lock:
                            conn_to_info[conn] = {"username": username, "room": "main"}
                            name_to_conn[username] = conn
                            ensure_main_room()
                            rooms["main"]["clients"].add(conn)
                            rooms["main"]["members"].add(username)

                        key_b64 = base64.b64encode(rooms["main"]["key"]).decode()
                        conn.sendall(build_control("key", room="main", key=key_b64).encode() + b"\n")

                        broadcast_to_main(build_control("join", user=username, room="main"), exclude=conn)
                        print(f"[Chat] {username} joined main")

                    elif mtype == "list_users":
                        with clients_lock:
                            users = list(name_to_conn.keys())
                        resp = json.dumps({"type": "user_list", "users": users})
                        conn.sendall(resp.encode() + b"\n")

                    elif mtype == "packet":
                        room = msg.get("room")
                        sender = msg.get("sender")

                        if room == "main":
                            broadcast_to_main(line.decode(), exclude=conn)
                            print(f"[Main] {sender}: {msg.get('payload', '')[:50]}...")
                        else:
                            with clients_lock:
                                if room in name_to_conn:
                                    target = name_to_conn.get(room)
                                    try:
                                        target.sendall(line + b"\n")
                                        print(f"[Private] {sender} -> {room}")
                                    except:
                                        pass

                    else:
                        pass

            except socket.timeout:
                continue
            except Exception:
                break

    finally:
        with clients_lock:
            info = conn_to_info.get(conn, {})
            username = info.get("username")

            if username in name_to_conn:
                del name_to_conn[username]

            if conn in conn_to_info:
                del conn_to_info[conn]

            if "main" in rooms:
                rooms["main"]["clients"].discard(conn)
                rooms["main"]["members"].discard(username)

        if username:
            broadcast_to_main(json.dumps({"type": "leave", "user": username, "room": "main"}))
            print(f"[Chat] {username} left main")

        conn.close()
        print(f"[-] Closed connection {addr[0]}")


def broadcast_to_main(msg_str, exclude=None):
    if "main" not in rooms:
        return

    with clients_lock:
        for c in list(rooms["main"]["clients"]):
            if c == exclude:
                continue

            try:
                if isinstance(msg_str, str):
                    c.sendall(msg_str.encode() + b"\n")
                else:
                    c.sendall(msg_str + b"\n")
            except:
                pass


def accept_loop(server_sock):
    server_sock.settimeout(1.0)
    while not shutdown_flag.is_set():
        try:
            conn, addr = server_sock.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
        except socket.timeout:
            continue
        except Exception as e:
            if not shutdown_flag.is_set():
                print("Accept error:", e)
            break

def start_server():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(100)

        ensure_main_room()

        local_ip = get_local_ip()

        print(f"╔{'═' * 50}╗")
        print(f"║{'MORSIFY Server':^50}║")
        print(f"╠{'═' * 50}╣")
        print(f"║ {'Status:':<15} {'🟢 RUNNING':<31} ║")
        print(f"║ {'Port:':<15} {'9010':<32} ║")
        print(f"║ {'Local IP:':<15} {local_ip:<32} ║")
        print(f"╠{'═' * 50}╣")
        print(f"║ {'LAN Connection:':<48} ║")
        print(f"║ {'Clients connect to: ' + local_ip + ':9010':<48} ║")
        print(f"║ {'Same PC: localhost:9010':<48} ║")
        print(f"╚{'═' * 50}╝")
        print("\nPress Ctrl+C to stop the server")

        accept_loop(s)
        s.close()

    except Exception as e:
        print("[ERROR] Failed to start server:", e)


if __name__ == "__main__":
    start_server()
