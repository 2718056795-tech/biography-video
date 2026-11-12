#!/usr/bin/env python3
"""Offline, integrity-checked Natural Earth physical geography for series maps.

The bundled data are WGS84 longitude/latitude LineStrings, retaining the original
Natural Earth geometry. There are no downloads or optional GIS dependencies at
render time. ``load_default_basemap()`` returns a cached read-only-by-convention
GeoJSON FeatureCollection with ``provenance`` and ``sha256`` metadata. Callers
that need to edit it must first make a deep copy.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path


GEOGRAPHY_ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'series' / 'geography'
BASEMAP_PATH = GEOGRAPHY_ASSETS / 'natural_earth_basemap.geojson.gz'
PROVENANCE_PATH = GEOGRAPHY_ASSETS / 'provenance.json'
LICENSE_PATH = GEOGRAPHY_ASSETS / 'LICENSE.md'

# Pin the manifest itself so edits to both the data and its claimed hash fail.
EXPECTED_PROVENANCE_SHA256 = 'bdd9ffd7e50b920fa0109ecf88f31d56f45947b20073adf804da0dcbc90fd6d9'


class BasemapIntegrityError(ValueError):
    """Bundled geography or its provenance does not match the reviewed release."""


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _check_hash(raw, expected, name):
    actual = _sha256(raw)
    if actual != expected:
        raise BasemapIntegrityError(f'{name}: SHA256 mismatch ({actual}; expected {expected})')


@lru_cache(maxsize=8)
def _file_bytes(path, stat_key):
    """Read/hash once per filesystem identity and modification signature."""
    raw = Path(path).read_bytes()
    return raw, _sha256(raw)


def _local_file(path, expected=None, name=None):
    info = path.stat()
    stat_key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    raw, digest = _file_bytes(str(path), stat_key)
    if expected is not None and digest != expected:
        raise BasemapIntegrityError(
            f'{name or path.name}: SHA256 mismatch ({digest}; expected {expected})')
    return raw, digest


@lru_cache(maxsize=1)
def _read_provenance(raw):
    _check_hash(raw, EXPECTED_PROVENANCE_SHA256, 'Bundled basemap provenance')
    try:
        provenance = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise BasemapIntegrityError('Bundled basemap provenance is invalid JSON') from exc
    if provenance.get('schema_version') != 1 or provenance.get('crs') != 'EPSG:4326':
        raise BasemapIntegrityError('Unsupported basemap provenance schema or coordinate reference')
    return provenance


def _validate_features(collection, provenance):
    if collection.get('type') != 'FeatureCollection' or not isinstance(collection.get('features'), list):
        raise BasemapIntegrityError('Bundled basemap must be a GeoJSON FeatureCollection')
    counts = Counter()
    for feature in collection['features']:
        if feature.get('type') != 'Feature':
            raise BasemapIntegrityError('Bundled basemap contains a non-Feature record')
        properties = feature.get('properties', {})
        layer = properties.get('layer')
        if layer not in ('coast', 'river') or not properties.get('source_id'):
            raise BasemapIntegrityError('Bundled geography requires a coast/river layer and source ID')
        geometry = feature.get('geometry', {})
        kind, coordinates = geometry.get('type'), geometry.get('coordinates')
        if kind == 'LineString':
            runs = [coordinates]
        elif kind == 'MultiLineString':
            runs = coordinates
        else:
            raise BasemapIntegrityError(f'Bundled geography contains unsupported geometry: {kind}')
        if not isinstance(runs, list) or not runs:
            raise BasemapIntegrityError('Bundled geography contains an empty geometry')
        for run in runs:
            if not isinstance(run, list) or len(run) < 2:
                raise BasemapIntegrityError('Bundled geography contains an incomplete line')
            for point in run:
                if (not isinstance(point, list) or len(point) != 2 or
                        any(type(v) not in (float, int) or not math.isfinite(v) for v in point) or
                        not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90):
                    raise BasemapIntegrityError('Bundled geography contains an invalid WGS84 coordinate')
        counts[layer] += 1
    if dict(counts) != provenance.get('feature_counts'):
        raise BasemapIntegrityError('Bundled basemap feature counts differ from provenance')


@lru_cache(maxsize=1)
def _decode_basemap(raw, provenance_raw, local_files):
    provenance = deepcopy(_read_provenance(provenance_raw))
    expected = provenance['outputs']['data']
    _check_hash(raw, expected['sha256'], 'Bundled basemap data')
    try:
        uncompressed = gzip.decompress(raw)
        collection = json.loads(uncompressed)
    except (OSError, EOFError, ValueError, UnicodeDecodeError) as exc:
        raise BasemapIntegrityError('Bundled basemap is not valid gzip-compressed GeoJSON') from exc
    _check_hash(uncompressed, expected['uncompressed_sha256'], 'Uncompressed basemap GeoJSON')
    if _canonical_json(collection) != uncompressed:
        raise BasemapIntegrityError('Bundled basemap does not use the declared canonical JSON encoding')
    if _sha256(uncompressed) != provenance['canonical_data_sha256']:
        raise BasemapIntegrityError('Bundled basemap canonical fingerprint differs from provenance')
    _validate_features(collection, provenance)
    provenance['local_files'] = [{'path': path, 'sha256': digest} for path, digest in local_files]
    collection['provenance'] = provenance
    collection['sha256'] = provenance['canonical_data_sha256']
    return collection


def load_default_basemap():
    """Load verified bundled coast/rivers without network access.

    Returns ``{'type': 'FeatureCollection', 'features': [...],
    'provenance': {...}, 'sha256': '<canonical data fingerprint>'}``.
    The fingerprint covers the canonical source GeoJSON collection, excluding
    the added ``provenance`` and ``sha256`` keys. Properties identify ``layer``
    (``coast`` or ``river``), the upstream dataset/record, and available names.

    File reads and SHA256 checks are cached by device, inode, size, modification
    time and change time; changed files are checked again. Parsing/coordinate
    validation are cached by content. Runtime ``provenance.local_files`` records
    absolute paths and hashes for data, provenance, license and this loader.
    Missing or altered assets raise an error without fallback or downloading.
    """
    provenance_raw, provenance_sha = _local_file(
        PROVENANCE_PATH, EXPECTED_PROVENANCE_SHA256, 'Bundled basemap provenance')
    provenance = _read_provenance(provenance_raw)
    data_raw, data_sha = _local_file(
        BASEMAP_PATH, provenance['outputs']['data']['sha256'], 'Bundled basemap data')
    _, license_sha = _local_file(
        LICENSE_PATH, provenance['outputs']['license']['sha256'], 'Bundled Natural Earth license')
    module_path = Path(__file__).resolve()
    _, module_sha = _local_file(module_path)
    local_files = ((str(BASEMAP_PATH), data_sha), (str(PROVENANCE_PATH), provenance_sha),
                   (str(LICENSE_PATH), license_sha), (str(module_path), module_sha))
    return _decode_basemap(data_raw, provenance_raw, local_files)


def validate_default_basemap_fingerprint(fingerprint):
    """Check a reported data fingerprint against the verified offline bundle.

    Returns False for a different fingerprint. Missing files and integrity
    failures raise the same exceptions as ``load_default_basemap()``.
    """
    return isinstance(fingerprint, str) and load_default_basemap()['sha256'] == fingerprint


def main():
    """Print machine-readable evidence after checking the entire local bundle."""
    data = load_default_basemap()
    provenance = data['provenance']
    print(json.dumps({'status': 'verified', 'sha256': data['sha256'],
                      'upstream': provenance['upstream'],
                      'feature_counts': provenance['feature_counts'],
                      'crs': provenance['crs'],
                      'outputs': provenance['outputs']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
