#!/usr/bin/env python3
"""Data-driven cumulative maps in the locked biography-series panel.

No person-specific names, scene IDs, geographic bounds, downloads, or system-font
fallbacks are embedded here. Geometry/timing styles come from series_style.json;
routes, geographic view, region annotations, and palette come from the project.
"""
from __future__ import annotations

from copy import deepcopy
from collections import OrderedDict
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping

from PIL import Image, ImageColor, ImageDraw, ImageFont, PngImagePlugin

SERIES_ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'series'
STYLE_PATH = SERIES_ASSETS / 'series_style.json'
POLICY_PATH = SERIES_ASSETS / 'map_policy.json'
EVIDENCE_KEY = 'series_map_evidence'
_RENDERERS = OrderedDict()
_PIXEL_HASHES = OrderedDict()


def _json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


@lru_cache(maxsize=64)
def _file_hash_at_stat(path, size, mtime_ns, ctime_ns):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_sha256(path):
    """Hash static sources once per actual file revision, never once per frame."""
    path = Path(path).resolve()
    stat = path.stat()
    return _file_hash_at_stat(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _remember(cache, key, value, maximum):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > maximum:
        cache.popitem(last=False)


def _luminance(rgb):
    channels = [c / 255 for c in rgb]
    return sum(k * (v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4)
               for k, v in zip((.2126, .7152, .0722), channels))


def _contrast(ink, paper, alpha=255):
    composite = [round((a * alpha + b * (255 - alpha)) / 255)
                 for a, b in zip(ink, paper)]
    light, dark = sorted((_luminance(composite), _luminance(paper)), reverse=True)
    return (light + .05) / (dark + .05)


def _clip_segment(a, b, bounds):
    """Liang–Barsky intersection, retaining crossing segments with no inside vertex."""
    west, east, south, north = bounds
    dx, dy = b[0] - a[0], b[1] - a[1]
    lo, hi = 0., 1.
    for p, q in ((-dx, a[0]-west), (dx, east-a[0]),
                 (-dy, a[1]-south), (dy, north-a[1])):
        if p == 0:
            if q < 0:
                return None
        else:
            u = q / p
            if p < 0:
                lo = max(lo, u)
            else:
                hi = min(hi, u)
            if lo > hi:
                return None
    first = (a[0]+lo*dx, a[1]+lo*dy)
    last = (a[0]+hi*dx, a[1]+hi*dy)
    return None if math.dist(first, last) < 1e-12 else (first, last)


def _clip_runs(coords, bounds):
    """Split at real exits, separate source parts and longitude discontinuities."""
    run = []
    for a, b in zip(coords, coords[1:]):
        clipped = None if abs(b[0]-a[0]) > 180 else _clip_segment(a, b, bounds)
        if clipped is None:
            if len(run) > 1:
                yield run
            run = []
            continue
        first, last = clipped
        if run and math.dist(run[-1], first) < 1e-9:
            run.append(last)
        else:
            if len(run) > 1:
                yield run
            run = [first, last]
    if len(run) > 1:
        yield run


def _object(value, name):
    if isinstance(value, Mapping):
        return deepcopy(dict(value))
    if isinstance(value, (str, Path)):
        result = json.loads(Path(value).read_text(encoding='utf-8'))
        if isinstance(result, dict):
            return result
    raise TypeError(f'{name} must be a JSON object or local JSON path')


def _rgb(value, role):
    color = ImageColor.getrgb(value) if isinstance(value, str) else tuple(value)
    if len(color) != 3 or any(not isinstance(c, int) or not 0 <= c <= 255 for c in color):
        raise ValueError(f'{role} must be RGB; opacity is owned by the series style')
    return color


def _ease(value):
    value = max(0., min(1., value))
    return value * value * (3 - 2 * value)


class SeriesMap:
    """SeriesMap(route_data, style, theme, coastline_geojson=None).

    ``render(scene_id, t, duration)`` returns an unpositioned transparent RGBA
    880x430 image. Composite at ``position`` on the native 1080x1920 frame.
    ``geometry_report()`` returns JSON-serializable coordinates and diagnostics.
    """

    def __init__(self, route_data, style, theme, coastline_geojson=None, basemap_geojson=None):
        canonical = _object(STYLE_PATH, 'series style')
        supplied = _object(style, 'style')
        supplied_map = supplied.get('map', supplied)
        for key, value in canonical['map'].items():
            if key in supplied_map and supplied_map[key] != value:
                raise ValueError(f'Locked map style changed: {key}')
        # Sparse input may inherit canonical fields; it cannot replace them.
        self.style = deepcopy(canonical['map'])
        self.width, self.height = self.style['width'], self.style['height']
        self.position = (self.style['x'], self.style['y'])
        self.size = (self.width, self.height)
        self.ss = self.style['supersampling']
        if (self.position, self.size, self.ss, self.style['plot_box']) != (
                (96, 150), (880, 430), 2, [20, 8, 860, 415]):
            raise ValueError('Authoritative series map geometry is incompatible')
        self._motion = deepcopy(canonical['motion'])
        self._default_location_intro_sec = canonical['standard']['meta']['start']
        self.policy = _object(POLICY_PATH, 'map policy')
        for key in ('map_segment_delay', 'map_active_window_sec'):
            if key in supplied.get('motion', {}) and supplied['motion'][key] != self._motion[key]:
                raise ValueError(f'Locked map timing changed: {key}')
        self._font_paths = {
            bold: SERIES_ASSETS / canonical['fonts']['sans_bold' if bold else 'sans_regular']
            for bold in (False, True)
        }
        for path in self._font_paths.values():
            if not path.is_file():
                raise FileNotFoundError(f'Required bundled series font missing: {path}')

        self.data = _object(route_data, 'route_data')
        self.theme = _object(theme, 'theme')
        colors = self.theme.get('colors', self.theme.get('roles', self.theme.get('palette', self.theme)))
        self.colors = {}
        for role in ('map_ink', 'map_accent', 'map_halo', 'map_coast', 'paper'):
            if role not in colors:
                raise ValueError(f'Theme is missing {role}')
            self.colors[role] = _rgb(colors[role], role)
        self.colors['map_label_halo'] = _rgb(
            colors.get('map_label_halo', colors.get('label_halo', colors['paper'])), 'map_label_halo')
        self.requested_colors = deepcopy(self.colors)
        # A narrow paper outline protects the same fixed labels over every leg.
        # Keep the requested value in evidence, while the effective map outline
        # always matches the actual theme paper. Other theme roles stay intact.
        self.colors['map_label_halo'] = self.colors['paper']
        self._readability = self._adapt_colors(colors)
        self._readability['label_halo'] = {
            'requested': list(self.requested_colors['map_label_halo']),
            'effective': list(self.colors['map_label_halo']), 'paper_matched': True,
            'alpha': self.style['label_halo_alpha'], 'stroke_px': self.style['label_stroke_px']}
        self.nodes = {}
        for item in self.data.get('nodes', []):
            node = deepcopy(item)
            key = node.get('id')
            if not isinstance(key, str) or not key or key in self.nodes:
                raise ValueError('Nodes require unique nonempty string IDs')
            lon = node.get('lon', node.get('longitude'))
            lat = node.get('lat', node.get('latitude'))
            if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
                raise ValueError(f'Node {key}: missing numeric lon/lat')
            if not math.isfinite(lon) or not math.isfinite(lat) or not -180 <= lon <= 180 or not -85 <= lat <= 85:
                raise ValueError(f'Node {key}: coordinates outside supported geographic range')
            if not isinstance(node.get('label'), str) or not node['label']:
                raise ValueError(f'Node {key}: missing label')
            node.update(lon=float(lon), lat=float(lat))
            self.nodes[key] = node
        if not self.nodes:
            raise ValueError('At least one geographic node is required')

        self.visit_report = []
        visits = self.data.get('visits', [])
        if 'sequence' in self.data:
            self.sequence = list(self.data['sequence'])
        elif visits:
            self.sequence = []
            visit_ids = set()
            for row in visits:
                if row.get('id') in visit_ids or not row.get('id'):
                    raise ValueError('Visits require unique nonempty IDs')
                visit_ids.add(row['id'])
                key = row.get('node_id')
                if not self.sequence or self.sequence[-1] != key:
                    self.sequence.append(key)
                self.visit_report.append({**row, 'sequence_index': len(self.sequence)-1})
        else:
            raise ValueError('Provide sequence[node_id] or visits[{id,node_id,scene_id}]')
        if not self.sequence or any(key not in self.nodes for key in self.sequence):
            raise ValueError('Sequence contains no visits or references an unknown node')
        scene_data = self.data.get('per_scene', self.data.get('scenes'))
        if scene_data is not None:
            if not isinstance(scene_data, dict):
                raise ValueError('per_scene must map scene IDs to index ranges')
            self.per_scene = deepcopy(scene_data)
        elif self.visit_report:
            self.per_scene = self._derive_scenes()
        else:
            raise ValueError('Explicit sequence requires per_scene index ranges')
        self.scene_order = self.data.get('scene_order', list(self.per_scene))
        if (not isinstance(self.scene_order, list) or not self.scene_order
                or any(not isinstance(sid, str) or not sid for sid in self.scene_order)
                or len(set(self.scene_order)) != len(self.scene_order)
                or set(self.scene_order) != set(self.per_scene)):
            raise ValueError('scene_order must include each per_scene ID exactly once')
        self.scene_order = list(self.scene_order)
        # JSON evidence is canonicalized with sorted object keys. Bind the
        # resolved insertion order explicitly so a replay cannot reorder scenes.
        self.data['scene_order'] = list(self.scene_order)
        self.opening_scene_id = self.scene_order[0]
        self.first_location_scene_id = self.scene_order[1] if len(self.scene_order) > 1 else None
        for sid, plan in self.per_scene.items():
            if not isinstance(plan, dict):
                raise ValueError(f'{sid}: map plan must be an object')
            a, b = plan.get('start_index'), plan.get('end_index')
            if type(a) is not int or type(b) is not int or not 0 <= a <= b < len(self.sequence):
                raise ValueError(f'{sid}: invalid start_index/end_index')
            region = plan.get('region_node_ids', [])
            if any(key not in self.nodes for key in region):
                raise ValueError(f'{sid}: unknown region node ID')
            if region and not plan.get('region_label'):
                raise ValueError(f'{sid}: region_node_ids requires a region_label')
            intro = plan.get('location_intro_sec', self._default_location_intro_sec)
            if (isinstance(intro, bool) or not isinstance(intro, (int, float))
                    or not math.isfinite(intro) or intro < 0):
                raise ValueError(f'{sid}: location_intro_sec must be finite and nonnegative')
            if sid != self.opening_scene_id and intro < self._default_location_intro_sec:
                raise ValueError(f'{sid}: location_intro_sec must be at least '
                                 f'{self._default_location_intro_sec}s, when location metadata starts')
        opening = self.per_scene[self.opening_scene_id]
        if (opening['start_index'], opening['end_index']) != (0, 0):
            raise ValueError(f'{self.opening_scene_id}: opening map must hold origin index 0..0; '
                             'move its journey visits into the following scene so no nodes are skipped')
        previous = 0
        for sid in self.scene_order[1:]:
            plan = self.per_scene[sid]
            if plan['start_index'] != previous:
                raise ValueError(f'{sid}: start_index must equal the previous scene end_index '
                                 f'({previous}); do not skip or replay journey visits')
            previous = plan['end_index']

        projection = self.data.get('projection', {})
        bounds = projection.get('bounds', projection.get('bounds_west_east_south_north'))
        automatic = bounds is None
        if bounds is None:
            lons = [n['lon'] for n in self.nodes.values()]
            lats = [n['lat'] for n in self.nodes.values()]
            if max(lons) - min(lons) > 180:
                raise ValueError('Auto bounds crossing the antimeridian need separate regional views')
            viewport = self.policy['viewport']
            fraction = viewport['route_padding_fraction']
            lon_span = max(viewport['automatic_minimum_longitude_span_deg'],
                           (max(lons)-min(lons))*(1+2*fraction))
            lat_span = max(viewport['automatic_minimum_latitude_span_deg'],
                           (max(lats)-min(lats))*(1+2*fraction))
            lon_mid, lat_mid = (max(lons)+min(lons))/2, (max(lats)+min(lats))/2
            bounds = self._bounded_view(lon_mid, lat_mid, lon_span, lat_span)
        if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
            raise ValueError('bounds must be [west,east,south,north] finite numbers')
        self._geo_lines, self._sources, self._ignored_geometries = [], [], []
        self._custom_basemap = _object(basemap_geojson, 'basemap_geojson') if basemap_geojson is not None else None
        self._custom_coast = _object(coastline_geojson, 'coastline_geojson') if coastline_geojson is not None else None
        if self._custom_basemap is None:
            try:
                from series_basemap import load_default_basemap
            except ImportError:
                from .series_basemap import load_default_basemap
            try:
                default_geography = load_default_basemap()
            except FileNotFoundError as exc:
                raise ValueError('Bundled coast/river basemap is missing. Reinstall assets/series/geography '
                                 'or supply a sourced basemap_geojson; routes alone cannot be rendered.') from exc
            self._read_geography(default_geography, 'bundled Natural Earth')
        else:
            self._read_geography(self._custom_basemap, 'supplied basemap', basemap_geojson)
        if self._custom_coast is not None:
            self._read_geography(self._custom_coast, 'supplied coastline', coastline_geojson, default_layer='coast')
        self.bounds = tuple(map(float, bounds))
        west, east, south, north = self.bounds
        if not -180 <= west < east <= 180 or not -85 <= south < north <= 85:
            raise ValueError('Invalid or unsupported geographic bounds')
        self.lat0 = float(projection.get('standard_parallel', (south+north)/2))
        self.lon0 = float(projection.get('central_meridian', (west+east)/2))
        if not math.isfinite(self.lat0) or not -85 <= self.lat0 <= 85 or not math.isfinite(self.lon0):
            raise ValueError('Invalid projection center')
        attempts = self.policy['viewport']['empty_context_expansion_attempts'] if automatic else 0
        self._viewport_expansions = 0
        for attempt in range(attempts+1):
            self._set_projection()
            self._basemap_runs = self._visible_geography()
            length = sum(math.dist(a, b) for item in self._basemap_runs
                         for a, b in zip(item['points'], item['points'][1:]))
            if length >= self.policy['basemap']['minimum_visible_length_px']:
                break
            if attempt < attempts:
                west, east, south, north = self.bounds
                factor = self.policy['viewport']['empty_context_expansion_factor']
                self.bounds = tuple(self._bounded_view((west+east)/2, (south+north)/2,
                                                       (east-west)*factor, (north-south)*factor))
                self._viewport_expansions += 1
        else:
            raise ValueError('No usable sourced geographic context in map viewport '
                             f'{list(self.bounds)}. Widen projection.bounds or supply a sourced '
                             'higher-resolution coast/river LineString basemap; routes alone are not a map. '
                             'Country polygons and fabricated coastal substitutes are not accepted.')
        outside = [key for key, node in self.nodes.items() if not (
            self.bounds[0] <= node['lon'] <= self.bounds[1] and
            self.bounds[2] <= node['lat'] <= self.bounds[3])]
        if outside:
            raise ValueError(f'Map viewport excludes route nodes {outside}; widen projection.bounds')
        self._automatic_view = automatic
        self.points = [self.pixel(self.nodes[key]['lon'], self.nodes[key]['lat']) for key in self.sequence]
        self.curves = [self._curve(i) for i in range(len(self.points)-1)]
        self._degenerate = [i for i,p in enumerate(self.curves) if math.dist(p[0],p[-1]) < .001]
        self._label_layouts = self._layout_labels()
        self._label_layout_sha256 = _json_hash(self._label_layouts)
        self._coast_runs = [r['points'] for r in self._basemap_runs if r['layer'] == 'coast']
        self._coast_status = f'{len(self._coast_runs)} actual clipped coast runs; inland views may show rivers only'
        self._base_image = self._make_base()
        self._native_basemap = self._base_image.resize(self.size, Image.Resampling.LANCZOS)
        self._geometry = self._geometry_report()
        self._geometry_sha256 = _json_hash(self._geometry)
        self._render_spec = {'route_data': self.data, 'theme': self.theme,
                             'basemap_geojson': self._custom_basemap,
                             'coastline_geojson': self._custom_coast,
                             'basemap_source_path': str(Path(basemap_geojson).resolve()) if isinstance(basemap_geojson,(str,Path)) else None,
                             'coastline_source_path': str(Path(coastline_geojson).resolve()) if isinstance(coastline_geojson,(str,Path)) else None}
        self._render_spec_sha256 = _json_hash(self._render_spec)
        _remember(_RENDERERS, (self._geometry_sha256, self._render_spec_sha256), self, 12)

    def _derive_scenes(self):
        by_scene = {}
        input_order = []
        last_scene = None
        for row in self.visit_report:
            sid = row.get('scene_id')
            if not isinstance(sid, str) or not sid:
                raise ValueError('Visits require scene_id when deriving per_scene')
            if sid != last_scene:
                if sid in by_scene:
                    raise ValueError('Visits for each scene must be contiguous')
                input_order.append(sid)
            by_scene.setdefault(sid, []).append(row['sequence_index'])
            last_scene = sid
        order = self.data.get('scene_order', input_order)
        if len(set(order)) != len(order) or not set(by_scene).issubset(order):
            raise ValueError('scene_order must include each visit scene exactly once')
        result, previous = {}, 0
        for sid in order:
            end = max(by_scene.get(sid, [previous]))
            if end < previous:
                raise ValueError('scene_order must follow visit chronology')
            result[sid] = {'start_index':previous, 'end_index':end}
            previous = end
        return result

    def validate_scene_timings(self, scenes, fps):
        """Check storyboard cues without changing the evidence-bound route inputs."""
        if (isinstance(fps, bool) or not isinstance(fps, (int, float))
                or not math.isfinite(fps) or fps <= 0):
            raise ValueError('Storyboard fps must be finite and positive')
        if not isinstance(scenes, list) or any(not isinstance(scene, dict) for scene in scenes):
            raise ValueError('Storyboard scenes must be a list of scene objects')
        if [scene.get('id') for scene in scenes] != self.scene_order:
            raise ValueError('Storyboard scene order must match the map scene_order exactly')
        for index, scene in enumerate(scenes):
            sid = scene['id']
            if (scene.get('kind') == 'opening') != (index == 0):
                raise ValueError(f'{sid}: only the first storyboard scene must be kind opening')
            start, end = scene.get('start_frame'), scene.get('end_frame')
            if type(start) is not int or type(end) is not int or not 0 <= start < end:
                raise ValueError(f'{sid}: storyboard requires a positive integer frame window')
            duration = (end-start)/fps
            intro = self._location_intro_sec(sid)
            if 'location_intro_sec' in scene:
                cue = scene['location_intro_sec']
                if (isinstance(cue, bool) or not isinstance(cue, (int, float))
                        or not math.isfinite(cue) or cue != intro):
                    raise ValueError(f'{sid}: storyboard location_intro_sec must match the map cue ({intro})')
            self.frame_state(sid, 0., duration)
            if index:
                final = self.frame_state(sid, (end-start-1)/fps, duration)
                if final['current_index'] != self.per_scene[sid]['end_index']:
                    raise ValueError(f'{sid}: journey must reach end_index before the last native frame; '
                                     'introduce the location earlier or move visits into a later scene')
        return self

    def _location_intro_sec(self, scene_id):
        return (0. if scene_id == self.opening_scene_id else
                float(self.per_scene[scene_id].get('location_intro_sec', self._default_location_intro_sec)))

    def _adapt_colors(self, theme_colors):
        paper = self.colors['paper']
        records = {}
        for role, requirements in self.policy['readability'].items():
            if not isinstance(requirements, list):
                continue
            requested = self.colors[role]
            def passes(candidate):
                return all(_contrast(candidate, paper, row['alpha']) >= row['minimum_contrast']
                           for row in requirements)
            effective = requested
            target_name = 'requested'
            if not passes(effective):
                theme_ink = _rgb(theme_colors.get('ink', requested), 'ink')
                extremes = sorted(((0,0,0), (255,255,255)),
                                  key=lambda color: _contrast(color, paper), reverse=True)
                for target_name, target in [('theme ink', theme_ink), ('contrast ink', extremes[0])]:
                    found = False
                    for step in range(1, 257):
                        candidate = tuple(round(a+(b-a)*step/256) for a,b in zip(requested, target))
                        if passes(candidate):
                            effective, found = candidate, True
                            break
                    if found:
                        break
                else:
                    raise ValueError(f'Map palette cannot meet {role} readability thresholds on paper {paper}')
            self.colors[role] = effective
            checks = [{'purpose': row['purpose'], 'alpha': row['alpha'],
                       'minimum_contrast': row['minimum_contrast'],
                       'requested_contrast': _contrast(requested, paper, row['alpha']),
                       'effective_contrast': _contrast(effective, paper, row['alpha']),
                       'passed': passes(effective)} for row in requirements]
            records[role] = {'requested': list(requested), 'effective': list(effective),
                             'adapted': effective != requested, 'toward': target_name, 'checks': checks}
        return {'method': self.policy['readability']['method'], 'paper': list(paper),
                'roles': records, 'passed': all(c['passed'] for r in records.values() for c in r['checks']),
                'scope': 'map colors only, measured on theme paper; other theme colors unchanged'}

    @staticmethod
    def _bounded_view(lon, lat, lon_span, lat_span):
        lon_span, lat_span = min(360., lon_span), min(170., lat_span)
        west = max(-180., min(180.-lon_span, lon-lon_span/2))
        south = max(-85., min(85.-lat_span, lat-lat_span/2))
        return [west, west+lon_span, south, south+lat_span]

    def _set_projection(self):
        west, east, south, north = self.bounds
        self.x0, self.y0 = self._project(west, south)
        x1, self.y1 = self._project(east, north)
        left, top, right, bottom = self.style['plot_box']
        self.scale = min((right-left)/(x1-self.x0), (bottom-top)/(self.y1-self.y0))
        self.ox = (left+right-(x1-self.x0)*self.scale)/2
        self.oy = (top+bottom-(self.y1-self.y0)*self.scale)/2

    def _read_geography(self, raw, label, source=None, default_layer=None):
        features = raw.get('features', [raw])
        collection = {'type': 'FeatureCollection', 'features': features}
        fingerprint = _json_hash(collection)
        if raw.get('sha256') and raw['sha256'] != fingerprint:
            raise ValueError(f'{label}: geographic data fingerprint does not match its coordinates')
        provenance = deepcopy(raw.get('provenance', {}))
        source_files = []
        # Only local runtime records are hashed here. Upstream files are documented
        # with URLs/checksums in provenance and need not exist in an installed bundle.
        for item in provenance.get('local_files', []):
            if not isinstance(item, dict) or not item.get('path') or not item.get('sha256'):
                raise ValueError(f'{label}: invalid local source file record')
            path = Path(item['path']).resolve()
            actual = file_sha256(path)
            if actual != item['sha256']:
                raise ValueError(f'{label}: local source checksum mismatch: {path}')
            source_files.append({'path': str(path), 'sha256': actual})
        if isinstance(source, (str, Path)):
            path = Path(source).resolve()
            source_files.append({'path': str(path), 'sha256': file_sha256(path)})
        if label == 'bundled Natural Earth' and not provenance:
            raise ValueError('Bundled basemap lacks source provenance; reinstall the complete series package')
        has_lines = any(f.get('geometry', f).get('type') in ('LineString', 'MultiLineString') for f in features)
        if label != 'bundled Natural Earth' and has_lines:
            url = provenance.get('source_url', '')
            if not isinstance(url, str) or not url.startswith(('https://', 'http://')) or not isinstance(provenance.get('license'), str) or not provenance['license'].strip():
                raise ValueError(f'{label}: custom geographic lines require provenance.source_url '
                                 '(http/https) and provenance.license; document the actual data source')
        self._sources.append({'label': label, 'data_sha256': fingerprint,
                              'source_files': source_files, 'provenance': provenance})
        cfg = self.data.get('coastline', {}) if default_layer == 'coast' else {}
        filter_bounds = cfg.get('filter_bounds', self.data.get('projection', {}).get('coast_filter_bounds'))
        if filter_bounds is not None and (len(filter_bounds) != 4 or
                not all(isinstance(v, (float, int)) and math.isfinite(v) for v in filter_bounds)):
            raise ValueError('coast filter_bounds must contain four finite geographic numbers')
        for index, feature in enumerate(features):
            g = feature.get('geometry', feature)
            typ = g.get('type')
            if typ in ('Polygon', 'MultiPolygon'):
                self._ignored_geometries.append({'source': label, 'feature': index, 'type': typ,
                                                  'reason': 'country rings are not coastlines'})
                continue
            if typ not in ('LineString', 'MultiLineString'):
                raise ValueError(f'{label}: unsupported geometry {typ}; provide actual coast/river lines')
            props = feature.get('properties') or {}
            layer = props.get('layer', props.get('kind', default_layer))
            if layer not in ('coast', 'river'):
                raise ValueError(f'{label}: feature {index} requires properties.layer coast or river')
            parts = [g['coordinates']] if typ == 'LineString' else g['coordinates']
            for part_index, coords in enumerate(parts):
                if not isinstance(coords, list) or len(coords) < 2:
                    continue
                clean = []
                for coord in coords:
                    if (not isinstance(coord, (list, tuple)) or len(coord) < 2 or
                            not all(isinstance(v, (int, float)) and math.isfinite(v) for v in coord[:2]) or
                            not -180 <= coord[0] <= 180 or not -90 <= coord[1] <= 90):
                        raise ValueError(f'{label}: invalid WGS84 coordinate in feature {index}')
                    clean.append((float(coord[0]), float(coord[1])))
                self._geo_lines.append({'layer': layer, 'coords': clean, 'name': props.get('name'),
                                        'source_id': props.get('source_id', index), 'part': part_index,
                                        'data_sha256': fingerprint,
                                        'bbox': (min(x for x,y in clean), min(y for x,y in clean),
                                                 max(x for x,y in clean), max(y for x,y in clean)),
                                        'filter_bounds': filter_bounds if layer == 'coast' else None})

    def _visible_geography(self):
        result = []
        for item in self._geo_lines:
            bounds = self.bounds
            coords = item['coords']
            # Quick rejection keeps worldwide data inexpensive in regional views.
            xmin, ymin, xmax, ymax = item['bbox']
            if xmax < bounds[0] or xmin > bounds[1] or ymax < bounds[2] or ymin > bounds[3]:
                continue
            if item['filter_bounds'] is not None:
                a,b,c,d = item['filter_bounds']
                bounds = (max(bounds[0],a), min(bounds[1],b), max(bounds[2],c), min(bounds[3],d))
                if bounds[0] >= bounds[1] or bounds[2] >= bounds[3]:
                    continue
            for run in _clip_runs(coords, bounds):
                result.append({'layer': item['layer'], 'name': item['name'],
                               'source_id': item['source_id'], 'part': item['part'],
                               'data_sha256': item['data_sha256'],
                               'geographic_points': run,
                               'points': [self.pixel(lon, lat) for lon, lat in run]})
        return result

    def _project(self, lon, lat):
        return ((lon-self.lon0)*math.cos(math.radians(self.lat0)), lat-self.lat0)

    def pixel(self, lon, lat):
        x,y = self._project(lon,lat)
        return self.ox+(x-self.x0)*self.scale, self.oy+(self.y1-y)*self.scale

    @lru_cache(maxsize=16)
    def _font(self, size, bold=False):
        return ImageFont.truetype(str(self._font_paths[bool(bold)]), size*self.ss)

    def _line(self,d,points,color,width=1):
        d.line([(round(x*self.ss),round(y*self.ss)) for x,y in points],
               fill=color,width=max(1,round(width*self.ss)),joint='curve')

    def _circle(self,d,x,y,r,fill=None,outline=None,width=1):
        d.ellipse(tuple(round(v*self.ss) for v in (x-r,y-r,x+r,y+r)),fill=fill,
                  outline=outline,width=max(1,round(width*self.ss)))

    def _curve(self,i):
        a,b = self.points[i],self.points[i+1]
        dx,dy = b[0]-a[0],b[1]-a[1]
        raw_length = math.hypot(dx,dy)
        if raw_length < .001:
            return [a]*91  # no decorative loop for a same-place hold
        length=max(.01,raw_length);nx,ny=-dy/length,dx/length
        bend=min(23.,max(5.,length*.14))*(1 if i%2==0 else -1)
        c1=(a[0]+dx/3+nx*bend,a[1]+dy/3+ny*bend)
        c2=(a[0]+dx*2/3+nx*bend,a[1]+dy*2/3+ny*bend)
        return [((1-t)**3*a[0]+3*(1-t)**2*t*c1[0]+3*(1-t)*t*t*c2[0]+t**3*b[0],
                 (1-t)**3*a[1]+3*(1-t)**2*t*c1[1]+3*(1-t)*t*t*c2[1]+t**3*b[1])
                for t in [j/90 for j in range(91)]]

    def _make_base(self):
        im=Image.new('RGBA',(self.width*self.ss,self.height*self.ss),(0,0,0,0))
        d=ImageDraw.Draw(im)
        for item in self._basemap_runs:
            style = self.policy['basemap'][item['layer']]
            self._line(d,item['points'],self.colors['map_coast']+(style['alpha'],),style['width'])
        return im

    def _region_layout(self,plan):
        points=[self.pixel(self.nodes[key]['lon'],self.nodes[key]['lat']) for key in plan['region_node_ids']]
        cx=sum(x for x,y in points)/len(points);cy=sum(y for x,y in points)/len(points)
        # Legacy series radius is retained at normal scales. Tiny regional views
        # also respect the actual center's edge distance. Do not move real points.
        edge_radius=max(0.,min(cx-4,self.width-4-cx,cy-4,self.height-4-cy))
        radius=min(26*self.scale/(221/11.5), self.height*.45,edge_radius)
        box=(cx-radius,cy-radius,cx+radius,cy+radius)
        f=self._font(26);label=plan['region_label']
        width=f.getlength(label)/self.ss
        height=f.getbbox(label,anchor='lt')[3]/self.ss
        if width>self.width-8:
            raise ValueError('Region label exceeds the locked panel width')
        tx=cx+radius+9;ty=cy-4
        if tx+width>self.width-4:tx=cx-radius-9-width
        tx=max(4.,min(self.width-4-width,tx))
        ty=max(4.,min(self.height-4-height,ty))
        label_box=(tx,ty,tx+width,ty+height)
        clipped=not (0<=box[0]<=box[2]<=self.width and 0<=box[1]<=box[3]<=self.height)
        return {'center':[cx,cy],'radius':radius,'circle_bounds':list(box),
                'label_position':[tx,ty],'label_bounds':list(label_box),
                'circle_clipped':clipped,'font_size':26}

    def _region(self,d,plan,alpha=200):
        layout=self._region_layout(plan)
        box=layout['circle_bounds']
        d.ellipse(tuple(round(v*self.ss) for v in box),
                  outline=self.colors['map_accent']+(min(alpha,130),),width=2*self.ss)
        d.text(tuple(round(v*self.ss) for v in layout['label_position']),plan['region_label'],
               font=self._font(26),fill=self.colors['map_accent']+(alpha,),anchor='lt')

    def _layout_labels(self):
        """One immutable layout for every arrival, future route and region annotation."""
        renderer = self
        cfg = self.policy['labels']
        max_search_states = cfg['search_budget']
        unique_ids = list(dict.fromkeys(renderer.sequence))
        first_index = {key: renderer.sequence.index(key) for key in unique_ids}
        font_size = renderer.style['label_size']
        bold = renderer.style['label_bold']
        stroke = renderer.style['label_stroke_px']
        ss = renderer.ss
        font = renderer._font(font_size, bold)
        node_points = {key: renderer.pixel(node['lon'], node['lat'])
                       for key, node in renderer.nodes.items()}
        margin, label_gap, node_radius = cfg['panel_margin_px'], cfg['label_gap_px'], cfg['node_clearance_px']
        gaps = cfg['candidate_gaps_px']
        reserved = sorted(set(tuple(renderer._region_layout(plan)[field])
                              for plan in renderer.per_scene.values()
                              if plan.get('region_node_ids')
                              for field in ('circle_bounds', 'label_bounds')))
        route_edges = [(a, b) for curve in renderer.curves
                       for a, b in zip(curve, curve[1:]) if a != b]

        def overlaps(a, b, padding=label_gap):
            return (a[0] < b[2]+padding and a[2] > b[0]-padding
                    and a[1] < b[3]+padding and a[3] > b[1]-padding)

        def fail(details):
            raise ValueError(f'Cannot fit every visited place label at the locked {font_size}px '
                             f'font in the {renderer.width}x{renderer.height} map panel. '
                             'Use shorter unambiguous labels or separate regional itinerary views; '
                             'the engine will not hide labels, shrink text, or move geographic nodes. '
                             + details)

        candidates = {}
        for key in unique_ids:
            label = renderer.nodes[key]['label']
            x, y = node_points[key]
            bb = tuple(v/ss for v in font.getbbox(label, anchor='lt', stroke_width=stroke*ss))
            width, height = bb[2]-bb[0], bb[3]-bb[1]
            if width > renderer.width-2*margin or height > renderer.height-2*margin:
                fail(f'Label {key!r} ({label!r}) exceeds the bounded paint area.')
            seen = set()
            options = []
            for gap in gaps:
                for degrees in range(0, 360, cfg['candidate_angle_step_deg']):
                    angle = math.radians(degrees)
                    cx = x+math.cos(angle)*(width/2+gap)
                    cy = y+math.sin(angle)*(height/2+gap)
                    # Snap the text origin to the exact supersampled paint grid, then
                    # derive bounds from it: reported rectangles match drawn pixels.
                    tx = round((cx-width/2-bb[0])*ss)/ss
                    ty = round((cy-height/2-bb[1])*ss)/ss
                    bounds = (tx+bb[0], ty+bb[1], tx+bb[2], ty+bb[3])
                    if bounds in seen:
                        continue
                    seen.add(bounds)
                    if (bounds[0] < margin or bounds[1] < margin
                            or bounds[2] > renderer.width-margin
                            or bounds[3] > renderer.height-margin):
                        continue
                    if any(overlaps(bounds, obstacle) for obstacle in reserved):
                        continue
                    if any(overlaps(bounds, (nx-node_radius, ny-node_radius,
                                             nx+node_radius, ny+node_radius), 0)
                           for nx, ny in node_points.values()):
                        continue
                    nearest = (max(bounds[0], min(bounds[2], x)),
                               max(bounds[1], min(bounds[3], y)))
                    distance = math.dist((x, y), nearest)
                    expanded = (bounds[0]-2, bounds[2]+2, bounds[1]-2, bounds[3]+2)
                    intersections = sum(_clip_segment(a, b, expanded) is not None
                                        for a, b in route_edges)
                    options.append({'position': [tx, ty], 'bounds': list(bounds),
                                    'nearest': nearest, 'distance': distance,
                                    'route_intersections': intersections})
            candidates[key] = sorted(options, key=lambda item: (item['route_intersections'],
                                                                item['distance'], item['bounds']))
            if not candidates[key]:
                fail(f'No collision-free candidate for node {key!r} ({label!r}).')

        attempts = []
        def solve(allow_route_intersections):
            placed = {}
            states = 0
            def search(remaining):
                nonlocal states
                states += 1
                if states > max_search_states:
                    return False
                if not remaining:
                    return True
                choices = []
                for key in remaining:
                    valid = [candidate for candidate in candidates[key]
                             if (allow_route_intersections or candidate['route_intersections'] == 0)
                             and all(not overlaps(candidate['bounds'], old['bounds'])
                                     for old in placed.values())]
                    if not valid:
                        return False
                    choices.append((len(valid), first_index[key], key, valid))
                _, _, key, valid = min(choices)
                for candidate in valid:
                    placed[key] = candidate
                    if search([item for item in remaining if item != key]):
                        return True
                    if states > max_search_states:
                        break
                placed.pop(key, None)
                return False
            success = search(unique_ids)
            attempts.append({'allow_route_intersections': allow_route_intersections,
                             'search_states': states, 'success': success})
            return placed if success else None

        # First guarantee no text intersects any past OR FUTURE itinerary edge.
        # If that is geometrically infeasible within the bounded candidate set,
        # accept the fewest/shortest edge intersections per candidate; caller paints
        # labels last with the locked paper halo to retain their readability.
        chosen = solve(False)
        if chosen is None:
            chosen = solve(True)
        if chosen is None:
            fail(f'All bounded candidates exhausted (search limit {max_search_states}).')
        layouts = {}
        for key in unique_ids:
            candidate = chosen[key]
            x, y = node_points[key]
            near_x, near_y = candidate['nearest']
            length = candidate['distance']
            leader = []
            if length > 18:
                dx, dy = (near_x-x)/length, (near_y-y)/length
                leader = [[x+dx*node_radius, y+dy*node_radius],
                          [near_x-dx*2, near_y-dy*2]]
            layouts[key] = {'node_id': key, 'label': renderer.nodes[key]['label'],
                            'first_sequence_index': first_index[key],
                            'position': candidate['position'], 'bounds': candidate['bounds'],
                            'font_size': font_size, 'font_bold': bold, 'stroke_px': stroke,
                            'anchor': 'lt', 'node_pixel': [x, y],
                            'color_role': cfg['color_role'], 'alpha': cfg['alpha'],
                            'halo_alpha': cfg['halo_alpha'],
                            'leader': {'points':leader, 'width':cfg['leader_width'], 'alpha':cfg['leader_alpha']},
                            'leader_distance_px': length,
                            'route_intersections': candidate['route_intersections']}
        self._label_layout_audit = {'method': 'whole-route deterministic candidates with MRV backtracking',
                         'font_size': font_size, 'panel_margin_px': margin,
                         'label_gap_px': label_gap, 'node_clearance_px': node_radius,
                         'candidate_counts': {key: len(candidates[key]) for key in unique_ids},
                         'attempts': attempts,
                         'reserved_region_boxes': [list(box) for box in reserved],
                         'all_route_edges_considered': len(route_edges),
                         'route_intersections': sum(item['route_intersections'] for item in layouts.values())}

        return layouts

    def frame_state(self, scene_id, t, duration):
        """Chronological arrivals and route growth, independent of label placement."""
        if scene_id not in self.per_scene:
            raise KeyError(f'No map plan for scene {scene_id}')
        if not math.isfinite(t) or not math.isfinite(duration) or duration <= 0:
            raise ValueError('t must be finite; duration must be finite and positive')
        plan = self.per_scene[scene_id]
        start, end = plan['start_index'], plan['end_index']
        opening = scene_id == self.opening_scene_id
        intro = self._location_intro_sec(scene_id)
        if not opening and intro >= duration:
            raise ValueError(f'{scene_id}: location_intro_sec must be before the scene duration')
        growth_start = intro+self._motion['map_segment_delay']
        if opening:
            return {'current_index': None, 'visible_label_ids': [], 'visible_marker_ids': [],
                    'overview_preview': False, 'arrival_status': 'basemap_only',
                    'is_opening': True, 'base_only': True,
                    'location_intro_sec': intro, 'route_growth_start_sec': growth_start,
                    'region_active': False, 'region_only': False, 'route_segment_states': []}
        introduced = t >= intro
        current = start
        moving = [j for j in range(start, end) if j not in self._degenerate]
        active_window = min(self._motion['map_active_window_sec'], max(1., duration*.6))
        slot = active_window/max(1, len(moving))
        segments = []
        for j, path in enumerate(self.curves):
            if j >= end:
                break
            if j in self._degenerate:
                if j >= start and current >= j and introduced:
                    current = j+1
                continue
            if j < start:
                progress = 1.
            else:
                order = moving.index(j)
                progress = _ease((t-growth_start-order*slot)/(slot*.85))
            if progress > 0:
                count = max(2, min(len(path), round(1+progress*(len(path)-1))))
                segments.append({'index': j, 'progress': progress, 'points_count': count})
            if j >= start and progress >= .99:
                current = j+1
        if end == start:
            current = end
        if scene_id == self.first_location_scene_id and not introduced:
            current = None
        visible = [] if current is None else list(dict.fromkeys(self.sequence[:current+1]))
        region = introduced and bool(plan.get('region_node_ids')) and current == end
        base_only = not visible and not segments and not region
        return {'current_index': current,
                'visible_label_ids': visible, 'visible_marker_ids': list(visible), 'overview_preview': False,
                'arrival_status': 'awaiting_location_introduction' if base_only else 'cumulative_arrivals',
                'is_opening': False, 'base_only': base_only,
                'location_intro_sec': intro, 'route_growth_start_sec': growth_start,
                'region_active': region,
                'region_only': region and bool(plan.get('region_only', end == start)),
                'route_segment_states': segments}

    def _render_pixels(self, scene_id, t, duration):
        state = self.frame_state(scene_id, t, duration)
        plan = self.per_scene[scene_id]
        if state['base_only']:
            return self._native_basemap.copy()
        im = self._base_image.copy()
        d = ImageDraw.Draw(im)
        ink, accent = self.colors['map_ink'], self.colors['map_accent']
        for key in state['visible_marker_ids']:
            point = self.pixel(self.nodes[key]['lon'], self.nodes[key]['lat'])
            self._circle(d, *point, self.style['node_radius'], ink+(65,))
        stroke = self.policy['route_stroke']
        paths = [self.curves[row['index']][:row['points_count']]
                 for row in state['route_segment_states']]
        # All halos precede all foreground strokes, so a later halo cannot erase
        # an earlier leg at a crossing. Historical and growing legs use one ink.
        for path in paths:
            self._line(d, path, self.colors['map_halo']+(stroke['halo_alpha'],), stroke['halo_width'])
        for path in paths:
            self._line(d, path, accent+(stroke['alpha'],), stroke['width'])
        for row in state['route_segment_states']:
            if row['progress'] < 1:
                tip = self.curves[row['index']][row['points_count']-1]
                self._circle(d, *tip, self.style['growing_tip_radius'], accent+(stroke['alpha'],))
        if state['region_active']:
            self._region(d, plan)
        if state['current_index'] is not None and not state['region_only']:
            x,y = self.points[state['current_index']]
            self._circle(d,x,y,self.style['current_ring_radius'],outline=accent+(110,),width=1)
            self._circle(d,x,y,self.style['current_point_radius'],accent+(self.style['current_alpha'],))
        # Leaders precede every label. The final paper-colored outline protects
        # glyphs even when a dense itinerary requires a route-crossing fallback.
        labels = [self._label_layouts[key] for key in state['visible_label_ids']]
        for layout in labels:
            leader = layout['leader']
            if leader['points']:
                self._line(d, leader['points'], accent+(leader['alpha'],), leader['width'])
        for layout in labels:
            d.text(tuple(round(v*self.ss) for v in layout['position']), layout['label'],
                   font=self._font(self.style['label_size'], self.style['label_bold']),
                   fill=accent+(self.style['current_alpha'],),
                   stroke_width=self.style['label_stroke_px']*self.ss,
                   stroke_fill=self.colors['map_label_halo']+(self.style['label_halo_alpha'],), anchor='lt')
        return im.resize(self.size, Image.Resampling.LANCZOS)

    def _basemap_report(self):
        layers = {}
        for layer in ('coast', 'river'):
            runs = [item for item in self._basemap_runs if item['layer'] == layer]
            layers[layer] = {'visible_segments': len(runs),
                             'visible_edges': sum(len(r['points'])-1 for r in runs),
                             'visible_length_px': sum(math.dist(a,b) for r in runs
                                                      for a,b in zip(r['points'],r['points'][1:]))}
        return {'status': 'sourced geographic context', 'layers': layers,
                'visible_coast_segments': layers['coast']['visible_segments'],
                'visible_river_segments': layers['river']['visible_segments'],
                'visible_length_px': sum(item['visible_length_px'] for item in layers.values()),
                'source_fingerprint': _json_hash(self._sources), 'sources': deepcopy(self._sources),
                'geometry': deepcopy(self._basemap_runs),
                'ignored_geometries': deepcopy(self._ignored_geometries),
                'viewport_automatic': self._automatic_view,
                'viewport_expansions': self._viewport_expansions,
                'country_borders_drawn': False, 'coast_required_for_inland': False,
                'data_scope': 'modern generalized geographic context, not reconstructed historical geography'}

    def geometry_report(self):
        return deepcopy(self._geometry)

    def render(self, scene_id, t, duration):
        im = self._render_pixels(scene_id, t, duration)
        digest = hashlib.sha256(im.tobytes()).hexdigest()
        key = (self._geometry_sha256, self._render_spec_sha256, scene_id, float(t), float(duration))
        _remember(_PIXEL_HASHES, key, digest, 256)
        im.info[EVIDENCE_KEY] = {
            'schema_version': '2.2', 'engine_sha256': file_sha256(__file__),
            'engine_path': str(Path(__file__).resolve()), 'policy_sha256': file_sha256(POLICY_PATH),
            'style_sha256': file_sha256(STYLE_PATH), 'geometry_sha256': self._geometry_sha256,
            'scene_id': scene_id, 'time_sec': float(t), 'duration_sec': float(duration),
            'image_sha256': digest, 'map_size': list(im.size), 'image_mode': 'RGBA',
            'basemap': deepcopy({k:v for k,v in self._geometry['basemap'].items() if k != 'geometry'}),
            'readability': deepcopy(self._readability),
            'geometry': self._geometry, 'render_spec': self._render_spec,
            'render_spec_sha256': self._render_spec_sha256,
            'visible_label_ids': self.frame_state(scene_id, t, duration)['visible_label_ids'],
            'frame_state': self.frame_state(scene_id, t, duration),
            'label_layout_sha256': self._label_layout_sha256,
            'route_stroke_policy': deepcopy(self.policy['route_stroke']),
        }
        return im

    def _geometry_report(self):
        xmin=min(x for x,y in self.points);xmax=max(x for x,y in self.points)
        ymin=min(y for x,y in self.points);ymax=max(y for x,y in self.points)
        outside=[key for key,n in self.nodes.items() if not (
            self.bounds[0]<=n['lon']<=self.bounds[1] and self.bounds[2]<=n['lat']<=self.bounds[3])]
        return {
            'panel':{'x':self.position[0],'y':self.position[1],'width':self.width,'height':self.height,
                     'supersampling':self.ss,'plot_box':self.style['plot_box'],
                     'heading':False,'side_caption':False,'legend':False},
            'styles':deepcopy(self.style),'motion':{k:self._motion[k] for k in ('map_segment_delay','map_active_window_sec')},
            'projection':{'name':'local equirectangular','bounds':self.bounds,
                          'standard_parallel':self.lat0,'central_meridian':self.lon0,
                          'single_scale':self.scale,'scale_units':'pixels per projected degree',
                          'north_up':True,'node_extent_px':[xmin,ymin,xmax,ymax]},
            'nodes':[{'id':key,'label':n['label'],'lon':n['lon'],'lat':n['lat'],
                      'precision':n.get('precision',n.get('precision_note','not supplied')),
                      'source':n.get('source',n.get('coordinate_source_url',n.get('source_url'))),
                      'source_read_status':n.get('source_read_status',n.get('source_status','not supplied')),
                      'pixel':list(self.pixel(n['lon'],n['lat'])),
                      'frame_pixel':[self.position[0]+self.pixel(n['lon'],n['lat'])[0],
                                     self.position[1]+self.pixel(n['lon'],n['lat'])[1]]}
                     for key,n in self.nodes.items()],
            'sequence':list(self.sequence),'visits':deepcopy(self.visit_report),
            'label_layouts':deepcopy(self._label_layouts),
            'label_layout_sha256':self._label_layout_sha256,
            'label_layout_audit':deepcopy(self._label_layout_audit),
            'route_stroke_policy':deepcopy(self.policy['route_stroke']),
            'label_visibility_policy':deepcopy(self.policy['labels']),
            'per_scene':deepcopy(self.per_scene),'scene_order':list(self.scene_order),
            'opening_scene_id':self.opening_scene_id,
            'location_introduction_policy':deepcopy(self.policy['chronology']),
            'curve_samples_per_segment':91,
            'region_annotations':{sid:self._region_layout(plan) for sid,plan in self.per_scene.items()
                                  if plan.get('region_node_ids')},
            'same_place_segments_suppressed':list(self._degenerate),'nodes_outside_view':outside,
            'coastline':{'status':self._coast_status,'visible_runs':len(self._coast_runs),
                         'source':deepcopy(self.data.get('coastline',{}))},
            'font_paths':{str(k):str(v) for k,v in self._font_paths.items()},
            'static_files':[{'path':str(path),'sha256':file_sha256(path)}
                            for path in [STYLE_PATH, POLICY_PATH, *self._font_paths.values()]],
            'theme_id':self.theme.get('theme_id'),'theme_colors':deepcopy(self.colors),
            'requested_theme_colors':deepcopy(self.requested_colors),
            'basemap':self._basemap_report(), 'readability':deepcopy(self._readability),
            'policy':{'path':str(POLICY_PATH), 'sha256':file_sha256(POLICY_PATH), 'policy_id':self.policy['policy_id']},
            'precision_claim':'structural coordinates and supplied metadata only; not historical verification',
        }


def _evidence_renderer(evidence):
    key = evidence['geometry_sha256'], evidence['render_spec_sha256']
    renderer = _RENDERERS.get(key)
    if renderer is None:
        spec = evidence['render_spec']
        renderer = SeriesMap(spec['route_data'], STYLE_PATH, spec['theme'],
                             coastline_geojson=spec.get('coastline_source_path') or spec.get('coastline_geojson'),
                             basemap_geojson=spec.get('basemap_source_path') or spec.get('basemap_geojson'))
        if renderer._geometry_sha256 != key[0] or renderer._render_spec_sha256 != key[1]:
            raise ValueError('Map evidence geometry is not the official projection of its bound route and geographic sources')
    return renderer


def validate_map_evidence(evidence, scene_id=None, t=None, duration=None):
    """Validate an audit record and current sources; pixels require ensure_map_evidence.

    A renderer reconstructed from the bound inputs verifies geometry and all
    summaries. Reconstructed renderers and static file hashes are cached.
    """
    if not isinstance(evidence, dict) or evidence.get('schema_version') != '2.2':
        raise ValueError('Map requires SeriesMap 2.2 geographic evidence; render it with the current engine')
    required = ('engine_sha256', 'policy_sha256', 'style_sha256', 'geometry_sha256',
                'render_spec_sha256', 'scene_id', 'time_sec', 'duration_sec', 'image_sha256',
                'map_size', 'image_mode', 'basemap', 'readability', 'geometry', 'render_spec',
                'visible_label_ids', 'frame_state', 'label_layout_sha256', 'route_stroke_policy')
    if any(key not in evidence for key in required):
        raise ValueError('Incomplete map evidence: expected source, geometry, readability, scene and pixel bindings')
    for key, path in (('engine_sha256', __file__), ('policy_sha256', POLICY_PATH), ('style_sha256', STYLE_PATH)):
        if evidence[key] != file_sha256(path):
            raise ValueError(f'Stale map evidence: {key} differs from the current bundled file; regenerate map')
    if evidence['map_size'] != [880, 430] or evidence['image_mode'] != 'RGBA':
        raise ValueError('Map evidence does not match locked 880x430 RGBA geometry')
    for key in ('time_sec', 'duration_sec'):
        value = evidence[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError(f'Map evidence {key} must be finite numeric time')
    if evidence['duration_sec'] <= 0 or not isinstance(evidence['scene_id'], str):
        raise ValueError('Map evidence requires a scene and positive duration')
    for actual, expected, label in ((evidence['scene_id'], scene_id, 'scene'),
                                    (evidence['time_sec'], t, 'time'),
                                    (evidence['duration_sec'], duration, 'duration')):
        if expected is not None and actual != expected:
            raise ValueError(f'Map evidence {label} mismatch: expected {expected}, got {actual}')
    try:
        if _json_hash(evidence['geometry']) != evidence['geometry_sha256']:
            raise ValueError('Map geometry fingerprint mismatch')
        if _json_hash(evidence['render_spec']) != evidence['render_spec_sha256']:
            raise ValueError('Map render input fingerprint mismatch')
        geometry = evidence['geometry']
        basemap = geometry['basemap']
        if not isinstance(basemap, dict) or not isinstance(evidence['readability'], dict):
            raise ValueError('Map evidence must contain measured geographic and readability records')
        if evidence['basemap'] != {k:v for k,v in basemap.items() if k != 'geometry'}:
            raise ValueError('Map basemap summary is not bound to geometry')
        if evidence['readability'] != geometry['readability'] or geometry['readability']['passed'] is not True:
            raise ValueError('Map readability evidence is absent or failed')
        if (basemap['visible_length_px'] < _object(POLICY_PATH, 'map policy')['basemap']['minimum_visible_length_px']
                or not basemap['geometry'] or not basemap['sources']):
            raise ValueError('Map evidence contains no usable sourced geographic context')
        if basemap['source_fingerprint'] != _json_hash(basemap['sources']):
            raise ValueError('Map basemap source fingerprint mismatch')
        for source in basemap['sources']:
            if source['label'] == 'bundled Natural Earth':
                try:
                    from series_basemap import validate_default_basemap_fingerprint
                except ImportError:
                    from .series_basemap import validate_default_basemap_fingerprint
                if not validate_default_basemap_fingerprint(source['data_sha256']):
                    raise ValueError('Bundled basemap source changed; regenerate map')
            for record in source['source_files']:
                if file_sha256(record['path']) != record['sha256']:
                    raise ValueError(f'Map source checksum mismatch: {record["path"]}')
        for record in geometry['static_files']:
            if file_sha256(record['path']) != record['sha256']:
                raise ValueError(f'Map static file checksum mismatch: {record["path"]}')
        renderer = _evidence_renderer(evidence)
        if renderer._geometry != geometry:
            # JSON turns tuples into lists; canonical equality is the portable comparison.
            if _json_hash(renderer._geometry) != _json_hash(geometry):
                raise ValueError('Map report differs from its official renderer')
        if evidence['scene_id'] not in renderer.per_scene:
            raise ValueError('Map evidence references an unknown scene')
        official_state = renderer.frame_state(evidence['scene_id'], evidence['time_sec'], evidence['duration_sec'])
        if evidence['frame_state'] != official_state or evidence['visible_label_ids'] != official_state['visible_label_ids']:
            raise ValueError('Map visible labels or arrival state differ from the official route chronology')
        if evidence['label_layout_sha256'] != renderer._label_layout_sha256:
            raise ValueError('Map static label layout fingerprint differs from the official renderer')
        if evidence['route_stroke_policy'] != renderer.policy['route_stroke']:
            raise ValueError('Map route stroke policy differs from the uniform official stroke')
    except (KeyError, TypeError, FileNotFoundError) as exc:
        raise ValueError(f'Invalid map geographic evidence: {exc}') from exc
    return evidence


def ensure_map_evidence(image, scene_id=None, t=None, duration=None):
    """Bind actual pixels to the sourced renderer, geometry and exact scene time."""
    if not isinstance(image, Image.Image) or image.mode != 'RGBA':
        raise ValueError('Map must be the RGBA image returned by SeriesMap.render')
    evidence = validate_map_evidence(image.info.get(EVIDENCE_KEY), scene_id, t, duration)
    actual = hashlib.sha256(image.tobytes()).hexdigest()
    if list(image.size) != evidence['map_size'] or actual != evidence['image_sha256']:
        raise ValueError('Map pixels do not match their evidence; map was replaced, resized or edited')
    key = (evidence['geometry_sha256'], evidence['render_spec_sha256'], evidence['scene_id'],
           float(evidence['time_sec']), float(evidence['duration_sec']))
    expected = _PIXEL_HASHES.get(key)
    if expected is None:
        renderer = _evidence_renderer(evidence)
        official = renderer._render_pixels(evidence['scene_id'], evidence['time_sec'], evidence['duration_sec'])
        expected = hashlib.sha256(official.tobytes()).hexdigest()
        _remember(_PIXEL_HASHES, key, expected, 256)
    if actual != expected:
        raise ValueError('Map pixels differ from the official sourced renderer for this geometry and scene time')
    return evidence


def attach_map_evidence(image, evidence):
    """Attach externally preserved evidence, then verify actual RGBA pixels."""
    if isinstance(evidence, (str, Path)):
        evidence = json.loads(Path(evidence).read_text(encoding='utf-8'))
    image.info[EVIDENCE_KEY] = deepcopy(evidence)
    ensure_map_evidence(image)
    return image


def save_map_png(image, path):
    evidence = ensure_map_evidence(image)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = PngImagePlugin.PngInfo()
    text = json.dumps(evidence, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    metadata.add_itxt(EVIDENCE_KEY, text, zip=True)
    image.save(path, pnginfo=metadata)
    Path(str(path)+'.evidence.json').write_text(text+'\n', encoding='utf-8')
    return path


def load_map_png(path):
    path = Path(path)
    with Image.open(path) as source:
        embedded = source.info.get(EVIDENCE_KEY)
        image = source.convert('RGBA')
    sidecar = Path(str(path)+'.evidence.json')
    evidence = json.loads(embedded) if isinstance(embedded, str) else None
    if sidecar.is_file():
        separate = json.loads(sidecar.read_text(encoding='utf-8'))
        if evidence is not None and evidence != separate:
            raise ValueError('Embedded map evidence and sidecar differ')
        evidence = separate
    return attach_map_evidence(image, evidence)


def validate_map_background(map_image, background_image):
    """Measure native geographic/route/text stroke cores on the actual art crop.

    Returns a report with passed/status. The caller must reject a failed report.
    The crop is the opaque, already composited 880x430 art under the map.
    Edge antialias pixels are excluded; map dimensions and placement stay fixed.
    """
    import numpy as np
    evidence = ensure_map_evidence(map_image)
    if not isinstance(background_image, Image.Image) or background_image.size != map_image.size:
        raise ValueError('Actual map background must be the composited 880x430 art crop')
    if background_image.mode == 'RGBA' and background_image.getextrema()[3] != (255,255):
        raise ValueError('Actual map background must be composited to opaque paper before readability checks')
    background = background_image.convert('RGB')
    bg = np.asarray(background, dtype=np.float64)
    fg = np.asarray(map_image, dtype=np.float64)
    renderer = _evidence_renderer(evidence)
    base = renderer._native_basemap
    base_alpha = np.asarray(base, dtype=np.uint8)[...,3]
    composite = (fg[...,:3]*fg[...,3:4]+bg*(255-fg[...,3:4]))/255
    def luminance(rgb):
        values = rgb/255
        linear = np.where(values <= .04045, values/12.92, ((values+.055)/1.055)**2.4)
        return linear @ np.array([.2126,.7152,.0722])
    back_lum, comp_lum = luminance(bg), luminance(composite)
    ratios = (np.maximum(back_lum,comp_lum)+.05)/(np.minimum(back_lum,comp_lum)+.05)
    accent = np.array(renderer.colors['map_accent'])
    accent_core = np.max(np.abs(fg[...,:3]-accent), axis=2) <= 8
    masks = [('geographic_context', base_alpha >= 100, 1.20),
             ('route', accent_core & (fg[...,3] >= 160), 1.8),
             ('current_label', accent_core & (fg[...,3] >= 230), 3.0)]
    checks = []
    for label, mask, minimum in masks:
        samples = ratios[mask]
        count = int(samples.size)
        fraction = float(np.mean(samples >= minimum)) if count else None
        passed = (count > 0 and fraction >= .9) if label == 'geographic_context' else (not count or fraction >= .9)
        checks.append({'purpose': label, 'sample_pixels': count, 'minimum_contrast': minimum,
                       'required_passing_fraction': .9, 'passing_fraction': fraction,
                       'measured_contrast_p10': float(np.percentile(samples,10)) if count else None,
                       'passed': bool(passed)})
    passed = all(c['passed'] for c in checks)
    return {'schema_version': '2.2', 'status': 'passed' if passed else 'failed', 'passed': passed,
            'method': 'WCAG native stroke-core pixel contrast over actual composited art crop',
            'background_sha256': hashlib.sha256(background.tobytes()).hexdigest(),
            'background_size': list(background.size), 'background_mode': 'RGB',
            'map_image_sha256': evidence['image_sha256'], 'engine_sha256': evidence['engine_sha256'],
            'geometry_sha256': evidence['geometry_sha256'], 'checks': checks}
