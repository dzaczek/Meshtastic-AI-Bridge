#!/usr/bin/env python3
"""
Meshtastic AI Bridge TUI - Modern Textual Interface
Using Textual framework: https://github.com/Textualize/textual
"""
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Input, ListView, ListItem, Label, Button, Log, RichLog
from textual.reactive import reactive
from textual.binding import Binding
from textual.message import Message
from textual import events
from textual.css.query import NoMatches
from datetime import datetime
import time
import threading
import asyncio
from typing import Dict, List, Optional
import meshtastic
from meshtastic_handler import MeshtasticHandler
from ai_bridge import AIBridge
from conversation_manager import ConversationManager
from hal_bot import HalBot
import config
import random
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.console import RenderableType
import json
import os
import sys
import re
import traceback

class AIProcessingWorker:
    """Worker class to handle AI processing in a separate thread"""
    def __init__(self, app, text: str, sender_id: str, sender_name: str, channel_id: int, is_dm: bool, conversation_id: str, url_pattern=None, skip_triage: bool = False):
        self.app = app
        self.text = text
        self.sender_id = sender_id
        self.sender_name = sender_name
        self.channel_id = channel_id
        self.is_dm = is_dm
        self.conversation_id = conversation_id
        self.url_pattern = url_pattern
        # Always skip triage for DMs
        self.skip_triage = True if is_dm else skip_triage

    def run(self) -> None:
        """Run the AI processing"""
        try:
            log_info = getattr(self.app, 'log_info', print)
            log_error = getattr(self.app, 'log_error', print)
            log_info(f"[AIWorker] Starting for conv_id={self.conversation_id}, is_dm={self.is_dm}, sender_id={self.sender_id}, channel_id={self.channel_id}")
            context_history = self.app.conversation_manager.get_contextual_history(
                self.conversation_id, 
                for_user_name=self.sender_name
            )
            log_info(f"[AIWorker] Context history loaded: {context_history[-2:] if context_history else 'EMPTY'}")
            web_analysis_summary = None
            if self.url_pattern:
                urls_found = self.url_pattern.findall(self.text)
                if urls_found:
                    detected_url = urls_found[0]
                    try:
                        web_analysis_summary = self.app.ai_bridge.analyze_url_content(detected_url)
                        log_info(f"[AIWorker] Web analysis summary: {web_analysis_summary}")
                        # Save URL analysis to conversation history so AI remembers it
                        self.app.conversation_manager.add_url_analysis(self.conversation_id, detected_url, web_analysis_summary)
                    except Exception as e:
                        web_analysis_summary = f"[Error analyzing URL: {str(e)}]"
                        log_error(f"[AIWorker] Error analyzing URL: {e}")
                    else:
                        web_analysis_summary = None
            ai_response = self.app.ai_bridge.get_response(
                context_history,
                self.text,
                self.sender_name,
                self.sender_id,
                web_analysis_summary=web_analysis_summary,
                skip_triage=self.skip_triage
            )
            log_info(f"[AIWorker] AI response: {ai_response}")
            if ai_response:
                if self.app.ai_min_delay >= 0 and self.app.ai_max_delay > self.app.ai_min_delay:
                    delay = random.uniform(self.app.ai_min_delay, self.app.ai_max_delay)
                    log_info(f"[AIWorker] Applying delay: {delay:.2f}s")
                    time.sleep(delay)
                self.app.conversation_manager.add_message(
                    self.conversation_id,
                    "assistant",
                    ai_response
                )
                self.app.last_response_times[self.conversation_id] = time.time()
                if self.is_dm:
                    log_info(f"[AIWorker] Sending DM reply to {self.sender_id} on channel 0")
                    success, reason = self.app.meshtastic_handler.send_message(
                        ai_response,
                        destination_id_hex=self.sender_id,
                        channel_index=0  # DMs always use channel 0
                    )
                else:
                    log_info(f"[AIWorker] Sending channel reply on channel {self.channel_id}")
                    success, reason = self.app.meshtastic_handler.send_message(
                        ai_response,
                        channel_index=self.channel_id
                    )
                log_info(f"[AIWorker] send_message result: success={success}, reason={reason}")
                # Update UI
                asyncio.run_coroutine_threadsafe(
                    self.app.update_after_ai_response(
                        self.conversation_id,
                        success,
                        reason,
                        self.sender_name
                    ),
                    self.app.app_loop or asyncio.get_running_loop()
                )
            else:
                log_error(f"[AIWorker] No valid AI response for {self.sender_name} in conv_id={self.conversation_id}")
        except Exception as e:
            log_error = getattr(self.app, 'log_error', print)
            log_error(f"[AIWorker] Exception: {e}")
            traceback.print_exc()

class NodeListItem(ListItem):
    """Custom list item for nodes"""
    def __init__(self, node_id: str, node_info: dict, is_favorite: bool = False, unread_count: int = 0):
        super().__init__()
        self.node_id = node_id
        self.node_info = node_info
        self.is_favorite = is_favorite
        self.unread_count = unread_count
        
        # Define fallback icons for terminals with limited Unicode support
        self.favorite_icon = "★"  # Unicode star
        self.favorite_icon_fallback = "*"  # ASCII fallback
        self.node_icon = "●"  # Unicode circle
        self.node_icon_fallback = "o"  # ASCII fallback
        self.mqtt_icon = "🌐"  # Unicode globe
        self.mqtt_icon_fallback = "[M]"  # ASCII fallback
        
    def _get_icon(self, unicode_icon: str, fallback_icon: str) -> str:
        """Try to use Unicode icon, fall back to ASCII if terminal doesn't support it"""
        try:
            # Test if terminal can display the Unicode character
            unicode_icon.encode('utf-8').decode('utf-8')
            return unicode_icon
        except UnicodeError:
            return fallback_icon
        
    def _sanitize_name(self, name: str) -> str:
        """Sanitize node name while preserving UTF-8 characters"""
        if not name:
            return "Unknown"
            
        # Remove any markup that could interfere with display
        name = re.sub(r'\[.*?\]', '', name)  # Remove any remaining brackets and their contents
        
        # Remove control characters but preserve printable Unicode
        name = ''.join(char for char in name if char.isprintable() or char.isspace())
        
        # Clean up any double spaces created by the replacements
        name = re.sub(r'\s+', ' ', name).strip()
        
        return name
        
    def compose(self) -> ComposeResult:
        """Compose the node item"""
        # Get appropriate icons with fallbacks
        icon = self._get_icon(self.favorite_icon, self.favorite_icon_fallback) if self.is_favorite else self._get_icon(self.node_icon, self.node_icon_fallback)
        
        # Get name and sanitize it while preserving UTF-8
        name = self._sanitize_name(self.node_info.get('long_name', 'Unknown'))
        node_id = self.node_id
        
        # Check if this is a default Meshtastic name
        # Default names are like "Meshtastic XXXX" where XXXX matches the last 4 chars of node ID
        is_default_name = False
        if name.startswith("Meshtastic ") and len(name) > 11:
            # Extract the suffix from the name
            name_suffix = name[11:].strip()
            # Check if it matches the end of the node ID
            if node_id.endswith(name_suffix.lower()):
                is_default_name = True
                # For default names, just show "Node" + suffix to avoid redundancy
                name = f"Node {name_suffix}"
        
        # Add hop count to the name
        hops_away = self.node_info.get('hops_away')
        if hops_away is not None:
            if hops_away == 0:
                hop_indicator = " (D)"  # Direct connection
            else:
                hop_indicator = f" ({hops_away})"  # Number of hops
        else:
            hop_indicator = ""  # No hop count data available

        # Add MQTT indicator if node is connected via TCP/MQTT
        mqtt_icon = self._get_icon(self.mqtt_icon, self.mqtt_icon_fallback) if self.node_info.get('connection_type') == 'tcp' else ""
        mqtt_indicator = f" {mqtt_icon}" if mqtt_icon else ""
        
        # For default names, we can skip showing the full node ID since it's redundant
        if is_default_name:
            display_text = f"{icon} {name}{hop_indicator}{mqtt_indicator}"
        else:
            display_text = f"{icon} {name}{hop_indicator}{mqtt_indicator} !{node_id}"
        
        # Use plain text style to avoid markup issues
        style = "reverse" if self.unread_count > 0 else ""
        yield Label(display_text, classes=style, markup=False)

class ChannelListItem(ListItem):
    """Custom list item for channels"""
    def __init__(self, channel_id: int, channel_name: str, unread_count: int = 0):
        super().__init__()
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.unread_count = unread_count
        
    def compose(self) -> ComposeResult:
        """Compose the channel item"""
        style = "reverse" if self.unread_count > 0 else ""
        yield Label(f"Ch {self.channel_id}: {self.channel_name}", classes=style)

class StatsPanel(Static):
    """Stats panel widget"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_connected = False
        self.node_count = 0
        self.channel_info = "Channel 0"
    
    def on_mount(self) -> None:
        """Set up periodic updates"""
        self.set_interval(1.0, self.refresh_stats)
    
    def refresh_stats(self) -> None:
        """Refresh the stats display"""
        self.refresh()
    
    def render(self) -> RenderableType:
        """Render the stats panel"""
        table = Table(show_header=False, box=None, expand=True)
        table.add_column("Stat", style="bold")
        table.add_column("Value")
        
        # Connection status
        status = "Connected" if self.is_connected else "Disconnected"
        status_style = "green" if self.is_connected else "red"
        table.add_row("Status", Text(status, style=status_style))
        
        # Node count
        table.add_row("Nodes", str(self.node_count))
        
        # Current channel
        table.add_row("Active", self.channel_info)
        
        # Time
        table.add_row("Time", datetime.now().strftime("%H:%M:%S"))
        
        return Panel(table, title="Stats", border_style="blue")

class InfoPanel(Static):
    """Shows aggregate info such as unread counts and node stats."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stats: dict | None = None

    def set_stats(self, stats_dict: dict):
        self.stats = stats_dict
        self.refresh()

    def render(self) -> RenderableType:  # type: ignore[override]
        if not self.stats:
            return Panel("No stats", border_style="red", title="Info")

        table = Table(show_header=False, box=None)
        for key, val in self.stats.items():
            table.add_row(key, str(val))
        return Panel(table, title="Info", border_style="green")

class NodeStatsPanel(Static):
    """Detailed node statistics panel"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_node_id = None
        self.node_data = {}
        
    def set_node(self, node_id: str, node_info: dict):
        """Set the node to display statistics for"""
        self.selected_node_id = node_id
        self.node_data = node_info
        self.refresh()
        
    def render(self) -> RenderableType:
        """Render the detailed node statistics"""
        if not self.selected_node_id or not self.node_data:
            return Panel("Select a node to view detailed statistics", title="Node Statistics", border_style="blue")
        
        # Create main table
        table = Table(show_header=False, box=None, expand=True)
        table.add_column("Property", style="bold cyan")
        table.add_column("Value", style="white")
        
        # Basic node info
        node_id = self.node_data.get('node_id', 'Unknown')
        long_name = self.node_data.get('long_name', 'Unknown')
        short_name = self.node_data.get('short_name', 'UNK')
        
        table.add_row("Node ID", f"!{node_id}")
        table.add_row("Long Name", long_name)
        table.add_row("Short Name", short_name)
        
        # User role (if available)
        user_role = self.node_data.get('user_role', 'Unknown')
        table.add_row("User Role", user_role)
        
        # First heard
        first_heard = self.node_data.get('first_heard')
        if first_heard:
            first_heard_str = datetime.fromtimestamp(first_heard).strftime("%Y-%m-%d %H:%M:%S")
            table.add_row("First Heard", first_heard_str)
        
        # Last heard
        last_heard = self.node_data.get('last_heard')
        if last_heard:
            last_heard_str = datetime.fromtimestamp(last_heard).strftime("%Y-%m-%d %H:%M:%S")
            time_ago = self._format_time_ago(last_heard)
            table.add_row("Last Heard", f"{last_heard_str} ({time_ago})")
        
        # Connection info
        connection_type = self.node_data.get('connection_type', 'radio')
        hops_away = self.node_data.get('hops_away')
        if hops_away is not None:
            hops_str = f"{hops_away} hop{'s' if hops_away != 1 else ''}"
        else:
            hops_str = "Unknown"
        
        table.add_row("Connection", f"{connection_type.upper()} ({hops_str})")
        
        # Signal statistics for last 4 packets
        signal_history = self.node_data.get('signal_history', [])
        if signal_history:
            table.add_row("", "")  # Empty row for spacing
            table.add_row("Signal History", "")
            
            for i, packet in enumerate(signal_history[-4:], 1):  # Last 4 packets
                timestamp = packet.get('timestamp', 0)
                rssi = packet.get('rssi')
                snr = packet.get('snr')
                time_ago = self._format_time_ago(timestamp)
                
                rssi_str = f"{rssi} dBm" if rssi is not None else "N/A"
                snr_str = f"{snr} dB" if snr is not None else "N/A"
                
                table.add_row(f"  Packet {i}", f"{time_ago} - RSSI: {rssi_str}, SNR: {snr_str}")
        
        # Current signal info
        current_rssi = self.node_data.get('rssi')
        current_snr = self.node_data.get('snr')
        if current_rssi is not None or current_snr is not None:
            table.add_row("", "")  # Empty row for spacing
            table.add_row("Current Signal", "")
            rssi_str = f"{current_rssi} dBm" if current_rssi is not None else "N/A"
            snr_str = f"{current_snr} dB" if current_snr is not None else "N/A"
            table.add_row("  RSSI", rssi_str)
            table.add_row("  SNR", snr_str)
        
        # GPS Position (if available)
        position = self.node_data.get('position')
        if position:
            table.add_row("", "")  # Empty row for spacing
            table.add_row("GPS Position", "")
            lat = position.get('latitude')
            lon = position.get('longitude')
            alt = position.get('altitude')
            if lat is not None and lon is not None:
                table.add_row("  Coordinates", f"{lat:.6f}, {lon:.6f}")
            if alt is not None:
                table.add_row("  Altitude", f"{alt}m")
        
        # Model info
        model = self.node_data.get('model', 'Unknown')
        table.add_row("Model", model)
        
        # Battery info
        battery = self.node_data.get('battery_level')
        if battery is not None:
            table.add_row("Battery", f"{battery}%")
        
        # Uptime
        uptime = self.node_data.get('uptime')
        if uptime:
            table.add_row("Uptime", uptime)
        
        return Panel(table, title=f"Node Statistics - {short_name}", border_style="green")
    
    def _format_time_ago(self, timestamp: float) -> str:
        """Format time ago from timestamp"""
        if not timestamp:
            return "Unknown"
        
        now = time.time()
        diff = now - timestamp
        
        if diff < 60:
            return f"{int(diff)}s ago"
        elif diff < 3600:
            return f"{int(diff // 60)}m ago"
        elif diff < 86400:
            return f"{int(diff // 3600)}h ago"
        else:
            return f"{int(diff // 86400)}d ago"

class MeshtasticInteractive(App):
    """Main Interactive Application using Textual"""
    
    TITLE = "Meshtastic AI Bridge - Interactive Interface"
    CSS_PATH = "meshtastic_tui.css"
    BINDINGS = [
        ("q", "quit_app", "Quit"),
        ("ctrl+c", "quit_app", "Quit"),
        ("f", "force_ai", "Force AI Response"),
        ("c", "focus_channel_list", "Focus Channels"),
        ("n", "focus_node_list", "Focus Nodes"),
        ("m", "focus_messages", "Focus Messages"),
        ("i", "focus_input", "Focus Input")
    ]
    current_conversation_id = reactive(None, layout=True)
    sidebar_conversations = reactive([], layout=True)

    CSS = """
    Screen {
        layout: grid;
        grid-size: 4 7;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-rows: auto 1fr 1fr 1fr 1fr 1fr 1;
    }
    
    Header {
        column-span: 4;
    }
    
    #left-panel {
        column-span: 1;
        row-span: 5;
        border: solid green;
        height: 100%;
        padding: 1;
        layout: vertical;
    }
    
    #center-panel {
        column-span: 2;
        row-span: 5;
        border: solid yellow;
        height: 100%;
        overflow: hidden;
        layout: vertical;
    }
    
    #right-panel {
        column-span: 1;
        row-span: 5;
        border: solid blue;
        height: 100%;
        padding: 1;
        layout: vertical;
    }
    
    #channel-list {
        height: 30%;
        border-bottom: solid $accent;
        margin-bottom: 1;
    }
    
    #info-panel {
        height: 30%;
        border-bottom: solid $accent;
        margin-bottom: 1;
    }
    
    #stats-panel {
        height: 40%;
    }
    
    #node-list {
        height: 60%;
        border-bottom: solid $accent;
        margin-bottom: 1;
    }
    
    #node-stats {
        height: 40%;
    }
    
    #bottom-panel {
        column-span: 4;
        border: solid cyan;
        height: 100%;
        layout: horizontal;
    }
    
    #log-box {
        width: 100%;
        padding: 1;
    }
    
    Footer {
        column-span: 4;
    }
    
    ListView {
        height: 100%;
        background: $surface;
    }
    
    #message-display {
        height: 1fr;
        background: $surface;
        overflow-y: scroll;
        scrollbar-gutter: stable;
        scrollbar-size: 1 1;
    }
    
    #message-display:focus {
        border: thick $accent;
    }
    
    #message-container {
        padding: 0 1;
        width: 100%;
    }
    
    #input-container {
        layout: horizontal;
        height: 3;
        dock: bottom;
        width: 100%;
    }
    
    #message-input {
        width: 1fr;
        height: 3;
    }
    
    #force-ai-button {
        width: 10;
        height: 3;
        margin-left: 1;
        background: #2c3e50;
        color: white;
    }
    
    #force-ai-button:hover {
        background: #34495e;
    }
    
    #force-ai-button:focus {
        background: #1a252f;
    }
    
    Log {
        height: 100%;
        background: $surface;
    }
    
    /* Add styles for unread highlighting */
    .reverse {
        background: $accent;
        color: $surface;
    }
    """
    
    def __init__(self):
        super().__init__()
        self.app_config = config
        self.ai_bridge = AIBridge(self.app_config)
        self.conversation_manager = ConversationManager(self.app_config, self.ai_bridge)
        self.app_loop = None  # Initialize app_loop as None
        self.message_queue = asyncio.Queue()
        
        # Initialize Meshtastic handler
        self.meshtastic_handler = MeshtasticHandler(
            connection_type=self.app_config.MESHTASTIC_CONNECTION_TYPE,
            device_specifier=self.app_config.MESHTASTIC_DEVICE_SPECIFIER,
            on_message_received_callback=self.handle_meshtastic_message
        )
        
        # Get AI node ID
        self.ai_node_id = self._norm_id(f"{self.meshtastic_handler.node_id:x}") if self.meshtastic_handler.node_id else None
        self.log_info(f"AI Node ID set to: '{self.ai_node_id}' (from meshtastic_handler.node_id: {self.meshtastic_handler.node_id})")
        
        # Initialize HAL bot
        self.hal_bot = HalBot(self.meshtastic_handler)
        
        # Other initializations
        self.url_pattern = re.compile(r'https?://[^\s/$.?#].[^\s]*', re.IGNORECASE)
        self.last_response_times = {}
        self.tx_count = 0
        self.rx_count = 0
        self.active_channel_for_ai_posts = getattr(self.app_config, 'ACTIVE_MESHTASTIC_CHANNEL_INDEX', 0)
        self.ai_response_probability = getattr(self.app_config, 'AI_RESPONSE_PROBABILITY', 0.85)
        self.ai_min_delay = getattr(self.app_config, 'AI_MIN_RESPONSE_DELAY_S', 2)
        self.ai_max_delay = getattr(self.app_config, 'AI_MAX_RESPONSE_DELAY_S', 8)
        self.ai_cooldown = getattr(self.app_config, 'AI_RESPONSE_COOLDOWN_S', 60)
        self.enable_ai_triage = getattr(self.app_config, 'ENABLE_AI_TRIAGE_ON_CHANNELS', False)
        
        # State
        self.nodes: Dict[str, dict] = {}
        self.current_chat_type = "channel"
        self.current_chat_id = "0"
        self.last_viewed_messages: Dict[str, int] = {}
        
        # Unread message tracking
        self.unread_counts: Dict[str, int] = {}
        self.channel_unread: Dict[int, int] = {}  # {channel_id: count}
        self.node_unread: Dict[str, int] = {}  # {node_id: count}
        
        # Load persisted last viewed state
        self.load_last_viewed_state()
    
    def log_info(self, message: str) -> None:
        """Log info message to file and console"""
        import logging
        logging.info(message)
        try:
            log_widget = self.query_one("#app-log", RichLog)
            log_widget.write(f"[blue]{message}[/blue]")
        except:
            print(f"INFO: {message}")
    
    def log_error(self, message: str) -> None:
        """Log error message to file and console"""
        import logging
        logging.error(message)
        try:
            log_widget = self.query_one("#app-log", RichLog)
            log_widget.write(f"[red]{message}[/red]")
        except:
            print(f"ERROR: {message}")
    
    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        
        # Left panel - Channels, Info, and Stats
        with Container(id="left-panel"):
            yield Label("Channels", classes="title")
            yield ListView(
                ChannelListItem(0, "Primary"),
                ChannelListItem(1, "Channel 1"),
                ChannelListItem(2, "Channel 2"),
                ChannelListItem(3, "Channel 3"),
                ChannelListItem(4, "Channel 4"),
                ChannelListItem(5, "Channel 5"),
                ChannelListItem(6, "Channel 6"),
                ChannelListItem(7, "Channel 7"),
                id="channel-list"
            )
            yield InfoPanel(id="info-panel")
            yield StatsPanel(id="stats-panel")
        
        # Center panel - Messages
        with Container(id="center-panel"):
            yield RichLog(id="message-display", wrap=True, markup=True, highlight=True, auto_scroll=True)
            with Horizontal(id="input-container"):
                yield Input(placeholder="Type a message...", id="message-input")
                yield Button("🤖 Force AI", id="force-ai-button")
        
        # Right panel - Node list and stats
        with Container(id="right-panel"):
            yield Label("Nodes", classes="title")
            yield ListView(id="node-list")
            yield NodeStatsPanel(id="node-stats")
        
        # Bottom panel - Logs only
        with Container(id="bottom-panel"):
            with Container(id="log-box"):
                yield RichLog(id="app-log", highlight=True, markup=True)
        
        yield Footer()
    
    async def on_mount(self) -> None:
        """Called when the app is mounted"""
        self.app_loop = asyncio.get_running_loop()
        # Start message queue processor
        self.run_worker(self.process_message_queue, group="message_processor")
        
        # Load initial nodes
        self.load_initial_nodes()
        
        # Set default channel
        self.load_conversation()
        
        # Update stats
        self.update_stats()
        
        # Log startup
        self.query_one("#app-log", RichLog).write("[green]TUI started successfully[/green]")
        
        # Initial info panel update
        self.refresh_info_panel()
        
        # Focus the message input by default
        self.query_one("#message-input").focus()
    
    def load_initial_nodes(self) -> None:
        """Load nodes from Meshtastic interface"""
        if self.meshtastic_handler and self.meshtastic_handler.interface:
            interface = self.meshtastic_handler.interface
            if hasattr(interface, 'nodes') and interface.nodes:
                for node_id, node_info in interface.nodes.items():
                    if 'user' in node_info:
                        user = node_info['user']
                        # Handle node_id format
                        if isinstance(node_id, str):
                            node_id_str = self._norm_id(node_id)
                        else:
                            node_id_str = self._norm_id(f"{node_id:x}")
                        
                        # Get detailed node information
                        detailed_info = self._get_detailed_node_info(node_id_str, node_info)
                        
                        self.nodes[node_id_str] = detailed_info
                
                self.update_node_list()
    
    def _get_detailed_node_info(self, node_id_str: str, node_info: dict) -> dict:
        """Get detailed information about a node including signal history"""
        user = node_info.get('user', {})
        
        # Basic info
        detailed_info = {
            'long_name': user.get('longName', 'Unknown'),
            'short_name': user.get('shortName', 'UNK'),
            'last_heard': node_info.get('lastHeard', time.time()),
            'first_heard': node_info.get('firstHeard', time.time()),
            'is_favorite': node_info.get('isFavorite', False),
            'hops_away': node_info.get('hopsAway', None),
            'connection_type': self.app_config.MESHTASTIC_CONNECTION_TYPE,
            'node_id': node_id_str,
            'user_role': user.get('role', 'Unknown'),
            'model': node_info.get('model', 'Unknown'),
            'battery_level': node_info.get('batteryLevel'),
            'uptime': node_info.get('uptime'),
        }
        
        # Signal information
        rssi = node_info.get('rssi')
        snr = node_info.get('snr')
        if rssi is None and 'lastPacketRssi' in node_info:
            rssi = node_info['lastPacketRssi']
        if snr is None and 'lastPacketSnr' in node_info:
            snr = node_info['lastPacketSnr']
        
        detailed_info['rssi'] = rssi
        detailed_info['snr'] = snr
        
        # GPS Position
        position = node_info.get('position')
        if position:
            detailed_info['position'] = {
                'latitude': position.get('latitude'),
                'longitude': position.get('longitude'),
                'altitude': position.get('altitude'),
            }
        
        # Signal history (simulate last 4 packets - in real implementation this would track actual packets)
        signal_history = []
        current_time = time.time()
        for i in range(4):
            # Simulate signal history with slight variations
            packet_time = current_time - (i * 60)  # Each packet 1 minute apart
            packet_rssi = rssi + random.randint(-5, 5) if rssi is not None else None
            packet_snr = snr + random.randint(-2, 2) if snr is not None else None
            
            signal_history.append({
                'timestamp': packet_time,
                'rssi': packet_rssi,
                'snr': packet_snr,
            })
        
        detailed_info['signal_history'] = signal_history
        
        return detailed_info

    def update_node_list(self) -> None:
        """Update the node list widget with unread counts"""
        node_list = self.query_one("#node-list", ListView)
        node_list.clear()
        
        # Sort nodes by last heard
        sorted_nodes = sorted(self.nodes.items(), key=lambda x: x[1]['last_heard'], reverse=True)
        
        for node_id, node_info in sorted_nodes:
            # Get DM conversation ID
            conv_id = self._dm_conv(node_id)
            # Get total messages in conversation
            messages = self.conversation_manager.load_conversation(conv_id)
            total_messages = len(messages)
            # Get last viewed count
            last_viewed = self.last_viewed_messages.get(conv_id, 0)
            # Calculate unread
            unread = max(0, total_messages - last_viewed)
            self.node_unread[node_id] = unread
            node_list.append(NodeListItem(node_id, node_info, node_info.get('is_favorite', False), unread))
    
    def get_last_viewed_file_path(self) -> str:
        """Get the path to the last viewed state file"""
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_viewed.json")
    
    def save_last_viewed_state(self) -> None:
        """Save the last viewed message counts to a file"""
        try:
            state = {
                'last_viewed': self.last_viewed_messages,
                'timestamp': time.time()
            }
            with open(self.get_last_viewed_file_path(), 'w') as f:
                json.dump(state, f)
        except Exception as e:
            # Since we might be shutting down, just print to stderr
            print(f"Failed to save last viewed state: {str(e)}", file=sys.stderr)
    
    def load_last_viewed_state(self) -> None:
        """Load the last viewed message counts from file"""
        try:
            file_path = self.get_last_viewed_file_path()
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    state = json.load(f)
                    self.last_viewed_messages = state.get('last_viewed', {})
        except Exception as e:
            # If there's an error loading, start fresh
            self.last_viewed_messages = {}
    
    def load_conversation(self) -> None:
        """Load messages for current conversation"""
        log_widget = self.query_one("#app-log", RichLog)
        if self.current_chat_type == "channel":
            conv_id = f"ch_{self.current_chat_id}_broadcast"
        else:
            conv_id = self._dm_conv(self.current_chat_id)
        
        log_widget.write(f"[dodger_blue1]Loading conversation for conv_id: {conv_id}[/dodger_blue1]")

        messages = self.conversation_manager.load_conversation(conv_id)
        
        # Debug: Show the actual message count and some info about first/last messages
        if messages:
            first_msg = messages[0]
            last_msg = messages[-1]
            log_widget.write(f"[green]Loaded {len(messages)} total messages from file[/green]")
            log_widget.write(f"[green]First: {first_msg.get('user_name', 'Unknown')} at {datetime.fromtimestamp(first_msg.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M')}[/green]")
            log_widget.write(f"[green]Last: {last_msg.get('user_name', 'Unknown')} at {datetime.fromtimestamp(last_msg.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M')}[/green]")
        else:
            log_widget.write(f"[yellow]No messages found for conv_id: {conv_id}[/yellow]")
        
        message_display = self.query_one("#message-display", RichLog)
        
        # Clear the message display
        message_display.clear()
        
        # Write all messages to the RichLog
        if not messages:
            message_display.write("[dim italic]No messages yet...[/dim italic]")
        else:
            for msg in messages:
                # Format each message
                timestamp = datetime.fromtimestamp(msg.get('timestamp', time.time())).strftime("%H:%M:%S")
                sender = msg.get('user_name', 'Unknown')
                content = msg.get('content', '')
                role = msg.get('role', 'user')
                
                # Style based on role
                if role == 'assistant':
                    style = "cyan"
                    sender = "AI"
                elif sender == "You" or sender == "You (TUI)":
                    style = "green"
                    sender = "You"
                else:
                    style = "yellow"
                
                # Write the message with markup
                message_display.write(f"[dim]{timestamp}[/dim] [{style} bold]{sender}:[/{style} bold] {content}")
        
        # Update last viewed count and persist it
        self.last_viewed_messages[conv_id] = len(messages)
        self.save_last_viewed_state()
        
        # Update lists to reflect current unread status
        self.update_channel_list()
        self.update_node_list()
        self.refresh_info_panel()
        
        # Scroll to bottom to show newest messages
        message_display.scroll_end(animate=False)
        
        # Focus the message input
        self.query_one("#message-input").focus()
    
    def update_stats(self) -> None:
        """Update stats panel"""
        stats = self.query_one("#stats-panel", StatsPanel)
        stats.is_connected = self.meshtastic_handler.is_connected if self.meshtastic_handler else False
        stats.node_count = len(self.nodes)
        
        if self.current_chat_type == "channel":
            stats.channel_info = f"Channel {self.current_chat_id}"
        else:
            node = self.nodes.get(self.current_chat_id, {})
            stats.channel_info = f"DM: {node.get('long_name', 'Unknown')[:15]}"
    
    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list selection"""
        if isinstance(event.item, ChannelListItem):
            self.current_chat_type = "channel"
            self.current_chat_id = str(event.item.channel_id)
            self.load_conversation()
            self.update_stats()
            log = self.query_one("#app-log", RichLog)
            log.write(f"[blue]Selected channel {event.item.channel_id}[/blue]")
        elif isinstance(event.item, NodeListItem):
            self.current_chat_type = "dm"
            self.current_chat_id = event.item.node_id
            self.load_conversation()
            self.update_stats()
            
            # Update node statistics panel
            node_stats_panel = self.query_one("#node-stats", NodeStatsPanel)
            node_info = self.nodes.get(event.item.node_id, {})
            node_stats_panel.set_node(event.item.node_id, node_info)
            
            log = self.query_one("#app-log", RichLog)
            log.write(f"[magenta]Selected DM with {event.item.node_info['long_name']}[/magenta]")
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle message submission"""
        message = event.value.strip()
        if not message:
            return
        
        # Clear input
        event.input.value = ""
        
        # Send message
        if self.current_chat_type == "channel":
            success, reason = self.meshtastic_handler.send_message(
                message, channel_index=int(self.current_chat_id)
            )
            conv_id = f"ch_{self.current_chat_id}_broadcast"
        else:
            success, reason = self.meshtastic_handler.send_message(
                message, destination_id_hex=self.current_chat_id
            )
            conv_id = self._dm_conv(self.current_chat_id)
        
        if success:
            # Add to conversation
            self.conversation_manager.add_message(
                conv_id, "user", message,
                user_name="You",
                node_id=self.ai_node_id
            )
            # Update last viewed count since we just sent a message and persist it
            self.last_viewed_messages[conv_id] = len(self.conversation_manager.load_conversation(conv_id))
            self.save_last_viewed_state()
            self.load_conversation()
            log = self.query_one("#app-log", RichLog)
            log.write(f"[green]Message sent[/green]")
            
            # tx counter update
            self.tx_count += 1
            self.update_stats()
        else:
            log = self.query_one("#app-log", RichLog)
            log.write(f"[red]Failed to send: {reason}[/red]")
    
    def handle_meshtastic_message(self, text, sender_id, sender_name, destination_id, channel_id):
        """Handle incoming Meshtastic messages"""
        try:
            # Update AI node ID to ensure it's current
            self._update_ai_node_id()
            
            # Queue for async processing
            if self.app_loop is None:
                # If app_loop is not ready, store message in queue
                self.message_queue.put_nowait({
                    'text': text,
                    'sender_id': self._norm_id(sender_id),
                    'sender_name': sender_name,
                    'destination_id': self._norm_id(destination_id),
                    'channel_id': channel_id
                })
            else:
                # If app_loop is ready, use it to queue the message
                asyncio.run_coroutine_threadsafe(
                    self.message_queue.put({
                        'text': text,
                        'sender_id': self._norm_id(sender_id),
                        'sender_name': sender_name,
                        'destination_id': self._norm_id(destination_id),
                        'channel_id': channel_id
                    }),
                    self.app_loop
                )
        except Exception as e:
            log_error(f"Error in handle_meshtastic_message: {e}")
            traceback.print_exc()
    
    async def process_message_queue(self) -> None:
        """Process queued messages"""
        while True:
            try:
                if not self.message_queue.empty():
                    data = await self.message_queue.get()
                    await self.process_incoming_message(data)
                await asyncio.sleep(0.1)  # Small delay to prevent CPU spinning
            except Exception as e:
                log_error(f"Error in process_message_queue: {e}")
                traceback.print_exc()
                await asyncio.sleep(1)  # Longer delay on error
    
    async def process_incoming_message(self, data: dict) -> None:
        """Process an incoming message"""
        try:
            log_widget = self.query_one("#app-log", RichLog)
            log_widget.write(f"[deep_sky_blue1]Processing incoming message data: {data!r}[/deep_sky_blue1]")

            text = data['text']
            sender_id = self._norm_id(data['sender_id'])
            sender_name = data['sender_name']
            destination_id = self._norm_id(data['destination_id'])
            channel_id = data['channel_id']

            # Determine effective channel ID first (treat None as 0)
            effective_channel_id = channel_id if channel_id is not None else 0

            # Determine conversation ID consistently
            is_broadcast = destination_id.lower() == f"{meshtastic.BROADCAST_NUM:x}".lower() or destination_id.lower() == "broadcast"
            is_dm_to_ai = (self.ai_node_id and destination_id == self.ai_node_id)
            
            # Debug logging for DM detection
            log_widget.write(f"[cyan]DM Debug: ai_node_id='{self.ai_node_id}', destination_id='{destination_id}', is_dm_to_ai={is_dm_to_ai}[/cyan]")
            
            if is_dm_to_ai:
                conv_id = self._dm_conv(sender_id)  # DM with the sender of this message
            else:
                conv_id = f"ch_{effective_channel_id}_broadcast"

            # Add the incoming message to conversation history first
            self.conversation_manager.add_message(conv_id, "user", text, user_name=sender_name, node_id=sender_id)

            # Check if this is a HAL bot command
            if self.hal_bot.should_handle_message(text):
                log_widget.write(f"[bright_green]Message is a HAL bot command. Processing...[/bright_green]")
                hal_result = self.hal_bot.handle_command(text, sender_id, sender_name, effective_channel_id, is_dm_to_ai)
                if hal_result and isinstance(hal_result, dict):
                    response_text = hal_result['response']  # Extract just the response text
                    is_channel_message = hal_result.get('is_channel_message', False)
                    
                    log_widget.write(f"[bright_green]Sending HAL bot response to {sender_name}[/bright_green]")
                    if self.meshtastic_handler and self.meshtastic_handler.is_connected:
                        if is_channel_message:
                            # Send to channel
                            success, reason = self.meshtastic_handler.send_message(
                                response_text,  # Use the extracted response text
                                channel_index=effective_channel_id
                            )
                        else:
                            # Send as DM
                            success, reason = self.meshtastic_handler.send_message(
                                response_text,  # Use the extracted response text
                                destination_id_hex=sender_id,
                                channel_index=effective_channel_id
                            )
                        
                        if success:
                            log_widget.write(f"[green]HAL bot response sent successfully[/green]")
                            self.tx_count += 1
                            
                            # Add HAL bot response to conversation history
                            self.conversation_manager.add_message(
                                conv_id, 
                                "assistant", 
                                response_text, 
                                user_name="HAL9000", 
                                node_id=f"{self.meshtastic_handler.node_id:x}"
                            )
                            
                            # Update display if this is the current conversation
                            current_conv_id = f"ch_{self.current_chat_id}_broadcast" if self.current_chat_type == "channel" else self._dm_conv(self.current_chat_id)
                            if conv_id == current_conv_id:
                                self.load_conversation()
                            else:
                                self.update_channel_list()
                                self.update_node_list()
                                self.refresh_info_panel()
                        else:
                            log_widget.write(f"[red]Failed to send HAL bot response: {reason}[/red]")
                    return

            # Update node info with enhanced data
            self._update_node_info_from_message(sender_id, sender_name, effective_channel_id)
            
            # Get current conversation ID that is being viewed
            current_conv_id = f"ch_{self.current_chat_id}_broadcast" if self.current_chat_type == "channel" else self._dm_conv(self.current_chat_id)
            log_widget.write(f"[plum2]  Currently viewing conv_id: {current_conv_id}[/plum2]")

            # Update unread status and display
            if conv_id == current_conv_id:
                log_widget.write(f"[green3]  Incoming message for currently viewed chat. Reloading conversation.[/green3]")
                self.load_conversation() # This also handles unread count for the current conversation
            else:
                log_widget.write(f"[yellow3]  Incoming message for a background chat. Updating unread lists.[/yellow3]")
                # Update lists to show new unread status for background chats
                self.update_channel_list()
                self.update_node_list()
                self.refresh_info_panel()
            
            # Log raw message to app log
            log_widget.write(f"[yellow]MSG from {sender_name}: {text[:50].strip()}...[/yellow]")
            
            # rx counter update
            self.rx_count += 1
            
            # STEP 2: Decide if our AI should respond to this incoming message
            log_widget.write(f"[bright_magenta]AI Decision Logic: is_dm_to_ai={is_dm_to_ai}, channel_id={effective_channel_id}, active_ai_channel={self.active_channel_for_ai_posts}[/bright_magenta]")
            
            should_ai_respond = False
            skip_triage = False
            
            # Check if AI should respond
            if is_dm_to_ai:
                log_widget.write(f"[bright_magenta]  This is a DM to AI - AI WILL respond (skip_triage=True)[/bright_magenta]")
                should_ai_respond = True
                skip_triage = True  # Always skip triage for DMs
            elif effective_channel_id == self.active_channel_for_ai_posts and is_broadcast:
                log_widget.write(f"[bright_magenta]  This is on AI's active channel {self.active_channel_for_ai_posts} - checking probability...[/bright_magenta]")
                # Check cooldown
                now = time.time()
                if self.ai_cooldown > 0:
                    last_response_time = self.last_response_times.get(conv_id, 0)
                    time_since_last = now - last_response_time
                    if time_since_last < self.ai_cooldown:
                        log_widget.write(f"[bright_magenta]  Cooldown active: {time_since_last:.1f}s < {self.ai_cooldown}s - AI will NOT respond[/bright_magenta]")
                        should_ai_respond = False
                    else:
                        # Check probability
                        roll = random.random()
                        if roll <= self.ai_response_probability:
                            log_widget.write(f"[bright_magenta]  Probability check passed: {roll:.2f} <= {self.ai_response_probability} - AI WILL respond[/bright_magenta]")
                            should_ai_respond = True
                            skip_triage = not self.enable_ai_triage  # Use triage if enabled for channels
                        else:
                            log_widget.write(f"[bright_magenta]  Probability check failed: {roll:.2f} > {self.ai_response_probability} - AI will NOT respond[/bright_magenta]")
                            should_ai_respond = False
                else:
                    # No cooldown, just check probability
                    roll = random.random()
                    if roll <= self.ai_response_probability:
                        log_widget.write(f"[bright_magenta]  Probability check passed: {roll:.2f} <= {self.ai_response_probability} - AI WILL respond[/bright_magenta]")
                        should_ai_respond = True
                        skip_triage = not self.enable_ai_triage  # Use triage if enabled for channels
                    else:
                        log_widget.write(f"[bright_magenta]  Probability check failed: {roll:.2f} > {self.ai_response_probability} - AI will NOT respond[/bright_magenta]")
                        should_ai_respond = False
            else:
                log_widget.write(f"[bright_magenta]  Not a DM to AI and not on AI's active channel - AI will NOT respond[/bright_magenta]")
                should_ai_respond = False
            
            # Start AI worker if needed
            if should_ai_respond:
                log_widget.write(f"[bright_green]Starting AIProcessingWorker for {sender_name} in conv_id={conv_id}, skip_triage={skip_triage}[/bright_green]")
                processor = AIProcessingWorker(
                    self,
                    text,
                    sender_id,
                    sender_name,
                    effective_channel_id,
                    is_dm_to_ai,
                    conv_id,
                    self.url_pattern,
                    skip_triage=skip_triage
                )
                self.run_worker(
                    processor.run,
                    exclusive=True,
                    group="ai_proc",
                    thread=True
                )
            else:
                log_widget.write(f"[bright_red]AI will NOT respond to this message[/bright_red]")

        except Exception as e:
            log_error(f"Error in process_incoming_message: {e}")
            traceback.print_exc()
    
    def _dm_conv(self, remote_id: str) -> str:
        """Get conversation ID for a DM with another node"""
        if not self.ai_node_id:
            return f"dm_{remote_id}"
        # Sort IDs to ensure consistent conversation ID regardless of who initiated
        return f"dm_{'_'.join(sorted([self._norm_id(remote_id), self.ai_node_id]))}"

    def _norm_id(self, s: str) -> str:
        """Normalize node ID format"""
        return s.lstrip('!').lower() if isinstance(s, str) else str(s)

    def handle_ai_response(self, text, sender_id, sender_name, channel_id, is_dm, conv_id):
        """Handle AI response generation"""
        # Check cooldown
        now = time.time()
        if self.ai_cooldown > 0:
            last_response_time = self.last_response_times.get(conv_id, 0)
            if (now - last_response_time) < self.ai_cooldown:
                return
        
        # Check probability
        if random.random() > self.ai_response_probability:
            return
        
        try:
            # Get context
            context_history = self.conversation_manager.get_contextual_history(conv_id, for_user_name=sender_name)
            
            # Get AI response
            ai_response = self.ai_bridge.get_response(context_history, text, sender_name, sender_id, skip_triage=is_dm)
            
            if ai_response:
                # Apply delay
                if self.ai_min_delay >= 0 and self.ai_max_delay > self.ai_min_delay:
                    delay = random.uniform(self.ai_min_delay, self.ai_max_delay)
                    time.sleep(delay)
                
                # Save to conversation
                self.conversation_manager.add_message(conv_id, "assistant", ai_response)
                self.last_response_times[conv_id] = time.time()
                
                # Send message
                if is_dm:
                    success, reason = self.meshtastic_handler.send_message(
                        ai_response, destination_id_hex=sender_id, channel_index=channel_id
                    )
                else:
                    success, reason = self.meshtastic_handler.send_message(
                        ai_response, channel_index=channel_id
                    )
                
                # Update UI
                asyncio.run_coroutine_threadsafe(
                    self.update_after_ai_response(conv_id, success, reason, sender_name),
                    self.app_loop or asyncio.get_running_loop()
                )
        except Exception as e:
            pass
    
    async def update_after_ai_response(self, conv_id: str, success: bool, reason: str, sender_name: str) -> None:
        """Update UI after AI response"""
        # Reload conversation if current
        current_conv_id = f"ch_{self.current_chat_id}_broadcast" if self.current_chat_type == "channel" else self._dm_conv(self.current_chat_id)
        if conv_id == current_conv_id:
            self.load_conversation()
        
        # Log result
        log = self.query_one("#app-log", RichLog)
        if success:
            log.write(f"[cyan]AI replied to {sender_name}[/cyan]")
            
            # tx counter update
            self.tx_count += 1
        else:
            log.write(f"[red]Failed to send AI reply: {reason}[/red]")
    
    def action_focus_channel_list(self) -> None:
        """Focus the channel list"""
        self.query_one("#channel-list").focus()
    
    def action_focus_node_list(self) -> None:
        """Focus the node list"""
        self.query_one("#node-list").focus()
    
    def action_focus_messages(self) -> None:
        """Focus the message display"""
        self.query_one("#message-display").focus()

    def action_focus_input(self) -> None:
        """Focus the message input"""
        self.query_one("#message-input").focus()

    def refresh_info_panel(self):
        """Update the compact info panel with current stats."""
        try:
            # Calculate total unread from both channels and nodes
            total_channel_unread = sum(self.channel_unread.values())
            total_node_unread = sum(self.node_unread.values())
            total_unread = total_channel_unread + total_node_unread
            
            info_stats = {
                "Unread": total_unread,
                "Nodes": len(self.nodes),
                "RX": self.rx_count,
                "TX": self.tx_count,
            }
            # Future: add SNR / RSSI / Util: placeholders for now
            self.query_one("#info-panel", InfoPanel).set_stats(info_stats)
        except Exception as e:
            # Log the error but don't crash
            log = self.query_one("#app-log", RichLog)
            log.write(f"[red]Error updating info panel: {str(e)}[/red]")

    def update_channel_list(self) -> None:
        """Update the channel list widget with unread counts"""
        channel_list = self.query_one("#channel-list", ListView)
        channel_list.clear()
        
        # Add all channels with unread counts
        for channel_id in range(8):  # Assuming 8 channels
            channel_name = "Primary" if channel_id == 0 else f"Channel {channel_id}"
            conv_id = f"ch_{channel_id}_broadcast"
            # Get total messages in conversation
            messages = self.conversation_manager.load_conversation(conv_id)
            total_messages = len(messages)
            # Get last viewed count
            last_viewed = self.last_viewed_messages.get(conv_id, 0)
            # Calculate unread
            unread = max(0, total_messages - last_viewed)
            self.channel_unread[channel_id] = unread
            channel_list.append(ChannelListItem(channel_id, channel_name, unread))

    async def on_unmount(self, event: events.Unmount) -> None:
        """Called when app is unmounting"""
        # Save state before closing
        self.save_last_viewed_state()
        # Close Meshtastic handler
        if self.meshtastic_handler:
            self.meshtastic_handler.close()
        # No need to call super() as we're handling the event directly

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events"""
        if event.button.id == "force-ai-button":
            await self.force_ai_response()

    async def action_force_ai(self) -> None:
        """Action handler for force AI keyboard shortcut"""
        await self.force_ai_response()

    async def force_ai_response(self) -> None:
        """Force AI to respond to recent messages"""
        if not self.current_chat_id:
            self.query_one("#app-log", RichLog).write("[orange3]Cannot force AI response: No active chat.[/orange3]")
            return
        
        # Determine conversation ID
        if self.current_chat_type == "channel":
            conv_id = f"ch_{self.current_chat_id}_broadcast"
        else: # DM
            conv_id = self._dm_conv(self.current_chat_id)
        
        history = self.conversation_manager.load_conversation(conv_id)
        if not history:
            # It's possible to force a reply in an empty chat, so create a minimal context
            self.query_one("#app-log", RichLog).write("[grey53]Forcing AI response in empty chat.[/grey53]")
            # No history, AI will respond based on the prompt alone
        
        # Get the last 3-4 messages if history exists
        recent_messages = history[-4:] if history and len(history) >= 4 else (history if history else [])
        
        # Create a context from recent messages
        context_str = "\n".join([
            f"{msg.get('user_name', 'Unknown')}: {msg.get('content', '')}"
            for msg in recent_messages
        ])
        
        # Create a prompt for the AI
        if recent_messages:
            prompt = f"Recent conversation context:\n{context_str}\n\nPlease provide a natural response to this conversation."
        else:
            prompt = "Please provide a general, friendly opening message for this new conversation."

        is_current_chat_dm = self.current_chat_type == "dm"
        
        # If DM, the AIProcessingWorker's 'sender_id' param becomes the destination_id_hex.
        # If channel, it's context for the AI.
        target_node_id_for_worker = self.current_chat_id if is_current_chat_dm else "local_tui_user"

        # Log the details before starting worker
        log_msg = f"Forcing AI response. DM: {is_current_chat_dm}, Target: {target_node_id_for_worker}, Conv: {conv_id}"
        self.query_one("#app-log", RichLog).write(f"[grey53]{log_msg}[/grey53]")

        processor = AIProcessingWorker(
            self, # app instance
            prompt, # text for AI
            target_node_id_for_worker, # For DMs, this is the destination. For channels, context.
            "You (TUI)", # sender_name for AI context (who is asking for the response)
            self.active_channel_for_ai_posts, # channel_id to send on
            is_current_chat_dm, # is_dm flag
            conv_id, # conversation_id
            self.url_pattern,
            skip_triage=True  # Skip triage for forced responses
        )
        
        self.run_worker(
            processor.run, 
            exclusive=True,
            group="ai_proc",
            thread=True
        )

    def _update_node_info_from_message(self, sender_id: str, sender_name: str, channel_id: int) -> None:
        """Update node information when a message is received"""
        current_time = time.time()
        
        # Get or create node info
        if sender_id not in self.nodes:
            self.nodes[sender_id] = {
                'long_name': sender_name,
                'short_name': sender_name[:3].upper(),
                'last_heard': current_time,
                'first_heard': current_time,
                'is_favorite': False,
                'hops_away': None,
                'connection_type': self.app_config.MESHTASTIC_CONNECTION_TYPE,
                'node_id': sender_id,
                'user_role': 'Unknown',
                'model': 'Unknown',
                'signal_history': []
            }
        else:
            # Update last heard time
            self.nodes[sender_id]['last_heard'] = current_time
        
        # Try to get enhanced info from meshtastic interface
        if self.meshtastic_handler and self.meshtastic_handler.interface:
            interface = self.meshtastic_handler.interface
            if hasattr(interface, 'nodes') and interface.nodes:
                # Find the node in the interface by numeric ID
                for node_num, node_info in interface.nodes.items():
                    node_id_str = self._norm_id(f"{node_num:x}") if isinstance(node_num, int) else self._norm_id(node_num)
                    if node_id_str == sender_id:
                        # Update with enhanced data
                        self._update_node_from_interface(sender_id, node_info)
                        break

    def _update_node_from_interface(self, node_id: str, node_info: dict) -> None:
        """Update node information from meshtastic interface data"""
        if node_id not in self.nodes:
            return
            
        user = node_info.get('user', {})
        
        # Update basic info
        self.nodes[node_id].update({
            'long_name': user.get('longName', self.nodes[node_id].get('long_name', 'Unknown')),
            'short_name': user.get('shortName', self.nodes[node_id].get('short_name', 'UNK')),
            'user_role': user.get('role', 'Unknown'),
            'model': node_info.get('model', 'Unknown'),
            'battery_level': node_info.get('batteryLevel'),
            'uptime': node_info.get('uptime'),
            'hops_away': node_info.get('hopsAway'),
        })
        
        # Update signal info
        rssi = node_info.get('rssi')
        snr = node_info.get('snr')
        if rssi is None and 'lastPacketRssi' in node_info:
            rssi = node_info['lastPacketRssi']
        if snr is None and 'lastPacketSnr' in node_info:
            snr = node_info['lastPacketSnr']
        
        self.nodes[node_id]['rssi'] = rssi
        self.nodes[node_id]['snr'] = snr
        
        # Update GPS position
        position = node_info.get('position')
        if position:
            self.nodes[node_id]['position'] = {
                'latitude': position.get('latitude'),
                'longitude': position.get('longitude'),
                'altitude': position.get('altitude'),
            }
        
        # Update signal history with new packet
        current_time = time.time()
        new_packet = {
            'timestamp': current_time,
            'rssi': rssi,
            'snr': snr,
        }
        
        signal_history = self.nodes[node_id].get('signal_history', [])
        signal_history.append(new_packet)
        
        # Keep only last 10 packets
        if len(signal_history) > 10:
            signal_history = signal_history[-10:]
        
        self.nodes[node_id]['signal_history'] = signal_history

    def _update_ai_node_id(self):
        """Update AI node ID from meshtastic handler"""
        if self.meshtastic_handler and self.meshtastic_handler.node_id:
            old_ai_node_id = self.ai_node_id
            self.ai_node_id = self._norm_id(f"{self.meshtastic_handler.node_id:x}")
            if old_ai_node_id != self.ai_node_id:
                self.log_info(f"AI Node ID updated from '{old_ai_node_id}' to '{self.ai_node_id}'")
        else:
            self.ai_node_id = None

def main():
    """Main entry point"""
    # Set up logging to file
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler('interactive.backend.log', mode='a'),
            logging.StreamHandler()
        ]
    )
    logging.info("Starting interactive application")
    
    app = MeshtasticInteractive()
    app.run()

if __name__ == "__main__":
    main() 