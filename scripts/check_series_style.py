#!/usr/bin/env python3
"""Check renderer layout records against the locked series profile and variable theme.

Checks geometry/font records, not image-pixel similarity or historical/aesthetic
truth. Per-person palette and background motifs are intentionally variable.
"""
import argparse
import json
import math
from pathlib import Path
from series_cover import DEFAULT_PROFILE, read_theme, sha256_file


def check_layout(report, profile, theme, profile_path):
    errors = []
    def require(condition, message):
        if not condition:
            errors.append(message)
    def mapping(value):
        return value if isinstance(value, dict) else {}
    require(isinstance(report, dict), '布局报告顶层须为对象')
    report = mapping(report)
    require(report.get('profile_id') == profile.get('profile_id'), 'profile_id与系列母版不一致')
    profile_hash = sha256_file(profile_path)
    require(report.get('profile_sha256') == profile_hash, '布局报告未绑定当前不可改动的母版文件')
    manifest_path = Path(profile_path).parent / 'series_manifest.json'
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            require(isinstance(manifest, dict) and manifest.get('style_sha256') == profile_hash, '母版文件与系列锁定manifest不一致')
        except (OSError, ValueError):
            errors.append('系列锁定manifest不可读')
    font_manifest = None
    for filename in ['fonts_manifest.json', 'font_manifest.json']:
        candidate = Path(profile_path).parent / filename
        if candidate.is_file():
            try:
                font_manifest = json.loads(candidate.read_text(encoding='utf-8'))
                require(isinstance(font_manifest, dict), '字体锁定manifest须为对象')
            except (OSError, ValueError):
                errors.append('字体锁定manifest不可读')
            break
    require(report.get('theme_tokens') == theme['colors'], '报告主题色角色与本人物theme不一致；人物间允许换色，不能套用其他人物色表')
    kind = report.get('kind')
    require(kind in ['cover', 'frame'], 'kind须为cover或frame')
    spec_canvas = profile['cover'] if kind == 'cover' else profile['video']
    canvas = mapping(report.get('canvas'))
    require((canvas.get('width'), canvas.get('height')) == (spec_canvas['width'], spec_canvas['height']), '画布尺寸或方向与母版不一致')
    elements = report.get('elements')
    require(isinstance(elements, list) and bool(elements), '缺少实际排版元素记录')
    elements = elements if isinstance(elements, list) else []
    quote_line_count = sum(isinstance(element, dict) and element.get('role') == 'standard.quote' for element in elements)
    required = {'cover.name', 'cover.film_title', 'cover.hook', 'cover.accent_line'} if kind == 'cover' else {'header.series_name', 'header.page_number', 'footer.event', 'footer.assessment'}
    seen, font_roles, used_text = set(), set(), set()
    font_coverage = {}
    for element in elements:
        if not isinstance(element, dict):
            errors.append('element须为对象')
            continue
        role = element.get('role')
        if not isinstance(role, str) or role.count('.') != 1:
            errors.append('element.role须为母版的section.role')
            continue
        section, key = role.split('.')
        allowed_sections = ['cover'] if kind == 'cover' else ['header', 'standard', 'bookend', 'footer']
        if section not in allowed_sections or key not in profile.get(section, {}):
            errors.append(f'非母版排版角色: {role}')
            continue
        locked = profile[section][key]
        line_index = element.get('line_index', 0)
        if not isinstance(line_index, int) or isinstance(line_index, bool) or line_index < 0:
            errors.append(f'{role}: line_index须为非负整数')
            line_index = 0
        identity = (role, line_index)
        require(identity not in seen, f'{role}: 同一行重复记录')
        seen.add(identity)
        if 'max_lines' in locked:
            require(line_index < locked['max_lines'], f'{role}: 超出母版行数')
        if 'font' in locked:
            font_role = locked['font']
            font_roles.add(font_role)
            used_text.add(role)
            expected_y = locked['y'] + line_index * locked.get('line_height', 0)
            if role == 'standard.source' and quote_line_count:
                quote_spec = profile['standard']['quote']
                expected_y = quote_spec['y'] + quote_line_count * quote_spec['line_height'] + 1 + line_index * locked.get('line_height', 0)
            require(element.get('x') == locked['x'] and element.get('y') == expected_y, f'{role}: 坐标偏离固定版位')
            require(element.get('font') == font_role, f'{role}: 字体角色被替换')
            sizes = {locked['size']}
            if role == 'footer.event':
                sizes = set(range(locked['min_size'], locked['size'] + 1))
            require(type(element.get('size')) is int and element['size'] in sizes, f'{role}: 字号不在允许范围{sorted(sizes)}')
            require(element.get('anchor') == 'lt', f'{role}: 文字anchor须为lt，不能按baseline错移')
            text = element.get('text')
            require(isinstance(text, str) and bool(text.strip()), f'{role}: 缺少实际文字')
            if isinstance(text, str) and font_manifest is not None:
                if font_role not in font_coverage:
                    coverage_record = mapping(mapping(font_manifest).get('roles')).get(font_role)
                    codepoints = mapping(coverage_record).get('supported_codepoints')
                    valid_coverage = isinstance(codepoints, list) and all(type(value) is int for value in codepoints)
                    require(valid_coverage, f'{font_role}: 锁定字体缺少可用的字形覆盖清单')
                    font_coverage[font_role] = set(codepoints) if valid_coverage else set()
                missing = sorted({ord(char) for char in text if not char.isspace() and ord(char) not in font_coverage[font_role]})
                require(not missing, f'{role}: 固定字体不支持字符{[f"U+{value:04X}" for value in missing[:8]]}；须保持系列字体，核对文字或采用有依据的常用写法，不得悄悄换字体')
            bbox = element.get('bbox', element.get('actual_bbox'))
            valid_bbox = isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in bbox)
            require(valid_bbox, f'{role}: 缺少实际文字边界记录')
            if valid_bbox:
                require(0 <= bbox[0] <= bbox[2] <= spec_canvas['width'] and 0 <= bbox[1] <= bbox[3] <= spec_canvas['height'], f'{role}: 实际文字出画布')
                if 'max_width' in locked:
                    require(bbox[2] - bbox[0] <= locked['max_width'], f'{role}: 文本超过固定宽度，应缩短内容')
                if kind == 'cover':
                    require(bbox[3] <= profile['cover']['art_reserved_top'], f'{role}: 文字进入封面下部美术区')
                else:
                    require(bbox[2] <= profile['video']['right_text_limit'] and bbox[3] <= profile['video']['bottom_text_limit'], f'{role}: 实际文字超出母版右侧/底部文字安全区')
        else:
            for field in ['x', 'y', 'x1', 'y1', 'x2', 'y2', 'width', 'height', 'alpha', 'fade_in_px']:
                if field in locked:
                    require(element.get(field) == locked[field], f'{role}: {field}偏离母版')
        require(element.get('color_role') == locked['color'], f'{role}: 颜色角色映射被替换')
        if 'start' in locked:
            expected_start = locked['start'] + line_index * locked.get('line_delay', 0)
            if role.startswith('footer.') and report.get('chapter_kind') == 'opening':
                expected_start = locked['intro_start']
            actual_start = element.get('start_sec', element.get('start'))
            require(isinstance(actual_start, (int, float)) and not isinstance(actual_start, bool) and math.isclose(actual_start, expected_start, abs_tol=1e-9), f'{role}: 显示时刻偏离母版')
    present_roles = {role for role, _ in seen}
    require(required.issubset(present_roles), f'缺少必须版位: {sorted(required - present_roles)}')
    fonts = mapping(report.get('fonts'))
    for role in font_roles:
        expected_path = profile['fonts'][role]
        record = mapping(fonts.get(role))
        require(record.get('path') == expected_path, f'{role}: 不是母版捆绑字体路径')
        try:
            expected_hash = sha256_file(Path(profile_path).parent / expected_path)
            require(record.get('sha256') == expected_hash, f'{role}: 字体文件SHA256不一致')
            if font_manifest is not None:
                manifest_role = mapping(mapping(font_manifest).get('roles')).get(role)
                manifest_role = mapping(manifest_role)
                require(manifest_role.get('sha256') == expected_hash, f'{role}: 实际字体与锁定manifest哈希不一致')
                require(manifest_role.get('file', manifest_role.get('path')) == expected_path, f'{role}: 字体锁定manifest路径不一致')
        except OSError:
            errors.append(f'{role}: 母版字体文件缺失')
    if kind == 'cover':
        art = mapping(report.get('art'))
        c = profile['cover']
        require(art.get('source_size') == [c['width'], c['height']], '封面底图尺寸与母版不一致')
        require(art.get('reserved_top') == c['art_reserved_top'] and art.get('top_overwritten') is True, '封面保留区没有按母版覆盖清空')
        require(art.get('retained_bounds') == [0, c['art_reserved_top'], c['width'], c['height']], '封面下部无字美术保留范围改变')
    elif kind == 'frame':
        require(any(role.startswith('standard.') or role.startswith('bookend.') for role in present_roles), '缺少standard/bookend正文版位')
        map_record = mapping(report.get('map'))
        for key, value in profile['map'].items():
            require(map_record.get(key) == value, f'map.{key}偏离母版')
        stage = mapping(report.get('stage'))
        name = stage.get('profile_name')
        locked_stage = profile['stage_profiles'].get(name) if isinstance(name, str) else None
        require(locked_stage is not None, '使用了母版以外的舞台profile')
        if locked_stage:
            for field in ['scale', 'offset_y']:
                require(stage.get(field) == locked_stage[field], f'stage.{field}偏离选定母版profile')
        if 'motion' in report:
            require(report['motion'] == profile['motion'], '动画/文字时钟配置偏离母版')
    return {'technical_status': 'passed' if not errors else 'failed', 'errors': errors,
            'checked_kind': kind, 'profile_id': profile.get('profile_id'),
            'scope': 'Layout/font/theme-role records checked against the supplied locked profile. Per-person palette and art pixels are not compared to Du Fu. This does not independently certify image pixels, historical truth, title wording, semantic motifs or aesthetic quality.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True, help='series_cover.py或series_frame.py生成的布局记录JSON')
    parser.add_argument('--profile', type=Path, default=DEFAULT_PROFILE)
    parser.add_argument('--theme', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='QA结果JSON，不能覆盖输入')
    args = parser.parse_args()
    for source in [args.report, args.profile, args.theme]:
        if args.output.resolve() == source.resolve() or (args.output.exists() and source.exists() and args.output.samefile(source)):
            parser.error('QA输出不得覆盖输入')
    try:
        profile = json.loads(args.profile.read_text(encoding='utf-8'))
        theme = read_theme(args.theme, profile)
        result = check_layout(json.loads(args.report.read_text(encoding='utf-8')), profile, theme, args.profile)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'technical_status': 'failed', 'errors': [str(exc)], 'scope': 'Layout-record check failed; no visual or historical certification.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['technical_status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
