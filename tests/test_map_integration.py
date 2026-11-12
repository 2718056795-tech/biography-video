"""Regression checks for required, pixel-bound series maps.

Run with ``python -m unittest discover -s tests -p 'test_map_integration.py'``.
The short encoder check uses native frames and verifies the decoded frame count.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
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
from render_series_video import render_clip
from series_frame import DEFAULT_STYLE, SeriesFrame
from series_map import SeriesMap, load_map_png, save_map_png


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


class RequiredMapIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = ROOT / 'assets/series/examples/dufu-project'
        cls.project = read_json(base / 'project.json')
        cls.profile = read_json(DEFAULT_STYLE)
        cls.theme = read_json(base / cls.project['theme'])
        cls.scene = read_json(base / 'data/storyboard.json')['scenes'][1]
        cls.duration = (cls.scene['end_frame'] - cls.scene['start_frame']) / 30
        route = read_json(base / 'data/life_route.json')
        coast_value = cls.project.get('coastline_geojson', route.get('coastline', {}).get('file'))
        cls.maps = SeriesMap(route, cls.profile, cls.theme,
                             coastline_geojson=base / coast_value if coast_value else None)
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
            output = Path(directory) / 'map-silent-preview.mp4'
            layout = Path(directory) / 'layout.json'

            def draw_art(scene_id, t, duration, theme):
                self.assertEqual(scene_id, self.scene['id'])
                art = self.art.copy()
                # A real moving art pixel also ensures the provider is called per frame.
                art.putpixel((20 + round(t * 30), 900), (20, 30, 40, 255))
                return art

            render_clip(output, self.scene, 3.5, 3, self.frames, self.maps, draw_art,
                        self.theme, fps=30, layout_path=layout)
            metadata = json.loads(subprocess.check_output([
                'ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,nb_read_frames', '-of', 'json', str(output)
            ], text=True))['streams'][0]
            self.assertEqual((metadata['width'], metadata['height']), (1080, 1920))
            self.assertEqual(int(metadata['nb_read_frames']), 3)
            self.assertIs(read_json(layout)['map_present'], True)
            self.assertIn('map_evidence', read_json(layout))


if __name__ == '__main__':
    unittest.main()
