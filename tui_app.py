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
                    except Exception as e:
                        web_analysis_summary = f"[Error analyzing URL: {str(e)}]"
                        log_error(f"[AIWorker] Error analyzing URL: {e}")
            ai_response = self.app.ai_bridge.get_response(
                context_history,
                self.text,
                self.sender_name,
                self.sender_id,
                web_analysis_summary=web_analysis_summary
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
                    log_info(f"[AIWorker] Sending DM reply to {self.sender_id} on channel {self.channel_id}")
                    success, reason = self.app.meshtastic_handler.send_message(
                        ai_response,
                        destination_id_hex=self.sender_id,
                        channel_index=self.channel_id
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
            import traceback; log_error(traceback.format_exc())

class NodeListItem(ListItem):
    """Custom list item for nodes"""
    def __init__(self, node_id: str, node_info: dict, is_favorite: bool = False, unread_count: int = 0):
        super().__init__()
        self.node_id = node_id
        self.node_info = node_info
        self.is_favorite = is_favorite
        self.unread_count = unread_count
        
    def compose(self) -> ComposeResult:
        """Compose the node item"""
        icon = "★" if self.is_favorite else "●"
        name = self.node_info.get('long_name', 'Unknown')
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
        
        # For default names, we can skip showing the full node ID since it's redundant
        if is_default_name:
            display_text = f"{icon} {name}{hop_indicator}"
        else:
            display_text = f"{icon} {name}{hop_indicator} !{node_id}"
        
        style = "reverse" if self.unread_count > 0 else ""
        yield Label(display_text, classes=style)

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

class MeshtasticTUI(App):
    """Main TUI Application using Textual"""
    
    CSS = """
    Screen {
        layout: grid;
        grid-size: 4 6;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-rows: auto 1fr 1fr 1fr 1fr 3;
    }
    
    Header {
        column-span: 4;
    }
    
    #left-panel {
        column-span: 1;
        row-span: 4;
        border: solid green;
        height: 100%;
        padding: 1;
    }
    
    #center-panel {
        column-span: 2;
        row-span: 4;
        border: solid yellow;
        height: 100%;
        overflow: hidden;
        layout: vertical;
    }
    
    #right-panel {
        column-span: 1;
        row-span: 4;
        border: solid blue;
        height: 100%;
        padding: 1;
    }
    
    #bottom-panel {
        column-span: 4;
        border: solid cyan;
        height: 100%;
        layout: horizontal;
    }
    
    #stats-box {
        width: 30%;
        padding: 1;
    }
    
    #log-box {
        width: 70%;
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
    
    /* Shrink channel list visually */
    #channel-list {
        height: 10;
    }

    #info-panel {
        height: 1fr;
        padding: 0 1;
    }
    
    /* Add styles for unread highlighting */
    .reverse {
        background: $accent;
        color: $surface;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("tab", "focus_next", "Next"),
        Binding("shift+tab", "focus_previous", "Previous"),
        Binding("c", "toggle_channel", "Channels"),
        Binding("n", "toggle_nodes", "Nodes"),
        Binding("f", "force_ai", "Force AI Response"),
        Binding("m", "focus_messages", "Focus Chat"),
    ]
    
    def __init__(self):
        super().__init__()
        self.app_config = config
        self.ai_bridge = AIBridge(self.app_config)
        self.conversation_manager = ConversationManager(self.app_config, self.ai_bridge)
        
        # Define helper functions first
        self._norm_id = lambda s: s.lstrip('!').lower() if isinstance(s, str) else s
        
        # URL pattern for web content analysis
        self.url_pattern = re.compile(r'https?://[^\s/$.?#].[^\s]*', re.IGNORECASE)
        
        # State
        self.nodes: Dict[str, dict] = {}
        self.current_chat_type = "channel"
        self.current_chat_id = "0"
        self.message_queue = asyncio.Queue()
        
        # Initialize Meshtastic handler
        self.meshtastic_handler = MeshtasticHandler(
            connection_type=self.app_config.MESHTASTIC_CONNECTION_TYPE,
            device_specifier=self.app_config.MESHTASTIC_DEVICE_SPECIFIER,
            on_message_received_callback=self.handle_meshtastic_message
        )
        
        # Get AI node ID
        self.ai_node_id = self._norm_id(f"{self.meshtastic_handler.node_id:x}") if self.meshtastic_handler.node_id else None
        
        # Define DM conversation helper after ai_node_id is set
        self._dm_conv = lambda remote: f"dm_{'_'.join(sorted([self._norm_id(remote), self.ai_node_id]))}"
        
        # AI settings
        self.active_channel_for_ai_posts = getattr(self.app_config, 'ACTIVE_MESHTASTIC_CHANNEL_INDEX', 0)
        self.last_response_times = {}
        self.ai_response_probability = getattr(self.app_config, 'AI_RESPONSE_PROBABILITY', 0.85)
        self.ai_min_delay = getattr(self.app_config, 'AI_MIN_RESPONSE_DELAY_S', 2)
        self.ai_max_delay = getattr(self.app_config, 'AI_MAX_RESPONSE_DELAY_S', 8)
        self.ai_cooldown = getattr(self.app_config, 'AI_RESPONSE_COOLDOWN_S', 60)
        # AI Triage settings
        self.enable_ai_triage = getattr(self.app_config, 'ENABLE_AI_TRIAGE_ON_CHANNELS', False)
        self.triage_context_count = getattr(self.app_config, 'TRIAGE_CONTEXT_MESSAGE_COUNT', 3)
        
        # Unread message tracking
        self.unread_counts: Dict[str, int] = {}  # {conv_id: count}
        self.channel_unread: Dict[int, int] = {}  # {channel_id: count}
        self.node_unread: Dict[str, int] = {}  # {node_id: count}
        self.last_viewed_messages: Dict[str, int] = {}  # {conv_id: last_message_count}
        
        # Traffic counters for info stats
        self.rx_count: int = 0  # received messages this session
        self.tx_count: int = 0  # sent messages this session
        
        # Reference to the asyncio event loop the UI will run on
        self.app_loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_event_loop()
        
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
        
        # Left panel - Channels
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
        
        # Center panel - Messages
        with Container(id="center-panel"):
            yield RichLog(id="message-display", wrap=True, markup=True, highlight=True, auto_scroll=True)
            with Horizontal(id="input-container"):
                yield Input(placeholder="Type a message...", id="message-input")
                yield Button("🤖 Force AI", id="force-ai-button")
        
        # Right panel - Nodes
        with Container(id="right-panel"):
            yield Label("Nodes", classes="title")
            yield ListView(id="node-list")
        
        # Bottom panel - Stats and Logs
        with Container(id="bottom-panel"):
            with Container(id="stats-box"):
                yield StatsPanel(id="stats")
            with Container(id="log-box"):
                yield RichLog(id="app-log", highlight=True, markup=True)
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app is mounted"""
        self.title = "Meshtastic AI Bridge"
        self.sub_title = "Modern TUI Interface"
        
        # Load initial nodes
        self.load_initial_nodes()
        
        # Set default channel
        self.load_conversation()
        
        # Start message processor
        self.set_interval(0.1, self.process_message_queue)
        
        # Update stats
        self.update_stats()
        
        # Log startup
        self.query_one("#app-log", RichLog).write("[green]TUI started successfully[/green]")
        
        # Refresh the stored loop – now guaranteed to be the correct one used by Textual.
        self.app_loop = asyncio.get_running_loop()
        
        # Initial info panel update
        self.refresh_info_panel()
        
        # Focus the message display for immediate scrolling
        self.query_one("#message-display", RichLog).focus()
    
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
                        
                        self.nodes[node_id_str] = {
                            'long_name': user.get('longName', 'Unknown'),
                            'short_name': user.get('shortName', 'UNK'),
                            'last_heard': node_info.get('lastHeard', time.time()),
                            'is_favorite': node_info.get('isFavorite', False),
                            'hops_away': node_info.get('hopsAway', None)  # Add hop count if available
                        }
                
                self.update_node_list()
    
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
        
        # Focus the message display to enable scrolling
        self.call_after_refresh(lambda: message_display.focus())
    
    def update_stats(self) -> None:
        """Update stats panel"""
        stats = self.query_one("#stats", StatsPanel)
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
        else:
            log = self.query_one("#app-log", RichLog)
            log.write(f"[red]Failed to send: {reason}[/red]")
    
    def handle_meshtastic_message(self, text, sender_id, sender_name, destination_id, channel_id):
        """Handle incoming Meshtastic messages"""
        # Queue for async processing
        asyncio.run_coroutine_threadsafe(
            self.message_queue.put({
                'text': text,
                'sender_id': self._norm_id(sender_id),
                'sender_name': sender_name,
                'destination_id': self._norm_id(destination_id),
                'channel_id': channel_id
            }),
            self.app_loop or asyncio.get_running_loop()
        )
    
    async def process_message_queue(self) -> None:
        """Process queued messages"""
        try:
            while not self.message_queue.empty():
                data = await self.message_queue.get()
                await self.process_incoming_message(data)
        except Exception:
            pass
    
    async def process_incoming_message(self, data: dict) -> None:
        """Process an incoming message"""
        log_widget = self.query_one("#app-log", RichLog)
        log_widget.write(f"[deep_sky_blue1]Processing incoming message data: {data!r}[/deep_sky_blue1]")

        text = data['text']
        sender_id = self._norm_id(data['sender_id'])
        sender_name = data['sender_name']
        destination_id = self._norm_id(data['destination_id'])
        channel_id = data['channel_id']
        
        log_widget.write(f"[sky_blue1]  Parsed: sender_id={sender_id}, sender_name='{sender_name}', dest_id={destination_id}, ch_id={channel_id}[/sky_blue1]")

        # Update node info
        if sender_id not in self.nodes:
            self.nodes[sender_id] = {
                'long_name': sender_name,
                'short_name': sender_name[:3].upper(),
                'last_heard': time.time(),
                'is_favorite': False,
                'hops_away': None  # Will be updated if available from meshtastic interface
            }
        else:
            # Update last heard time
            self.nodes[sender_id]['last_heard'] = time.time()
        
        # Try to get hop count from meshtastic interface if available
        if self.meshtastic_handler and self.meshtastic_handler.interface:
            interface = self.meshtastic_handler.interface
            if hasattr(interface, 'nodes') and interface.nodes:
                # Find the node in the interface by numeric ID
                for node_num, node_info in interface.nodes.items():
                    node_id_str = self._norm_id(f"{node_num:x}") if isinstance(node_num, int) else self._norm_id(node_num)
                    if node_id_str == sender_id and 'hopsAway' in node_info:
                        self.nodes[sender_id]['hops_away'] = node_info.get('hopsAway')
        
        # Determine conversation
        effective_channel_id = channel_id if channel_id is not None else 0
        is_broadcast = destination_id.lower() == f"{meshtastic.BROADCAST_NUM:x}".lower() or destination_id.lower() == "broadcast"
        is_dm_to_ai = (self.ai_node_id and destination_id == self.ai_node_id)
        
        log_widget.write(f"[sky_blue1]  Flags: is_broadcast={is_broadcast}, is_dm_to_ai={is_dm_to_ai}, self.ai_node_id={self.ai_node_id}[/sky_blue1]")

        if is_dm_to_ai:
            conv_id = self._dm_conv(sender_id) # DM with the sender of this message
        else:
            conv_id = f"ch_{effective_channel_id}_broadcast"
        
        log_widget.write(f"[cyan1]  Calculated conv_id: {conv_id} (for sender_id: {sender_id})[/cyan1]")

        # Add message to conversation
        # For incoming messages, the "role" is always "user" from the perspective of this conversation history
        # user_name is the sender_name from the packet
        log_widget.write(f"[cyan1]  Adding to ConversationManager: conv_id='{conv_id}', role='user', user_name='{sender_name}', node_id='{sender_id}'[/cyan1]")
        self.conversation_manager.add_message(conv_id, "user", text, user_name=sender_name, node_id=sender_id)
        
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
            ai_response = self.ai_bridge.get_response(context_history, text, sender_name, sender_id)
            
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
    
    def action_toggle_channel(self) -> None:
        """Focus channel list"""
        self.query_one("#channel-list").focus()
    
    def action_toggle_nodes(self) -> None:
        """Focus node list"""
        self.query_one("#node-list").focus()
    
    def action_focus_messages(self) -> None:
        """Focus the message display for scrolling"""
        self.query_one("#message-display", RichLog).focus()

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

def main():
    """Main entry point"""
    # Set up logging to file
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler('tui.backend.log', mode='a'),
            logging.StreamHandler()
        ]
    )
    logging.info("Starting TUI application")
    
    app = MeshtasticTUI()
    app.run()

if __name__ == "__main__":
    main() 