#!/usr/bin/env python3
"""Gate delivery on BOTH actual video and cover, plus a passed video report.

The existing verify_media.py report must match the actual video's SHA256.
The cover defaults to PNG 1200x1500: user name 5:4竖屏, actual width:height 4:5.
This command rechecks the cover pixels but does not rerun the video decoder,
certify history/title/OCR/style, or replace manual/model visual review.
"""
import argparse
import json
from pathlib import Path
from verify_cover import inspect_cover, same_file, sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--cover', required=True, type=Path)
    parser.add_argument('--media-report', required=True, type=Path, help='verify_media.py生成的完整成片技术报告')
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--cover-width', type=int, default=1200, help='仅用户明确要求另一封面规格时修改')
    parser.add_argument('--cover-height', type=int, default=1500)
    args = parser.parse_args()
    if args.cover_width <= 0 or args.cover_height <= 0:
        parser.error('封面宽高须为正整数')
    for source in [args.video, args.cover, args.media_report]:
        if same_file(source, args.report):
            parser.error('交付报告不得覆盖视频、封面或媒体验收报告')
    errors = []
    result = {'technical_status': 'failed',
              'inputs': {key: str(value.expanduser().resolve()) for key, value in
                         [('video', args.video), ('cover', args.cover), ('media_report', args.media_report)]},
              'required_deliverables': ['video', 'cover'], 'measurements': {}, 'errors': errors,
              'scope': 'Actual deliverable existence and hashes, cover PNG validity/dimensions, passed media report binding. No fresh video decoding, historical truth, OCR, title or style certification.',
              'manual_checks': {'cover_title_and_person': 'pending', 'cover_thumbnail_style': 'pending',
                                'video_content_and_animation': 'pending', 'listening_and_device_preview': 'pending'}}
    if not args.video.is_file():
        errors.append('必交视频文件不存在')
    else:
        result['measurements']['video_sha256'] = sha256_file(args.video)
    try:
        report = json.loads(args.media_report.read_text(encoding='utf-8'))
        if not isinstance(report, dict):
            raise ValueError('报告顶层不是对象')
        if report.get('technical_status') != 'passed' or report.get('errors') != []:
            errors.append('视频技术报告未通过或仍有错误')
        measured = report.get('measurements', {})
        recorded = measured.get('input_sha256', {}) if isinstance(measured, dict) else {}
        recorded_hash = recorded.get('video') if isinstance(recorded, dict) else None
        if not recorded_hash or recorded_hash != result['measurements'].get('video_sha256'):
            errors.append('视频报告SHA256与实际交付视频不一致或缺失')
        result['measurements']['media_report_sha256'] = sha256_file(args.media_report)
    except (OSError, ValueError) as exc:
        errors.append(f'视频技术报告不可读: {exc}')
    result['cover_check'] = inspect_cover(args.cover, args.cover_width, args.cover_height)
    if result['cover_check']['technical_status'] != 'passed':
        errors.extend(result['cover_check']['errors'])
    if not errors:
        result['technical_status'] = 'passed'
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == '__main__':
    main()
