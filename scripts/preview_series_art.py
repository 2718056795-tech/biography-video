#!/usr/bin/env python3
"""Export text bounds or preview actual artwork and composited frames."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw
from render_series_video import load_project


def review_frames(scene):
    """Take the midpoint and a distinct, declared action frame when available."""
    start, end = scene['start_frame'], scene['end_frame']
    middle = start + (end - start) // 2
    action = next((frame for frame in reversed(scene.get('action_sample_frames') or [])
                   if type(frame) is int and start <= frame < end and frame != middle),
                  start + (end - start) * 2 // 3)
    return middle, action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new PNG or text-layout JSON path')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--backgrounds-only', action='store_true', help='show the actual scenery layers without characters')
    modes.add_argument('--with-text', action='store_true', help='show actual final composition at two phases per scene')
    modes.add_argument('--text-layout', action='store_true', help='export actual text bounds and timing in final-canvas coordinates')
    args = parser.parse_args()
    output = args.output.expanduser()
    suffix = '.json' if args.text_layout else '.png'
    if output.suffix.lower() != suffix or output.exists():
        parser.error(f'Choose a new {suffix} output path')

    project_path = args.project.expanduser().resolve()
    if args.text_layout:
        scenes, compositor = load_project(project_path, layout_only=True)
        fps = compositor.style['video']['fps']
        layouts = []
        for scene in scenes:
            duration = (scene['end_frame'] - scene['start_frame']) / fps
            layouts.append({'scene_id': scene['id'], 'stage': scene['stage_profile'],
                            'text': compositor.text_layout(scene, duration)})
        result = {'width': compositor.width, 'height': compositor.height, 'profile_sha256': compositor.profile_sha256,
                  'max_entry_offset_y': compositor.style['motion']['text_enter_slide_y'], 'scenes': layouts}
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        print(output)
        return

    project, scenes, theme, compositor, maps, draw_art, _, _, _ = load_project(project_path)
    if args.backgrounds_only and project.get('background_policy') != 'per_scene':
        parser.error('Background-only previews require a project with separately rendered scenery')
    width, height = compositor.width, compositor.height
    fps = compositor.style['video']['fps']
    columns, gutter, label_height = (2 if args.with_text else 3), 8, 22
    tile_width, tile_height = width // 4, height // 4
    cell_height = tile_height + label_height + gutter
    rows = len(scenes) if args.with_text else (len(scenes) + columns - 1) // columns
    sheet = Image.new('RGB', (columns * (tile_width + gutter) + gutter,
                              rows * cell_height + gutter), '#282828')
    labels = ImageDraw.Draw(sheet)

    for index, scene in enumerate(scenes):
        start, end = scene['start_frame'], scene['end_frame']
        duration = (end - start) / fps
        offsets = review_frames(scene) if args.with_text else ((start + end) // 2,)
        for phase, frame_index in enumerate(offsets):
            time_sec = (frame_index - start) / fps
            if args.backgrounds_only:
                frame = draw_art.background(scene['id'], time_sec, duration)
            else:
                frame = draw_art(scene['id'], time_sec, duration, theme)
            if not isinstance(frame, Image.Image) or frame.mode != 'RGBA' or frame.size != (width, height):
                raise ValueError(f"{scene['id']}: artwork must be native {width}x{height} RGBA")
            label = scene['id']
            if args.with_text:
                frame = compositor.compose(scene, time_sec, duration, frame, maps.render(scene['id'], time_sec, duration))
                label = f'{label}  {time_sec:.2f}s'
            row, column = (index, phase) if args.with_text else divmod(index, columns)
            x, y = gutter + column * (tile_width + gutter), gutter + row * cell_height
            tile = frame.resize((tile_width, tile_height), Image.Resampling.LANCZOS)
            sheet.paste(tile, (x, y), tile if tile.mode == 'RGBA' else None)
            labels.text((x, y + tile_height + 4), label, fill='white')

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        sheet.save(handle, format='PNG')
    print(output)


if __name__ == '__main__':
    main()
