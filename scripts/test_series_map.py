#!/usr/bin/env python3
"""Geographic regression checks: no invented context and pixel-bound evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import series_map as maps
from series_map import SeriesMap, ensure_map_evidence, validate_map_background


ASSETS = maps.SERIES_ASSETS


def route(points=((108.93,34.26),(109.32,34.15)), bounds=None):
    result = {'nodes':[{'id':str(i),'label':label,'lon':lon,'lat':lat}
                       for i,((lon,lat),label) in enumerate(zip(points,('长安','蓝田','再访')))],
              'sequence':[str(i) for i in range(len(points))],
              'per_scene':{'travel':{'start_index':0,'end_index':len(points)-1},
                           'stay':{'start_index':len(points)-1,'end_index':len(points)-1},
                           'overview':{'start_index':0,'end_index':0,'overview':True}}}
    if bounds is not None:
        result['projection'] = {'bounds':bounds}
    return result


def fixture(lines, layer='river'):
    return {'type':'FeatureCollection',
            'provenance':{'source_url':'https://example.org/map-test-fixture','license':'test fixture'},
            'features':[{'type':'Feature','properties':{'layer':layer},
                         'geometry':{'type':'LineString','coordinates':line}} for line in lines]}


class GeographicMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.theme = json.loads((ASSETS/'themes/dufu.json').read_text())
        cls.inland = SeriesMap(route(), maps.STYLE_PATH, cls.theme)

    def test_sparse_inland_has_real_rivers_without_forced_coast(self):
        report = self.inland.geometry_report()
        self.assertEqual(report['basemap']['visible_coast_segments'],0)
        self.assertGreater(report['basemap']['visible_river_segments'],0)
        self.assertTrue(any('wei' in str(run['name']).lower() for run in report['basemap']['geometry']))
        self.assertAlmostEqual(self.inland.bounds[1]-self.inland.bounds[0],8)
        self.assertAlmostEqual(self.inland.bounds[3]-self.inland.bounds[2],5)
        self.assertFalse(report['nodes_outside_view'])
        self.assertEqual(report['projection']['single_scale'],self.inland.scale)
        for node in report['nodes']:
            self.assertEqual(node['pixel'],list(self.inland.pixel(node['lon'],node['lat'])))

    def test_foreign_view_uses_local_sourced_geography(self):
        renderer = SeriesMap(route(((-.12,51.5),(.12,52.2))), maps.STYLE_PATH, self.theme)
        report = renderer.geometry_report()
        self.assertGreater(report['basemap']['visible_river_segments'],0)
        self.assertGreater(report['basemap']['visible_coast_segments'],0)
        self.assertLess(renderer.bounds[1],10)
        self.assertTrue(ensure_map_evidence(renderer.render('travel',3,6))['readability']['passed'])

    def test_revisit_and_same_place_hold_keep_real_chronology(self):
        data = route()
        del data['sequence']; del data['per_scene']
        data['visits'] = [{'id':str(i),'node_id':node,'scene_id':scene}
                         for i,(node,scene) in enumerate([('0','A'),('1','B'),('1','C'),('0','D')])]
        renderer = SeriesMap(data,maps.STYLE_PATH,self.theme)
        self.assertEqual(renderer.sequence,['0','1','0'])
        self.assertEqual(renderer.per_scene['C'],{'start_index':1,'end_index':1})
        self.assertEqual(renderer.per_scene['D'],{'start_index':1,'end_index':2})
        self.assertEqual(renderer.points[0],renderer.points[-1])
        self.assertNotEqual(renderer.render('D',0,6).tobytes(),renderer.render('D',5,6).tobytes())
        self.assertEqual(renderer.render('C',0,6).tobytes(),renderer.render('C',5,6).tobytes())

    def test_segment_clipping_keeps_crossings_and_splits_excursions(self):
        self.assertEqual(list(maps._clip_runs([(-2,0),(2,0)],(-1,1,-1,1))),
                         [[(-1.,0.),(1.,0.)]])
        runs = list(maps._clip_runs([(0,0),(2,0),(2,.5),(0,.5)],(-1,1,-1,1)))
        self.assertEqual(len(runs),2)
        self.assertEqual(runs[0][-1],(1.,0.))
        self.assertEqual(runs[1][0],(1.,.5))
        self.assertFalse(list(maps._clip_runs([(179,0),(-179,0)],(-180,180,-1,1))))

    def test_missing_and_contextless_data_are_actionable_failures(self):
        with patch('series_basemap.load_default_basemap',side_effect=FileNotFoundError('missing')):
            with self.assertRaisesRegex(ValueError,'Reinstall.*geography'):
                SeriesMap(route(),maps.STYLE_PATH,self.theme)
        with self.assertRaisesRegex(ValueError,'Widen projection.bounds'):
            SeriesMap(route(bounds=[108.9,109.4,34.1,34.3]),maps.STYLE_PATH,self.theme,
                      basemap_geojson=fixture([[(0,0),(1,1)]]))
        with self.assertRaisesRegex(ValueError,'routes alone'):
            SeriesMap(route(),maps.STYLE_PATH,self.theme,basemap_geojson=fixture([]))

    def test_country_ring_does_not_turn_into_coast(self):
        polygon = {'type':'FeatureCollection','features':[{'type':'Feature','properties':{},
                   'geometry':{'type':'Polygon','coordinates':[[[105,32],[112,32],[112,36],[105,32]]]}}]}
        renderer = SeriesMap(route(),maps.STYLE_PATH,self.theme,coastline_geojson=polygon)
        self.assertEqual(renderer.geometry_report()['basemap']['visible_coast_segments'],0)
        self.assertEqual(len(renderer.geometry_report()['basemap']['ignored_geometries']),1)
        with self.assertRaisesRegex(ValueError,'Country polygons'):
            SeriesMap(route(),maps.STYLE_PATH,self.theme,basemap_geojson=polygon)

    def test_custom_geography_requires_documented_source(self):
        data = fixture([[(105,34),(112,34)]])
        del data['provenance']
        with self.assertRaisesRegex(ValueError,'provenance.source_url'):
            SeriesMap(route(),maps.STYLE_PATH,self.theme,basemap_geojson=data)

    def test_pale_map_palette_is_adapted_without_changing_theme(self):
        theme = deepcopy(self.theme)
        for role in ('map_ink','map_accent','map_coast'):
            theme['colors'][role] = theme['colors']['paper']
        original = deepcopy(theme)
        renderer = SeriesMap(route(),maps.STYLE_PATH,theme)
        readability = renderer.geometry_report()['readability']
        self.assertTrue(readability['passed'])
        self.assertTrue(all(r['adapted'] for r in readability['roles'].values()))
        self.assertEqual(theme,original)
        for role, record in readability['roles'].items():
            for check in record['checks']:
                self.assertGreaterEqual(check['effective_contrast'],check['minimum_contrast'])
                self.assertEqual(check['requested_contrast'],1)

    def test_pixel_geometry_time_and_png_bindings(self):
        image = self.inland.render('travel',3,6)
        evidence = deepcopy(ensure_map_evidence(image,'travel',3,6))
        with self.assertRaisesRegex(ValueError,'time mismatch'):
            ensure_map_evidence(image,t=2)
        image.putpixel((20,20),(255,0,0,255))
        with self.assertRaisesRegex(ValueError,'pixels do not match'):
            ensure_map_evidence(image)
        blank = Image.new('RGBA',(880,430))
        evidence['image_sha256'] = hashlib.sha256(blank.tobytes()).hexdigest()
        blank.info[maps.EVIDENCE_KEY] = evidence
        with self.assertRaisesRegex(ValueError,'official sourced renderer'):
            ensure_map_evidence(blank)
        image = self.inland.render('travel',3,6)
        with tempfile.TemporaryDirectory() as directory:
            path = maps.save_map_png(image,Path(directory)/'map.png')
            maps._RENDERERS.clear(); maps._PIXEL_HASHES.clear()
            restored = maps.load_map_png(path)
            self.assertEqual(restored.tobytes(),image.tobytes())
            sidecar = Path(str(path)+'.evidence.json')
            payload = json.loads(sidecar.read_text());payload['scene_id']='stay'
            sidecar.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError,'sidecar differ'):
                maps.load_map_png(path)

    def test_actual_paper_readability_and_ink_background_rejection(self):
        image = self.inland.render('travel',3,6)
        paper = Image.new('RGB',image.size,self.inland.colors['paper'])
        self.assertTrue(validate_map_background(image,paper)['passed'])
        same_ink = Image.new('RGB',image.size,self.inland.colors['map_coast'])
        self.assertFalse(validate_map_background(image,same_ink)['passed'])


if __name__ == '__main__':
    unittest.main()
