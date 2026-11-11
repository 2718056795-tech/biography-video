#!/usr/bin/env python3
"""Build transparent graticule and narrative city route data, without fake outlines.

Offline, deterministic; dependencies: Pillow and the Python standard library.
All nodes and geographic grid use the same local equirectangular projection
and a single scale factor. No geodata download is attempted by this script.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '素材' / '地图'
WIDTH, HEIGHT = 700, 500
SUPER = 3
LAT0 = 32.6
LON0 = 105.0
RADIUS_M = 6371008.8
# Local geographic view; one scale and padding preserve projected proportions.
BOUNDS = (101.75, 108.25, 30.15, 35.05)  # west, east, south, north
PADDING = 24


def project(lon: float, lat: float) -> tuple[float, float]:
    return (
        RADIUS_M * math.radians(lon - LON0) * math.cos(math.radians(LAT0)),
        RADIUS_M * math.radians(lat - LAT0),
    )


X0, Y0 = project(BOUNDS[0], BOUNDS[2])
X1, Y1 = project(BOUNDS[1], BOUNDS[3])
SCALE = min((WIDTH - 2 * PADDING) / (X1 - X0), (HEIGHT - 2 * PADDING) / (Y1 - Y0))
OFFSET_X = (WIDTH - (X1 - X0) * SCALE) / 2
OFFSET_Y = (HEIGHT - (Y1 - Y0) * SCALE) / 2


def pixel(lon: float, lat: float) -> list[float]:
    x, y = project(lon, lat)
    return [round(OFFSET_X + (x - X0) * SCALE, 3), round(OFFSET_Y + (Y1 - y) * SCALE, 3)]


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    return ImageFont.truetype(str(path), size * SUPER) if path.exists() else ImageFont.load_default()


def curve(a: list[float], b: list[float], bow: float) -> list[list[float]]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    c1 = [a[0] + dx / 3 + nx * bow, a[1] + dy / 3 + ny * bow]
    c2 = [a[0] + dx * 2 / 3 + nx * bow, a[1] + dy * 2 / 3 + ny * bow]
    result = []
    for i in range(121):
        t = i / 120
        u = 1 - t
        result.append([
            round(u**3 * a[0] + 3 * u*u*t * c1[0] + 3 * u*t*t * c2[0] + t**3 * b[0], 3),
            round(u**3 * a[1] + 3 * u*u*t * c1[1] + 3 * u*t*t * c2[1] + t**3 * b[1], 3),
        ])
    return result


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads((ROOT / '数据' / '地图节点.json').read_text())
    canvas = Image.new('RGBA', (WIDTH * SUPER, HEIGHT * SUPER), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    grid_color = (114, 145, 130, 66)
    type_color = (155, 166, 145, 125)

    def line(coords: list[list[float]]) -> None:
        d.line([(round(x*SUPER), round(y*SUPER)) for x, y in coords], fill=grid_color, width=SUPER)

    # Mathematical longitude/latitude grid only. No pseudo coastline or terrain.
    for lon in range(102, 109):
        line([pixel(lon, BOUNDS[2]), pixel(lon, BOUNDS[3])])
        p = pixel(lon, 34.91)
    for lat in range(31, 36):
        if lat > BOUNDS[3]:
            continue
        line([pixel(BOUNDS[0], lat), pixel(BOUNDS[1], lat)])
        p = pixel(101.86, lat)

    nodes = []
    for node in data['nodes']:
        p = pixel(node['longitude'], node['latitude'])
        nodes.append({
            'id': node['id'], 'label': node['label'], 'modern_name': node['modern_name'],
            'longitude': node['longitude'], 'latitude': node['latitude'],
            'pixel': p, 'label_pixel': [round(p[0] + 20, 3), round(p[1] - 8, 3)],
        })
    routes = []
    for i in range(2):
        routes.append({
            'from': nodes[i]['id'], 'to': nodes[i+1]['id'],
            'points': curve(nodes[i]['pixel'], nodes[i+1]['pixel'], 14 if i == 0 else -28),
            'meaning': 'narrative city connection; not an ancient road or measured itinerary',
        })
    metadata = {
        'width': WIDTH, 'height': HEIGHT, 'nodes': nodes, 'routes': routes,
        'projection': {'name': 'local equirectangular', 'central_meridian': LON0,
                       'standard_parallel': LAT0, 'sphere_radius_m': RADIUS_M,
                       'single_pixels_per_projected_meter': SCALE,
                       'north_up': True, 'bounds_west_east_south_north': BOUNDS},
        'basemap': 'Mathematical graticule only. No coastline, river, terrain or administrative boundary.',
        'caption': '现代城市约位 · 连线仅示叙事次序',
        'attribution': 'City coordinates: GeoNames, CC BY 4.0; rounded and projected.',
    }
    canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(OUT / 'transparent_map.png')
    (OUT / 'routes.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'image': str(OUT / 'transparent_map.png'), 'nodes': nodes}, ensure_ascii=False))


if __name__ == '__main__':
    build()
