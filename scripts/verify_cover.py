#!/usr/bin/env python3
"""Verify a real PNG cover (default portrait 1200x1500); requires Pillow.

This checks the file, complete PNG verification/pixel loading, dimensions and
hash. It does not certify Chinese text, title, composition or thumbnail style.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def same_file(first, second):
    return first.resolve() == second.resolve() or (first.exists() and second.exists() and first.samefile(second))


def inspect_cover(path, width=1200, height=1500):
    path = path.expanduser().resolve()
    result = {
        'technical_status': 'failed', 'inputs': {'cover': str(path)},
        'expected': {'width': width, 'height': height, 'orientation': 'portrait' if height > width else 'landscape',
                     'format': 'PNG', 'default_user_name': '5:4竖屏', 'default_long_short_ratio': '5:4',
                     'default_width_height_ratio': '4:5'},
        'measurements': {}, 'errors': [],
        'scope': 'Actual file, PNG verification and decoded pixels, dimensions and SHA256 only; no OCR, title correctness, composition or style certification.',
        'manual_checks': {'title_and_person_correct': 'pending', 'thumbnail_readability_and_style': 'pending'}
    }
    if not path.is_file():
        result['errors'].append('必交封面文件不存在')
        return result
    result['measurements']['sha256'] = sha256_file(path)
    try:
        from PIL import Image
        with Image.open(path) as image:
            actual = {'format': image.format, 'width': image.width, 'height': image.height, 'mode': image.mode}
            result['measurements'].update(actual)
            if image.format != 'PNG':
                result['errors'].append('封面须为真实PNG，不能只改扩展名')
            if image.size != (width, height):
                result['errors'].append(f'封面尺寸须为{width}×{height}；实际{image.width}×{image.height}')
            image.verify()
        if not result['errors']:
            with Image.open(path) as image:
                image.load()
            result['measurements']['png_structure_and_pixels'] = 'passed'
    except ImportError:
        result['errors'].append('缺少Pillow，无法验证实际PNG；先安装依赖')
    except (OSError, ValueError, SyntaxError) as exc:
        result['errors'].append(f'PNG验证或像素解码失败: {exc}')
    if not result['errors']:
        result['technical_status'] = 'passed'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cover', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--width', type=int, default=1200, help='默认1200；仅用户明确指定另一封面规格时更改')
    parser.add_argument('--height', type=int, default=1500, help='默认1500；“5:4竖屏”指长短边5:4，实际宽高4:5')
    args = parser.parse_args()
    if args.width <= 0 or args.height <= 0:
        parser.error('封面宽高须为正整数')
    if same_file(args.cover, args.report):
        parser.error('报告不得覆盖封面文件')
    result = inspect_cover(args.cover, args.width, args.height)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['technical_status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
