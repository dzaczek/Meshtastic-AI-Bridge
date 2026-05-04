"""Server-side stats image generation + imgbb upload for !stats command."""

import io
import math
import time
import base64
import hashlib
import logging
import threading
from typing import Optional

import requests

log = logging.getLogger(__name__)

# ── Dark theme (matches web UI) ────────────────────────────────
_BG    = '#0d1117'
_TEXT  = '#e6edf3'
_MUTED = '#8b949e'
_PRIM  = '#4dffd1'

ROLE_COLORS = {
    'ROUTER':  '#f0883e', 'ROUTER+': '#ffc84d', 'CLIENT':  '#4dffd1',
    'MUTE':    '#8888aa', 'TRACKER': '#88aaff', 'SENSOR':  '#cc88ff',
    'TAK':     '#ff5555', 'HIDDEN':  '#666677', 'L&F':     '#ff88cc',
}
_ROLE_ORDER = ['ROUTER', 'ROUTER+', 'CLIENT', 'MUTE', 'TRACKER', 'SENSOR', 'TAK', 'HIDDEN', 'L&F']
RADIAL_HOP_COLORS = ['#00ff88','#4dffd1','#88ccff','#88aaff','#cc88ff','#f0883e','#ff5555','#ff2222']
_ROLE_MAP = {
    'CLIENT': 'CLIENT', 'CLIENT_MUTE': 'MUTE', 'MUTE_CLIENT': 'MUTE',
    'ROUTER': 'ROUTER', 'ROUTER_CLIENT': 'ROUTER+', 'TRACKER': 'TRACKER',
    'SENSOR': 'SENSOR', 'TAK': 'TAK', 'TAK_TRACKER': 'TAK',
    'CLIENT_HIDDEN': 'HIDDEN', 'LOST_AND_FOUND': 'L&F',
}

def _role(r: str) -> str:
    return _ROLE_MAP.get((r or '').upper(), 'CLIENT')

def _hex_rgb(h: str) -> tuple:
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))

def _nhash(node_id: str, salt: str = '') -> float:
    """Deterministic value in [-0.5, 0.5) seeded from node id."""
    raw = int(hashlib.md5((salt + str(node_id)).encode()).hexdigest()[:8], 16)
    return (raw % 100000) / 100000 - 0.5

# ── Per-node cooldown ──────────────────────────────────────────
_cooldowns: dict = {}
_cd_lock = threading.Lock()
COOLDOWN_HOURS = 4

def check_cooldown(node_id: str) -> Optional[int]:
    """Return seconds remaining if still on cooldown, else None."""
    with _cd_lock:
        ts = _cooldowns.get(str(node_id), 0)
    rem = int(ts + COOLDOWN_HOURS * 3600 - time.time())
    return rem if rem > 0 else None

def set_cooldown(node_id: str):
    with _cd_lock:
        _cooldowns[str(node_id)] = time.time()

# ── Individual chart renderers ─────────────────────────────────
def _draw_radial(ax, nodes, avg_hops_map):
    """Roles × Hops polar scatter."""
    import matplotlib.pyplot as plt

    ax.set_facecolor(_hex_rgb(_BG))
    ax.axis('off')

    roles_seen = set(_role(n.get('role', '')) for n in nodes)
    roles = [r for r in _ROLE_ORDER if r in roles_seen]
    for r in roles_seen:
        if r not in roles:
            roles.append(r)

    if not roles:
        ax.text(0.5, 0.5, 'No radio nodes', ha='center', va='center',
                color=_hex_rgb(_MUTED), transform=ax.transAxes, fontsize=8)
        ax.set_title('Roles × Hops', color=_hex_rgb(_TEXT), fontsize=9, pad=5)
        return

    n_roles    = len(roles)
    aslice     = 2 * math.pi / n_roles
    max_r      = 8.0   # rings 0-7 + tiny margin

    ax.set_xlim(-max_r * 1.38, max_r * 1.38)
    ax.set_ylim(-max_r * 1.38, max_r * 1.38)
    ax.set_aspect('equal')

    # Hop rings
    for h in range(8):
        circle = plt.Circle((0, 0), h + 1, fill=False,
                             color='white', alpha=0.07, linewidth=0.5)
        ax.add_patch(circle)
        ax.text(0.1, h + 0.7, f'{h}h', color='white', alpha=0.22,
                fontsize=5, va='top', fontfamily='monospace')

    # Spokes
    for i in range(n_roles):
        a = i * aslice - math.pi / 2
        ax.plot([0, max_r * math.cos(a)], [0, max_r * math.sin(a)],
                color='white', alpha=0.08, linewidth=0.5)

    # Dots
    for n in nodes:
        rl = _role(n.get('role', ''))
        if rl not in roles:
            continue
        idx   = roles.index(rl)
        avg_h = avg_hops_map.get(n.get('id', ''), n.get('hops_away'))
        if avg_h is None:
            avg_h = 7.0
        avg_h = min(max(float(avg_h), 0), 7)

        jA = _nhash(n.get('id', ''), '')  * aslice * 0.70
        jR = _nhash(n.get('id', ''), 'r') * 0.18

        a  = idx * aslice - math.pi / 2 + jA
        rv = max(0.15, avg_h + jR)
        c  = _hex_rgb(ROLE_COLORS.get(rl, _PRIM))
        ax.scatter(rv * math.cos(a), rv * math.sin(a),
                   color=c, s=12, zorder=5, alpha=0.88, linewidths=0)

    # Role labels
    lr = max_r * 1.18
    for i, rl in enumerate(roles):
        a  = i * aslice - math.pi / 2
        x, y = lr * math.cos(a), lr * math.sin(a)
        ha = 'center' if abs(x) < 0.5 else ('left' if x > 0 else 'right')
        ax.text(x, y, rl, color=_hex_rgb(ROLE_COLORS.get(rl, _PRIM)),
                fontsize=6, ha=ha, va='center', fontfamily='monospace',
                fontweight='bold')

    # Compact role legend (bottom-left)
    for li, rl in enumerate(roles):
        c = _hex_rgb(ROLE_COLORS.get(rl, _PRIM))
        ax.scatter(-max_r * 1.3, -max_r * 1.15 + li * 1.5, color=c, s=9, zorder=6)
        ax.text(-max_r * 1.18, -max_r * 1.15 + li * 1.5, rl,
                color=c, fontsize=5, va='center', fontfamily='monospace')

    ax.set_title('Roles × Hops', color=_hex_rgb(_TEXT), fontsize=9, pad=5)


def _draw_force(ax, top_links, node_names):
    """All Unicast Packets force-directed graph."""
    import networkx as nx

    ax.set_facecolor(_hex_rgb(_BG))
    ax.axis('off')

    if not top_links:
        ax.text(0.5, 0.5, 'No unicast data', ha='center', va='center',
                color=_hex_rgb(_MUTED), transform=ax.transAxes, fontsize=8)
        ax.set_title('Unicast Packets', color=_hex_rgb(_TEXT), fontsize=9, pad=5)
        return

    # Merge bidirectional edges
    weight_map: dict = {}
    for lnk in top_links:
        key = tuple(sorted([lnk['from'], lnk['to']]))
        weight_map[key] = weight_map.get(key, 0) + lnk['count']

    G = nx.Graph()
    for (s, t), w in weight_map.items():
        G.add_edge(s, t, weight=w)

    if not G.nodes():
        ax.text(0.5, 0.5, 'No data', ha='center', va='center',
                color=_hex_rgb(_MUTED), transform=ax.transAxes, fontsize=8)
        ax.set_title('Unicast Packets', color=_hex_rgb(_TEXT), fontsize=9, pad=5)
        return

    k = 2.2 / max(1, math.sqrt(len(G.nodes())))
    pos = nx.spring_layout(G, seed=42, k=k, iterations=60)

    max_w = max(weight_map.values())

    # Edges
    for (s, t), w in weight_map.items():
        if s not in pos or t not in pos:
            continue
        x0, y0 = pos[s]; x1, y1 = pos[t]
        alpha = 0.15 + 0.60 * w / max_w
        lw    = 0.4 + 1.8 * w / max_w
        ax.plot([x0, x1], [y0, y1], color='#3fb950', alpha=alpha, linewidth=lw)

    # Nodes
    for nid, (x, y) in pos.items():
        ax.scatter(x, y, color=_hex_rgb(_PRIM), s=22, zorder=5, linewidths=0)
        label = node_names.get(nid, '!' + str(nid)[-4:])[:9]
        ax.text(x, y + 0.06, label, color=_hex_rgb(_TEXT),
                fontsize=4.5, ha='center', va='bottom', alpha=0.82)

    ax.set_title('Unicast Packets (Force Graph)', color=_hex_rgb(_TEXT), fontsize=9, pad=5)


def _draw_activity(ax, buckets, bucket_label):
    """Activity bar chart."""
    ax.set_facecolor(_hex_rgb(_BG))
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.spines['bottom'].set_visible(True)
    ax.spines['bottom'].set_color((1, 1, 1, 0.12))
    ax.spines['left'].set_visible(True)
    ax.spines['left'].set_color((1, 1, 1, 0.12))
    ax.tick_params(colors=_hex_rgb(_MUTED), labelsize=6)
    ax.yaxis.label.set_color(_hex_rgb(_MUTED))
    ax.grid(axis='y', color='white', alpha=0.05, linewidth=0.5)

    if not buckets:
        ax.text(0.5, 0.5, 'No activity data', ha='center', va='center',
                color=_hex_rgb(_MUTED), transform=ax.transAxes, fontsize=8)
        ax.set_title(f'Activity ({bucket_label})', color=_hex_rgb(_TEXT), fontsize=9, pad=5)
        return

    labels = [b['label'] for b in buckets]
    counts = [b['count'] for b in buckets]
    x = range(len(labels))

    ax.bar(x, counts, color=_hex_rgb(_PRIM), alpha=0.72, width=0.75)

    step = max(1, len(labels) // 14)
    ax.set_xticks([i for i in x if i % step == 0])
    ax.set_xticklabels([labels[i] for i in x if i % step == 0],
                       rotation=40, ha='right', fontsize=6,
                       color=_hex_rgb(_MUTED))
    ax.set_ylabel('packets', color=_hex_rgb(_MUTED), fontsize=7)
    ax.set_title(f'Activity — packet count per {bucket_label} bucket',
                 color=_hex_rgb(_TEXT), fontsize=9, pad=5)


def _draw_hop_reachability(ax, hop_data):
    """Node reachability time-series: one line per hop distance 0-7."""
    import numpy as np

    ax.set_facecolor(_hex_rgb(_BG))
    for sp in ax.spines.values():
        sp.set_visible(False)
    for sp in ['bottom', 'left']:
        ax.spines[sp].set_visible(True)
        ax.spines[sp].set_color((1, 1, 1, 0.12))
    ax.tick_params(colors=_hex_rgb(_MUTED), labelsize=6)
    ax.grid(axis='y', color='white', alpha=0.05, linewidth=0.5)

    buckets = hop_data.get('buckets', [])
    series  = hop_data.get('series', [])
    blabel  = hop_data.get('bucket_label', '')

    if not buckets or not series:
        ax.text(0.5, 0.5, 'No hop reachability data',
                ha='center', va='center',
                color=_hex_rgb(_MUTED), transform=ax.transAxes, fontsize=8)
        ax.set_title('Node Reachability by Hop Count',
                     color=_hex_rgb(_TEXT), fontsize=9, pad=5)
        return

    x = np.arange(len(buckets))
    for s in series:
        col = RADIAL_HOP_COLORS[s['hop']] if s['hop'] < 8 else '#888'
        y   = s['counts']
        ax.plot(x, y, color=col, linewidth=1.6, alpha=0.9,
                label=f"{s['hop']} hop{'s' if s['hop']!=1 else ''}")
        # Dots on non-zero points
        non_zero = [(i, v) for i, v in enumerate(y) if v > 0]
        if non_zero:
            xi, yi = zip(*non_zero)
            ax.scatter(list(xi), list(yi), color=col, s=10, zorder=5, linewidths=0)

    # X ticks
    step = max(1, len(buckets) // 12)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(buckets[::step], rotation=35, ha='right',
                       fontsize=6, color=_hex_rgb(_MUTED))
    ax.set_ylabel('distinct nodes', color=_hex_rgb(_MUTED), fontsize=7)
    ax.yaxis.label.set_color(_hex_rgb(_MUTED))

    # Legend (outside right)
    legend = ax.legend(
        loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0,
        frameon=False, fontsize=7, labelcolor='white',
        title='Hop dist.', title_fontsize=7,
    )
    legend.get_title().set_color(_hex_rgb(_MUTED))

    time_desc = f'Time ({blabel} buckets)' if blabel else 'Time'
    ax.set_xlabel(time_desc, color=_hex_rgb(_MUTED), fontsize=7)
    ax.set_title(
        'Node Reachability by Hop Count — distinct radio nodes visible per hop distance over time',
        color=_hex_rgb(_TEXT), fontsize=9, pad=5,
    )


# ── Public API ─────────────────────────────────────────────────
def generate_stats_image(db_module, hours: float = 4.0,
                         own_node_id: Optional[str] = None) -> bytes:
    """
    Generate composite stats PNG with 4 charts stacked vertically:
      Row 1 (side by side): Roles×Hops Radial | Unicast Packets Force Graph
      Row 2 (full width):   Packet Activity bar chart
      Row 3 (full width):   Node Reachability by Hop Count line chart
    Returns raw PNG bytes.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec

    # ── Gather data ──
    analytics   = db_module.get_packet_analytics(hours=hours)
    avg_hops    = db_module.get_avg_hops_per_node(hours=hours)
    hop_reach   = db_module.get_hop_reachability(hours=hours)
    all_nodes   = db_module.get_all_nodes()

    node_names: dict = {}
    for n in all_nodes:
        nid = n.get('id', '')
        node_names[nid] = (n.get('long_name') or n.get('short_name')
                           or ('!' + str(nid)[-4:]))

    cutoff = time.time() - hours * 3600
    nodes_radio = [
        n for n in all_nodes
        if not n.get('via_mqtt')
        and n.get('last_seen', 0) >= cutoff
        and n.get('id') != own_node_id
    ]

    buckets    = analytics.get('hourly', [])
    bucket_lbl = analytics.get('bucket_label', '15m')
    top_links  = analytics.get('top_links', [])

    # ── Layout ──
    # Row 0: [Radial (square) | Force graph (square)]  height_ratio 1.6
    # Row 1: [Activity bar — full width]               height_ratio 1.0
    # Row 2: [Hop reachability lines — full width]     height_ratio 1.0
    fig = plt.figure(figsize=(14, 11), facecolor=_hex_rgb(_BG))
    gs  = gridspec.GridSpec(
        3, 2, figure=fig,
        hspace=0.48, wspace=0.28,
        height_ratios=[1.6, 1.0, 1.0],
        left=0.05, right=0.93,
        top=0.93, bottom=0.06,
    )
    ax_r  = fig.add_subplot(gs[0, 0])          # Roles×Hops radial
    ax_f  = fig.add_subplot(gs[0, 1])          # Force graph
    ax_a  = fig.add_subplot(gs[1, :])          # Activity (full width)
    ax_hr = fig.add_subplot(gs[2, :])          # Hop reachability (full width)

    for ax in (ax_r, ax_f, ax_a, ax_hr):
        ax.set_facecolor(_hex_rgb(_BG))

    _draw_radial(ax_r, nodes_radio, avg_hops)
    _draw_force(ax_f, top_links, node_names)
    _draw_activity(ax_a, buckets, bucket_lbl)
    _draw_hop_reachability(ax_hr, hop_reach)

    ts_str = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())
    fig.suptitle(
        f'Meshtastic Network Stats  ·  last {int(hours)}h  ·  {ts_str}',
        color=_hex_rgb(_TEXT), fontsize=10, y=0.97,
    )

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=130, bbox_inches='tight',
                facecolor=_hex_rgb(_BG), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def upload_imgbb(image_bytes: bytes, api_key: str) -> Optional[str]:
    """Upload PNG bytes to imgbb. Returns public image URL or None."""
    b64  = base64.b64encode(image_bytes).decode()
    name = f'mesh_stats_{int(time.time())}'
    try:
        resp = requests.post(
            'https://api.imgbb.com/1/upload',
            data={'key': api_key, 'image': b64, 'name': name},
            timeout=45,
        )
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            return data.get('url') or data.get('display_url')
        log.warning('imgbb upload failed HTTP %s: %s', resp.status_code, resp.text[:300])
    except Exception as exc:
        log.error('imgbb upload error: %s', exc)
    return None
