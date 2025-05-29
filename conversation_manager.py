# conversation_manager.py
import json
import os
import time
import traceback
import meshtastic # Required for meshtastic.BROADCAST_NUM if used in _get_conversation_id logic

def simple_token_counter(text_content):
    if not isinstance(text_content, str): return 0
    return len(text_content.split()) # Very rough estimate

class ConversationManager:
    def __init__(self, app_config, ai_bridge_instance, storage_path="conversations/"):
        self.config = app_config
        self.ai_bridge = ai_bridge_instance 
        self.storage_path = storage_path
        if self.storage_path and not os.path.exists(self.storage_path):
            try:
                os.makedirs(self.storage_path)
                print(f"Created conversation storage directory: {self.storage_path}")
            except OSError as e:
                print(f"ERROR creating conversation storage directory {self.storage_path}: {e}")
                self.storage_path = None 

    def _get_conversation_id(self, sender_id_hex, channel_id=None, ai_node_id_hex=None, destination_id_hex=None):
        sender_id_hex_str = str(sender_id_hex).lower()
        ai_node_id_hex_str = str(ai_node_id_hex).lower() if ai_node_id_hex else None
        destination_id_hex_str = str(destination_id_hex).lower() if destination_id_hex else None
        channel_id_str = str(channel_id) if channel_id is not None else None

        is_dm_to_ai = (ai_node_id_hex_str and destination_id_hex_str == ai_node_id_hex_str and sender_id_hex_str != ai_node_id_hex_str)
        is_dm_from_ai_to_user = (ai_node_id_hex_str and sender_id_hex_str == ai_node_id_hex_str and \
                                 destination_id_hex_str and \
                                 destination_id_hex_str != "broadcast" and \
                                 destination_id_hex_str != f"{meshtastic.BROADCAST_NUM:x}".lower() and \
                                 destination_id_hex_str != ai_node_id_hex_str)

        if is_dm_to_ai:
            user_ids = sorted([ai_node_id_hex_str, sender_id_hex_str])
            return f"dm_{user_ids[0]}_{user_ids[1]}"
        elif is_dm_from_ai_to_user: 
            user_ids = sorted([ai_node_id_hex_str, destination_id_hex_str])
            return f"dm_{user_ids[0]}_{user_ids[1]}"
        elif channel_id_str is not None:
            return f"channel_{channel_id_str}"
        else:
            print(f"Warning: Fallback conversation ID for sender {sender_id_hex_str}, (To: {destination_id_hex_str}, Ch: {channel_id_str}).")
            if destination_id_hex_str and destination_id_hex_str != "broadcast" and destination_id_hex_str != f"{meshtastic.BROADCAST_NUM:x}".lower():
                user_ids = sorted([sender_id_hex_str, destination_id_hex_str])
                return f"dm_other_{user_ids[0]}_{user_ids[1]}"
            return f"unknown_context_sender_{sender_id_hex_str}"


    def _get_file_path(self, conversation_id):
        if not self.storage_path:
            return None
        safe_conv_id = "".join(c for c in str(conversation_id) if c.isalnum() or c in ('_', '-')).rstrip()
        if not safe_conv_id: safe_conv_id = "unknown_conversation"
        return os.path.join(self.storage_path, f"{safe_conv_id}.json")

    def load_conversation(self, conversation_id):
        file_path = self._get_file_path(conversation_id)
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"ERROR loading conversation {conversation_id} from {file_path}: {e}")
        return [] 

    def save_conversation(self, conversation_id, history):
        file_path = self._get_file_path(conversation_id)
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(history, f, indent=2)
            except IOError as e:
                print(f"ERROR saving conversation {conversation_id} to {file_path}: {e}")

    def add_message(self, conversation_id, role, content, user_name=None, node_id=None):
        history = self.load_conversation(conversation_id)
        message_entry = {"role": role, "content": content, "timestamp": time.time()}
        if role == "user": 
            if user_name: message_entry["user_name"] = user_name
            if node_id: message_entry["node_id"] = node_id
        
        history.append(message_entry)
        self.save_conversation(conversation_id, history)
        return history

    def get_contextual_history(self, conversation_id, for_user_name="User"):
        history = self.load_conversation(conversation_id)
        
        ai_formatted_history = []
        for msg in history:
            ai_formatted_history.append({"role": msg["role"], "content": msg["content"]})

        current_total_simple_tokens = sum(simple_token_counter(msg["content"]) for msg in ai_formatted_history)

        if current_total_simple_tokens > self.config.SUMMARIZE_THRESHOLD_TOKENS and len(ai_formatted_history) > 5: 
            num_recent_to_keep = 3 
            if len(ai_formatted_history) > num_recent_to_keep:
                to_summarize_msgs = ai_formatted_history[:-num_recent_to_keep]
                recent_msgs_for_ai = ai_formatted_history[-num_recent_to_keep:]
                
                text_to_summarize = "\n".join([f"{m['role']}: {m['content']}" for m in to_summarize_msgs])
                
                if text_to_summarize.strip() and self.ai_bridge:
                    summary = self.ai_bridge.summarize_text(text_to_summarize)
                    summarized_history_for_ai = [{"role": "system", "content": f"Summary of earlier parts of this conversation: {summary}"}]
                    summarized_history_for_ai.extend(recent_msgs_for_ai)
                    return summarized_history_for_ai

        if len(ai_formatted_history) > self.config.MAX_HISTORY_MESSAGES_FOR_CONTEXT:
            ai_formatted_history = ai_formatted_history[-self.config.MAX_HISTORY_MESSAGES_FOR_CONTEXT:]
            
        return ai_formatted_history


