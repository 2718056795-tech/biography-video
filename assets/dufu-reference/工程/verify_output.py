#!/usr/bin/env python3
"""Read-only technical acceptance for the locked 120-second portrait film.

Only the JSON report is written. Decoded audio is hashed in memory as a stream.
Technical success does not claim a human listening review or platform preview.
"""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = ROOT / '输出/杜甫_此心在人间_生平解读动画版_v4_1080p_120秒.mp4'
DEFAULT_AUDIO = ROOT / '配乐/固定BGM_用户指定_原音轨.m4a'
DEFAULT_REPORT = ROOT / '质检/成片技术验收.json'
TIME_TOLERANCE = 0.1
PTS_TOLERANCE = 2e-6
FPS = 30
FRAME_COUNT = 3600


def numeric(value):
    try:
        result = float(Fraction(str(value)))
        return result if math.isfinite(result) else None
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def probe(path, *options):
    result = subprocess.run(['ffprobe', '-v', 'error', *options, '-of', 'json', str(path)],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:4000] or f'ffprobe 退出 {result.returncode}')
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise RuntimeError('ffprobe 未返回有效 JSON') from error


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def pcm_hash(path, index):
    """Hash native-rate/native-channel signed 16-bit PCM without saving it."""
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(path),
               '-map', f'0:{index}', '-vn', '-sn', '-dn', '-c:a', 'pcm_s16le',
               '-f', 's16le', 'pipe:1']
    digest = hashlib.sha256()
    size = 0
    # A temporary stderr handle prevents a full stderr pipe from blocking audio.
    # No PCM bytes are written to a file.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        try:
            with process.stdout:
                for chunk in iter(lambda: process.stdout.read(1024 * 1024), b''):
                    size += len(chunk)
                    digest.update(chunk)
            code = process.wait()
        except BaseException:
            process.kill()
            process.wait()
            raise
        errors.seek(0)
        message = errors.read(4000).decode('utf-8', errors='replace').strip()
    if code or message:
        raise RuntimeError(message or f'PCM 解码退出 {code}')
    if not size:
        raise RuntimeError('PCM 解码未产生任何样本')
    return {'sha256': digest.hexdigest(), 'byte_count': size,
            'sample_format': 'signed 16-bit little endian',
            'sample_rate_conversion': False, 'channel_conversion': False}


def packet_hashes(path, index):
    metadata = probe(path, '-select_streams', str(index), '-show_packets',
                     '-show_data_hash', 'sha256', '-show_entries', 'packet=size,data_hash')
    packets = metadata.get('packets', [])
    if not packets or any(not packet.get('data_hash', '').startswith('SHA256:')
                          for packet in packets):
        raise RuntimeError('AAC 包数据 SHA256 缺失或不可用')
    sequence = [(int(packet['size']), packet['data_hash']) for packet in packets]
    encoded = json.dumps(sequence, separators=(',', ':')).encode('ascii')
    summary = {'packet_count': len(sequence),
               'packet_payload_sequence_sha256': hashlib.sha256(encoded).hexdigest(),
               'first_packet_sha256': sequence[0][1], 'last_packet_sha256': sequence[-1][1]}
    return sequence, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description='杜甫竖版成片只读技术验收')
    parser.add_argument('--video', type=Path, default=DEFAULT_VIDEO)
    parser.add_argument('--source-audio', type=Path, default=DEFAULT_AUDIO)
    parser.add_argument('--report', type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    args.video = args.video.resolve()
    args.source_audio = args.source_audio.resolve()
    args.report = args.report.resolve()
    report = {
        'tool_version': '1.0',
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'technical_status': 'incomplete',
        'manual_review_status': 'pending',
        'inputs': {'video': str(args.video), 'source_audio': str(args.source_audio)},
        'expected': {'width': 1080, 'height': 1920, 'orientation': 'portrait',
                     'aspect_ratio': '9:16', 'fps': FPS, 'frame_count': FRAME_COUNT,
                     'duration_sec': 120, 'sample_aspect_ratio': '1:1',
                     'video_codec': 'h264', 'pixel_format': 'yuv420p',
                     'audio_codec': 'aac', 'audio_sample_rate': 44100, 'audio_channels': 2,
                     'time_tolerance_sec': TIME_TOLERANCE,
                     'pts_tolerance_sec': PTS_TOLERANCE,
                     'first_frame_pts_sec': 0,
                     'last_frame_pts_sec': (FRAME_COUNT - 1) / FPS},
        'measurements': {}, 'checks': [], 'errors': [], 'warnings': [],
        'manual_checks': [
            {'item': '主观听审、音乐情绪与画面事件卡点', 'status': 'pending'},
            {'item': '逐幕字幕阅读、历史与引文、地图表达、画面遮挡与风格', 'status': 'pending'},
            {'item': '原生竖屏构图、平台 UI 安全区及抖音实际发布预览', 'status': 'pending'},
        ],
    }

    def check(name, passed, detail):
        report['checks'].append({'name': name, 'status': 'passed' if passed else 'failed',
                                 'detail': detail})
        if not passed:
            report['errors'].append(f'{name}：{detail}')

    def fail(name, error):
        check(name, False, str(error))

    def finish(code):
        report['technical_status'] = ('incomplete' if code == 2 else
                                      'failed' if report['errors'] else 'passed')
        try:
            if args.report in (args.video, args.source_audio):
                raise ValueError('报告路径不得覆盖输入素材')
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                                   encoding='utf-8')
        except (OSError, ValueError) as error:
            print('无法写入报告：' + str(error), file=sys.stderr)
            return 2
        print(f"技术验收 {report['technical_status']}；错误 {len(report['errors'])}；"
              '主观听审及平台预览 pending')
        for message in report['errors']:
            print('错误：' + message)
        print('报告：' + str(args.report))
        return code

    for path in (args.video, args.source_audio):
        if not path.is_file():
            report['errors'].append('输入文件缺失：' + str(path))
    for executable in ('ffprobe', 'ffmpeg'):
        if not shutil.which(executable):
            report['errors'].append('缺少工具：' + executable)
    if args.report in (args.video, args.source_audio):
        print('报告路径不得覆盖输入素材', file=sys.stderr)
        return 2
    if report['errors']:
        return finish(2)

    try:
        metadata = probe(args.video, '-show_format', '-show_streams')
        original = probe(args.source_audio, '-show_format', '-show_streams')
        report['measurements']['input_sha256'] = {
            'video': sha256_file(args.video), 'source_audio': sha256_file(args.source_audio)}
    except (OSError, RuntimeError) as error:
        fail('媒体元数据读取', error)
        return finish(1)

    videos = [stream for stream in metadata.get('streams', [])
              if stream.get('codec_type') == 'video'
              and not stream.get('disposition', {}).get('attached_pic')]
    audios = [stream for stream in metadata.get('streams', [])
              if stream.get('codec_type') == 'audio']
    originals = [stream for stream in original.get('streams', [])
                 if stream.get('codec_type') == 'audio']
    check('唯一实际视频流', len(videos) == 1, f'实际 {len(videos)} 条')
    check('唯一成片音轨', len(audios) == 1, f'实际 {len(audios)} 条')
    check('唯一源音轨', len(originals) == 1, f'实际 {len(originals)} 条')
    if not videos or not audios or not originals:
        return finish(1)
    video, audio, source = videos[0], audios[0], originals[0]
    report['measurements']['video'] = {key: video.get(key) for key in
        ('index', 'codec_name', 'width', 'height', 'pix_fmt', 'sample_aspect_ratio',
         'avg_frame_rate', 'r_frame_rate', 'duration', 'start_time', 'nb_frames')}
    for label, stream in (('output_audio', audio), ('source_audio', source)):
        report['measurements'][label] = {key: stream.get(key) for key in
            ('index', 'codec_name', 'sample_rate', 'channels', 'duration', 'start_time')}
    check('视频尺寸', (video.get('width'), video.get('height')) == (1080, 1920),
          f"实际 {video.get('width')}×{video.get('height')}，目标 1080×1920")
    check('H.264 编码', video.get('codec_name') == 'h264', str(video.get('codec_name')))
    check('像素格式', video.get('pix_fmt') == 'yuv420p', str(video.get('pix_fmt')))
    sar = video.get('sample_aspect_ratio')
    sar_number = numeric(sar.replace(':', '/')) if isinstance(sar, str) else None
    check('SAR 1:1', sar_number == 1,
          f'实际 {sar!r}' if sar_number is not None else 'SAR 缺失或无效，未能核验 1:1')
    for name in ('avg_frame_rate', 'r_frame_rate'):
        rate = numeric(video.get(name))
        check(name, rate is not None and abs(rate - FPS) < 1e-6,
              f"实际 {video.get(name)!r}，目标 30/1；另做实际 PTS 检查")
    for label, stream in (('成片', audio), ('源', source)):
        check(label + ' AAC 音轨', stream.get('codec_name') == 'aac',
              str(stream.get('codec_name')))
        check(label + '采样率', numeric(stream.get('sample_rate')) == 44100,
              str(stream.get('sample_rate')))
        check(label + '双声道', stream.get('channels') == 2, str(stream.get('channels')))

    fmt = metadata.get('format', {})
    check('MP4 容器', 'mp4' in fmt.get('format_name', '').split(',')
          and args.video.suffix.lower() == '.mp4', str(fmt.get('format_name')))
    measured_times = {}
    for name, value in (('container_duration_sec', fmt.get('duration')),
                        ('video_duration_sec', video.get('duration')),
                        ('audio_duration_sec', audio.get('duration'))):
        value = numeric(value)
        measured_times[name] = value
        check(name, value is not None and abs(value - 120) <= TIME_TOLERANCE + 1e-9,
              f'实际 {value!r}s，目标 120s，容差 0.1s')
    vd, ad = measured_times['video_duration_sec'], measured_times['audio_duration_sec']
    vs, aus = numeric(video.get('start_time')), numeric(audio.get('start_time'))
    duration_difference = abs(vd - ad) if vd is not None and ad is not None else None
    start_difference = abs(vs - aus) if vs is not None and aus is not None else None
    end_difference = (abs(vs + vd - aus - ad)
                      if all(value is not None for value in (vd, ad, vs, aus)) else None)
    measured_times.update({'video_start_sec': vs, 'audio_start_sec': aus,
                          'av_duration_difference_sec': duration_difference,
                          'av_start_difference_sec': start_difference,
                          'av_end_difference_sec': end_difference})
    report['measurements']['timing'] = measured_times
    for name, value in (('视音轨时长差', duration_difference), ('视音轨起点差', start_difference),
                        ('视音轨终点差', end_difference)):
        check(name, value is not None and value <= TIME_TOLERANCE + 1e-9,
              f'实际 {value!r}s，容差 0.1s')

    try:
        frames = probe(args.video, '-select_streams', str(video['index']), '-show_frames',
                       '-show_entries', 'frame=best_effort_timestamp_time').get('frames', [])
        pts = [numeric(frame.get('best_effort_timestamp_time')) for frame in frames]
        absent = [index for index, value in enumerate(pts) if value is None]
        check('实际解码帧数', len(frames) == FRAME_COUNT,
              f'实际 {len(frames)} 帧，目标 {FRAME_COUNT} 帧')
        check('逐帧 PTS 完整性', not absent, f'缺失/无效 PTS 的帧位置：{absent[:12]}')
        frame_report = {'observed_frame_count': len(frames), 'invalid_pts_indices': absent[:12],
                        'interval_count': max(0, len(frames) - 1),
                        'expected_interval_sec': 1 / FPS,
                        'tolerance_sec': PTS_TOLERANCE}
        if pts and not absent:
            interval_errors = [abs((second - first) - 1 / FPS)
                               for first, second in zip(pts, pts[1:])]
            absolute_errors = [abs(value - index / FPS) for index, value in enumerate(pts)]
            bad_intervals = [index for index, value in enumerate(interval_errors)
                             if value > PTS_TOLERANCE]
            bad_absolute = [index for index, value in enumerate(absolute_errors)
                            if value > PTS_TOLERANCE]
            frame_report.update({'first_pts_sec': pts[0], 'last_pts_sec': pts[-1],
                                 'max_interval_error_sec': max(interval_errors, default=0),
                                 'max_absolute_pts_error_sec': max(absolute_errors, default=0),
                                 'bad_interval_indices': bad_intervals[:12],
                                 'bad_absolute_pts_indices': bad_absolute[:12]})
            check('首帧 PTS', abs(pts[0]) <= PTS_TOLERANCE, f'实际 {pts[0]}s，目标 0s')
            check('末帧 PTS', abs(pts[-1] - (FRAME_COUNT - 1) / FPS) <= PTS_TOLERANCE,
                  f'实际 {pts[-1]}s，目标 {(FRAME_COUNT - 1) / FPS:.9f}s')
            check('实际相邻帧间隔 CFR', not bad_intervals,
                  f"{len(interval_errors)} 个间隔，最大误差 {frame_report['max_interval_error_sec']:.12g}s；"
                  f'异常间隔位置 {bad_intervals[:12]}')
            check('逐帧绝对 PTS', not bad_absolute,
                  f"最大误差 {frame_report['max_absolute_pts_error_sec']:.12g}s；"
                  f'异常帧位置 {bad_absolute[:12]}')
        report['measurements']['frame_timestamps'] = frame_report
    except (OSError, RuntimeError) as error:
        fail('逐帧 PTS 检查', error)

    try:
        decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i',
                                  str(args.video), '-map', f"0:{video['index']}",
                                  '-map', f"0:{audio['index']}", '-f', 'null', '-'],
                                 capture_output=True, text=True, check=False)
        report['measurements']['full_decode'] = {
            'exit_code': decoded.returncode, 'stderr': decoded.stderr[:4000]}
        check('完整视频/音频解码', decoded.returncode == 0 and not decoded.stderr.strip(),
              decoded.stderr.strip()[:4000] or f'退出码 {decoded.returncode}')
    except OSError as error:
        fail('完整视频/音频解码', error)

    try:
        source_pcm = pcm_hash(args.source_audio, source['index'])
        output_pcm = pcm_hash(args.video, audio['index'])
        for item, stream in ((source_pcm, source), (output_pcm, audio)):
            channel_count = stream.get('channels')
            if isinstance(channel_count, int) and channel_count > 0:
                item['samples_per_channel'] = item['byte_count'] // (2 * channel_count)
        pcm_equal = (source_pcm['sha256'] == output_pcm['sha256']
                     and source_pcm['byte_count'] == output_pcm['byte_count'])
        report['measurements']['pcm_comparison'] = {
            'source': source_pcm, 'output': output_pcm, 'identical': pcm_equal}
        check('锁定音轨 PCM 完全一致', pcm_equal,
              f"源 {source_pcm['byte_count']} bytes / {source_pcm['sha256']}；"
              f"成片 {output_pcm['byte_count']} bytes / {output_pcm['sha256']}")
    except (OSError, RuntimeError) as error:
        fail('锁定音轨 PCM 比较', error)

    try:
        source_packets, source_summary = packet_hashes(args.source_audio, source['index'])
        output_packets, output_summary = packet_hashes(args.video, audio['index'])
        packet_equal = source_packets == output_packets
        first_difference = next((index for index, pair in
                                 enumerate(zip(source_packets, output_packets))
                                 if pair[0] != pair[1]), None)
        if first_difference is None and len(source_packets) != len(output_packets):
            first_difference = min(len(source_packets), len(output_packets))
        report['measurements']['aac_packet_comparison'] = {
            'source': source_summary, 'output': output_summary,
            'identical_payload_sequence': packet_equal,
            'first_difference_index': first_difference,
            'comparison_scope': '依次比较各 AAC 包的字节长度与载荷 SHA256；不把容器时间戳当作音频载荷'}
        check('AAC 包载荷保持原样', packet_equal,
              f'源 {len(source_packets)} 包，成片 {len(output_packets)} 包；'
              f'首个差异位置 {first_difference!r}')
    except (OSError, RuntimeError, KeyError, ValueError) as error:
        fail('AAC 包载荷比较', error)

    return finish(1 if report['errors'] else 0)


if __name__ == '__main__':
    sys.exit(main())
