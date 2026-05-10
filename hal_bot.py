import json
import time
import math
import threading
from datetime import datetime
import re
from typing import Dict, Optional, Tuple
import node_db
try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
try:
    import stats_chart as _sc
    _HAS_STATS = True
except ImportError:
    _HAS_STATS = False
try:
    import weather_map as _wm
    _HAS_WEATHER_MAP = True
except ImportError:
    _HAS_WEATHER_MAP = False

class HalBot:
    def __init__(self, meshtastic_handler, app_config=None):
        self.meshtastic_handler = meshtastic_handler
        self.app_config = app_config
        self.bot_name = getattr(app_config, 'BOT_NAME', 'Eva') if app_config else 'Eva'
        self.command_pattern = re.compile(r'^(?:bot\s+)?(\w+)(?:\s+(.+))?$', re.IGNORECASE)
        self.admin_pattern = re.compile(r'^!admin\s+(\w+)(?:\s+(.+))?$', re.IGNORECASE)
        self.traceroute_timeout = 30  # seconds
        self.pending_traceroutes = {}  # Store pending traceroute requests
        self.active_traceroutes = {}  # Store active traceroute requests
        self.mqtt_broker = "mqtt.meshtastic.org"  # Default MQTT broker
        self.gateway_info = {}  # Store gateway information for MQTT nodes
        self.admin_node_ids = getattr(app_config, 'ADMIN_NODE_IDS', []) if app_config else []
        self.matrix_forward_cb = None   # set by main_app after init
        self.private_reply_fn = None   # set by main_app after init
        self._pending_sends = []       # (reply, destination_id_hex, channel_index, is_dm) tuples
        self._pending_lock = threading.Lock()

    def _get_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the great circle distance between two points on the earth (specified in decimal degrees)"""
        R = 6371.0 # Radius of the earth in km
        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)
        a = math.sin(dLat / 2) * math.sin(dLat / 2) + \
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
            math.sin(dLon / 2) * math.sin(dLon / 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @staticmethod
    def _normalize_cmd(text: str) -> str:
        """Strip !, /, backticks and extra whitespace from a command text."""
        t = text.strip()
        # Strip leading / (but not //)
        if t.startswith('/') and not t.startswith('//'):
            t = t[1:].strip()
        # Strip leading ! (but not !admin)
        if t.startswith('!') and not t.lower().startswith('!admin'):
            t = t[1:].strip()
        # Strip backtick wrapping: `command` or `command args`
        t = t.strip('`').strip()
        return t

    def _help_triggered(self, original_text: str, clean: str) -> bool:
        """'help' fires only with ! prefix OR when followed by a partial bot name."""
        has_bang = original_text.lstrip().startswith('!')
        # !help  or  !help <anything>
        if has_bang and (clean == 'help' or clean.startswith('help ')):
            return True
        # help <word> where word partially matches bot name (case-insensitive)
        m = re.match(r'^help\s+(\S+)', clean)
        if m:
            word = m.group(1).upper()
            bot_up = self.bot_name.upper()
            # word is prefix of bot name, or bot name contains word
            if bot_up.startswith(word) or word in bot_up:
                return True
        return False

    def should_handle_message(self, text: str) -> bool:
        """Check if the message should be handled by the bot"""
        text = text.strip()
        text_lower = text.lower()

        # Admin commands
        if text_lower.startswith("!admin"):
            return True

        # Normalize (strip !, backticks) before checking commands
        clean = self._normalize_cmd(text).lower()

        # Direct commands (no bot-name guard needed)
        if clean in ['ping', 'traceroute', 'gtraceroute', 'info', 'test', 'qsl',
                     'distance', 'odleglosc', 'stats',
                     'weather', 'pogoda', 'wx', 'meteo', 'wetter', 'météo', 'tiempo', 'tempo']:
            return True

        # 'help' requires ! prefix or bot name partial match
        if self._help_triggered(text, clean):
            return True

        # Bot-prefixed commands  e.g.  "bot ping"
        match = self.command_pattern.match(clean)
        if match:
            command = match.group(1).lower()
            if command in ['ping', 'traceroute', 'gtraceroute', 'info', 'test', 'qsl',
                           'distance', 'odleglosc', 'stats',
                           'weather', 'pogoda', 'wx', 'meteo', 'wetter', 'météo', 'tiempo', 'tempo']:
                return True
            if command == 'help' and self._help_triggered(text, clean):
                return True

        return False

    def get_node_info(self, node_id: str) -> Dict:
        """Get detailed information about a node"""
        if not self.meshtastic_handler or not self.meshtastic_handler.interface:
            return {}
            
        interface = self.meshtastic_handler.interface
        node_info = {}
        
        # Normalize the input node_id
        node_id = node_id.lower().lstrip('!')
        
        # Try to find node in interface
        for node_num, info in interface.nodes.items():
            # Convert node_num to string and normalize
            if isinstance(node_num, int):
                node_id_str = f"{node_num:x}"
            else:
                node_id_str = str(node_num).lower().lstrip('!')
            
            # Debug print
            # Compare normalized node IDs
            
            if node_id_str == node_id:
                # Get user info with fallbacks
                user_info = info.get('user', {})
                long_name = user_info.get('longName', 'Unknown')
                short_name = user_info.get('shortName', 'UNK')
                
                # Get connection info
                connection_type = 'mqtt' if info.get('connectionType') == 'tcp' else 'radio'
                gateway = info.get('gateway', 'N/A')
                
                # Get signal info with fallbacks
                rssi = info.get('rssi')
                snr = info.get('snr')
                if rssi is None and 'lastPacketRssi' in info:
                    rssi = info['lastPacketRssi']
                if snr is None and 'lastPacketSnr' in info:
                    snr = info['lastPacketSnr']

                hops_away = info.get('hopsAway', None)

                # interface.nodes['hopsAway'] is only updated from NodeInfo packets,
                # not from text messages. Fall back to the most recent signal_history row.
                if hops_away is None or rssi is None or snr is None:
                    sig = node_db.get_latest_signal(node_id_str)
                    if sig:
                        if hops_away is None:
                            hops_away = sig.get('hops_away')
                        if rssi is None:
                            rssi = sig.get('rssi')
                        if snr is None:
                            snr = sig.get('snr')

                # Get timing info
                last_heard = info.get('lastHeard', time.time())
                uptime = self._format_uptime(info.get('uptime', 0))
                
                # Get battery info — batteryLevel is already 0-100 integer in Meshtastic
                battery_level = info.get('batteryLevel', None)
                if battery_level is not None:
                    battery_level = int(battery_level)
                
                # Get position from DB as fallback or from info if available
                lat = None
                lon = None

                pos_hist = node_db.get_position_history(node_id_str, limit=1)
                if pos_hist:
                    lat = pos_hist[-1].get('lat')
                    lon = pos_hist[-1].get('lon')

                # Interface position — handle both float (latitude) and int (latitudeI × 1e7)
                if 'position' in info:
                    pos = info['position']
                    raw_lat = pos.get('latitude') or (pos.get('latitudeI', 0) / 1e7 if pos.get('latitudeI') else None)
                    raw_lon = pos.get('longitude') or (pos.get('longitudeI', 0) / 1e7 if pos.get('longitudeI') else None)
                    if raw_lat and raw_lon and not (raw_lat == 0.0 and raw_lon == 0.0):
                        lat, lon = raw_lat, raw_lon

                node_info = {
                    'node_id': node_id_str,  # Use the normalized node_id_str
                    'long_name': long_name,
                    'short_name': short_name,
                    'hops_away': hops_away,
                    'rssi': rssi,
                    'snr': snr,
                    'last_heard': last_heard,
                    'battery_level': battery_level,
                    'connection_type': connection_type,
                    'uptime': uptime,
                    'gateway': gateway,
                    'lat': lat,
                    'lon': lon
                }
                pass  # node found
                break
        
        if not node_info:
            pass  # node not found
        
        return node_info

    def _get_own_position(self):
        """Get bot's own current position — tries local node first, then node_db."""
        if not self.meshtastic_handler or not self.meshtastic_handler.interface:
            return None, None
        try:
            node = self.meshtastic_handler.interface.getNode('^local')
            pos  = getattr(node, 'position', None) or {}
            lat  = pos.get('latitude')  or pos.get('lat')
            lon  = pos.get('longitude') or pos.get('lon')
            if lat and lon and not (lat == 0.0 and lon == 0.0):
                return lat, lon
        except Exception:
            pass
        # Fallback: node_db position history for own node
        if self.meshtastic_handler.node_id:
            bot_id = f"{self.meshtastic_handler.node_id:x}"
            hist = node_db.get_position_history(bot_id, limit=1)
            if hist:
                return hist[-1].get('lat'), hist[-1].get('lon')
        return None, None

    def _get_distance_str(self, target_lat: float, target_lon: float) -> str:
        """Helper to format distance from bot to target"""
        if target_lat is None or target_lon is None:
            return ""
        bot_lat, bot_lon = self._get_own_position()
        if bot_lat is not None and bot_lon is not None:
            dist = self._get_distance(bot_lat, bot_lon, target_lat, target_lon)
            return f"• Dist: {dist:.1f}km\n"
        return ""

    def format_status_response(self, command: str, node_info: Dict) -> str:
        """Format a professional status response"""
        status = "OK" if node_info["hops_away"] is not None else "UNK"
        rssi_str = f"{node_info['rssi']}dBm" if node_info['rssi'] is not None else "N/A"
        snr_str = f"{node_info['snr']}dB" if node_info['snr'] is not None else "N/A"
        hops_str = f"{node_info['hops_away']}h" if node_info['hops_away'] is not None else "unk"
        mqtt_str = "MQTT" if node_info['connection_type'] == 'mqtt' else "LoRa"
        
        dist_str = self._get_distance_str(node_info.get('lat'), node_info.get('lon'))

        response = f"[{command.upper()}] !{node_info['node_id']}\n"
        response += f"• Stat: {status}\n"
        response += f"• Sig: {rssi_str}/{snr_str}\n"
        response += f"• Hops: {hops_str}\n"
        if dist_str:
            response += dist_str
        response += f"• Conn: {mqtt_str}\n"
        response += f"• Last: {self._format_last_heard(node_info['last_heard'])}"
        
        return response

    def format_ping_response(self, node_info: dict, is_mqtt: bool = False) -> str:
        """Format ping response with detailed information"""
        node_id   = node_info.get('node_id', 'unknown')
        name      = node_info.get('long_name') or node_info.get('short_name') or f'!{node_id}'
        rssi      = node_info.get('rssi')
        snr       = node_info.get('snr')
        last_heard = node_info.get('last_heard', 0)
        battery   = node_info.get('battery_level')

        rssi_str    = f"{rssi}dBm" if rssi is not None else "N/A"
        snr_str     = f"{snr}dB"   if snr  is not None else "N/A"
        battery_str = f"{battery}%" if battery is not None else "N/A"

        time_since = int(time.time() - last_heard) if last_heard else 0
        last_seen  = f"{time_since}s" if time_since < 60 else f"{time_since // 60}m"

        hops_away = node_info.get('hops_away')
        if hops_away is None:
            hops_str = "N/A"
        elif hops_away == 0:
            hops_str = "0 (direct)"
        else:
            hops_str = str(hops_away)

        dist_str = self._get_distance_str(node_info.get('lat'), node_info.get('lon'))
        dist_line = dist_str.strip() if dist_str else "• Dist: N/A (no GPS)"

        tag = 'PONG (MQTT)' if is_mqtt else 'PONG'
        response  = f"[{tag}] {name} !{node_id}\n"
        response += f"• Hops: {hops_str}\n"
        response += f"• Sig:  {rssi_str}/{snr_str}\n"
        response += f"• Bat:  {battery_str}\n"
        response += f"• Last: {last_seen} ago\n"
        response += dist_line

        return response

    def format_traceroute_response(self, path_info: dict, is_mqtt: bool = False) -> str:
        """Format traceroute response with detailed path information"""
        target_id  = path_info.get('target_id', 'unknown')
        hops       = path_info.get('hops', [])
        total_hops = len(hops) - 1 if hops else 0

        target_info = self.get_node_info(target_id)
        dist_str = self._get_distance_str(
            target_info.get('lat') if target_info else None,
            target_info.get('lon') if target_info else None,
        )
        dist_line = dist_str.strip() if dist_str else "• Dist: N/A"

        if is_mqtt:
            response  = f"[TRACE] !{target_id} (MQTT)\n"
            response += dist_line
            return response

        path_lines = []
        for i, hop in enumerate(hops):
            node_id   = hop.get('node_id', 'unknown')
            node_name = hop.get('node_name', 'Unknown')
            rssi = hop.get('rssi')
            snr  = hop.get('snr')

            if rssi not in (None, 'N/A') and snr not in (None, 'N/A'):
                sig_str = f"[{rssi}dBm/{snr}dB]"
            elif snr not in (None, 'N/A'):
                sig_str = f"[{snr}dB]"
            else:
                sig_str = ""

            display_name = node_name[:8] if node_name != 'Unknown' else ''
            node_label   = f"!{node_id}" + (f"({display_name})" if display_name else "")

            path_lines.append(f"{'↳' if i > 0 else ''}{node_label}{sig_str}")

        response  = f"[TRACE] !{target_id}\n"
        response += "\n".join(path_lines) + "\n"
        response += f"• Hops: {total_hops}\n"
        response += dist_line
        return response

    def _find_node_by_name(self, name: str) -> Optional[str]:
        """Find a node ID by its name (long or short)"""
        if not self.meshtastic_handler or not self.meshtastic_handler.interface:
            return None
            
        interface = self.meshtastic_handler.interface
        name = name.lower().strip()
        
        for node_num, info in interface.nodes.items():
            if 'user' in info:
                user_info = info['user']
                long_name = user_info.get('longName', '').lower()
                short_name = user_info.get('shortName', '').lower()
                
                if name in long_name or name in short_name:
                    return f"{node_num:x}" if isinstance(node_num, int) else str(node_num)
        
        return None

    def _handle_ping_qsl(self, sender_id: str, sender_name: str, channel_id: int, is_dm: bool) -> dict:
        node_info = self.get_node_info(sender_id)
        if not node_info:
            node_info = {
                'node_id': sender_id,
                'long_name': sender_name,
                'short_name': sender_name[:3].upper() if len(sender_name) >= 3 else 'UNK',
                'hops_away': None,
                'rssi': None,
                'snr': None,
                'last_heard': time.time(),
                'battery_level': None,
                'connection_type': 'radio',
                'uptime': 'N/A',
                'gateway': 'N/A'
            }
        is_mqtt = node_info.get('connection_type') == 'mqtt'
        response_text = self.format_ping_response(node_info, is_mqtt)
        return {
            'response': response_text,
            'channel_id': channel_id,
            'is_channel_message': not is_dm
        }

    def _handle_info_test(self, command: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool) -> dict:
        node_info = self.get_node_info(sender_id)
        if not node_info:
            node_info = {
                'node_id': sender_id,
                'long_name': sender_name,
                'short_name': sender_name[:3].upper() if len(sender_name) >= 3 else 'UNK',
                'hops_away': None,
                'rssi': None,
                'snr': None,
                'last_heard': time.time(),
                'battery_level': None,
                'connection_type': 'radio',
                'uptime': 'N/A',
                'gateway': 'N/A'
            }
        response_text = self.format_status_response(command, node_info)
        return {
            'response': response_text,
            'channel_id': channel_id,
            'is_channel_message': not is_dm
        }

    def _handle_distance(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool) -> dict:
        if not args:
            target_id = sender_id
        else:
            target = args.strip().lstrip('!')
            if not target:
                return {
                    'response': f"[{self.bot_name}] Invalid target format.",
                    'channel_id': channel_id,
                    'is_channel_message': not is_dm
                }
            target_id = target
            if not re.match(r'^[0-9a-f]+$', target.lower()):
                target_id = self._find_node_by_name(target)
                if not target_id:
                    return {
                        'response': f"[{self.bot_name}] Could not find a node matching '{target}'",
                        'channel_id': channel_id,
                        'is_channel_message': not is_dm
                    }

        target_info = self.get_node_info(target_id)
        if not target_info:
            return {
                'response': f"[{self.bot_name}] Node !{target_id} not found",
                'channel_id': channel_id,
                'is_channel_message': not is_dm
            }

        target_lat = target_info.get('lat')
        target_lon = target_info.get('lon')

        if target_lat is None or target_lon is None:
            return {
                'response': f"[{self.bot_name}] Node !{target_info.get('node_id', target_id)} does not have GPS coordinates available.",
                'channel_id': channel_id,
                'is_channel_message': not is_dm
            }

        dist_str = self._get_distance_str(target_lat, target_lon)

        if dist_str:
            response = f"[DISTANCE] !{target_info.get('node_id', target_id)}\n{dist_str.strip()}"
        else:
            response = f"[{self.bot_name}] Could not calculate distance. Ensure my own GPS coordinates are available."

        return {
            'response': response,
            'channel_id': channel_id,
            'is_channel_message': not is_dm
        }

    def _handle_traceroute(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool) -> dict:
        if not args:
            target_id = sender_id
        else:
            target = args.strip().lstrip('!')
            if not target:
                return {
                    'response': f"{self.bot_name}: Invalid target format. Please use !1234abcd, 1234abcd, or a node name",
                    'channel_id': channel_id,
                    'is_channel_message': not is_dm
                }
            target_id = target
            if not re.match(r'^[0-9a-f]+$', target.lower()):
                target_id = self._find_node_by_name(target)
                if not target_id:
                    return {
                        'response': f"{self.bot_name}: Could not find a node matching '{target}'",
                        'channel_id': channel_id,
                        'is_channel_message': not is_dm
                    }

        if target_id in self.active_traceroutes:
            return {
                'response': f"{self.bot_name}: Traceroute already in progress for this node",
                'channel_id': channel_id,
                'is_channel_message': not is_dm
            }

        target_info = self.get_node_info(target_id)
        if not target_info:
            return {
                'response': f"{self.bot_name}: Target node !{target_id} not found",
                'channel_id': channel_id,
                'is_channel_message': not is_dm
            }

        is_mqtt = target_info.get('connection_type') == 'mqtt'

        self.active_traceroutes[target_id] = {
            'start_time': time.time(),
            'target_info': target_info,
            'is_mqtt': is_mqtt,
            'requester_id': sender_id,
            'requester_name': sender_name,
            'channel_id': channel_id,
            'is_dm': is_dm,
        }

        # Initiate an actual traceroute over the mesh network
        if self.meshtastic_handler and hasattr(self.meshtastic_handler, 'send_traceroute') and not is_mqtt:
            self.meshtastic_handler.send_traceroute(target_id)

        self._start_traceroute_collection(target_id)

        if not args:
            response = f"{self.bot_name}: Starting traceroute to your node (!{target_id})..."
        else:
            response = f"{self.bot_name}: Starting traceroute to !{target_id}..."

        return {
            'response': response,
            'channel_id': channel_id,
            'is_channel_message': not is_dm
        }

    def _handle_weather(self, args: str, sender_id: str, sender_name: str,
                        channel_id: int, is_dm: bool) -> dict:
        """Weather map + local weather text. Generates map in background thread."""
        def _mk(msg):
            return {'response': msg, 'channel_id': channel_id, 'is_channel_message': not is_dm}

        city = args.strip() if args else None

        if not _HAS_REQUESTS:
            return _mk('Weather: requests library not available.')
        if not _HAS_WEATHER_MAP:
            return _mk('Weather: weather_map module not available (missing libs).')

        api_key = getattr(self.app_config, 'IMGBB_API_KEY', '') if self.app_config else ''
        if not api_key:
            return _mk('Weather: imgbb API key not configured (IMGBB_API_KEY).')

        # Check if the weather reply should go as DM
        reply_as_dm = bool(getattr(self.app_config, 'WEATHER_MAP_REPLY_AS_DM', False)) if self.app_config else False

        # Get requester node info for local weather
        requester_info = self.get_node_info(sender_id)
        requester_lat = requester_info.get('lat') if requester_info else None
        requester_lon = requester_info.get('lon') if requester_info else None

        def _generate():
            try:
                import stats_chart as _sc
                img_bytes = _wm.generate_weather_map(node_db, self.meshtastic_handler)
                url = None
                if img_bytes:
                    url = _sc.upload_imgbb(img_bytes, api_key)

                # Build local weather text
                local_txt = ''
                try:
                    from urllib.parse import quote_plus
                    if city:
                        wurl = f"https://wttr.in/{quote_plus(city)}?format=%C,+%t,+wind:%w,+hum:%h&lang=en"
                    elif requester_lat and requester_lon:
                        wurl = f"https://wttr.in/{requester_lat},{requester_lon}?format=%C,+%t,+wind:%w,+hum:%h&lang=en"
                    else:
                        wurl = "https://wttr.in/Aarau?format=%C,+%t,+wind:%w,+hum:%h&lang=en"
                    r = requests.get(wurl, timeout=8)
                    if r.status_code == 200:
                        local_txt = r.text.strip()
                except Exception:
                    local_txt = ''

                # Compose reply
                if url:
                    lines = [f'Weather Map: {url}']
                    if local_txt:
                        loc_label = city.capitalize() if city else (
                            requester_info.get('short_name') or requester_info.get('long_name')
                        ) if requester_info else 'Here'
                        lines.append(f'Local ({loc_label}): {local_txt}')
                    reply = '\n'.join(lines)
                else:
                    if local_txt:
                        loc_label = city.capitalize() if city else 'Here'
                        reply = f'Weather ({loc_label}): {local_txt}'
                    else:
                        reply = 'Weather: no map generated and no weather data available.'
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error('weather error: %s', exc, exc_info=True)
                reply = f'Weather: error — {exc}'

            # Enqueue result for the pubsub thread to send.
            # Direct send_message() from a daemon thread contends on Meshtastic's
            # unprotected self.queue and silently loses packets.
            send_as_dm = reply_as_dm or is_dm
            if not send_as_dm and self.private_reply_fn and self.private_reply_fn():
                send_as_dm = True
            dest = sender_id if send_as_dm else None
            ch   = None if send_as_dm else channel_id
            with self._pending_lock:
                self._pending_sends.append((reply, dest, ch, send_as_dm))

        threading.Thread(target=_generate, daemon=True, name='weather-gen').start()

        ack = 'Generating weather map...'
        return _mk(ack)

    def handle_command(self, text: str, sender_id: str, sender_name: str, channel_id: int = None, is_dm: bool = False) -> Optional[dict]:
        """Handle bot commands"""
        text = text.strip()
        text_lower = text.lower()

        # Normalize sender_id
        sender_id = sender_id.lower().lstrip('!')

        # --- Admin commands ---
        if text_lower.startswith("!admin"):
            return self._handle_admin(text, sender_id, sender_name, channel_id)

        # Normalize: strip !, backticks before matching
        clean = self._normalize_cmd(text)
        clean_lower = clean.lower()

        # Handle direct commands without bot prefix
        if clean_lower in ['ping', 'traceroute', 'gtraceroute', 'info', 'test', 'qsl',
                            'distance', 'odleglosc',
                            'weather', 'pogoda', 'wx', 'meteo', 'wetter', 'météo', 'tiempo', 'tempo',
                            'help']:
            command = clean_lower
            args = ""
        elif self._help_triggered(text, clean_lower):
            # "help marvin", "help MAR" etc.
            command = 'help'
            args = ""
        else:
            match = self.command_pattern.match(clean)
            if not match:
                return None
            command = match.group(1).lower()
            args = match.group(2) if match.group(2) else ""

        if command in ['ping', 'qsl']:
            return self._handle_ping_qsl(sender_id, sender_name, channel_id, is_dm)
        elif command in ['info', 'test']:
            return self._handle_info_test(command, sender_id, sender_name, channel_id, is_dm)
        elif command in ['traceroute', 'gtraceroute']:
            return self._handle_traceroute(args, sender_id, sender_name, channel_id, is_dm)
        elif command in ['distance', 'odleglosc']:
            return self._handle_distance(args, sender_id, sender_name, channel_id, is_dm)
        elif command in ['weather', 'pogoda', 'wx', 'meteo', 'wetter', 'météo', 'tiempo', 'tempo']:
            return self._handle_weather(args, sender_id, sender_name, channel_id, is_dm)
        elif command == 'stats':
            return self._handle_stats(sender_id, sender_name, channel_id, is_dm)
        elif command == 'help':
            return self._handle_help(channel_id, is_dm)

    def _handle_stats(self, sender_id: str, sender_name: str,
                      channel_id: int, is_dm: bool) -> dict:
        """Generate 4h stats image and upload to imgbb. Rate-limited 1x per 4h per user."""
        def _mk(msg):
            return {'response': msg, 'channel_id': channel_id, 'is_channel_message': not is_dm}

        if not _HAS_STATS:
            return _mk('Stats charts unavailable (missing libs).')

        api_key = getattr(self.app_config, 'IMGBB_API_KEY', '') if self.app_config else ''
        if not api_key:
            return _mk('Stats: imgbb API key not configured (IMGBB_API_KEY).')

        # Cooldown check
        rem = _sc.check_cooldown(sender_id)
        if rem is not None:
            h, s = divmod(rem, 3600)
            m    = s // 60
            wait = f'{h}h {m}m' if h else f'{m}m'
            return _mk(f'Stats on cooldown. Next in {wait}.')

        # Kick off generation in background thread — send "working" ack immediately,
        # then send the URL when ready via meshtastic_handler.
        def _generate():
            try:
                own_id = None
                if self.meshtastic_handler:
                    try:
                        num = self.meshtastic_handler.node_id
                        if num:
                            own_id = f'{num:x}'
                    except Exception:
                        pass

                img_bytes = _sc.generate_stats_image(node_db, hours=4.0, own_node_id=own_id)
                url = _sc.upload_imgbb(img_bytes, api_key)

                if url:
                    _sc.set_cooldown(sender_id)
                    reply = f'Stats (4h): {url}'
                else:
                    reply = 'Stats: upload failed. Try again later.'
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error('!stats error: %s', exc, exc_info=True)
                reply = f'Stats: generation error — {exc}'

            # Enqueue result for the pubsub thread to send (see weather comment).
            send_as_dm = is_dm
            if not send_as_dm and self.private_reply_fn and self.private_reply_fn():
                send_as_dm = True
            dest = sender_id if send_as_dm else None
            ch   = None if send_as_dm else channel_id
            with self._pending_lock:
                self._pending_sends.append((reply, dest, ch, send_as_dm))

        threading.Thread(target=_generate, daemon=True, name='stats-gen').start()

        ack = f'Generating stats (4h)... link coming shortly.'
        return _mk(ack)

    def _handle_help(self, channel_id: int, is_dm: bool) -> dict:
        lines = [
            f"[{self.bot_name}] Commands (! optional):",
            "ping/qsl     – signal report",
            "info/test    – node status",
            "traceroute [!id|name] – hop path",
            "distance [!id|name]   – dist to node",
            "wx/weather/meteo/wetter/météo/tiempo/tempo [city]  – weather map + local",
            "stats        – 4h chart image (1x/4h)",
            "AI: just write to me",
        ]
        response = "\n".join(lines)
        return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}

    def _drain_pending_sends(self):
        """Send all queued pending messages. MUST be called from the pubsub callback
        thread (or main thread) to avoid Meshtastic queue contention."""
        with self._pending_lock:
            if not self._pending_sends:
                return
            batch = self._pending_sends[:]
            self._pending_sends.clear()
        for reply, dest_id, ch_idx, as_dm in batch:
            try:
                if as_dm:
                    ok, reason = self.meshtastic_handler.send_message(
                        reply, destination_id_hex=dest_id, want_ack=False)
                else:
                    ok, reason = self.meshtastic_handler.send_message(
                        reply, channel_index=ch_idx, want_ack=False)
                if not ok:
                    import logging
                    logging.getLogger(__name__).error(
                        'pending send failed: %s', reason)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error(
                    'pending send error: %s', exc)

    def _start_traceroute_collection(self, target_id: str) -> None:
        """Start background traceroute collection"""
        def collect_traceroute():
            time.sleep(self.traceroute_timeout)
            if target_id in self.active_traceroutes:
                traceroute_data = self.active_traceroutes[target_id]
                path_info = self._get_traceroute_info(target_id)
                is_mqtt = traceroute_data['is_mqtt']
                response = self.format_traceroute_response(path_info, is_mqtt)
                
                # Send response back to the requester (not the target)
                is_dm      = traceroute_data.get('is_dm', False)
                channel_id = traceroute_data.get('channel_id') or 0
                req_id     = traceroute_data.get('requester_id')
                if self.meshtastic_handler and self.meshtastic_handler.is_connected:
                    if is_dm:
                        self.meshtastic_handler.send_message(
                            response, destination_id_hex=req_id
                        )
                    else:
                        self.meshtastic_handler.send_message(
                            response, channel_index=channel_id
                        )
                # Forward result to Matrix
                if self.matrix_forward_cb:
                    try:
                        self.matrix_forward_cb(
                            response, self.bot_name,
                            channel_index=0 if is_dm else channel_id,
                            is_dm=is_dm,
                            destination_id=req_id if is_dm else None,
                        )
                    except Exception:
                        pass
                # Clean up
                del self.active_traceroutes[target_id]
        
        # Start collection in a separate thread
        import threading
        thread = threading.Thread(target=collect_traceroute)
        thread.daemon = True
        thread.start()

    def _get_traceroute_info(self, target_id: str) -> dict:
        """Get traceroute information for a target node"""
        if not self.meshtastic_handler or not self.meshtastic_handler.interface:
            return {'target_id': target_id, 'hops': []}
            
        interface = self.meshtastic_handler.interface
        path_info = {
            'target_id': target_id,
            'target_name': 'Unknown',
            'hops': [],
            'latency': None
        }
        
        # Get target node info
        target_info = self.get_node_info(target_id)
        if target_info:
            path_info['target_name'] = target_info.get('long_name', 'Unknown')

        bot_node_id = f"{self.meshtastic_handler.node_id:x}" if self.meshtastic_handler.node_id else None

        # 1) Check node_db for a real traceroute
        recent_traces = node_db.get_traceroutes(bot_node_id, limit=20) if bot_node_id else []
        best_trace = None
        for tr in recent_traces:
            # We want a trace FROM bot TO target
            if tr.get('from_id') == bot_node_id and tr.get('to_id') == target_id:
                # Make sure it's somewhat recent (e.g. within 5 minutes of now)
                # Note: tr['ts'] might be from the past, we allow up to 300s window
                # Alternatively just pick the most recent one since limit=20 is ordered by ts DESC
                if time.time() - tr.get('ts', 0) < 300:
                    best_trace = tr
                    break

        if best_trace:
            # Reconstruct hops from the real trace
            # route format is usually just the intermediate node IDs
            route_ids = best_trace.get('route', [])
            snrs = best_trace.get('snr_towards', [])

            # Start with the bot itself
            path_info['hops'].append({
                'node_id': bot_node_id,
                'node_name': self.bot_name,
                'rssi': 'N/A',
                'snr': 'N/A'
            })

            # Add intermediate nodes
            for i, hop_id in enumerate(route_ids):
                hop_info = self.get_node_info(hop_id) or {}
                hop_name = hop_info.get('short_name') or hop_info.get('long_name') or 'Unknown'
                # get snr if available
                snr_val = snrs[i] if i < len(snrs) else 'N/A'
                path_info['hops'].append({
                    'node_id': hop_id,
                    'node_name': hop_name,
                    'rssi': 'N/A', # not reliably available in basic traceroute
                    'snr': snr_val
                })

            # Add the target node
            final_snr = snrs[-1] if len(snrs) > len(route_ids) else 'N/A'
            target_name = target_info.get('short_name') or target_info.get('long_name') or 'Unknown'
            path_info['hops'].append({
                'node_id': target_id,
                'node_name': target_name,
                'rssi': target_info.get('rssi', 'N/A'),
                'snr': final_snr
            })

            return path_info

        # 2) Fallback: Build path based on node's parent nodes
        current_id = target_id
        max_hops = 10  # Prevent infinite loops
        visited = set()
        
        while current_id and len(path_info['hops']) < max_hops:
            if current_id in visited:
                break
                
            visited.add(current_id)
            node_info = self.get_node_info(current_id)
            if node_info:
                path_info['hops'].insert(0, {
                    'node_id': current_id,
                    'node_name': node_info.get('short_name') or node_info.get('long_name') or 'Unknown',
                    'rssi': node_info.get('rssi', 'N/A'),
                    'snr': node_info.get('snr', 'N/A')
                })
                
                # Try to get parent node
                if interface.nodes:
                    for node_num, info in interface.nodes.items():
                        if str(node_num).lower() == current_id.lower():
                            parent_id = info.get('parentId')
                            if parent_id:
                                current_id = f"{parent_id:x}" if isinstance(parent_id, int) else str(parent_id)
                            else:
                                current_id = None
                            break
            else:
                break
        
        # Add bot node as the first hop if not already present
        if not path_info['hops'] or path_info['hops'][0]['node_id'] != bot_node_id:
            path_info['hops'].insert(0, {
                'node_id': bot_node_id,
                'node_name': self.bot_name,
                'rssi': 'N/A',
                'snr': 'N/A'
            })
        
        return path_info

    def _format_uptime(self, seconds: int) -> str:
        """Format uptime in seconds to a human-readable string"""
        if not seconds:
            return 'N/A'
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

    def _format_last_heard(self, last_heard: float) -> str:
        """Format last heard timestamp to a human-readable string"""
        if not last_heard:
            return "Never"
        time_since = int(time.time() - last_heard)
        if time_since < 60:
            return f"{time_since} seconds ago"
        elif time_since < 3600:
            return f"{time_since // 60} minutes ago"
        else:
            return f"{time_since // 3600} hours ago"

    # ------------------------------------------------------------------
    # Admin / self-management commands  (!admin <cmd> [args])
    # ------------------------------------------------------------------

    def _handle_admin(self, text: str, sender_id: str, sender_name: str, channel_id: int) -> Optional[dict]:
        """Process !admin commands. Only authorized nodes may use these."""
        if self.admin_node_ids and sender_id not in self.admin_node_ids:
            return {
                'response': f"[ADMIN] {self.bot_name}: Access denied. You are not authorised for admin commands.",
                'channel_id': channel_id,
                'is_channel_message': False,
            }

        match = self.admin_pattern.match(text)
        if not match:
            return {
                'response': f"[ADMIN] {self.bot_name}: Usage: !admin <status|persona|switch_ai|nodes|channels|reboot>",
                'channel_id': channel_id,
                'is_channel_message': False,
            }

        cmd = match.group(1).lower()
        args = match.group(2).strip() if match.group(2) else ""

        if cmd == "status":
            return self._admin_status(channel_id)
        elif cmd == "nodes":
            return self._admin_nodes(channel_id)
        elif cmd == "channels":
            return self._admin_channels(channel_id)
        elif cmd == "persona" and args:
            return self._admin_set_persona(args, channel_id)
        elif cmd == "switch_ai" and args:
            return self._admin_switch_ai(args, channel_id)
        else:
            return {
                'response': f"[ADMIN] {self.bot_name}: Unknown admin command '{cmd}'. "
                            f"Available: status, persona <text>, switch_ai <openai|gemini>, nodes, channels",
                'channel_id': channel_id,
                'is_channel_message': False,
            }

    def _admin_status(self, channel_id):
        handler = self.meshtastic_handler
        connected = handler.is_connected if handler else False
        node_id = f"!{handler.node_id:x}" if handler and handler.node_id else "N/A"
        node_count = 0
        if handler and handler.interface and hasattr(handler.interface, 'nodes'):
            node_count = len(handler.interface.nodes or {})

        ai_service = getattr(self.app_config, 'DEFAULT_AI_SERVICE', 'N/A') if self.app_config else 'N/A'

        # Get state machine status
        conn_status = handler.get_connection_status() if handler and hasattr(handler, 'get_connection_status') else {}
        state_name = conn_status.get('state', 'N/A')
        retries = conn_status.get('retry_count', 0)

        lines = [
            f"[ADMIN] {self.bot_name} System Status:",
            f"• Node: {node_id}",
            f"• State: {state_name}",
            f"• Connected: {'Yes' if connected else 'No'}",
            f"• Retries: {retries}",
            f"• Nodes seen: {node_count}",
            f"• AI service: {ai_service}",
            f"• Time: {datetime.now().strftime('%H:%M:%S')}",
        ]
        return {
            'response': "\n".join(lines),
            'channel_id': channel_id,
            'is_channel_message': False,
        }

    def _admin_nodes(self, channel_id):
        if not self.meshtastic_handler or not self.meshtastic_handler.interface:
            return {'response': f"[ADMIN] {self.bot_name}: No interface available.", 'channel_id': channel_id, 'is_channel_message': False}

        interface = self.meshtastic_handler.interface
        if not hasattr(interface, 'nodes') or not interface.nodes:
            return {'response': f"[ADMIN] {self.bot_name}: No nodes found.", 'channel_id': channel_id, 'is_channel_message': False}

        lines = [f"[ADMIN] {self.bot_name}: {len(interface.nodes)} node(s):"]
        for node_num, info in list(interface.nodes.items())[:15]:  # cap at 15 to fit message
            nid = f"{node_num:x}" if isinstance(node_num, int) else str(node_num)
            user = info.get('user', {})
            name = user.get('shortName') or user.get('longName') or 'UNK'
            lines.append(f"• !{nid} {name}")

        return {'response': "\n".join(lines), 'channel_id': channel_id, 'is_channel_message': False}

    def _admin_channels(self, channel_id):
        channels = self.meshtastic_handler.list_channels() if self.meshtastic_handler else []
        if not channels:
            return {'response': f"[ADMIN] {self.bot_name}: No channel info available.", 'channel_id': channel_id, 'is_channel_message': False}

        lines = [f"[ADMIN] {self.bot_name}: Channels:"]
        for ch in channels:
            lines.append(f"• {ch['index']}: {ch['name']} ({ch['role']})")

        return {'response': "\n".join(lines), 'channel_id': channel_id, 'is_channel_message': False}

    def _admin_set_persona(self, persona_text, channel_id):
        # Store on config so AI bridge picks it up
        if self.app_config:
            self.app_config.DEFAULT_PERSONA = persona_text
        return {
            'response': f"[ADMIN] {self.bot_name}: Persona updated ({len(persona_text)} chars).",
            'channel_id': channel_id,
            'is_channel_message': False,
        }

    def _admin_switch_ai(self, service, channel_id):
        service = service.lower().strip()
        if service not in ("openai", "gemini"):
            return {
                'response': f"[ADMIN] {self.bot_name}: Unknown AI service '{service}'. Use openai or gemini.",
                'channel_id': channel_id,
                'is_channel_message': False,
            }
        if self.app_config:
            self.app_config.DEFAULT_AI_SERVICE = service
        return {
            'response': f"[ADMIN] {self.bot_name}: AI service switched to {service}.",
            'channel_id': channel_id,
            'is_channel_message': False,
        }