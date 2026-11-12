#!/usr/bin/env python3
"""Deterministic, themeable compositor for the locked biography series.

This module composes already animated, text-free artwork and a mandatory sourced map.
It never invents a biography, fabricates animation, or redesigns the layout.
Requires Pillow. The packaged fonts are mandatory; there is no font fallback.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from series_map import ensure_map_evidence, validate_map_background

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STYLE = SKILL_ROOT / 'assets/series/series_style.json'
FORBIDDEN_OVERRIDES = {
    'layout_override', 'layout_overrides', 'positions', 'font_overrides',
    'title_x', 'title_y', 'meta_x', 'meta_y', 'quote_x', 'quote_y',
    'event_x', 'event_y', 'assessment_x', 'assessment_y',
    'stage_scale', 'stage_offset_y', 'font_size', 'font_family',
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smooth(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


class SeriesFrame:
    """Use one frozen coordinate contract with per-person theme/content data.

    ``scene.index`` is one-based. ``scene.kind`` is opening/chapter/ending.
    ``art_rgba`` must be a native 1080x1920 text-free, animated RGBA frame.
    ``map_rgba`` is already projected 880x430 RGBA; it is never rescaled here.
    """

    def __init__(self, style_path=None, theme=None, person=None, scene_count=12):
        self.style_path = Path(style_path or DEFAULT_STYLE).expanduser().resolve()
        self.style = json.loads(self.style_path.read_text(encoding='utf-8'))
        self.profile_sha256 = sha256_file(self.style_path)
        self.width = int(self.style['video']['width'])
        self.height = int(self.style['video']['height'])
        if (self.width, self.height) != (1080, 1920):
            raise ValueError('This series contract requires native 1080x1920')
        self.theme_tokens = deepcopy(theme)
        if not isinstance(theme, dict):
            raise ValueError('A per-person theme mapping is required')
        self.colors = deepcopy(theme.get('colors', theme.get('palette', theme)))
        if not isinstance(self.colors, dict):
            raise ValueError('theme.colors must be a color-role object')
        for role in ('paper', 'ink', 'muted', 'accent', 'assessment'):
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(self.colors.get(role, ''))):
                raise ValueError(f'Missing or invalid theme color: {role}')
        if not isinstance(person, dict):
            raise ValueError('person must contain name and film_title')
        self.person = deepcopy(person)
        for key in ('name', 'film_title'):
            if not isinstance(self.person.get(key), str) or not self.person[key].strip():
                raise ValueError(f'person.{key} is required')
        if not isinstance(scene_count, int) or isinstance(scene_count, bool) or scene_count < 1:
            raise ValueError('scene_count must be a positive integer')
        self.scene_count = scene_count
        self.font_paths = {
            role: (self.style_path.parent / relative).resolve()
            for role, relative in self.style['fonts'].items()
        }
        self._fonts = {}
        self._prepared = {}
        self._font_records = None
        self.last_report = None

    def font(self, role, size):
        key = (role, int(size))
        if key not in self._fonts:
            path = self.font_paths[role]
            if not path.is_file():
                raise FileNotFoundError(f'Packaged series font missing: {path}; do not substitute another font')
            self._fonts[key] = ImageFont.truetype(str(path), int(size), index=0)
        return self._fonts[key]

    def _font_report(self):
        if self._font_records is None:
            self._font_records = {}
            for role, path in self.font_paths.items():
                if not path.is_file():
                    raise FileNotFoundError(f'Packaged series font missing: {path}')
                self._font_records[role] = {'path': self.style['fonts'][role], 'resolved_path': str(path), 'sha256': sha256_file(path)}
        return deepcopy(self._font_records)

    def _color(self, role):
        try:
            return self.colors[role]
        except KeyError as exc:
            raise ValueError(f'Theme does not define color role {role}') from exc

    def _wrap(self, text, role, size, max_width):
        result, current = [], ''
        for char in text:
            if char == '\n':
                result.append(current)
                current = ''
                continue
            if current and self.font(role, size).getlength(current + char) > max_width:
                result.append(current)
                current = char
            else:
                current += char
        if current:
            result.append(current)
        return result

    def _sprite(self, text, role, size, color):
        font = self.font(role, size)
        bounds = font.getbbox(text, anchor='lt')
        image = Image.new('RGBA', (math.ceil(font.getlength(text)) + 8, bounds[3] - bounds[1] + 8))
        ImageDraw.Draw(image).text((4, 4), text, font=font, fill=color, anchor='lt')
        return image

    def _prepare(self, scene, duration, paper_rgb):
        if not isinstance(scene, dict):
            raise ValueError('scene must be an object')
        forbidden = FORBIDDEN_OVERRIDES.intersection(scene)
        if forbidden:
            raise ValueError('Per-scene layout overrides are forbidden: ' + ', '.join(sorted(forbidden)))
        index = scene.get('index')
        if index is None:
            match = re.fullmatch(r'S(\d+)', str(scene.get('id', '')))
            index = int(match[1]) if match else None
        if not isinstance(index, int) or isinstance(index, bool) or not 1 <= index <= self.scene_count:
            raise ValueError('scene.index must be a one-based chapter number')
        kind = scene.get('kind', 'opening' if index == 1 else 'ending' if index == self.scene_count else 'chapter')
        if kind not in ('opening', 'chapter', 'ending'):
            raise ValueError('scene.kind must be opening, chapter or ending')
        profile_name = scene.get('stage_profile')
        if profile_name not in self.style['stage_profiles']:
            raise ValueError('stage_profile must be one of the five locked profiles')
        stage = self.style['stage_profiles'][profile_name]
        for key in ('title', 'meta', 'event_summary', 'assessment'):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f'{scene.get("id", index)}: {key} is required')
        sprites, elements = [], []
        header = Image.new('RGBA', (self.width, self.height))
        header_draw = ImageDraw.Draw(header)
        motion = self.style['motion']

        def add(text, role, spec, *, y=None, start=None, size=None, line_index=0):
            x = spec['x']
            y = spec['y'] if y is None else y
            size = spec['size'] if size is None else size
            start = spec['start'] if start is None else start
            image = self._sprite(text, spec['font'], size, self._color(spec['color']))
            # The padded sprite check intentionally matches the V4 source.
            if x + image.width > self.style['video']['right_text_limit']:
                raise ValueError(f'{role}: text exceeds the locked right boundary; shorten content, do not move text')
            if y + image.height > self.style['video']['bottom_text_limit']:
                raise ValueError(f'{role}: text exceeds the locked bottom boundary')
            sprites.append((image, x - 4, y - 4, start))
            elements.append({'role': role, 'x': x, 'y': y, 'font': spec['font'],
                             'size': size, 'color_role': spec['color'], 'color': self._color(spec['color']),
                             'anchor': 'lt', 'bbox': [x, y, x + image.width - 8, y + image.height - 8],
                             'text': text, 'line_index': line_index, 'start_sec': start,
                             'full_opacity_after_sec': start + motion['text_fade_sec'],
                             'conservative_fade_out_begins_sec': duration - motion['read_budget_out_before_end']})

        header_text = f'{self.person["name"]} / {self.person["film_title"]}'
        header_spec = self.style['header']['series_name']
        if header_spec['x'] + self.font(header_spec['font'], header_spec['size']).getlength(header_text) > self.style['header']['page_number']['x'] - 32:
            raise ValueError('Header name/film title is too long; shorten the film title instead of moving the header')
        for role, text in [('series_name', header_text), ('page_number', self.style['header']['page_number']['format'].format(index=index, count=self.scene_count))]:
            spec = self.style['header'][role]
            font = self.font(spec['font'], spec['size'])
            header_draw.text((spec['x'], spec['y']), text, font=font, fill=self._color(spec['color']), anchor='lt')
            bbox = font.getbbox(text, anchor='lt')
            elements.append({'role': 'header.' + role, 'x': spec['x'], 'y': spec['y'],
                             'font': spec['font'], 'size': spec['size'], 'color_role': spec['color'],
                             'color': self._color(spec['color']), 'anchor': 'lt', 'text': text,
                             'bbox': [spec['x'], spec['y'], spec['x'] + math.ceil(font.getlength(text)), spec['y'] + bbox[3] - bbox[1]]})

        if kind in ('opening', 'ending'):
            group = self.style['bookend']
            add(self.person['name'], 'bookend.person', group['person'])
            add(scene['title'], 'bookend.title', group['title'])
            meta = scene.get('bookend_meta') or (self.person.get('birth_death') if kind == 'ending' else self.person.get('opening_meta'))
            if not isinstance(meta, str) or not meta.strip():
                raise ValueError('Provide person.birth_death / person.opening_meta, or scene.bookend_meta')
            add(meta, 'bookend.meta', group['meta'])
            spec = group['explanation']
            lines = self._wrap(scene.get('explanation', ''), spec['font'], spec['size'], spec['max_width'])
            if len(lines) > 1:
                raise ValueError('The bookend explanation must fit one locked line')
            for i, line in enumerate(lines):
                add(line, 'bookend.explanation', spec, y=spec['y'] + i * spec['line_height'], start=spec['start'] + i * spec['line_delay'], line_index=i)
        else:
            group = self.style['standard']
            add(scene['title'], 'standard.title', group['title'])
            add(scene['meta'], 'standard.meta', group['meta'])
            quotes = scene.get('quote_lines') or []
            if not isinstance(quotes, list) or any(not isinstance(line, str) or not line for line in quotes):
                raise ValueError('quote_lines must be a list of nonempty strings')
            if quotes:
                if not isinstance(scene.get('source_label'), str) or not scene['source_label'].strip():
                    raise ValueError('A quoted chapter must include the verified work/source label')
                spec = group['quote']
                if len(quotes) > spec['max_lines']:
                    raise ValueError('A quote is limited to two locked lines; choose a shorter verified excerpt')
                for i, line in enumerate(quotes):
                    add(line, 'standard.quote', spec, y=spec['y'] + i * spec['line_height'], start=spec['start'] + i * spec['line_delay'], line_index=i)
                spec = group['source']
                source_y = group['quote']['y'] + len(quotes) * group['quote']['line_height'] + 1
                for i, line in enumerate(self._wrap(scene.get('source_label', ''), spec['font'], spec['size'], spec['max_width'])):
                    add(line, 'standard.source', spec, y=source_y + i * spec['line_height'], line_index=i)
            else:
                spec = group['explanation']
                lines = self._wrap(scene.get('explanation', ''), spec['font'], spec['size'], spec['max_width'])
                if not lines or len(lines) > 2:
                    raise ValueError('A no-quote chapter needs a one/two-line explanation in the locked area')
                for i, line in enumerate(lines):
                    add(line, 'standard.explanation', spec, y=spec['y'] + i * spec['line_height'], start=spec['start'] + i * spec['line_delay'], line_index=i)
                if scene.get('source_label'):
                    add(scene['source_label'], 'standard.narrative_source', group['narrative_source'])

        footer = self.style['footer']
        event_spec = footer['event']
        event_size = event_spec['size']
        while event_size > event_spec['min_size'] and self.font(event_spec['font'], event_size).getlength(scene['event_summary']) > event_spec['max_width']:
            event_size -= 1
        if self.font(event_spec['font'], event_size).getlength(scene['event_summary']) > event_spec['max_width']:
            raise ValueError('event_summary is too long even at the permitted 32px; shorten it')
        assessment_spec = footer['assessment']
        if self.font(assessment_spec['font'], assessment_spec['size']).getlength(scene['assessment']) > assessment_spec['max_width']:
            raise ValueError('assessment must fit one 30px locked line; shorten it')
        add(scene['event_summary'], 'footer.event', event_spec, size=event_size,
            start=event_spec['intro_start'] if kind == 'opening' else event_spec['start'])
        add(scene['assessment'], 'footer.assessment', assessment_spec,
            start=assessment_spec['intro_start'] if kind == 'opening' else assessment_spec['start'])

        wash_spec = footer['wash']
        wash = Image.new('RGBA', (self.width, wash_spec['height']), (0, 0, 0, 0))
        draw = ImageDraw.Draw(wash)
        for y in range(wash.height):
            alpha = round(wash_spec['alpha'] * max(0.0, min(1.0, y / wash_spec['fade_in_px'])))
            draw.line([(0, y), (self.width, y)], fill=tuple(paper_rgb) + (alpha,))
        accent = footer['accent_line']
        draw.line([(accent['x1'] - wash_spec['x'], accent['y1'] - wash_spec['y']),
                   (accent['x2'] - wash_spec['x'], accent['y2'] - wash_spec['y'])],
                  fill=self._color(accent['color']), width=accent['width'])
        elements.append({'role': 'footer.accent_line', 'x': accent['x1'], 'y': accent['y1'],
                         'x1': accent['x1'], 'y1': accent['y1'],
                         'x2': accent['x2'], 'y2': accent['y2'], 'width': accent['width'],
                         'color_role': accent['color'], 'color': self._color(accent['color'])})
        elements.append({'role': 'footer.wash', **deepcopy(wash_spec),
                         'color_role': wash_spec['color'], 'actual_paper_rgb': list(paper_rgb)})
        return {'sprites': sprites, 'header': header, 'wash': wash, 'elements': elements,
                'kind': kind, 'index': index, 'stage': {'profile_name': profile_name, **deepcopy(stage)},
                'actual_paper_rgb': list(paper_rgb)}

    def fit_stage(self, art_rgba, stage):
        scale, offset = stage['scale'], stage['offset_y']
        pad = max(0, math.ceil((self.width / scale - self.width) / 2) + 2)
        bottom = max(0, math.ceil((self.height - offset) / scale) - self.height + 2)
        expanded = Image.new('RGBA', (self.width + 2 * pad, self.height + bottom))
        expanded.paste(art_rgba, (pad, 0))
        if pad:
            expanded.paste(art_rgba.crop((0, 0, 1, self.height)).resize((pad, self.height), Image.Resampling.NEAREST), (0, 0))
            expanded.paste(art_rgba.crop((self.width - 1, 0, self.width, self.height)).resize((pad, self.height), Image.Resampling.NEAREST), (self.width + pad, 0))
        if bottom:
            expanded.paste(expanded.crop((0, self.height - 1, expanded.width, self.height)).resize((expanded.width, bottom), Image.Resampling.NEAREST), (0, self.height))
        scaled = expanded.resize((round(expanded.width * scale), round(expanded.height * scale)), Image.Resampling.BILINEAR)
        canvas = Image.new('RGBA', (self.width, self.height), art_rgba.getpixel((0, 0)))
        canvas.alpha_composite(scaled, ((self.width - scaled.width) // 2, offset))
        return canvas

    def compose(self, scene, t, duration, art_rgba, map_rgba=None):
        try:
            t, duration = float(t), float(duration)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError('t/duration must be finite numbers') from exc
        if not math.isfinite(t) or not math.isfinite(duration) or duration <= 0:
            raise ValueError('t/duration must be finite and duration must be positive')
        if art_rgba.mode != 'RGBA' or art_rgba.size != (self.width, self.height):
            raise ValueError('art_rgba must be a native 1080x1920 RGBA frame')
        map_spec = self.style['map']
        if map_rgba is None:
            raise ValueError('Every series frame requires an official sourced map with evidence')
        if not isinstance(map_rgba, Image.Image) or map_rgba.mode != 'RGBA' or map_rgba.size != (map_spec['width'], map_spec['height']):
            raise ValueError('map_rgba must be an already projected native 880x430 RGBA layer')
        map_evidence = ensure_map_evidence(map_rgba, scene_id=scene.get('id'), t=t, duration=duration)
        paper_rgb = art_rgba.getpixel((0, 0))[:3]
        key = json.dumps({'scene': scene, 'duration': duration, 'paper': paper_rgb}, ensure_ascii=False, sort_keys=True)
        if key not in self._prepared:
            self._prepared[key] = self._prepare(scene, duration, paper_rgb)
        prepared = self._prepared[key]
        canvas = self.fit_stage(art_rgba, prepared['stage'])
        background = canvas.crop((map_spec['x'], map_spec['y'], map_spec['x'] + map_spec['width'], map_spec['y'] + map_spec['height']))
        background_readability = validate_map_background(map_rgba, background)
        if background_readability.get('passed') is not True:
            failed = [check.get('purpose') for check in background_readability.get('checks', []) if check.get('passed') is not True]
            raise ValueError('Map is unreadable over the actual artwork background: ' + ', '.join(failed))
        canvas.alpha_composite(map_rgba, (map_spec['x'], map_spec['y']))
        wash = self.style['footer']['wash']
        canvas.alpha_composite(prepared['wash'], (wash['x'], wash['y']))
        canvas.alpha_composite(prepared['header'])
        motion = self.style['motion']
        fade = motion['text_fade_sec']
        for image, x, y, start in prepared['sprites']:
            opacity = smooth((t - start) / fade) * smooth((duration - motion['text_out_end_before_scene_end'] - t) / fade)
            if opacity <= 0:
                continue
            if opacity < .999:
                image = image.copy()
                image.putalpha(image.getchannel('A').point(lambda value: round(value * opacity)))
            y_offset = round(motion['text_enter_slide_y'] * (1 - smooth((t - start) / motion['text_enter_slide_sec'])))
            canvas.alpha_composite(image, (x, y + y_offset))
        final_fade = motion['final_picture_fade_sec']
        if prepared['kind'] == 'ending' and t > duration - final_fade:
            amount = smooth((t - (duration - final_fade)) / final_fade)
            canvas = Image.blend(canvas, Image.new('RGBA', (self.width, self.height), self._color('paper')), amount)
        picture = canvas.convert('RGB')
        panel = picture.crop((map_spec['x'], map_spec['y'], map_spec['x'] + map_spec['width'], map_spec['y'] + map_spec['height']))
        self.last_report = {
            'profile_id': self.style['profile_id'], 'kind': 'frame',
            'canvas': {'width': self.width, 'height': self.height},
            'profile_sha256': self.profile_sha256, 'theme_tokens': deepcopy(self.colors),
            'theme_direction': deepcopy(self.theme_tokens),
            'fonts': self._font_report(), 'elements': deepcopy(prepared['elements']),
            'map': deepcopy(map_spec),
            'map_present': True, 'map_evidence': deepcopy(map_evidence),
            'map_background_readability': background_readability,
            'frame_mode': 'RGB', 'frame_sha256': hashlib.sha256(picture.tobytes()).hexdigest(),
            'composited_map_sha256': hashlib.sha256(panel.tobytes()).hexdigest(),
            'stage': deepcopy(prepared['stage']),
            'scene_id': scene.get('id'), 'chapter_index': prepared['index'],
            'chapter_kind': prepared['kind'], 'time_sec': t, 'duration_sec': duration,
            'footer_actual_paper_rgb': prepared['actual_paper_rgb'],
            'motion': deepcopy(motion),
            'scope': 'Actual compositor geometry, fonts, sourced map evidence and RGB pixel hashes; not historical, animation, audio or device certification',
        }
        return picture
