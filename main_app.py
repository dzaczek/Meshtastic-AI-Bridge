# main_app.py
import sys
import os 
import time
import threading
import meshtastic 
import traceback
import re 
import argparse 
import asyncio 
import random 
from collections import deque
import logging
from tui_app import main as tui_main
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll, Container
from textual.widgets import Header, Footer, ListView, RichLog, Input, Button
from textual.reactive import reactive

# --- Initial Setup & Debug Function ---
print_debug = True 

# Global log buffer for interactive mode
interactive_log_buffer = deque(maxlen=50)  # Keep last 50 log entries

LOG_FILE_PATH = "interactive.backend.log"
logging.basicConfig(
    filename=LOG_FILE_PATH,
    filemode='a',
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.DEBUG
)

def dprint(message: str):
    if print_debug:
        try:
            print(f"DEBUG: {message}")
            # Also add to interactive log buffer
            interactive_log_buffer.append(f"DEBUG: {message}")
            logging.debug(message)
        except UnicodeEncodeError:
            fallback_msg = f"DEBUG (ascii-fallback): {message.encode('ascii', 'replace').decode('ascii')}"
            print(fallback_msg)
            interactive_log_buffer.append(fallback_msg)
            logging.debug(fallback_msg)

def log_info(message: str):
    """Log info messages that should appear in both console and interactive logs"""
    print(f"INFO: {message}")
    interactive_log_buffer.append(f"INFO: {message}")
    logging.info(message)

def log_error(message: str):
    """Log error messages that should appear in both console and interactive logs"""
    print(f"ERROR: {message}")
    interactive_log_buffer.append(f"ERROR: {message}")
    logging.error(message)

dprint("main_app.py - Script execution started (Top of file).")
# dprint(f"Python version: {sys.version}") # Optional: for verbose debugging
# dprint(f"Python executable: {sys.executable}") # Optional: for verbose debugging
# dprint(f"Current working directory: {os.getcwd()}") # Optional: for verbose debugging

try:
    if hasattr(sys.stdout, 'reconfigure'): 
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        dprint("main_app.py - Attempted to reconfigure stdout/stderr for UTF-8.")
except Exception as e_reconfig:
    dprint(f"main_app.py - Could not reconfigure stdout/stderr for UTF-8: {e_reconfig}")

# --- CRITICAL CONFIG IMPORT ---
config = None 
try:
    dprint("main_app.py - Attempting to import 'config' module...")
    import config 
    dprint("main_app.py - 'import config' statement executed.")
    if config is None: 
        dprint("CRITICAL ERROR: 'config' module is None after import. This indicates a severe import issue.")
        exit(1)
    test_attr = config.DEFAULT_AI_SERVICE 
    dprint(f"main_app.py - Successfully imported 'config' and accessed DEFAULT_AI_SERVICE: '{test_attr}'")
    dprint(f"Is 'config' in globals now? {'config' in globals()}")
except ImportError:
    print("ERROR: config.py not found! Please copy config_template.py to config.py and fill it out properly.")
    traceback.print_exc()
    print("CRITICAL: Application cannot start without config.py. Exiting.")
    exit(1) 
except AttributeError as e_attr: 
    print(f"ERROR: The imported 'config.py' is missing an expected attribute: {e_attr}")
    print("       This usually means your config.py is outdated or incomplete.")
    print("       Please compare it with the latest config_template.py and add missing variables.")
    traceback.print_exc()
    print("CRITICAL: config.py is incomplete. Application cannot continue. Exiting.")
    exit(1)
except Exception as e_config: 
    print(f"ERROR: An critical unexpected error occurred while importing or parsing config.py: {e_config}")
    traceback.print_exc()
    print("CRITICAL: config.py could not be used. Application cannot continue. Exiting.")
    exit(1)
dprint("main_app.py - Config import block successfully passed.")

from meshtastic_handler import MeshtasticHandler
from ai_bridge import AIBridge 
from conversation_manager import ConversationManager

# #############################################################################
# CONSOLE UI APPLICATION (CLI MODE) - MeshtasticAIAppConsole
# #############################################################################
class MeshtasticAIAppConsole:
    def __init__(self, attempt_number=1):
        dprint(f"MeshtasticAIAppConsole.__init__ - Initializing (Attempt {attempt_number})...")
        self.app_config = config 
        self.ai_bridge = AIBridge(self.app_config)
        self.conversation_manager = ConversationManager(self.app_config, self.ai_bridge)
        
        self.meshtastic_handler = None
        self.ai_node_id_hex = None
        self.active_channel_for_ai_posts = self.app_config.ACTIVE_MESHTASTIC_CHANNEL_INDEX
        self._stop_event = threading.Event()
        self.reconnection_monitor_thread = None 
        self.is_actively_reconnecting = False 

        self.url_pattern = re.compile(r'https?://[^\s/$.?#].[^\s]*', re.IGNORECASE)
        dprint("MeshtasticAIAppConsole.__init__ - URL pattern compiled.")

        self.last_response_times = {} 
        self.ai_response_probability = getattr(self.app_config, 'AI_RESPONSE_PROBABILITY', 0.85)
        self.ai_min_delay = getattr(self.app_config, 'AI_MIN_RESPONSE_DELAY_S', 2)
        self.ai_max_delay = getattr(self.app_config, 'AI_MAX_RESPONSE_DELAY_S', 8)
        self.ai_cooldown = getattr(self.app_config, 'AI_RESPONSE_COOLDOWN_S', 60)
        self.enable_ai_triage = getattr(self.app_config, 'ENABLE_AI_TRIAGE_ON_CHANNELS', False)
        self.triage_context_count = getattr(self.app_config, 'TRIAGE_CONTEXT_MESSAGE_COUNT', 3)
        dprint(f"MeshtasticAIAppConsole.__init__ - Human-like settings: Prob={self.ai_response_probability*100:.0f}%, Delay=({self.ai_min_delay}-{self.ai_max_delay}s), Cooldown={self.ai_cooldown}s, Triage={self.enable_ai_triage}")

        dprint("MeshtasticAIAppConsole.__init__ - Initializing Meshtastic Handler...")
        self.meshtastic_handler = MeshtasticHandler(
            connection_type=self.app_config.MESHTASTIC_CONNECTION_TYPE,
            device_specifier=self.app_config.MESHTASTIC_DEVICE_SPECIFIER,
            on_message_received_callback=self.handle_meshtastic_message
        )
        
        connect_wait_retries = 7
        initial_connection_confirmed = False
        while connect_wait_retries > 0:
            if self.meshtastic_handler and self.meshtastic_handler.is_connected:
                initial_connection_confirmed = True; break
            # dprint(f"MeshtasticAIAppConsole.__init__ - Waiting for connection... ({connect_wait_retries})") # Can be too noisy
            time.sleep(1); connect_wait_retries -= 1

        if not initial_connection_confirmed:
            if self.meshtastic_handler: self.meshtastic_handler.close()
            raise ConnectionError("CLI: Meshtastic handler initialized, but connection not confirmed (is_connected is False).")

        if self.meshtastic_handler.node_id is not None:
            self.ai_node_id_hex = f"{self.meshtastic_handler.node_id:x}"
            dprint(f"MeshtasticAIAppConsole.__init__ - Handler connected. AI Node ID: {self.ai_node_id_hex}")
        else:
            if self.meshtastic_handler: self.meshtastic_handler.close()
            raise ConnectionError("CLI: Handler reported connected but node_id is None.")
        
        dprint("MeshtasticAIAppConsole.__init__ - Initialization complete.")

    def handle_meshtastic_message(self, text, sender_id, sender_name, destination_id, channel_id):
        print(f"\n[RX CONSOLE] From: {sender_name} ({sender_id}) | To: {destination_id} | Ch: {channel_id} | Msg: \"{text[:100]}{'...' if len(text)>100 else ''}\"")
        print(f"DEBUG: Entered handle_meshtastic_message with sender_id={sender_id}, destination_id={destination_id}, ai_node_id_hex={self.ai_node_id_hex}")
        effective_channel_id = channel_id
        is_broadcast_msg = destination_id.lower() == f"{meshtastic.BROADCAST_NUM:x}".lower() or destination_id.lower() == "broadcast"
        if effective_channel_id is None and is_broadcast_msg: effective_channel_id = 0 
        elif effective_channel_id is None and not is_broadcast_msg: effective_channel_id = 0
        if self.ai_node_id_hex and sender_id.lower() == self.ai_node_id_hex.lower():
            print("DEBUG: Message is from AI itself. Ignoring.")
            return
        is_dm_to_ai = (self.ai_node_id_hex and destination_id.lower() == self.ai_node_id_hex.lower())
        print(f"DEBUG: is_dm_to_ai={is_dm_to_ai}")
        is_on_ai_active_channel_broadcast = (effective_channel_id == self.active_channel_for_ai_posts and is_broadcast_msg)
        conv_id_params = {"sender_id_hex": sender_id, "channel_id": effective_channel_id if not is_dm_to_ai else None, "ai_node_id_hex": self.ai_node_id_hex, "destination_id_hex": destination_id}
        conversation_id = self.conversation_manager._get_conversation_id(**conv_id_params)
        print(f"DEBUG: conversation_id={conversation_id}")
        self.conversation_manager.add_message(conversation_id, "user", text, user_name=sender_name, node_id=sender_id)
        should_consider_reply = False
        if is_dm_to_ai:
            print(f"CLI: Message is DM to AI. Will consider responding.")
            should_consider_reply = True
        elif is_on_ai_active_channel_broadcast:
            if self.enable_ai_triage:
                print(f"CLI: Message on active AI channel. Performing AI Triage for conv_id '{conversation_id}'...")
                history_for_triage_raw = self.conversation_manager.load_conversation(conversation_id)
                triage_context_messages = []
                for msg_entry in history_for_triage_raw[-(self.triage_context_count + 1) : -1]: 
                    if msg_entry.get("role") == "user":
                        name = msg_entry.get("user_name", f"Node-{msg_entry.get('node_id','????')}")
                        triage_context_messages.append(f"{name}: {msg_entry.get('content','')}")
                if self.ai_bridge.should_main_ai_respond(triage_context_messages, text, sender_name):
                    print("CLI: AI Triage decided YES. AI will consider responding.")
                    should_consider_reply = True
                else: print("CLI: AI Triage decided NO. AI will not respond.")
            else: 
                print("CLI: Message on active AI channel (Triage disabled). AI will consider responding.")
                should_consider_reply = True
        if not should_consider_reply:
            print("DEBUG: should_consider_reply is False. Exiting.")
            return
        now = time.time()
        if self.ai_cooldown > 0:
            last_response_time = self.last_response_times.get(conversation_id, 0)
            if (now - last_response_time) < self.ai_cooldown:
                print(f"CLI: AI Cooldown active for conv_id '{conversation_id}'. Skipping. Last response {now - last_response_time:.0f}s ago.")
                return 
        if random.random() > self.ai_response_probability:
            print(f"CLI: AI decided not to respond based on probability ({self.ai_response_probability*100:.0f}% chance).")
            return
        context_history = self.conversation_manager.get_contextual_history(conversation_id, for_user_name=sender_name)
        web_analysis_summary = None
        urls_found = self.url_pattern.findall(text)
        if urls_found:
            detected_url = urls_found[0] 
            print(f"INFO: URL detected: {detected_url}. Analyzing content...")
            try:
                web_analysis_summary = self.ai_bridge.analyze_url_content(detected_url)
                if web_analysis_summary: print(f"INFO: Web analysis summary: {web_analysis_summary[:100]}...")
                else: print(f"INFO: Web analysis for {detected_url} yielded no summary.")
            except Exception as e_web: print(f"ERROR: URL analysis failed: {e_web}"); traceback.print_exc(); web_analysis_summary = f"[Error analyzing URL]"
        print(f"DEBUG: Getting AI response for {sender_name} ({sender_id})...")
        ai_response_text = self.ai_bridge.get_response(context_history, text, sender_name, sender_id, web_analysis_summary=web_analysis_summary)
        print(f"DEBUG: ai_response_text={ai_response_text}")
        if ai_response_text and ai_response_text.strip():
            if self.ai_min_delay >= 0 and self.ai_max_delay > self.ai_min_delay :
                delay = random.uniform(self.ai_min_delay, self.ai_max_delay)
                print(f"AI response generated. Applying random delay of {delay:.1f}s before sending.")
                time.sleep(delay)
            print(f"[AI CONSOLE Replying -> {sender_name}] {ai_response_text[:100]}{'...' if len(ai_response_text)>100 else ''}")
            log_info(f"AI sent reply to {sender_name}")
            self.conversation_manager.add_message(conversation_id, "assistant", ai_response_text) 
            self.last_response_times[conversation_id] = time.time()
            reply_channel_index = effective_channel_id
            if self.meshtastic_handler and self.meshtastic_handler.is_connected:
                if is_dm_to_ai:
                    success, reason = self.meshtastic_handler.send_message(ai_response_text, destination_id_hex=sender_id, channel_index=reply_channel_index)
                    print(f"DEBUG: DM send_message result: success={success}, reason={reason}")
                    if not success:
                        print(f"ERROR: Failed to send DM reply: {reason}")
                else:
                    success, reason = self.meshtastic_handler.send_message(ai_response_text, channel_index=reply_channel_index)
                    print(f"DEBUG: Channel send_message result: success={success}, reason={reason}")
                    if not success:
                        print(f"ERROR: Failed to send channel reply: {reason}")
            else: print("ERROR: Cannot send AI reply, Meshtastic disconnected.")
        else: print(f"INFO: No valid AI response. No message sent to {sender_name}.")

    def run_console_ui(self):
        print("\n--- Meshtastic AI Bridge Console (CLI Mode) ---")
        if not self.meshtastic_handler or not self.meshtastic_handler.is_connected: print("WARNING: Meshtastic not connected at UI start.")
        print("Type 'quit' to exit, 'help' for commands.")
        while not self._stop_event.is_set():
            try:
                if self.meshtastic_handler and not self.meshtastic_handler.is_connected and not self.is_actively_reconnecting: print("\nWARNING: Meshtastic connection lost. Reconnection attempts in background.")
                cmd_input = input("CMD> ").strip()
                if not cmd_input: continue
                if cmd_input.lower() == 'quit': print("Exiting application..."); self._stop_event.set(); break
                elif cmd_input.lower() == 'help': 
                    print("\nCommands:")
                    print("  send <message>          - Send message as AI to active channel")
                    print("  dm <node_id_hex> <msg>  - Send direct message as AI")
                    print("  persona <text>          - Set AI persona")
                    print("  use_ai <openai|gemini>  - Switch AI service")
                    print("  active_channel <idx>    - Set active Meshtastic channel for AI's own posts")
                    print("  list_channels           - List available Meshtastic channels")
                    print("  token_limit <num>       - Set summarization token trigger")
                    print("  status                  - Show current status")
                    print("  quit                    - Exit the application\n")
                elif cmd_input.startswith("send "):
                    if not self.meshtastic_handler or not self.meshtastic_handler.is_connected: print("ERROR: Meshtastic not connected."); continue
                    msg = cmd_input[len("send "):].strip();
                    if msg:
                        success, reason = self.meshtastic_handler.send_message(f"{msg}", channel_index=self.active_channel_for_ai_posts)
                        if not success:
                            print(f"ERROR: Failed to send message: {reason}")
                    else:
                        print("Usage: send <message>")
                elif cmd_input.startswith("dm "):
                    if not self.meshtastic_handler or not self.meshtastic_handler.is_connected: print("ERROR: Meshtastic not connected."); continue
                    parts = cmd_input.split(" ", 2); node_id_hex, msg = (parts[1], parts[2].strip()) if len(parts) == 3 else (None,None)
                    if node_id_hex and msg:
                        success, reason = self.meshtastic_handler.send_message(f"{msg}", destination_id_hex=node_id_hex)
                        if not success:
                            print(f"ERROR: Failed to send DM: {reason}")
                    else: print("Usage: dm <node_id_hex> <message>")
                elif cmd_input.startswith("persona "):
                    persona_text = cmd_input[len("persona "):].strip(); self.ai_bridge.set_persona(persona_text) if persona_text else print("Persona text empty.")
                elif cmd_input.startswith("use_ai "): self.ai_bridge.set_ai_service(cmd_input[len("use_ai "):].strip().lower())
                elif cmd_input.startswith("active_channel "):
                    try: self.active_channel_for_ai_posts = int(cmd_input[len("active_channel "):].strip())
                    except ValueError: print("Invalid channel index.")
                elif cmd_input.lower() == "list_channels":
                    if not self.meshtastic_handler or not self.meshtastic_handler.is_connected: print("ERROR: Meshtastic not connected."); continue
                    self.meshtastic_handler.list_channels() 
                elif cmd_input.startswith("token_limit "):
                    try: limit = int(cmd_input[len("token_limit "):].strip()); self.app_config.SUMMARIZE_THRESHOLD_TOKENS = limit if limit > 50 else print("Token limit too low.")
                    except ValueError: print("Invalid token limit.")
                elif cmd_input.lower() == "status":
                    print("\n--- Status ---")
                    print(f"  AI Service: {self.ai_bridge.current_ai_service if self.ai_bridge else 'N/A'}")
                    persona_display = 'N/A'; text_persona = self.ai_bridge.current_persona if self.ai_bridge else None
                    if text_persona: persona_display = text_persona[:97] + "..." if len(text_persona) > 100 else text_persona
                    print(f"  AI Persona: {persona_display}")
                    print(f"  AI Node ID: {self.ai_node_id_hex or 'N/A'}")
                    print(f"  AI Active Channel: {self.active_channel_for_ai_posts}")
                    print(f"  Summarize Threshold: {self.app_config.SUMMARIZE_THRESHOLD_TOKENS}")
                    print(f"  AI Response Prob: {self.ai_response_probability*100:.0f}%")
                    print(f"  AI Response Delay: {self.ai_min_delay}-{self.ai_max_delay}s")
                    print(f"  AI Response Cooldown: {self.ai_cooldown}s")
                    print(f"  AI Triage on Channels: {self.enable_ai_triage}")
                    mh_status = "No Handler"; handler_is_connected = self.meshtastic_handler.is_connected if self.meshtastic_handler else False
                    if self.meshtastic_handler: mh_status = "Connected" if handler_is_connected else "Disconnected"
                    print(f"  Meshtastic Status: {mh_status}")
                    if self.is_actively_reconnecting: print("  Reconnection in progress...")
                    print("---------------\n")
                else: print("Unknown command. Type 'help'.")
            except KeyboardInterrupt: print("\nCtrl+C detected. Type 'quit' to exit.")
            except EOFError: print("\nEOF. Exiting."); self._stop_event.set(); break
            except Exception as e_ui: print(f"ERROR in console UI: {e_ui}"); traceback.print_exc()
        print("Console UI loop ended."); print("Console UI initiated shutdown sequence.")

    def close_app(self):
        dprint("MeshtasticAIAppConsole.close_app() called.")
        self._stop_event.set()
        if self.meshtastic_handler: self.meshtastic_handler.close()
        if self.reconnection_monitor_thread and self.reconnection_monitor_thread.is_alive():
            dprint("Waiting for console reconnection monitor thread to join...")
            self.reconnection_monitor_thread.join(timeout=2.0) 
            if self.reconnection_monitor_thread.is_alive(): print("WARNING: Console reconnection monitor thread did not join.")
        dprint("Console App resources released.")

# --- Main Execution & Reconnection Logic (Helper Functions MUST be defined before __main__) ---
def try_create_cli_app_instance(attempt_num):
    try: 
        app_instance = MeshtasticAIAppConsole(attempt_number=attempt_num)
        return app_instance 
    except ConnectionError as e: 
        print(f"ERROR on CLI app creation attempt {attempt_num} (ConnectionError): {e}")
    except Exception as e: 
        print(f"ERROR on CLI app creation attempt {attempt_num} (Unexpected Exception): {e}")
        traceback.print_exc()
    return None

def cli_connection_monitor_loop(app_instance_ref_list, stop_event_ref):
    dprint("CLI Connection monitor thread started.")
    app_config_local = config 
    while not stop_event_ref.is_set():
        for _ in range(getattr(app_config_local, 'MONITOR_CONNECTION_INTERVAL', 30)):
            if stop_event_ref.is_set(): break
            time.sleep(1)
        if stop_event_ref.is_set(): break
        if not app_instance_ref_list or app_instance_ref_list[0] is None: 
            dprint("CLI Monitor: App instance is None.")
            time.sleep(5)
            continue
        app = app_instance_ref_list[0]
        if not app or not hasattr(app, 'meshtastic_handler'): 
            dprint("CLI Monitor: App instance or meshtastic_handler not available.")
            continue
        if not app.meshtastic_handler or not app.meshtastic_handler.is_connected:
            if not app.is_actively_reconnecting:
                print("INFO: CLI Monitor: Detected disconnection. Attempting to re-establish.")
                app.is_actively_reconnecting = True
                if app.meshtastic_handler: 
                    dprint("CLI Monitor closing existing handler.")
                    app.meshtastic_handler.close()
                    app.meshtastic_handler = None
                    app.ai_node_id_hex = None
                reconnect_attempts = 0
                max_retries = getattr(app_config_local, 'RECONNECTION_MAX_RETRIES', 3)
                retry_delay = getattr(app_config_local, 'RECONNECTION_RETRY_DELAY', 10)
                while reconnect_attempts < max_retries and not stop_event_ref.is_set():
                    reconnect_attempts += 1
                    dprint(f"CLI Monitor: Reconnection attempt {reconnect_attempts}/{max_retries}...")
                    try:
                        app.meshtastic_handler = MeshtasticHandler( 
                            connection_type=app.app_config.MESHTASTIC_CONNECTION_TYPE, 
                            device_specifier=app.app_config.MESHTASTIC_DEVICE_SPECIFIER, 
                            on_message_received_callback=app.handle_meshtastic_message 
                        )
                        connect_wait_retries = 7
                        reconnected_successfully = False
                        while connect_wait_retries > 0:
                            if app.meshtastic_handler.is_connected: 
                                reconnected_successfully = True
                                break
                            time.sleep(1)
                            connect_wait_retries -= 1
                        if reconnected_successfully and app.meshtastic_handler.node_id is not None: 
                            app.ai_node_id_hex = f"{app.meshtastic_handler.node_id:x}"
                            print(f"INFO: CLI Monitor: Reconnection successful! AI Node ID: {app.ai_node_id_hex}")
                            break 
                        else: 
                            dprint(f"CLI Monitor: Reconn attempt {reconnect_attempts} - handler status uncertain.")
                            if app.meshtastic_handler: app.meshtastic_handler.close()
                            app.meshtastic_handler = None 
                    except Exception as e_recon: 
                        print(f"ERROR: CLI Monitor: Exception during reconn attempt {reconnect_attempts}: {e_recon}")
                        if app.meshtastic_handler: app.meshtastic_handler.close()
                        app.meshtastic_handler = None 
                    if reconnect_attempts < max_retries and not stop_event_ref.is_set():
                        dprint(f"CLI Monitor: Waiting {retry_delay}s before next attempt.")
                        for _ in range(retry_delay): 
                            if stop_event_ref.is_set(): break
                            time.sleep(1)
                    if stop_event_ref.is_set(): break 
                if not (app.meshtastic_handler and app.meshtastic_handler.is_connected): 
                    print("ERROR: CLI Monitor: Failed to reconnect.")
                app.is_actively_reconnecting = False
            else: 
                if app.meshtastic_handler and app.meshtastic_handler.is_connected and app.is_actively_reconnecting: 
                    app.is_actively_reconnecting = False
                    dprint("CLI Monitor: Connection restored.")
    dprint("CLI Connection monitor thread finished.")

class MeshtasticInteractive(App[None]):
    TITLE = "Meshtastic AI Bridge - Interactive Interface"
    CSS_PATH = "meshtastic_tui.css"
    BINDINGS = [
        ("q", "quit_app", "Quit"),
        ("ctrl+c", "quit_app", "Quit"),
        ("f", "force_ai", "Force AI Response")  # Add keyboard shortcut
    ]
    current_conversation_id = reactive(None, layout=True)
    sidebar_conversations = reactive([], layout=True)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="app-grid"):
            with VerticalScroll(id="sidebar", classes="sidebar-area"):
                yield Label("Conversations", classes="sidebar-title")
                yield ListView(id="conversation_list")
            with Container(id="chat-view-container"):
                yield RichLog(id="chat_log", wrap=True, markup=True, classes="chat-log-area")
                with Horizontal(id="input-container"):
                    yield Input(placeholder="Type message...", id="message_input")
                    yield Button("🤖 Force AI", id="force_ai_button", classes="force-ai-button")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events"""
        if event.button.id == "force_ai_button":
            await self.force_ai_response()

    async def action_force_ai(self) -> None:
        """Action handler for force AI keyboard shortcut"""
        await self.force_ai_response()

    async def force_ai_response(self) -> None:
        """Force AI to respond to recent messages"""
        if not self.current_conversation_id:
            return
        
        # Get the last few messages from the current conversation
        history = self.conversation_manager.load_conversation(self.current_conversation_id)
        if not history:
            return
        
        # Get the last 3-4 messages
        recent_messages = history[-4:] if len(history) >= 4 else history
        
        # Create a context from recent messages
        context = "\n".join([
            f"{msg.get('user_name', 'Unknown')}: {msg.get('content', '')}"
            for msg in recent_messages
        ])
        
        # Create a prompt for the AI
        prompt = f"Recent conversation context:\n{context}\n\nPlease provide a natural response to this conversation."
        
        # Run AI worker without triage
        self.run_worker(
            AIProcessingWorker(
                self,
                prompt,
                "local_tui_user",
                "You (TUI)",
                self.active_channel_for_ai_posts,
                False,  # not a DM
                self.current_conversation_id,
                self.url_pattern,
                skip_triage=True  # Skip triage for forced responses
            ),
            exclusive=True,
            group="ai_proc",
            thread=True
        )

    async def process_incoming_mesh_message(self, text, sender_id, sender_name, destination_id, channel_id):
        str_ai_id = str(self.ai_node_id_hex or "").lower()
        str_dest_id = str(destination_id or "").lower()
        is_dm_to_ai = (str_ai_id and str_dest_id == str_ai_id)
        eff_ch_id = channel_id if channel_id is not None else 0

        # Determine conversation ID (mirroring CLI logic)
        conv_params = {"sender_id_hex": str(sender_id), "channel_id": eff_ch_id if not is_dm_to_ai else None, "ai_node_id_hex": str_ai_id, "destination_id_hex": str_dest_id}
        conv_id = self.conversation_manager._get_conversation_id(**conv_params)
        self.conversation_manager.add_message(conv_id, "user", text, user_name=sender_name, node_id=str(sender_id))

        if is_dm_to_ai:
            dprint(f"TUI: AI to respond to DM. Starting worker for conv_id={conv_id}.")
            self.run_worker(
                AIProcessingWorker(self, text, str(sender_id), sender_name, eff_ch_id, True, conv_id, self.url_pattern),
                exclusive=True, group="ai_proc", thread=True
            )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meshtastic AI Bridge Application")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run with interactive TUI (default)")
    parser.add_argument("--no-debug-prints", action="store_true", help="Disable verbose DEBUG prints")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable ultra-verbose debug logging")
    cmd_args = parser.parse_args()
    
    # Initialize the wrapper for CLI app
    active_cli_app_wrapper = [None]

    if cmd_args.no_debug_prints: print_debug = False
    if cmd_args.debug: print_debug = True
    dprint(f"main_app.py - Parsed cmd args: {cmd_args}")
    
    # Default to interactive mode if no other mode specified
    if not cmd_args.interactive and not any([cmd_args.no_debug_prints, cmd_args.debug]):
        cmd_args.interactive = True
    
    if cmd_args.interactive:
        dprint("Starting Interactive TUI mode...")
        try:
            tui_main()
        except Exception as e:
            print(f"ERROR: Interactive TUI failed to start: {e}")
            traceback.print_exc()
        dprint("Interactive TUI mode ended.")
    else:
        print("ERROR: Interactive TUI mode is now the default. Use -i to explicitly enable it.")
        sys.exit(1)

    dprint("main_app.py - Script finished.")



