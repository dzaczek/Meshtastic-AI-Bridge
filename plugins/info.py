from typing import Dict, Any, Optional
from .base import BotPlugin

class InfoPlugin(BotPlugin):
    @property
    def commands(self) -> list[str]:
        return ['info', 'test']

    def handle(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool, bot: Any) -> Optional[Dict[str, Any]]:
        command = 'info'
        node_info = bot.get_node_info(sender_id)
        if not node_info:
            node_info = {
                'node_id': sender_id,
                'long_name': sender_name,
                'short_name': sender_name[:4] if sender_name else 'UNK',
                'rssi': None,
                'snr': None,
                'hops_away': None
            }
        response = bot.format_status_response(command, node_info)
        return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}
