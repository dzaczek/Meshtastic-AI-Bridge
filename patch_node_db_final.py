import re
with open("node_db.py", "r") as f:
    content = f.read()

search = """
        top_links = _conn.execute(
            \"\"\"SELECT from_id, to_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id != '?' AND to_id NOT IN ('?', 'broadcast', 'ffffffff')
               GROUP BY from_id, to_id ORDER BY cnt DESC LIMIT 10\"\"\",
            (start_ts,)
        ).fetchall()

        dest_stats = _conn.execute(
"""

replace = """
        top_links = _conn.execute(
            \"\"\"SELECT from_id, to_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id != '?' AND to_id NOT IN ('?', 'broadcast', 'ffffffff')
               GROUP BY from_id, to_id ORDER BY cnt DESC LIMIT 10\"\"\",
            (start_ts,)
        ).fetchall()

        encrypted_senders = _conn.execute(
            \"\"\"SELECT from_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id != '?' AND encrypted=1
               GROUP BY from_id ORDER BY cnt DESC LIMIT 100\"\"\",
            (start_ts,)
        ).fetchall()

        encrypted_links = _conn.execute(
            \"\"\"SELECT from_id, to_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id != '?' AND to_id NOT IN ('?', 'broadcast', 'ffffffff') AND encrypted=1
               GROUP BY from_id, to_id ORDER BY cnt DESC LIMIT 100\"\"\",
            (start_ts,)
        ).fetchall()

        # Get positions of top senders to use in heatmap
        node_positions = _conn.execute(
            \"\"\"SELECT node_id, lat, lon FROM position_history
               WHERE ts = (SELECT MAX(ts) FROM position_history p2 WHERE p2.node_id = position_history.node_id)
            \"\"\"
        ).fetchall()
        positions_map = {r[0]: {"lat": r[1], "lon": r[2]} for r in node_positions}

        dest_stats = _conn.execute(
"""

if search in content:
    content = content.replace(search, replace)
    with open("node_db.py", "w") as f:
        f.write(content)
    print("Replaced section 1")
else:
    print("Section 1 not found")

search2 = """
    return {
        "total": total_packets,
        "encrypted": total_encrypted,
        "plaintext": total_packets - total_encrypted,
        "hourly": hourly,
        "top_senders": [{"id": r[0], "count": r[1]} for r in top_senders],
        "top_links": [{"from": r[0], "to": r[1], "count": r[2]} for r in top_links],
        "destinations": {"broadcast": broadcast_cnt, "private": private_cnt},
        "top_types": [{"type": r[0], "count": r[1]} for r in top_types]
    }
"""

replace2 = """
    return {
        "total": total_packets,
        "encrypted": total_encrypted,
        "plaintext": total_packets - total_encrypted,
        "hourly": hourly,
        "top_senders": [{"id": r[0], "count": r[1]} for r in top_senders],
        "top_links": [{"from": r[0], "to": r[1], "count": r[2]} for r in top_links],
        "encrypted_senders": [{"id": r[0], "count": r[1]} for r in encrypted_senders],
        "encrypted_links": [{"from": r[0], "to": r[1], "count": r[2]} for r in encrypted_links],
        "node_positions": positions_map,
        "destinations": {"broadcast": broadcast_cnt, "private": private_cnt},
        "top_types": [{"type": r[0], "count": r[1]} for r in top_types]
    }
"""

if search2 in content:
    content = content.replace(search2, replace2)
    with open("node_db.py", "w") as f:
        f.write(content)
    print("Replaced section 2")
else:
    print("Section 2 not found")
