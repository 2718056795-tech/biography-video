#!/usr/bin/env python3
"""Render the fixed 120s series using data, an art provider and locked compositors.

Full films copy the complete locked AAC stream. Preview clips explicitly excerpt
the corresponding music interval. Run verify_media.py and the visual checks
after this renderer; its render report is not a delivery-acceptance certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from PIL import Image
from series_frame import DEFAULT_STYLE, SeriesFrame, map_presentation_summary
from series_map import SeriesMap, ensure_map_evidence, save_map_png, validate_map_evidence


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def obj(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected a JSON object: {path}')
    return value


def geometry_hash(report):
    return hashlib.sha256(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def map_source_paths(value):
    """Collect all local, hash-bound basemap/manifest inputs from map evidence."""
    # Upstream provenance can also contain source_files archive members. Read
    # only the engine's explicit runtime dependency locations, never recurse
    # through arbitrary upstream metadata or silently discard missing inputs.
    records = list(value.get('static_files', []))
    for source in value.get('basemap', {}).get('sources', []):
        records.extend(source.get('source_files', []))
        records.extend(source.get('provenance', {}).get('local_files', []))
    return [Path(record['path']) for record in records
            if isinstance(record, dict) and isinstance(record.get('path'), str)
            and isinstance(record.get('sha256'), str)]


def map_qa_summary(checks, path):
    return {'status': checks['status'], 'scene_id': checks['scene_id'],
            'geometry_sha256': checks['geometry_sha256'], 'report': str(path),
            'label_persistence': checks['label_persistence'],
            'samples': [{'checkpoints': sample['checkpoints'], 'frame_index': sample['frame_index'],
                         'local_time_sec': sample['local_time_sec'],
                         'map_image_sha256': sample['map_evidence']['image_sha256'],
                         'map_labels': sample['map_labels'],
                         'readability_passed': sample['map_evidence']['readability']['passed'],
                         'background_readability': sample.get('background_readability')}
                        for sample in checks['samples']]}


def map_checkpoints(maps, scene_id, duration, local_start, count, fps):
    """Sample rendered frames surrounding introductions, growth and arrivals.

    Arrival clocks come from the same engine state used to draw the map. A
    fixed label-layout hash binds every sample to the entire project route.
    """
    indices = {}
    for label, index in [('before', 0), ('mid', count//2), ('after', count-1)]:
        indices.setdefault(index, []).append(label)
    initial_state = maps.frame_state(scene_id, local_start, duration)
    for label, key in [('location_intro', 'location_intro_sec'),
                       ('route_growth', 'route_growth_start_sec')]:
        threshold = initial_state.get(key)
        if isinstance(threshold, (float, int)) and not isinstance(threshold, bool):
            crossing = math.ceil((threshold-local_start)*fps-1e-9)
            for index, side in ((crossing-1, 'before_'), (crossing, 'at_')):
                if 0 <= index < count:
                    indices.setdefault(index, []).append(side+label)
    previous = None
    transitions = []
    for frame in range(count):
        state = maps.frame_state(scene_id, local_start+frame/fps, duration)
        visible = state['visible_label_ids']
        if previous is not None:
            if not set(previous).issubset(visible):
                raise ValueError('An arrived map label disappeared during the clip')
            arrived = [key for key in visible if key not in previous]
            if arrived:
                names = ','.join(arrived)
                indices.setdefault(frame-1, []).append('before_arrival:' + names)
                indices.setdefault(frame, []).append('after_arrival:' + names)
                transitions.append({'frame_index': frame, 'local_time_sec': local_start+frame/fps,
                                    'arrived_label_ids': arrived,
                                    'before_visible_label_ids': previous,
                                    'after_visible_label_ids': visible})
        previous = visible
    return indices, {'status': 'passed', 'checked_native_frames': count,
                     'location_intro_sec': initial_state.get('location_intro_sec'),
                     'route_growth_start_sec': initial_state.get('route_growth_start_sec'),
                     'arrival_transitions': transitions}


def probe(path, count=False):
    command = ['ffprobe', '-v', 'error'] + (['-count_frames'] if count else [])
    command += ['-show_streams', '-show_format', '-of', 'json', str(path)]
    return json.loads(subprocess.check_output(command, text=True))


def same(a, b):
    return a.resolve() == b.resolve() or (a.exists() and b.exists() and a.samefile(b))


def check_background_plan(project, scenes):
    """Require each chapter to explain its own setting and visual composition."""
    if 'background_policy' not in project:
        return
    if project['background_policy'] != 'per_scene':
        raise ValueError('background_policy must be per_scene when specified')
    direction = project.get('art_direction')
    rows = direction.get('backgrounds') if isinstance(direction, dict) else None
    if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
            or [row.get('scene_id') for row in rows] != [scene['id'] for scene in scenes]):
        raise ValueError('Plan a background for each scene in storyboard order')
    used = {}
    for row in rows:
        scene_id = row['scene_id']
        setting, composition = (row.get(key) for key in ('setting', 'composition'))
        if any(not isinstance(value, str) or not value.strip() for value in (setting, composition)):
            raise ValueError(f'{scene_id}: describe the background setting and composition')
        design = tuple(' '.join(value.casefold().split()) for value in (setting, composition))
        if design in used:
            raise ValueError(f'{scene_id} and {used[design]} describe the same background design')
        used[design] = scene_id


def check_background_frames(scenes, fps, draw_art, theme):
    """Catch identical backgrounds at each scene's representative native frame."""
    used = {}
    for scene in scenes:
        count = scene['end_frame'] - scene['start_frame']
        scene_id = scene['id']
        time_sec, duration = (count // 2) / fps, count / fps
        frame = draw_art.background(scene_id, time_sec, duration)
        digest = hashlib.sha256(frame.convert('RGBa').tobytes()).digest()
        if digest in used:
            raise ValueError(f'{scene_id} and {used[digest]} render identical backgrounds; redesign the scene artwork')
        used[digest] = scene_id
        foreground = draw_art.foreground(scene_id, time_sec, duration, theme)
        if foreground.getchannel('A').getextrema()[0] == 255:
            raise ValueError(f'{scene_id}: the foreground covers the entire background at the review frame')


def load_project(path):
    project, base = obj(path), path.parent
    style = obj(DEFAULT_STYLE)
    expected = style['video']
    for key, value in [('width', expected['width']), ('height', expected['height']),
                       ('fps', expected['fps']), ('duration_sec', expected['duration_sec']),
                       ('total_frames', expected['cut_frames'][-1]), ('cut_frames', expected['cut_frames'])]:
        if key in project and project[key] != value:
            raise ValueError(f'project.{key} differs from the series contract')
    for key in ('series_profile_id', 'style_profile_id'):
        if key in project and project[key] != style['profile_id']:
            raise ValueError(f'project.{key} differs from the series contract')
    if project.get('series_profile_sha256', sha(DEFAULT_STYLE)) != sha(DEFAULT_STYLE):
        raise ValueError('project.series_profile_sha256 differs from the series contract')
    board_path = base / project.get('storyboard', 'data/storyboard.json')
    board = project if 'scenes' in project else obj(board_path)
    scenes = board.get('scenes')
    cuts = expected['cut_frames']
    if not isinstance(scenes, list) or len(scenes) != len(cuts)-1:
        raise ValueError('This series edition requires the 12 canonical chapter slots')
    ids = set()
    normalized = []
    for i, row in enumerate(scenes):
        scene = dict(row)
        if not isinstance(scene.get('id'), str) or not scene['id'] or scene['id'] in ids:
            raise ValueError('Scene IDs must be unique nonempty strings')
        ids.add(scene['id'])
        kind = 'opening' if i == 0 else 'ending' if i == len(scenes)-1 else 'chapter'
        for key, value in [('index', i+1), ('kind', kind), ('start_frame', cuts[i])]:
            if key in scene and scene[key] != value:
                raise ValueError(f'{scene["id"]}.{key} changes the canonical slot')
            scene[key] = value
        end = scene.get('end_frame', scene.get('end_frame_exclusive', cuts[i+1]))
        if end != cuts[i+1]:
            raise ValueError(f'{scene["id"]}: end_frame changes the canonical slot')
        scene['end_frame'] = end
        if 'meta' not in scene:
            scene['meta'] = '｜'.join(str(scene.get(k, '')).strip() for k in ('period', 'place')).strip('｜')
        normalized.append(scene)
    check_background_plan(project, normalized)
    person = project.get('person') or {k:project.get(k, '') for k in ('name','film_title','birth_death','opening_meta')}
    theme_path = None
    theme = project.get('theme')
    if isinstance(theme, str):
        theme_path = base/theme
        theme = obj(theme_path)
    elif isinstance(theme, dict) and 'path' in theme and 'colors' not in theme:
        theme_path = base/theme['path']
        theme = obj(theme_path)
    route_path = base/project.get('route', 'data/life_route.json')
    route = obj(route_path)
    coast_value = project.get('coastline_geojson', route.get('coastline', {}).get('file'))
    coast_path = base/coast_value if coast_value else None
    compositor = SeriesFrame(theme=theme, person=person, scene_count=len(scenes))
    if theme.get('person') not in (None, person['name']):
        raise ValueError('The per-person theme belongs to a different subject')
    basemap_value = project.get('basemap_geojson', route.get('basemap', {}).get('file'))
    basemap_path = base/basemap_value if basemap_value else None
    map_renderer = SeriesMap(route, style, theme, coastline_geojson=coast_path, basemap_geojson=basemap_path)
    map_renderer.validate_scene_timings(normalized, expected['fps'])
    map_geometry = map_renderer.geometry_report()
    provider_path = base/project.get('art_provider', 'art/scene_provider.py')
    if not provider_path.is_file():
        raise FileNotFoundError(f'Art provider missing: {provider_path}')
    spec = importlib.util.spec_from_file_location('series_art_' + sha(provider_path)[:12], provider_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    draw_foreground = getattr(module, 'draw_art', None)
    if not callable(draw_foreground):
        raise ValueError('Art provider must define draw_art(scene_id,t,duration,theme)')
    draw_art = draw_foreground
    if project.get('background_policy') == 'per_scene':
        provider_background = getattr(module, 'draw_background', None)
        if not callable(provider_background):
            raise ValueError('Art provider must define draw_background(scene_id,t,duration,theme)')

        def draw_background(scene_id, t, duration):
            frame = provider_background(scene_id, t, duration, theme)
            if not isinstance(frame, Image.Image) or frame.mode != 'RGBA' or frame.size != (compositor.width, compositor.height):
                raise ValueError(f'{scene_id}: draw_background must return a native {compositor.width}x{compositor.height} RGBA frame')
            return frame

        def foreground_frame(scene_id, t, duration, scene_theme):
            foreground = draw_foreground(scene_id, t, duration, scene_theme)
            if (not isinstance(foreground, Image.Image) or foreground.mode != 'RGBA'
                    or foreground.size != (compositor.width, compositor.height)):
                raise ValueError(f'{scene_id}: draw_art must return a matching RGBA foreground')
            return foreground

        def draw_art(scene_id, t, duration, scene_theme):
            return Image.alpha_composite(draw_background(scene_id, t, duration),
                                         foreground_frame(scene_id, t, duration, scene_theme))

        draw_art.background = draw_background
        draw_art.foreground = foreground_frame
    audio_spec = project.get('audio', {})
    audio = base/audio_spec.get('path', '')
    if not audio.is_file() or sha(audio) != audio_spec.get('sha256'):
        raise ValueError('Locked audio is missing or its SHA256 differs from project.audio.sha256')
    original = probe(audio)
    tracks = [s for s in original['streams'] if s.get('codec_type') == 'audio']
    if len(tracks) != 1 or tracks[0].get('codec_name') != 'aac':
        raise ValueError('The locked series soundtrack must contain one AAC track')
    if abs(float(tracks[0].get('duration', original['format']['duration']))-expected['duration_sec']) > .1:
        raise ValueError('Locked audio duration does not match the canonical 120-second film')
    sources = [path, provider_path, audio, route_path, DEFAULT_STYLE,
               Path(__file__), Path(__file__).with_name('series_frame.py'),
               Path(__file__).with_name('series_map.py'), *compositor.font_paths.values()]
    if 'scenes' not in project:sources.append(board_path)
    if theme_path:sources.append(theme_path)
    if coast_path:sources.append(coast_path)
    if basemap_path:sources.append(basemap_path)
    sources.extend(map_source_paths(map_geometry))
    dependencies = [base/'art']+[base/name for name in project.get('art_dependencies', [])]
    for dependency in dependencies:
        if dependency.is_dir():
            sources.extend(f for f in dependency.rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.suffix != '.pyc')
        elif dependency.is_file():sources.append(dependency)
        elif dependency != base/'art':raise FileNotFoundError(f'Art dependency missing: {dependency}')
    sources = sorted({p.resolve() for p in sources}, key=str)
    fingerprint = {str(p):sha(p) for p in sources}
    # Geometry binds the route, projection, labels, source selection and readability
    # policy even when a change is represented by engine-resolved default inputs.
    fingerprint['series_map_geometry_sha256'] = geometry_hash(map_geometry)
    return project, normalized, theme, compositor, map_renderer, draw_art, audio, sources, fingerprint


def render_clip(target, scene, local_start, count, compositor, maps, draw_art, theme, audio=None, global_audio_start=0., fps=30, layout_path=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.stem+'.working.mp4')
    command = ['ffmpeg','-nostdin','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24',
               '-s','1080x1920','-framerate',str(fps),'-i','pipe:0']
    if audio:
        command += ['-ss',str(global_audio_start),'-t',str(count/fps),'-i',str(audio),'-map','0:v:0','-map','1:a:0']
    else:command += ['-an']
    command += ['-frames:v',str(count),'-c:v','libx264','-preset','fast','-crf','18','-threads','2',
                '-pix_fmt','yuv420p','-vf','setsar=1','-r',str(fps),'-g','60','-video_track_timescale','15360']
    if audio:command += ['-c:a','copy','-t',str(count/fps)]
    command += ['-movflags','+faststart',str(temp)]
    duration = (scene['end_frame']-scene['start_frame'])/fps
    inspect_index = min(count-1,max(0,round((min(3.5,duration/2)-local_start)*fps)))
    checks = {'status': 'incomplete', 'scene_id': scene['id'],
              'geometry_sha256': geometry_hash(maps.geometry_report()), 'samples': [],
              'scope': 'Actual before/mid/after rendered map pixels and sourced geography/readability evidence; not historical certification'}
    # Retain coincident checkpoints for short clips and sample both sides of
    # arrivals, which a simple before/mid/after sample can otherwise miss.
    sample_indices, checks['label_persistence'] = map_checkpoints(
        maps, scene['id'], duration, local_start, count, fps)
    map_qa_path = layout_path.with_name(layout_path.stem + '.map-qa.json') if layout_path else target.with_suffix('.map-qa.json')
    def write_map_qa(status, error=None):
        checks['status'] = status
        if error is not None:
            checks['error'] = str(error)
        map_qa_path.parent.mkdir(parents=True, exist_ok=True)
        map_qa_path.write_text(json.dumps(checks, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with target.with_suffix('.encode.log').open('w') as errors:
        process = subprocess.Popen(command,stdin=subprocess.PIPE,stderr=errors)
        try:
            for frame in range(count):
                t = local_start+frame/fps
                art = draw_art(scene['id'],t,duration,theme)
                if not isinstance(art, Image.Image) or art.mode != 'RGBA' or art.size != (1080,1920):
                    raise ValueError('draw_art must return a native1080x1920 RGBA frame')
                map_layer = maps.render(scene['id'],t,duration)
                picture = compositor.compose(scene,t,duration,art,map_layer)
                evidence = compositor.last_report['map_evidence']
                if frame in sample_indices:
                    checks['samples'].append({'checkpoints': sample_indices[frame], 'frame_index': frame,
                                              'local_time_sec': t, 'map_evidence': evidence,
                                              'map_labels': map_presentation_summary(evidence),
                                              'background_readability': compositor.last_report['map_background_readability']})
                process.stdin.write(picture.tobytes())
                if frame == inspect_index and layout_path:
                    layout_path.parent.mkdir(parents=True,exist_ok=True)
                    layout_path.write_text(json.dumps(compositor.last_report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                    picture.save(layout_path.with_name(layout_path.stem+'.frame.png'))
                    save_map_png(map_layer, layout_path.with_name(layout_path.stem+'.map.png'))
                if frame and frame%120 == 0:print(f'{scene["id"]}: {frame}/{count}',flush=True)
            process.stdin.close()
            if process.wait():raise RuntimeError(f'FFmpeg encode failed; see {target.with_suffix(".encode.log")}')
        except BaseException as exc:
            process.kill();process.wait()
            write_map_qa('failed', exc)
            raise
    temp.replace(target)
    write_map_qa('passed')
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--scenes',default='all',help='all or comma-separated scene IDs/one-based numbers; a subset creates parts, not a full film')
    parser.add_argument('--resume',action='store_true',help='reuse only fingerprint/hash/frame-count-matching parts')
    parser.add_argument('--preview-scene',help='make a visibly labelled local sample instead of a complete film')
    parser.add_argument('--preview-seconds',type=float,default=2.)
    parser.add_argument('--preview-start',type=float,default=0.)
    parser.add_argument('--silent-preview',action='store_true',help='preview only; output filename must contain silent or 无声')
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    base=args.project.expanduser().resolve().parent
    report_path=(args.report or base/'qa'/('preview-render.json' if args.preview_scene else 'video-render.json')).expanduser().resolve()
    args.output=args.output.expanduser().resolve()
    if args.output.exists() and not args.overwrite:parser.error('Output already exists; choose a new version path or explicitly use --overwrite')
    result={'status':'incomplete','preview_only':bool(args.preview_scene),'errors':[],
            'acceptance':'not a verify_media/check_delivery or historical/visual certificate'}
    started=time.monotonic()
    safe_to_write_report=False
    try:
        if same(args.project.expanduser(),report_path) or same(args.project.expanduser(),args.output) or same(args.output,report_path):
            parser.error('Output/report cannot overwrite the project or each other')
        for tool in ('ffmpeg','ffprobe'):
            if not shutil.which(tool):raise RuntimeError(f'Required executable missing: {tool}')
        project,scenes,theme,frames,maps,draw,audio,sources,fingerprint=load_project(args.project.expanduser().resolve())
        if any(same(dest,source) for dest in (args.output,report_path) for source in sources) or same(args.output,report_path):
            parser.error('Output/report cannot overwrite any project, style, font, art or audio input')
        safe_to_write_report=True
        fps=frames.style['video']['fps'];audio_before=sha(audio)
        qa=base/'qa/series-layout';qa.mkdir(parents=True,exist_ok=True)
        result.update(profile_id=frames.style['profile_id'],profile_sha256=frames.profile_sha256,
                      theme_id=theme.get('theme_id'),source_audio_sha256=audio_before,
                      source_fingerprint=fingerprint,provider=project.get('art_provider','art/scene_provider.py'),
                      map_geometry_sha256=fingerprint['series_map_geometry_sha256'],map_qa=[])
        (qa/'map-geometry.json').write_text(json.dumps(maps.geometry_report(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        by_id={s['id']:i for i,s in enumerate(scenes)}
        def index(value):
            found=by_id.get(value)
            if found is None:
                try:found=int(value)-1
                except ValueError:raise ValueError(f'Unknown scene: {value}')
            if not 0<=found<len(scenes):raise ValueError(f'Unknown scene: {value}')
            return found
        if args.preview_scene:
            scene=scenes[index(args.preview_scene)]
            duration=(scene['end_frame']-scene['start_frame'])/fps
            count=round(args.preview_seconds*fps)
            if not math.isfinite(args.preview_seconds) or not math.isfinite(args.preview_start) or abs(count/fps-args.preview_seconds)>1e-6 or abs(round(args.preview_start*fps)-args.preview_start*fps)>1e-6 or count<1 or args.preview_start<0 or args.preview_start+count/fps>duration:
                raise ValueError('Preview needs a positive integer-frame duration entirely within the scene')
            if args.silent_preview and not any(s in args.output.stem.lower() for s in ('silent','无声')):
                raise ValueError('A silent preview filename must explicitly contain silent or 无声')
            map_checks = render_clip(args.output,scene,args.preview_start,count,frames,maps,draw,theme,
                        audio=None if args.silent_preview else audio,
                        global_audio_start=scene['start_frame']/fps+args.preview_start,
                        fps=fps,layout_path=qa/f'{scene["id"]}.json')
            result['map_qa'].append(map_qa_summary(map_checks, qa/f'{scene["id"]}.map-qa.json'))
            expected_count=count
            result.update(status='preview_rendered',scene_id=scene['id'],local_start_sec=args.preview_start,
                          source_audio_excerpt_start_sec=scene['start_frame']/fps+args.preview_start,
                          audio_method='none, explicitly labelled' if args.silent_preview else 'corresponding original AAC excerpt, stream copied')
        else:
            if args.silent_preview:raise ValueError('--silent-preview is only valid with --preview-scene')
            selected=list(range(len(scenes))) if args.scenes=='all' else sorted({index(value.strip()) for value in args.scenes.split(',')})
            if project.get('background_policy') == 'per_scene':
                check_background_frames([scenes[i] for i in selected], fps, draw, theme)
            parts=base/'output/.series-parts';parts.mkdir(parents=True,exist_ok=True)
            for i in selected:
                scene=scenes[i];target=parts/f'part_{i+1:02d}.mp4';cache=target.with_suffix('.inputs.json')
                count=scene['end_frame']-scene['start_frame'];valid=False
                if args.resume and target.is_file() and cache.is_file():
                    record=obj(cache)
                    if record.get('source_fingerprint')==fingerprint and record.get('clip_sha256')==sha(target):
                        streams=[s for s in probe(target)['streams'] if s.get('codec_type')=='video']
                        valid=len(streams)==1 and int(streams[0].get('nb_frames',0))==count and (streams[0]['width'],streams[0]['height'])==(1080,1920)
                        map_qa_path = qa/f'{scene["id"]}.map-qa.json'
                        if valid and map_qa_path.is_file():
                            map_checks = obj(map_qa_path)
                            valid = map_checks.get('status') == 'passed' and map_checks.get('geometry_sha256') == fingerprint['series_map_geometry_sha256'] and bool(map_checks.get('samples'))
                            if valid:
                                try:
                                    expected_indices, expected_persistence = map_checkpoints(maps, scene['id'], count/fps, 0., count, fps)
                                    if (map_checks.get('label_persistence') != expected_persistence
                                            or {sample.get('frame_index') for sample in map_checks['samples']} != set(expected_indices)):
                                        raise ValueError('Cached clip lacks map arrival checkpoints')
                                    for sample in map_checks['samples']:
                                        validate_map_evidence(sample.get('map_evidence'), scene_id=scene['id'], t=sample.get('local_time_sec'), duration=count/fps)
                                        if (sample.get('map_labels') != map_presentation_summary(sample['map_evidence'])
                                                or sample.get('checkpoints') != expected_indices[sample['frame_index']]
                                                or sample.get('local_time_sec') != sample['frame_index']/fps):
                                            raise ValueError('Cached clip map label state differs from its official frame')
                                        background_check = sample.get('background_readability', {})
                                        if (background_check.get('status') != 'passed' or background_check.get('passed') is not True
                                                or background_check.get('engine_sha256') != sample['map_evidence'].get('engine_sha256')
                                                or background_check.get('map_image_sha256') != sample['map_evidence'].get('image_sha256')):
                                            raise ValueError('Cached clip lacks valid actual-art map readability evidence')
                                except (ValueError, OSError, KeyError, TypeError):
                                    valid = False
                        else:
                            valid = False
                if not valid:
                    map_checks = render_clip(target,scene,0.,count,frames,maps,draw,theme,fps=fps,layout_path=qa/f'{scene["id"]}.json')
                    cache.write_text(json.dumps({'source_fingerprint':fingerprint,'clip_sha256':sha(target)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                result['map_qa'].append(map_qa_summary(map_checks, qa/f'{scene["id"]}.map-qa.json'))
                print(f'finished {scene["id"]}',flush=True)
            if len(selected)!=len(scenes):
                result.update(status='segments_rendered',complete_film=False,selected_scenes=[scenes[i]['id'] for i in selected],parts=str(parts))
                return finish(result,report_path,started,0)
            listing=parts/'concat.txt';listing.write_text(''.join(f"file 'part_{i+1:02d}.mp4'\n" for i in range(len(scenes))),encoding='utf-8')
            args.output.parent.mkdir(parents=True,exist_ok=True)
            temp=args.output.with_name(args.output.stem+'.working.mp4')
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-i',str(audio),
                            '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','copy','-movflags','+faststart',str(temp)],check=True)
            temp.replace(args.output);expected_count=frames.style['video']['cut_frames'][-1]
            result.update(status='full_film_rendered',complete_film=True,audio_method='complete original AAC stream copy, no trim/fade/retime')
        measured=probe(args.output,count=True)
        video=next(s for s in measured['streams'] if s.get('codec_type')=='video')
        if int(video.get('nb_read_frames',0))!=expected_count or (video['width'],video['height'])!=(1080,1920) or video['avg_frame_rate']!='30/1' or video.get('pix_fmt')!='yuv420p' or video.get('sample_aspect_ratio')!='1:1':
            raise RuntimeError('Actual encoded video frames/geometry differ from the requested render')
        if sha(audio)!=audio_before:raise RuntimeError('Original audio source changed during rendering')
        result.update(output=str(args.output),output_sha256=sha(args.output),actual_decoded_video_frames=int(video['nb_read_frames']),
                      source_audio_unchanged=True,media=measured,
                      next_checks=['verify_media.py for a full film, not a preview','actual encoded-frame motion/content review','verify_cover.py','check_delivery.py'])
        return finish(result,report_path,started,0)
    except Exception as exc:
        result['status']='failed';result['errors'].append(str(exc))
        if not safe_to_write_report:
            result['report_not_written']='Inputs were not fully validated; refusing to risk overwriting an input'
            print(json.dumps(result,ensure_ascii=False),file=sys.stderr)
            return 1
        return finish(result,report_path,started,1)


def finish(result,path,started,code):
    result['elapsed_sec']=round(time.monotonic()-started,3)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'report':str(path),'errors':result['errors']},ensure_ascii=False),flush=True)
    return code


if __name__=='__main__':
    raise SystemExit(main())
