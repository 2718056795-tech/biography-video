#!/usr/bin/env python3
"""Geographic regression checks: no invented context and pixel-bound evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

import series_map as maps
from series_map import SeriesMap, ensure_map_evidence, validate_map_background


ASSETS = maps.SERIES_ASSETS


def route(points=((108.93,34.26),(109.32,34.15)), bounds=None):
    result = {'nodes':[{'id':str(i),'label':label,'lon':lon,'lat':lat}
                       for i,((lon,lat),label) in enumerate(zip(points,('长安','蓝田','再访')))],
              'sequence':[str(i) for i in range(len(points))],
              'per_scene':{'opening':{'start_index':0,'end_index':0},
                           'travel':{'start_index':0,'end_index':len(points)-1},
                           'stay':{'start_index':len(points)-1,'end_index':len(points)-1}}}
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


class PersistentLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = SeriesMap(ASSETS/'examples/dufu-project/data/life_route.json',
                                 maps.STYLE_PATH, ASSETS/'themes/dufu.json')

    def test_arrivals_persist_across_chapters_without_future_names(self):
        renderer = self.renderer
        expected = [('S02',0,[]), ('S02',.3,['gong']), ('S02',3.5,['gong','wuyue']),
                    ('S02',8,['gong','wuyue','qilu']),
                    ('S03',0,['gong','wuyue','qilu']),
                    ('S03',8,['gong','wuyue','qilu','changan'])]
        for scene, time, names in expected:
            with self.subTest(scene=scene,time=time):
                image = renderer.render(scene,time,9)
                evidence = ensure_map_evidence(image,scene,time,9)
                self.assertEqual(evidence['visible_label_ids'],names)
                self.assertEqual(evidence['frame_state']['visible_label_ids'],names)
        self.assertEqual(renderer.frame_state('S01',5,7)['visible_label_ids'],[])

    def test_revisits_do_not_duplicate_labels_and_region_only_keeps_past(self):
        renderer = self.renderer
        before = renderer.frame_state('S04',9,10)['visible_label_ids']
        after = renderer.frame_state('S05',9,10)['visible_label_ids']
        self.assertEqual(before,after)  # Revisit Chang'an.
        final = renderer.frame_state('S12',4,8)
        self.assertTrue(final['region_only'])
        self.assertEqual(final['visible_label_ids'],list(dict.fromkeys(renderer.sequence)))
        self.assertEqual(len(final['visible_label_ids']),15)
        self.assertTrue(ensure_map_evidence(renderer.render('S12',4,8))['frame_state']['region_only'])

    def test_layout_is_static_with_fixed_font_and_true_geographic_nodes(self):
        renderer = self.renderer
        original = renderer.geometry_report()['label_layouts']
        fingerprint = renderer._label_layout_sha256
        with patch.object(renderer,'_layout_labels',side_effect=AssertionError('layout must be computed once')):
            for scene,time in [('S02',0),('S02',8),('S03',8),('S12',4)]:
                image = renderer.render(scene,time,9)
                self.assertEqual(image.info[maps.EVIDENCE_KEY]['label_layout_sha256'],fingerprint)
                self.assertEqual(image.info[maps.EVIDENCE_KEY]['geometry']['label_layouts'],original)
        for key, layout in original.items():
            self.assertEqual(layout['node_pixel'],list(renderer.pixel(renderer.nodes[key]['lon'],renderer.nodes[key]['lat'])))
            self.assertEqual((layout['font_size'],layout['font_bold'],layout['alpha']),(28,True,245))

    def test_dense_dufu_labels_avoid_each_other_regions_and_all_future_routes(self):
        renderer = self.renderer
        report = renderer.geometry_report()
        layouts = list(report['label_layouts'].values())
        self.assertEqual(len(layouts),15)
        self.assertEqual(report['label_layout_audit']['route_intersections'],0)
        self.assertEqual(report['label_layout_audit']['all_route_edges_considered'],1440)
        def overlap(a,b,gap=0):
            return a[0]<b[2]+gap and a[2]>b[0]-gap and a[1]<b[3]+gap and a[3]>b[1]-gap
        for i, layout in enumerate(layouts):
            box = layout['bounds']
            self.assertTrue(4<=box[0]<box[2]<=876 and 4<=box[1]<box[3]<=426)
            for other in layouts[i+1:]:
                self.assertFalse(overlap(box,other['bounds'],3))
            for region in report['label_layout_audit']['reserved_region_boxes']:
                self.assertFalse(overlap(box,region,3))
            for path in renderer.curves:
                for a,b in zip(path,path[1:]):
                    self.assertIsNone(maps._clip_segment(a,b,(box[0]-2,box[2]+2,box[1]-2,box[3]+2)))

    def test_old_completed_and_growing_routes_use_one_stroke(self):
        renderer = self.renderer
        policy = renderer.geometry_report()['route_stroke_policy']
        self.assertEqual(policy,{'width':2.1,'alpha':210,'halo_width':4.5,'halo_alpha':64,
                                 'all_segments_same':True,'aging':False})
        self.assertEqual(renderer.style['old_line_width'],renderer.style['new_line_width'])
        for scene,time in [('S06',1.2),('S06',8),('S01',0)]:
            with patch.object(renderer,'_line',wraps=renderer._line) as lines:
                renderer.render(scene,time,9)
            route_calls = [call.args for call in lines.call_args_list if call.args[3]==2.1]
            halo_calls = [call.args for call in lines.call_args_list if call.args[3]==4.5]
            expected_count = len(renderer.frame_state(scene,time,9)['route_segment_states'])
            self.assertEqual(len(route_calls),expected_count)
            self.assertEqual(len(halo_calls),expected_count)
            self.assertTrue(all(args[2]==renderer.colors['map_accent']+(210,) for args in route_calls))
            self.assertTrue(all(args[2]==renderer.colors['map_halo']+(64,) for args in halo_calls))

    def test_label_paint_is_above_routes_with_fixed_paper_halo(self):
        renderer = self.renderer
        events, text_calls = [], []
        original_line, original_text = renderer._line, ImageDraw.ImageDraw.text
        def line(*args,**kwargs):
            events.append('line')
            return original_line(*args,**kwargs)
        def text(draw,*args,**kwargs):
            events.append('text'); text_calls.append(kwargs)
            return original_text(draw,*args,**kwargs)
        # Region-free S06 contains old and currently growing legs. Every glyph
        # is painted after both route strokes and leader lines, protecting text
        # even if the bounded layout must use a route-intersection fallback.
        with patch.object(renderer,'_line',side_effect=line), patch.object(ImageDraw.ImageDraw,'text',new=text):
            renderer.render('S06',8,9)
        first_text = events.index('text')
        self.assertTrue(all(event=='text' for event in events[first_text:]))
        self.assertTrue(all(call['stroke_fill']==renderer.colors['map_label_halo']+(245,) for call in text_calls))
        self.assertTrue(all(call['stroke_width']==4 for call in text_calls))

    def test_impossible_label_fit_is_an_actionable_refusal(self):
        data = route()
        data['nodes'][0]['label']='超出地图容量的地名'*40
        with self.assertRaisesRegex(ValueError,'will not hide labels, shrink text, or move geographic nodes'):
            SeriesMap(data,maps.STYLE_PATH,ASSETS/'themes/dufu.json')

    def test_label_outline_uses_paper_even_if_custom_halo_was_requested(self):
        theme = json.loads((ASSETS/'themes/dufu.json').read_text())
        theme['colors']['map_label_halo']='#ff0000'
        renderer = SeriesMap(route(),maps.STYLE_PATH,theme)
        self.assertEqual(renderer.colors['map_label_halo'],renderer.colors['paper'])
        self.assertEqual(renderer.geometry_report()['readability']['label_halo']['requested'],[255,0,0])
        self.assertEqual(theme['colors']['map_label_halo'],'#ff0000')

    def test_forged_visible_labels_and_stroke_policy_are_rejected(self):
        renderer = self.renderer
        for key,value in [('visible_label_ids',['gong','wuyue']),
                          ('label_layout_sha256','0'*64),
                          ('route_stroke_policy',{'width':1.3,'alpha':70})]:
            image = renderer.render('S02',.3,9)
            image.info[maps.EVIDENCE_KEY] = deepcopy(image.info[maps.EVIDENCE_KEY])
            image.info[maps.EVIDENCE_KEY][key] = value
            with self.assertRaises(ValueError,msg=key):
                ensure_map_evidence(image)


class OpeningChronologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = SeriesMap(ASSETS/'examples/dufu-project/data/life_route.json',
                                 maps.STYLE_PATH, ASSETS/'themes/dufu.json')
        cls.theme = ASSETS/'themes/dufu.json'

    def test_every_opening_native_frame_is_exact_sourced_basemap(self):
        renderer = self.renderer
        duration, fps, count = 205/30, 30, 205
        baseline = renderer._native_basemap.tobytes()
        self.assertGreater(renderer.geometry_report()['basemap']['visible_length_px'],24)
        with patch.object(renderer,'_line',side_effect=AssertionError('no opening itinerary lines')), \
                patch.object(renderer,'_circle',side_effect=AssertionError('no opening place markers')), \
                patch.object(ImageDraw.ImageDraw,'text',side_effect=AssertionError('no opening place names')):
            for frame in range(count):
                t = frame/fps
                image = renderer.render('S01',t,duration)
                state = ensure_map_evidence(image,'S01',t,duration)['frame_state']
                self.assertTrue(state['is_opening'])
                self.assertTrue(state['base_only'])
                self.assertIsNone(state['current_index'])
                self.assertEqual(state['route_segment_states'],[])
                self.assertEqual(state['visible_label_ids'],[])
                self.assertEqual(state['visible_marker_ids'],[])
                self.assertFalse(state['region_active'])
                self.assertFalse(state['overview_preview'])
                self.assertEqual(image.tobytes(),baseline)

    def test_opening_is_generic_ordered_and_legacy_flags_cannot_preview(self):
        data = route(((108.93,34.26),(109.32,34.15),(110.2,34.4)))
        opening = data['per_scene'].pop('opening')
        data['per_scene']['prologue'] = {**opening,'overview':True}
        data['per_scene']['travel'].update(end_index=1,overview=True)
        data['per_scene']['stay'].update(start_index=1)
        data['scene_order'] = ['prologue','travel','stay']
        renderer = SeriesMap(data,maps.STYLE_PATH,self.theme)
        for t in (0,.3,3,6,60):
            self.assertEqual(renderer.render('prologue',t,6).tobytes(),renderer._native_basemap.tobytes())
            state = renderer.frame_state('travel',t,6)
            self.assertFalse(state['overview_preview'])
            self.assertTrue(all(row['index']==0 for row in state['route_segment_states']))
            self.assertNotIn('2',state['visible_label_ids'])
            self.assertNotIn('2',state['visible_marker_ids'])

    def test_first_location_and_route_wait_for_the_introduction_cue(self):
        renderer = self.renderer
        for t in (0,.299):
            image = renderer.render('S02',t,9)
            evidence = ensure_map_evidence(image)
            self.assertEqual(image.tobytes(),renderer._native_basemap.tobytes())
            self.assertEqual(evidence['visible_label_ids'],[])
            self.assertEqual(evidence['frame_state']['visible_marker_ids'],[])
        for t in (.3,.75):
            state = renderer.frame_state('S02',t,9)
            self.assertEqual(state['visible_label_ids'],['gong'])
            self.assertEqual(state['visible_marker_ids'],['gong'])
            self.assertEqual(state['route_segment_states'],[])
            self.assertEqual(state['location_intro_sec'],.3)
            self.assertEqual(state['route_growth_start_sec'],.75)
        growing = renderer.frame_state('S02',.8,9)
        self.assertEqual(growing['visible_label_ids'],['gong'])
        self.assertEqual([row['index'] for row in growing['route_segment_states']],[0])
        self.assertGreater(growing['route_segment_states'][0]['progress'],0)
        self.assertLess(growing['route_segment_states'][0]['progress'],1)

    def test_unintroduced_markers_are_absent_from_pixels_and_evidence(self):
        renderer = self.renderer
        with patch.object(renderer,'_circle',wraps=renderer._circle) as circles, \
                patch.object(renderer,'_line',wraps=renderer._line) as lines:
            image = renderer.render('S02',.3,9)
        state = ensure_map_evidence(image)['frame_state']
        self.assertEqual(state['visible_marker_ids'],['gong'])
        origin = renderer.points[0]
        self.assertEqual(len(circles.call_args_list),3)
        self.assertTrue(all(call.args[1:3]==origin for call in circles.call_args_list))
        self.assertTrue(all(call.args[3] not in (2.1,4.5) for call in lines.call_args_list))

    def test_later_chapters_retain_history_and_never_draw_future_segments(self):
        renderer = self.renderer
        for sid in renderer.scene_order[1:]:
            plan = renderer.per_scene[sid]
            for t in (0,.299,.3,.75,1,3,8.99):
                state = renderer.frame_state(sid,t,9)
                self.assertTrue(all(row['index']<plan['end_index'] for row in state['route_segment_states']))
                if sid != renderer.first_location_scene_id:
                    prior = list(dict.fromkeys(renderer.sequence[:plan['start_index']+1]))
                    self.assertEqual(state['visible_label_ids'][:len(prior)],prior)
                    expected_past = [j for j in range(plan['start_index']) if j not in renderer._degenerate]
                    past = state['route_segment_states'][:len(expected_past)]
                    self.assertEqual([row['index'] for row in past],expected_past)
                    self.assertTrue(all(row['progress']==1 for row in past))
                self.assertEqual(state['visible_label_ids'],state['visible_marker_ids'])

    def test_invalid_opening_ranges_and_skipped_initial_visits_are_actionable(self):
        for first in ((0,1),(1,1)):
            data = route()
            data['per_scene']['opening'].update(start_index=first[0],end_index=first[1])
            with self.assertRaisesRegex(ValueError,'opening map must hold origin.*move.*journey'):
                SeriesMap(data,maps.STYLE_PATH,self.theme)
        data = route()
        data['per_scene']['travel']['start_index'] = 1
        with self.assertRaisesRegex(ValueError,'previous scene end_index.*do not skip'):
            SeriesMap(data,maps.STYLE_PATH,self.theme)
        data = route(); data['scene_order'] = ['opening','travel']
        with self.assertRaisesRegex(ValueError,'each per_scene ID exactly once'):
            SeriesMap(data,maps.STYLE_PATH,self.theme)

    def test_intro_timing_validation_binds_actual_storyboard_cues(self):
        for value in (True,None,-1,.1,float('nan'),float('inf')):
            data = route(); data['per_scene']['travel']['location_intro_sec'] = value
            with self.assertRaisesRegex(ValueError,'location_intro_sec'):
                SeriesMap(data,maps.STYLE_PATH,self.theme)
        renderer = SeriesMap(route(),maps.STYLE_PATH,self.theme)
        scenes = [{'id':sid,'kind':'opening' if i==0 else 'chapter',
                   'start_frame':i*180,'end_frame':(i+1)*180,
                   'location_intro_sec':0 if i==0 else .3}
                  for i,sid in enumerate(renderer.scene_order)]
        self.assertIs(renderer.validate_scene_timings(scenes,30),renderer)
        bad = deepcopy(scenes); bad[1]['location_intro_sec'] = .4
        with self.assertRaisesRegex(ValueError,'must match the map cue'):
            renderer.validate_scene_timings(bad,30)
        with self.assertRaisesRegex(ValueError,'match the map scene_order'):
            renderer.validate_scene_timings(scenes[::-1],30)
        bad = deepcopy(scenes); bad[0]['kind'] = 'chapter'
        with self.assertRaisesRegex(ValueError,'kind opening'):
            renderer.validate_scene_timings(bad,30)
        with self.assertRaisesRegex(ValueError,'before the scene duration'):
            renderer.frame_state('travel',0,.3)
        data = route(); data['per_scene']['travel']['location_intro_sec'] = 5.9
        late = SeriesMap(data,maps.STYLE_PATH,self.theme)
        bad = deepcopy(scenes); bad[1]['location_intro_sec'] = 5.9
        with self.assertRaisesRegex(ValueError,'journey must reach end_index before the last native frame'):
            late.validate_scene_timings(bad,30)

    def test_colocated_arrivals_remain_visible_in_following_chapter(self):
        data = route(((108.93,34.26),(109.32,34.15),(109.32,34.15)))
        data['nodes'].append({'id':'3','label':'洛阳','lon':112.44,'lat':34.67})
        data['sequence'].append('3')
        data['per_scene']['travel']['end_index'] = 2
        data['per_scene']['stay'].update(start_index=2,end_index=3)
        renderer = SeriesMap(data,maps.STYLE_PATH,self.theme)
        self.assertEqual(renderer.frame_state('travel',5,6)['visible_label_ids'],['0','1','2'])
        for t in (0,.299,.3):
            state = renderer.frame_state('stay',t,6)
            self.assertEqual(state['current_index'],2)
            self.assertEqual(state['visible_label_ids'],['0','1','2'])
            self.assertEqual(state['visible_marker_ids'],['0','1','2'])

    def test_strict_evidence_replay_rejects_future_markers_and_forged_route_pixels(self):
        renderer = self.renderer
        image = renderer.render('S02',.3,9)
        forged = deepcopy(image.info[maps.EVIDENCE_KEY])
        forged['frame_state']['visible_marker_ids'].append('wuyue')
        image.info[maps.EVIDENCE_KEY] = forged
        with self.assertRaisesRegex(ValueError,'official route chronology'):
            ensure_map_evidence(image)
        image = renderer.render('S01',0,7)
        forged = deepcopy(image.info[maps.EVIDENCE_KEY])
        draw = ImageDraw.Draw(image)
        draw.line(renderer.curves[0],fill=renderer.colors['map_accent']+(210,),width=2)
        forged['image_sha256'] = hashlib.sha256(image.tobytes()).hexdigest()
        image.info[maps.EVIDENCE_KEY] = forged
        maps._PIXEL_HASHES.clear()
        with self.assertRaisesRegex(ValueError,'official sourced renderer'):
            ensure_map_evidence(image)
        image = renderer.render('S01',6,7)
        with tempfile.TemporaryDirectory() as directory:
            path = maps.save_map_png(image,Path(directory)/'opening.png')
            maps._RENDERERS.clear(); maps._PIXEL_HASHES.clear()
            restored = maps.load_map_png(path)
            self.assertEqual(restored.tobytes(),renderer._native_basemap.tobytes())


if __name__ == '__main__':
    unittest.main()
