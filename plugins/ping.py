from typing import Dict, Any, Optional
from .base import BotPlugin

class PingPlugin(BotPlugin):
    @property
    def commands(self) -> list[str]:
        return ['ping', 'qsl']

    def handle(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool, bot: Any) -> Optional[Dict[str, Any]]:
        node_info = bot.get_node_info(sender_id)
        if not node_info:
            node_info = {
                'node_id': sender_id,
                'long_name': sender_name,
                'short_name': sender_name[:4] if sender_name else 'UNK',
                'rssi': 'N/A',
                'snr': 'N/A',
                'last_heard': None,
                'battery_level': None,
                'lat': None,
                'lon': None
            }

        is_mqtt = False
        if bot.meshtastic_handler and bot.meshtastic_handler.interface:
            interface = bot.meshtastic_handler.interface
            if hasattr(interface, 'nodes'):
                target_node = None
                for node_num, info in interface.nodes.items():
                    if isinstance(node_num, int):
                        node_id_str = f"{node_num:x}"
                    else:
                        node_id_str = str(node_num).lower().lstrip('!')
                    if node_id_str == sender_id:
                        target_node = info
                        break

                if target_node:
                    is_mqtt = target_node.get('viaMqtt', False)
                    if target_node.get('isMqtt', False):
                        is_mqtt = True

        response = bot.format_ping_response(node_info, is_mqtt=is_mqtt)
        return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}
