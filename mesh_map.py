"""
mesh_map.py - Generate terminal mesh network maps using OSM tiles + Pillow.

Fetches OpenStreetMap tiles, stitches them, overlays node markers,
and converts the result to Unicode half-block art for terminal display.
"""
import math
import os
import time
import hashlib
from io import BytesIO
from typing import Dict, Optional, Tuple, List
from PIL import Image, ImageDraw, ImageFont

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Tile cache directory
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".map_cache")
CACHE_TTL = 86400 * 7  # 7 days
TILE_SIZE = 256
OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = "MeshtasticAIBridge/1.0"


# ---------------------------------------------------------------------------
# OSM tile math
# ---------------------------------------------------------------------------

def _lat_lon_to_tile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _tile_to_lat_lon(x: int, y: int, zoom: int) -> Tuple[float, float]:
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lon


def _best_zoom(min_lat, max_lat, min_lon, max_lon, target_w=80, target_h=40) -> int:
    """Find best zoom level to fit bbox in roughly target_w x target_h tiles-pixels."""
    for z in range(18, 0, -1):
        x1, y1 = _lat_lon_to_tile(max_lat, min_lon, z)
        x2, y2 = _lat_lon_to_tile(min_lat, max_lon, z)
        pw = (abs(x2 - x1) + 1) * TILE_SIZE
        ph = (abs(y2 - y1) + 1) * TILE_SIZE
        # We want the image to be reasonable but not too many tiles
        if pw <= target_w * 8 and ph <= target_h * 8 and (abs(x2-x1)+1) <= 6 and (abs(y2-y1)+1) <= 6:
            return z
    return 4


# ---------------------------------------------------------------------------
# Tile fetching with disk cache
# ---------------------------------------------------------------------------

def _get_tile(z: int, x: int, y: int) -> Optional[Image.Image]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_key = f"{z}_{x}_{y}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.png")

    # Check cache
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < CACHE_TTL:
            try:
                return Image.open(cache_path).convert("RGB")
            except Exception:
                pass

    if not HAS_REQUESTS:
        return _blank_tile()

    url = OSM_URL.format(z=z, x=x, y=y)
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        if resp.status_code == 200:
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            img.save(cache_path)
            return img
    except Exception:
        pass

    return _blank_tile()


def _blank_tile() -> Image.Image:
    img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (13, 17, 23))
    return img


# ---------------------------------------------------------------------------
# Map generation
# ---------------------------------------------------------------------------

def generate_map(
    nodes: Dict[str, dict],
    selected_node_id: Optional[str] = None,
    map_filter: str = "all",
    term_width: int = 80,
    term_height: int = 40,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
    zoom_override: Optional[int] = None,
) -> Optional[Image.Image]:
    """
    Generate a map image with OSM background and node markers.
    Returns a PIL Image or None if no nodes with GPS.
    """
    # Filter nodes with GPS
    now = time.time()
    gps_nodes = {}
    for nid, info in nodes.items():
        pos = info.get('position')
        if not pos or pos.get('latitude') is None or pos.get('longitude') is None:
            continue
        if pos['latitude'] == 0 and pos['longitude'] == 0:
            continue

        # Apply filter
        f = map_filter
        if f == "0hop":
            if info.get('hops_away') != 0:
                continue
        elif f == "1hop":
            if (info.get('hops_away') or 999) > 1:
                continue
        elif f == "2hop":
            if (info.get('hops_away') or 999) > 2:
                continue
        elif f == "3hop+":
            if (info.get('hops_away') or 0) < 3:
                continue
        elif f == "1h":
            if now - info.get('last_heard', 0) > 3600:
                continue
        elif f == "6h":
            if now - info.get('last_heard', 0) > 21600:
                continue
        elif f == "24h":
            if now - info.get('last_heard', 0) > 86400:
                continue

        gps_nodes[nid] = info

    if not gps_nodes:
        return None

    # Bounding box
    lats = [n['position']['latitude'] for n in gps_nodes.values()]
    lons = [n['position']['longitude'] for n in gps_nodes.values()]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    if zoom_override is not None and center_lat is not None and center_lon is not None:
        # Fixed zoom centered on a specific point
        # Calculate bbox from center + zoom level
        # At zoom z, one tile covers 360/2^z degrees of longitude
        n = 2 ** zoom_override
        # Approximate degrees per pixel
        lon_per_px = 360.0 / (n * TILE_SIZE)
        lat_per_px = 170.0 / (n * TILE_SIZE)  # rough approximation
        half_w = lon_per_px * term_width
        half_h = lat_per_px * term_height * 2
        min_lat = center_lat - half_h
        max_lat = center_lat + half_h
        min_lon = center_lon - half_w
        max_lon = center_lon + half_w
    else:
        # Pad bounding box
        lat_pad = max((max_lat - min_lat) * 0.15, 0.005)
        lon_pad = max((max_lon - min_lon) * 0.15, 0.005)
        min_lat -= lat_pad
        max_lat += lat_pad
        min_lon -= lon_pad
        max_lon += lon_pad

    # Target image size (2 pixels per terminal char width, 4 per height due to half-blocks)
    img_w = term_width * 2
    img_h = term_height * 4

    if zoom_override is not None:
        zoom = max(1, min(18, zoom_override))
    else:
        zoom = _best_zoom(min_lat, max_lat, min_lon, max_lon, term_width, term_height)

    # Get tile range
    tx1, ty1 = _lat_lon_to_tile(max_lat, min_lon, zoom)
    tx2, ty2 = _lat_lon_to_tile(min_lat, max_lon, zoom)
    if tx1 > tx2:
        tx1, tx2 = tx2, tx1
    if ty1 > ty2:
        ty1, ty2 = ty2, ty1

    # Stitch tiles
    tiles_w = tx2 - tx1 + 1
    tiles_h = ty2 - ty1 + 1
    stitched = Image.new("RGB", (tiles_w * TILE_SIZE, tiles_h * TILE_SIZE))

    for tx in range(tx1, tx2 + 1):
        for ty in range(ty1, ty2 + 1):
            tile = _get_tile(zoom, tx, ty)
            if tile:
                stitched.paste(tile, ((tx - tx1) * TILE_SIZE, (ty - ty1) * TILE_SIZE))

    # Convert bbox to pixel coordinates on stitched image
    def lat_lon_to_px(lat, lon):
        n = 2 ** zoom
        x_frac = (lon + 180.0) / 360.0 * n
        lat_rad = math.radians(lat)
        y_frac = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
        px_x = (x_frac - tx1) * TILE_SIZE
        px_y = (y_frac - ty1) * TILE_SIZE
        return px_x, px_y

    # Crop to bounding box
    crop_x1, crop_y1 = lat_lon_to_px(max_lat, min_lon)
    crop_x2, crop_y2 = lat_lon_to_px(min_lat, max_lon)
    crop_x1, crop_x2 = sorted([crop_x1, crop_x2])
    crop_y1, crop_y2 = sorted([crop_y1, crop_y2])

    # Ensure valid crop
    crop_x1 = max(0, int(crop_x1))
    crop_y1 = max(0, int(crop_y1))
    crop_x2 = min(stitched.width, int(crop_x2))
    crop_y2 = min(stitched.height, int(crop_y2))

    if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
        return None

    cropped = stitched.crop((crop_x1, crop_y1, crop_x2, crop_y2))

    # Resize to terminal target
    cropped = cropped.resize((img_w, img_h), Image.LANCZOS)

    # Draw node markers
    draw = ImageDraw.Draw(cropped)

    crop_lat_range = max_lat - min_lat
    crop_lon_range = max_lon - min_lon

    for nid, info in gps_nodes.items():
        lat = info['position']['latitude']
        lon = info['position']['longitude']

        # Map to image pixels
        px = int((lon - min_lon) / crop_lon_range * (img_w - 1))
        py = int((max_lat - lat) / crop_lat_range * (img_h - 1))
        px = max(0, min(img_w - 1, px))
        py = max(0, min(img_h - 1, py))

        is_mqtt = info.get('connection_type') == 'tcp'
        hops = info.get('hops_away')
        is_selected = (nid == selected_node_id)

        # Colors
        if is_selected:
            color = (255, 136, 0)       # orange
            radius = 7
        elif hops == 0:
            color = (63, 185, 80)       # green - direct
            radius = 5
        elif is_mqtt:
            color = (240, 136, 62)      # orange - mqtt
            radius = 5
        else:
            color = (88, 166, 255)      # blue - radio
            radius = 5

        # Draw marker (filled circle + outline)
        draw.ellipse(
            [px - radius, py - radius, px + radius, py + radius],
            fill=color, outline=(255, 255, 255), width=1
        )

        # Draw label
        name = info.get('short_name', nid[:4])
        try:
            draw.text((px + radius + 3, py - 6), name,
                      fill=(255, 255, 255))
            # Dark outline for readability
            for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                draw.text((px + radius + 3 + dx, py - 6 + dy), name,
                          fill=(0, 0, 0))
            draw.text((px + radius + 3, py - 6), name,
                      fill=(255, 255, 255))
        except Exception:
            pass

    return cropped


# ---------------------------------------------------------------------------
# Image to Rich markup (half-block Unicode)
# ---------------------------------------------------------------------------

def image_to_halfblock(img: Image.Image, width: int = 80) -> str:
    """
    Convert PIL Image to colored Unicode half-block string with Rich markup.
    Uses top-half block (\\u2580) with fg=top_pixel, bg=bottom_pixel.
    Each character represents 2 vertical pixels.
    """
    # Resize to target width, height must be even
    h = int(img.height * width / img.width)
    if h % 2 != 0:
        h += 1
    img = img.resize((width, h), Image.LANCZOS)

    pixels = img.load()
    lines = []

    for y in range(0, h, 2):
        line_parts = []
        for x in range(width):
            r1, g1, b1 = pixels[x, y][:3]
            if y + 1 < h:
                r2, g2, b2 = pixels[x, y + 1][:3]
            else:
                r2, g2, b2 = 0, 0, 0

            # Use Rich color tags
            fg = f"#{r1:02x}{g1:02x}{b1:02x}"
            bg = f"#{r2:02x}{g2:02x}{b2:02x}"
            line_parts.append(f"[{fg} on {bg}]\u2580[/]")

        lines.append(''.join(line_parts))

    return '\n'.join(lines)


def render_map_text(
    nodes: Dict[str, dict],
    selected_node_id: Optional[str] = None,
    map_filter: str = "all",
    term_width: int = 80,
    term_height: int = 35,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
    zoom_override: Optional[int] = None,
) -> str:
    """
    High-level: generate map + convert to Rich markup string.
    Returns Rich-formatted string for display in a Static/RichLog widget.
    """
    img = generate_map(
        nodes, selected_node_id, map_filter,
        term_width=term_width, term_height=term_height,
        center_lat=center_lat, center_lon=center_lon,
        zoom_override=zoom_override,
    )

    if img is None:
        return (
            f"[dim]No nodes with GPS data[/dim]\n"
            f"[dim]Filter: {map_filter}[/dim]\n\n"
            f"[dim]Nodes need GPS position to appear on map[/dim]"
        )

    # Leave room for header/footer lines
    map_h = max(10, term_height - 6)
    map_text = image_to_halfblock(img, width=term_width)

    # Count GPS nodes for header
    now = time.time()
    gps_count = sum(1 for n in nodes.values()
                    if n.get('position', {}).get('latitude') is not None)

    zoom_str = f"z{zoom_override}" if zoom_override else "auto"
    header = (
        f"[bold #58a6ff]Mesh Map[/]  "
        f"[#8b949e]Nodes:[/] [bold #e6edf3]{gps_count}[/]  "
        f"[#8b949e]Zoom:[/] [bold #e6edf3]{zoom_str}[/]  "
        f"[#8b949e]Filter:[/] [bold #e6edf3]{map_filter.upper()}[/]"
    )
    controls = (
        "[#8b949e]F9[/] close  "
        "[#8b949e]F10[/] filter  "
        "[#8b949e]+/-[/] zoom  "
        "[#8b949e]0[/] reset zoom"
    )
    legend = (
        "[#3fb950]\u2b24[/] direct  "
        "[#58a6ff]\u2b24[/] radio  "
        "[#f0883e]\u2b24[/] mqtt  "
        "[bold #ff8800]\u2b24[/] selected"
    )

    return f"{header}\n{controls}\n{legend}\n{map_text}"
