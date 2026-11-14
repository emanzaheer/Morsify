import socket
import threading
import json
import base64
from tkinter import  messagebox
import customtkinter as ctk
from utils import make_message_id, chunk_bytes, packet_msg, build_control
from morse_plus import encode_to_morse_plus, decode_from_morse_plus
from cryptography.fernet import Fernet

SERVER_HOST = "localhost"
SERVER_PORT = 9010

COLOR_SIDEBAR      = "#1A2A2A"
COLOR_CHAT_BG      = "#0F1C1C"
COLOR_BTN          = "#00BFA5"
COLOR_BTN_HOVER    = "#008C7E"
COLOR_ENTRY        = "#1A2A2A"
COLOR_TEXT         = "#FFF5E6"
COLOR_BUBBLE_ME    = "#00BFA5"
COLOR_BUBBLE_THEM  = "#008C7E"
COLOR_ACCENT       = "#FFF5E6"
COLOR_CARD_BG      = "#1A2A2A"
COLOR_NOTIFICATION = "#00BFA5"
COLOR_MORSE        = "#FFF5E6"
COLOR_BORDER       = "#004D40"

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")


class ClientApp:
    def __init__(self, master):
        self.master = master
        master.title("MORSIFY")
        master.geometry("1200x700")
        master.configure(bg=COLOR_CHAT_BG)

        self.sock = None
        self.username = ""
        self.room = "main"
        self.fernet = None
        self.server_host = SERVER_HOST

        self.packets_sent = 0
        self.packets_recv = 0
        self.packets_lost = 0
        self.reassembly = {}
        self.lock = threading.Lock()

        self.main_frame = None
        self.user_list_frame = None
        self.chat_header = None
        self.message_canvas = None
        self.entry = None
        self.send_btn = None
        self.stat_label = None
        self.input_frame = None
        self.morse_preview_label = None
        self.login_frame = None

        self.current_chat = None
        self.chat_history = {}
        self.unread_messages = {}
        self.chat_buttons = {}

        self.online_users = []

        self.build_login_ui()

    def build_login_ui(self):
        self.login_frame = ctk.CTkFrame(self.master, fg_color=COLOR_CHAT_BG, corner_radius=0)
        self.login_frame.pack(fill="both", expand=True)

        login_card = ctk.CTkFrame(self.login_frame, width=400, height=450,
                                 fg_color=COLOR_CARD_BG, corner_radius=20)
        login_card.pack(expand=True, pady=80)
        login_card.pack_propagate(False)

        title = ctk.CTkLabel(login_card, text="MORSIFY",
                             font=ctk.CTkFont(size=32, weight="bold"),
                             text_color=COLOR_ACCENT)
        title.pack(pady=(50, 10))

        subtitle = ctk.CTkLabel(login_card,
                                text="LAN Secure Messenger",
                                font=ctk.CTkFont(size=14),
                                text_color=COLOR_TEXT)
        subtitle.pack(pady=(0, 40))

        input_frame = ctk.CTkFrame(login_card, fg_color="transparent")
        input_frame.pack(pady=20, padx=40, fill="x")

        ctk.CTkLabel(input_frame, text="Server Address",
                     text_color=COLOR_TEXT, font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")

        self.server_entry = ctk.CTkEntry(input_frame,
                                         placeholder_text="localhost or 192.168.x.x",
                                         height=45,
                                         fg_color=COLOR_ENTRY,
                                         border_color=COLOR_BTN,
                                         text_color=COLOR_TEXT,
                                         font=ctk.CTkFont(size=14))
        self.server_entry.pack(fill="x", pady=(5, 20))
        self.server_entry.insert(0, "localhost")

        ctk.CTkLabel(input_frame, text="Username",
                     text_color=COLOR_TEXT, font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")

        self.username_entry = ctk.CTkEntry(input_frame,
                                           placeholder_text="Enter your username",
                                           height=45,
                                           fg_color=COLOR_ENTRY,
                                           border_color=COLOR_BTN,
                                           text_color=COLOR_TEXT,
                                           font=ctk.CTkFont(size=14))
        self.username_entry.pack(fill="x", pady=(5, 20))
        self.username_entry.focus_set()

        help_text = ctk.CTkLabel(login_card,
                                 text="• Same Computer: localhost\n"
                                      "• LAN: server's IP (e.g., 192.168.1.100)",
                                 text_color=COLOR_ACCENT,
                                 font=ctk.CTkFont(size=11),
                                 justify="left")
        help_text.pack(pady=(0, 20))

        self.connect_btn_login = ctk.CTkButton(login_card,
                                               text="Connect to Chat",
                                               height=45,
                                               font=ctk.CTkFont(size=14, weight="bold"),
                                               command=self.connect_and_show_home,
                                               fg_color=COLOR_BTN,
                                               hover_color=COLOR_BTN_HOVER)
        self.connect_btn_login.pack(pady=20, padx=40, fill="x")

        self.server_entry.bind("<Return>", lambda e: self.username_entry.focus())
        self.username_entry.bind("<Return>", lambda e: self.connect_and_show_home())

    def connect_and_show_home(self):
        server_host = self.server_entry.get().strip()
        username = self.username_entry.get().strip()

        if not server_host:
            messagebox.showwarning("Server Address", "Please enter server address.")
            return

        if not username:
            messagebox.showwarning("Username", "Please enter a username.")
            return

        self.server_host = server_host
        self.username = username

        self.connect_btn_login.configure(state="disabled", text="Connecting...")
        self.master.update()

        if not self.connect_socket_only():
            self.connect_btn_login.configure(state="normal", text="Connect to Chat")
            return

        try:
            self.login_frame.pack_forget()
            self.login_frame.destroy()
            self.login_frame = None
        except Exception as e:
            print(f"Login UI cleanup: {e}")

        self.build_main_ui()

        try:
            join_msg = build_control("join", username=self.username, room=self.room)
            self.sock.sendall(join_msg.encode() + b"\n")
            self.request_user_list()
            if "main" not in self.chat_history:
                self.chat_history["main"] = []
        except Exception as e:
            print(f"Initial join failed: {e}")

        self.refresh_lists()

    def connect_socket_only(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect((self.server_host, SERVER_PORT))
            self.sock.settimeout(None)
            self.recv_thread = threading.Thread(target=self.recv_loop, daemon=True)
            self.recv_thread.start()
            return True
        except Exception as e:
            messagebox.showerror("Connection Failed",
                                 f"Could not connect to {self.server_host}:\n{str(e)}\n\n"
                                 f"Make sure:\n"
                                 f"• Server is running on {self.server_host}\n"
                                 f"• Port {SERVER_PORT} is open\n"
                                 f"• Computers are on same network")
            self.sock = None
            return False

    def build_main_ui(self):
        if self.main_frame:
            self.main_frame.destroy()

        self.main_frame = ctk.CTkFrame(self.master, fg_color=COLOR_CHAT_BG, corner_radius=0)
        self.main_frame.pack(fill="both", expand=True)

        top = ctk.CTkFrame(self.main_frame, fg_color=COLOR_CHAT_BG, corner_radius=0)
        top.pack(fill="both", expand=True, padx=15, pady=15)

        left = ctk.CTkFrame(top, width=280, fg_color=COLOR_SIDEBAR, corner_radius=15)
        left.pack(side="left", fill="y", padx=(0, 12), pady=6)
        left.pack_propagate(False)

        user_header = ctk.CTkFrame(left, fg_color=COLOR_SIDEBAR, height=80, corner_radius=12)
        user_header.pack(fill="x", padx=12, pady=(12, 8))
        user_header.pack_propagate(False)

        ctk.CTkLabel(user_header, text=f"👤 {self.username}",
                     anchor="w", text_color=COLOR_ACCENT,
                     font=ctk.CTkFont(size=16, weight="bold")).pack(padx=15, pady=(15, 5))
        ctk.CTkLabel(user_header, text=f"Connected to: {self.server_host}",
                     anchor="w", text_color="#00FF00",
                     font=ctk.CTkFont(size=10)).pack(padx=15, pady=(0, 15))

        users_card = ctk.CTkFrame(left, fg_color=COLOR_CARD_BG, corner_radius=12)
        users_card.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(users_card, text="🟢 Online Users", anchor="w",
                     text_color=COLOR_TEXT, font=ctk.CTkFont(size=14, weight="bold")).pack(padx=12, pady=(12, 8))

        main_btn = ctk.CTkButton(
            users_card,
            text="🏠 Main Room",
            width=240,
            height=40,
            fg_color=COLOR_CARD_BG,
            hover_color=COLOR_BTN,
            text_color=COLOR_TEXT,
            anchor="w",
            command=lambda: self.select_main_chat()
        )
        main_btn.pack(padx=8, pady=(8, 12), fill="x")
        self.chat_buttons["main"] = main_btn
        if "main" not in self.chat_history:
            self.chat_history["main"] = []

        self.user_list_frame = ctk.CTkScrollableFrame(users_card, height=200,
                                                      fg_color=COLOR_CARD_BG, corner_radius=8)
        self.user_list_frame.pack(fill="x", padx=8, pady=(0, 8))

        action_frame = ctk.CTkFrame(left, fg_color=COLOR_SIDEBAR)
        action_frame.pack(fill="x", padx=12, pady=12)

        ctk.CTkButton(action_frame, text="🔄 Refresh",
                      command=self.refresh_lists,
                      fg_color=COLOR_BTN,
                      hover_color=COLOR_BTN_HOVER,
                      height=35).pack(fill="x", pady=(0, 8))

        center = ctk.CTkFrame(top, fg_color=COLOR_CHAT_BG, corner_radius=15)
        center.pack(side="left", fill="both", expand=True)

        self.chat_header = ctk.CTkFrame(center, height=70, fg_color=COLOR_CARD_BG, corner_radius=12)
        self.chat_header.pack(fill="x", padx=12, pady=(12, 8))

        self.chat_title_label = ctk.CTkLabel(self.chat_header, text="💬 Welcome to MORSIFY",
                                             text_color=COLOR_ACCENT,
                                             font=ctk.CTkFont(size=18, weight="bold"))
        self.chat_title_label.pack(anchor="w", padx=20, pady=20)

        self.message_canvas = ctk.CTkScrollableFrame(center, fg_color=COLOR_CHAT_BG, corner_radius=12)
        self.message_canvas.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.input_frame = ctk.CTkFrame(center, fg_color=COLOR_CARD_BG, corner_radius=12)
        self.input_frame.pack(fill="x", padx=12, pady=(0, 12))
        self.input_frame.pack_forget()

        morse_preview_frame = ctk.CTkFrame(self.input_frame, fg_color="transparent", height=30)
        morse_preview_frame.pack(fill="x", padx=15, pady=(8, 0))

        self.morse_preview_label = ctk.CTkLabel(morse_preview_frame,
                                               text="Morse: ",
                                               text_color=COLOR_MORSE,
                                               font=ctk.CTkFont(size=11, family="Courier"),
                                               anchor="w")
        self.morse_preview_label.pack(fill="x")

        input_container = ctk.CTkFrame(self.input_frame, fg_color="transparent")
        input_container.pack(fill="x", padx=15, pady=(0, 12))

        self.entry = ctk.CTkEntry(input_container,
                                 placeholder_text="Type your message...",
                                 height=45,
                                 fg_color=COLOR_ENTRY,
                                 border_color=COLOR_BTN,
                                 text_color=COLOR_TEXT,
                                 font=ctk.CTkFont(size=14))
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry.bind("<KeyRelease>", self.update_morse_preview)
        self.entry.bind("<Return>", lambda e: self.send_message())

        self.send_btn = ctk.CTkButton(input_container,
                                     text="Send",
                                     width=100,
                                     height=45,
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     command=self.send_message,
                                     fg_color=COLOR_BTN,
                                     hover_color=COLOR_BTN_HOVER)
        self.send_btn.pack(side="right")

        right = ctk.CTkFrame(top, width=200, fg_color=COLOR_SIDEBAR, corner_radius=15)
        right.pack(side="right", fill="y", padx=(12, 0), pady=6)
        right.pack_propagate(False)

        stats_card = ctk.CTkFrame(right, fg_color=COLOR_CARD_BG, corner_radius=12)
        stats_card.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(stats_card, text="📊 Statistics",
                     text_color=COLOR_ACCENT,
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 10))

        self.stat_label = ctk.CTkLabel(stats_card,
                                      text="Sent: 0\nReceived: 0\nLost: 0",
                                      text_color=COLOR_TEXT,
                                      font=ctk.CTkFont(size=12),
                                      justify="left")
        self.stat_label.pack(pady=(0, 15))

        encryption_card = ctk.CTkFrame(right, fg_color=COLOR_CARD_BG, corner_radius=12)
        encryption_card.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(encryption_card, text="🔒 Encryption",
                     text_color=COLOR_ACCENT,
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 8))

        self.encryption_status = ctk.CTkLabel(encryption_card,
                                             text="Morse: Active\nFernet: Inactive",
                                             text_color=COLOR_TEXT,
                                             font=ctk.CTkFont(size=11),
                                             justify="left")
        self.encryption_status.pack(pady=(0, 12))

        self.show_welcome_message()

    def update_morse_preview(self, event=None):
        """Update the morse code preview as user types"""
        text = self.entry.get()
        if text:
            morse_text = encode_to_morse_plus(text)
            if len(morse_text) > 100:
                morse_preview = morse_text[:100] + "..."
            else:
                morse_preview = morse_text
            self.morse_preview_label.configure(text=f"Morse: {morse_preview}")
        else:
            self.morse_preview_label.configure(text="Morse: ")

    def update_encryption_status(self):
        """Update the encryption status display"""
        status_text = "Morse: Active\n"
        if self.fernet:
            status_text += "Fernet: Active"
        else:
            status_text += "Fernet: Inactive"
        self.encryption_status.configure(text=status_text)

    def show_welcome_message(self):
        self.clear_message_area()

        welcome_container = ctk.CTkFrame(self.message_canvas, fg_color=COLOR_CHAT_BG)
        welcome_container.pack(fill="both", expand=True, pady=80)

        ctk.CTkLabel(welcome_container, text="🔒",
                     font=ctk.CTkFont(size=64),
                     text_color=COLOR_ACCENT).pack(pady=(0, 20))

        ctk.CTkLabel(welcome_container, text="Welcome to MORSIFY",
                     font=ctk.CTkFont(size=28, weight="bold"),
                     text_color=COLOR_TEXT).pack(pady=(0, 10))

        ctk.CTkLabel(welcome_container,
                     text="Select a user from the sidebar to start a private chat\n\n"
                          "• Secure encrypted messaging\n"
                          "• Real-time communication\n"
                          "• Private chats and main room\n",
                     font=ctk.CTkFont(size=14),
                     text_color=COLOR_TEXT,
                     justify="center").pack(pady=20)

    def toggle_input_area(self, show: bool):
        if show:
            self.input_frame.pack(fill="x", padx=12, pady=(0, 12))
            self.morse_preview_label.configure(text="Morse: ")
        else:
            self.input_frame.pack_forget()

    def add_notification(self, chat_name):
        """Add notification dot to a chat"""
        if chat_name not in self.unread_messages:
            self.unread_messages[chat_name] = 0
        self.unread_messages[chat_name] += 1
        self.update_chat_button(chat_name)

    def clear_notification(self, chat_name):
        """Clear notifications when chat is opened"""
        if chat_name in self.unread_messages:
            self.unread_messages[chat_name] = 0
            self.update_chat_button(chat_name)

    def update_chat_button(self, chat_name):
        """Update button with notification dot"""
        if chat_name in self.chat_buttons:
            button = self.chat_buttons[chat_name]
            unread_count = self.unread_messages.get(chat_name, 0)

            if unread_count > 0:
                button.configure(text=f"{self.get_chat_icon(chat_name)} {chat_name} •{unread_count}")
            else:
                button.configure(text=f"{self.get_chat_icon(chat_name)} {chat_name}")

    def get_chat_icon(self, chat_name):
        """Get appropriate icon for chat type"""
        if chat_name == "main":
            return "🏠"
        return "👤"

    def recv_loop(self):
        buf = b""
        while True:
            try:
                data = self.sock.recv(8192)
                if not data:
                    self.append_system("Server disconnected")
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode())
                        self.handle_msg(msg)
                    except Exception as e:
                        print(f"JSON decode error: {e}")
                        continue
            except Exception as e:
                if self.sock:
                    self.append_system("Connection lost")
                break

    def handle_msg(self, msg):
        t = msg.get("type")

        if t == "user_list":
            users = msg.get("users", [])
            self.online_users = users
            self.populate_user_list(users)
        elif t == "key":
            try:
                key_b64 = msg.get("key")
                key = base64.b64decode(key_b64.encode())
                self.fernet = Fernet(key)
                self.update_encryption_status()
                self.append_system("🔒 Encryption key received - Fernet encryption activated")
            except Exception as e:
                print(f"Key setup error: {e}")
        elif t == "join":
            user = msg.get("user")
            room = msg.get("room", "main")
            if user != self.username:
                self.append_system(f"{user} joined {room}.")
            self.request_user_list()
        elif t == "leave":
            user = msg.get("user")
            self.append_system(f"{user} left.")
            self.request_user_list()
        elif t == "reaction":
            user = msg.get("user")
            reaction = msg.get("reaction")
            self.append_system(f"{user} reacted {reaction}")
        elif t == "packet":
            room = msg.get("room")
            sender = msg.get("sender")
            if sender != self.username and (room == self.username or room == self.room):
                self.handle_packet(msg)
        elif t == "error":
            error_msg = msg.get("message", "Unknown error")
            self.append_system(f"❌ Error: {error_msg}")
        else:
            print(f"Unknown message type: {t}")

    def handle_packet(self, msg):
        self.packets_recv += 1
        self.update_stats()
        mid = msg.get("message_id")
        pkt_no = msg.get("packet_no")
        total = msg.get("total_packets")
        sender = msg.get("sender")
        room = msg.get("room")
        payload_b64 = msg.get("payload")

        with self.lock:
            if mid not in self.reassembly:
                self.reassembly[mid] = {"total": total, "recv": {}, "sender": sender, "room": room}
            self.reassembly[mid]["recv"][pkt_no] = payload_b64
            if len(self.reassembly[mid]["recv"]) == total:
                parts = [self.reassembly[mid]["recv"][i] for i in range(total)]
                full_b64 = "".join(parts)
                try:
                    data = base64.b64decode(full_b64.encode())

                    if self.fernet and room == self.room:
                        try:
                            plaintext = self.fernet.decrypt(data).decode()
                        except:
                            plaintext = data.decode()
                    else:
                        plaintext = data.decode()

                    final_text = decode_from_morse_plus(plaintext)

                    if room == self.username:
                        chat_name = sender
                    else:
                        chat_name = "main"

                    if chat_name not in self.chat_history:
                        self.chat_history[chat_name] = []
                    self.chat_history[chat_name].append((sender, final_text))

                    if not self.current_chat or self.current_chat["name"] != chat_name:
                        self.add_notification(chat_name)
                    else:
                        self.render_chat(chat_name)

                except Exception as e:
                    print(f"Message decode error: {e}")
                    self.append_system("Failed to decode message")
                finally:
                    if mid in self.reassembly:
                        del self.reassembly[mid]

    def request_user_list(self):
        if not self.sock:
            return
        try:
            self.sock.sendall(json.dumps({"type": "list_users"}).encode() + b"\n")
        except Exception as e:
            print(f"Error requesting user list: {e}")

    def refresh_lists(self):
        self.request_user_list()

    def populate_user_list(self, users):
        try:
            for widget in self.user_list_frame.winfo_children():
                widget.destroy()
        except:
            pass

        for u in users:
            if u == self.username:
                continue
            if u not in self.unread_messages:
                self.unread_messages[u] = 0

            btn_text = f"👤 {u}"
            if self.unread_messages[u] > 0:
                btn_text += f" •{self.unread_messages[u]}"

            b = ctk.CTkButton(self.user_list_frame,
                              text=btn_text,
                              width=240,
                              height=40,
                              fg_color=COLOR_CARD_BG,
                              hover_color=COLOR_BTN,
                              text_color=COLOR_TEXT,
                              anchor="w",
                              command=lambda name=u: self.select_chat_user(name))
            b.pack(padx=8, pady=4, fill="x")
            self.chat_buttons[u] = b

    def select_chat_user(self, username):
        self.current_chat = {"name": username, "type": "user"}
        self.chat_title_label.configure(text=f"👤 {username}")
        if username not in self.chat_history:
            self.chat_history[username] = []
        self.clear_notification(username)
        self.render_chat(username)
        self.toggle_input_area(True)

    def select_main_chat(self):
        """Open main broadcast room"""
        self.current_chat = {"name": "main", "type": "room"}
        self.chat_title_label.configure(text="🏠 Main Chat (Broadcast)")
        self.clear_notification("main")

        if "main" not in self.chat_history:
            self.chat_history["main"] = []

        self.render_chat("main")
        self.toggle_input_area(True)

    def clear_message_area(self):
        try:
            for widget in self.message_canvas.winfo_children():
                widget.destroy()
        except:
            pass

    def render_chat(self, chat_name):
        self.clear_message_area()
        msgs = self.chat_history.get(chat_name, [])
        for sender, text in msgs:
            self._append_message_widget(sender, text)

        try:
            self.message_canvas._parent_canvas.yview_moveto(1.0)
        except:
            pass

    def _append_message_widget(self, sender, text):
        container = ctk.CTkFrame(self.message_canvas, fg_color=COLOR_CHAT_BG, corner_radius=8)
        container.pack(fill="x", padx=12, pady=4)

        if sender == self.username:
            bubble_frame = ctk.CTkFrame(container,
                                       fg_color=COLOR_BUBBLE_ME,
                                       corner_radius=15)
            bubble_frame.pack(side="right", anchor="e", padx=8)

            ctk.CTkLabel(bubble_frame, text=text,
                         wraplength=400,
                         justify="left",
                         fg_color=COLOR_BUBBLE_ME,
                         text_color=COLOR_TEXT,
                         corner_radius=15,
                         font=ctk.CTkFont(size=13)).pack(padx=15, pady=10)
        else:
            header_frame = ctk.CTkFrame(container, fg_color="transparent")
            header_frame.pack(side="left", anchor="w", fill="x")

            if sender != "System":
                ctk.CTkLabel(header_frame, text=sender,
                             text_color=COLOR_ACCENT,
                             font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=20)

            bubble_frame = ctk.CTkFrame(header_frame,
                                       fg_color=COLOR_BUBBLE_THEM,
                                       corner_radius=15)
            bubble_frame.pack(side="left", anchor="w", padx=20, pady=(2, 0) if sender != "System" else (0, 0))

            ctk.CTkLabel(bubble_frame, text=text,
                         wraplength=400,
                         justify="left",
                         fg_color=COLOR_BUBBLE_THEM,
                         text_color=COLOR_TEXT,
                         corner_radius=15,
                         font=ctk.CTkFont(size=13)).pack(padx=15, pady=10)

    def send_message(self):
        if not self.current_chat or not self.sock:
            return

        txt = self.entry.get().strip()
        if not txt:
            return

        chat = self.current_chat
        target = chat["name"]

        if target not in self.chat_history:
            self.chat_history[target] = []
        self.chat_history[target].append((self.username, txt))

        if self.current_chat and self.current_chat["name"] == target:
            self.render_chat(target)

        original_text = self.send_btn.cget("text")
        self.send_btn.configure(text="Sending...", state="disabled")
        self.master.update()

        try:
            morse_text = encode_to_morse_plus(txt)
            payload_bytes = morse_text.encode()

            to_encrypt = False
            if chat["name"] == "main" and self.fernet:
                to_encrypt = True

            if to_encrypt:
                try:
                    payload_bytes = self.fernet.encrypt(payload_bytes)
                except Exception as e:
                    print(f"Encryption failed: {e}")

            chunks = chunk_bytes(payload_bytes)
            total = len(chunks)
            mid = make_message_id()
            for i, c in enumerate(chunks):
                b64 = base64.b64encode(c).decode()
                pkt = packet_msg(mid, i, total, self.username, target, b64)
                try:
                    self.sock.sendall(pkt.encode() + b"\n")
                    self.packets_sent += 1
                except Exception as e:
                    print(f"Send error: {e}")
                    self.packets_lost += 1
            self.update_stats()

        except Exception as e:
            print(f"Message send error: {e}")
            self.append_system("Failed to send message")
        finally:
            self.send_btn.configure(text=original_text, state="normal")

        try:
            self.entry.delete(0, "end")
            self.morse_preview_label.configure(text="Morse: ")
        except:
            pass

    def append_system(self, text):
        self.master.after(0, self._append_system_safe, text)

    def _append_system_safe(self, text):
        """Thread-safe system message appending"""
        try:
            container = ctk.CTkFrame(self.message_canvas, fg_color=COLOR_CHAT_BG, corner_radius=8)
            container.pack(fill="x", padx=12, pady=4)

            lbl = ctk.CTkLabel(container,
                               text=f"💬 {text}",
                               anchor="center",
                               text_color=COLOR_ACCENT,
                               font=ctk.CTkFont(size=11, slant="italic"))
            lbl.pack(fill="x", padx=8, pady=6)
        except Exception as e:
            print(f"System message error: {e}")

    def update_stats(self):
        try:
            if self.stat_label:
                self.stat_label.configure(
                    text=f"Sent: {self.packets_sent}\n"
                         f"Received: {self.packets_recv}\n"
                         f"Lost: {self.packets_lost}"
                )
        except:
            pass


if __name__ == "__main__":
    root = ctk.CTk()
    app = ClientApp(root)
    root.mainloop()
