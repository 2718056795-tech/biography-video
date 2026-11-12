#!/usr/bin/env python3
"""Check planning completeness, declared evidence and input hashes; not factual truth or rendered motion."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


def check(root):
    errors = []
    def require(condition, message):
        if not condition:
            errors.append(message)
    def load(relative):
        try:
            value = json.loads((root / relative).read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                errors.append(f'{relative}: 顶层须为JSON对象')
                return {}
            return value
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f'{relative}: {exc}')
            return {}
    project = load('project.json')
    board = project if 'scenes' in project else load(project.get('storyboard', 'data/storyboard.json'))
    route = load(project.get('route', 'data/life_route.json'))
    map_preflight = {'status': 'not_run', 'scope': 'Technical map input/readability checks; not historical validation'}
    def records(value, context):
        if not isinstance(value, list):
            errors.append(f'{context}: 须为数组')
            return []
        require(all(isinstance(item, dict) for item in value), f'{context}: 每项须为对象')
        return [item for item in value if isinstance(item, dict)]
    def identifier(value):
        return isinstance(value, str) and bool(value.strip())
    positive_int = lambda value: isinstance(value, int) and not isinstance(value, bool) and value > 0
    for key in ['width', 'height', 'fps', 'duration_sec', 'total_frames']:
        require(positive_int(project.get(key)), f'project.{key}须为正整数')
    if all(positive_int(project.get(k)) for k in ['fps', 'duration_sec', 'total_frames']):
        require(project['total_frames'] == project['fps'] * project['duration_sec'], 'total_frames与时长×帧率不一致')
    require(bool(str(project.get('name', '')).strip()), '人物姓名缺失')
    require(project.get('orientation') in ['portrait', 'landscape'], '画幅方向缺失')
    if positive_int(project.get('width')) and positive_int(project.get('height')):
        require((project['height'] > project['width']) == (project.get('orientation') == 'portrait'), '尺寸与画幅方向不符')
    cover = project.get('cover', {})
    require(isinstance(cover, dict), 'cover须为对象；封面是必交项')
    if isinstance(cover, dict):
        require(cover.get('required') is True, '封面必须为必交项，不能默认省略')
        default_cover = (cover.get('width'), cover.get('height'), cover.get('orientation'), cover.get('format')) == (1200, 1500, 'portrait', 'PNG')
        override = cover.get('explicit_user_override')
        require(default_cover or (isinstance(override, str) and bool(override.strip())), '默认封面须为1200×1500 PNG竖屏；其他规格需记录用户明确要求')
        require(bool(cover.get('path')) and isinstance(cover.get('path'), str), '缺少封面交付路径')
        if default_cover:
            require(cover.get('long_short_ratio') == '5:4' and cover.get('width_height_ratio') == '4:5', '“5:4竖屏”指长短边5:4，实际宽高4:5，不能颠倒')
    map_config = project.get('map', {})
    require(isinstance(map_config, dict) and map_config.get('show_title') is False, '默认地图应去掉字面“一生足迹”标题，使用地点标签')
    if isinstance(map_config, dict):
        require(map_config.get('required') is not False and map_config.get('enabled') is not False,
                '系列地图为每帧必需项，不能禁用或设为可选')
        require(map_config.get('readability_checks') not in (False, 'disabled', 'off'), '地图可读性检查不能禁用')
    sources = {}
    try:
        with (root / 'references/source_ledger.csv').open(newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                sid = (row.get('id') or '').strip()
                require(bool(sid) and sid not in sources, '史料ID缺失或重复')
                sources[sid] = row
    except OSError as exc:
        errors.append(f'史料台账不可读: {exc}')
    def evidence(ids, context):
        require(isinstance(ids, list) and bool(ids), f'{context}: 缺少source_ids')
        if not isinstance(ids, list):
            return
        for sid in ids:
            if not identifier(sid):
                errors.append(f'{context}: 史料ID须为非空字符串')
                continue
            row = sources.get(sid)
            require(row is not None, f'{context}: 未登记史料{sid}')
            if row:
                require(row.get('status') == 'verified' and all((row.get(k) or '').strip() for k in ['citation', 'url_or_path', 'claim', 'verification_note']), f'{context}: {sid}缺少已核查声明或证据记录')
    scenes = records(board.get('scenes', []), 'scenes')
    require(bool(scenes), '分镜为空，不能制作或验收')
    series_declared = 'series_profile_id' in project or 'style_profile_id' in project
    series_backgrounds = []
    if series_declared:
        theme = None
        try:
            master_path = Path(__file__).resolve().parents[1] / 'assets/series/series_style.json'
            master = json.loads(master_path.read_text(encoding='utf-8'))
            declared = project.get('series_profile_id', project.get('style_profile_id'))
            require(declared == master['profile_id'], '系列profile ID与固定母版不一致')
            require(project.get('schema_version') == master['schema_version'], '系列项目schema_version与当前母版不一致')
            require(board.get('schema_version') == master['schema_version'], '系列分镜schema_version与当前母版不一致')
            if 'series_profile_id' in project and 'style_profile_id' in project:
                require(project['series_profile_id'] == project['style_profile_id'], '两种profile ID字段互相冲突')
            master_hash = hashlib.sha256(master_path.read_bytes()).hexdigest()
            if 'series_profile_sha256' in project:
                require(project['series_profile_sha256'] == master_hash, '系列计划绑定的母版SHA256已变化')
            lock_path = master_path.parent / 'series_manifest.json'
            if lock_path.is_file():
                lock = json.loads(lock_path.read_text(encoding='utf-8'))
                require(isinstance(lock, dict) and lock.get('style_sha256') == master_hash, '系列母版与锁定manifest不一致')
            for key in ['width', 'height', 'fps', 'duration_sec']:
                require(project.get(key) == master['video'][key], f'系列{key}不得改动固定母版值')
            require(project.get('orientation') == 'portrait' and project.get('total_frames') == master['video']['cut_frames'][-1], '系列方向/总帧数偏离母版')
            require(project.get('cut_frames') == master['video']['cut_frames'], '系列12槽切点不得改动')
            require(len(scenes) == len(master['video']['cut_frames']) - 1, '系列必须有固定12槽')
            for group in ['header', 'standard', 'bookend', 'footer', 'fonts', 'stage_profiles', 'motion']:
                if group in project:
                    require(project[group] == master[group], f'项目{group}不能覆盖母版坐标、字号或字体')
            for key in ['layout_override', 'layout_overrides', 'positions', 'font_overrides', 'stage_scale', 'stage_offset_y', 'font_size', 'font_family']:
                require(key not in project, f'系列项目不得设置{key}')
            if isinstance(map_config, dict):
                for key, value in master['map'].items():
                    if key in map_config:
                        require(map_config[key] == value, f'项目map.{key}偏离母版')
            if isinstance(cover, dict):
                require((cover.get('width'), cover.get('height'), cover.get('orientation'), cover.get('format')) == (master['cover']['width'], master['cover']['height'], 'portrait', 'PNG'), '系列封面必须保持母版1200×1500 PNG')
            forbidden_scene_fields = {'layout_override', 'layout_overrides', 'positions', 'font_overrides', 'title_x', 'title_y', 'meta_x', 'meta_y', 'quote_x', 'quote_y', 'event_x', 'event_y', 'assessment_x', 'assessment_y', 'stage_scale', 'stage_offset_y', 'font_size', 'font_family'}
            cuts = master['video']['cut_frames']
            for index, scene in enumerate(scenes):
                if index >= len(cuts)-1:
                    break
                require(scene.get('id') == f'S{index+1:02d}' and type(scene.get('index')) is int and scene['index'] == index+1, '系列槽ID/index必须按S01—S12顺序')
                require((scene.get('start_frame'), scene.get('end_frame')) == (cuts[index], cuts[index+1]), f'S{index+1:02d}: 系列固定帧窗被改动')
                expected_kind = 'opening' if index == 0 else 'ending' if index == len(cuts)-2 else 'chapter'
                require(scene.get('kind') == expected_kind, f'S{index+1:02d}: 开篇/章节/收束类型错误')
                stage = scene.get('stage_profile')
                require(identifier(stage) and stage in master['stage_profiles'], f'S{index+1:02d}: stage_profile不在固定枚举内')
                require(not forbidden_scene_fields.intersection(scene), f'S{index+1:02d}: 不能添加任意版位覆盖字段')
                require(identifier(scene.get('meta')), f'S{index+1:02d}: 缺少实际上屏的年代地点meta')
            person = project.get('person', {})
            require(isinstance(person, dict), '系列person须为对象')
            if isinstance(person, dict):
                for key in ['name', 'film_title', 'birth_death', 'opening_meta']:
                    require(identifier(person.get(key)), f'person.{key}缺失；史料不明须明确写约年/范围，不留空冒充完成')
                require(person.get('name') == project.get('name'), '人物姓名字段不一致')
            theme_value = project.get('theme')
            require(identifier(theme_value), '系列theme须为明确的人物主题JSON相对路径')
            if identifier(theme_value):
                theme = load(theme_value)
                require(theme.get('profile_id', master['profile_id']) == master['profile_id'], '主题profile_id与当前系列母版不一致')
                require(theme.get('person') == project.get('name'), '主题人物与本期人物不符，不得默认套用杜甫')
                colors = theme.get('colors', {})
                require(isinstance(colors, dict), '主题colors须为对象')
                if isinstance(colors, dict):
                    required_roles = {'paper','ink','muted','accent','assessment','map_ink','map_accent','map_halo','map_coast'}
                    require(required_roles.issubset(colors), '主题缺少排版/地图颜色角色')
                    require(all(isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) for value in colors.values()), '主题颜色须为#RRGGBB')
                require(identifier(theme.get('rationale')), '主题须有本人物配色与母题依据')
            provider = project.get('art_provider')
            require(identifier(provider) and (root/provider).is_file(), '系列art_provider代码文件缺失；实际动画仍须渲染验证')
            direction = project.get('art_direction', {})
            require(isinstance(direction, dict), 'art_direction须为本人物美术方向对象')
            if isinstance(direction, dict):
                require(identifier(direction.get('rationale')), 'art_direction缺少本人物美术方向理由')
                motifs = direction.get('motifs')
                require(isinstance(motifs, list) and 1 <= len(motifs) <= 3 and all(identifier(motif) for motif in motifs), 'art_direction须有1—3个本人物母题')
                series_backgrounds = records(direction.get('backgrounds', []), 'art_direction.backgrounds')
                require(len(series_backgrounds) == len(cuts)-1, '每个系列槽都需要独立场景美术说明')
                for index, background in enumerate(series_backgrounds):
                    require(background.get('scene_id') == f'S{index+1:02d}', '美术场景须按S01—S12关联')
                    for key in ['setting', 'buildings', 'props', 'light', 'source_basis']:
                        require(identifier(background.get(key)), f'{background.get("scene_id")}: 美术{key}缺失')
            # Reuse the production map engine so missing geography, unsourced
            # overrides, failed labels/contrast and unsupported views fail here.
            from series_map import SeriesMap, ensure_map_evidence
            from render_series_video import map_checkpoints
            coast_value = project.get('coastline_geojson', route.get('coastline', {}).get('file'))
            coast_path = root/coast_value if coast_value else None
            basemap_value = project.get('basemap_geojson', route.get('basemap', {}).get('file'))
            basemap_path = root/basemap_value if basemap_value else None
            maps = SeriesMap(route, master, theme, coastline_geojson=coast_path, basemap_geojson=basemap_path)
            maps.validate_scene_timings(scenes, master['video']['fps'])
            samples, chapter_persistence = [], []
            previous_labels = []
            for scene in scenes:
                fps = master['video']['fps']
                count = scene['end_frame']-scene['start_frame']
                duration = count/fps
                checkpoints, persistence = map_checkpoints(maps, scene['id'], duration, 0., count, fps)
                first_labels = maps.frame_state(scene['id'], 0., duration)['visible_label_ids']
                if not set(previous_labels).issubset(first_labels):
                    raise ValueError(f'{scene["id"]}: 已到达地名未在下一章节保留')
                chapter_persistence.append({'scene_id': scene['id'], 'status': 'passed',
                                            'retained_from_previous_chapter': previous_labels,
                                            'start_visible_label_ids': first_labels,
                                            **persistence})
                for frame, labels in sorted(checkpoints.items()):
                    t = frame/fps
                    evidence_record = ensure_map_evidence(maps.render(scene['id'], t, duration),
                                                          scene_id=scene['id'], t=t, duration=duration)
                    samples.append({'scene_id': scene['id'], 'time_sec': t,
                                    'checkpoints': labels,
                                    'visible_label_ids': evidence_record['visible_label_ids'],
                                    'label_layout_sha256': evidence_record['label_layout_sha256'],
                                    'image_sha256': evidence_record.get('image_sha256'),
                                    'readability_passed': evidence_record.get('readability', {}).get('passed') is True})
                previous_labels = maps.frame_state(scene['id'], (count-1)/fps, duration)['visible_label_ids']
            map_geometry = maps.geometry_report()
            map_preflight.update(status='passed', samples=samples,
                                 label_layouts=map_geometry['label_layouts'],
                                 route_stroke_policy=map_geometry['route_stroke_policy'],
                                 label_persistence=chapter_persistence,
                                 basemap={key:value for key,value in map_geometry.get('basemap', {}).items() if key != 'geometry'},
                                 readability=map_geometry.get('readability'),
                                 geometry_sha256=hashlib.sha256(json.dumps(map_geometry, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest())
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f'系列计划配置不可用: {exc}')
            map_preflight.update(status='failed', error=str(exc))
    for background in series_backgrounds:
        evidence(background.get('source_ids'), f'美术场景{background.get("scene_id")}')
    scene_ids, previous_end, previous_visits = set(), 0, []
    for scene in scenes:
        sid = scene.get('id')
        if not identifier(sid):
            errors.append('场景ID须为非空字符串')
            sid = ''
        require(bool(sid) and sid not in scene_ids, '场景ID缺失或重复')
        scene_ids.add(sid)
        for key in ['title', 'period', 'place', 'event', 'local_action', 'environment_action']:
            require(bool(str(scene.get(key, '')).strip()), f'{sid}: {key}缺失；每章需要独立标题和动作')
        for key in ['event_summary', 'assessment']:
            value = scene.get(key)
            require(isinstance(value, str) and bool(value.strip()), f'{sid}: {key}须为非空短句；含诗句的幕也须有实际显示的事件说明和原创解读')
        if all(isinstance(scene.get(key), str) and scene[key].strip() for key in ['event_summary', 'assessment']):
            require(scene['event_summary'].strip() != scene['assessment'].strip(), f'{sid}: 事件说明与原创解读不能直接重复')
        start, end = scene.get('start_frame'), scene.get('end_frame')
        valid_window = all(isinstance(v, int) and not isinstance(v, bool) for v in [start, end]) and start >= 0 and end > start
        require(valid_window, f'{sid}: 需合法整数帧窗口[起点,终点)')
        if valid_window:
            require(start == previous_end, f'{sid}: 分镜时间不连续')
            previous_end = end
            samples = scene.get('action_sample_frames', [])
            valid_samples = isinstance(samples, list) and all(isinstance(v, int) and not isinstance(v, bool) and start <= v < end for v in samples)
            require(valid_samples and len(set(samples)) >= 2, f'{sid}: 至少两个不同的幕内动作取样帧')
        evidence(scene.get('source_ids'), f'场景{sid}')
        visits = scene.get('visible_visit_ids', [])
        opening = scene is scenes[0] and scene.get('kind') == 'opening'
        valid_visits = (visits == [] if opening else
                        isinstance(visits, list) and bool(visits) and all(identifier(vid) for vid in visits))
        require(valid_visits, f'{sid}: 开篇足迹须为空数组' if opening else f'{sid}: 累计足迹须为非空访问ID数组')
        if valid_visits:
            require(visits[:len(previous_visits)] == previous_visits, f'{sid}: 旧足迹被删除或顺序改变')
            previous_visits = visits
    if len(scenes) >= 2:
        require(len({str(scene.get('title', '')).strip() for scene in scenes}) > 1, '全部章节标题相同，应按人生节点使用独立章节标题')
    require(previous_end == project.get('total_frames'), '分镜帧窗口未覆盖完整片长')
    nodes = records(route.get('nodes', []), 'nodes')
    visits = records(route.get('visits', []), 'visits')
    segments = records(route.get('segments', []), 'segments')
    require(bool(nodes), '足迹节点为空')
    require(bool(visits), '足迹访问序列为空')
    node_ids, visit_ids = set(), set()
    for node in nodes:
        nid = node.get('id')
        if not identifier(nid):
            errors.append('地点ID须为非空字符串')
            nid = ''
        require(bool(nid) and nid not in node_ids, '地点ID缺失或重复')
        node_ids.add(nid)
        require(bool(node.get('label')) and node.get('precision') in ['city_approx', 'region_approx', 'sourced_exact'], f'{nid}: 地名或定位精度声明缺失')
        require(isinstance(node.get('lon'), (int, float)) and -180 <= node['lon'] <= 180 and isinstance(node.get('lat'), (int, float)) and -90 <= node['lat'] <= 90, f'{nid}: 经纬度无效')
    for visit in visits:
        vid = visit.get('id')
        if not identifier(vid):
            errors.append('访问ID须为非空字符串')
            vid = ''
        require(bool(vid) and vid not in visit_ids, '访问ID缺失或重复；回访须新建visit但复用node')
        visit_ids.add(vid)
        require(identifier(visit.get('node_id')) and visit['node_id'] in node_ids, f'{vid}: 地点节点不存在')
        require(identifier(visit.get('scene_id')) and visit['scene_id'] in scene_ids and bool(visit.get('period')), f'{vid}: 幕/时期关联缺失')
        evidence(visit.get('source_ids'), f'访问{vid}')
    ordered_visits = [visit.get('id') for visit in visits]
    scene_order = {scene.get('id'): i for i, scene in enumerate(scenes) if identifier(scene.get('id'))}
    visit_scenes = {visit['id']: visit.get('scene_id') for visit in visits if identifier(visit.get('id'))}
    for current_index, scene in enumerate(scenes):
        ids = scene.get('visible_visit_ids', [])
        if isinstance(ids, list) and all(identifier(vid) for vid in ids):
            require(ids == ordered_visits[:len(ids)], f'{scene.get("id")}: 可见足迹必须为全局访问序列的完整有序前缀')
            require(all(scene_order.get(visit_scenes.get(vid), len(scenes)) <= current_index for vid in ids), f'{scene.get("id")}: 不能提前显示后续章节的访问')
    require(previous_visits == ordered_visits, '终章未按顺序保留全部已登记访问')
    expected_pairs = {(a.get('id'), b.get('id')) for a, b in zip(visits, visits[1:]) if identifier(a.get('id')) and identifier(b.get('id')) and a.get('node_id') != b.get('node_id')}
    actual_pairs = set()
    for segment in segments:
        pair = (segment.get('from_visit'), segment.get('to_visit'))
        if not all(identifier(vid) for vid in pair):
            errors.append('路线段的访问ID须为非空字符串')
            continue
        require(pair not in actual_pairs, '路线段重复')
        actual_pairs.add(pair)
        require(segment.get('schematic') is True, '主连接必须声明示意，不冒充真实古道')
        evidence(segment.get('source_ids'), f'连接{pair}')
    require(actual_pairs == expected_pairs, '主连接应按访问顺序连接异地，同地停留不制造迁移')
    audio = project.get('audio', {})
    if not isinstance(audio, dict):
        errors.append('audio须为对象')
        audio = {}
    audio_path = root / (audio.get('path') if isinstance(audio.get('path'), str) else '')
    require(audio_path.is_file() and bool(audio.get('sha256')), '缺少用户指定配乐与SHA256锁定')
    if audio_path.is_file() and audio.get('sha256'):
        require(hashlib.sha256(audio_path.read_bytes()).hexdigest() == audio['sha256'], '锁定配乐文件已变化')
    return {'status': 'planning_preflight_passed' if not errors else 'planning_preflight_failed',
            'errors': errors, 'scope': '检查计划结构、证据记录声明、输入音频哈希及主题纸色上的地图来源/几何/可读性；不证明史实真实或人物动画成立，实际美术背景对比度由渲染合成器验证。',
            'map_preflight': map_preflight,
            'rendered_video_checks': 'not_run', 'historical_truth_check': 'not_automated',
            'manual_audio_and_device_preview': 'not_run'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path, help='包含project.json的项目目录')
    parser.add_argument('--report', type=Path, help='可选：写出预检JSON')
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    if args.report:
        protected = [root / name for name in ['project.json', 'data/storyboard.json', 'data/life_route.json', 'references/source_ledger.csv']]
        try:
            project = json.loads((root / 'project.json').read_text(encoding='utf-8'))
            audio = project.get('audio', {}) if isinstance(project, dict) else {}
            if isinstance(audio, dict) and isinstance(audio.get('path'), str) and audio['path']:
                protected.append(root / audio['path'])
            if isinstance(project, dict):
                for key in ['theme', 'art_provider']:
                    if isinstance(project.get(key), str) and project[key]:
                        protected.append(root / project[key])
        except (OSError, ValueError):
            pass
        target = args.report.expanduser().resolve()
        for source in protected:
            if target == source.resolve() or (target.exists() and source.exists() and target.samefile(source)):
                parser.error('--report不得覆盖项目输入、史料台账或锁定配乐')
        args.report = target
    result = check(root)
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding='utf-8')
    print(text, end='')
    raise SystemExit(0 if not result['errors'] else 1)


if __name__ == '__main__':
    main()
