#!/usr/bin/env python3
"""Focused offline provenance, geographic coverage, and tamper checks."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    from scripts import series_basemap as basemap
except ModuleNotFoundError:
    import series_basemap as basemap


class BundledBasemapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = basemap.load_default_basemap()

    def test_pinned_public_domain_sources(self):
        provenance = self.data['provenance']
        commit = 'f1890d9f152c896d250a77557a5751a93d494776'
        self.assertEqual(provenance['upstream']['commit'], commit)
        self.assertEqual(provenance['upstream']['release'], 'v5.1.2')
        self.assertEqual(provenance['crs'], 'EPSG:4326')
        self.assertEqual(provenance['license']['name'], 'Public domain')
        self.assertIn('Everything here is public domain.', basemap.LICENSE_PATH.read_text())
        for source in provenance['source_files']:
            self.assertEqual(source['url'],
                             f'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{commit}/{source["path"]}')
            self.assertRegex(source['sha256'], r'^[0-9a-f]{64}$')
            self.assertGreater(source['bytes'], 0)
        for local in provenance['local_files']:
            self.assertEqual(hashlib.sha256(Path(local['path']).read_bytes()).hexdigest(), local['sha256'])

    def test_natural_line_layers_and_feature_counts(self):
        features = self.data['features']
        self.assertEqual(Counter(f['properties']['layer'] for f in features),
                         {'coast': 1428, 'river': 1471})
        self.assertTrue(all(f['geometry']['type'] in ('LineString', 'MultiLineString') for f in features))
        self.assertEqual({f['properties']['source'] for f in features},
                         {'ne_50m_coastline', 'ne_10m_rivers_lake_centerlines'})
        classes = {f['properties']['featurecla'] for f in features if f['properties']['layer'] == 'river'}
        self.assertEqual(classes, {'River', 'River (Intermittent)', 'Lake Centerline'})
        self.assertEqual(len({f['properties']['source_id'] for f in features}), len(features))

    def test_genuine_inland_and_european_references(self):
        rivers = [f for f in self.data['features'] if f['properties']['layer'] == 'river']
        names = {f['properties'].get('name_en') for f in rivers}
        self.assertTrue({'Wei', 'Thames', 'Seine', 'Rhine', 'Danube'}.issubset(names))
        wei = next(f for f in rivers if f['properties'].get('wikidataid') == 'Q847641')
        self.assertEqual(wei['properties']['name_zh'], '渭河')
        runs = (wei['geometry']['coordinates'] if wei['geometry']['type'] == 'MultiLineString'
                else [wei['geometry']['coordinates']])
        self.assertTrue(any(108.5 < lon < 109.5 and 34.0 < lat < 34.7
                            for run in runs for lon, lat in run))
        coast_bounds = [f['bbox'] for f in self.data['features'] if f['properties']['layer'] == 'coast']
        self.assertEqual(min(box[0] for box in coast_bounds), -180)
        self.assertEqual(max(box[2] for box in coast_bounds), 180)
        self.assertLess(min(box[1] for box in coast_bounds), -80)
        self.assertGreater(max(box[3] for box in coast_bounds), 80)

    def test_geometry_fingerprint_is_independently_reproducible(self):
        collection = {key: self.data[key] for key in ('type', 'features')}
        raw = json.dumps(collection, sort_keys=True, ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(self.data['sha256'], digest)
        self.assertTrue(basemap.validate_default_basemap_fingerprint(digest))
        self.assertFalse(basemap.validate_default_basemap_fingerprint('0' * 64))

    def test_offline_load_and_unchanged_file_cache(self):
        basemap._decode_basemap.cache_clear()
        with mock.patch('socket.socket', side_effect=AssertionError('Network is disabled')):
            loaded = basemap.load_default_basemap()
            before = basemap._file_bytes.cache_info()
            self.assertIs(loaded, basemap.load_default_basemap())
            after = basemap._file_bytes.cache_info()
        self.assertEqual(after.misses, before.misses)
        self.assertEqual(after.hits - before.hits, 4)

    def test_cached_bundle_rejects_same_size_edits_with_restored_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = {}
            for attr in ('BASEMAP_PATH', 'PROVENANCE_PATH', 'LICENSE_PATH'):
                original = getattr(basemap, attr)
                target = Path(directory) / original.name
                target.write_bytes(original.read_bytes())
                paths[attr] = target
            with mock.patch.multiple(basemap, **paths):
                basemap.load_default_basemap()
                for attr, path in paths.items():
                    with self.subTest(file=attr):
                        raw, info = path.read_bytes(), path.stat()
                        path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
                        with self.assertRaises(basemap.BasemapIntegrityError):
                            basemap.load_default_basemap()
                        path.write_bytes(raw)
                        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
                        self.assertEqual(basemap.load_default_basemap()['sha256'], self.data['sha256'])


if __name__ == '__main__':
    unittest.main()
