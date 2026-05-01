from web_ui import app, start_in_background
import time

start_in_background("0.0.0.0", 8080)
while True:
    time.sleep(1)
