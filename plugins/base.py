from typing import Dict, Any, Optional

class BotPlugin:
    """Base class for all HalBot plugins."""

    @property
    def commands(self) -> list[str]:
        """List of string commands that trigger this plugin."""
        return []

    def handle(self, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool, bot: Any) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("Plugins must implement the handle method.")
