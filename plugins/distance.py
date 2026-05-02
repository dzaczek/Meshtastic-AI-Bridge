from typing import Dict, Any, Optional
from .base import BotPlugin

class DistancePlugin(BotPlugin):
    @property
    def commands(self) -> list[str]:
        return ['distance', 'odleglosc']

    def handle(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool, bot: Any) -> Optional[Dict[str, Any]]:
        if not args:
            target_id = sender_id
        else:
            target = args.strip().lstrip('!')
            if not target:
                target_id = sender_id
            else:
                found_id = bot._find_node_by_name(target)
                target_id = found_id if found_id else target

        target_info = bot.get_node_info(target_id)
        # Using safe fallbacks like original hal_bot.py
        if not target_info or target_info.get('lat') is None or target_info.get('lon') is None:
            name_str = f"!{target_id}"
            if target_info and target_info.get('short_name'):
                name_str += f" ({target_info.get('short_name')})"
            response = f"[DIST] {name_str}: No position data available"
            return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}

        dist_str = bot._get_distance_str(target_info.get('lat'), target_info.get('lon'))
        if not dist_str:
            response = "[DIST] Unable to calculate distance (missing local or target position)"
        else:
            name_str = f"!{target_id}"
            if target_info.get('short_name'):
                name_str += f" ({target_info.get('short_name')})"
            response = f"[DIST] {name_str}\n{dist_str.rstrip('\n')}"

        return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}
