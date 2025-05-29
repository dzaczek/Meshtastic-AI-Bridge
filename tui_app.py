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
        style = "reverse" if self.unread_count > 0 else ""
        yield Label(f"{icon} {name} ({self.node_id})", classes=style)

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

class MessageDisplay(ScrollableContainer):
    """Widget to display chat messages"""
    messages = reactive([])
    
    def compose(self) -> ComposeResult:
        """Compose the message display"""
        yield Container(id="message-container")
    
    def on_mount(self) -> None:
        """Called when widget is mounted"""
        self.update_messages()
    
    def watch_messages(self, messages: list) -> None:
        """React to message changes"""
        self.update_messages()
    
    def update_messages(self) -> None:
        """Update the displayed messages"""
        container = self.query_one("#message-container", Container)
        container.remove_children()
        
        for msg in self.messages:
            # Create message widget
            timestamp = datetime.fromtimestamp(msg.get('timestamp', time.time())).strftime("%H:%M:%S")
            sender = msg.get('user_name', 'Unknown')
            content = msg.get('content', '')
            role = msg.get('role', 'user')
            
            # Style based on role
            if role == 'assistant':
                style = "cyan"
                sender = "AI"
            elif sender == "You":
                style = "green"
            else:
                style = "yellow"
            
            # Create rich text
            message_text = Text()
            message_text.append(f"[{timestamp}] ", style="dim")
            message_text.append(f"{sender}: ", style=f"bold {style}")
            message_text.append(content)
            
            container.mount(Static(message_text))
        
        # Scroll to bottom
        self.scroll_end()

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
    
    MessageDisplay {
        height: 100%;
        background: $surface;
    }
    
    Input {
        dock: bottom;
        margin: 1;
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
    ]
    
    def __init__(self):
        super().__init__()
        self.app_config = config
        self.ai_bridge = AIBridge(self.app_config)
        self.conversation_manager = ConversationManager(self.app_config, self.ai_bridge)
        
        # State
        self.nodes: Dict[str, dict] = {}
        self.current_chat_type = "channel"
        self.current_chat_id = "0"
        self.message_queue = asyncio.Queue()
        
        # Unread message tracking
        self.unread_counts: Dict[str, int] = {}  # {conv_id: count}
        self.channel_unread: Dict[int, int] = {}  # {channel_id: count}
        self.node_unread: Dict[str, int] = {}  # {node_id: count}
        self.last_viewed_messages: Dict[str, int] = {}  # {conv_id: last_message_count}
        
        # Traffic counters for info stats
        self.rx_count: int = 0  # received messages this session
        self.tx_count: int = 0  # sent messages this session
        
        # <ADD> Reference to the asyncio event loop the UI will run on.
        # It is set here to a best-guess value immediately and then updated
        # during `on_mount` once the Textual App is fully running.
        self.app_loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_event_loop()
        
        # Helper for consistent node-id handling
        self._norm_id = lambda s: s.lstrip('!').lower() if isinstance(s, str) else s
        
        # Helper to build a stable DM conversation ID
        self._dm_conv = lambda remote: f"dm_{'_'.join(sorted([self._norm_id(remote), self.ai_node_id]))}"
        
        # Initialize Meshtastic handler
        self.meshtastic_handler = MeshtasticHandler(
            connection_type=self.app_config.MESHTASTIC_CONNECTION_TYPE,
            device_specifier=self.app_config.MESHTASTIC_DEVICE_SPECIFIER,
            on_message_received_callback=self.handle_meshtastic_message
        )
        
        # AI settings
        self.ai_node_id = self._norm_id(f"{self.meshtastic_handler.node_id:x}") if self.meshtastic_handler.node_id else None
        self.last_response_times = {}
        self.ai_response_probability = getattr(self.app_config, 'AI_RESPONSE_PROBABILITY', 0.85)
        self.ai_min_delay = getattr(self.app_config, 'AI_MIN_RESPONSE_DELAY_S', 2)
        self.ai_max_delay = getattr(self.app_config, 'AI_MAX_RESPONSE_DELAY_S', 8)
        self.ai_cooldown = getattr(self.app_config, 'AI_RESPONSE_COOLDOWN_S', 60)
        # AI Triage settings
        self.enable_ai_triage = getattr(self.app_config, 'ENABLE_AI_TRIAGE_ON_CHANNELS', False)
        self.triage_context_count = getattr(self.app_config, 'TRIAGE_CONTEXT_MESSAGE_COUNT', 3)
        
        # Load persisted last viewed state
        self.load_last_viewed_state()
    
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
            yield MessageDisplay(id="message-display")
            yield Input(placeholder="Type a message...", id="message-input")
        
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
                            'is_favorite': node_info.get('isFavorite', False)
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
        if self.current_chat_type == "channel":
            conv_id = f"ch_{self.current_chat_id}_broadcast"
        else:
            conv_id = self._dm_conv(self.current_chat_id)
        
        messages = self.conversation_manager.load_conversation(conv_id)
        message_display = self.query_one("#message-display", MessageDisplay)
        message_display.messages = messages
        
        # Update last viewed count and persist it
        self.last_viewed_messages[conv_id] = len(messages)
        self.save_last_viewed_state()
        
        # Update lists to reflect current unread status
        self.update_channel_list()
        self.update_node_list()
        self.refresh_info_panel()
    
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
        text = data['text']
        sender_id = self._norm_id(data['sender_id'])
        sender_name = data['sender_name']
        destination_id = self._norm_id(data['destination_id'])
        channel_id = data['channel_id']
        
        # Update node info
        if sender_id not in self.nodes:
            self.nodes[sender_id] = {
                'long_name': sender_name,
                'short_name': sender_name[:3].upper(),
                'last_heard': time.time(),
                'is_favorite': False
            }
        
        # Determine conversation
        effective_channel_id = channel_id if channel_id is not None else 0
        is_broadcast = destination_id.lower() == f"{meshtastic.BROADCAST_NUM:x}".lower()
        is_dm_to_ai = (self.ai_node_id and destination_id == self.ai_node_id)
        
        if is_dm_to_ai:
            conv_id = self._dm_conv(sender_id)
        else:
            conv_id = f"ch_{effective_channel_id}_broadcast"
        
        # Add message to conversation
        self.conversation_manager.add_message(conv_id, "user", text, user_name=sender_name, node_id=sender_id)
        
        # Get current conversation ID
        current_conv_id = f"ch_{self.current_chat_id}_broadcast" if self.current_chat_type == "channel" else self._dm_conv(self.current_chat_id)
        
        # Update unread status if message is not in current conversation
        if conv_id != current_conv_id:
            # Update lists to show new unread status
            self.update_channel_list()
            self.update_node_list()
            self.refresh_info_panel()
        
        # Update display if this message belongs to the conversation currently open
        if conv_id == current_conv_id:
            self.load_conversation()
        
        # Log message
        log = self.query_one("#app-log", RichLog)
        log.write(f"[yellow]Message from {sender_name}: {text[:50]}...[/yellow]")
        
        # rx counter update
        self.rx_count += 1
        
        # Decide if the AI should respond
        should_consider_reply = False
        if is_dm_to_ai:
            should_consider_reply = True
        elif is_broadcast and effective_channel_id == self.app_config.ACTIVE_MESHTASTIC_CHANNEL_INDEX:
            if self.enable_ai_triage:
                history_for_triage_raw = self.conversation_manager.load_conversation(conv_id)
                triage_context_messages = []
                for msg_entry in history_for_triage_raw[-(self.triage_context_count + 1):-1]:
                    if msg_entry.get("role") == "user":
                        name = msg_entry.get("user_name", f"Node-{msg_entry.get('node_id','????')}")
                        triage_context_messages.append(f"{name}: {msg_entry.get('content','')}")

                triage_decision = self.ai_bridge.should_main_ai_respond(
                    triage_context_messages, text, sender_name
                )
                log.write(f"[bright_yellow]Triage decision for {sender_name}: {'YES' if triage_decision else 'NO'}[/bright_yellow]")
                should_consider_reply = triage_decision
            else:
                should_consider_reply = True

        if should_consider_reply:
            threading.Thread(
                target=self.handle_ai_response,
                args=(text, sender_id, sender_name, effective_channel_id, is_dm_to_ai, conv_id),
                daemon=True
            ).start()
    
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

def main():
    """Main entry point"""
    app = MeshtasticTUI()
    app.run()

if __name__ == "__main__":
    main() 