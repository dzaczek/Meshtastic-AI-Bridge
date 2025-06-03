#!/usr/bin/env python3
"""
Diagnostic script to identify message sending issues in interactive mode
"""
import sys
import time

print("=== Interactive Mode Message Sending Diagnostic ===")
print("\nChecking logs for key patterns...\n")

# Read the log file
log_file = "interactive.backend.log"
try:
    with open(log_file, 'r') as f:
        lines = f.readlines()
except FileNotFoundError:
    print(f"ERROR: {log_file} not found. Please run the application in interactive mode first.")
    sys.exit(1)

# Analysis patterns
patterns = {
    "AI Response Generated": [],
    "meshtastic_handler.send_message() returned": [],
    "Using backend handler directly": [],
    "Using TUI's handler reference": [],
    "send_message returned False": [],
    "Error sending": [],
    "Meshtastic disconnected": [],
    "interface is None": [],
    "Manual send result": [],
    "AI sent DM reply": [],
    "AI sent channel reply": [],
    "Failed to send": []
}

# Search for patterns
for i, line in enumerate(lines):
    for pattern in patterns:
        if pattern in line:
            patterns[pattern].append((i+1, line.strip()))

# Report findings
print("=== ANALYSIS RESULTS ===\n")

# Check if AI responses are being generated
ai_responses = patterns["AI Response Generated"]
send_attempts = patterns["meshtastic_handler.send_message() returned"]

print(f"1. AI Responses Generated: {len(ai_responses)}")
print(f"2. Send Attempts: {len(send_attempts)}")

# Check which handler is being used
backend_used = patterns["Using backend handler directly"]
tui_used = patterns["Using TUI's handler reference"]
print(f"\n3. Handler Usage:")
print(f"   - Backend handler: {len(backend_used)} times")
print(f"   - TUI handler: {len(tui_used)} times")

# Check for failures
failures = patterns["send_message returned False"]
errors = patterns["Error sending"]
disconnects = patterns["Meshtastic disconnected"]
interface_none = patterns["interface is None"]

print(f"\n4. Failures Detected:")
print(f"   - Send returned False: {len(failures)}")
print(f"   - Send errors: {len(errors)}")
print(f"   - Disconnected: {len(disconnects)}")
print(f"   - Interface None: {len(interface_none)}")

# Check manual vs AI sends
manual_sends = patterns["Manual send result"]
ai_dm_success = patterns["AI sent DM reply"]
ai_ch_success = patterns["AI sent channel reply"]

print(f"\n5. Send Success Comparison:")
print(f"   - Manual sends: {len(manual_sends)}")
print(f"   - AI DM success: {len(ai_dm_success)}")
print(f"   - AI channel success: {len(ai_ch_success)}")

# Show failures in detail
if failures or errors:
    print("\n=== FAILURE DETAILS ===")
    for line_no, line in failures[:5]:  # Show first 5
        print(f"Line {line_no}: {line}")
    for line_no, line in errors[:5]:  # Show first 5
        print(f"Line {line_no}: {line}")

# Show send results
if send_attempts:
    print("\n=== SEND RESULTS ===")
    for line_no, line in send_attempts[-10:]:  # Show last 10
        print(f"Line {line_no}: {line}")
        # Check if True or False
        if "True" in line:
            print("  ✓ SUCCESS")
        elif "False" in line:
            print("  ✗ FAILED")

print("\n=== RECOMMENDATIONS ===")
if len(failures) > 0:
    print("- Messages are failing to send (returning False)")
    print("- Check if the Meshtastic device is properly connected")
    print("- Verify the channel index is correct")
elif len(errors) > 0:
    print("- Exceptions occurring during send")
    print("- Check the error details above")
elif len(send_attempts) == 0:
    print("- No send attempts found - AI responses may not be reaching the send code")
    print("- Check if AI is generating responses")
else:
    print("- Send attempts are being made")
    print("- Check if messages are actually appearing on other devices")

print("\nDiagnostic complete.") 