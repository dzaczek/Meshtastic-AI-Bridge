import os
import importlib
import inspect
from typing import Dict, Any, Optional, List
from .base import BotPlugin

class PluginManager:
    def __init__(self, bot: Any):
        self.bot = bot
        self.plugins: Dict[str, BotPlugin] = {}
        self._load_plugins()

    def _load_plugins(self):
        plugins_dir = os.path.dirname(__file__)
        for filename in os.listdir(plugins_dir):
            if filename.endswith('.py') and filename not in ('__init__.py', 'base.py', 'plugin_manager.py'):
                module_name = f'plugins.{filename[:-3]}'
                try:
                    module = importlib.import_module(module_name)
                    for _, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, BotPlugin) and obj is not BotPlugin:
                            plugin_instance = obj()
                            for cmd in plugin_instance.commands:
                                self.plugins[cmd.lower()] = plugin_instance
                except Exception as e:
                    print(f"Failed to load plugin {filename}: {e}")

    def get_supported_commands(self) -> List[str]:
        return list(self.plugins.keys())

    def handle_command(self, command: str, args: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool) -> Optional[Dict[str, Any]]:
        plugin = self.plugins.get(command.lower())
        if plugin:
            return plugin.handle(args, sender_id, sender_name, channel_id, is_dm, self.bot)
        return None
