"""Weather map generation — temperature overlay on OSM basemap + imgbb upload."""

import io
import time
import math
import logging
from typing import Optional, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from mesh_map import (
    _lat_lon_to_tile, _get_tile, TILE_SIZE,
)

log = logging.getLogger(__name__)

# ── Dark theme ────────────────────────────────────────────────────
_BG        = (13, 17, 23)
_SURFACE   = (22, 27, 34)
_BORDER    = (48, 54, 61)
_TEXT      = (230, 237, 243)
_TEXT_DIM  = (139, 148, 158)
_PRIM      = (77, 255, 209)
_WHITE     = (255, 255, 255)
_BLACK     = (0, 0, 0)
_CHART_BG  = (18, 22, 28)
_GRID      = (36, 41, 48)

# ── Temperature colour ramp ──────────────────────────────────────
def _temp_color(temp_c: float) -> Tuple[int, int, int]:
    """Blue (-20) → Cyan → Green → Yellow → Orange → Red (45+)."""
    if temp_c is None:
        return _TEXT_DIM
    t = max(-20, min(45, temp_c))
    f = (t + 20) / 65.0
    if f < 0.2:
        s = f / 0.2
        return (int(0 + 100 * s), int(100 + 155 * s), int(200 + 55 * s))
    elif f < 0.4:
        s = (f - 0.2) / 0.2
        return (int(100 + 100 * s), int(255 - 100 * s), int(255 - 155 * s))
    elif f < 0.6:
        s = (f - 0.4) / 0.2
        return (int(200 + 55 * s), int(155 + 100 * s), int(100 - 100 * s))
    elif f < 0.8:
        s = (f - 0.6) / 0.2
        return (255, int(255 - 115 * s), 0)
    else:
        s = (f - 0.8) / 0.2
        return (int(255 - 15 * s), int(140 - 100 * s), 0)


def _temp_brightness(color: Tuple[int, int, int]) -> int:
    r, g, b = color
    return int(0.299 * r + 0.587 * g + 0.114 * b)


# ── Data helpers ──────────────────────────────────────────────────
def _get_4h_temp_data(db_module) -> Dict[str, dict]:
    """Return {node_id: {last_temp, avg_temp, samples}} for last 4h."""
    if not db_module._conn:
        return {}
    cutoff = time.time() - 4 * 3600
    result: Dict[str, dict] = {}
    with db_module._lock:
        rows = db_module._conn.execute("""
            SELECT node_id, temperature, ts FROM telemetry_history
            WHERE temperature IS NOT NULL AND ts >= ?
            ORDER BY ts DESC
        """, (cutoff,)).fetchall()
    if not rows:
        return {}
    temps_by_node: Dict[str, list] = {}
    for r in rows:
        nid = r["node_id"]
        temps_by_node.setdefault(nid, []).append(r["temperature"])
    for nid, temps in temps_by_node.items():
        vals = [t for t in temps if t is not None]
        if not vals:
            continue
        result[nid] = {
            "last_temp": round(vals[0], 1),
            "avg_temp": round(sum(vals) / len(vals), 1),
            "samples": len(vals),
        }
    return result


def _get_24h_series(db_module, node_ids: List[str]) -> Dict[str, List[dict]]:
    """Return {node_id: [{ts, temp, humidity}, ...]} for last 24h."""
    if not db_module._conn or not node_ids:
        return {}
    cutoff = time.time() - 24 * 3600
    placeholders = ",".join("?" for _ in node_ids)
    series: Dict[str, List[dict]] = {nid: [] for nid in node_ids}
    with db_module._lock:
        rows = db_module._conn.execute(
            f"""SELECT node_id, ts, temperature, humidity
                FROM telemetry_history
                WHERE node_id IN ({placeholders})
                  AND ts >= ?
                  AND temperature IS NOT NULL
                ORDER BY node_id, ts ASC""",
            (*node_ids, cutoff),
        ).fetchall()
    for r in rows:
        series[r["node_id"]].append({
            "ts": r["ts"], "temp": r["temperature"], "hum": r["humidity"],
        })
    return series


def _get_node_positions(db_module, meshtastic_handler) -> Dict[str, dict]:
    """Collect node positions. Returns {nid: {lat, lon, name}}."""
    positions: Dict[str, dict] = {}

    # 1) position_history — latest per node
    try:
        if db_module._conn:
            with db_module._lock:
                rows = db_module._conn.execute("""
                    SELECT p.node_id, p.lat, p.lon
                    FROM position_history p
                    WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL
                      AND NOT (p.lat = 0 AND p.lon = 0)
                      AND p.ts = (SELECT MAX(ts) FROM position_history
                                  WHERE node_id = p.node_id)
                """).fetchall()
            for r in rows:
                positions[r["node_id"]] = {
                    "lat": r["lat"], "lon": r["lon"],
                    "name": "!" + r["node_id"][:4],
                }
    except Exception:
        pass

    # 2) node_db — fills in names
    try:
        nodes = db_module.get_all_nodes()
        for n in nodes:
            nid = n.get("id", "")
            if not nid:
                continue
            name = n.get("short_name") or n.get("long_name") or ("!" + nid[:4])
            nlat = n.get("lat"); nlon = n.get("lon")
            if nlat is not None and nlon is not None and not (nlat == 0 and nlon == 0):
                if nid not in positions:
                    positions[nid] = {"lat": nlat, "lon": nlon, "name": name}
                else:
                    positions[nid]["name"] = name
            elif nid in positions:
                positions[nid]["name"] = name
    except Exception:
        pass

    # 3) Live interface — highest priority
    if meshtastic_handler and meshtastic_handler.interface:
        for node_num, info in meshtastic_handler.interface.nodes.items():
            pos = info.get("position") or {}
            lat = pos.get("latitude") or (
                pos.get("latitudeI", 0) / 1e7 if pos.get("latitudeI") else None)
            lon = pos.get("longitude") or (
                pos.get("longitudeI", 0) / 1e7 if pos.get("longitudeI") else None)
            if not lat or not lon or (lat == 0 and lon == 0):
                continue
            nid = f"{node_num:x}" if isinstance(node_num, int) else str(node_num)
            name = (info.get("user", {}).get("shortName")
                    or info.get("user", {}).get("longName")
                    or ("!" + nid[:4]))
            positions[nid] = {"lat": lat, "lon": lon, "name": name}
    return positions


# ── Fonts ─────────────────────────────────────────────────────────
def _load_fonts() -> Tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont,
                           ImageFont.FreeTypeFont, ImageFont.FreeTypeFont,
                           ImageFont.FreeTypeFont]:
    """Return (title, heading, body, mono, tiny) fonts."""
    fd = "/usr/share/fonts/truetype/dejavu/"
    try:
        return (
            ImageFont.truetype(fd + "DejaVuSans-Bold.ttf", 22),
            ImageFont.truetype(fd + "DejaVuSans-Bold.ttf", 15),
            ImageFont.truetype(fd + "DejaVuSans.ttf", 13),
            ImageFont.truetype(fd + "DejaVuSansMono.ttf", 12),
            ImageFont.truetype(fd + "DejaVuSans.ttf", 10),
        )
    except Exception:
        d = ImageFont.load_default()
        return d, d, d, d, d  # type: ignore[return-value]


# ── Sparkline renderer ────────────────────────────────────────────
def _draw_sparkline(
    draw: ImageDraw.Draw, x: int, y: int, w: int, h: int,
    series: List[dict], y_min: float, y_max: float,
    color: Tuple[int, int, int], fill_alpha: int = 40,
):
    """Draw a temperature sparkline (line + area fill) inside (x,y,w,h)."""
    if len(series) < 1:
        return

    now = time.time()
    t_min = now - 24 * 3600
    t_range = max(1, now - t_min)
    v_range = max(0.5, y_max - y_min)

    pts = []
    for s in series:
        fx = (s["ts"] - t_min) / t_range
        fy = (s["temp"] - y_min) / v_range
        px = x + int(fx * (w - 1))
        py = y + h - 1 - int(fy * (h - 1))
        pts.append((px, py))

    if len(pts) == 1:
        # Single point — draw a dot
        px, py = pts[0]
        draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=color)
        return

    # Area fill below the line
    fill_color = (*color, fill_alpha)
    poly_pts = [(x, y + h - 1)] + pts + [(pts[-1][0], y + h - 1)]
    try:
        # PIL doesn't support alpha in draw.polygon with ImageDraw on RGB,
        # so we use a semi-transparent solid colour.
        draw.polygon(poly_pts, fill=(color[0] // 3, color[1] // 3, color[2] // 3))
    except Exception:
        pass

    # Line segments
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=color, width=2)

    # Dots at each data point
    for px, py in pts:
        draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=color)


# ── OSM tile stitching ────────────────────────────────────────────
def _stitch_osm_map(
    min_lat: float, max_lat: float,
    min_lon: float, max_lon: float,
) -> Optional[Image.Image]:
    """Stitch OSM tiles and return cropped/resized PIL Image."""
    lat_span = max_lat - min_lat
    lon_span = max_lon - min_lon
    span = max(lat_span, lon_span)
    if span > 1.0:       zoom = 10
    elif span > 0.3:     zoom = 11
    elif span > 0.1:     zoom = 12
    elif span > 0.05:    zoom = 13
    elif span > 0.02:    zoom = 14
    else:                zoom = 15

    tx1, ty1 = _lat_lon_to_tile(max_lat, min_lon, zoom)
    tx2, ty2 = _lat_lon_to_tile(min_lat, max_lon, zoom)
    if tx1 > tx2: tx1, tx2 = tx2, tx1
    if ty1 > ty2: ty1, ty2 = ty2, ty1

    if (tx2 - tx1 + 1) * (ty2 - ty1 + 1) > 36:
        zoom -= 1
        tx1, ty1 = _lat_lon_to_tile(max_lat, min_lon, zoom)
        tx2, ty2 = _lat_lon_to_tile(min_lat, max_lon, zoom)
        if tx1 > tx2: tx1, tx2 = tx2, tx1
        if ty1 > ty2: ty1, ty2 = ty2, ty1

    tiles_w = tx2 - tx1 + 1
    tiles_h = ty2 - ty1 + 1
    stitched = Image.new("RGB", (tiles_w * TILE_SIZE, tiles_h * TILE_SIZE), _BG)

    for tx in range(tx1, tx2 + 1):
        for ty in range(ty1, ty2 + 1):
            tile = _get_tile(zoom, tx, ty)
            if tile:
                stitched.paste(tile, ((tx - tx1) * TILE_SIZE, (ty - ty1) * TILE_SIZE))

    def _to_px(lat, lon):
        n = 2 ** zoom
        x_frac = (lon + 180.0) / 360.0 * n
        lat_rad = math.radians(lat)
        y_frac = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
        return (x_frac - tx1) * TILE_SIZE, (y_frac - ty1) * TILE_SIZE

    cx1, cy1 = _to_px(max_lat, min_lon)
    cx2, cy2 = _to_px(min_lat, max_lon)
    cx1, cx2 = sorted([cx1, cx2])
    cy1, cy2 = sorted([cy1, cy2])
    cx1, cy1 = max(0, int(cx1)), max(0, int(cy1))
    cx2, cy2 = min(stitched.width, int(cx2)), min(stitched.height, int(cy2))

    if cx2 <= cx1 or cy2 <= cy1:
        return None

    cropped = stitched.crop((cx1, cy1, cx2, cy2))
    cropped = cropped.resize((1120, 1050), Image.LANCZOS)
    return cropped


# ── Main map generation ───────────────────────────────────────────
def generate_weather_map(db_module, meshtastic_handler) -> Optional[bytes]:
    """
    Generate high-quality weather-temp map image with side panel.
    Layout: [ Title bar ]  [ Map | Data cards with sparklines ]  [ Legend bar ]
    Returns PNG bytes, or None if no nodes have both GPS + temperature.
    """
    temp_4h = _get_4h_temp_data(db_module)
    positions = _get_node_positions(db_module, meshtastic_handler)

    # Intersect: nodes with GPS + temp data
    plot_list: List[dict] = []
    for nid, pos in positions.items():
        if nid in temp_4h:
            plot_list.append({**pos, "id": nid, "temp": temp_4h[nid]})

    if not plot_list:
        return None

    # Sort by last temp (hottest first)
    plot_list.sort(key=lambda x: x["temp"]["last_temp"], reverse=True)

    # Fetch 24h series for sparklines
    all_ids = [n["id"] for n in plot_list]
    series_24h = _get_24h_series(db_module, all_ids)

    # ── Layout constants ────────────────────────────────────────
    IMG_W, IMG_H = 1800, 1150
    TOP_BAR_H  = 48
    LEGEND_H   = 44
    MAP_W      = 1120
    MAP_H      = IMG_H - TOP_BAR_H - LEGEND_H
    MAP_Y      = TOP_BAR_H
    PANEL_X    = MAP_W
    PANEL_W    = IMG_W - MAP_W
    PAD        = 14
    CARD_GAP   = 10

    font_title, font_head, font_body, font_mono, font_tiny = _load_fonts()

    # ── Bounding box ────────────────────────────────────────────
    lats = [n["lat"] for n in plot_list]
    lons = [n["lon"] for n in plot_list]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lat_pad = max((max_lat - min_lat) * 0.25, 0.015)
    lon_pad = max((max_lon - min_lon) * 0.25, 0.015)
    min_lat -= lat_pad; max_lat += lat_pad
    min_lon -= lon_pad; max_lon += lon_pad

    # ── Build OSM map ───────────────────────────────────────────
    map_img = _stitch_osm_map(min_lat, max_lat, min_lon, max_lon)
    if map_img is None:
        return None
    map_img = map_img.resize((MAP_W, MAP_H), Image.LANCZOS)
    draw_map = ImageDraw.Draw(map_img)
    lat_rng = max_lat - min_lat
    lon_rng = max_lon - min_lon

    def _geo_to_map(lat, lon):
        px = int((lon - min_lon) / lon_rng * (MAP_W - 1))
        py = int((max_lat - lat) / lat_rng * (MAP_H - 1))
        return max(5, min(MAP_W - 5, px)), max(5, min(MAP_H - 5, py))

    # Numbered markers on map
    for i, nd in enumerate(plot_list):
        px, py = _geo_to_map(nd["lat"], nd["lon"])
        color = _temp_color(nd["temp"]["last_temp"])
        r = 10
        draw_map.ellipse(
            [px - r, py - r, px + r, py + r],
            fill=color, outline=_WHITE, width=2)
        num_str = str(i + 1)
        tb = draw_map.textbbox((0, 0), num_str, font=font_head)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        nc = _BLACK if _temp_brightness(color) > 128 else _WHITE
        draw_map.text((px - tw // 2, py - th // 2 - 1), num_str, fill=nc, font=font_head)
        # Short ID label below
        id_label = nd["name"][:8]
        ib = draw_map.textbbox((0, 0), id_label, font=font_mono)
        iw = ib[2] - ib[0]
        draw_map.rectangle(
            [px - iw // 2 - 3, py + r + 2, px + iw // 2 + 3, py + r + 18],
            fill=(0, 0, 0, 170))
        draw_map.text((px - iw // 2, py + r + 3), id_label, fill=_TEXT, font=font_mono)

    # ── Compose final image ─────────────────────────────────────
    img = Image.new("RGB", (IMG_W, IMG_H), _BG)
    draw = ImageDraw.Draw(img)

    # --- Top bar ---
    draw.rectangle([0, 0, IMG_W, TOP_BAR_H], fill=_SURFACE)
    draw.line([0, TOP_BAR_H, IMG_W, TOP_BAR_H], fill=_BORDER, width=1)
    ts_str = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    title = f"Mesh Temperature Map   ·   {ts_str}   ·   {len(plot_list)} node(s)"
    draw.text((PAD, 11), title, fill=_PRIM, font=font_title)

    # --- Paste map ---
    img.paste(map_img, (0, MAP_Y))

    # --- Right panel background ---
    draw.rectangle([PANEL_X, MAP_Y, IMG_W, MAP_Y + MAP_H], fill=_SURFACE)
    draw.line([PANEL_X, MAP_Y, PANEL_X, MAP_Y + MAP_H], fill=_BORDER, width=1)

    # --- Data cards with sparklines ---
    panel_header = " Node Data  ·  24h temp trend"
    draw.text((PANEL_X + PAD, MAP_Y + PAD), panel_header, fill=_PRIM, font=font_head)

    # Dynamic card height to fill available space
    available_h = MAP_H - 38  # below header
    n_cards = len(plot_list)
    # Allocate space: 28px for text rows + chart area
    text_header_h = 28
    chart_h = max(36, (available_h - CARD_GAP * (n_cards - 1)) // n_cards - text_header_h)
    card_h = text_header_h + chart_h

    cy = MAP_Y + 36
    for i, nd in enumerate(plot_list):
        tinfo = nd["temp"]
        color = _temp_color(tinfo["last_temp"])
        series = series_24h.get(nd["id"], [])

        # Card background
        draw.rectangle(
            [PANEL_X + PAD, cy, IMG_W - PAD, cy + card_h],
            fill=(30, 35, 42), outline=_BORDER, width=1)

        # Color swatch (left edge of card)
        draw.rectangle(
            [PANEL_X + PAD + 4, cy + 4, PANEL_X + PAD + 20, cy + card_h - 4],
            fill=color)

        # Number inside swatch (top)
        num_str = str(i + 1)
        nb = draw.textbbox((0, 0), num_str, font=font_head)
        nw = nb[2] - nb[0]
        nc = _BLACK if _temp_brightness(color) > 128 else _WHITE
        draw.text(
            (PANEL_X + PAD + 12 - nw // 2, cy + 4),
            num_str, fill=nc, font=font_head)

        # Text rows (left side of card, right of swatch)
        lx = PANEL_X + PAD + 30
        # Row 1: Name
        draw.text((lx, cy + 4), nd["name"], fill=_TEXT, font=font_head)
        # Row 2: Node ID
        draw.text((lx, cy + 22), f"!{nd['id']}", fill=_TEXT_DIM, font=font_mono)

        # Temp values (right side, top)
        last_str = f"{tinfo['last_temp']}°C"
        avg_str  = f"avg {tinfo['avg_temp']}°C"
        samples_str = f"{tinfo['samples']}smp"
        # Last temp — prominent + coloured
        last_bb = draw.textbbox((0, 0), last_str, font=font_title)
        lw = last_bb[2] - last_bb[0]
        draw.text((IMG_W - PAD - lw, cy + 2), last_str, fill=color, font=font_title)
        # Avg + samples below last temp
        meta_str = f"avg {tinfo['avg_temp']}°C · {tinfo['samples']} samples"
        meta_bb = draw.textbbox((0, 0), meta_str, font=font_tiny)
        mw = meta_bb[2] - meta_bb[0]
        draw.text((IMG_W - PAD - mw, cy + 28), meta_str, fill=_TEXT_DIM, font=font_tiny)

        # --- Sparkline chart ---
        chart_y = cy + text_header_h + 4
        chart_w = PANEL_W - PAD * 2 - 30  # space between lx and right edge
        chart_x = lx

        # Chart background
        draw.rectangle(
            [chart_x, chart_y, chart_x + chart_w, chart_y + chart_h],
            fill=_CHART_BG, outline=_GRID, width=1)

        if series and len(series) >= 1:
            temps = [s["temp"] for s in series]
            y_min = min(temps) - 1
            y_max = max(temps) + 1
            if y_max - y_min < 2:
                y_min -= 1; y_max += 1

            # Y-axis labels (min / max)
            draw.text((chart_x + 2, chart_y + 2),
                      f"{y_max:.0f}°", fill=_TEXT_DIM, font=font_tiny)
            draw.text((chart_x + 2, chart_y + chart_h - 12),
                      f"{y_min:.0f}°", fill=_TEXT_DIM, font=font_tiny)

            # Sparkline (with left margin for y labels)
            spark_x = chart_x + 32
            spark_w = chart_w - 34
            _draw_sparkline(
                draw, spark_x, chart_y + 2, spark_w, chart_h - 4,
                series, y_min, y_max, color)

            # X-axis time markers
            now = time.time()
            for h_ago, lbl in [(24, "-24h"), (12, "-12h"), (0, "now")]:
                fx = (now - h_ago * 3600 - (now - 24 * 3600)) / (24 * 3600)
                tx = spark_x + int(fx * (spark_w - 1))
                draw.line([tx, chart_y + chart_h - 1, tx, chart_y + chart_h - 5],
                          fill=_GRID, width=1)
                draw.text((tx - 12, chart_y + chart_h - 12),
                          lbl, fill=_TEXT_DIM, font=font_tiny)
        else:
            draw.text((chart_x + 4, chart_y + 4),
                      "no 24h data", fill=_TEXT_DIM, font=font_tiny)

        cy += card_h + CARD_GAP

    # --- Legend bar at bottom ---
    ly = IMG_H - LEGEND_H
    draw.rectangle([0, ly, IMG_W, IMG_H], fill=_SURFACE)
    draw.line([0, ly, IMG_W, ly], fill=_BORDER, width=1)

    draw.text((PAD, ly + 10), "Temperature:", fill=_TEXT_DIM, font=font_head)
    temp_ranges = [
        ("<0°C", _temp_color(-5)), ("0–15°C", _temp_color(8)),
        ("15–25°C", _temp_color(20)), ("25–35°C", _temp_color(30)),
        (">35°C", _temp_color(40)),
    ]
    sx = 170
    for label, col in temp_ranges:
        draw.rectangle([sx, ly + 14, sx + 18, ly + 30], fill=col, outline=_BORDER, width=1)
        draw.text((sx + 24, ly + 12), label, fill=_TEXT_DIM, font=font_body)
        sx += 110

    version_label = "Meshtastic AI Bridge  ·  weather map"
    vb = draw.textbbox((0, 0), version_label, font=font_mono)
    draw.text((IMG_W - PAD - (vb[2] - vb[0]), ly + 12), version_label, fill=_TEXT_DIM, font=font_mono)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()
