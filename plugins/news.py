from typing import Dict, Any, Optional
from .base import BotPlugin

class NewsPlugin(BotPlugin):
    @property
    def commands(self) -> list[str]:
        return ['news']

    def handle(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool, bot: Any) -> Optional[Dict[str, Any]]:
        headline = "Mesh network expanding globally."
        response = f"[NEWS] {headline}"
        return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}
