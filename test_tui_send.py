#!/usr/bin/env python3
"""
Test script to debug TUI message sending issue
"""
import time
from meshtastic_handler import MeshtasticHandler
import config

def test_meshtastic_send():
    """Test basic meshtastic send functionality"""
    print("Starting Meshtastic send test...")
    
    try:
        # Initialize handler
        handler = MeshtasticHandler(
            connection_type=config.MESHTASTIC_CONNECTION_TYPE,
            device_specifier=config.MESHTASTIC_DEVICE_SPECIFIER,
            on_message_received_callback=lambda *args: print(f"Received: {args}")
        )
        
        # Wait for connection
        retries = 10
        while retries > 0 and not handler.is_connected:
            print(f"Waiting for connection... ({retries})")
            time.sleep(1)
            retries -= 1
        
        if not handler.is_connected:
            print("ERROR: Could not connect to Meshtastic")
            return
        
        print(f"Connected! Node ID: {handler.node_id:x}")
        
        # Test 1: Send to channel
        print("\nTest 1: Sending to channel 0...")
        result = handler.send_message("Test message from debug script", channel_index=0)
        print(f"Channel send result: {result}")
        
        # Test 2: Send DM (if you have a target node)
        # Uncomment and set a valid node ID to test DM
        # target_node = "e49a0455"  # Example node ID
        # print(f"\nTest 2: Sending DM to {target_node}...")
        # result = handler.send_message("Test DM from debug script", destination_id_hex=target_node, channel_index=0)
        # print(f"DM send result: {result}")
        
        # Keep alive to receive any responses
        print("\nListening for 10 seconds...")
        time.sleep(10)
        
        # Close
        handler.close()
        print("Test complete.")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_meshtastic_send() 