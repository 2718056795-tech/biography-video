#!/usr/bin/env python3
"""Compose one locked-layout frame from a normalized project and artwork.

This is a real frame compositor, not a video or animation generator.
"""
import argparse
import json
from pathlib import Path
from PIL import Image
from series_frame import SeriesFrame


def read_object(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'{path}: expected a JSON object')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path, help='project.json; scenes may be inline or in data/storyboard.json')
    parser.add_argument('--scene', required=True, help='scene id or one-based index')
    parser.add_argument('--time', type=float, default=3.5, help='local scene seconds')
    parser.add_argument('--duration', type=float, help='override only for component preview; otherwise use scene frame window')
    parser.add_argument('--art', required=True, type=Path, help='text-free native1080x1920 artwork RGBA frame')
    parser.add_argument('--map', dest='map_path', type=Path, help='already projected880x430 RGBA layer')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--style', type=Path, help='normally omitted; package series_style.json is the canonical contract')
    args = parser.parse_args()
    project_path = args.project.expanduser().resolve()
    source_paths = [project_path]
    project = read_object(project_path)
    scenes = project.get('scenes')
    if scenes is None:
        board_path = project_path.parent / project.get('storyboard', 'data/storyboard.json')
        source_paths.append(board_path.resolve())
        scenes = read_object(board_path).get('scenes', [])
    if not isinstance(scenes, list) or not scenes:
        parser.error('Project has no scenes')
    index = next((i for i, scene in enumerate(scenes) if scene.get('id') == args.scene), None)
    if index is None:
        try:
            index = int(args.scene) - 1
        except ValueError:
            parser.error('No matching scene id or index')
    if index < 0 or index >= len(scenes):
        parser.error('Scene index is out of range')
    scene = dict(scenes[index])
    scene.setdefault('index', index + 1)
    scene.setdefault('kind', 'opening' if index == 0 else 'ending' if index == len(scenes) - 1 else 'chapter')
    if 'meta' not in scene:
        scene['meta'] = '｜'.join(str(scene.get(key, '')).strip() for key in ('period', 'place')).strip('｜')
    person = project.get('person') or {
        key: project.get(key, '') for key in ('name', 'film_title', 'birth_death', 'opening_meta')
    }
    theme = project.get('theme')
    if isinstance(theme, str):
        theme_path = project_path.parent / theme
        source_paths.append(theme_path.resolve())
        theme = read_object(theme_path)
    elif isinstance(theme, dict) and 'path' in theme and not any(key in theme for key in ('colors', 'palette', 'ink')):
        theme_path = project_path.parent / theme['path']
        source_paths.append(theme_path.resolve())
        theme = read_object(theme_path)
    fps = project.get('fps', 30)
    end_frame = scene.get('end_frame', scene.get('end_frame_exclusive'))
    if args.duration is not None:
        duration = args.duration
    elif isinstance(scene.get('start_frame'), int) and isinstance(end_frame, int):
        duration = (end_frame - scene['start_frame']) / fps
    else:
        parser.error('Scene requires integer start_frame/end_frame, or --duration for a component preview')
    source_paths.append(args.art.resolve())
    if args.map_path:
        source_paths.append(args.map_path.resolve())
    renderer = SeriesFrame(style_path=args.style, theme=theme, person=person, scene_count=len(scenes))
    source_paths.extend([renderer.style_path, *renderer.font_paths.values()])
    for dest in (args.output, args.report):
        if any(dest.resolve() == source.resolve() or (dest.exists() and source.exists() and dest.samefile(source)) for source in source_paths):
            parser.error('Output/report cannot overwrite project, theme, artwork, style or font inputs')
    if args.output.resolve() == args.report.resolve() or (args.output.exists() and args.report.exists() and args.output.samefile(args.report)):
        parser.error('Output image and JSON report need distinct paths')
    art = Image.open(args.art).convert('RGBA')
    map_layer = Image.open(args.map_path).convert('RGBA') if args.map_path else None
    image = renderer.compose(scene, args.time, duration, art, map_layer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(renderer.last_report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output.resolve()), 'report': str(args.report.resolve()),
                      'profile_id': renderer.style['profile_id'], 'scope': 'single composed frame, not a completed video'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
