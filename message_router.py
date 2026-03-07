# message_router.py
"""
Centralised message routing logic shared by CLI and TUI.

MessageRouter receives every incoming Meshtastic message, classifies it, and
decides what should happen (HAL bot command, AI response, help alert, etc.).
The caller (CLI or TUI) only needs to call `router.on_message(...)` and act
on the returned `RouteResult`.
"""

import re
import time
import random
import traceback
import meshtastic
from dataclasses import dataclass, field
from typing import Optional, List

from hal_bot import HalBot
from ai_bridge import AIBridge
from conversation_manager import ConversationManager


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MessageContext:
    """All metadata about an incoming message."""
    text: str
    sender_id: str          # hex, lowercase, no '!'
    sender_name: str
    destination_id: str     # hex, lowercase
    channel_id: int         # effective channel (None -> 0)
    ai_node_id: Optional[str]  # our own node id (hex)

    # derived (filled by router)
    is_broadcast: bool = False
    is_dm_to_ai: bool = False
    conversation_id: str = ""


@dataclass
class RouteResult:
    """What the UI layer should do after routing."""
    # If set, send this text back on the mesh
    reply_text: Optional[str] = None
    # Where to send: DM back to sender or channel broadcast
    reply_as_dm: bool = False
    reply_channel: int = 0
    reply_destination: Optional[str] = None  # hex node id for DM

    # If set, broadcast this alert on ALL channels
    broadcast_alert: Optional[str] = None
    broadcast_channels: List[int] = field(default_factory=list)

    # Conversation id (for UI to track / refresh)
    conversation_id: str = ""

    # Whether an AI worker should be spawned
    needs_ai_response: bool = False
    skip_triage: bool = False

    # If the message was already fully handled (e.g. HAL bot)
    handled: bool = False


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class MessageRouter:
    """
    Stateless-ish router that classifies messages and produces RouteResults.

    Holds references to shared services (hal_bot, ai_bridge, conversation_manager)
    and config values, but does NOT hold UI state.
    """

    # SOS / help keywords (multi-language)
    HELP_KEYWORDS = [
        "sos", "help", "pomoc", "ratunku", "emergency", "mayday",
        "alarm", "wypadek", "accident", "rescue", "hilfe", "au secours",
        "socorro", "danger", "niebezpieczenstwo",
    ]

    def __init__(self, app_config, ai_bridge: AIBridge,
                 conversation_manager: ConversationManager,
                 hal_bot: HalBot, meshtastic_handler):
        self.config = app_config
        self.ai_bridge = ai_bridge
        self.conversation_manager = conversation_manager
        self.hal_bot = hal_bot
        self.meshtastic_handler = meshtastic_handler

        # URL detection
        self.url_pattern = re.compile(
            r'https?://[^\s/$.?#].[^\s]*', re.IGNORECASE
        )
        # Info-request patterns (weather, search, extract)
        self.weather_pattern = re.compile(
            r'(?:weather|temperature|temp|pogoda|temperatura)\s+'
            r'(?:in|for|w|dla)?\s+([a-zA-Z\s]+)', re.IGNORECASE
        )
        self.search_pattern = re.compile(
            r'(?:search|find|szukaj|znajdz|szukam|chce|potrzebuje)\s+'
            r'(?:for|dla|mi)?\s*(.+)', re.IGNORECASE
        )
        self.extract_pattern = re.compile(
            r'(?:extract|get|pobierz|wez)\s+'
            r'(temperature|price|title|description|news|weather|pogoda|cene|tytul|opis)\s+'
            r'(?:from|z|ze)?\s+(https?://[^\s]+)', re.IGNORECASE
        )

        # Human-like behaviour
        self.last_response_times: dict = {}
        self.ai_response_probability = getattr(app_config, 'AI_RESPONSE_PROBABILITY', 0.85)
        self.ai_min_delay = getattr(app_config, 'AI_MIN_RESPONSE_DELAY_S', 2)
        self.ai_max_delay = getattr(app_config, 'AI_MAX_RESPONSE_DELAY_S', 8)
        self.ai_cooldown = getattr(app_config, 'AI_RESPONSE_COOLDOWN_S', 60)
        self.enable_ai_triage = getattr(app_config, 'ENABLE_AI_TRIAGE_ON_CHANNELS', False)
        self.triage_context_count = getattr(app_config, 'TRIAGE_CONTEXT_MESSAGE_COUNT', 3)
        self.active_channel = getattr(app_config, 'ACTIVE_MESHTASTIC_CHANNEL_INDEX', 0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_message(self, text: str, sender_id: str, sender_name: str,
                   destination_id: str, channel_id, ai_node_id: str) -> RouteResult:
        """
        Main entry point.  Returns a RouteResult describing what to do.
        The caller is responsible for actually sending messages / spawning workers.
        """
        ctx = self._build_context(text, sender_id, sender_name,
                                  destination_id, channel_id, ai_node_id)

        # Ignore our own messages
        if ctx.ai_node_id and ctx.sender_id == ctx.ai_node_id:
            return RouteResult(handled=True, conversation_id=ctx.conversation_id)

        # Save incoming message to history
        self.conversation_manager.add_message(
            ctx.conversation_id, "user", ctx.text,
            user_name=ctx.sender_name, node_id=ctx.sender_id
        )

        # --- Priority 1: SOS / Help ---
        help_result = self._check_help(ctx)
        if help_result:
            return help_result

        # --- Priority 2: HAL bot commands (ping, traceroute, info ...) ---
        hal_result = self._check_hal_bot(ctx)
        if hal_result:
            return hal_result

        # --- Priority 3: Should AI respond? ---
        return self._check_ai_response(ctx)

    # ------------------------------------------------------------------
    # AI response generation (called by UI layer after routing)
    # ------------------------------------------------------------------

    def generate_ai_response(self, ctx_or_conv_id, text: str,
                             sender_name: str, sender_id: str,
                             is_dm: bool, skip_triage: bool = False) -> Optional[str]:
        """
        Generate an AI response.  This is blocking and should run in a thread.
        Returns the response text or None.
        """
        conv_id = ctx_or_conv_id if isinstance(ctx_or_conv_id, str) else ctx_or_conv_id.conversation_id

        context_history = self.conversation_manager.get_contextual_history(
            conv_id, for_user_name=sender_name
        )

        # Check for specific info requests
        specific_info = self._extract_specific_info(text)

        # URL analysis
        web_analysis = None
        urls = self.url_pattern.findall(text)
        if urls:
            try:
                web_analysis = self.ai_bridge.analyze_url_content(urls[0])
                if web_analysis:
                    self.conversation_manager.add_url_analysis(conv_id, urls[0], web_analysis)
            except Exception as e:
                print(f"ERROR: URL analysis failed: {e}")
                web_analysis = f"[Error analyzing URL]"

        if specific_info:
            web_analysis = (f"{web_analysis}\n\nSpecific Information: {specific_info}"
                           if web_analysis else f"Specific Information: {specific_info}")

        # If no specific info and no URL, try AI web agent
        if not specific_info and not urls:
            try:
                response = self.ai_bridge.get_response_with_web_search(
                    context_history, text, sender_name, sender_id
                )
                if response and response.strip():
                    return response
            except Exception:
                traceback.print_exc()

        # Standard AI response
        response = self.ai_bridge.get_response(
            context_history, text, sender_name, sender_id,
            web_analysis_summary=web_analysis,
            skip_triage=is_dm
        )
        return response

    def apply_human_delay(self):
        """Apply random delay to simulate human-like response time."""
        if self.ai_min_delay >= 0 and self.ai_max_delay > self.ai_min_delay:
            delay = random.uniform(self.ai_min_delay, self.ai_max_delay)
            time.sleep(delay)

    def record_response(self, conversation_id: str, response_text: str):
        """Save AI response to conversation and update cooldown timer."""
        self.conversation_manager.add_message(conversation_id, "assistant", response_text)
        self.last_response_times[conversation_id] = time.time()

    # ------------------------------------------------------------------
    # Internal: context building
    # ------------------------------------------------------------------

    def _build_context(self, text, sender_id, sender_name,
                       destination_id, channel_id, ai_node_id) -> MessageContext:
        sender_id = sender_id.lower().lstrip('!')
        destination_id = (destination_id or "").lower().lstrip('!')
        ai_node_id = ai_node_id.lower().lstrip('!') if ai_node_id else None
        eff_ch = channel_id if channel_id is not None else 0

        broadcast_hex = f"{meshtastic.BROADCAST_NUM:x}".lower()
        is_broadcast = destination_id in (broadcast_hex, "broadcast")
        is_dm = bool(ai_node_id and destination_id == ai_node_id and sender_id != ai_node_id)

        conv_params = {
            "sender_id_hex": sender_id,
            "channel_id": eff_ch if not is_dm else None,
            "ai_node_id_hex": ai_node_id,
            "destination_id_hex": destination_id,
        }
        conv_id = self.conversation_manager._get_conversation_id(**conv_params)

        return MessageContext(
            text=text,
            sender_id=sender_id,
            sender_name=sender_name,
            destination_id=destination_id,
            channel_id=eff_ch,
            ai_node_id=ai_node_id,
            is_broadcast=is_broadcast,
            is_dm_to_ai=is_dm,
            conversation_id=conv_id,
        )

    # ------------------------------------------------------------------
    # Internal: help / SOS detection
    # ------------------------------------------------------------------

    def _check_help(self, ctx: MessageContext) -> Optional[RouteResult]:
        text_lower = ctx.text.lower()
        if not any(kw in text_lower for kw in self.HELP_KEYWORDS):
            return None

        alert_text = f"[SOS] ALERT from {ctx.sender_name} (!{ctx.sender_id}): {ctx.text}"

        # Determine which channels to broadcast on
        channels = self._get_all_channel_indices()

        # Confirmation back to sender
        num_ch = len(channels)
        confirm = f"HAL9000: Your distress message has been broadcast on {num_ch} channel(s). Help is on the way."

        return RouteResult(
            reply_text=confirm,
            reply_as_dm=ctx.is_dm_to_ai,
            reply_channel=ctx.channel_id,
            reply_destination=ctx.sender_id if ctx.is_dm_to_ai else None,
            broadcast_alert=alert_text,
            broadcast_channels=channels,
            conversation_id=ctx.conversation_id,
            handled=True,
        )

    def _get_all_channel_indices(self) -> List[int]:
        """Get all active channel indices from the device."""
        if (self.meshtastic_handler and self.meshtastic_handler.interface and
                hasattr(self.meshtastic_handler.interface, 'channels') and
                self.meshtastic_handler.interface.channels):
            return list(self.meshtastic_handler.interface.channels.keys())
        return [0]  # fallback: just default channel

    # ------------------------------------------------------------------
    # Internal: HAL bot commands
    # ------------------------------------------------------------------

    def _check_hal_bot(self, ctx: MessageContext) -> Optional[RouteResult]:
        if not self.hal_bot.should_handle_message(ctx.text):
            return None

        hal_result = self.hal_bot.handle_command(
            ctx.text, ctx.sender_id, ctx.sender_name,
            ctx.channel_id, ctx.is_dm_to_ai
        )
        if not hal_result or not isinstance(hal_result, dict):
            return None

        response_text = hal_result['response']
        is_channel = hal_result.get('is_channel_message', False)

        return RouteResult(
            reply_text=response_text,
            reply_as_dm=not is_channel,
            reply_channel=ctx.channel_id,
            reply_destination=ctx.sender_id if not is_channel else None,
            conversation_id=ctx.conversation_id,
            handled=True,
        )

    # ------------------------------------------------------------------
    # Internal: AI response decision
    # ------------------------------------------------------------------

    def _check_ai_response(self, ctx: MessageContext) -> RouteResult:
        result = RouteResult(
            conversation_id=ctx.conversation_id,
            reply_channel=ctx.channel_id,
            reply_as_dm=ctx.is_dm_to_ai,
            reply_destination=ctx.sender_id if ctx.is_dm_to_ai else None,
        )

        should_respond = False
        skip_triage = False

        if ctx.is_dm_to_ai:
            should_respond = True
            skip_triage = True
        elif ctx.channel_id == self.active_channel and ctx.is_broadcast:
            if self.enable_ai_triage:
                history_raw = self.conversation_manager.load_conversation(ctx.conversation_id)
                triage_msgs = []
                for entry in history_raw[-(self.triage_context_count + 1):-1]:
                    if entry.get("role") == "user":
                        name = entry.get("user_name", f"Node-{entry.get('node_id', '????')}")
                        triage_msgs.append(f"{name}: {entry.get('content', '')}")
                if self.ai_bridge.should_main_ai_respond(triage_msgs, ctx.text, ctx.sender_name):
                    should_respond = True
                # else stays False
            else:
                should_respond = True

        if not should_respond:
            return result

        # Cooldown check
        now = time.time()
        if self.ai_cooldown > 0:
            last = self.last_response_times.get(ctx.conversation_id, 0)
            if (now - last) < self.ai_cooldown:
                return result

        # Probability check
        if random.random() > self.ai_response_probability:
            return result

        result.needs_ai_response = True
        result.skip_triage = skip_triage
        return result

    # ------------------------------------------------------------------
    # Internal: info extraction helpers
    # ------------------------------------------------------------------

    def _extract_specific_info(self, text: str) -> Optional[str]:
        weather_match = self.weather_pattern.search(text)
        if weather_match:
            city = weather_match.group(1).strip()
            return self.ai_bridge.get_weather_data(city)

        search_match = self.search_pattern.search(text)
        if search_match:
            query = search_match.group(1).strip()
            return self.ai_bridge.search_web(query)

        extract_match = self.extract_pattern.search(text)
        if extract_match:
            info_type = extract_match.group(1).strip()
            url = extract_match.group(2).strip()
            return self.ai_bridge.extract_specific_info(url, info_type)

        return None
