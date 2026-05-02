from typing import Dict, Any, Optional
from .base import BotPlugin
import time
import node_db

class NodesPlugin(BotPlugin):
    @property
    def commands(self) -> list[str]:
        return ['nodes']

    def handle(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool, bot: Any) -> Optional[Dict[str, Any]]:
        try:
            nodes = node_db.get_all_nodes(limit=5)
        except AttributeError:
            nodes = []

        if not nodes:
            return {'response': "[NODES] No nodes visible.", 'channel_id': channel_id, 'is_channel_message': not is_dm}

        lines = ["[NODES] Visible:"]
        current_time = time.time()
        for node in nodes:
            short_name = node.get('short_name') or 'UNK'
            last_seen = node.get('last_seen', 0)

            elapsed = int(current_time - last_seen)
            if elapsed < 60:
                time_str = f"{elapsed}s"
            elif elapsed < 3600:
                time_str = f"{elapsed//60}m"
            else:
                time_str = f"{elapsed//3600}h"

            lines.append(f"• {short_name} ({time_str})")

        response = "\n".join(lines)
        return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}
