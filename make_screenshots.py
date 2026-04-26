#!/usr/bin/env python3
"""Generate SVG mockup screenshots for README."""
import os, textwrap

W, H = 960, 580
BG   = "#050d14"
SURF = "#0d1720"
SURF2= "#111c28"
SURF3= "#0a1018"
BORD = "#1a3045"
TEXT = "#d4e5f0"
MUTE = "#4a6a7a"
PRIM = "#00ff88"
BLUE = "#1e90ff"
AI   = "#ffa040"
ERR  = "#ff4d4d"
YEL  = "#ffd700"

def hdr(tabs, active):
    btns = ""
    x = 12
    for t in tabs:
        col = PRIM if t == active else TEXT
        bg  = "#0a2e1a" if t == active else "none"
        btns += f'<rect x="{x}" y="4" width="{len(t)*8+20}" height="26" rx="4" fill="{bg}"/>'
        btns += f'<text x="{x+10}" y="21" fill="{col}" font-size="12" font-weight="bold">{t}</text>'
        x   += len(t)*8 + 28
    return f'''
<rect x="0" y="0" width="{W}" height="34" fill="{SURF}" opacity=".95"/>
<rect x="0" y="33" width="{W}" height="1" fill="{BORD}"/>
<text x="10" y="50" fill="{PRIM}" font-size="13" font-weight="bold" dy="-17">⬡ Mesh AI Bridge</text>
<g transform="translate(160,4)">{btns}</g>
<text x="{W-60}" y="21" fill="{MUTE}" font-size="11">v5.8</text>
'''

def panel(x, y, w, h, rx=10, fill=SURF, stroke=BORD, opacity=".88"):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1" opacity="{opacity}"/>'

def txt(x, y, s, fill=TEXT, size=12, weight="normal", anchor="start", opacity=1.0):
    return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" opacity="{opacity}">{s}</text>'

def badge(x, y, label, color):
    w = len(label)*7 + 14
    return f'<rect x="{x}" y="{y-12}" width="{w}" height="18" rx="9" fill="{color}" opacity=".25"/>' \
           f'<text x="{x+w//2}" y="{y}" fill="{color}" font-size="10" font-weight="bold" text-anchor="middle">{label}</text>'

def svg_wrap(content, title="Meshtastic AI Bridge"):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#030a12"/>
      <stop offset="100%" stop-color="#071525"/>
    </linearGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="2"/></filter>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  <!-- subtle grid -->
  <g opacity=".04" stroke="#1e90ff" stroke-width="0.5">
    {''.join(f'<line x1="{x}" y1="0" x2="{x}" y2="{H}"/>' for x in range(0,W,40))}
    {''.join(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}"/>' for y in range(0,H,40))}
  </g>
  <g font-family="'JetBrains Mono', 'Consolas', monospace">
{content}
  </g>
</svg>'''

# ── SCREEN 1: OPS DASHBOARD ─────────────────────────────────────────────────
def make_ops():
    TABS = ["OPS","CHAT","NODES","MAP","PACKETS","RADAR","CONFIG"]
    c = hdr(TABS, "OPS")
    c += f'<rect x="0" y="34" width="{W}" height="{H-34}" fill="url(#bg)"/>'

    # Map area (big card left)
    c += panel(10, 44, 530, 290, fill=SURF3)
    c += txt(20, 62, "MAP OVERVIEW", PRIM, 9, "bold", opacity=.8)
    # fake map tiles
    c += f'<rect x="10" y="44" width="530" height="290" rx="10" fill="#071020" opacity=".6"/>'
    # grid lines for map feel
    for gx in range(10, 540, 45):
        c += f'<line x1="{gx}" y1="44" x2="{gx}" y2="334" stroke="#0a2040" stroke-width="0.7"/>'
    for gy in range(44, 334, 35):
        c += f'<line x1="10" y1="{gy}" x2="540" y2="{gy}" stroke="#0a2040" stroke-width="0.7"/>'
    # node dots
    nodes = [
        (200,150,"Base Station","#ffff00",True),
        (310,200,"Alpha Node","#00ff88",False),
        (140,230,"Mobile-1","#00ff88",False),
        (380,130,"Gateway","#f0883e",False),
        (450,260,"Remote-7","#88aaff",False),
        (260,280,"Relay-3","#00ff88",False),
    ]
    # traceroute line
    pts = [(200,150),(310,200),(380,130)]
    for i in range(len(pts)-1):
        c += f'<line x1="{pts[i][0]}" y1="{pts[i][1]}" x2="{pts[i+1][0]}" y2="{pts[i+1][1]}" stroke="{PRIM}" stroke-width="2" stroke-dasharray="6 3" opacity=".7"/>'
    for nx,ny,name,col,mine in nodes:
        r = 8 if mine else 6
        c += f'<circle cx="{nx}" cy="{ny}" r="{r+4}" fill="{col}" opacity=".12"/>'
        c += f'<circle cx="{nx}" cy="{ny}" r="{r}" fill="{col}" opacity=".85"/>'
        c += f'<text x="{nx+10}" y="{ny+4}" fill="{TEXT}" font-size="9">{name}</text>'

    # Stats row bottom-left
    c += panel(10, 342, 530, 82, fill=SURF2)
    stats = [("RX Packets","1 847",BLUE),("TX Sent","43",PRIM),("AI Responses","38",AI),
             ("Nodes Seen","12",YEL),("Uptime","14h 32m",TEXT)]
    for i,(lbl,val,col) in enumerate(stats):
        sx = 28 + i*106
        c += txt(sx, 368, lbl, MUTE, 9)
        c += txt(sx, 390, val, col, 20, "bold")

    # Sidebar right
    # Activity feed
    c += panel(548, 44, 402, 200, fill=SURF2)
    c += txt(558, 62, "LIVE ACTIVITY", PRIM, 9, "bold", opacity=.8)
    events = [
        ("[10:24:01]","RX","Alpha Node","Hello from the field!",BLUE),
        ("[10:23:55]","AI","MeshBot","Acknowledged! SNR is -5 dB here.",AI),
        ("[10:23:48]","TX","MeshBot → Mobile-1","Roger, over.",PRIM),
        ("[10:23:40]","RX","Gateway","POSITION update received",BLUE),
        ("[10:23:30]","RX","Remote-7","Battery: 78%",BLUE),
        ("[10:23:12]","RX","Relay-3","ping",MUTE),
    ]
    for i,(ts,typ,src,msg,col) in enumerate(events):
        y = 82 + i*24
        c += txt(558, y, ts, MUTE, 9)
        c += txt(618, y, typ, col, 9, "bold")
        c += txt(656, y, f"{src}: {msg[:30]}", TEXT, 9)

    # Top nodes
    c += panel(548, 252, 402, 172, fill=SURF2)
    c += txt(558, 270, "TOP NODES  (signal strength)", PRIM, 9, "bold", opacity=.8)
    tnodes = [("Base Station","Direct","SNR +8.5",PRIM),
              ("Alpha Node","Direct","SNR +3.1",PRIM),
              ("Gateway","MQTT","SNR +1.2",AI),
              ("Mobile-1","1 hop","SNR -2.0",YEL),
              ("Remote-7","2 hops","SNR -8.5",ERR)]
    for i,(name,hop,snr,col) in enumerate(tnodes):
        y = 290 + i*24
        c += f'<rect x="558" y="{y-10}" width="{int(200*(1-i*0.18))}" height="16" rx="3" fill="{col}" opacity=".15"/>'
        c += txt(562, y+2, name, TEXT, 10)
        c += txt(700, y+2, hop, MUTE, 9)
        c += txt(780, y+2, snr, col, 10, "bold")

    # Connection status bar
    c += panel(10, 432, 940, 32, fill="#041018", stroke=PRIM)
    c += f'<circle cx="28" cy="448" r="5" fill="{PRIM}"/>'
    c += txt(40, 452, "CONNECTED  ·  TCP 192.168.x.x  ·  Node: MeshBot  ·  Ch 0  ·  Region: EU_868", PRIM, 10)
    c += txt(W-10, 452, "Last RX: 12s ago", MUTE, 9, anchor="end")

    return svg_wrap(c, "OPS Dashboard")

# ── SCREEN 2: CHAT ──────────────────────────────────────────────────────────
def make_chat():
    TABS = ["OPS","CHAT","NODES","MAP","PACKETS","RADAR","CONFIG"]
    c = hdr(TABS, "CHAT")
    c += f'<rect x="0" y="34" width="{W}" height="{H-34}" fill="url(#bg)"/>'

    # Sidebar
    c += panel(10, 44, 190, H-54, fill=SURF, stroke=BORD, rx=10)
    c += txt(20, 64, "CHANNELS", PRIM, 9, "bold", opacity=.8)
    channels = [("# Channel 0", True), ("# Channel 3", False), ("# Channel 7", False)]
    for i,(name,act) in enumerate(channels):
        y = 80 + i*24
        col = PRIM if act else TEXT
        bg  = "#0a2e1a" if act else "none"
        c += f'<rect x="14" y="{y-12}" width="182" height="20" rx="3" fill="{bg}"/>'
        c += f'<rect x="11" y="{y-12}" width="3" height="20" fill="{PRIM if act else "none"}"/>'
        c += txt(20, y+2, name, col, 11)

    c += txt(20, 164, "DIRECT MESSAGES", PRIM, 9, "bold", opacity=.8)
    dms = [
        ("🟢 Alpha Node","[AlpN] · Direct · 2m", False, 3),
        ("🟢 Base Station","[BaSt] · Direct · 5m", False, 0),
        ("📡 Mobile-1","[Mob1] · 1 hop · 18m", False, 1),
        ("☁  Gateway","[Gate] · MQTT · 1h", False, 0),
        ("📡 Remote-7","[Rem7] · 2 hops · 3h", False, 0),
    ]
    for i,(name,sub,act,badge_n) in enumerate(dms):
        y = 180 + i*38
        c += f'<rect x="14" y="{y-2}" width="182" height="34" rx="3" fill="{"#0a2e1a" if act else "none"}"/>'
        c += txt(20, y+12, name, PRIM if act else TEXT, 11)
        c += txt(20, y+26, sub, MUTE, 9)
        if badge_n:
            c += f'<rect x="174" y="{y+2}" width="18" height="16" rx="8" fill="{ERR}"/>'
            c += txt(183, y+13, str(badge_n), "#fff", 9, anchor="middle")

    # Main chat area
    c += panel(208, 44, W-218, H-54, fill=SURF3, stroke=BORD, rx=10)
    # toolbar
    c += f'<rect x="208" y="44" width="{W-218}" height="34" rx="10" fill="{SURF}" opacity=".7"/>'
    c += txt(222, 66, "# Channel 0  ·  General", PRIM, 12, "bold")
    c += txt(W-60, 66, "System", MUTE, 10)

    msgs = [
        (None,     "system", "[10:15:02]","","Connected to mesh. Node: MeshBot (!ffaf8db4)",   MUTE,   False),
        ("AlpN",   "rx",     "[10:20:14]","Alpha Node","Hello everyone! Testing range today.",     BLUE,   True),
        ("MeshBot","ai",     "[10:20:18]","MeshBot","Hi Alpha! SNR is +3.1 dB here, great signal. What's your location?", AI, False),
        ("AlpN",   "rx",     "[10:21:05]","Alpha Node","About 2 km north of base. Battery 85%.",  BLUE,   True),
        ("MeshBot","ai",     "[10:21:10]","MeshBot","Excellent! I can see 6 nodes on the mesh right now.", AI, False),
        ("Mob1",   "rx",     "[10:23:48]","Mobile-1","Can someone relay to Remote-7?",            BLUE,   True),
        ("MeshBot","ai",     "[10:23:52]","MeshBot","On it! Traceroute to Remote-7: 2 hops via Relay-3 ✓", AI, False),
        ("BaSt",   "rx",     "[10:24:01]","Base Station","Position update sent.",                 BLUE,   False),
    ]
    for i,row in enumerate(msgs):
        _, mtype, ts, sender, text, col, clickable = row
        y = 98 + i*56
        bdr = BLUE if mtype=="rx" else (AI if mtype=="ai" else BORD)
        c += f'<rect x="210" y="{y-4}" width="{W-222}" height="48" rx="0" fill="{"#0d1520" if i%2==0 else "none"}"/>'
        c += f'<rect x="210" y="{y-4}" width="3" height="48" fill="{bdr}"/>'
        c += txt(218, y+10, ts, MUTE, 9)
        if sender:
            und = "underline" if clickable else "none"
            cur = ' style="cursor:pointer"' if clickable else ""
            c += f'<text x="278" y="{y+10}" fill="{col}" font-size="11" font-weight="bold" text-decoration="{und}">{sender}:</text>'
        c += txt(218, y+30, text[:72], TEXT, 10)
        # ACK
        if mtype in ("rx","ai"):
            c += txt(W-20, y+10, "✓", PRIM, 10, anchor="end")

    # Send bar
    c += f'<rect x="208" y="{H-54}" width="{W-218}" height="44" rx="8" fill="{SURF}" opacity=".8"/>'
    c += f'<rect x="218" y="{H-44}" width="{W-268}" height="28" rx="6" fill="{SURF3}" stroke="{BORD}" stroke-width="1"/>'
    c += txt(228, H-26, "Type a message...", MUTE, 11)
    c += f'<rect x="{W-56}" y="{H-44}" width="44" height="28" rx="6" fill="{PRIM}" opacity=".85"/>'
    c += txt(W-34, H-26, "Send", BG, 11, "bold", anchor="middle")

    return svg_wrap(c, "Chat")

# ── SCREEN 3: NODES ─────────────────────────────────────────────────────────
def make_nodes():
    TABS = ["OPS","CHAT","NODES","MAP","PACKETS","RADAR","CONFIG"]
    c = hdr(TABS, "NODES")
    c += f'<rect x="0" y="34" width="{W}" height="{H-34}" fill="url(#bg)"/>'

    # Toolbar
    c += panel(10, 44, W-20, 36, fill=SURF2, rx=6)
    filters = ["All","Direct","MQTT","GPS"]
    hops    = ["Any hops","Direct","1 hop","2+ hops"]
    c += txt(20, 67, "Show:", MUTE, 10)
    for i,f in enumerate(filters):
        col = PRIM if i==0 else TEXT; bg = "#0a2e1a" if i==0 else "none"
        c += f'<rect x="{70+i*68}" y="50" width="64" height="22" rx="4" fill="{bg}" stroke="{PRIM if i==0 else BORD}" stroke-width="1"/>'
        c += txt(70+i*68+32, 65, f, col, 10, anchor="middle")
    c += txt(360, 67, "Sort:", MUTE, 10)
    sorts = ["Last seen","Name","SNR"]
    for i,s in enumerate(sorts):
        c += f'<rect x="{400+i*80}" y="50" width="74" height="22" rx="4" fill="none" stroke="{BORD}" stroke-width="1"/>'
        c += txt(400+i*80+37, 65, s, MUTE, 10, anchor="middle")

    # Node cards grid 3-col
    node_data = [
        ("Base Station","BaSt", True, False, 0, "+8.5","-82","72%","GPS","ffff00",True),
        ("Alpha Node",  "AlpN", True, False, 0, "+3.1","-95","85%","GPS","00ff88",False),
        ("Mobile Unit 1","Mob1",True, False, 1, "+1.2","-101","61%","GPS","00ff88",False),
        ("Gateway-EU",  "Gate", False,True,  0, "—",   "—",  "95%","—",  "f0883e",False),
        ("Remote-7",    "Rem7", False,False, 2, "-8.5","-118","33%","—",  "88aaff",False),
        ("Relay Node 3","Rel3", True, False, 1, "-2.0","-107","—",  "—",  "00ff88",False),
    ]
    cols_x = [10, 328, 646]
    for i,(long,short,online,mqtt,hops,snr,rssi,bat,gps,col,mine) in enumerate(node_data):
        cx = cols_x[i % 3]
        cy = 90 + (i // 3) * 208
        dot = PRIM if online else (AI if mqtt else MUTE)
        bdr = col
        c += f'<rect x="{cx}" y="{cy}" width="308" height="194" rx="12" fill="{SURF}" stroke="#{bdr}" stroke-width="1" opacity=".9"/>'
        c += f'<rect x="{cx}" y="{cy}" width="308" height="194" rx="12" fill="#{col}" opacity=".04"/>'
        # header
        c += f'<circle cx="{cx+20}" cy="{cy+22}" r="6" fill="{dot}"/>'
        c += txt(cx+32, cy+27, long, TEXT, 13, "bold")
        if mine:
            c += f'<rect x="{cx+260}" y="{cy+12}" width="34" height="18" rx="9" fill="{PRIM}" opacity=".2"/>'
            c += txt(cx+277, cy+24, "ME", PRIM, 9, "bold", anchor="middle")
        c += txt(cx+12, cy+44, f"[{short}]  !a1b2c3d{i+1}", MUTE, 9)
        # hop badge
        hop_txt = "Direct" if hops==0 else (f"{hops} hop" if hops==1 else f"{hops} hops")
        hop_col = PRIM if hops==0 else (YEL if hops==1 else ERR)
        if mqtt: hop_txt, hop_col = "MQTT", AI
        c += f'<rect x="{cx+12}" y="{cy+52}" width="{len(hop_txt)*7+12}" height="16" rx="8" fill="{hop_col}" opacity=".2"/>'
        c += txt(cx+18, cy+63, hop_txt, hop_col, 9, "bold")
        # metrics
        rows = [("SNR",snr+" dB"),("RSSI",rssi+" dBm"),("Battery",bat),("GPS",gps)]
        for j,(lbl,val) in enumerate(rows):
            mx = cx+12 + (j%2)*148; my = cy+90 + (j//2)*38
            c += txt(mx, my, lbl, MUTE, 9)
            c += txt(mx, my+18, val, TEXT, 13, "bold")
        # buttons
        c += f'<rect x="{cx+12}" y="{cy+166}" width="88" height="22" rx="5" fill="{PRIM}" opacity=".15" stroke="{PRIM}" stroke-width="1"/>'
        c += txt(cx+56, cy+181, "Details", PRIM, 10, anchor="middle")
        c += f'<rect x="{cx+110}" y="{cy+166}" width="100" height="22" rx="5" fill="none" stroke="{BORD}" stroke-width="1"/>'
        c += txt(cx+160, cy+181, "⚡ Traceroute", MUTE, 10, anchor="middle")

    return svg_wrap(c, "Nodes")

# ── SCREEN 4: CONFIG ─────────────────────────────────────────────────────────
def make_config():
    TABS = ["OPS","CHAT","NODES","MAP","PACKETS","RADAR","CONFIG"]
    c = hdr(TABS, "CONFIG")
    c += f'<rect x="0" y="34" width="{W}" height="{H-34}" fill="url(#bg)"/>'

    # Sidebar
    c += panel(10, 44, 160, H-54, fill=SURF, rx=10)
    sections = ["Device","LoRa","Position","Power","Network","Display","Bluetooth","Channels","MQTT","Telemetry"]
    for i,s in enumerate(sections):
        act = i==1
        col = PRIM if act else TEXT; bg = "#0a2e1a" if act else "none"
        c += f'<rect x="14" y="{64+i*46-10}" width="152" height="38" rx="4" fill="{bg}"/>'
        if act: c += f'<rect x="11" y="{64+i*46-10}" width="3" height="38" fill="{PRIM}"/>'
        c += txt(24, 64+i*46+8, s, col, 11)

    # Main config area — LoRa settings
    c += panel(178, 44, W-188, H-54, fill=SURF3, rx=10)
    c += txt(192, 68, "LoRa Radio Settings", TEXT, 14, "bold")
    c += txt(192, 84, "Configure the LoRa radio parameters for your region and use case.", MUTE, 10)

    fields = [
        ("Region",          "EU_868",              "Frequency band for your country"),
        ("Preset / Modem",  "LONG_FAST",            "Modulation preset — range vs speed tradeoff"),
        ("Bandwidth",       "250 kHz",              "Channel bandwidth"),
        ("Spreading Factor","SF 11",                "Higher = longer range, lower data rate"),
        ("Hop Limit",       "3",                    "Max hops a packet will traverse"),
        ("TX Power",        "27 dBm (max)",         "Transmit power"),
        ("Frequency Offset","0 Hz",                 "Fine-tune carrier frequency"),
    ]
    for i,(lbl,val,hint) in enumerate(fields):
        row_y = 104 + i*58
        c += f'<rect x="190" y="{row_y}" width="{W-208}" height="50" rx="6" fill="{SURF2}" opacity=".7"/>'
        c += txt(204, row_y+16, lbl, TEXT, 11, "bold")
        c += txt(204, row_y+30, hint, MUTE, 9)
        # value box
        c += f'<rect x="{W-230}" y="{row_y+8}" width="200" height="28" rx="5" fill="{SURF3}" stroke="{BORD}"/>'
        c += txt(W-224, row_y+27, val, PRIM, 12)

    # Save button
    c += f'<rect x="{W-140}" y="{H-58}" width="120" height="34" rx="8" fill="{PRIM}" opacity=".9"/>'
    c += txt(W-80, H-36, "Save Config", BG, 12, "bold", anchor="middle")
    c += f'<rect x="{W-270}" y="{H-58}" width="120" height="34" rx="8" fill="none" stroke="{BORD}"/>'
    c += txt(W-210, H-36, "Reboot Device", MUTE, 12, anchor="middle")

    return svg_wrap(c, "Config")

# ── SCREEN 5: PACKETS ───────────────────────────────────────────────────────
def make_packets():
    TABS = ["OPS","CHAT","NODES","MAP","PACKETS","RADAR","CONFIG"]
    c = hdr(TABS, "PACKETS")
    c += f'<rect x="0" y="34" width="{W}" height="{H-34}" fill="url(#bg)"/>'

    # Stats left
    c += panel(10, 44, 220, H-54, fill=SURF, rx=10)
    c += txt(22, 65, "STATISTICS", PRIM, 9, "bold", opacity=.8)

    stat_blocks = [
        ("Total Packets","1 847", BLUE),
        ("Rate","12 / min", PRIM),
    ]
    for i,(lbl,val,col) in enumerate(stat_blocks):
        sy = 82 + i*60
        c += txt(22, sy, lbl, MUTE, 9)
        c += txt(22, sy+26, val, col, 22, "bold")

    c += txt(22, 212, "By Channel", MUTE, 9)
    for i,(ch,n) in enumerate([("ch0","1 203"),("ch3","421"),("ch7","223")]):
        c += txt(22, 230+i*20, f"{ch}:", MUTE, 9)
        c += f'<rect x="54" y="{220+i*20}" width="{int(120*(1-i*0.3))}" height="12" rx="2" fill="{BLUE}" opacity="{0.7-i*0.15}"/>'
        c += txt(180, 230+i*20, n, TEXT, 9, anchor="end")

    c += txt(22, 305, "By Type", MUTE, 9)
    for i,(typ,n,col) in enumerate([("TEXT","384",BLUE),("POSITION","512",PRIM),("TELEMETRY","621",AI),("NODEINFO","330",YEL)]):
        c += txt(22, 322+i*20, typ, col, 9)
        c += txt(215, 322+i*20, n, TEXT, 9, anchor="end")

    c += txt(22, 410, "Top Nodes", MUTE, 9)
    for i,(node,n) in enumerate([("Base Station","483"),("Alpha Node","312"),("Gateway","287"),("Mobile-1","198")]):
        c += txt(22, 426+i*18, f"• {node}", TEXT, 9)
        c += txt(215, 426+i*18, n, MUTE, 9, anchor="end")

    # Feed right
    c += panel(238, 44, W-248, H-54, fill=SURF3, rx=10)
    # toolbar
    c += f'<rect x="238" y="44" width="{W-248}" height="32" rx="8" fill="{SURF2}" opacity=".8"/>'
    tbtns = ["All","Text","Position","Telemetry","Node Info","Routing","Routes"]
    bx = 248
    for i,b in enumerate(tbtns):
        act = i==0
        col = PRIM if act else MUTE; bg = "#0a2e1a" if act else "none"
        w = len(b)*7+14
        c += f'<rect x="{bx}" y="50" width="{w}" height="20" rx="4" fill="{bg}"/>'
        c += txt(bx+w//2, 64, b, col, 9, anchor="middle")
        bx += w + 6

    # Header row
    c += f'<rect x="238" y="78" width="{W-248}" height="18" fill="{SURF2}" opacity=".5"/>'
    for hx,hl in [(248,"Time"),(308,"Type"),(400,"Route"),(560,"Ch"),(620,"SNR/RSSI"),(720,"Summary")]:
        c += txt(hx, 91, hl, MUTE, 9, "bold")

    # Packet rows
    pkts = [
        ("[10:24:03]","TEXT","AlphaN→BrCast","0","+3.1 / -95","Hello everyone! Testing range.",BLUE),
        ("[10:24:00]","POSITION","BaseSt→BrCast","0","+8.5 / -82","lat=52.2297 lon=21.0122 alt=105m",PRIM),
        ("[10:23:58]","TELEMETRY","Remote7→BrCast","0","-8.5 / -118","bat=33% volt=3.72 temp=21.3°C",AI),
        ("[10:23:55]","NODEINFO","Mobile1→BrCast","0","+1.2 / -101","long=Mobile Unit 1 short=Mob1",YEL),
        ("[10:23:52]","ROUTING","MeshBot→AlpN","0","+3.1 / -95","ACK id=0xf1a2",MUTE),
        ("[10:23:48]","TEXT","Mobile1→MeshBot","0","+1.2 / -101","Can someone relay to Remote-7?",BLUE),
        ("[10:23:40]","POSITION","AlphaN→BrCast","0","+3.1 / -95","lat=52.2450 lon=21.0010",PRIM),
        ("[10:23:30]","TELEMETRY","Gateway→BrCast","3","— / —","bat=95% via MQTT",AI),
    ]
    for i,(ts,typ,route,ch,sig,summary,col) in enumerate(pkts):
        ry = 98 + i*54
        c += f'<rect x="240" y="{ry-4}" width="{W-252}" height="46" rx="0" fill="{"#0d1520" if i%2==0 else "none"}"/>'
        c += f'<rect x="240" y="{ry-4}" width="3" height="46" fill="{col}"/>'
        c += txt(248, ry+12, ts, MUTE, 9)
        c += txt(308, ry+12, typ, col, 9, "bold")
        c += txt(400, ry+12, route, TEXT, 9)
        c += txt(560, ry+12, ch, MUTE, 9)
        c += txt(620, ry+12, sig, TEXT, 9)
        c += txt(248, ry+30, summary[:60], MUTE, 9)

    return svg_wrap(c, "Packets")

os.makedirs("mdfiles", exist_ok=True)
files = {
    "mdfiles/screen_ops.svg":    make_ops(),
    "mdfiles/screen_chat.svg":   make_chat(),
    "mdfiles/screen_nodes.svg":  make_nodes(),
    "mdfiles/screen_config.svg": make_config(),
    "mdfiles/screen_packets.svg":make_packets(),
}
for path, content in files.items():
    with open(path, "w") as f:
        f.write(content)
    print(f"Written: {path}")
print("Done.")
