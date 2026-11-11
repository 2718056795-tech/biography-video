#!/usr/bin/env python3
"""Create a biography plan with mandatory portrait cover config; does not render either file."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True, help='人物姓名')
    parser.add_argument('--output', required=True, type=Path, help='新建目录；必须不存在或为空')
    parser.add_argument('--orientation', choices=['portrait', 'landscape'], default='portrait')
    parser.add_argument('--duration', type=int, default=120)
    parser.add_argument('--fps', type=int, default=30)
    parser.add_argument('--audio', type=Path, help='已获用户指定的音频文件；复制并记录SHA256')
    args = parser.parse_args()
    if not args.name.strip() or args.duration <= 0 or args.fps <= 0:
        parser.error('姓名须非空，时长与帧率须为正整数')
    if args.audio and not args.audio.is_file():
        parser.error('--audio 必须是已存在的音频文件')
    target = args.output.expanduser().resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        parser.error('拒绝覆盖非空目录，请指定新目录')
    template_dir = Path(__file__).resolve().parent.parent / 'assets' / 'templates'
    project = json.loads((template_dir / 'project.json').read_text(encoding='utf-8'))
    project.update(name=args.name.strip(), orientation=args.orientation,
                   duration_sec=args.duration, fps=args.fps,
                   total_frames=args.duration * args.fps)
    project['width'], project['height'] = ((1080, 1920) if args.orientation == 'portrait' else (1920, 1080))
    for directory in ['data', 'references', 'art', 'audio', 'output', 'qa']:
        (target / directory).mkdir(parents=True, exist_ok=True)
    if args.audio:
        audio_target = target / 'audio' / ('locked-bgm' + args.audio.suffix.lower())
        shutil.copy2(args.audio, audio_target)
        project['audio'] = {'path': audio_target.relative_to(target).as_posix(),
                            'sha256': hashlib.sha256(audio_target.read_bytes()).hexdigest(),
                            'policy': 'preserve_exact_audio_payload'}
    (target / 'project.json').write_text(json.dumps(project, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for filename in ['storyboard.json', 'life_route.json']:
        shutil.copy2(template_dir / filename, target / 'data' / filename)
    with (target / 'references' / 'source_ledger.csv').open('w', newline='', encoding='utf-8') as handle:
        csv.writer(handle).writerow(['id', 'status', 'citation', 'url_or_path', 'claim', 'verification_note'])
    print(json.dumps({'project': str(target), 'status': 'scaffold_created',
                      'next': '补齐史料、逐章分镜、动作与累计路线，再运行check_project.py。完整交付必须有视频及1200×1500 PNG封面；此脚本不生成成片或封面，空模板不能通过预检。'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
