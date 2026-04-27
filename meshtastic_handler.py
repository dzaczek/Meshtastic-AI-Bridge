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
    def __init__(self, connection_type="serial", device_specifier=None,
                 on_message_received_callback=None, on_packet_callback=None):
        self.on_message_received_callback = on_message_received_callback
        self.on_packet_callback = on_packet_callback  # fires for EVERY received packet
        self.interface = None
        self.node_id = None
        self._connection_type = connection_type
        self._device_specifier = device_specifier
        self._last_rx_time: float = 0.0    # unix ts of last received packet
        self._last_tx_packet_id: int | None = None  # id of last sent packet

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

            # Recreate interface — wrap in thread with timeout so a hanging
            # TCP connect (device rebooting) doesn't block forever.
            _TCP_TIMEOUT = 25  # seconds
            new_iface = [None]
            new_err   = [None]
            done_ev   = threading.Event()

            def _connect():
                try:
                    if self._connection_type == "serial":
                        iface = meshtastic.serial_interface.SerialInterface(
                            devPath=self._device_specifier, connectNow=False)
                        iface.connect()
                        if not iface.isConnected.wait(timeout=5.0):
                            raise TimeoutError("Serial connection timeout")
                        new_iface[0] = iface
                    elif self._connection_type == "tcp":
                        new_iface[0] = meshtastic.tcp_interface.TCPInterface(
                            hostname=self._device_specifier)
                except Exception as e:
                    new_err[0] = e
                finally:
                    done_ev.set()

            t = threading.Thread(target=_connect, daemon=True)
            t.start()
            if not done_ev.wait(timeout=_TCP_TIMEOUT):
                raise TimeoutError(f"Connection attempt timed out after {_TCP_TIMEOUT}s")
            if new_err[0]:
                raise new_err[0]

            self.interface = new_iface[0]
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

    @property
    def last_rx_time(self) -> float:
        """Unix timestamp of last received packet (0 = never)."""
        return self._last_rx_time

    @property
    def is_link_alive(self) -> bool:
        """True if connected AND received traffic in the last 3 minutes."""
        if not self.is_connected:
            return False
        if self._last_rx_time == 0:
            return True          # just connected, give it grace period
        return (time.time() - self._last_rx_time) < 180

    def _on_receive_internal(self, packet, interface):
        if not packet: return
        self._last_rx_time = time.time()
        # Update state machine activity on every received packet
        self._conn_sm.update_activity()

        # Fire raw packet callback (for packet analysis / web UI)
        if self.on_packet_callback:
            try:
                self.on_packet_callback(packet, interface)
            except Exception:
                pass

        sender_id_hex = ""
        user_name_to_use = ""
        try:
            sender_id_num = packet.get('from')
            if sender_id_num is None: return
            if self.node_id is not None and sender_id_num == self.node_id: return

            sender_id_hex = f"{sender_id_num:x}"
            user_name_to_use = f"Node-{sender_id_hex}" 

            if interface and hasattr(interface, 'nodes') and interface.nodes:
                # Try int key first, then string "!hex" key
                node_info = interface.nodes.get(sender_id_num)
                if node_info is None:
                    node_info = interface.nodes.get(f"!{sender_id_hex}")
                if node_info and 'user' in node_info and node_info['user']:
                    user_data = node_info['user']
                    short_name_val = user_data.get('shortName')
                    long_name_val = user_data.get('longName')

                    s_name = str(short_name_val).strip() if short_name_val is not None else ""
                    l_name = str(long_name_val).strip() if long_name_val is not None else ""

                    if s_name and l_name and s_name != l_name:
                        user_name_to_use = f"{s_name}/{l_name}"
                    elif l_name:
                        user_name_to_use = l_name
                    elif s_name:
                        user_name_to_use = s_name
            
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
                    pkt = self.interface.sendText(text, destinationId=dest_node_num, wantAck=True)
                    self._last_tx_packet_id = getattr(pkt, 'id', None)
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
                pkt = self.interface.sendText(text, channelIndex=channel_index, wantAck=False)
                self._last_tx_packet_id = getattr(pkt, 'id', None)
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
            return []

        channels_info = []
        try:
            # interface.channels may be an empty dict in some library versions;
            # fall back to node.channels which is a list of Channel proto objects.
            ch_source = None
            iface_ch  = getattr(self.interface, 'channels', None)
            if iface_ch:
                ch_source = iface_ch  # dict {index: Channel}
            else:
                try:
                    node = self.interface.getNode('^local')
                    node_ch = getattr(node, 'channels', None)
                    if node_ch:
                        ch_source = node_ch  # list of Channel proto
                except Exception:
                    pass

            if not ch_source:
                return []

            # Normalise: dict → items(), list → enumerate
            if isinstance(ch_source, dict):
                items = ch_source.items()
            else:
                items = enumerate(ch_source)

            for ch_index, ch_container in items:
                settings = getattr(ch_container, 'settings', None)
                role     = getattr(ch_container, 'role', None)

                # Skip DISABLED channels (role == 0)
                if role is not None and int(role) == 0:
                    continue

                name = settings.name if (settings and getattr(settings, 'name', '')) else f"Ch-{ch_index}"
                if not name:
                    name = "PRIMARY" if int(role or 0) == 1 else f"Ch-{ch_index}"

                try:
                    role_name = str(role)
                except Exception:
                    role_name = "unknown"

                channels_info.append({"index": ch_index, "name": name, "role": role_name})

        except Exception as e:
            print(f"ERROR listing channels: {e}")
        return channels_info

    def get_connection_status(self):
        """Get detailed connection status from state machine."""
        return self._conn_sm.get_connection_status()

    def _raw_config_debug(self) -> dict:
        """Return diagnostic info about what Python sees in the interface."""
        if not self.interface:
            return {'error': 'no interface'}
        info = {}
        # Library version
        try:
            import meshtastic as _m
            info['meshtastic_version'] = getattr(_m, '__version__', 'unknown')
        except Exception:
            info['meshtastic_version'] = 'import failed'
        # Key interface attributes
        for attr in ('localConfig', 'moduleConfig', 'channels', 'myInfo',
                     'radioConfig', 'nodesByNum', 'localNode'):
            val = getattr(self.interface, attr, 'MISSING')
            size = len(val) if hasattr(val, '__len__') else 'n/a'
            info[f'iface.{attr}'] = f'{type(val).__name__} | len={size}'
        # Try to read lora fields directly
        lc = getattr(self.interface, 'localConfig', None)
        if lc is not None:
            try:
                info['lc_text_sample'] = str(lc)[:400]
                info['lora_region']      = int(lc.lora.region)
                info['lora_hop_limit']   = int(lc.lora.hop_limit)
            except Exception as e:
                info['lc_read_error'] = str(e)
        # Try getNode
        try:
            node = self.interface.getNode('^local')
            info['node_type'] = type(node).__name__
            nlc = getattr(node, 'localConfig', 'MISSING')
            info['node.localConfig'] = type(nlc).__name__
            if nlc not in (None, 'MISSING') and hasattr(nlc, 'lora'):
                info['node.lora_region'] = int(nlc.lora.region)
            nch = getattr(node, 'channels', 'MISSING')
            info['node.channels'] = f'{type(nch).__name__} len={len(nch) if hasattr(nch,"__len__") else "?"}'
            info['node_methods'] = [m for m in dir(node) if not m.startswith('_') and callable(getattr(node, m, None))]
        except Exception as e:
            info['node_error'] = str(e)
        return info

    def _get_local_node(self):
        """Return the local node object, trying multiple library APIs."""
        try:
            return self.interface.getNode('^local')
        except Exception:
            pass
        # Fallback: localNode attribute (some library versions)
        return getattr(self.interface, 'localNode', None)

    def _resolve_lc_mc(self, warnings: list):
        """Resolve localConfig, moduleConfig and channels from the best source."""
        node = self._get_local_node()

        # ── localConfig: prefer node.localConfig (interface.localConfig may not exist) ─
        lc = None
        for src in (
            lambda: getattr(self.interface, 'localConfig', None),
            lambda: getattr(node, 'localConfig', None) if node else None,
        ):
            candidate = src()
            # Accept only genuine protobuf messages (not None / strings / etc.)
            if candidate is not None and hasattr(candidate, 'lora'):
                lc = candidate
                break

        if lc is None and self.is_connected and node:
            fn = getattr(node, 'requestConfig', None) or getattr(node, '_requestConfig', None)
            if callable(fn):
                warnings.append('Calling requestConfig() — waiting up to 4 s')
                try:
                    fn()
                except Exception as e:
                    warnings.append(f'requestConfig() raised: {e}')
                for _ in range(40):
                    time.sleep(0.1)
                    cand = getattr(self.interface, 'localConfig', None) or \
                           getattr(node, 'localConfig', None)
                    if cand is not None and hasattr(cand, 'lora'):
                        lc = cand
                        warnings.append('Got localConfig after requestConfig()')
                        break

        # ── moduleConfig ──────────────────────────────────────────────────
        mc = None
        for src in (
            lambda: getattr(self.interface, 'moduleConfig', None),
            lambda: getattr(node, 'moduleConfig', None) if node else None,
        ):
            candidate = src()
            if candidate is not None and hasattr(candidate, 'mqtt'):
                mc = candidate
                break

        # ── channels: node.channels is a list in this library version ─────
        ch_raw = None
        for src in (
            lambda: getattr(self.interface, 'channels', None),
            lambda: getattr(node, 'channels', None) if node else None,
        ):
            candidate = src()
            if candidate:          # non-empty list or non-empty dict
                ch_raw = candidate
                break

        return lc, mc, ch_raw

    def get_device_config(self) -> dict:
        """Return full device config as a JSON-serializable dict."""
        if not self.interface:
            return {'_error': 'Not connected'}
        result: dict = {}
        warnings: list = []

        try:
            from google.protobuf.json_format import MessageToDict
        except ImportError as exc:
            return {'_error': f'google.protobuf unavailable: {exc}'}

        _base = dict(preserving_proto_field_name=True, use_integers_for_enums=True)

        def _probe_extra(sample_msg):
            """Find which extra kwargs MessageToDict accepts in this protobuf version."""
            for extra in (
                {'including_default_value_fields': True, 'float_precision': 6},
                {'including_default_value_fields': True},
                {'always_print_fields_with_no_presence': True},
                {},
            ):
                try:
                    MessageToDict(sample_msg, **_base, **extra)
                    return extra
                except (TypeError, AttributeError):
                    continue
            return {}

        def m2d(msg, _extra=[None]):
            # Lazy-probe on first real call so we have an actual msg object
            if _extra[0] is None:
                _extra[0] = _probe_extra(msg)
            try:
                return MessageToDict(msg, **_base, **_extra[0])
            except Exception:
                return MessageToDict(msg)

        LOCAL_SECS  = ('device', 'position', 'power', 'network', 'display', 'lora', 'bluetooth')
        MODULE_SECS = (
            'mqtt', 'serial', 'external_notification', 'store_forward',
            'range_test', 'telemetry', 'canned_message', 'audio',
            'remote_hardware', 'neighbor_info', 'ambient_lighting', 'detection_sensor',
        )

        lc, mc, channels_raw = self._resolve_lc_mc(warnings)

        # ── Local config ──────────────────────────────────────────────────
        for sec in LOCAL_SECS:
            if lc is None:
                result[sec] = {}
                continue
            try:
                sub = getattr(lc, sec, None)
                result[sec] = m2d(sub) if sub is not None else {}
            except Exception as exc:
                result[sec] = {}
                warnings.append(f'lc.{sec}: {exc}')

        # ── Module config ─────────────────────────────────────────────────
        for sec in MODULE_SECS:
            if mc is None:
                result[sec] = {}
                continue
            try:
                sub = getattr(mc, sec, None)
                result[sec] = m2d(sub) if sub is not None else {}
            except Exception as exc:
                result[sec] = {}
                warnings.append(f'mc.{sec}: {exc}')

        # ── Owner ─────────────────────────────────────────────────────────
        my_num = self.node_id
        for nd in (getattr(self.interface, 'nodes', None) or {}).values():
            if nd.get('num') == my_num:
                u = nd.get('user', {})
                result['owner'] = {
                    'long_name':   u.get('longName',  ''),
                    'short_name':  u.get('shortName', ''),
                    'is_licensed': bool(u.get('isLicensed', False)),
                }
                break
        if 'owner' not in result:
            result['owner'] = {}
            warnings.append('Own node not found in nodes cache')

        # ── Channels (list or dict depending on library version) ──────────
        if channels_raw:
            result['channels'] = []
            # node.channels is a list; interface.channels may be a dict
            if isinstance(channels_raw, dict):
                items = [(idx, channels_raw[idx]) for idx in sorted(channels_raw.keys())]
            else:
                items = [(ch_obj.index if hasattr(ch_obj, 'index') else i, ch_obj)
                         for i, ch_obj in enumerate(channels_raw)]
            for idx, ch_obj in items:
                try:
                    ch_dict = m2d(ch_obj)
                    ch_dict['index'] = int(idx)
                    ch_dict.setdefault('settings', {})
                    result['channels'].append(ch_dict)
                except Exception as exc:
                    warnings.append(f'channel {idx}: {exc}')
        else:
            result['channels'] = []
            warnings.append('No channel data')

        if warnings:
            result['_warnings'] = warnings
        return result

    def set_device_config(self, section: str, values: dict) -> tuple:
        """Write one config section to the device. Returns (ok, message)."""
        if not self.interface or not self.is_connected:
            return False, "Not connected"
        LOCAL_SECS  = {'device', 'position', 'power', 'network', 'display', 'lora', 'bluetooth'}
        MODULE_SECS = {
            'mqtt', 'serial', 'external_notification', 'store_forward', 'range_test',
            'telemetry', 'canned_message', 'audio', 'remote_hardware', 'neighbor_info',
            'ambient_lighting', 'detection_sensor',
        }
        try:
            from google.protobuf.json_format import ParseDict
            node = self.interface.getNode('^local')
            if section == 'owner':
                node.setOwner(
                    long_name=values.get('long_name') or values.get('longName') or '',
                    short_name=values.get('short_name') or values.get('shortName') or '',
                    is_licensed=bool(values.get('is_licensed', False)),
                )
                return True, "Owner updated"
            elif section in LOCAL_SECS:
                # Resolve localConfig from node (interface.localConfig may not exist)
                lc = getattr(self.interface, 'localConfig', None)
                if lc is None or not hasattr(lc, section):
                    lc = getattr(node, 'localConfig', None)
                if lc is None:
                    return False, "localConfig not available"
                proto_cfg = getattr(lc, section)
                ParseDict(values, proto_cfg, ignore_unknown_fields=True)
                node.writeConfig(section)
                return True, f"Saved {section}"
            elif section in MODULE_SECS:
                mc = getattr(self.interface, 'moduleConfig', None)
                if mc is None or not hasattr(mc, section):
                    mc = getattr(node, 'moduleConfig', None)
                if mc is None:
                    return False, "moduleConfig not available"
                proto_cfg = getattr(mc, section, None)
                if proto_cfg is None:
                    return False, f"Module section not found: {section}"
                ParseDict(values, proto_cfg, ignore_unknown_fields=True)
                node.writeConfig(section)
                return True, f"Saved module/{section}"
            elif section == 'channel':
                import base64 as _b64
                ch_idx = int(values.get('index', 0))
                # Find the channel object in node.channels (list or dict)
                node_chs = getattr(node, 'channels', None)
                ch_obj = None
                if isinstance(node_chs, list):
                    for c in node_chs:
                        if getattr(c, 'index', None) == ch_idx:
                            ch_obj = c
                            break
                elif isinstance(node_chs, dict):
                    ch_obj = node_chs.get(ch_idx)
                if ch_obj is None:
                    # Channel slot not found — use the slot directly from the list
                    # (writeChannel uses list index, NOT ch.index field)
                    if isinstance(node_chs, list) and ch_idx < len(node_chs):
                        ch_obj = node_chs[ch_idx]
                    else:
                        from meshtastic import channel_pb2
                        ch_obj = channel_pb2.Channel()
                        ch_obj.index = ch_idx
                # Set role
                ch_obj.role = int(values.get('role', 0))
                settings = values.get('settings', {})
                if settings:
                    # Handle PSK explicitly — NEVER rely on ParseDict for bytes fields.
                    # ParseDict can silently mangle the bytes depending on protobuf version.
                    # We decode base64 → raw bytes directly, matching what the official
                    # Meshtastic clients do.
                    psk_b64 = settings.pop('psk', None)
                    if psk_b64 is not None:
                        psk_b64_clean = str(psk_b64).strip()
                        if psk_b64_clean:
                            # Normalise padding and decode
                            missing = len(psk_b64_clean) % 4
                            if missing:
                                psk_b64_clean += '=' * (4 - missing)
                            ch_obj.settings.psk = _b64.b64decode(psk_b64_clean)
                        else:
                            ch_obj.settings.psk = b''   # empty = no encryption
                    # Remaining settings (name, uplink_enabled, etc.) via ParseDict
                    if settings:
                        ParseDict(settings, ch_obj.settings, ignore_unknown_fields=True)
                # Write to device — prefer writeChannel(idx), fall back to setChannel
                if hasattr(node, 'writeChannel'):
                    node.writeChannel(ch_idx)
                elif hasattr(node, 'setChannel'):
                    node.setChannel(ch_obj)
                else:
                    return False, "No write method (writeChannel/setChannel) on node"
                # Verify what was actually written back
                try:
                    written_psk = _b64.b64encode(ch_obj.settings.psk).decode()
                    print(f"[channel] CH{ch_idx} saved — role={ch_obj.role} "
                          f"psk_written={written_psk!r} ({len(ch_obj.settings.psk)}B)")
                except Exception:
                    pass
                return True, f"Channel {ch_idx} saved"
            else:
                return False, f"Unknown section: {section}"
        except Exception as e:
            traceback.print_exc()
            return False, str(e)

    def send_traceroute(self, dest_id_hex: str, hop_limit: int = 7) -> tuple:
        """Send a TRACEROUTE_APP packet to a destination node."""
        if not self.interface or not self.is_connected:
            return False, "Not connected"
        try:
            dest_num = int(dest_id_hex, 16)

            # Method 1: high-level interface API
            if hasattr(self.interface, 'sendTraceroute'):
                self.interface.sendTraceroute(dest_num, hop_limit)
                return True, f"Traceroute sent to !{dest_id_hex}"

            # Method 2: node-level API
            try:
                node = self.interface.getNode('^local')
                if hasattr(node, 'sendTraceroute'):
                    node.sendTraceroute(dest_num, hop_limit)
                    return True, f"Traceroute sent to !{dest_id_hex}"
            except Exception:
                pass

            # Method 3: sendData with TRACEROUTE_APP portnum = 70
            # This works across all meshtastic library versions that have sendData
            if hasattr(self.interface, 'sendData'):
                try:
                    self.interface.sendData(
                        b'',
                        destinationId=dest_num,
                        portNum=70,   # TRACEROUTE_APP
                        wantAck=False,
                        wantResponse=True,
                        hopLimit=hop_limit,
                    )
                except TypeError:
                    # Older versions don't have hopLimit param
                    self.interface.sendData(
                        b'',
                        destinationId=dest_num,
                        portNum=70,
                        wantAck=False,
                        wantResponse=True,
                    )
                return True, f"Traceroute sent to !{dest_id_hex}"

            return False, "sendData not available — upgrade meshtastic library"

        except Exception as e:
            traceback.print_exc()
            return False, str(e)

    def set_fixed_position(self, lat: float, lon: float, alt: int = 0) -> tuple:
        """Set a fixed GPS position that the node broadcasts when GPS is disabled."""
        if not self.interface or not self.is_connected:
            return False, "Not connected"
        try:
            node = self.interface.getNode('^local')
            node.setFixedPosition(lat, lon, alt)
            return True, f"Fixed position set: {lat:.6f}, {lon:.6f} alt={alt}m"
        except Exception as e:
            traceback.print_exc()
            return False, str(e)

    def remove_fixed_position(self) -> tuple:
        """Remove the fixed position from the device."""
        if not self.interface or not self.is_connected:
            return False, "Not connected"
        try:
            node = self.interface.getNode('^local')
            node.removeFixedPosition()
            return True, "Fixed position removed"
        except Exception as e:
            traceback.print_exc()
            return False, str(e)

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

