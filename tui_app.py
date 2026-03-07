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
from message_router import MessageRouter, RouteResult
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
import math

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
    """Custom list item for nodes with connection type icons"""
    # Connection type icons
    ICONS = {
        'radio':    ("📡", "R"),   # LoRa radio
        'mqtt':     ("☁️",  "M"),   # MQTT / internet
        'favorite': ("★",  "*"),   # Favorite
    }

    def __init__(self, node_id: str, node_info: dict, is_favorite: bool = False, unread_count: int = 0):
        super().__init__()
        self.node_id = node_id
        self.node_info = node_info
        self.is_favorite = is_favorite
        self.unread_count = unread_count

    @staticmethod
    def _icon(key: str) -> str:
        uni, fallback = NodeListItem.ICONS.get(key, ("?", "?"))
        try:
            uni.encode('utf-8').decode('utf-8')
            return uni
        except UnicodeError:
            return fallback

    def _sanitize_name(self, name: str) -> str:
        if not name:
            return "Unknown"
        name = re.sub(r'\[.*?\]', '', name)
        name = ''.join(c for c in name if c.isprintable() or c.isspace())
        return re.sub(r'\s+', ' ', name).strip()

    def compose(self) -> ComposeResult:
        name = self._sanitize_name(self.node_info.get('long_name', 'Unknown'))
        node_id = self.node_id
        is_mqtt = self.node_info.get('connection_type') == 'tcp'

        # Connection icon
        if self.is_favorite:
            conn_icon = self._icon('favorite')
        elif is_mqtt:
            conn_icon = self._icon('mqtt')
        else:
            conn_icon = self._icon('radio')

        # Default Meshtastic name check
        is_default_name = False
        if name.startswith("Meshtastic ") and len(name) > 11:
            name_suffix = name[11:].strip()
            if node_id.endswith(name_suffix.lower()):
                is_default_name = True
                name = f"Node {name_suffix}"

        # Hop count
        hops_away = self.node_info.get('hops_away')
        if hops_away is not None:
            hop_indicator = " [D]" if hops_away == 0 else f" [{hops_away}hop]"
        else:
            hop_indicator = ""

        # Last heard age (rounded to full minutes/hours)
        last_heard = self.node_info.get('last_heard', 0)
        if last_heard:
            age_s = int(time.time() - last_heard)
            if age_s < 120:
                age_str = "1m"
            elif age_s < 3600:
                age_str = f"{round(age_s / 60)}m"
            elif age_s < 86400:
                age_str = f"{round(age_s / 3600)}h"
            else:
                age_str = f"{round(age_s / 86400)}d"
            age_tag = f" {age_str}"
        else:
            age_tag = ""

        if is_default_name:
            display_text = f"{conn_icon}{age_tag} {name}{hop_indicator}"
        else:
            display_text = f"{conn_icon}{age_tag} {name}{hop_indicator}"

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
        badge = f" ({self.unread_count})" if self.unread_count > 0 else ""
        style = "unread" if self.unread_count > 0 else ""
        yield Label(f"# {self.channel_name}{badge}", classes=style, markup=False)

class InfoPanel(Static):
    """Compact status bar for the sidebar bottom."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stats: dict | None = None

    def set_stats(self, stats_dict: dict):
        self.stats = stats_dict
        self.refresh()

    def render(self) -> RenderableType:  # type: ignore[override]
        if not self.stats:
            return Text(" -- ", style="dim")
        parts = []
        for key, val in self.stats.items():
            if key == "Status":
                style = "bold green" if val == "ON" else "bold red"
                parts.append(Text(f"{val}", style=style))
            else:
                parts.append(Text(f"{key}:{val}", style="dim"))
        line = Text(" ")
        for p in parts:
            line.append(p)
            line.append("  ")
        return line

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
            return Panel("[dim]Select a node\nto view stats[/dim]", title="Node Info", border_style="dim")

        # Create main table
        table = Table(show_header=False, box=None, expand=True, padding=(0, 1))
        table.add_column("K", style="bold #58a6ff", width=10, no_wrap=True)
        table.add_column("V", style="#e6edf3")

        node_id = self.node_data.get('node_id', 'Unknown')
        long_name = self.node_data.get('long_name', 'Unknown')
        short_name = self.node_data.get('short_name', 'UNK')

        table.add_row("Name", f"[bold #e6edf3]{long_name}[/]")
        table.add_row("ID", f"[#8b949e]!{node_id}[/]")
        table.add_row("Short", short_name)

        user_role = self.node_data.get('user_role', 'Unknown')
        if user_role != 'Unknown':
            table.add_row("Role", user_role)

        # Connection info
        connection_type = self.node_data.get('connection_type', 'radio')
        hops_away = self.node_data.get('hops_away')
        conn_icon = "[#f0883e]MQTT[/]" if connection_type == 'tcp' else "[#3fb950]RADIO[/]"
        hops_str = f" {hops_away}h" if hops_away is not None else ""
        table.add_row("Link", f"{conn_icon}{hops_str}")

        # Last heard
        last_heard = self.node_data.get('last_heard')
        if last_heard:
            table.add_row("Heard", f"[#e6edf3]{self._format_time_ago(last_heard)}[/]")

        # Signal
        current_rssi = self.node_data.get('rssi')
        current_snr = self.node_data.get('snr')
        if current_rssi is not None:
            color = "#3fb950" if current_rssi > -100 else "#f0883e" if current_rssi > -115 else "#f85149"
            table.add_row("RSSI", f"[{color}]{current_rssi} dBm[/]")
        if current_snr is not None:
            color = "#3fb950" if current_snr > 5 else "#f0883e" if current_snr > 0 else "#f85149"
            table.add_row("SNR", f"[{color}]{current_snr} dB[/]")

        # Signal history (compact)
        signal_history = self.node_data.get('signal_history', [])
        if signal_history:
            table.add_row("", "")
            table.add_row("[bold #58a6ff]History[/]", "")
            for packet in signal_history[-3:]:
                rssi = packet.get('rssi')
                snr = packet.get('snr')
                t = self._format_time_ago(packet.get('timestamp', 0))
                r = f"{rssi}" if rssi is not None else "-"
                s = f"{snr}" if snr is not None else "-"
                table.add_row(f"  {t}", f"[#8b949e]{r}/{s}[/]")

        # GPS
        position = self.node_data.get('position')
        if position:
            lat = position.get('latitude')
            lon = position.get('longitude')
            alt = position.get('altitude')
            if lat is not None and lon is not None:
                table.add_row("", "")
                table.add_row("GPS", f"[#e6edf3]{lat:.4f},{lon:.4f}[/]")
                if alt is not None:
                    table.add_row("Alt", f"{alt}m")

        # Model / Battery
        model = self.node_data.get('model', 'Unknown')
        if model != 'Unknown':
            table.add_row("Model", f"[#8b949e]{model}[/]")

        battery = self.node_data.get('battery_level')
        if battery is not None:
            color = "#3fb950" if battery > 50 else "#f0883e" if battery > 20 else "#f85149"
            table.add_row("Batt", f"[{color}]{battery}%[/]")

        uptime = self.node_data.get('uptime')
        if uptime:
            table.add_row("Up", f"[#8b949e]{uptime}[/]")

        return Panel(table, title=f"[bold #58a6ff]{short_name}[/]", border_style="#30363d")
    
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

class MeshMapPanel(Static):
    """ASCII map of mesh nodes based on GPS coordinates"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.nodes_data = {}
        self.selected_node_id = None
        self.map_filter = "all"  # "all", "0hop", "1hop", "2hop", "3hop+", "1h", "6h", "24h"

    def set_nodes(self, nodes: dict, selected: str = None, map_filter: str = "all"):
        self.nodes_data = nodes
        self.selected_node_id = selected
        self.map_filter = map_filter
        self.refresh()

    def _filter_nodes(self) -> dict:
        filtered = {}
        now = time.time()
        for nid, info in self.nodes_data.items():
            pos = info.get('position')
            if not pos or pos.get('latitude') is None or pos.get('longitude') is None:
                continue
            # Apply filter
            f = self.map_filter
            if f == "all":
                pass
            elif f == "0hop":
                if info.get('hops_away') != 0:
                    continue
            elif f == "1hop":
                if (info.get('hops_away') or 999) > 1:
                    continue
            elif f == "2hop":
                if (info.get('hops_away') or 999) > 2:
                    continue
            elif f == "3hop+":
                if (info.get('hops_away') or 0) < 3:
                    continue
            elif f == "1h":
                if now - info.get('last_heard', 0) > 3600:
                    continue
            elif f == "6h":
                if now - info.get('last_heard', 0) > 21600:
                    continue
            elif f == "24h":
                if now - info.get('last_heard', 0) > 86400:
                    continue
            filtered[nid] = info
        return filtered

    def render(self) -> RenderableType:
        nodes = self._filter_nodes()
        if not nodes:
            return Panel(
                f"[dim]No nodes with GPS data\nFilter: {self.map_filter}[/dim]\n\n"
                "[dim]F9=filter  Nodes need GPS position to appear on map[/dim]",
                title="[bold #58a6ff]Mesh Map[/]", border_style="#30363d"
            )

        # Collect coordinates
        lats = [n['position']['latitude'] for n in nodes.values()]
        lons = [n['position']['longitude'] for n in nodes.values()]

        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # Add padding
        lat_pad = max((max_lat - min_lat) * 0.1, 0.001)
        lon_pad = max((max_lon - min_lon) * 0.1, 0.001)
        min_lat -= lat_pad
        max_lat += lat_pad
        min_lon -= lon_pad
        max_lon += lon_pad

        # Map dimensions (fit in panel)
        map_w = 60
        map_h = 30

        # Build grid
        grid = [[' ' for _ in range(map_w)] for _ in range(map_h)]
        node_positions = {}

        lat_range = max_lat - min_lat if max_lat != min_lat else 0.01
        lon_range = max_lon - min_lon if max_lon != min_lon else 0.01

        for nid, info in nodes.items():
            lat = info['position']['latitude']
            lon = info['position']['longitude']
            # Map to grid (lat is inverted - higher lat = top)
            x = int((lon - min_lon) / lon_range * (map_w - 1))
            y = int((max_lat - lat) / lat_range * (map_h - 1))
            x = max(0, min(map_w - 1, x))
            y = max(0, min(map_h - 1, y))
            node_positions[nid] = (x, y)

            is_mqtt = info.get('connection_type') == 'tcp'
            hops = info.get('hops_away')
            if nid == self.selected_node_id:
                ch = '@'
            elif hops == 0:
                ch = 'O'
            elif is_mqtt:
                ch = 'M'
            else:
                ch = '*'
            grid[y][x] = ch

        # Build output with Rich Text
        lines = []
        # Header
        filter_str = self.map_filter.upper()
        lines.append(f"[bold #58a6ff]Filter:[/] [#e6edf3]{filter_str}[/]  "
                      f"[bold #58a6ff]Nodes:[/] [#e6edf3]{len(nodes)}[/]  "
                      f"[dim]F9=cycle filter[/]")
        lines.append("")

        # Render grid
        for row in grid:
            line_chars = []
            for ch in row:
                if ch == '@':
                    line_chars.append(f'[bold #f0883e]{ch}[/]')
                elif ch == 'O':
                    line_chars.append(f'[bold #3fb950]{ch}[/]')
                elif ch == 'M':
                    line_chars.append(f'[#f0883e]{ch}[/]')
                elif ch == '*':
                    line_chars.append(f'[#58a6ff]{ch}[/]')
                else:
                    line_chars.append(f'[#21262d].[/]')
            lines.append(''.join(line_chars))

        lines.append("")
        # Legend
        lines.append("[bold #3fb950]O[/]=direct  [#58a6ff]*[/]=radio  "
                      "[#f0883e]M[/]=mqtt  [bold #f0883e]@[/]=selected")

        # Node labels (closest to their position)
        lines.append("")
        for nid, info in nodes.items():
            name = info.get('short_name', nid[:4])
            hops = info.get('hops_away')
            hop_s = f" [{hops}hop]" if hops is not None else ""
            last = info.get('last_heard', 0)
            age = ""
            if last:
                age_s = int(time.time() - last)
                if age_s < 120:
                    age = " 1m"
                elif age_s < 3600:
                    age = f" {round(age_s/60)}m"
                elif age_s < 86400:
                    age = f" {round(age_s/3600)}h"
                else:
                    age = f" {round(age_s/86400)}d"

            is_sel = nid == self.selected_node_id
            style = "bold #f0883e" if is_sel else "#8b949e"
            lines.append(f"[{style}]{name}{hop_s}{age}[/]")

        return Panel('\n'.join(lines), title="[bold #58a6ff]Mesh Map[/]", border_style="#30363d")


class MeshtasticInteractive(App):
    """Main Interactive Application using Textual"""

    TITLE = "Eva  Mesh AI"
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("f5", "force_ai", "AI Reply", show=True),
        Binding("f1", "focus_channel_list", "Channels", show=True),
        Binding("f2", "focus_node_list", "Nodes", show=True),
        Binding("f3", "focus_messages", "Chat", show=True),
        Binding("f4", "focus_input", "Input", show=True),
        Binding("f6", "toggle_logs", "Logs", show=True),
        Binding("f7", "cycle_node_filter", "Filter", show=True),
        Binding("f8", "cycle_hop_filter", "Hops", show=True),
        Binding("f9", "toggle_map", "Map", show=True),
        Binding("f10", "cycle_map_filter", "MapFlt", show=True),
        Binding("escape", "focus_input", "Input"),
    ]
    current_conversation_id = reactive(None, layout=True)
    sidebar_conversations = reactive([], layout=True)
    show_logs = reactive(False)
    node_filter = reactive("all")  # "all", "radio", "mqtt"
    hop_filter = reactive("all")  # "all", "0", "1", "2", "3+"
    show_map = reactive(False)
    map_filter = reactive("all")  # "all", "0hop", "1hop", "2hop", "3hop+", "1h", "6h", "24h"

    CSS = """
    Screen {
        background: #0d1117;
        color: #c9d1d9;
    }

    Header {
        background: #161b22;
        color: #58a6ff;
        dock: top;
        height: 1;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
    }

    /* ---- Main grid ---- */
    #app-grid {
        layout: horizontal;
        height: 1fr;
    }

    /* ---- Sidebar ---- */
    #sidebar {
        width: 34;
        min-width: 28;
        background: #0d1117;
        border-right: vkey #30363d;
        layout: vertical;
    }

    .sidebar-label {
        color: #8b949e;
        text-style: bold;
        padding: 0 1;
        margin-top: 1;
        height: 1;
    }

    #channel-list {
        height: auto;
        max-height: 12;
        background: #0d1117;
        margin: 0;
        padding: 0;
    }

    #node-list {
        height: 1fr;
        background: #0d1117;
        margin: 0;
        padding: 0;
    }

    #status-bar {
        height: 3;
        dock: bottom;
        background: #161b22;
        padding: 0 1;
        border-top: solid #30363d;
    }

    ListView {
        background: #0d1117;
        scrollbar-size: 1 1;
    }

    ListView > ListItem {
        padding: 0 1;
        height: 1;
        background: #0d1117;
    }

    ListView > ListItem:hover {
        background: #161b22;
    }

    ListView > ListItem.-selected,
    ListView:focus > ListItem.--highlight {
        background: #1f6feb33;
        color: #58a6ff;
    }

    /* ---- Center: chat ---- */
    #center {
        width: 1fr;
        layout: vertical;
        background: #0d1117;
    }

    #chat-header {
        height: 1;
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
        padding: 0 1;
        border-bottom: solid #30363d;
    }

    #message-display {
        height: 1fr;
        background: #0d1117;
        padding: 0 1;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }

    #message-display:focus {
        border: none;
    }

    #input-area {
        height: 3;
        dock: bottom;
        layout: horizontal;
        background: #161b22;
        padding: 0;
    }

    #message-input {
        width: 1fr;
        height: 3;
        background: #0d1117;
        color: #e6edf3;
        border: none;
        border-top: solid #58a6ff;
        padding: 0 1;
    }

    #message-input:focus {
        border-top: solid #79c0ff;
        background: #161b22;
    }

    #force-ai-button {
        width: 6;
        height: 3;
        background: #238636;
        color: #ffffff;
        text-style: bold;
        border: none;
        margin: 0;
    }

    #force-ai-button:hover {
        background: #2ea043;
    }

    /* ---- Right panel (node details) ---- */
    #right-panel {
        width: 36;
        background: #0d1117;
        border-left: vkey #30363d;
        layout: vertical;
        padding: 1;
    }

    #node-stats {
        height: 1fr;
    }

    #map-panel {
        width: 1fr;
        height: 1fr;
        background: #0d1117;
        display: none;
        padding: 0;
    }

    #map-panel.visible {
        display: block;
    }

    #mesh-map {
        height: 1fr;
        width: 1fr;
    }

    #info-panel {
        height: auto;
        margin-bottom: 1;
    }

    /* ---- Bottom log bar ---- */
    #log-panel {
        height: 8;
        dock: bottom;
        background: #161b22;
        border-top: solid #30363d;
        display: none;
    }

    #log-panel.visible {
        display: block;
    }

    #app-log {
        height: 1fr;
        background: #161b22;
        scrollbar-size: 1 1;
        padding: 0 1;
    }

    /* ---- Unread badge ---- */
    .unread {
        background: #1f6feb33;
        color: #58a6ff;
        text-style: bold;
    }

    .reverse {
        background: #1f6feb33;
        color: #58a6ff;
        text-style: bold;
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
        
        # Initialize HAL bot and message router
        self.hal_bot = HalBot(self.meshtastic_handler, self.app_config)
        self.router = MessageRouter(
            self.app_config, self.ai_bridge,
            self.conversation_manager, self.hal_bot,
            self.meshtastic_handler
        )
        
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
        self.selected_node_id = None
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

        with Horizontal(id="app-grid"):
            # -- Sidebar: channels + nodes --
            with Vertical(id="sidebar"):
                yield Label(" CHANNELS", classes="sidebar-label")
                yield ListView(
                    ChannelListItem(0, "Primary"),
                    id="channel-list"
                )
                yield Label(" NODES (t=filter)", classes="sidebar-label", id="node-filter-label", markup=False)
                yield ListView(id="node-list")
                yield InfoPanel(id="status-bar")

            # -- Center: chat --
            with Vertical(id="center"):
                yield Label(" Channel 0 - Primary", id="chat-header")
                yield RichLog(id="message-display", wrap=True, markup=True, highlight=True, auto_scroll=True)
                with Horizontal(id="input-area"):
                    yield Input(placeholder="Type a message...", id="message-input")
                    yield Button("AI", id="force-ai-button")

            # -- Right: node details --
            with Vertical(id="right-panel"):
                yield NodeStatsPanel(id="node-stats")

        # -- Map overlay (hidden by default, replaces app-grid) --
        with Vertical(id="map-panel"):
            yield MeshMapPanel(id="mesh-map")

        # -- Collapsible log bar --
        with Container(id="log-panel"):
            yield RichLog(id="app-log", highlight=True, markup=True)

        yield Footer()
    
    def action_cycle_node_filter(self) -> None:
        """Cycle node filter: all -> radio -> mqtt -> all"""
        cycle = {"all": "radio", "radio": "mqtt", "mqtt": "all"}
        self.node_filter = cycle.get(self.node_filter, "all")
        filter_labels = {"all": " NODES (F7=type F8=hops)", "radio": " NODES radio only", "mqtt": " NODES mqtt only"}
        try:
            self.query_one("#node-filter-label", Label).update(filter_labels[self.node_filter])
        except Exception:
            pass
        self.update_node_list()

    def action_cycle_hop_filter(self) -> None:
        """Cycle hop filter: all -> 0 -> 1 -> 2 -> 3+ -> all"""
        cycle = {"all": "0", "0": "1", "1": "2", "2": "3+", "3+": "all"}
        self.hop_filter = cycle.get(self.hop_filter, "all")
        hop_labels = {
            "all": " NODES (F7=type F8=hops)",
            "0": " NODES [direct only]",
            "1": " NODES [<=1 hop]",
            "2": " NODES [<=2 hops]",
            "3+": " NODES [3+ hops]",
        }
        try:
            self.query_one("#node-filter-label", Label).update(hop_labels[self.hop_filter])
        except Exception:
            pass
        self.update_node_list()

    def action_toggle_map(self) -> None:
        """Toggle mesh map view (replaces main grid)"""
        self.show_map = not self.show_map
        try:
            app_grid = self.query_one("#app-grid")
            map_panel = self.query_one("#map-panel")
            if self.show_map:
                app_grid.styles.display = "none"
                map_panel.add_class("visible")
                self._refresh_map()
            else:
                app_grid.styles.display = "block"
                map_panel.remove_class("visible")
        except Exception:
            pass

    def action_cycle_map_filter(self) -> None:
        """Cycle map filter"""
        cycle = {"all": "0hop", "0hop": "1hop", "1hop": "2hop", "2hop": "3hop+",
                 "3hop+": "1h", "1h": "6h", "6h": "24h", "24h": "all"}
        self.map_filter = cycle.get(self.map_filter, "all")
        self._refresh_map()

    def _refresh_map(self) -> None:
        """Refresh the mesh map with current nodes"""
        try:
            mesh_map = self.query_one("#mesh-map", MeshMapPanel)
            mesh_map.set_nodes(self.nodes, self.selected_node_id, self.map_filter)
        except Exception:
            pass

    def action_toggle_logs(self) -> None:
        """Toggle log panel visibility"""
        self.show_logs = not self.show_logs
        log_panel = self.query_one("#log-panel")
        if self.show_logs:
            log_panel.add_class("visible")
        else:
            log_panel.remove_class("visible")

    async def on_mount(self) -> None:
        """Called when the app is mounted"""
        self.app_loop = asyncio.get_running_loop()
        # Start message queue processor
        self.run_worker(self.process_message_queue, group="message_processor")

        # Populate channel list from device
        self.update_channel_list()

        # Load initial nodes
        self.load_initial_nodes()

        # Set default channel
        self.load_conversation()

        # Update stats
        self.update_stats()

        # Log startup
        self.query_one("#app-log", RichLog).write("[green]Eva Mesh AI started[/green]")

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
        # Detect connection type: viaMqtt flag or hopsAway=-1 means MQTT
        is_mqtt = node_info.get('viaMqtt', False)
        if not is_mqtt and node_info.get('hopsAway') == -1:
            is_mqtt = True

        detailed_info = {
            'long_name': user.get('longName', 'Unknown'),
            'short_name': user.get('shortName', 'UNK'),
            'last_heard': node_info.get('lastHeard', time.time()),
            'first_heard': node_info.get('firstHeard', time.time()),
            'is_favorite': node_info.get('isFavorite', False),
            'hops_away': node_info.get('hopsAway', None),
            'connection_type': 'tcp' if is_mqtt else 'radio',
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
        """Update the node list widget with unread counts.
        Sort order: MQTT/internet nodes first, then by last_heard (newest first), then by hops (closest first).
        Respects self.node_filter: 'all', 'radio', or 'mqtt'.
        """
        node_list = self.query_one("#node-list", ListView)
        node_list.clear()

        def sort_key(item):
            _nid, info = item
            is_mqtt = 0 if info.get('connection_type') == 'tcp' else 1  # MQTT first
            last_heard = -(info.get('last_heard', 0))  # newest first (negative for desc)
            hops = info.get('hops_away') if info.get('hops_away') is not None else 999  # closest first
            return (is_mqtt, last_heard, hops)

        sorted_nodes = sorted(self.nodes.items(), key=sort_key)

        # Apply connection type filter
        if self.node_filter == "radio":
            sorted_nodes = [(nid, info) for nid, info in sorted_nodes if info.get('connection_type') != 'tcp']
        elif self.node_filter == "mqtt":
            sorted_nodes = [(nid, info) for nid, info in sorted_nodes if info.get('connection_type') == 'tcp']

        # Apply hop filter
        if self.hop_filter == "0":
            sorted_nodes = [(nid, info) for nid, info in sorted_nodes if info.get('hops_away') == 0]
        elif self.hop_filter == "1":
            sorted_nodes = [(nid, info) for nid, info in sorted_nodes if (info.get('hops_away') or 999) <= 1]
        elif self.hop_filter == "2":
            sorted_nodes = [(nid, info) for nid, info in sorted_nodes if (info.get('hops_away') or 999) <= 2]
        elif self.hop_filter == "3+":
            sorted_nodes = [(nid, info) for nid, info in sorted_nodes if (info.get('hops_away') or 0) >= 3]

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

        # Update chat header
        bot_name = getattr(self.app_config, 'BOT_NAME', 'Eva')
        try:
            header = self.query_one("#chat-header", Label)
            if self.current_chat_type == "channel":
                header.update(f" Ch {self.current_chat_id}  |  {len(messages)} msgs  |  {bot_name}")
            else:
                node = self.nodes.get(self.current_chat_id, {})
                name = node.get('long_name', self.current_chat_id)
                header.update(f" DM  {name}  |  {len(messages)} msgs")
        except Exception:
            pass

        message_display = self.query_one("#message-display", RichLog)
        message_display.clear()

        if not messages:
            message_display.write("[dim italic]No messages yet...[/dim italic]")
        else:
            prev_date = None
            for msg in messages:
                ts = msg.get('timestamp', time.time())
                msg_date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                timestamp = datetime.fromtimestamp(ts).strftime("%H:%M")
                sender = msg.get('user_name', 'Unknown')
                content = msg.get('content', '')
                role = msg.get('role', 'user')

                # Date separator
                if msg_date != prev_date:
                    message_display.write(f"[dim]{'':>10}--- {msg_date} ---[/dim]")
                    prev_date = msg_date

                # Style per role
                if role == 'assistant':
                    name_style = "bold #58a6ff"
                    sender = bot_name
                    msg_style = "#58a6ff"
                elif sender in ("You", "You (TUI)"):
                    name_style = "bold #3fb950"
                    sender = "You"
                    msg_style = "#c9d1d9"
                else:
                    name_style = "bold #d2a8ff"
                    msg_style = "#c9d1d9"

                message_display.write(
                    f"[dim #484f58]{timestamp}[/dim #484f58] [{name_style}]{sender}[/{name_style}]  [{msg_style}]{content}[/{msg_style}]"
                )

        # Update last viewed count and persist
        self.last_viewed_messages[conv_id] = len(messages)
        self.save_last_viewed_state()

        # Update sidebar counts
        self.update_channel_list()
        self.update_node_list()
        self.refresh_info_panel()

        # Scroll to bottom
        message_display.scroll_end(animate=False)

        # Focus input
        self.query_one("#message-input").focus()
    
    def update_stats(self) -> None:
        """Update info/status bar"""
        self.refresh_info_panel()
    
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
            self.selected_node_id = event.item.node_id

            # Update map if visible
            if self.show_map:
                self._refresh_map()
            
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
        """Process an incoming message via the central MessageRouter."""
        try:
            log_widget = self.query_one("#app-log", RichLog)

            text = data['text']
            sender_id = self._norm_id(data['sender_id'])
            sender_name = data['sender_name']
            destination_id = self._norm_id(data['destination_id'])
            channel_id = data['channel_id']

            # Update AI node ID
            self._update_ai_node_id()

            # --- Route via centralised router ---
            result = self.router.on_message(
                text, sender_id, sender_name, destination_id,
                channel_id, self.ai_node_id
            )
            conv_id = result.conversation_id

            # Update node info
            eff_ch = channel_id if channel_id is not None else 0
            self._update_node_info_from_message(sender_id, sender_name, eff_ch)

            # Refresh UI
            current_conv_id = (f"ch_{self.current_chat_id}_broadcast"
                               if self.current_chat_type == "channel"
                               else self._dm_conv(self.current_chat_id))
            if conv_id == current_conv_id:
                self.load_conversation()
            else:
                self.update_channel_list()
                self.update_node_list()
                self.refresh_info_panel()

            log_widget.write(f"[yellow]MSG from {sender_name}: {text[:50].strip()}[/yellow]")
            self.rx_count += 1

            # --- Broadcast SOS alert ---
            if result.broadcast_alert and self.meshtastic_handler and self.meshtastic_handler.is_connected:
                for ch in result.broadcast_channels:
                    self.meshtastic_handler.send_message(result.broadcast_alert, channel_index=ch)
                log_widget.write(f"[red bold]SOS ALERT broadcast on {len(result.broadcast_channels)} channel(s)[/red bold]")

            # --- Send direct reply (HAL bot / help confirmation) ---
            if result.reply_text and result.handled:
                if self.meshtastic_handler and self.meshtastic_handler.is_connected:
                    if result.reply_as_dm:
                        success, reason = self.meshtastic_handler.send_message(
                            result.reply_text, destination_id_hex=result.reply_destination, channel_index=0
                        )
                    else:
                        success, reason = self.meshtastic_handler.send_message(
                            result.reply_text, channel_index=result.reply_channel
                        )
                    if success:
                        log_widget.write(f"[green]Bot response sent to {sender_name}[/green]")
                        self.tx_count += 1
                        self.conversation_manager.add_message(
                            conv_id, "assistant", result.reply_text,
                            user_name=getattr(self.app_config, 'BOT_NAME', 'Eva'),
                            node_id=f"{self.meshtastic_handler.node_id:x}"
                        )
                        if conv_id == current_conv_id:
                            self.load_conversation()
                    else:
                        log_widget.write(f"[red]Failed to send bot response: {reason}[/red]")
                return

            # --- AI response needed: spawn worker ---
            if result.needs_ai_response:
                log_widget.write(f"[bright_green]Starting AI worker for {sender_name} (conv={conv_id})[/bright_green]")
                processor = AIProcessingWorker(
                    self, text, sender_id, sender_name, eff_ch,
                    result.reply_as_dm, conv_id, self.router.url_pattern,
                    skip_triage=result.skip_triage
                )
                self.run_worker(processor.run, exclusive=True, group="ai_proc", thread=True)
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
        """Update the compact status bar in sidebar."""
        try:
            total_channel_unread = sum(self.channel_unread.values())
            total_node_unread = sum(self.node_unread.values())
            total_unread = total_channel_unread + total_node_unread
            connected = self.meshtastic_handler.is_connected if self.meshtastic_handler else False

            info_stats = {
                "Status": "ON" if connected else "OFF",
                "Nodes": len(self.nodes),
                "Unread": total_unread,
            }
            self.query_one("#status-bar", InfoPanel).set_stats(info_stats)
        except Exception:
            pass

    def update_channel_list(self) -> None:
        """Update the channel list from device info with unread counts"""
        channel_list = self.query_one("#channel-list", ListView)
        channel_list.clear()

        # Get actual channels from device
        device_channels = self.meshtastic_handler.list_channels() if self.meshtastic_handler else []

        if device_channels:
            for ch in device_channels:
                ch_id = ch['index']
                ch_name = ch['name'] if ch['name'] not in ('', f'Ch-{ch_id}', f'Secondary-{ch_id}') else f"Ch {ch_id}"
                conv_id = f"ch_{ch_id}_broadcast"
                messages = self.conversation_manager.load_conversation(conv_id)
                total_messages = len(messages)
                last_viewed = self.last_viewed_messages.get(conv_id, 0)
                unread = max(0, total_messages - last_viewed)
                self.channel_unread[ch_id] = unread
                channel_list.append(ChannelListItem(ch_id, ch_name, unread))
        else:
            # Fallback: show 8 channels
            for channel_id in range(8):
                channel_name = "Primary" if channel_id == 0 else f"Ch {channel_id}"
                conv_id = f"ch_{channel_id}_broadcast"
                messages = self.conversation_manager.load_conversation(conv_id)
                total_messages = len(messages)
                last_viewed = self.last_viewed_messages.get(conv_id, 0)
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
                'connection_type': 'unknown',
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
        
        # Detect connection type from viaMqtt flag
        is_mqtt = node_info.get('viaMqtt', False)
        if not is_mqtt and node_info.get('hopsAway') == -1:
            is_mqtt = True
        self.nodes[node_id]['connection_type'] = 'tcp' if is_mqtt else 'radio'

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