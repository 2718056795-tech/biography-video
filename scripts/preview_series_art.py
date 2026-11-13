#!/usr/bin/env python3
"""Preview one actual artwork frame per chapter before encoding the film."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw
from render_series_video import load_project


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new PNG path')
    parser.add_argument('--backgrounds-only', action='store_true', help='show the actual scenery layers without characters')
    args = parser.parse_args()
    output = args.output.expanduser()
    if output.suffix.lower() != '.png' or output.exists():
        parser.error('Choose a new .png output path')

    project_path = args.project.expanduser().resolve()
    project, scenes, theme, compositor, _, draw_art, _, _, _ = load_project(project_path)
    if args.backgrounds_only and project.get('background_policy') != 'per_scene':
        parser.error('Background-only previews require a project with separately rendered scenery')
    width, height = compositor.width, compositor.height
    fps = compositor.style['video']['fps']
    columns, gutter, label_height = 3, 8, 22
    tile_width, tile_height = width // 4, height // 4
    cell_height = tile_height + label_height + gutter
    rows = (len(scenes) + columns - 1) // columns
    sheet = Image.new('RGB', (columns * (tile_width + gutter) + gutter,
                              rows * cell_height + gutter), '#282828')
    labels = ImageDraw.Draw(sheet)

    for index, scene in enumerate(scenes):
        count = scene['end_frame'] - scene['start_frame']
        time_sec, duration = (count // 2) / fps, count / fps
        if args.backgrounds_only:
            frame = draw_art.background(scene['id'], time_sec, duration)
        else:
            frame = draw_art(scene['id'], time_sec, duration, theme)
        if not isinstance(frame, Image.Image) or frame.mode != 'RGBA' or frame.size != (width, height):
            raise ValueError(f"{scene['id']}: draw_art must return native {width}x{height} RGBA artwork")
        tile = frame.resize((tile_width, tile_height), Image.Resampling.LANCZOS)
        row, column = divmod(index, columns)
        x, y = gutter + column * (tile_width + gutter), gutter + row * cell_height
        sheet.paste(tile, (x, y), tile)
        labels.text((x, y + tile_height + 4), scene['id'], fill='white')

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        sheet.save(handle, format='PNG')
    print(output)


if __name__ == '__main__':
    main()
