#!/usr/bin/env python3
"""Evidence for visible scene-internal motion, not an automatic aesthetic verdict.

Draws the real actor/environment modules without transitions or old subjects.
Removes actor translation before examining local arms/legs/paper differences.
Writes only below 质检/动作验收; does not modify scene data, assets or audio.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '质检/动作验收'
W, H, FPS = 1080, 1920, 30
WALK = {'S02', 'S03', 'S04', 'S06', 'S07', 'S10'}
HANDS = {'S01', 'S05', 'S08', 'S09', 'S11'}
OVERRIDES = {'S01': {'mid'}, 'S02': {'fg'}, 'S05': {'fg'}, 'S07': {'fg'},
             'S08': {'mid'}, 'S09': {'mid'}, 'S10': {'fg'}, 'S11': {'mid', 'fg'}}
INK = (30, 42, 38)
PAPER = (243, 235, 220)
FOLD = (220, 210, 188)
RUST = (163, 107, 78)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=8)
def font(size):
    path = Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    return ImageFont.truetype(str(path), size, index=2)


def checked_layer(image, label):
    if image is None:
        return Image.new('RGBA', (W, H))
    if image.mode != 'RGBA' or image.size != (W, H):
        raise ValueError(f'{label} 必须返回 1080×1920 RGBA，实际 {image.mode}/{image.size}')
    return image


def alpha_mask(image):
    return np.asarray(image.getchannel('A')) >= 128


def palette_mask(image, colors):
    pixels = np.asarray(image)
    match = np.zeros(pixels.shape[:2], dtype=bool)
    for color in colors:
        match |= np.all(pixels[:, :, :3] == color, axis=2)
    return match & (pixels[:, :, 3] >= 128)


def xy_centroid(mask):
    y, x = np.nonzero(mask)
    return (float(x.mean()), float(y.mean())) if len(x) else None


def isolate_walker(image, sid):
    """Exclude the waving bystander / second traveller before pose registration."""
    if sid not in ('S06', 'S07'):
        return image
    mask = alpha_mask(image)
    occupied = np.flatnonzero(np.any(mask, axis=0))
    if not len(occupied):
        return image
    groups = np.split(occupied, np.flatnonzero(np.diff(occupied) > 1) + 1)
    groups = [group for group in groups if mask[:, group].sum() > 25]
    if not groups:
        raise ValueError(f'{sid} 未能隔离行走者')
    right = max(groups, key=lambda group: int(group[-1]))
    # Keep coordinates in world space; do not scale, stretch, or redraw the actor.
    result = Image.new('RGBA', (W, H))
    result.alpha_composite(image.crop((int(right[0]), 0, int(right[-1]) + 1, H)),
                           (int(right[0]), 0))
    return result


def upper_anchor(image):
    box = image.getchannel('A').getbbox()
    if not box:
        return None
    mask = alpha_mask(image)
    bottom = box[1] + max(4, round((box[3] - box[1]) * .22))
    mask[bottom:] = False
    return xy_centroid(mask)


def register(images):
    anchors = [upper_anchor(image) for image in images]
    if any(anchor is None for anchor in anchors):
        raise ValueError('演员抽样为空，不能比较姿态')
    reference = anchors[0]
    aligned, shifts = [], []
    for image, anchor in zip(images, anchors):
        dx, dy = round(reference[0] - anchor[0]), round(reference[1] - anchor[1])
        target = Image.new('RGBA', (W, H))
        target.alpha_composite(image, (dx, dy))
        aligned.append(target)
        shifts.append([dx, dy])
    return aligned, {'method': 'top 22% alpha centroid, translation only; no scale or rotation',
                     'anchors_xy': anchors, 'integer_shifts_xy': shifts}


def union_box(images, pad=0):
    boxes = [image.getchannel('A').getbbox() for image in images]
    boxes = [box for box in boxes if box]
    if not boxes:
        return None
    return (max(0, min(box[0] for box in boxes) - pad),
            max(0, min(box[1] for box in boxes) - pad),
            min(W, max(box[2] for box in boxes) + pad),
            min(H, max(box[3] for box in boxes) + pad))


def local_difference(images, box, paper_only=False):
    """Compare registered local structure; no whole-scene pixel differences."""
    frames = [np.asarray(image.crop(box)) for image in images]
    masks = [(palette_mask(image.crop(box), (PAPER, FOLD)) if paper_only
              else pixels[:, :, 3] >= 128) for image, pixels in zip(images, frames)]
    pairs = []
    for first, second in combinations(range(len(images)), 2):
        a, b = frames[first], frames[second]
        ma, mb = masks[first], masks[second]
        occupied = ma | mb
        xor = ma ^ mb
        color_changed = np.max(np.abs(a[:, :, :3].astype(np.int16)
                                      - b[:, :, :3].astype(np.int16)), axis=2) >= 22
        changed = xor | (color_changed & ma & mb)
        total = int(occupied.sum())
        pairs.append({'pair': [first, second], 'occupied_union_pixels': total,
                      'mask_xor_pixels': int(xor.sum()),
                      'mask_xor_fraction': float(xor.sum() / max(1, total)),
                      'local_changed_pixels': int(changed.sum()),
                      'local_changed_fraction': float(changed.sum() / max(1, total))})
    best = max(pairs, key=lambda item: item['local_changed_fraction'])
    return {'roi_xyxy': box, 'paper_palette_only': paper_only, 'pairs': pairs,
            'largest_observed_change': best,
            'signal_flag': best['local_changed_pixels'] >= 12
                           and best['local_changed_fraction'] >= .02,
            'interpretation': '局部形变线索，仅辅助挑选肉眼复核；阈值不证明动作自然、可读或真实。'}


def checker(size):
    image = Image.new('RGBA', size, (238, 234, 223, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], 24):
        for x in range(0, size[0], 24):
            if (x // 24 + y // 24) % 2:
                draw.rectangle((x, y, x + 23, y + 23), fill=(218, 215, 206, 255))
    return image


def actor_strip(images, times, sid, label):
    box = union_box(images, 20)
    if not box:
        return None
    width, height = box[2] - box[0], box[3] - box[1]
    factor = min(360 / width, 490 / height)
    target_size = (max(1, round(width * factor)), max(1, round(height * factor)))
    sheet = Image.new('RGB', (400 * len(images), 610), '#F3EBDC')
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 10), f'{sid} {label} / 同一倍率 {factor:.2f}×', font=font(23), fill=INK)
    for index, (image, seconds) in enumerate(zip(images, times)):
        crop = checker((width, height))
        crop.alpha_composite(image.crop(box))
        crop = crop.convert('RGB').resize(target_size, Image.Resampling.NEAREST)
        x = index * 400 + (400 - target_size[0]) // 2
        y = 72 + (490 - target_size[1]) // 2
        sheet.paste(crop, (x, y))
        draw.text((index * 400 + 18, 558), f'幕内 {seconds:.3f}s', font=font(23), fill=INK)
    destination = OUT / f'{sid}_{label}.png'
    sheet.save(destination)
    return str(destination.relative_to(ROOT))


@lru_cache(maxsize=2)
def base_layers(sid):
    result = {}
    for name in ('bg', 'mid', 'fg'):
        if name in OVERRIDES.get(sid, set()):
            path = ROOT / '素材/动画底层' / f'{sid}_{name}.png'
            if not path.is_file():
                raise FileNotFoundError(f'缺少已生成动画底层缓存 {path}；请由生产流程生成，验收不改素材')
        else:
            path = ROOT / '素材/图层' / f'{sid}_{name}.png'
        result[name] = checked_layer(Image.open(path).convert('RGBA'), str(path))
    return result


def compose(sid, t, duration, actor_module, environment_module):
    layers = base_layers(sid)
    canvas = layers['bg'].copy()
    environment_module.draw_environment(canvas, sid, t, duration, stage='back')
    canvas.alpha_composite(layers['mid'])
    actor = checked_layer(actor_module.draw_actor(sid, t, duration), sid)
    canvas.alpha_composite(actor)
    environment_module.draw_environment(canvas, sid, t, duration, stage='front')
    canvas.alpha_composite(layers['fg'])
    return canvas.convert('RGB')


def context_strip(images, times, sid):
    # Fixed world-space crop: shoreline/buildings do not follow the actor.
    sheet = Image.new('RGB', (540 * len(images), 446), '#F3EBDC')
    draw = ImageDraw.Draw(sheet)
    draw.text((18, 10), f'{sid} 原坐标动作区 / 无字幕、地图、转场', font=font(25), fill=INK)
    for index, (image, seconds) in enumerate(zip(images, times)):
        crop = image.crop((0, 740, W, 1460)).resize((540, 360), Image.Resampling.LANCZOS)
        sheet.paste(crop, (index * 540, 48))
        draw.text((index * 540 + 18, 411), f'幕内 {seconds:.3f}s', font=font(22), fill=INK)
    path = OUT / f'{sid}_原坐标场景动作条.png'
    sheet.save(path)
    return str(path.relative_to(ROOT))


def environment_layer(module, sid, t, duration, stage):
    canvas = Image.new('RGBA', (W, H))
    module.draw_environment(canvas, sid, t, duration, stage=stage)
    return canvas


def angle_from_mask(mask):
    y, x = np.nonzero(mask)
    if len(x) < 8:
        return None
    points = np.column_stack((x, y)).astype(float)
    _, vectors = np.linalg.eigh(np.cov(points.T))
    axis = vectors[:, -1]
    return math.degrees(math.atan2(axis[1], axis[0])) % 180


def scene_samples(scene, music):
    start_frame = scene['start_frame']
    end_frame = scene['end_frame_exclusive']
    duration = (end_frame - start_frame) / FPS
    entries = next((entry for entry in music['scene_action_candidates']
                    if entry['scene_id'] == scene['id']), {'action_candidates': []})
    early = [item['nearest_frame'] / FPS - start_frame / FPS
             for item in entries['action_candidates']
             if .25 <= item['nearest_frame'] / FPS - start_frame / FPS <= 1.8]
    motion_start = early[0] if early else .4
    motion_duration = duration - motion_start
    fractions = (.02, .25, .45, .85) if scene['id'] == 'S12' else (.08, .25, .45, .70)
    frames = [min(end_frame - start_frame - 1, round((motion_start + value * motion_duration) * FPS))
              for value in fractions]
    scene_times = [frame / FPS for frame in frames]
    motion_times = [max(0, seconds - motion_start) for seconds in scene_times]
    return {'duration': duration, 'motion_start': motion_start, 'motion_duration': motion_duration,
            'fractions': fractions, 'local_frames': frames,
            'global_frames': [frame + start_frame for frame in frames],
            'scene_times': scene_times, 'motion_times': motion_times}


def review_scene(scene, music, actor_module, environment_module, make_clip):
    sid = scene['id']
    sample = scene_samples(scene, music)
    times, motion_times = sample['scene_times'], sample['motion_times']
    duration = sample['motion_duration']
    actors = [checked_layer(actor_module.draw_actor(sid, seconds, duration), sid)
              for seconds in motion_times]
    record = {'scene_id': sid, 'samples': sample, 'visual_review_status': 'pending',
              'artifacts': [], 'measurements': {}, 'flags': [],
              'scope': '独立真实动作层，不使用跨幕转场或全画面像素差作为动作证据'}
    if sid != 'S12':
        if any(not image.getchannel('A').getbbox() for image in actors):
            raise ValueError(f'{sid} 演员抽样存在空层')
        selected = [isolate_walker(image, sid) for image in actors]
        aligned, registration = register(selected)
        record['measurements']['registration'] = registration
        record['measurements']['actor_component'] = ('右侧行走者；其他人物不参与数值比较'
                                                       if sid in ('S06', 'S07') else '本幕演员层')
        for label, images in (('演员原位置', selected), ('演员消除平移后', aligned)):
            record['artifacts'].append(actor_strip(images, times, sid, label))
        box = union_box(aligned)
        left, top, right, bottom = box
        height = bottom - top
        regions = {'arms': (max(0, left - 40), round(top + height * .24),
                            min(W, right + 40), round(top + height * .78)),
                   'legs': (max(0, left - 25), round(top + height * .61),
                            min(W, right + 25), min(H, bottom + 12))}
        for name in ('arms', 'legs') if sid in WALK else ('arms',):
            metrics = local_difference(aligned, regions[name])
            record['measurements'][name] = metrics
            if not metrics['signal_flag']:
                record['flags'].append(f'{name} 配准后变化偏弱或采样同相，必须查看连续预览')
        if sid in HANDS:
            record['measurements']['paper'] = local_difference(aligned, regions['arms'], paper_only=True)
    else:
        record['measurements']['actor'] = '终章有意无演员，不据空层判失败'

    if sid == 'S11':
        layers = [environment_layer(environment_module, sid, t, duration, 'back')
                  for t in motion_times]
        centers = [xy_centroid(palette_mask(layer, (INK,))) for layer in layers]
        angles = [angle_from_mask(palette_mask(layer, (RUST,))) for layer in layers]
        displacement = max(center[0] for center in centers) - min(center[0] for center in centers)
        variations = [min(abs(a - b), 180 - abs(a - b)) for a, b in combinations(angles, 2)
                      if a is not None and b is not None]
        record['measurements']['boat'] = {
            'method': '只测独立环境back层中INK船壳像素质心；不使用boat_x公式或演员位移作替代',
            'hull_centroids_xy': centers, 'observed_horizontal_displacement_px': displacement,
            'over_150px': displacement > 150,
            'shoreline_reference': '原坐标场景条带保留固定岸线；未用全屏差分判定岸线静止'}
        record['measurements']['oar'] = {
            'method': '独立back层RUST桨杆像素PCA主轴，已消除平移，180度等价',
            'angles_degrees': angles, 'largest_angle_change_degrees': max(variations, default=0),
            'over_5deg': max(variations, default=0) > 5}
        if displacement <= 150:
            record['flags'].append('船壳实际像素横向位移未达到150px')
        if max(variations, default=0) <= 5:
            record['flags'].append('采样桨杆角度变化不明显，需连续预览排查同相采样')
    if sid == 'S12':
        layers = [environment_layer(environment_module, sid, t, duration, 'front')
                  for t in motion_times]
        paper_boxes, ink_counts = [], []
        for layer in layers:
            paper = Image.fromarray(palette_mask(layer, (PAPER,)).astype('uint8') * 255)
            paper_boxes.append(paper.getbbox())
            ink_counts.append(int(palette_mask(layer, (INK,)).sum()))
        widths = [box[2] - box[0] if box else 0 for box in paper_boxes]
        gain = max(widths) - min(widths)
        record['measurements']['scroll'] = {
            'method': '独立front层实际PAPER纸面像素宽度与INK字形像素数，不采用代码宽度公式',
            'paper_bbox_xyxy': paper_boxes, 'paper_widths_px': widths,
            'observed_width_increase_px': gain, 'over_300px': gain > 300,
            'ink_pixel_counts': ink_counts,
            'ink_appears_after_opening': ink_counts[-1] > ink_counts[0] + 100}
        if gain <= 300:
            record['flags'].append('实际纸面展开宽度未增加300px')
        if ink_counts[-1] <= ink_counts[0] + 100:
            record['flags'].append('纸面墨字未在抽样中明显出现')

    context = [compose(sid, seconds, duration, actor_module, environment_module)
               for seconds in motion_times]
    record['artifacts'].append(context_strip(context, times, sid))
    if make_clip:
        target = OUT / f'{sid}_原速动作区_无声.mp4'
        seconds = min(6.4, duration - .05)
        rate = 12
        command = ['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo',
                   '-pixel_format', 'rgb24', '-video_size', '720x480', '-framerate', str(rate),
                   '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                   '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for frame in range(round(seconds * rate)):
                canvas = compose(sid, frame / rate, duration, actor_module, environment_module)
                crop = canvas.crop((0, 740, W, 1460)).resize((720, 480), Image.Resampling.LANCZOS)
                process.stdin.write(crop.tobytes())
            process.stdin.close()
            message = process.stderr.read().decode(errors='replace')
            code = process.wait()
            if code:
                raise RuntimeError(f'预览编码失败：{message}')
        except BaseException:
            process.kill(); process.wait()
            raise
        record['artifacts'].append(str(target.relative_to(ROOT)))
        record['preview_note'] = '真实动作层前6.4秒内原速连续预览，12fps、无音轨；没有转场或镜头移动'
    return record


def main():
    parser = argparse.ArgumentParser(description='输出真实局部动作证据，最终观感须视觉复核')
    parser.add_argument('--scenes', default='all', help='all 或 S02,S09 等逗号分隔')
    parser.add_argument('--clips', action='store_true', help='另导出S02/S09/S11/S12原速无声动作区短片')
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    paths = [Path(__file__).with_name(name) for name in ('actor_motion.py', 'environment_motion.py')]
    before = {path.name: file_hash(path) for path in paths}
    import actor_motion
    import environment_motion
    timeline = json.loads((ROOT / '数据/最终时间轴.json').read_text())
    music = json.loads((ROOT / '数据/音乐节拍候选.json').read_text())
    scenes = timeline['scenes']
    if args.scenes != 'all':
        wanted = set(args.scenes.split(','))
        unknown = wanted - {scene['id'] for scene in scenes}
        if unknown:
            parser.error(f'未知幕编号：{sorted(unknown)}')
        scenes = [scene for scene in scenes if scene['id'] in wanted]
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'scope': '动作真实性辅助审查，不代表美术、自然度或最终视频验收通过',
              'visual_review_status': 'pending', 'module_sha256': before,
              'method_limits': [
                  '局部形变指标可排除纯平移，但不能证明关节动作自然、脚掌着地或手机上清晰。',
                  '条带固定倍率展示真实模块输出，不叠加伪造关节、运动线或插值姿态。',
                  '终片遮挡与最终速度需继续看实际成片；本条带省略字幕、地图和转场。'],
              'scenes': [], 'errors': []}
    for scene in scenes:
        sid = scene['id']
        try:
            report['scenes'].append(review_scene(scene, music, actor_motion, environment_motion,
                                                args.clips and sid in ('S02', 'S09', 'S11', 'S12')))
            print('review evidence', sid, flush=True)
        except Exception as error:
            report['errors'].append({'scene': sid, 'error': f'{type(error).__name__}: {error}'})
            print('review error', sid, str(error), flush=True)
    after = {path.name: file_hash(path) for path in paths}
    if after != before:
        report['errors'].append({'scene': 'all', 'error': '抽样期间动作模块变更，证据需重新生成'})
    report['evidence_generation_status'] = 'failed' if report['errors'] else 'completed'
    destination = OUT / '动作证据.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(destination, flush=True)
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
