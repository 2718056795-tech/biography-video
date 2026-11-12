#!/usr/bin/env python3
"""Migrate known published 2.1 project metadata to the 2.2 map contract.

The default is a read-only change report; --apply writes the listed files.
Historical content, route data, artwork, colors, timing and typography are
preserved. Original project-local files are backed up before replacement.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from series_frame import DEFAULT_STYLE, FORBIDDEN_OVERRIDES

LEGACY_PROFILE_ID = 'biography-paper-cut-series-2.0'
LEGACY_STYLE_SHA256 = '43deba6023e50ff117e5b74ceccbc8d4bb4f5b08e1e4aa9f0982465bd9b5e6f0'


def read_object(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected a JSON object: {path}')
    return value


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def migration_plan(project_path):
    project_path = project_path.expanduser().resolve()
    base = project_path.parent
    style = read_object(DEFAULT_STYLE)
    style_hash = hashlib.sha256(DEFAULT_STYLE.read_bytes()).hexdigest()
    original = read_object(project_path)
    project = deepcopy(original)
    ids = [project[key] for key in ('series_profile_id', 'style_profile_id') if key in project]
    binding = (ids[0] if ids else None, project.get('series_profile_sha256'))
    if not ids or any(value != ids[0] for value in ids):
        raise ValueError('Project needs one consistent, known series profile binding')
    if binding not in ((LEGACY_PROFILE_ID, LEGACY_STYLE_SHA256), (style['profile_id'], style_hash)):
        raise ValueError('Unknown or altered series profile; only the published 2.1 binding or current 2.2 binding can migrate')
    if project.get('schema_version') not in ('2.0', '2.1', style['schema_version']):
        raise ValueError('Unknown series project schema_version')
    for key in ('width', 'height', 'fps', 'duration_sec', 'cut_frames'):
        if project.get(key) != style['video'][key]:
            raise ValueError(f'project.{key} changes the locked series contract')
    if project.get('total_frames') != style['video']['cut_frames'][-1] or project.get('orientation') != 'portrait':
        raise ValueError('Project total_frames/orientation changes the locked series contract')
    for key in ('header', 'standard', 'bookend', 'footer', 'fonts', 'stage_profiles', 'motion'):
        if key in project and project[key] != style[key]:
            raise ValueError(f'Project {key} overrides the locked series contract')
    if FORBIDDEN_OVERRIDES.intersection(project):
        raise ValueError('Project contains a forbidden layout or font override')
    for key, value in project.get('map', {}).items():
        if key in style['map'] and value != style['map'][key]:
            raise ValueError(f'project.map.{key} overrides the locked series contract')

    # Each destination is project-local. Shared external inputs are copied only
    # when their old metadata needs changing, so other projects remain intact.
    changes = {}
    def plan_file(path, value):
        data = encoded(value)
        if path.is_file() and read_object(path) == value:
            return
        changes[path] = data

    def local_destination(source, relative):
        if source.is_relative_to(base):
            return source
        target = base / relative
        if target.exists():
            raise ValueError(f'Refusing to overwrite an unrelated local copy: {target}')
        return target

    if 'scenes' in project:
        board = project
        board_path = None
    else:
        board_path = (base / project.get('storyboard', 'data/storyboard.json')).resolve()
        board = read_object(board_path)
    if any(board.get(key, LEGACY_PROFILE_ID) not in (LEGACY_PROFILE_ID, style['profile_id'])
           for key in ('series_profile_id', 'style_profile_id')):
        raise ValueError('Storyboard declares an unknown series profile')
    scenes = board.get('scenes')
    cuts = style['video']['cut_frames']
    if not isinstance(scenes, list) or len(scenes) != len(cuts)-1:
        raise ValueError('Project must retain the 12 canonical chapter slots')
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or FORBIDDEN_OVERRIDES.intersection(scene):
            raise ValueError('Scene contains an invalid or forbidden layout override')
        if (scene.get('start_frame'), scene.get('end_frame', scene.get('end_frame_exclusive'))) != (cuts[index], cuts[index+1]):
            raise ValueError(f'Chapter {index+1} changes the canonical frame window')
        if scene.get('stage_profile') not in style['stage_profiles']:
            raise ValueError(f'Chapter {index+1} uses an unknown stage profile')
    board['schema_version'] = style['schema_version']
    board['series_profile_id'] = style['profile_id']
    if 'style_profile_id' in board:
        board['style_profile_id'] = style['profile_id']
    if board_path is not None and board != read_object(board_path):
        destination = local_destination(board_path, 'data/storyboard.json')
        project['storyboard'] = destination.relative_to(base).as_posix()
        plan_file(destination, board)

    theme_value = project.get('theme')
    if isinstance(theme_value, str):
        theme_path = (base / theme_value).resolve()
        theme = read_object(theme_path)
        if theme.get('profile_id', LEGACY_PROFILE_ID) not in (LEGACY_PROFILE_ID, style['profile_id']):
            raise ValueError('Theme declares an unknown series profile')
        if theme.get('profile_id') != style['profile_id']:
            theme['profile_id'] = style['profile_id']
            destination = local_destination(theme_path, 'style/theme.json')
            project['theme'] = destination.relative_to(base).as_posix()
            plan_file(destination, theme)
    elif isinstance(theme_value, dict) and isinstance(theme_value.get('colors'), dict):
        if theme_value.get('profile_id', LEGACY_PROFILE_ID) not in (LEGACY_PROFILE_ID, style['profile_id']):
            raise ValueError('Theme declares an unknown series profile')
        theme_value['profile_id'] = style['profile_id']
    else:
        raise ValueError('Project needs a theme JSON path or an inline theme with colors')

    project['schema_version'] = style['schema_version']
    project['series_profile_id'] = style['profile_id']
    project['series_profile_sha256'] = style_hash
    if 'style_profile_id' in project:
        project['style_profile_id'] = style['profile_id']
    plan_file(project_path, project)
    return base, style, style_hash, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--apply', action='store_true', help='write the listed metadata changes and project-local backups')
    args = parser.parse_args()
    try:
        base, style, style_hash, changes = migration_plan(args.project)
        backups = []
        if args.apply:
            # Check every backup before making any change. Original bytes are
            # preserved, including formatting, with no external-file writes.
            for path in changes:
                if path.exists():
                    backup = base / '.migration-backups/2.2' / path.relative_to(base)
                    data = path.read_bytes()
                    if backup.exists() and backup.read_bytes() != data:
                        raise ValueError(f'Existing migration backup differs; preserve it before retrying: {backup}')
                    backups.append((backup, data))
            for backup, data in backups:
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(data)
            for path, data in changes.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + '.migration-working')
                temporary.write_bytes(data)
                temporary.replace(path)
        result = {'status': 'migrated' if args.apply and changes else 'already_current' if not changes else 'dry_run',
                  'profile_id': style['profile_id'], 'style_sha256': style_hash,
                  'changed_files': [str(path) for path in changes],
                  'backups': [str(path) for path, _ in backups],
                  'preserved': 'Researched facts, route data, artwork, colors, chapter timing, coordinates and fonts'}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f'Migration refused: {exc}\n')


if __name__ == '__main__':
    main()
