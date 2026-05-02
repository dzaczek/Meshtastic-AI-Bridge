from typing import Dict, Any, Optional
from .base import BotPlugin
import node_db

class TldrPlugin(BotPlugin):
    @property
    def commands(self) -> list[str]:
        return ['tldr', 'missed']

    def handle(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool, bot: Any) -> Optional[Dict[str, Any]]:
        if not is_dm:
            return None

        limit = 5
        try:
            recent = node_db.get_recent_messages(limit=limit)
        except AttributeError:
            recent = []

        if not recent:
            return {'response': "[TLDR] No recent activity.", 'channel_id': channel_id, 'is_channel_message': False}

        lines = ["[TLDR] Recent activity:"]
        for msg in recent:
            short_id = msg.get('node_id', 'UNK')[:4]
            text = msg.get('text', '')
            if len(text) > 20:
                text = text[:17] + "..."
            lines.append(f"• {short_id}: {text}")

        response = "\n".join(lines)
        return {'response': response, 'channel_id': channel_id, 'is_channel_message': False}
