#!/usr/bin/env python3
"""
Chat UI - Modern Textual Interface for Chat Analysis
Features:
- Load and analyze chat history from JSON files
- Display message statistics per user and channel
- Show user message percentages in channels
- Color-coded messages per user
- Beautiful chat visualization
- Menu for selecting history files
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Input, ListView, ListItem, Label, Button, Log, RichLog
from textual.reactive import reactive
from textual.binding import Binding
from textual.message import Message
from textual import events
from datetime import datetime
import json
import os
from pathlib import Path
from collections import defaultdict
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.console import RenderableType
import glob
from typing import Dict, List, Optional, Tuple

class HistoryFileItem(ListItem):
    """Custom list item for history files"""
    def __init__(self, file_path: str, stats: dict):
        super().__init__()
        self.file_path = file_path
        self.stats = stats
        
    def compose(self) -> ComposeResult:
        """Compose the history file item"""
        file_name = os.path.basename(self.file_path)
        total_messages = self.stats.get('total_messages', 0)
        unique_users = len(self.stats.get('user_stats', {}))
        yield Label(f"{file_name} ({total_messages} msgs, {unique_users} users)")

class UserStatsPanel(Static):
    """Widget to display user statistics"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stats = {}
        
    def set_stats(self, stats: dict):
        """Update the statistics display"""
        self.stats = stats
        self.refresh()
        
    def render(self) -> RenderableType:
        """Render the statistics panel"""
        if not self.stats:
            return Panel("No statistics available", title="User Statistics")
            
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("User", style="cyan")
        table.add_column("Messages", justify="right", style="green")
        table.add_column("Percentage", justify="right", style="yellow")
        
        total_messages = self.stats.get('total_messages', 0)
        user_stats = self.stats.get('user_stats', {})
        
        # Sort users by message count
        sorted_users = sorted(user_stats.items(), key=lambda x: x[1]['count'], reverse=True)
        
        for user, data in sorted_users:
            count = data['count']
            percentage = (count / total_messages * 100) if total_messages > 0 else 0
            table.add_row(
                user,
                str(count),
                f"{percentage:.1f}%"
            )
            
        return Panel(table, title="User Statistics")

class ChannelStatsPanel(Static):
    """Widget to display channel statistics"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stats = {}
        
    def set_stats(self, stats: dict):
        """Update the channel statistics"""
        self.stats = stats
        self.refresh()
        
    def render(self) -> RenderableType:
        """Render the channel statistics panel"""
        if not self.stats:
            return Panel("No channel statistics available", title="Channel Statistics")
            
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Channel", style="cyan")
        table.add_column("Messages", justify="right", style="green")
        table.add_column("Users", justify="right", style="yellow")
        
        channel_stats = self.stats.get('channel_stats', {})
        
        # Sort channels by message count
        sorted_channels = sorted(channel_stats.items(), key=lambda x: x[1]['total_messages'], reverse=True)
        
        for channel, data in sorted_channels:
            table.add_row(
                f"Channel {channel}",
                str(data['total_messages']),
                str(len(data['users']))
            )
            
        return Panel(table, title="Channel Statistics")

class MessageDisplay(ScrollableContainer):
    """Widget to display chat messages"""
    messages = reactive([])
    user_colors = {}
    available_colors = [
        "bright_red", "bright_green", "bright_yellow", "bright_blue",
        "bright_magenta", "bright_cyan", "orange3", "spring_green1",
        "deep_sky_blue1", "medium_purple1"
    ]
    
    def get_user_color(self, user: str) -> str:
        """Get a consistent color for a user"""
        if user not in self.user_colors:
            self.user_colors[user] = self.available_colors[len(self.user_colors) % len(self.available_colors)]
        return self.user_colors[user]
    
    def compose(self) -> ComposeResult:
        """Compose the message display"""
        yield RichLog(id="message-log", wrap=True, markup=True, highlight=True, auto_scroll=True)
    
    def on_mount(self) -> None:
        """Called when widget is mounted"""
        self.update_messages()
    
    def watch_messages(self, messages: list) -> None:
        """React to message changes"""
        self.update_messages()
    
    def update_messages(self) -> None:
        """Update the displayed messages"""
        message_log = self.query_one("#message-log", RichLog)
        message_log.clear()
        
        if not self.messages:
            message_log.write("[dim italic]No messages to display...[/dim italic]")
            return
        
        for msg in self.messages:
            # Create message widget
            timestamp = datetime.fromtimestamp(msg.get('timestamp', 0)).strftime("%Y-%m-%d %H:%M:%S")
            sender = msg.get('user_name', 'Unknown')
            content = msg.get('content', '')
            role = msg.get('role', 'user')
            
            # Style based on role and user
            if role == 'assistant':
                style = "cyan"
                sender = "AI"
            else:
                style = self.get_user_color(sender)
            
            # Write message with markup
            message_log.write(f"[dim]{timestamp}[/dim] [{style} bold]{sender}:[/{style} bold] {content}")
        
        # Scroll to bottom
        message_log.scroll_end(animate=False)

class ChatAnalysisApp(App):
    """Main Chat Analysis Application"""
    
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 3fr;
        grid-rows: 1fr;
    }
    
    Header {
        dock: top;
    }
    
    Footer {
        dock: bottom;
    }
    
    #left-panel {
        height: 100%;
        border-right: solid $accent;
        layout: vertical;
    }
    
    #file-list {
        height: 30%;
        border-bottom: solid $accent;
        background: $surface;
    }
    
    #stats-container {
        height: 70%;
        layout: vertical;
        background: $surface;
    }
    
    #user-stats {
        height: 50%;
        border-bottom: solid $accent;
    }
    
    #channel-stats-panel {
        height: 50%;
    }
    
    #right-panel {
        height: 100%;
        layout: vertical;
    }
    
    #message-display {
        height: 100%;
        border: solid $accent;
        background: $surface;
        overflow-y: scroll;
        scrollbar-gutter: stable;
        scrollbar-size: 1 1;
    }
    
    #message-display:focus {
        border: thick $accent;
    }
    
    #message-log {
        height: 100%;
        background: $surface;
        padding: 1;
    }
    
    ListView {
        height: 100%;
        background: $surface;
    }
    
    .title {
        text-align: center;
        padding: 1;
        background: $accent;
        color: $text;
        text-style: bold;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("f", "focus_file_list", "Files"),
        Binding("m", "focus_messages", "Messages"),
        Binding("s", "focus_stats", "Stats"),
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
    ]
    
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.messages = []
        self.stats = {}
        self.channel_stats = {}
        
    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        
        # Left panel - File list and stats
        with Container(id="left-panel"):
            with Container(id="file-list"):
                yield Label("History Files", classes="title")
                yield ListView(id="history-list")
            
            with Container(id="stats-container"):
                yield UserStatsPanel(id="user-stats")
                yield ChannelStatsPanel(id="channel-stats-panel")
        
        # Right panel - Messages
        with Container(id="right-panel"):
            with Container(id="message-display"):
                yield MessageDisplay(id="messages")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app is mounted"""
        self.title = "Chat Analysis"
        self.sub_title = "Message History Viewer"
        
        # Load available history files
        self.load_history_files()
        
        # Focus the file list
        self.query_one("#history-list").focus()
    
    def load_history_files(self) -> None:
        """Load available history files"""
        history_list = self.query_one("#history-list", ListView)
        history_list.clear()
        
        # Find all JSON files in the current directory
        json_files = glob.glob("*.json")
        
        for file_path in json_files:
            try:
                # Load file to get basic stats
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        stats = self.calculate_basic_stats(data)
                        history_list.append(HistoryFileItem(file_path, stats))
            except Exception as e:
                self.log.error(f"Error loading {file_path}: {e}")
    
    def calculate_basic_stats(self, messages: list) -> dict:
        """Calculate basic statistics for a history file"""
        stats = {
            'total_messages': len(messages),
            'user_stats': defaultdict(lambda: {'count': 0}),
            'channel_stats': defaultdict(lambda: {'total_messages': 0, 'users': set()})
        }
        
        for msg in messages:
            user = msg.get('user_name', 'Unknown')
            channel = msg.get('channel_id', '0')
            role = msg.get('role', 'user')
            
            # Skip system messages
            if role == 'system':
                continue
                
            # Update user stats
            stats['user_stats'][user]['count'] += 1
            
            # Update channel stats
            stats['channel_stats'][channel]['total_messages'] += 1
            stats['channel_stats'][channel]['users'].add(user)
        
        return stats
    
    def calculate_detailed_stats(self, messages: list) -> Tuple[dict, dict]:
        """Calculate detailed statistics for the current file"""
        user_stats = defaultdict(lambda: {'count': 0, 'channels': defaultdict(int)})
        channel_stats = defaultdict(lambda: {'total_messages': 0, 'users': set(), 'user_messages': defaultdict(int)})
        
        for msg in messages:
            user = msg.get('user_name', 'Unknown')
            channel = msg.get('channel_id', '0')
            role = msg.get('role', 'user')
            
            # Skip system messages
            if role == 'system':
                continue
                
            # Update user stats
            user_stats[user]['count'] += 1
            user_stats[user]['channels'][channel] += 1
            
            # Update channel stats
            channel_stats[channel]['total_messages'] += 1
            channel_stats[channel]['users'].add(user)
            channel_stats[channel]['user_messages'][user] += 1
        
        return dict(user_stats), dict(channel_stats)
    
    def load_history_file(self, file_path: str) -> None:
        """Load and analyze a history file"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    raise ValueError("Invalid history file format")
                
                self.messages = data
                self.current_file = file_path
                
                # Calculate statistics
                user_stats, channel_stats = self.calculate_detailed_stats(data)
                
                # Update displays
                message_display = self.query_one("#messages", MessageDisplay)
                message_display.messages = data
                
                user_stats_panel = self.query_one("#user-stats", UserStatsPanel)
                user_stats_panel.set_stats({
                    'total_messages': len(data),
                    'user_stats': user_stats
                })
                
                channel_stats_panel = self.query_one("#channel-stats-panel", ChannelStatsPanel)
                channel_stats_panel.set_stats({
                    'channel_stats': channel_stats
                })
                
                self.title = f"Chat Analysis - {os.path.basename(file_path)}"
                
        except Exception as e:
            self.log.error(f"Error loading {file_path}: {e}")
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection"""
        if isinstance(event.item, HistoryFileItem):
            self.load_history_file(event.item.file_path)
    
    def action_refresh(self) -> None:
        """Refresh the current view"""
        if self.current_file:
            self.load_history_file(self.current_file)
        else:
            self.load_history_files()
    
    def action_focus_file_list(self) -> None:
        """Focus the file list"""
        self.query_one("#history-list").focus()
    
    def action_focus_messages(self) -> None:
        """Focus the message display"""
        self.query_one("#messages").focus()
    
    def action_focus_stats(self) -> None:
        """Focus the stats panel"""
        self.query_one("#user-stats").focus()

def main():
    """Main entry point"""
    app = ChatAnalysisApp()
    app.run()

if __name__ == "__main__":
    main()

