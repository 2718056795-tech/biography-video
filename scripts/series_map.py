#!/usr/bin/env python3
"""Data-driven cumulative maps in the locked biography-series panel.

No person-specific names, scene IDs, geographic bounds, downloads, or system-font
fallbacks are embedded here. Geometry/timing styles come from series_style.json;
routes, geographic view, region annotations, and palette come from the project.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Mapping

from PIL import Image, ImageColor, ImageDraw, ImageFont

SERIES_ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'series'
STYLE_PATH = SERIES_ASSETS / 'series_style.json'


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

    def __init__(self, route_data, style, theme, coastline_geojson=None):
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
        for sid, plan in self.per_scene.items():
            a, b = plan.get('start_index'), plan.get('end_index')
            if type(a) is not int or type(b) is not int or not 0 <= a <= b < len(self.sequence):
                raise ValueError(f'{sid}: invalid start_index/end_index')
            region = plan.get('region_node_ids', [])
            if any(key not in self.nodes for key in region):
                raise ValueError(f'{sid}: unknown region node ID')
            if region and not plan.get('region_label'):
                raise ValueError(f'{sid}: region_node_ids requires a region_label')

        projection = self.data.get('projection', {})
        bounds = projection.get('bounds', projection.get('bounds_west_east_south_north'))
        if bounds is None:
            lons = [n['lon'] for n in self.nodes.values()]
            lats = [n['lat'] for n in self.nodes.values()]
            if max(lons) - min(lons) > 180:
                raise ValueError('Auto bounds crossing the antimeridian need separate regional views')
            lon_pad = max(.5, (max(lons)-min(lons))*.12)
            lat_pad = max(.5, (max(lats)-min(lats))*.12)
            bounds = [max(-180,min(lons)-lon_pad), min(180,max(lons)+lon_pad),
                      max(-85,min(lats)-lat_pad), min(85,max(lats)+lat_pad)]
        if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
            raise ValueError('bounds must be [west,east,south,north] finite numbers')
        self.bounds = tuple(map(float, bounds))
        west, east, south, north = self.bounds
        if not -180 <= west < east <= 180 or not -85 <= south < north <= 85:
            raise ValueError('Invalid or unsupported geographic bounds')
        self.lat0 = float(projection.get('standard_parallel', (south+north)/2))
        self.lon0 = float(projection.get('central_meridian', (west+east)/2))
        if not math.isfinite(self.lat0) or not -85 <= self.lat0 <= 85 or not math.isfinite(self.lon0):
            raise ValueError('Invalid projection center')
        self.x0, self.y0 = self._project(west,south)
        x1, y1 = self._project(east,north)
        left, top, right, bottom = self.style['plot_box']
        self.scale = min((right-left)/(x1-self.x0), (bottom-top)/(y1-self.y0))
        self.ox = (left+right-(x1-self.x0)*self.scale)/2
        self.oy = (top+bottom-(y1-self.y0)*self.scale)/2
        self.y1 = y1
        self.points = [self.pixel(self.nodes[key]['lon'], self.nodes[key]['lat']) for key in self.sequence]
        self.curves = [self._curve(i) for i in range(len(self.points)-1)]
        self._degenerate = [i for i,p in enumerate(self.curves) if math.dist(p[0],p[-1]) < .001]
        self._coast_runs = []
        self._coast_status = 'not supplied; no coastline drawn'
        if coastline_geojson is not None:
            self._read_coast(_object(coastline_geojson, 'coastline_geojson'), projection)
        self._base_image = self._make_base()

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

    def _read_coast(self,raw,projection):
        cfg=self.data.get('coastline', {})
        coast_filter=cfg.get('filter_bounds',projection.get('coast_filter_bounds'))
        if coast_filter is not None and (len(coast_filter)!=4 or
                not all(math.isfinite(v) for v in coast_filter)):
            raise ValueError('coast filter_bounds must be [west,east,south,north]')
        features=raw.get('features',[raw])
        skipped_polygon=False
        for feature in features:
            g=feature.get('geometry',feature)
            typ=g.get('type')
            if typ in ('Polygon','MultiPolygon'):
                if coast_filter is None:
                    skipped_polygon=True
                    continue  # country polygons are not automatically coastlines
                polygons=g['coordinates'] if typ=='MultiPolygon' else [g['coordinates']]
                rings=[p[0] for p in polygons]
            elif typ in ('LineString','MultiLineString'):
                rings=[g['coordinates']] if typ=='LineString' else g['coordinates']
            else:
                raise ValueError(f'Unsupported coastline geometry {typ}')
            for ring in rings:
                run=[]
                for coord in ring:
                    lon,lat=coord[:2]
                    west,east,south,north=self.bounds
                    valid=west<=lon<=east and south<=lat<=north
                    if coast_filter is not None:
                        a,b,c,e=coast_filter
                        valid=valid and a<=lon<=b and c<=lat<=e
                    if valid:
                        run.append(self.pixel(lon,lat))
                    else:
                        if len(run)>1:self._coast_runs.append(run)
                        run=[]
                if len(run)>1:self._coast_runs.append(run)
        self._coast_status = ('local supplied geographic lines; ' +
            f'{len(self._coast_runs)} visible continuous runs; no fabricated substitute')
        if skipped_polygon:self._coast_status += '; polygon skipped without explicit coastal filter'

    def _make_base(self):
        im=Image.new('RGBA',(self.width*self.ss,self.height*self.ss),(0,0,0,0))
        d=ImageDraw.Draw(im)
        for run in self._coast_runs:
            self._line(d,run,self.colors['map_coast']+(self.style['coast_alpha'],),self.style['coast_width'])
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

    def render(self,scene_id,t,duration):
        if scene_id not in self.per_scene:
            raise KeyError(f'No map plan for scene {scene_id}')
        if not math.isfinite(t) or not math.isfinite(duration) or duration<=0:
            raise ValueError('t must be finite; duration must be finite and positive')
        plan=self.per_scene[scene_id];start,end=plan['start_index'],plan['end_index']
        im=self._base_image.copy();d=ImageDraw.Draw(im)
        ink=self.colors['map_ink'];accent=self.colors['map_accent']
        for i,key in enumerate(self.sequence):
            self._circle(d,*self.points[i],self.style['node_radius'],ink+(30 if i>end else 65,))
        current=start
        moving=[j for j in range(start,end) if j not in self._degenerate]
        active_window=min(self._motion['map_active_window_sec'],max(1.,duration*.6))
        slot=active_window/max(1,len(moving))
        for j,path in enumerate(self.curves):
            if j>=end:break
            if j in self._degenerate:
                if j>=start and current>=j:current=j+1
                continue
            if j<start:
                progress=1.;age=end-j
                alpha=max(self.style['old_line_alpha_min'],135-age*4)
                self._line(d,path,accent+(alpha,),self.style['old_line_width'])
            else:
                order=moving.index(j)
                progress=_ease((t-self._motion['map_segment_delay']-order*slot)/(slot*.85))
                if progress>0:
                    n=max(2,min(len(path),round(1+progress*(len(path)-1))))
                    alpha=210 if progress<1 else 165
                    self._line(d,path[:n],self.colors['map_halo']+(64,),self.style['new_line_halo_width'])
                    self._line(d,path[:n],accent+(alpha,),self.style['new_line_width'])
                    self._circle(d,*path[n-1],self.style['growing_tip_radius'],accent+(220,))
            if progress>=.99:current=j+1
        if end==start:current=end
        region=bool(plan.get('region_node_ids')) and current==end
        if plan.get('overview',False):
            for path in self.curves:self._line(d,path,accent+(32,),.85)
        elif region and (plan.get('region_only',end==start)):
            self._region(d,plan)
        else:
            x,y=self.points[current]
            self._circle(d,x,y,self.style['current_ring_radius'],outline=accent+(110,),width=1)
            self._circle(d,x,y,self.style['current_point_radius'],accent+(self.style['current_alpha'],))
            if region:self._region(d,plan)
            else:
                name=self.nodes[self.sequence[current]]['label']
                tx=x+13;ty=y-22
                width=self._font(self.style['label_size']).getlength(name)/self.ss
                if tx+width>self.width-6:tx=x-width-12
                ty=max(4,min(self.height-54,ty))
                d.text((round(tx*self.ss),round(ty*self.ss)),name,
                    font=self._font(self.style['label_size'],self.style['label_bold']),
                    fill=accent+(self.style['current_alpha'],),
                    stroke_width=self.style['label_stroke_px']*self.ss,
                    stroke_fill=self.colors['map_label_halo']+(155,),anchor='lt')
        return im.resize(self.size,Image.Resampling.LANCZOS)

    def geometry_report(self):
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
            'per_scene':deepcopy(self.per_scene),'curve_samples_per_segment':91,
            'region_annotations':{sid:self._region_layout(plan) for sid,plan in self.per_scene.items()
                                  if plan.get('region_node_ids')},
            'same_place_segments_suppressed':list(self._degenerate),'nodes_outside_view':outside,
            'coastline':{'status':self._coast_status,'visible_runs':len(self._coast_runs),
                         'source':deepcopy(self.data.get('coastline',{}))},
            'font_paths':{str(k):str(v) for k,v in self._font_paths.items()},
            'theme_id':self.theme.get('theme_id'),'theme_colors':deepcopy(self.colors),
            'precision_claim':'structural coordinates and supplied metadata only; not historical verification',
        }
