#!/usr/bin/env python3
"""Create a blank 12-slot locked-series project; does not invent facts or render.

Choose/adapt the new person's theme explicitly. Layout coordinates and fonts
remain in the packaged master; the generated plan deliberately fails preflight
until researched content, route and animated artwork are implemented.
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True, help='传主人物姓名')
    parser.add_argument('--title', required=True, help='本期片名，固定字号下应保持简短')
    parser.add_argument('--theme', required=True, help='该人物主题JSON路径，或包内主题名，如libai/sushi；不得省略后默用杜甫')
    parser.add_argument('--output', required=True, type=Path, help='新的空项目目录；拒绝覆盖非空目录')
    parser.add_argument('--audio', type=Path, default=SKILL_ROOT/'assets/fixed-bgm.m4a', help='默认本系列固定配乐；仅用户明确更换时指定')
    args = parser.parse_args()
    if not args.name.strip() or not args.title.strip():
        parser.error('姓名与片名须非空')
    candidates = [Path(args.theme).expanduser(), SKILL_ROOT/args.theme,
                  SKILL_ROOT/'assets/series/themes'/(args.theme if args.theme.endswith('.json') else args.theme+'.json')]
    theme_path = next((path.resolve() for path in candidates if path.is_file()), None)
    if theme_path is None:
        parser.error('找不到主题JSON；新人物可先自行选择配色与背景母题并写出新主题，无需另加用户确认')
    try:
        theme = json.loads(theme_path.read_text(encoding='utf-8'))
        if not isinstance(theme, dict) or theme.get('person') != args.name.strip():
            parser.error('主题person须对应本人物；请先改造该人物主题，不能把其他人物主题改名后直接套用')
        if not isinstance(theme.get('colors'), dict) or any(not re.fullmatch(r'#[0-9a-fA-F]{6}', str(theme['colors'].get(role, ''))) for role in ['paper','ink','muted','accent','assessment']):
            parser.error('主题缺少必需HEX颜色角色')
        style_path = SKILL_ROOT/'assets/series/series_style.json'
        style = json.loads(style_path.read_text(encoding='utf-8'))
        if theme.get('profile_id', style['profile_id']) != style['profile_id']:
            parser.error('主题profile_id与当前系列母版不一致')
        template = json.loads((SKILL_ROOT/'assets/templates/project.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not args.audio.is_file():
        parser.error('固定配乐文件缺失')
    target = args.output.expanduser().resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        parser.error('拒绝覆盖非空目录，请指定新目录')
    for directory in ['data', 'references', 'art', 'audio', 'output', 'qa', 'style']:
        (target/directory).mkdir(parents=True, exist_ok=True)
    audio_target = target/'audio'/('locked-bgm'+args.audio.suffix.lower())
    shutil.copy2(args.audio, audio_target)
    shutil.copy2(theme_path, target/'style/theme.json')
    video = style['video']
    cuts = video['cut_frames']
    scenes, backgrounds = [], []
    for index, (start, end) in enumerate(zip(cuts, cuts[1:]), 1):
        sid = f'S{index:02d}'
        scenes.append({'id': sid, 'index': index, 'kind': 'opening' if index == 1 else 'ending' if index == len(cuts)-1 else 'chapter',
                       'stage_profile': 'open_air', 'start_frame': start, 'end_frame': end,
                       'location_intro_sec': 0 if index == 1 else style['standard']['meta']['start'],
                       'title': '', 'meta': '', 'period': '', 'place': '', 'event': '',
                       'event_summary': '', 'assessment': '', 'explanation': '',
                       'quote_lines': [], 'source_label': '', 'source_ids': [],
                       'local_action': '', 'environment_action': '', 'action_sample_frames': [], 'visible_visit_ids': []})
        backgrounds.append({'scene_id': sid, 'setting': '', 'composition': '', 'buildings': '', 'props': '', 'light': '', 'source_basis': '', 'source_ids': []})
    template.update({'schema_version': style['schema_version'], 'series_profile_id': style['profile_id'],
                     'series_profile_sha256': hashlib.sha256(style_path.read_bytes()).hexdigest(),
                     'name': args.name.strip(), 'orientation': 'portrait',
                     'width': video['width'], 'height': video['height'], 'fps': video['fps'],
                     'duration_sec': video['duration_sec'], 'total_frames': cuts[-1], 'cut_frames': cuts,
                     'person': {'name': args.name.strip(), 'film_title': args.title.strip(), 'birth_death': '', 'opening_meta': ''},
                     'storyboard': 'data/storyboard.json', 'route': 'data/life_route.json', 'theme': 'style/theme.json',
                     'map': {'show_title': False, 'layout': 'locked_series_panel', 'required': True,
                             'basemap_policy': 'bundled_default', 'readability_checks': 'required',
                             'note': '自动采用包内有来源的海岸与河流底图；补齐人物路线即可渲染，无需另选地理文件。'},
                     'art_provider': 'art/scene_provider.py', 'art_dependencies': ['art'], 'background_policy': 'per_scene',
                     'art_direction': {'rationale': '', 'motifs': [], 'backgrounds': backgrounds},
                     'audio': {'path': audio_target.relative_to(target).as_posix(), 'sha256': hashlib.sha256(audio_target.read_bytes()).hexdigest(), 'policy': 'preserve_exact_audio_payload'}})
    write_json(target/'project.json', template)
    write_json(target/'data/storyboard.json', {'schema_version': style['schema_version'], 'series_profile_id': style['profile_id'], 'scenes': scenes})
    route = json.loads((SKILL_ROOT/'assets/templates/life_route.json').read_text(encoding='utf-8'))
    route['schema_version'] = style['schema_version']
    route['scene_order'] = [scene['id'] for scene in scenes]
    route['per_scene'] = {
        scene['id']: {'start_index': 0, 'end_index': 0, 'no_new_movement': True,
                      'location_intro_sec': scene['location_intro_sec']}
        for scene in scenes
    }
    write_json(target/'data/life_route.json', route)
    with (target/'references/source_ledger.csv').open('w', newline='', encoding='utf-8') as handle:
        csv.writer(handle).writerow(['id','status','citation','url_or_path','claim','verification_note'])
    (target/'art/scene_provider.py').write_text('''"""Create original, text-free scene art for this video."""\n\ndef draw_background(scene_id, local_t, full_scene_duration, theme):\n    """Return this scene's independently designed 1080x1920 RGBA scenery."""\n    raise NotImplementedError("Design and render the background for each scene in this project.")\n\ndef draw_art(scene_id, local_t, full_scene_duration, theme):\n    """Return 1080x1920 RGBA animated foreground layers over the scenery."""\n    raise NotImplementedError("Implement the original animated foreground on a transparent canvas.")\n''', encoding='utf-8')
    print(json.dumps({'status': 'blank_series_scaffold_created', 'project': str(target), 'slots': len(scenes),
                      'next': '补齐研究、分章、事件/评价、人物主题美术方向、路线及真实动画provider；当前空计划应当预检失败。'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
