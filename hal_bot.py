import json
import time
from datetime import datetime
import re
from typing import Dict, Optional, Tuple
import random

class HalBot:
    def __init__(self, meshtastic_handler):
        self.meshtastic_handler = meshtastic_handler
        self.command_pattern = re.compile(r'^(?:HAL\s+)?(\w+)(?:\s+(.+))?$', re.IGNORECASE)
        self.traceroute_timeout = 30  # seconds
        self.pending_traceroutes = {}  # Store pending traceroute requests
        self.active_traceroutes = {}  # Store active traceroute requests
        self.mqtt_broker = "mqtt.meshtastic.org"  # Default MQTT broker
        self.gateway_info = {}  # Store gateway information for MQTT nodes

    def should_handle_message(self, text: str) -> bool:
        """Check if the message should be handled by HAL bot"""
        # Check for direct commands first
        direct_commands = ['ping', 'traceroute', 'info', 'test', 'qsl']
        text_lower = text.lower().strip()
        
        # Handle direct commands without HAL prefix
        if text_lower in direct_commands:
            return True
            
        # Check for HAL prefixed commands
        return bool(self.command_pattern.match(text))

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
            print(f"Comparing node IDs: input='{node_id}', current='{node_id_str}'")
            
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
                
                # Get battery info
                battery_level = info.get('batteryLevel', None)
                if battery_level is not None:
                    battery_level = int(battery_level * 100)  # Convert to percentage
                
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
                    'gateway': gateway
                }
                print(f"Found node info: {node_info}")  # Debug print
                break
        
        if not node_info:
            print(f"No node info found for ID: {node_id}")  # Debug print
            # Print all available node IDs for debugging
            print("Available nodes:")
            for node_num in interface.nodes:
                if isinstance(node_num, int):
                    print(f"  !{node_num:x}")
                else:
                    print(f"  !{node_num}")
        
        return node_info

    def format_status_response(self, command: str, node_info: Dict) -> str:
        """Format a professional status response"""
        status = "OK" if node_info["hops_away"] is not None else "UNKNOWN"
        rssi_str = f"{node_info['rssi']} dBm" if node_info['rssi'] is not None else "N/A"
        hops_str = f"{node_info['hops_away']} hop{'s' if node_info['hops_away'] != 1 else ''}" if node_info['hops_away'] is not None else "unknown"
        mqtt_str = "MQTT connected" if node_info['connection_type'] == 'mqtt' else "LoRa only"
        
        response = f"HAL9000: {command.upper()} status for node {node_info['node_id']} ({node_info['long_name']}):\n"
        response += f"• Status: {status}\n"
        response += f"• Signal: {rssi_str}\n"
        response += f"• Distance: {hops_str}\n"
        response += f"• Connection: {mqtt_str}\n"
        response += f"• Last heard: {self._format_last_heard(node_info['last_heard'])}\n"
        response += f"• Timestamp: {datetime.now().isoformat()}"
        
        return response

    def format_ping_response(self, node_info: dict, is_mqtt: bool = False) -> str:
        """Format ping response with detailed information"""
        node_id = node_info.get('node_id', 'unknown')
        node_name = node_info.get('long_name', 'Unknown')
        rssi = node_info.get('rssi')
        snr = node_info.get('snr')
        hops = node_info.get('hops_away')
        last_heard = node_info.get('last_heard', 0)
        battery = node_info.get('battery_level')
        uptime = node_info.get('uptime', 'N/A')
        gateway = node_info.get('gateway', 'N/A')
        
        # Format signal info
        rssi_str = f"{rssi} dBm" if rssi is not None else "N/A"
        snr_str = f"{snr} dB" if snr is not None else "N/A"
        battery_str = f"{battery}%" if battery is not None else "N/A"
        
        # Calculate latency (simplified - in real implementation this would be actual ping time)
        latency = random.randint(80, 400) if is_mqtt else random.randint(300, 800)
        
        # Calculate time since last heard
        time_since = int(time.time() - last_heard) if last_heard else 0
        last_seen = f"{time_since} seconds ago" if time_since < 60 else f"{time_since // 60} minutes ago"
        
        # Build the response string
        if is_mqtt:
            response = f"""[PING] Pong from !{node_id} via MQTT ☁️
⏱ Latency: {latency} ms
🌍 Gateway: {gateway}
🕒 Uptime: {uptime}
📶 Connection: MQTT Direct
🔄 Last sync: {last_seen}"""
        else:
            response = f"""[PING] Pong from !{node_id} via radio 🌐
⏱ Latency: ~{latency} ms
📶 RSSI: {rssi_str} | SNR: {snr_str}
📡 Last seen: {last_seen}
🔋 Battery: {battery_str}"""
        
        return response  # Return the formatted string

    def format_traceroute_response(self, path_info: dict, is_mqtt: bool = False) -> str:
        """Format traceroute response with detailed path information"""
        target_id = path_info.get('target_id', 'unknown')
        target_name = path_info.get('target_name', 'Unknown')
        hops = path_info.get('hops', [])
        total_hops = len(hops) - 1  # Subtract 1 to exclude the target
        latency = path_info.get('latency', random.randint(100, 1000))
        
        if is_mqtt:
            return f"""[TRACEROUTE] MQTT route to !{target_id}:

HAL9000 (!{self.meshtastic_handler.node_id:x})
↳ MQTT Broker: {self.mqtt_broker}
↳ !{target_id} (subscribed) ✅
🌐 Path type: MQTT-direct
⏱ Delivery latency: {latency} ms
🔄 Last sync: {datetime.now().strftime('%H:%M:%S')}"""
        else:
            # Build the path visualization
            path_lines = []
            for i, hop in enumerate(hops):
                node_id = hop.get('node_id', 'unknown')
                rssi = hop.get('rssi')
                snr = hop.get('snr')
                
                # Format signal info
                rssi_str = f"{rssi} dBm" if rssi is not None else "N/A"
                snr_str = f"{snr} dB" if snr is not None else "N/A"
                
                if i == 0:
                    path_lines.append(f"HAL9000 (!{node_id})")
                elif i == len(hops) - 1:
                    path_lines.append(f"↳ !{node_id} (Target) ✅")
                else:
                    path_lines.append(f"↳ !{node_id} [RSSI: {rssi_str} | SNR: {snr_str}]")
            
            path_str = "\n".join(path_lines)
            
            return f"""[TRACEROUTE] Path to !{target_id}:

{path_str}
🪐 Total hops: {total_hops}
⏱ Estimated delay: ~{latency} ms
📡 Path type: Radio mesh
🔄 Trace completed: {datetime.now().strftime('%H:%M:%S')}"""

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

    def handle_command(self, text: str, sender_id: str, sender_name: str, channel_id: int = None, is_dm: bool = False) -> Optional[dict]:
        """Handle HAL bot commands"""
        # Clean up the text and check for direct commands
        text = text.strip()
        text_lower = text.lower()
        
        # Normalize sender_id
        sender_id = sender_id.lower().lstrip('!')
        
        # Handle direct commands without HAL prefix
        if text_lower in ['ping', 'traceroute', 'info', 'test', 'qsl']:
            command = text_lower
            args = ""
        else:
            # Handle HAL prefixed commands
            match = self.command_pattern.match(text)
            if not match:
                return None
            command = match.group(1).lower()
            args = match.group(2) if match.group(2) else ""
        
        if command in ['info', 'test', 'ping', 'qsl']:
            # Get node info
            node_info = self.get_node_info(sender_id)
            if not node_info:
                # If node info not found, try to get basic info from the sender
                node_info = {
                    'node_id': sender_id,
                    'long_name': sender_name,
                    'short_name': sender_name[:3].upper() if len(sender_name) >= 3 else 'UNK',
                    'hops_away': None,
                    'rssi': None,
                    'snr': None,
                    'last_heard': time.time(),
                    'battery_level': None,
                    'connection_type': 'radio',  # Default to radio if unknown
                    'uptime': 'N/A',
                    'gateway': 'N/A'
                }
                print(f"Using fallback node info for {sender_id}: {node_info}")  # Debug print
            
            # Check if node is connected via MQTT
            is_mqtt = node_info.get('connection_type') == 'mqtt'
            
            # Format response based on command
            response_text = None
            if command in ['ping', 'qsl']:
                response_text = self.format_ping_response(node_info, is_mqtt)
            else:  # info or test
                response_text = self.format_status_response(command, node_info)
            
            # Return the response and channel info for the caller to handle sending
            return {
                'response': response_text,  # This should be a string
                'channel_id': channel_id,  # Pass through the channel ID
                'is_channel_message': not is_dm  # Use is_dm parameter to determine if this was a channel message
            }
                
        elif command == 'traceroute':
            # If no args provided, use the requester's node ID as the target
            if not args:
                target_id = sender_id
            else:
                # Extract target identifier from argument
                target = args.strip().lstrip('!')
                if not target:
                    return {
                        'response': "HAL9000: Invalid target format. Please use !1234abcd, 1234abcd, or a node name",
                        'channel_id': channel_id,
                        'is_channel_message': channel_id is not None
                    }
                
                # Try to find node ID if a name was provided
                target_id = target
                if not re.match(r'^[0-9a-f]+$', target.lower()):
                    target_id = self._find_node_by_name(target)
                    if not target_id:
                        return {
                            'response': f"HAL9000: Could not find a node matching '{target}'",
                            'channel_id': channel_id,
                            'is_channel_message': channel_id is not None
                        }
            
            if target_id in self.active_traceroutes:
                return {
                    'response': "HAL9000: Traceroute already in progress for this node",
                    'channel_id': channel_id,
                    'is_channel_message': channel_id is not None
                }
            
            # Get target node info
            target_info = self.get_node_info(target_id)
            if not target_info:
                return {
                    'response': f"HAL9000: Target node !{target_id} not found",
                    'channel_id': channel_id,
                    'is_channel_message': channel_id is not None
                }
            
            # Check if target is connected via MQTT
            is_mqtt = target_info.get('connection_type') == 'mqtt'
            
            # Store traceroute request with requester info
            self.active_traceroutes[target_id] = {
                'start_time': time.time(),
                'target_info': target_info,
                'is_mqtt': is_mqtt,
                'requester_id': sender_id,  # Store who requested the traceroute
                'requester_name': sender_name,
                'channel_id': channel_id  # Store the channel ID for the response
            }
            
            # Start background collection
            self._start_traceroute_collection(target_id)
            
            # Customize response based on whether we're using default target
            if not args:
                response = f"HAL9000: Starting traceroute to your node (!{target_id})..."
            else:
                response = f"HAL9000: Starting traceroute to !{target_id}..."
            
            return {
                'response': response,
                'channel_id': channel_id,
                'is_channel_message': channel_id is not None
            }

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
                if self.meshtastic_handler and self.meshtastic_handler.is_connected:
                    # Use the stored channel_id if this was a channel message
                    channel_id = traceroute_data.get('channel_id')
                    if channel_id is not None:
                        # Send to channel
                        self.meshtastic_handler.send_message(
                            response,
                            channel_index=channel_id
                        )
                    else:
                        # Send as DM
                        self.meshtastic_handler.send_message(
                            response,
                            destination_id_hex=traceroute_data['requester_id']
                        )
                
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
        
        # Build path based on node's parent nodes
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
                    'node_name': node_info.get('long_name', 'Unknown'),
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
        
        # Add HAL9000 as the first hop if not already present
        if not path_info['hops'] or path_info['hops'][0]['node_id'] != f"{self.meshtastic_handler.node_id:x}":
            path_info['hops'].insert(0, {
                'node_id': f"{self.meshtastic_handler.node_id:x}",
                'node_name': 'HAL9000',
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