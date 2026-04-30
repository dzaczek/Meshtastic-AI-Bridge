with open("web_ui.py", "r") as f:
    content = f.read()

search = """
        # Resolve names for top_senders and top_links
        if "top_senders" in stats:
            for s in stats["top_senders"]:
                s["name"] = _node_name(s["id"], getattr(_meshtastic_handler, "interface", None))
        if "top_links" in stats:
            for l in stats["top_links"]:
                l["from_name"] = _node_name(l["from"], getattr(_meshtastic_handler, "interface", None))
                l["to_name"] = _node_name(l["to"], getattr(_meshtastic_handler, "interface", None))
"""

replace = """
        # Resolve names for top_senders and top_links
        if "top_senders" in stats:
            for s in stats["top_senders"]:
                s["name"] = _node_name(s["id"], getattr(_meshtastic_handler, "interface", None))
        if "top_links" in stats:
            for l in stats["top_links"]:
                l["from_name"] = _node_name(l["from"], getattr(_meshtastic_handler, "interface", None))
                l["to_name"] = _node_name(l["to"], getattr(_meshtastic_handler, "interface", None))
        if "encrypted_senders" in stats:
            for s in stats["encrypted_senders"]:
                s["name"] = _node_name(s["id"], getattr(_meshtastic_handler, "interface", None))
        if "encrypted_links" in stats:
            for l in stats["encrypted_links"]:
                l["from_name"] = _node_name(l["from"], getattr(_meshtastic_handler, "interface", None))
                l["to_name"] = _node_name(l["to"], getattr(_meshtastic_handler, "interface", None))
"""

if search in content:
    with open("web_ui.py", "w") as f:
        f.write(content.replace(search, replace))
    print("Replaced web_ui.py successfully.")
else:
    print("Search string not found in web_ui.py")
