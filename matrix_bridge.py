from __future__ import annotations

"""
matrix_bridge.py - Bridge between Meshtastic mesh and Matrix protocol.

Maps each Meshtastic channel to a Matrix room. Forwards messages both ways.
Requires: pip install matrix-nio[e2e]
"""

import asyncio
import time
import threading
import traceback
from typing import Dict, Optional, Callable

try:
    from nio import (
        AsyncClient, MatrixRoom, RoomMessageText,
        LoginResponse, RoomCreateResponse, JoinResponse,
        RoomResolveAliasResponse,
    )
    HAS_NIO = True
except ImportError:
    HAS_NIO = False


import logging

# Silence nio library loggers that flood stdout and break TUI
for _nio_logger_name in ("nio", "nio.rooms", "nio.client.base_client", "nio.responses"):
    logging.getLogger(_nio_logger_name).setLevel(logging.WARNING)

_matrix_logger = logging.getLogger("matrix_bridge")
if not _matrix_logger.handlers:
    _fh = logging.FileHandler("matrix_bridge.log", mode="a")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    _matrix_logger.addHandler(_fh)
    _matrix_logger.setLevel(logging.DEBUG)
    _matrix_logger.propagate = False

def log_info(msg):
    _matrix_logger.info(msg)

def log_error(msg):
    _matrix_logger.error(msg)


class MatrixBridge:
    """
    Bridges Meshtastic mesh channels to Matrix rooms.

    - Each mesh channel gets a Matrix room (auto-created if needed)
    - DMs get a separate room
    - Mesh -> Matrix: messages forwarded with sender name
    - Matrix -> Mesh: messages sent to the corresponding channel
    """

    def __init__(
        self,
        homeserver: str,
        username: str,
        password: str,
        room_prefix: str = "mesh",
        bot_name: str = "Eva",
        invite_users: Optional[list] = None,
        on_matrix_message: Optional[Callable] = None,
        meshtastic_handler=None,
        display_name: str = "",
    ):
        if not HAS_NIO:
            raise ImportError("matrix-nio is required: pip install matrix-nio[e2e]")

        self.homeserver = homeserver
        self.username = username
        self.password = password
        self.room_prefix = room_prefix
        self.bot_name = bot_name
        self.invite_users = invite_users or []
        self.on_matrix_message = on_matrix_message
        self.meshtastic_handler = meshtastic_handler
        self.display_name = display_name

        self.client: Optional[AsyncClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # channel_index -> room_id mapping
        self.channel_rooms: Dict[int, str] = {}
        # room_id -> channel_index reverse mapping
        self.room_channels: Dict[str, int] = {}
        # node_id -> dm room_id mapping
        self.dm_rooms: Dict[str, str] = {}
        # room_id -> node_id reverse mapping (for Matrix->Mesh DMs)
        self.room_dm_nodes: Dict[str, str] = {}

        # Track own messages to avoid echo
        self._own_messages: set = set()
        # Ignore messages older than start time
        self._start_time_ms = int(time.time() * 1000)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the Matrix bridge in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log_info("Bridge thread started")

    def stop(self):
        """Stop the Matrix bridge."""
        self._running = False
        if self._loop and self.client:
            asyncio.run_coroutine_threadsafe(self.client.close(), self._loop)
        log_info("Bridge stopped")

    def _run_loop(self):
        """Background thread event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            log_error(f"Bridge loop crashed: {e}")
            traceback.print_exc()

    async def _async_main(self):
        """Main async routine: login, setup rooms, sync forever."""
        self.client = AsyncClient(self.homeserver, self.username)

        # Login
        resp = await self.client.login(self.password)
        if not isinstance(resp, LoginResponse):
            log_error(f"Login failed: {resp}")
            return
        log_info(f"Logged in as {self.username} on {self.homeserver}")

        # Setup rooms — retry until meshtastic is connected
        await self._setup_rooms_with_retry()

        # Register message callback
        self.client.add_event_callback(self._on_matrix_event, RoomMessageText)

        # Do initial sync to skip old messages
        log_info("Performing initial sync...")
        try:
            await self.client.sync(timeout=10000, full_state=True)
        except Exception as e:
            log_error(f"Initial sync error: {e}")
        self._start_time_ms = int(time.time() * 1000)

        # Sync forever (sync_forever dispatches callbacks automatically)
        log_info("Starting sync loop...")
        try:
            await self.client.sync_forever(timeout=30000, full_state=False)
        except Exception as e:
            log_error(f"Sync loop ended: {e}")
        finally:
            await self.client.close()

    async def _setup_rooms_with_retry(self):
        """Try to setup rooms, retrying until meshtastic channels are available."""
        for attempt in range(15):
            await self._setup_rooms()
            if self.channel_rooms:
                log_info(f"Rooms ready: {len(self.channel_rooms)} channel(s), DM rooms: {len(self.dm_rooms)}")
                return
            log_info(f"No channels yet (attempt {attempt + 1}/15), waiting for meshtastic...")
            await asyncio.sleep(3)
        # Fallback — create at least ch0
        if not self.channel_rooms:
            log_info("Fallback: creating default ch0 room")
            await self._ensure_channel_room(0, "PRIMARY")

    # ------------------------------------------------------------------
    # Room management
    # ------------------------------------------------------------------

    async def _setup_rooms(self):
        """Create or join Matrix rooms for each Meshtastic channel."""
        if not self.meshtastic_handler:
            log_info("No meshtastic handler - creating default room for ch0")
            await self._ensure_channel_room(0, "PRIMARY")
            return

        channels = self.meshtastic_handler.list_channels()
        if not channels:
            log_info("No channels from device, creating default ch0 room")
            await self._ensure_channel_room(0, "PRIMARY")
            return

        for ch in channels:
            idx = ch["index"]
            name = ch["name"]
            role = ch.get("role", "")
            # Skip disabled channels
            if "DISABLED" in str(role).upper():
                continue
            await self._ensure_channel_room(idx, name)

    async def _ensure_channel_room(self, channel_index: int, channel_name: str):
        """Ensure a Matrix room exists for a mesh channel."""
        alias_local = f"{self.room_prefix}-ch{channel_index}"
        alias_full = f"#{alias_local}:{self._get_domain()}"

        # Try to resolve existing room
        room_id = await self._resolve_alias(alias_full)
        if room_id:
            self.channel_rooms[channel_index] = room_id
            self.room_channels[room_id] = channel_index
            log_info(f"Channel {channel_index} ({channel_name}) -> existing room {room_id}")
            await self.client.join(room_id)
            await self._invite_users(room_id)
            return

        # Create new room
        display_name = f"Mesh: {channel_name}" if channel_name != f"Ch-{channel_index}" else f"Mesh: Channel {channel_index}"
        resp = await self.client.room_create(
            name=display_name,
            alias=alias_local,
            topic=f"Meshtastic channel {channel_index} ({channel_name}) - messages bridged from mesh network",
            invite=self.invite_users,
        )
        if isinstance(resp, RoomCreateResponse):
            self.channel_rooms[channel_index] = resp.room_id
            self.room_channels[resp.room_id] = channel_index
            log_info(f"Channel {channel_index} ({channel_name}) -> created room {resp.room_id}")
        else:
            log_error(f"Failed to create room for channel {channel_index}: {resp}")

    async def _ensure_dm_room(self, node_id: str, node_name: str = ""):
        """Ensure a Matrix room exists for DMs with a specific mesh node."""
        if node_id in self.dm_rooms:
            return self.dm_rooms[node_id]

        alias_local = f"{self.room_prefix}-dm-{node_id}"
        alias_full = f"#{alias_local}:{self._get_domain()}"

        room_id = await self._resolve_alias(alias_full)
        if room_id:
            self.dm_rooms[node_id] = room_id
            self.room_dm_nodes[room_id] = node_id
            await self.client.join(room_id)
            await self._invite_users(room_id)
            log_info(f"DM room for !{node_id} ({node_name}) -> existing {room_id}")
            return room_id

        display = f"Mesh DM: {node_name}" if node_name else f"Mesh DM: !{node_id}"
        resp = await self.client.room_create(
            name=display,
            alias=alias_local,
            topic=f"Meshtastic DM with !{node_id} ({node_name})",
            invite=self.invite_users,
        )
        if isinstance(resp, RoomCreateResponse):
            self.dm_rooms[node_id] = resp.room_id
            self.room_dm_nodes[resp.room_id] = node_id
            log_info(f"DM room for !{node_id} ({node_name}) -> created {resp.room_id}")
            return resp.room_id
        else:
            log_error(f"Failed to create DM room for !{node_id}: {resp}")
            return None

    async def _resolve_alias(self, alias: str) -> Optional[str]:
        """Try to resolve a room alias to a room ID."""
        try:
            resp = await self.client.room_resolve_alias(alias)
            if isinstance(resp, RoomResolveAliasResponse):
                return resp.room_id
        except Exception:
            pass
        return None

    async def _invite_users(self, room_id: str):
        """Invite configured users to a room (ignores errors if already joined)."""
        for user_id in self.invite_users:
            try:
                await self.client.room_invite(room_id, user_id)
                log_info(f"Invited {user_id} to {room_id}")
            except Exception:
                pass  # already joined or other non-critical error

    def _get_domain(self) -> str:
        """Extract domain from homeserver URL."""
        domain = self.homeserver.replace("https://", "").replace("http://", "")
        domain = domain.rstrip("/")
        # If it has a port, keep it for the URL but use just domain for alias
        if ":" in domain:
            domain = domain.split(":")[0]
        return domain

    # ------------------------------------------------------------------
    # Mesh -> Matrix (called from outside)
    # ------------------------------------------------------------------

    def send_to_matrix(self, text: str, sender_name: str, sender_id: str,
                       channel_index: int = 0, is_dm: bool = False):
        """
        Forward a mesh message to Matrix. Call from the mesh message handler.
        Thread-safe: schedules the send on the bridge's event loop.
        """
        if not self._loop or not self.client:
            log_error(f"Cannot send to Matrix: loop={bool(self._loop)} client={bool(self.client)}")
            return

        formatted = f"**{sender_name}** (!{sender_id}): {text}"
        target = f"DM !{sender_id}" if is_dm else f"ch{channel_index}"
        log_info(f"Mesh -> Matrix [{target}]: {text[:60]}")

        asyncio.run_coroutine_threadsafe(
            self._async_send_to_matrix(formatted, channel_index, is_dm, sender_id, sender_name),
            self._loop
        )

    async def _async_send_to_matrix(self, text: str, channel_index: int,
                                     is_dm: bool, sender_id: str = "", sender_name: str = ""):
        """Actually send to Matrix room."""
        if is_dm:
            room_id = self.dm_rooms.get(sender_id)
        else:
            room_id = self.channel_rooms.get(channel_index)

        if not room_id:
            # Try to create room on the fly
            if is_dm:
                room_id = await self._ensure_dm_room(sender_id, sender_name)
            else:
                await self._ensure_channel_room(channel_index, f"Ch-{channel_index}")
                room_id = self.channel_rooms.get(channel_index)

        if not room_id:
            log_error(f"No Matrix room for {'DM' if is_dm else f'channel {channel_index}'} (known rooms: {list(self.channel_rooms.keys())})")
            return

        try:
            resp = await self.client.room_send(
                room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": text,
                    "format": "org.matrix.custom.html",
                    "formatted_body": text.replace("**", "<b>", 1).replace("**", "</b>", 1),
                },
            )
            log_info(f"Sent to Matrix room {room_id}: {type(resp).__name__}")
        except Exception as e:
            log_error(f"Failed to send to Matrix room {room_id}: {e}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Matrix -> Mesh (callback from nio)
    # ------------------------------------------------------------------

    async def _on_matrix_event(self, room: MatrixRoom, event: RoomMessageText):
        """Handle incoming Matrix messages -> forward to mesh."""
        log_info(f"Matrix event in {room.display_name} from {event.sender}: {event.body[:80]}")

        # Ignore own messages
        if event.sender == self.client.user_id:
            log_info("Ignoring own message")
            return

        # Ignore old messages from before bridge started
        if event.server_timestamp < self._start_time_ms:
            log_info(f"Ignoring old message (ts={event.server_timestamp} < start={self._start_time_ms})")
            return

        body = event.body
        sender = event.sender

        # Extract display name (use configured override if set)
        display_name = self.display_name or room.user_name(event.sender) or sender.split(":")[0].lstrip("@")

        # Find which channel/DM this room maps to
        channel_index = self.room_channels.get(room.room_id)
        dm_node_id = self.room_dm_nodes.get(room.room_id)

        if channel_index is None and dm_node_id is None:
            return

        # Forward to mesh
        if self.meshtastic_handler and self.meshtastic_handler.is_connected:
            mesh_text = f"[{display_name}] {body}"
            if len(mesh_text) > 194:
                mesh_text = mesh_text[:191] + "..."

            if dm_node_id:
                log_info(f"Matrix -> Mesh DM to !{dm_node_id}: [{display_name}]: {body[:80]}")
                self.meshtastic_handler.send_message(
                    mesh_text, destination_id_hex=dm_node_id
                )
            else:
                log_info(f"Matrix -> Mesh ch{channel_index}: [{display_name}]: {body[:80]}")
                self.meshtastic_handler.send_message(
                    mesh_text, channel_index=channel_index
                )

        if self.on_matrix_message:
            try:
                self.on_matrix_message(
                    text=body,
                    sender_name=display_name,
                    sender_id=sender,
                    channel_index=channel_index,
                    is_dm=bool(dm_node_id),
                )
            except Exception as e:
                log_error(f"on_matrix_message callback error: {e}")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        return bool(self.client and self._running and self._loop)

    def get_status(self) -> dict:
        return {
            "connected": self.is_connected(),
            "homeserver": self.homeserver,
            "username": self.username,
            "channel_rooms": len(self.channel_rooms),
            "dm_rooms": len(self.dm_rooms),
        }
