import meshtastic
import meshtastic.serial_interface
import meshtastic.tcp_interface
import meshtastic.util
from meshtastic import mesh_pb2
from meshtastic.mesh_interface import MeshInterface
from pubsub import pub
import time
import traceback
import threading
from datetime import datetime
from typing import Tuple, Optional
from connection_manager import ConnectionStateMachine, ConnectionConfig, ConnectionState

def log_info(msg):
    print(f"INFO: {msg}")
def log_error(msg):
    print(f"ERROR: {msg}")
def dprint(msg):
    print(f"DEBUG: {msg}")

class MeshtasticHandler:
    def __init__(self, connection_type="serial", device_specifier=None, on_message_received_callback=None):
        self.on_message_received_callback = on_message_received_callback
        self.interface = None
        self.node_id = None
        self._connection_type = connection_type
        self._device_specifier = device_specifier

        # Initialize connection state machine
        self._conn_sm = ConnectionStateMachine(
            config=ConnectionConfig(
                initial_timeout=5.0,
                max_retries=5,
                base_retry_delay=2.0,
                max_retry_delay=60.0,
                connection_check_interval=30.0,
            ),
            on_state_change=self._on_state_change,
        )

        print(f"Attempting Meshtastic connection: type='{connection_type}', specifier='{device_specifier or 'auto-detect'}'")
        self._conn_sm.start_connection()
        self._do_connect()

    @property
    def is_connected(self) -> bool:
        return self._conn_sm.state == ConnectionState.CONNECTED

    @is_connected.setter
    def is_connected(self, value: bool):
        # Backward-compat setter: only handle disconnection signals
        if not value and self._conn_sm.state == ConnectionState.CONNECTED:
            self._conn_sm.connection_failed(Exception("Connection lost (flagged externally)"))

    def _on_state_change(self, old_state: ConnectionState, new_state: ConnectionState):
        """React to state machine transitions."""
        log_info(f"Connection state: {old_state.name} -> {new_state.name}")
        if new_state == ConnectionState.CONNECTING and old_state in {ConnectionState.RECONNECTING, ConnectionState.FAILED}:
            # State machine scheduled a reconnect — attempt it in a background thread
            threading.Thread(target=self._do_reconnect, daemon=True).start()

    def _do_connect(self):
        """Perform the initial connection."""
        try:
            if self._connection_type == "serial":
                self.interface = meshtastic.serial_interface.SerialInterface(
                    devPath=self._device_specifier,
                    connectNow=False,
                )
                try:
                    self.interface.connect()
                    if not self.interface.isConnected.wait(timeout=5.0):
                        raise TimeoutError("Connection timeout waiting for Meshtastic device")
                except KeyboardInterrupt:
                    if self.interface:
                        try: self.interface.close()
                        except: pass
                    raise KeyboardInterrupt("Connection attempt interrupted by user")
            elif self._connection_type == "tcp":
                if not self._device_specifier:
                    raise ValueError("Hostname/IP (device_specifier) is required for TCP connection.")
                self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self._device_specifier)
            else:
                raise ValueError(f"Unsupported connection_type: {self._connection_type}")
        except KeyboardInterrupt:
            print("\nConnection attempt interrupted by user")
            if self.interface:
                try: self.interface.close()
                except: pass
            raise
        except Exception as e:
            print(f"Error initializing Meshtastic interface object: {e}")
            if self._connection_type == "serial" and self._device_specifier is None:
                print("Attempted auto-detect for serial. If a device is connected, try specifying its path directly.")
            if isinstance(e, (MeshInterface.MeshInterfaceError, ConnectionRefusedError, TimeoutError, OSError, TypeError)):
                self._conn_sm.connection_failed(e)
                raise ConnectionError(f"Failed to create Meshtastic interface object: {e}") from e
            else:
                raise

        if not self.interface:
            self._conn_sm.connection_failed(Exception("Interface is None"))
            raise ConnectionError("Meshtastic interface object could not be established (is None after init attempt).")

        # Try to get node info with timeout
        retries = 5
        while retries > 0 and (not hasattr(self.interface, 'myInfo') or self.interface.myInfo is None or \
                             not hasattr(self.interface.myInfo, 'my_node_num')):
            try:
                print(f"Waiting for Meshtastic interface to get myInfo (node details)... ({retries} retries left)")
                time.sleep(1.0)
                if hasattr(self.interface, '_readFromRadio'):
                    try: self.interface._readFromRadio()
                    except: pass
                retries -= 1
            except KeyboardInterrupt:
                if self.interface:
                    try: self.interface.close()
                    except: pass
                raise KeyboardInterrupt("Connection attempt interrupted by user")

        if not hasattr(self.interface, 'myInfo') or self.interface.myInfo is None or \
           not hasattr(self.interface.myInfo, 'my_node_num'):
            if self.interface:
                try: self.interface.close()
                except: pass
            self._conn_sm.connection_failed(Exception("No myInfo from device"))
            raise ConnectionError("Failed to get valid node info (myInfo.my_node_num) from Meshtastic device.")

        self.node_id = self.interface.myInfo.my_node_num

        print(f"Meshtastic interface initialized. Attempting to confirm connection status...")

        pub.subscribe(self._on_receive_internal, "meshtastic.receive")
        pub.subscribe(self._on_connection_established, "meshtastic.connection.established")
        pub.subscribe(self._on_connection_lost, "meshtastic.connection.lost")

        # Wait briefly for connection confirmation
        try:
            time.sleep(0.5)
            if self.interface and hasattr(self.interface, 'isConnected') and self.interface.isConnected:
                self._conn_sm.connection_succeeded()
                print(f"Meshtastic connected. Node ID: {self.node_id:x}")
                if hasattr(self.interface.myInfo, 'long_name') and hasattr(self.interface.myInfo, 'short_name'):
                    print(f"Node Name: {self.interface.myInfo.long_name} ({self.interface.myInfo.short_name})")
            elif self.interface and self.node_id is not None:
                self._conn_sm.connection_succeeded()
                print(f"Meshtastic Node ID {self.node_id:x} retrieved. Waiting for 'established' event.")
        except KeyboardInterrupt:
            if self.interface:
                try: self.interface.close()
                except: pass
            raise KeyboardInterrupt("Connection attempt interrupted by user")

    def _on_connection_established(self, interface):
        print(f"Meshtastic Connection Event: Established (Interface: {interface})")
        self._conn_sm.connection_succeeded()
        if self.interface and hasattr(self.interface, 'myInfo') and self.interface.myInfo and hasattr(self.interface.myInfo, 'my_node_num'):
             self.node_id = self.interface.myInfo.my_node_num
             print(f"Connection established. AI Node ID confirmed: {self.node_id:x}")
        else:
             print("Warning: myInfo not fully available on 'connection established' event.")

    def _on_connection_lost(self, interface):
        print(f"Meshtastic Connection Event: Lost (Interface: {interface})")
        self._conn_sm.connection_failed(Exception("Connection lost event from Meshtastic"))
        print("Meshtastic connection lost. State machine will handle reconnection.")

    def _do_reconnect(self):
        """Background reconnection attempt triggered by the state machine."""
        log_info("Attempting reconnection...")
        try:
            # Close old interface
            if self.interface:
                try:
                    pub.unsubscribe(self._on_receive_internal, "meshtastic.receive")
                    pub.unsubscribe(self._on_connection_established, "meshtastic.connection.established")
                    pub.unsubscribe(self._on_connection_lost, "meshtastic.connection.lost")
                except Exception:
                    pass
                try:
                    self.interface.close()
                except Exception:
                    pass
                self.interface = None

            # Recreate interface
            if self._connection_type == "serial":
                self.interface = meshtastic.serial_interface.SerialInterface(
                    devPath=self._device_specifier,
                    connectNow=False,
                )
                self.interface.connect()
                if not self.interface.isConnected.wait(timeout=5.0):
                    raise TimeoutError("Reconnection timeout")
            elif self._connection_type == "tcp":
                self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self._device_specifier)

            if not self.interface:
                raise ConnectionError("Interface is None after reconnect")

            # Wait for myInfo
            for _ in range(5):
                if hasattr(self.interface, 'myInfo') and self.interface.myInfo and hasattr(self.interface.myInfo, 'my_node_num'):
                    break
                time.sleep(1.0)

            if hasattr(self.interface, 'myInfo') and self.interface.myInfo and hasattr(self.interface.myInfo, 'my_node_num'):
                self.node_id = self.interface.myInfo.my_node_num

            pub.subscribe(self._on_receive_internal, "meshtastic.receive")
            pub.subscribe(self._on_connection_established, "meshtastic.connection.established")
            pub.subscribe(self._on_connection_lost, "meshtastic.connection.lost")

            self._conn_sm.connection_succeeded()
            log_info(f"Reconnection successful. Node ID: {self.node_id:x}")

        except Exception as e:
            log_error(f"Reconnection failed: {e}")
            self._conn_sm.connection_failed(e)

    def _on_receive_internal(self, packet, interface):
        if not packet: return
        # Update state machine activity on every received packet
        self._conn_sm.update_activity()
        sender_id_hex = ""
        user_name_to_use = ""
        try:
            sender_id_num = packet.get('from')
            if sender_id_num is None: return
            if self.node_id is not None and sender_id_num == self.node_id: return

            sender_id_hex = f"{sender_id_num:x}"
            user_name_to_use = f"Node-{sender_id_hex}" 

            if interface and hasattr(interface, 'nodes') and interface.nodes and sender_id_num in interface.nodes:
                node_info = interface.nodes[sender_id_num]
                if node_info and 'user' in node_info and node_info['user']:
                    user_data = node_info['user']
                    short_name_val = user_data.get('shortName')
                    long_name_val = user_data.get('longName')

                    s_name = str(short_name_val).strip() if short_name_val is not None else ""
                    l_name = str(long_name_val).strip() if long_name_val is not None else ""

                    if s_name: 
                        user_name_to_use = s_name
                    elif l_name: 
                        user_name_to_use = l_name
            
            decoded_packet = packet.get('decoded')
            if decoded_packet:
                message_text = None
                portnum_string = decoded_packet.get('portnum') 

                if portnum_string == 'TEXT_MESSAGE_APP': 
                    message_text = decoded_packet.get('text')
                elif portnum_string == 'PRIVATE_APP': 
                    if 'payload' in decoded_packet:
                        try:
                            message_text = decoded_packet['payload'].decode('utf-8', errors='strict')
                            if not (message_text and all(c.isprintable() or c.isspace() for c in message_text)):
                                message_text = None 
                        except UnicodeDecodeError:
                            message_text = None 
                
                if message_text is not None:
                    channel_id_from_packet_field = packet.get('channel')
                    destination_id_num = packet.get('to')
                    destination_id_hex = f"{destination_id_num:x}" if destination_id_num is not None else f"{meshtastic.BROADCAST_NUM:x}"
                    channel_id = channel_id_from_packet_field

                    if self.on_message_received_callback:
                        self.on_message_received_callback(
                            text=message_text, 
                            sender_id=sender_id_hex, 
                            sender_name=user_name_to_use, 
                            destination_id=destination_id_hex, 
                            channel_id=channel_id
                        )
        except Exception as e:
            error_user_context = user_name_to_use if user_name_to_use else sender_id_hex
            print(f"ERROR in _on_receive_internal (From: {error_user_context}). Packet: {packet}. Error: {e}")
            traceback.print_exc()

    def send_message(self, text: str, destination_id_hex: str = None, channel_index: int = None) -> Tuple[bool, str]:
        """Send a message to a specific node or channel"""
        if not self.is_connected:
            return False, "Not connected to Meshtastic device"
            
        log_prefix = f"[send_message@{datetime.now().isoformat()}]"
        # Ensure text is a string and handle it safely for logging
        text_str = str(text) if text is not None else ""
        log_info(f"{log_prefix} Attempting to send message.")
        log_info(f"{log_prefix} Text type: {type(text)}")
        log_info(f"{log_prefix} Text value: {repr(text)}")
        log_info(f"{log_prefix} Params: text='{text_str[:50]}', destination_id_hex={destination_id_hex}, channel_index={channel_index}")
        
        if not self.interface or not self.is_connected:
            msg = f"{log_prefix} ERROR: Meshtastic not connected. Cannot send message."
            print(msg)
            log_error(msg)
            return (False, "not_connected")
        
        if not isinstance(channel_index, int) or channel_index < 0:
            log_info(f"{log_prefix} Invalid channel_index '{channel_index}', defaulting to 0.")
            channel_index = 0
        
        try:
            is_broadcast_destination = False
            if destination_id_hex:
                dest_lower = destination_id_hex.lower()
                if dest_lower == "broadcast" or dest_lower == f"{meshtastic.BROADCAST_NUM:x}".lower():
                    is_broadcast_destination = True
            
            log_info(f"{log_prefix} is_broadcast_destination: {is_broadcast_destination}")
            
            if destination_id_hex and not is_broadcast_destination:
                try:
                    dest_node_num = int(destination_id_hex, 16)
                    log_info(f"{log_prefix} Sending DM to node {dest_node_num:x}")
                    before = datetime.now()
                    # For DMs, don't specify channelIndex to use default channel
                    self.interface.sendText(text, destinationId=dest_node_num, wantAck=True)
                    after = datetime.now()
                    log_info(f"{log_prefix} sendText() for DM completed in {(after-before).total_seconds():.3f}s")
                    self._conn_sm.update_activity()
                    return (True, "dm_sent")
                except ValueError:
                    msg = f"{log_prefix} ERROR: Invalid destination_id_hex format '{destination_id_hex}'. Cannot send DM."
                    print(msg)
                    log_error(msg)
                    return (False, "invalid_destination_id_hex")
            else:
                log_info(f"{log_prefix} Sending channel message on channel {channel_index}")
                before = datetime.now()
                self.interface.sendText(text, channelIndex=channel_index, wantAck=False)
                after = datetime.now()
                log_info(f"{log_prefix} sendText() for channel completed in {(after-before).total_seconds():.3f}s")
                self._conn_sm.update_activity()
                return (True, "channel_sent")
        except BrokenPipeError as bpe:
            msg = f"{log_prefix} ERROR sending Meshtastic message (BrokenPipeError): {bpe}. Connection likely lost."
            print(msg)
            log_error(msg)
            self.is_connected = False 
            if hasattr(self.interface, '_disconnected'): 
                try: self.interface._disconnected()
                except: pass
            log_error(f"{log_prefix} BrokenPipeError traceback: {traceback.format_exc()}")
            return (False, "broken_pipe")
        except Exception as e:
            msg = f"{log_prefix} ERROR sending Meshtastic message: {e}"
            print(msg)
            log_error(msg)
            log_error(f"{log_prefix} Exception traceback: {traceback.format_exc()}")
            if "not connected" in str(e).lower() or "disconnected" in str(e).lower() or "pipe" in str(e).lower():
                self.is_connected = False
            return (False, str(e))

    def list_channels(self):
        if not self.interface or not self.is_connected:
            print("ERROR: Meshtastic not connected. Cannot list channels.")
            return [] # Return empty list on error
        
        channels_info = []
        try:
            if self.interface and hasattr(self.interface, 'channels') and self.interface.channels:
                # print("\nAvailable Channels (from device's perspective):") # TUI will handle display
                for ch_index, ch_container in self.interface.channels.items(): # Iterate through dict
                    settings = ch_container.settings
                    role = ch_container.role 
                    
                    name = f"Ch-{ch_index}" # Default name
                    if mesh_pb2 and hasattr(mesh_pb2, 'Channel') and hasattr(mesh_pb2.Channel, 'Role'):
                        if settings and hasattr(settings, 'name') and settings.name: 
                            name = settings.name
                        elif role == mesh_pb2.Channel.Role.PRIMARY: 
                            name = "PRIMARY" 
                        elif role == mesh_pb2.Channel.Role.SECONDARY and (not settings or not settings.name): 
                            name = f"Secondary-{ch_index}"
                    elif settings and hasattr(settings, 'name') and settings.name:
                        name = settings.name

                    try: 
                        role_name = str(role) 
                        if mesh_pb2 and hasattr(mesh_pb2, 'Channel') and hasattr(mesh_pb2.Channel, 'Role') and hasattr(mesh_pb2.Channel.Role, 'Name'):
                            role_name = mesh_pb2.Channel.Role.Name(role) 
                    except: pass

                    # info_str = f"  Index: {ch_index}, Name: \"{name}\", Role: {role_name}"
                    # print(info_str) # Removed direct print
                    channels_info.append({"index": ch_index, "name": name, "role": role_name})
                # print("")
            else:
                print("INFO: No channel information available from device (interface.channels is empty or None).")
        except Exception as e:
            print(f"ERROR listing channels: {e}")
            traceback.print_exc()
        return channels_info

    def get_connection_status(self):
        """Get detailed connection status from state machine."""
        return self._conn_sm.get_connection_status()

    def close(self):
        print("Closing Meshtastic interface...")
        # Shutdown state machine (stops monitor thread, timers)
        self._conn_sm.shutdown()

        if self.interface:
            try:
                pub.unsubscribe(self._on_receive_internal, "meshtastic.receive")
                pub.unsubscribe(self._on_connection_established, "meshtastic.connection.established")
                pub.unsubscribe(self._on_connection_lost, "meshtastic.connection.lost")
            except Exception as e_unsub:
                print(f"Warning: Error during pubsub unsubscribe: {e_unsub}")

            try:
                self.interface.close()
            except Exception as e_close:
                print(f"Warning: Error closing Meshtastic interface: {e_close}")

            self.interface = None
        print("Meshtastic interface closed.")

