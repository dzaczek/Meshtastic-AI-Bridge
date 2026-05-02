from typing import Dict, Any, Optional
from .base import BotPlugin

class TraceroutePlugin(BotPlugin):
    @property
    def commands(self) -> list[str]:
        return ['traceroute', 'gtraceroute']

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

                    if node_id_str == target_id:
                        target_node = info
                        break

                if target_node:
                    is_mqtt = target_node.get('viaMqtt', False) or target_node.get('isMqtt', False)

        if bot.meshtastic_handler and bot.meshtastic_handler.is_connected and not is_mqtt:
            bot.meshtastic_handler.send_traceroute(target_id)

            bot.active_traceroutes[target_id] = {
                'requester_id': sender_id,
                'channel_id': channel_id,
                'is_dm': is_dm,
                'is_mqtt': False
            }

            bot._start_traceroute_collection(target_id)

            return {
                'response': f"[{bot.bot_name}] Traceroute initiated. Results in ~{bot.traceroute_timeout}s...",
                'channel_id': channel_id,
                'is_channel_message': not is_dm
            }
        else:
            path_info = bot._get_traceroute_info(target_id)
            response = bot.format_traceroute_response(path_info, is_mqtt=is_mqtt)
            return {'response': response, 'channel_id': channel_id, 'is_channel_message': not is_dm}
