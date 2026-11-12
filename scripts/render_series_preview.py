#!/usr/bin/env python3
"""Compose one locked-layout frame from a normalized project and artwork.

This is a real frame compositor, not a video or animation generator.
"""
import argparse
import json
from pathlib import Path
from PIL import Image
from series_frame import SeriesFrame
from series_map import SeriesMap, ensure_map_evidence, load_map_png, save_map_png
from render_series_video import map_source_paths


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
    parser.add_argument('--map', dest='map_path', type=Path, help='official880x430 RGBA PNG with embedded/sidecar evidence; omitted: render project route automatically')
    parser.add_argument('--map-output', type=Path, help='optional save of the actual map PNG and hash-bound .evidence.json for pixel QA')
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
        source_paths.append(Path(str(args.map_path) + '.evidence.json').resolve())
    renderer = SeriesFrame(style_path=args.style, theme=theme, person=person, scene_count=len(scenes))
    route_path = project_path.parent / project.get('route', 'data/life_route.json')
    route = read_object(route_path)
    source_paths.append(route_path.resolve())
    coast_value = project.get('coastline_geojson', route.get('coastline', {}).get('file'))
    coast_path = project_path.parent / coast_value if coast_value else None
    basemap_value = project.get('basemap_geojson', route.get('basemap', {}).get('file'))
    basemap_path = project_path.parent / basemap_value if basemap_value else None
    maps = SeriesMap(route, renderer.style, theme, coastline_geojson=coast_path, basemap_geojson=basemap_path)
    if coast_path:
        source_paths.append(coast_path.resolve())
    if basemap_path:
        source_paths.append(basemap_path.resolve())
    # Source basemap files are inputs too, even when selected by the engine default.
    source_paths.extend(path.resolve() for path in map_source_paths(maps.geometry_report()))
    source_paths.extend([renderer.style_path, *renderer.font_paths.values()])
    destinations = [args.output, args.report]
    if args.map_output:
        destinations.extend([args.map_output, Path(str(args.map_output) + '.evidence.json')])
    for dest in destinations:
        if any(dest.resolve() == source.resolve() or (dest.exists() and source.exists() and dest.samefile(source)) for source in source_paths):
            parser.error('Output/report cannot overwrite project, theme, artwork, style or font inputs')
    for i, dest in enumerate(destinations):
        if any(dest.resolve() == other.resolve() or (dest.exists() and other.exists() and dest.samefile(other)) for other in destinations[:i]):
            parser.error('Output image, map, evidence and JSON report need distinct paths')
    art = Image.open(args.art).convert('RGBA')
    official_map = maps.render(scene['id'], args.time, duration)
    if args.map_path and not Path(str(args.map_path) + '.evidence.json').is_file():
        parser.error('External --map requires its hash-bound <map.png>.evidence.json sidecar; use save_map_png or --map-output')
    map_layer = load_map_png(args.map_path) if args.map_path else official_map
    if args.map_path:
        evidence = ensure_map_evidence(map_layer, scene_id=scene['id'], t=args.time, duration=duration)
        if evidence.get('geometry_sha256') != official_map.info['series_map_evidence'].get('geometry_sha256'):
            parser.error('External map evidence does not match the current project route, sources, style and theme')
    image = renderer.compose(scene, args.time, duration, art, map_layer)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    if args.map_output:
        save_map_png(map_layer, args.map_output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(renderer.last_report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output.resolve()), 'report': str(args.report.resolve()),
                      'profile_id': renderer.style['profile_id'], 'scope': 'single composed frame, not a completed video'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
