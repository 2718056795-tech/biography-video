"""Regression checks for required, pixel-bound series maps.

Run with ``python -m unittest discover -s tests -p 'test_map_integration.py'``.
The short encoder check uses native frames and verifies the decoded frame count.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from check_series_style import check_layout
from check_project import check as check_project
from render_series_video import load_project, map_checkpoints, render_clip
from series_frame import DEFAULT_STYLE, SeriesFrame
from series_map import SeriesMap, load_map_png, save_map_png


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class RequiredMapIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = ROOT / 'assets/series/examples/dufu-project'
        cls.project = read_json(base / 'project.json')
        cls.profile = read_json(DEFAULT_STYLE)
        cls.theme = read_json(base / cls.project['theme'])
        cls.scenes = read_json(base / 'data/storyboard.json')['scenes']
        cls.scene = cls.scenes[1]
        cls.duration = (cls.scene['end_frame'] - cls.scene['start_frame']) / 30
        route = read_json(base / 'data/life_route.json')
        coast_value = cls.project.get('coastline_geojson', route.get('coastline', {}).get('file'))
        cls.maps = SeriesMap(route, cls.profile, cls.theme,
                             coastline_geojson=base / coast_value if coast_value else None)
        cls.maps.validate_scene_timings(cls.scenes, cls.project['fps'])
        cls.map_layer = cls.maps.render(cls.scene['id'], 3.5, cls.duration)
        cls.art = Image.new('RGBA', (1080, 1920), cls.theme['colors']['paper'])

    def setUp(self):
        self.frames = SeriesFrame(theme=self.theme, person=self.project['person'], scene_count=12)

    def compose(self, layer):
        return self.frames.compose(self.scene, 3.5, self.duration, self.art, layer)

    def report(self):
        frame = self.compose(self.map_layer)
        return frame, deepcopy(self.frames.last_report)

    def check(self, report, **images):
        return check_layout(report, self.profile, self.theme, DEFAULT_STYLE, **images)

    def assert_failed(self, result):
        self.assertEqual(result['technical_status'], 'failed', result)
        self.assertTrue(result['errors'])

    def test_map_is_required(self):
        with self.assertRaises((ValueError, TypeError)):
            self.compose(None)

    def test_arbitrary_native_rgba_is_rejected(self):
        with self.assertRaises(ValueError):
            self.compose(Image.new('RGBA', self.map_layer.size, '#123456'))

    def test_wrong_size_map_is_rejected(self):
        with self.assertRaises(ValueError):
            self.compose(self.map_layer.resize((879, 430)))

    def test_blank_map_with_copied_evidence_is_rejected(self):
        blank = Image.new('RGBA', self.map_layer.size)
        blank.info['series_map_evidence'] = deepcopy(self.map_layer.info['series_map_evidence'])
        with self.assertRaises(ValueError):
            self.compose(blank)

    def test_blank_map_with_rehashed_forged_evidence_is_rejected(self):
        blank = Image.new('RGBA', self.map_layer.size)
        blank.info['series_map_evidence'] = deepcopy(self.map_layer.info['series_map_evidence'])
        blank.info['series_map_evidence']['image_sha256'] = hashlib.sha256(blank.tobytes()).hexdigest()
        with self.assertRaises(ValueError):
            self.compose(blank)

    def test_map_pixels_cannot_change_under_valid_evidence(self):
        changed = self.map_layer.copy()
        changed.info = deepcopy(self.map_layer.info)
        x, y = changed.width // 2, changed.height // 2
        r, g, b, a = changed.getpixel((x, y))
        changed.putpixel((x, y), ((r + 1) % 256, g, b, a))
        with self.assertRaises(ValueError):
            self.compose(changed)

    def test_forged_engine_info_is_rejected(self):
        forged = self.map_layer.copy()
        forged.info = deepcopy(self.map_layer.info)
        forged.info['series_map_evidence']['engine_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.compose(forged)

    def test_official_map_is_bound_to_scene_and_clock(self):
        for scene_id, local_t, duration in ((self.scene['id'], 3.6, self.duration),
                                          (self.scene['id'], 3.5, self.duration + 1),
                                          ('S03', 3.5, self.duration)):
            with self.subTest(scene_id=scene_id, local_t=local_t, duration=duration):
                scene = dict(self.scene, id=scene_id)
                with self.assertRaises(ValueError):
                    self.frames.compose(scene, local_t, duration, self.art, self.map_layer)

    def test_actual_art_must_leave_map_readable(self):
        matching_art = Image.new('RGBA', (1080, 1920), self.theme['colors']['map_accent'])
        with self.assertRaises(ValueError):
            self.frames.compose(self.scene, 3.5, self.duration, matching_art, self.map_layer)

    def test_official_map_produces_pixel_bound_frame_report(self):
        frame, report = self.report()
        self.assertEqual(frame.size, (1080, 1920))
        self.assertEqual(frame.mode, 'RGB')
        self.assertIs(report['map_present'], True)
        self.assertEqual(report['frame_sha256'], hashlib.sha256(frame.tobytes()).hexdigest())
        self.assertEqual(report['map_evidence'], self.map_layer.info['series_map_evidence'])
        result = self.check(report, frame_image=frame, map_image=self.map_layer)
        self.assertEqual(result['technical_status'], 'passed', result)

    def test_arrived_names_persist_at_next_arrival_and_following_chapter(self):
        # S02 reaches 吴越 then 齐鲁. Check the rendered state on both sides of
        # the second arrival and again when S03 continues toward 长安.
        following = self.scenes[2]
        following_duration = (following['end_frame'] - following['start_frame']) / 30
        checkpoints = [
            (self.scene, 0., self.duration, []),
            (self.scene, .299, self.duration, []),
            (self.scene, .3, self.duration, ['gong']),
            (self.scene, 3.5, self.duration, ['gong', 'wuyue']),
            (self.scene, self.duration - 1/30, self.duration, ['gong', 'wuyue', 'qilu']),
            (following, 0., following_duration, ['gong', 'wuyue', 'qilu']),
            (following, following_duration - 1/30, following_duration,
             ['gong', 'wuyue', 'qilu', 'changan']),
        ]
        fixed_layouts = self.maps.geometry_report()['label_layouts']
        layout_hash = canonical_hash(fixed_layouts)
        for scene, t, duration, expected_ids in checkpoints:
            with self.subTest(scene_id=scene['id'], time=t):
                layer = self.maps.render(scene['id'], t, duration)
                self.frames.compose(scene, t, duration, self.art, layer)
                report = self.frames.last_report
                evidence = report['map_evidence']
                self.assertEqual(evidence['visible_label_ids'], expected_ids)
                self.assertEqual(evidence['label_layout_sha256'], layout_hash)
                self.assertEqual(evidence['geometry']['label_layouts'], fixed_layouts)
                self.assertEqual(report['map_labels']['visible_label_ids'], expected_ids)
                self.assertEqual(report['map_labels']['visible_layouts'],
                                 {node_id: fixed_layouts[node_id] for node_id in expected_ids})
                self.assertEqual(self.check(report)['technical_status'], 'passed')

    def test_opening_is_base_only_and_final_region_retains_all_arrived_names(self):
        opening, ending = self.scenes[0], self.scenes[-1]
        for scene in (opening, ending):
            duration = (scene['end_frame'] - scene['start_frame']) / 30
            evidence = self.maps.render(scene['id'], 0., duration).info['series_map_evidence']
            with self.subTest(scene_id=scene['id']):
                expected = [] if scene is opening else list(dict.fromkeys(self.maps.sequence))
                self.assertEqual(evidence['visible_label_ids'], expected)
                self.assertEqual(len(evidence['visible_label_ids']), len(set(evidence['visible_label_ids'])))

    def geographic_base_pixels(self):
        return self.maps._base_image.resize(self.maps.size, Image.Resampling.LANCZOS).tobytes()

    def test_every_native_opening_frame_contains_only_geographic_base_pixels(self):
        opening = self.scenes[0]
        count = opening['end_frame'] - opening['start_frame']
        base_pixels = self.geographic_base_pixels()
        for frame in range(count):
            layer = self.maps.render(opening['id'], frame / 30, count / 30)
            state = layer.info['series_map_evidence']['frame_state']
            with self.subTest(frame=frame):
                self.assertEqual(layer.tobytes(), base_pixels)
                self.assertEqual(state['visible_label_ids'], [])
                self.assertEqual(state['route_segment_states'], [])
                self.assertIsNone(state['current_index'])
                self.assertFalse(state['region_active'])

    def test_legacy_overview_true_never_previews_the_journey(self):
        route = deepcopy(self.maps.data)
        route['per_scene'][self.scenes[0]['id']]['overview'] = True
        maps = SeriesMap(route, self.profile, self.theme)
        maps.validate_scene_timings(self.scenes, 30)
        opening = self.scenes[0]
        duration = (opening['end_frame'] - opening['start_frame']) / 30
        for t in (0., 3.5, duration - 1/30):
            with self.subTest(time=t):
                layer = maps.render(opening['id'], t, duration)
                self.assertEqual(layer.tobytes(), self.geographic_base_pixels())
                self.assertEqual(layer.info['series_map_evidence']['visible_label_ids'], [])
                self.assertEqual(layer.info['series_map_evidence']['frame_state']['route_segment_states'], [])

    def test_first_location_waits_for_metadata_and_growth_waits_for_route_delay(self):
        base_pixels = self.geographic_base_pixels()
        intro = self.profile['standard']['meta']['start']
        growth_start = intro + self.profile['motion']['map_segment_delay']
        for t in (0., intro - .001):
            with self.subTest(time=t):
                layer = self.maps.render(self.scene['id'], t, self.duration)
                self.assertEqual(layer.tobytes(), base_pixels)
        for t in (intro, growth_start):
            with self.subTest(time=t):
                layer = self.maps.render(self.scene['id'], t, self.duration)
                state = layer.info['series_map_evidence']['frame_state']
                self.assertEqual(state['visible_label_ids'], ['gong'])
                self.assertEqual(state['route_segment_states'], [])
                self.assertNotEqual(layer.tobytes(), base_pixels)
        growing = self.maps.frame_state(self.scene['id'], growth_start + 1/30, self.duration)
        self.assertGreater(growing['route_segment_states'][0]['progress'], 0)
        self.assertLess(growing['route_segment_states'][0]['progress'], 1)
        self.assertEqual(growing['visible_label_ids'], ['gong'])

    def test_future_place_markers_are_absent_until_their_arrival(self):
        base = self.maps._base_image.resize(self.maps.size, Image.Resampling.LANCZOS)
        introduced = self.maps.render(self.scene['id'], .3, self.duration)
        for node_id in ('wuyue', 'qilu', 'changan', 'chengdu', 'kuizhou'):
            x, y = self.maps.pixel(self.maps.nodes[node_id]['lon'], self.maps.nodes[node_id]['lat'])
            box = (math.floor(x)-8, math.floor(y)-8, math.ceil(x)+9, math.ceil(y)+9)
            with self.subTest(node_id=node_id):
                self.assertEqual(introduced.crop(box).tobytes(), base.crop(box).tobytes())

    def test_previously_introduced_history_survives_later_chapter_intro_delay(self):
        previous = self.maps.render(self.scene['id'], self.duration - 1/30, self.duration)
        following = self.scenes[2]
        duration = (following['end_frame'] - following['start_frame']) / 30
        for t in (0., .299, .3):
            with self.subTest(time=t):
                layer = self.maps.render(following['id'], t, duration)
                self.assertEqual(layer.tobytes(), previous.tobytes())
                self.assertEqual(layer.info['series_map_evidence']['visible_label_ids'], ['gong', 'wuyue', 'qilu'])

    def test_map_checkpoints_cover_metadata_and_route_growth_boundaries(self):
        checkpoints, persistence = map_checkpoints(self.maps, self.scene['id'], self.duration,
                                                   0., self.scene['end_frame']-self.scene['start_frame'], 30)
        self.assertIn('before_location_intro', checkpoints[8])
        self.assertIn('at_location_intro', checkpoints[9])
        self.assertIn('before_route_growth', checkpoints[22])
        self.assertIn('at_route_growth', checkpoints[23])
        self.assertEqual(persistence['location_intro_sec'], .3)
        self.assertEqual(persistence['route_growth_start_sec'], .75)

    def test_production_loader_rejects_a_route_before_script_metadata_introduction(self):
        with tempfile.TemporaryDirectory(prefix='series-intro-loader-') as directory:
            directory = Path(directory)
            route = deepcopy(self.maps.data)
            route['per_scene']['S02']['location_intro_sec'] = .1
            (directory / 'route.json').write_text(json.dumps(route), encoding='utf-8')
            project = deepcopy(self.project)
            project.update(scenes=self.scenes, route='route.json', theme=self.theme)
            path = directory / 'project.json'
            path.write_text(json.dumps(project), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'intro|meta|location'):
                load_project(path)

    def test_generators_emit_safe_opening_and_matching_location_cues(self):
        with tempfile.TemporaryDirectory(prefix='series-intro-generators-') as directory:
            for script, extra in [('init_series_project.py', ['--name', '杜甫', '--title', '此心在人间', '--theme', 'dufu']),
                                  ('export_dufu_reference_project.py', [])]:
                with self.subTest(generator=script):
                    output = Path(directory) / Path(script).stem
                    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script),
                                             '--output', str(output), *extra], text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    scenes = read_json(output / 'data/storyboard.json')['scenes']
                    route = read_json(output / 'data/life_route.json')
                    opening = route['per_scene'][scenes[0]['id']]
                    self.assertEqual((opening['start_index'], opening['end_index']), (0, 0))
                    self.assertEqual(scenes[0]['visible_visit_ids'], [])
                    self.assertFalse(opening.get('overview', False))
                    for scene in scenes:
                        expected = 0 if scene['kind'] == 'opening' else .3
                        self.assertEqual(scene['location_intro_sec'], expected)
                        self.assertEqual(route['per_scene'][scene['id']]['location_intro_sec'], expected)
                    if route.get('visits'):
                        self.assertEqual(route['visits'][0]['scene_id'], scenes[1]['id'])

    def test_preflight_rejects_script_and_route_intro_timing_mismatch(self):
        base = ROOT / 'assets/series/examples/dufu-project'
        with tempfile.TemporaryDirectory(prefix='series-intro-preflight-') as directory:
            directory = Path(directory)
            project = deepcopy(self.project)
            project.update(storyboard='board.json', route='route.json',
                           theme=str((base / self.project['theme']).resolve()),
                           art_provider=str((base / self.project['art_provider']).resolve()))
            project['audio']['path'] = str((base / self.project['audio']['path']).resolve())
            scenes = deepcopy(self.scenes)
            scenes[1]['location_intro_sec'] = 1.
            for name, value in [('project.json', project), ('board.json', {'schema_version': self.profile['schema_version'], 'scenes': scenes}),
                                ('route.json', self.maps.data)]:
                (directory / name).write_text(json.dumps(value), encoding='utf-8')
            (directory / 'references').mkdir()
            shutil.copy2(base / 'references/source_ledger.csv', directory / 'references/source_ledger.csv')
            result = check_project(directory)
            self.assertEqual(result['map_preflight']['status'], 'failed', result)
            self.assertRegex(result['map_preflight']['error'], 'intro|meta|location')

    def test_label_pixels_persist_and_future_name_pixels_wait_for_arrival(self):
        before = self.maps.render(self.scene['id'], 3.5, self.duration)
        after = self.maps.render(self.scene['id'], self.duration - 1/30, self.duration)
        following = self.scenes[2]
        next_duration = (following['end_frame'] - following['start_frame']) / 30
        next_chapter = self.maps.render(following['id'], 0., next_duration)
        layouts = self.maps.geometry_report()['label_layouts']

        def opaque_label_pixels(image, node_id):
            bounds = layouts[node_id]['bounds']
            box = tuple(math.floor(v) if index < 2 else math.ceil(v)
                        for index, v in enumerate(bounds))
            # Label/halo ink is 245 alpha; route, leaders and basemap are lower.
            return bytes(value >= 230 for value in image.crop(box).getchannel('A').tobytes())

        for node_id in ('gong', 'wuyue'):
            with self.subTest(node_id=node_id):
                visible = opaque_label_pixels(before, node_id)
                self.assertGreater(sum(visible), 100)
                self.assertEqual(visible, opaque_label_pixels(after, node_id))
                self.assertEqual(visible, opaque_label_pixels(next_chapter, node_id))
        self.assertEqual(sum(opaque_label_pixels(before, 'qilu')), 0)
        arrived = opaque_label_pixels(after, 'qilu')
        self.assertGreater(sum(arrived), 100)
        self.assertEqual(arrived, opaque_label_pixels(next_chapter, 'qilu'))

    def test_whole_route_label_layout_has_no_overlaps_or_off_panel_names(self):
        geometry = self.maps.geometry_report()
        layouts = geometry['label_layouts']
        self.assertEqual(set(layouts), set(self.maps.sequence))
        self.assertEqual(len(layouts), 15)
        rebuilt = SeriesMap(deepcopy(self.maps.data), self.profile, self.theme)
        self.assertEqual(rebuilt.geometry_report()['label_layouts'], layouts)
        boxes = []
        for node_id, layout in layouts.items():
            with self.subTest(node_id=node_id):
                left, top, right, bottom = layout['bounds']
                self.assertTrue(0 <= left < right <= 880 and 0 <= top < bottom <= 430)
                self.assertEqual(layout['route_intersections'], 0)
                self.assertEqual(layout['font_size'], 28)
                self.assertIs(layout['font_bold'], True)
                self.assertEqual(layout['color_role'], 'map_accent')
                self.assertEqual(layout['alpha'], 245)
                for other_id, (ol, ot, oright, ob) in boxes:
                    self.assertFalse(left < oright and right > ol and top < ob and bottom > ot,
                                     f'{node_id} overlaps {other_id}')
                boxes.append((node_id, layout['bounds']))
        route_style = geometry['route_stroke_policy']
        self.assertEqual({key: route_style[key] for key in
                          ('width', 'alpha', 'halo_width', 'halo_alpha', 'all_segments_same')},
                         {'width': 2.1, 'alpha': 210, 'halo_width': 4.5,
                          'halo_alpha': 64, 'all_segments_same': True})

    def test_visible_label_claim_cannot_be_forged(self):
        for claimed_ids in ([], ['gong'], ['gong', 'wuyue', 'qilu'], ['gong', 'gong', 'wuyue']):
            with self.subTest(claimed_ids=claimed_ids):
                forged = self.map_layer.copy()
                forged.info = deepcopy(self.map_layer.info)
                evidence = forged.info['series_map_evidence']
                evidence['visible_label_ids'] = claimed_ids
                # Matching duplicated summaries must not turn an invented
                # future arrival into valid evidence.
                evidence['frame_state']['visible_label_ids'] = claimed_ids
                if claimed_ids:
                    evidence['frame_state']['current_index'] = self.maps.sequence.index(claimed_ids[-1])
                with self.assertRaises(ValueError):
                    self.compose(forged)
                _, report = self.report()
                report['map_evidence'] = evidence
                self.assert_failed(self.check(report))

    def test_label_layout_hash_cannot_be_forged(self):
        forged = self.map_layer.copy()
        forged.info = deepcopy(self.map_layer.info)
        forged.info['series_map_evidence']['label_layout_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.compose(forged)
        _, report = self.report()
        report['map_evidence']['label_layout_sha256'] = '0' * 64
        self.assert_failed(self.check(report))

    def test_rehashed_label_positions_and_route_style_cannot_be_forged(self):
        for field in ('label_layouts', 'route_stroke_policy'):
            with self.subTest(field=field):
                forged = self.map_layer.copy()
                forged.info = deepcopy(self.map_layer.info)
                evidence = forged.info['series_map_evidence']
                if field == 'label_layouts':
                    evidence['geometry'][field]['gong']['position'][0] += 1
                    evidence['label_layout_sha256'] = canonical_hash(evidence['geometry'][field])
                else:
                    evidence['geometry'][field]['alpha'] = 165
                evidence['geometry_sha256'] = canonical_hash(evidence['geometry'])
                with self.assertRaises(ValueError):
                    self.compose(forged)
                _, report = self.report()
                report['map_evidence'] = evidence
                self.assert_failed(self.check(report))

    def test_frame_label_summary_is_required_and_bound_to_verified_evidence(self):
        _, original = self.report()
        for field in (None, 'visible_label_ids', 'label_layout_sha256', 'visible_layouts', 'route_stroke_policy'):
            with self.subTest(field=field):
                report = deepcopy(original)
                if field is None:
                    report.pop('map_labels')
                elif field == 'visible_label_ids':
                    report['map_labels'][field] = ['gong', 'wuyue', 'qilu']
                elif field == 'label_layout_sha256':
                    report['map_labels'][field] = '0' * 64
                elif field == 'visible_layouts':
                    report['map_labels'][field]['gong']['position'][0] += 1
                else:
                    report['map_labels'][field]['alpha'] = 165
                self.assert_failed(self.check(report))

    def test_missing_or_false_map_flag_fails_style_check(self):
        _, report = self.report()
        for value in (None, False):
            with self.subTest(map_present=value):
                changed = deepcopy(report)
                if value is None:
                    changed.pop('map_present', None)
                else:
                    changed['map_present'] = value
                self.assert_failed(self.check(changed))

    def test_missing_map_evidence_fails_style_check(self):
        _, report = self.report()
        report.pop('map_evidence')
        self.assert_failed(self.check(report))

    def test_missing_actual_background_readability_fails_style_check(self):
        _, report = self.report()
        report.pop('map_background_readability')
        self.assert_failed(self.check(report))

    def test_falsified_background_thresholds_fail_style_check(self):
        _, report = self.report()
        report['map_background_readability']['checks'][0]['minimum_contrast'] = .01
        self.assert_failed(self.check(report))

    def test_background_measurement_is_bound_to_map_pixels(self):
        _, report = self.report()
        report['map_background_readability']['map_image_sha256'] = '0' * 64
        self.assert_failed(self.check(report))

    def test_forged_engine_report_fails_style_check(self):
        _, report = self.report()
        report['map_evidence']['engine_sha256'] = '0' * 64
        self.assert_failed(self.check(report))

    def test_missing_frame_hash_fails_style_check(self):
        _, report = self.report()
        report.pop('frame_sha256')
        self.assert_failed(self.check(report))

    def test_actual_frame_pixels_must_match_report(self):
        frame, report = self.report()
        changed = frame.copy()
        changed.putpixel((100, 100), (1, 2, 3))
        self.assert_failed(self.check(report, frame_image=changed, map_image=self.map_layer))

    def test_actual_map_pixels_must_match_report(self):
        frame, report = self.report()
        blank = Image.new('RGBA', self.map_layer.size)
        self.assert_failed(self.check(report, frame_image=frame, map_image=blank))

    def test_preview_generates_official_map_from_project(self):
        with tempfile.TemporaryDirectory(prefix='series-map-preview-') as directory:
            directory = Path(directory)
            artwork, output, report = directory / 'art.png', directory / 'frame.png', directory / 'frame.json'
            self.art.save(artwork)
            completed = subprocess.run([
                sys.executable, str(ROOT / 'scripts/render_series_preview.py'),
                '--project', str(ROOT / 'assets/series/examples/dufu-project/project.json'),
                '--scene', self.scene['id'], '--time', '3.5', '--art', str(artwork),
                '--output', str(output), '--report', str(report)
            ], text=True, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            recorded = read_json(report)
            with Image.open(output) as image:
                result = self.check(recorded, frame_image=image.convert('RGB'), map_image=self.map_layer)
            self.assertEqual(result['technical_status'], 'passed', result)

    def test_preview_rejects_arbitrary_external_png(self):
        with tempfile.TemporaryDirectory(prefix='series-map-external-') as directory:
            directory = Path(directory)
            artwork, bad_map = directory / 'art.png', directory / 'unproven-map.png'
            output, report = directory / 'frame.png', directory / 'frame.json'
            self.art.save(artwork)
            Image.new('RGBA', self.map_layer.size, '#123456').save(bad_map)
            completed = subprocess.run([
                sys.executable, str(ROOT / 'scripts/render_series_preview.py'),
                '--project', str(ROOT / 'assets/series/examples/dufu-project/project.json'),
                '--scene', self.scene['id'], '--time', '3.5', '--art', str(artwork),
                '--map', str(bad_map), '--output', str(output), '--report', str(report)
            ], text=True, capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(output.exists())

    def test_official_external_map_with_sidecar_survives_process_boundary(self):
        with tempfile.TemporaryDirectory(prefix='series-map-sidecar-') as directory:
            directory = Path(directory)
            artwork, map_path = directory / 'art.png', directory / 'map.png'
            output, report = directory / 'frame.png', directory / 'frame.json'
            self.art.save(artwork)
            save_map_png(self.map_layer, map_path)
            loaded = load_map_png(map_path)
            self.assertEqual(loaded.tobytes(), self.map_layer.tobytes())
            completed = subprocess.run([
                sys.executable, str(ROOT / 'scripts/render_series_preview.py'),
                '--project', str(ROOT / 'assets/series/examples/dufu-project/project.json'),
                '--scene', self.scene['id'], '--time', '3.5', '--art', str(artwork),
                '--map', str(map_path), '--output', str(output), '--report', str(report)
            ], text=True, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            recorded = read_json(report)
            with Image.open(output) as image:
                result = self.check(recorded, frame_image=image.convert('RGB'), map_image=loaded)
            self.assertEqual(result['technical_status'], 'passed', result)

    def test_style_cli_can_require_actual_pixels(self):
        _, report = self.report()
        with tempfile.TemporaryDirectory(prefix='series-style-pixels-') as directory:
            directory = Path(directory)
            report_path, theme_path, result_path = (directory / name for name in ('frame.json', 'theme.json', 'qa.json'))
            report_path.write_text(json.dumps(report), encoding='utf-8')
            theme_path.write_text(json.dumps(self.theme), encoding='utf-8')
            completed = subprocess.run([
                sys.executable, str(ROOT / 'scripts/check_series_style.py'),
                '--report', str(report_path), '--theme', str(theme_path),
                '--require-pixels', '--output', str(result_path)
            ], text=True, capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assert_failed(read_json(result_path))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg tools unavailable')
    def test_native_short_clip_encodes_real_frames(self):
        with tempfile.TemporaryDirectory(prefix='series-map-integration-') as directory:
            for scene, count in ((self.scenes[0], 3), (self.scene, 25)):
                with self.subTest(scene=scene['id']):
                    output = Path(directory) / f'{scene["id"]}-silent-preview.mp4'
                    layout = Path(directory) / f'{scene["id"]}-layout.json'
                    calls = []

                    def draw_art(scene_id, t, duration, theme):
                        self.assertEqual(scene_id, scene['id'])
                        calls.append(t)
                        art = self.art.copy()
                        # The provider is called for every actual encoded frame.
                        art.putpixel((20 + round(t * 30), 900), (20, 30, 40, 255))
                        return art

                    qa = render_clip(output, scene, 0., count, self.frames, self.maps, draw_art,
                                     self.theme, fps=30, layout_path=layout)
                    metadata = json.loads(subprocess.check_output([
                        'ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                        '-show_entries', 'stream=width,height,nb_read_frames', '-of', 'json', str(output)
                    ], text=True))['streams'][0]
                    self.assertEqual((metadata['width'], metadata['height']), (1080, 1920))
                    self.assertEqual(int(metadata['nb_read_frames']), count)
                    self.assertEqual(len(calls), count)
                    self.assertIs(read_json(layout)['map_present'], True)
                    self.assertIn('map_evidence', read_json(layout))
                    if scene['kind'] == 'opening':
                        for sample in qa['samples']:
                            self.assertEqual(sample['map_evidence']['visible_label_ids'], [])
                            self.assertEqual(sample['map_evidence']['image_sha256'],
                                             hashlib.sha256(self.geographic_base_pixels()).hexdigest())
                    else:
                        labels = {sample['frame_index']: sample['map_evidence']['visible_label_ids']
                                  for sample in qa['samples']}
                        self.assertEqual(labels[8], [])
                        self.assertEqual(labels[9], ['gong'])
                        self.assertEqual(qa['label_persistence']['route_growth_start_sec'], .75)


if __name__ == '__main__':
    unittest.main()
