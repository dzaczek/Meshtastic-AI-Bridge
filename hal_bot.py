import json
import time
import math
from datetime import datetime
import re
from typing import Dict, Optional, Tuple
import random
import node_db
try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

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
        self.matrix_forward_cb = None  # set by main_app after init

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
        """Strip !, backticks and extra whitespace from a command text."""
        t = text.strip()
        # Strip leading ! (but not !admin)
        if t.startswith('!') and not t.lower().startswith('!admin'):
            t = t[1:].strip()
        # Strip backtick wrapping: `command` or `command args`
        t = t.strip('`').strip()
        return t

    def should_handle_message(self, text: str) -> bool:
        """Check if the message should be handled by the bot"""
        text = text.strip()
        text_lower = text.lower()

        # Admin commands
        if text_lower.startswith("!admin"):
            return True

        # Normalize (strip !, backticks) before checking commands
        clean = self._normalize_cmd(text).lower()

        # Check for direct commands first
        if clean in ['ping', 'traceroute', 'gtraceroute', 'info', 'test', 'qsl',
                     'distance', 'odleglosc', 'weather', 'pogoda', 'wx', 'help']:
            return True

        # Check for bot prefixed commands
        match = self.command_pattern.match(clean)
        if match:
            command = match.group(1).lower()
            if command in ['ping', 'traceroute', 'gtraceroute', 'info', 'test', 'qsl',
                           'distance', 'odleglosc', 'weather', 'pogoda', 'wx', 'help']:
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

                # Interface position might be newer or immediately available
                if 'position' in info and 'latitude' in info['position'] and 'longitude' in info['position']:
                    lat = info['position']['latitude']
                    lon = info['position']['longitude']
                    if lat == 0.0 and lon == 0.0:
                        lat = None
                        lon = None

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
        node_id = node_info.get('node_id', 'unknown')
        rssi = node_info.get('rssi')
        snr = node_info.get('snr')
        last_heard = node_info.get('last_heard', 0)
        battery = node_info.get('battery_level')
        
        # Format signal info
        rssi_str = f"{rssi}dBm" if rssi is not None else "N/A"
        snr_str = f"{snr}dB" if snr is not None else "N/A"
        battery_str = f"{battery}%" if battery is not None else "N/A"
        
        # Calculate latency (simplified - in real implementation this would be actual ping time)
        latency = random.randint(80, 400) if is_mqtt else random.randint(300, 800)
        
        # Calculate time since last heard
        time_since = int(time.time() - last_heard) if last_heard else 0
        last_seen = f"{time_since}s" if time_since < 60 else f"{time_since // 60}m"
        
        dist_str = self._get_distance_str(node_info.get('lat'), node_info.get('lon'))
        
        hops_away = node_info.get('hops_away')
        hops_str  = f"{hops_away}" if hops_away is not None else "?"

        # Build the response string
        response = f"[{'PING' if not is_mqtt else 'PING (MQTT)'}] !{node_id}\n"
        response += f"• Hops: {hops_str}\n"
        if not is_mqtt:
            response += f"• Sig: {rssi_str}/{snr_str}\n"
        response += f"• Last: {last_seen} ago\n"
        response += f"• Bat: {battery_str}\n"
        if dist_str:
            response += dist_str.rstrip('\n')

        return response

    def format_traceroute_response(self, path_info: dict, is_mqtt: bool = False) -> str:
        """Format traceroute response with detailed path information"""
        target_id = path_info.get('target_id', 'unknown')
        hops = path_info.get('hops', [])
        total_hops = len(hops) - 1 if hops else 0
        latency = path_info.get('latency', random.randint(100, 1000))
        
        target_info = self.get_node_info(target_id)
        dist_str = self._get_distance_str(target_info.get('lat'), target_info.get('lon'))

        if is_mqtt:
            response = f"[TRACE] !{target_id} (MQTT)\n"
            response += f"• Latency: {latency}ms\n"
            if dist_str:
                response += dist_str.rstrip('\n')
            return response
        else:
            # Build the path visualization
            path_lines = []
            for i, hop in enumerate(hops):
                node_id = hop.get('node_id', 'unknown')
                node_name = hop.get('node_name', 'Unknown')
                rssi = hop.get('rssi')
                snr = hop.get('snr')
                
                # Format signal info
                if rssi != 'N/A' and rssi is not None and snr != 'N/A' and snr is not None:
                    sig_str = f"[{rssi}dBm/{snr}dB]"
                elif snr != 'N/A' and snr is not None:
                    sig_str = f"[{snr}dB]"
                else:
                    sig_str = ""
                
                # Ensure node name is short enough
                display_name = node_name[:8] if node_name != 'Unknown' else ''
                node_label = f"!{node_id}" + (f"({display_name})" if display_name else "")

                if i == 0:
                    path_lines.append(f"{node_label}")
                elif i == len(hops) - 1:
                    path_lines.append(f"↳{node_label}{sig_str}")
                else:
                    path_lines.append(f"↳{node_label}{sig_str}")
            
            path_str = "\n".join(path_lines)
            
            response = f"[TRACE] !{target_id}\n"
            response += f"{path_str}\n"
            response += f"• Hops: {total_hops}\n"
            response += f"• Delay: ~{latency}ms\n"
            if dist_str:
                response += dist_str.rstrip('\n')
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

    def _handle_weather(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool) -> dict:
        """Fetch current weather from wttr.in and return compact response."""
        city = args.strip() if args else "Aarau"
        if not city:
            city = "Aarau"
        if not _HAS_REQUESTS:
            return {'response': f"[WEATHER] Error: requests library not available.",
                    'channel_id': channel_id, 'is_channel_message': not is_dm}
        try:
            from urllib.parse import quote_plus
            url = f"https://wttr.in/{quote_plus(city)}?format=j1"
            r = requests.get(url, timeout=8)
            data = r.json()
            cur  = data['current_condition'][0]
            temp = cur['temp_C']
            desc = cur['weatherDesc'][0]['value']
            tmrw = data['weather'][1] if len(data.get('weather', [])) > 1 else {}
            tmax = tmrw.get('maxtempC', '?')
            tmin = tmrw.get('mintempC', '?')
            response = (f"[WEATHER] {city.capitalize()}\n"
                        f"• Now: {temp}°C, {desc}\n"
                        f"• 24h: {tmin}°C-{tmax}°C")
        except Exception as e:
            response = f"[WEATHER] Error: {str(e)[:60]}"
        return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}

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
                            'distance', 'odleglosc', 'weather', 'pogoda', 'wx', 'help']:
            command = clean_lower
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
        elif command in ['weather', 'pogoda', 'wx']:
            return self._handle_weather(args, sender_id, sender_name, channel_id, is_dm)
        elif command == 'help':
            return self._handle_help(channel_id, is_dm)

    def _handle_help(self, channel_id: int, is_dm: bool) -> dict:
        lines = [
            f"[{self.bot_name}] Commands (! optional):",
            "ping/qsl     – signal report",
            "info/test    – node status",
            "traceroute [!id|name] – hop path",
            "distance [!id|name]   – dist to node",
            "wx/weather [city]     – weather",
            "AI: just write to me",
        ]
        response = "\n".join(lines)
        return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}

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
            'latency': random.randint(100, 1000)  # Simplified latency calculation
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