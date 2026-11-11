#!/usr/bin/env python3
"""Compose the locked series cover from text-free 1200x1500 art and theme tokens.

All positions, font roles and sizes come from assets/series/series_style.json.
Overflow is an error: shorten the supplied display text; never shrink fonts.
The art's top 560px is reserved and overwritten before deterministic typography.
"""
import argparse
import hashlib
import json
import random
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DEFAULT_PROFILE = Path(__file__).resolve().parent.parent / 'assets/series/series_style.json'


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_theme(path, profile):
    theme = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(theme, dict) or not isinstance(theme.get('colors'), dict):
        raise ValueError('theme须为含colors对象的JSON')
    for key in ['theme_id', 'person', 'rationale']:
        if not isinstance(theme.get(key), str) or not theme[key].strip():
            raise ValueError(f'theme.{key}须为非空文字')
    def roles(value):
        found = set()
        if isinstance(value, dict):
            if isinstance(value.get('color'), str):
                found.add(value['color'])
            for child in value.values():
                found.update(roles(child))
        elif isinstance(value, list):
            for child in value:
                found.update(roles(child))
        return found
    allowed = roles(profile)
    if not allowed.issubset(theme['colors']):
        raise ValueError(f'theme.colors须包含布局色角色{sorted(allowed)}；允许额外背景/地图色角色，不能覆盖坐标或字体')
    if any(not isinstance(value, str) or re.fullmatch(r'#[0-9a-fA-F]{6}', value) is None for value in theme['colors'].values()):
        raise ValueError('主题色须为#RRGGBB')
    for key in ['motifs', 'background_choices']:
        if not isinstance(theme.get(key), list) or not theme[key] or not all(isinstance(value, str) and value.strip() for value in theme[key]):
            raise ValueError(f'theme.{key}须为非空文字组成的非空数组')
    if 'paper_variants' in theme and (not isinstance(theme['paper_variants'], list) or not all(isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) for value in theme['paper_variants'])):
        raise ValueError('theme.paper_variants须为#RRGGBB数组')
    forbidden = set(theme) & {'layout', 'fonts', 'font', 'font_size', 'coordinates', 'positions', 'x', 'y', 'cover', 'video', 'header', 'map', 'standard', 'bookend', 'footer', 'motion', 'stage_profiles'}
    if forbidden:
        raise ValueError(f'主题只描述人物、色彩与背景母题，不能提供布局覆盖字段: {sorted(forbidden)}')
    if 'profile_id' in theme and theme['profile_id'] != profile['profile_id']:
        raise ValueError('主题profile_id与系列母版不一致')
    return theme


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--art', type=Path, required=True, help='无字PNG，1200×1500；上部保留区不放重要人物或器物')
    parser.add_argument('--name', required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--hook', required=True)
    parser.add_argument('--theme', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args()
    inputs = [args.art, args.theme, args.profile]
    def same(a, b):
        return a.resolve() == b.resolve() or (a.exists() and b.exists() and a.samefile(b))
    if same(args.output, args.report) or any(same(target, source) for target in [args.output, args.report] for source in inputs):
        parser.error('输出和报告不得覆盖输入，也不得互相覆盖')
    try:
        profile = json.loads(args.profile.read_text(encoding='utf-8'))
        theme = read_theme(args.theme, profile)
        spec = profile['cover']
        width, height = spec['width'], spec['height']
        with Image.open(args.art) as source:
            if source.format != 'PNG' or source.size != (width, height):
                raise ValueError(f'无字画必须为真实{width}×{height} PNG，不能颠倒或裁切')
            source.verify()
        with Image.open(args.art) as source:
            source.load()
            art = source.convert('RGBA')
        colors = theme['colors']
        canvas = Image.new('RGBA', (width, height), colors['paper'])
        canvas.alpha_composite(art)
        draw = ImageDraw.Draw(canvas)
        reserved_top = spec['art_reserved_top']
        draw.rectangle((0, 0, width - 1, reserved_top - 1), fill=colors['paper'])
        # Fixed seed and pixel positions make the paper grain stable and repeatable.
        grain = Image.new('RGBA', (width, reserved_top), (0, 0, 0, 0))
        grain_draw = ImageDraw.Draw(grain)
        rng = random.Random(20261111)
        for _ in range((width * reserved_top) // 125):
            x, y = rng.randrange(width), rng.randrange(reserved_top)
            grain_draw.point((x, y), fill=(0, 0, 0, rng.choice((5, 8, 11))))
        canvas.alpha_composite(grain)
        draw = ImageDraw.Draw(canvas)
        font_records, elements = {}, []
        for role, text in [('name', args.name), ('film_title', args.title), ('hook', args.hook)]:
            if not text.strip() or '\n' in text or '\r' in text:
                raise ValueError(f'{role}须为非空单行文字')
            locked = spec[role]
            font_role = locked['font']
            font_path = args.profile.parent / profile['fonts'][font_role]
            font = ImageFont.truetype(str(font_path), locked['size'])
            anchor = (locked['x'], locked['y'])
            bbox = draw.textbbox(anchor, text, font=font, anchor='lt')
            if bbox[2] - bbox[0] > locked['max_width'] or bbox[0] < 0 or bbox[2] > width or bbox[3] > reserved_top:
                raise ValueError(f'{role}文字超出固定版位；请缩短片名/钩子或使用有依据的常用姓名，不得缩字号或改坐标')
            draw.text(anchor, text, font=font, fill=colors[locked['color']], anchor='lt')
            font_records[font_role] = {'path': profile['fonts'][font_role], 'sha256': sha256_file(font_path)}
            elements.append({'role': f'cover.{role}', 'text': text, 'x': anchor[0], 'y': anchor[1],
                             'font': font_role, 'size': locked['size'], 'color_role': locked['color'],
                             'anchor': 'lt', 'bbox': list(bbox)})
        line = spec['accent_line']
        draw.line((line['x1'], line['y1'], line['x2'], line['y2']), fill=colors[line['color']], width=line['width'])
        elements.append({'role': 'cover.accent_line', **{key: line[key] for key in ['x1', 'y1', 'x2', 'y2', 'width']}, 'color_role': line['color']})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        canvas.convert('RGB').save(args.output, format='PNG')
        report = {'schema_version': '2.0', 'profile_id': profile['profile_id'], 'kind': 'cover',
                  'profile_sha256': sha256_file(args.profile), 'canvas': {'width': width, 'height': height},
                  'theme_tokens': colors, 'theme_sha256': sha256_file(args.theme), 'fonts': font_records,
                  'elements': elements,
                  'art': {'path': str(args.art.resolve()), 'sha256': sha256_file(args.art),
                          'source_size': [width, height], 'reserved_top': reserved_top,
                          'retained_bounds': [0, reserved_top, width, height], 'top_overwritten': True,
                          'text_free_input_visual_check': 'required; not certified by OCR'},
                  'output': {'path': str(args.output.resolve()), 'sha256': sha256_file(args.output)},
                  'scope': 'Deterministic geometry and font compositor. Does not certify historical truth, artwork motifs, AI-text absence in lower art, title wording or aesthetic quality.'}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'output': str(args.output), 'report': str(args.report), 'status': 'rendered'}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
