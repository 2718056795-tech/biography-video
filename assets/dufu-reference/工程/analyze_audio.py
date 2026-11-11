#!/usr/bin/env python3
"""Read-only fixed-BGM analysis. All peaks are automatic candidates, not heard beats."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CUTS = [0, 7, 16, 26, 36, 47, 56, 66, 75, 89, 100, 111, 120]
REVIEW = "自动候选，未人工听审；由导演结合画面、阅读预算与成片听看后决定"


def run(argv: list[str], binary: bool = False):
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf-8", errors="replace")[-3000:])
    return p.stdout if binary else p.stdout.decode("utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def dbfs(x: float) -> float | None:
    return round(20 * math.log10(float(x)), 4) if x > 0 else None


def timing(sec: float, fps: int) -> dict:
    frame = round(sec * fps)
    return {
        "analysis_time_sec": round(float(sec), 6),
        "nearest_frame": frame,
        "aligned_time_sec": round(frame / fps, 6),
        "alignment_error_ms": round((frame / fps - sec) * 1000, 4),
    }


def ranges(mask: np.ndarray, step: float, min_sec: float) -> list[dict]:
    changes = np.diff(np.r_[False, mask, False].astype(np.int8))
    out = []
    for a, b in zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)):
        if (b - a) * step >= min_sec:
            out.append({"start_sec": round(a * step, 6),
                        "end_sec": round(b * step, 6),
                        "duration_sec": round((b - a) * step, 6)})
    return out


def choose(candidates: list[dict], target: float, radius: float) -> list[dict]:
    available = [c for c in candidates if abs(c["analysis_time_sec"] - target) <= radius]
    ranked = sorted(available, key=lambda c: c["strength"] * (
        0.65 + 0.35 * (1 - abs(c["analysis_time_sec"] - target) / radius)), reverse=True)
    return ranked


def analyze(audio: Path, output_dir: Path, fps: int) -> dict:
    lock_path = ROOT / "配乐" / "配乐锁定信息.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    source_hash = sha256(audio)
    expected = lock.get("audio_sha256")
    if not expected or source_hash != expected:
        raise ValueError("固定音轨SHA256与配乐锁定信息不一致；未继续分析，也未修改源文件")
    probe = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                            "-show_streams", "-show_format", "-of", "json", str(audio)]))
    stream = probe["streams"][0]
    channels = int(stream["channels"])
    native_sr = int(stream["sample_rate"])
    duration = float(stream["duration"])

    with tempfile.TemporaryDirectory(prefix="dufu_bgm_analysis_") as temp:
        temp = Path(temp)
        mono_path = temp / "analysis_mono.wav"
        native_path = temp / "native_float32.pcm"
        # Decode only. Mono downmix/resampling is a temporary feature-analysis view.
        run(["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(audio),
             "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le",
             str(mono_path)])
        run(["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(audio),
             "-map", "0:a:0", "-vn", "-c:a", "pcm_f32le", "-f", "f32le", str(native_path)])
        sr, pcm = wavfile.read(mono_path)
        mono = pcm.astype(np.float64) / 32768.0
        native = np.fromfile(native_path, dtype="<f4").reshape(-1, channels)

        native_metrics = []
        for ch in range(channels):
            x = native[:, ch].astype(np.float64)
            native_metrics.append({
                "channel": ch + 1,
                "sample_peak_linear": round(float(np.max(np.abs(x))), 8),
                "sample_peak_dbfs": dbfs(np.max(np.abs(x))),
                "integrated_rms_dbfs": dbfs(np.sqrt(np.mean(x * x))),
                "samples_at_or_above_0dbfs": int(np.count_nonzero(np.abs(x) >= 1)),
                "nonzero_samples": int(np.count_nonzero(x)),
            })
        correlation = float(np.corrcoef(native[:, 0], native[:, 1])[0, 1]) if channels == 2 else None
        # Reference s16 hash uses FFmpeg's conversion rather than a NumPy approximation.
        original_s16 = run(["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(audio),
                            "-map", "0:a:0", "-vn", "-c:a", "pcm_s16le", "-f", "s16le", "-"], binary=True)
        s16_hash = hashlib.sha256(original_s16).hexdigest()
        locked_pcm = lock.get("output_pcm_s16le", {})
        pcm_match = s16_hash == locked_pcm.get("sha256") and len(original_s16) == locked_pcm.get("bytes")

        # Short windows measure quiet intervals; absolute threshold is explicit.
        silence_window = round(0.05 * sr)
        complete = mono[:len(mono) // silence_window * silence_window]
        short_rms = np.sqrt(np.mean(complete.reshape(-1, silence_window) ** 2, axis=1))
        quiet = ranges(short_rms < 10 ** (-60 / 20), silence_window / sr, 0.3)

        nfft, hop = 1024, 220
        _, times, spectrum = signal.stft(
            mono, fs=sr, window="hann", nperseg=nfft, noverlap=nfft - hop,
            boundary=None, padded=False)
        magnitude = np.abs(spectrum)
        positive = np.maximum(np.diff(magnitude, axis=1), 0)
        flux = np.r_[0, np.sqrt(np.sum(positive * positive, axis=0))]
        cumsum = np.r_[0, np.cumsum(mono * mono)]
        starts = np.arange(len(times)) * hop
        rms = np.sqrt(np.maximum((cumsum[starts + nfft] - cumsum[starts]) / nfft, 0))
        rise = np.maximum(rms - np.r_[np.repeat(rms[0], 5), rms[:-5]], 0)

        def normalize(x):
            return np.clip(x / max(float(np.percentile(x, 95)), 1e-12), 0, 4)

        score = 0.8 * normalize(flux) + 0.2 * normalize(rise)
        peaks, _ = signal.find_peaks(score, height=0.22, prominence=0.10,
                                     distance=round(0.18 * sr / hop))
        candidates = []
        for index in peaks:
            candidates.append({**timing(float(times[index]), fps),
                               "strength": round(float(score[index]), 5),
                               "spectral_flux": round(float(flux[index]), 8),
                               "window_rms_dbfs": dbfs(rms[index]),
                               "status": REVIEW})

        cuts = []
        for t in DEFAULT_CUTS:
            choices = choose(candidates, t, 0.6) if 0 < t < 120 else []
            cuts.append({"original_cut_sec": t, "original_cut_frame": round(t * fps),
                         "search_window_sec": [max(0, t - 0.6), min(120, t + 0.6)],
                         "suggested_candidate": choices[0] if choices else None,
                         "alternatives": choices[1:3],
                         "adopted": False,
                         "note": "原切点保持；候选仅供导演选择，片头0与片尾120秒固定"})

        scene_source = ROOT / "数据" / "构思分镜.json"
        scenes = json.loads(scene_source.read_text(encoding="utf-8"))["scenes"] if scene_source.exists() else []
        action_suggestions = []
        for i, (a, b) in enumerate(zip(DEFAULT_CUTS[:-1], DEFAULT_CUTS[1:])):
            selected = []
            for target in [a + min(1.5, (b - a) * .25), a + (b - a) * .6]:
                options = choose(candidates, target, .9)
                options = [c for c in options if a + .7 < c["analysis_time_sec"] < b - .7
                           and all(abs(c["analysis_time_sec"] - x["analysis_time_sec"]) > 1.25 for x in selected)]
                if options:
                    selected.append(options[0])
            previous_cut = cuts[i]["suggested_candidate"]
            next_cut = cuts[i + 1]["suggested_candidate"]
            proposed_a = previous_cut["aligned_time_sec"] if previous_cut else a
            proposed_b = next_cut["aligned_time_sec"] if next_cut else b
            stable = scenes[i].get("stable") if i < len(scenes) else None
            action_suggestions.append({
                "scene_id": scenes[i].get("id") if i < len(scenes) else f"S{i+1:02}",
                "original_interval_sec": [a, b],
                "original_duration_sec": b-a,
                "planned_stable_reading_sec": stable,
                "if_both_neighbor_cut_candidates_adopted_duration_sec": round(proposed_b - proposed_a, 6),
                "remaining_transition_allowance_sec": round(proposed_b - proposed_a - stable, 6) if stable is not None else None,
                "reading_warning": "任何切点调整都须复核文字实际稳定可读时长；候选不自动替换分镜",
                "action_candidates": selected,
            })
        # Coarse envelope aids repeatable inspection, without claiming musical meter.
        envelope = []
        for second in range(120):
            x = mono[second * sr:min((second + 1) * sr, len(mono))]
            if len(x):
                envelope.append({"start_sec": second, "rms_dbfs": dbfs(np.sqrt(np.mean(x*x))),
                                 "sample_peak_dbfs": dbfs(np.max(np.abs(x)))})

        result = {
            "status": "automatic_analysis_only_not_listening_reviewed",
            "fps": fps,
            "source_relative_path": str(audio.relative_to(ROOT)),
            "source_sha256": source_hash,
            "locked_audio_sha256": expected,
            "source_hash_matches_lock": True,
            "source_unchanged_after_analysis": sha256(audio) == source_hash,
            "full_decode_success": True,
            "codec": stream.get("codec_name"),
            "sample_rate_hz": native_sr,
            "channels": channels,
            "channel_layout": stream.get("channel_layout"),
            "stream_start_sec": float(stream.get("start_time", 0)),
            "stream_duration_sec": duration,
            "stream_end_sec": float(stream.get("start_time", 0)) + duration,
            "container_duration_sec": float(probe["format"]["duration"]),
            "decoded_native_sample_frames": len(native),
            "decoded_native_duration_sec": round(len(native) / native_sr, 9),
            "duration_note": "AAC封装/编码边界会使时长标记与解码样本时长有毫秒级差别；未裁切或补音",
            "decoded_minus_stream_duration_ms": round((len(native) / native_sr - duration) * 1000, 6),
            "decoded_pcm_s16le_sha256": s16_hash,
            "decoded_pcm_s16le_bytes": len(original_s16),
            "decoded_pcm_matches_locked_reference": pcm_match,
            "channel_measurements": native_metrics,
            "stereo_channel_correlation": round(correlation, 6) if correlation is not None else None,
            "stereo_note": "相关系数仅描述通道相似程度，不代表空间听感；两个通道均须分别有信号",
            "overall_sample_peak_dbfs": dbfs(np.max(np.abs(native))),
            "overall_rms_dbfs": dbfs(np.sqrt(np.mean(native.astype(np.float64) ** 2))),
            "sample_peak_note": "采样峰值不是过采样真峰值；不能单凭此项断言无重建过载或听感失真",
            "significant_silence_definition": "临时单声道50ms窗RMS低于-60dBFS，持续至少0.3秒",
            "significant_silence_intervals": quiet,
            "analysis_method": {"mono_sample_rate_hz": sr, "stft_window_samples": nfft,
                                "hop_samples": hop, "hop_sec": round(hop/sr, 9),
                                "score": "0.8×正向频谱通量95分位归一值 + 0.2×50ms RMS正向增量95分位归一值",
                                "peak_min_spacing_sec": .18, "cut_search_radius_sec": .6,
                                "precision_note": "候选是约10ms步长/46ms窗的能量瞬态估计；30fps取整误差另列，不等于物理拍点误差"},
            "bpm": None,
            "bpm_note": "不将自由速度或复合节奏硬拟合为已确认BPM；未做人工听审",
            "music_edited": False,
            "cuts_automatically_changed": False,
            "cut_candidates": cuts,
            "scene_action_candidates": action_suggestions,
            "detected_transient_candidate_count": len(candidates),
            "one_second_envelope": envelope,
            "manual_checks_pending": ["完整音乐听审与段落情绪判断", "候选是否为可听见的音乐重音或乐句变化",
                                      "所有文字实际稳定可读时间", "字幕/路线动作在最终成片中的听感同步"],
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "音乐节拍候选.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "音乐检测说明.md").write_text(make_markdown(result), encoding="utf-8")
    return result


def make_markdown(d: dict) -> str:
    lines = ["# 固定配乐检测与动作候选", "",
             "本记录是**自动音频分析，尚未人工听审**。频谱通量或能量峰可能来自音色、和声、鼓击或噪声变化，不自动等同于强拍。没有编造精确 BPM，也没有修改音乐或自动替换分镜。", "",
             "## 原音轨与技术检查", "",
             f"- 文件：`{d['source_relative_path']}`；SHA256：`{d['source_sha256']}`，与配乐锁定信息一致。",
             f"- AAC / {d['sample_rate_hz']} Hz / {d['channels']} 声道；音轨起点 {d['stream_start_sec']:.6f} 秒，标记时长 {d['stream_duration_sec']:.6f} 秒；全轨完整解码成功。",
             f"- 解码样本时长 {d['decoded_native_duration_sec']:.9f} 秒，比音轨标记时长多 {d['decoded_minus_stream_duration_ms']:.6f} 毫秒；AAC 边界的毫秒级尾差保留，不变速、不裁剪、不循环、不补音。",
             f"- 本次完整解码 s16le 字节数 {d['decoded_pcm_s16le_bytes']}；与锁定参考PCM核验一致：{d['decoded_pcm_matches_locked_reference']}。",
             f"- 总体采样峰值 {d['overall_sample_peak_dbfs']:.4f} dBFS；总体 RMS {d['overall_rms_dbfs']:.4f} dBFS。采样峰值不等于过采样真峰值，不代替听感检查。",
             f"- 双声道相关系数 {d['stereo_channel_correlation']}；该值仅描述相似性，不评判立体声听感。", "",
             "| 声道 | 采样峰值 dBFS | 全轨RMS dBFS | ≥0dBFS样本数 |", "|---|---:|---:|---:|"]
    for c in d['channel_measurements']:
        lines.append(f"| {c['channel']} | {c['sample_peak_dbfs']} | {c['integrated_rms_dbfs']} | {c['samples_at_or_above_0dbfs']} |")
    lines += ["", "显著静音定义：" + d['significant_silence_definition'] + "。",
              "检出区间：" + (json.dumps(d['significant_silence_intervals'], ensure_ascii=False) if d['significant_silence_intervals'] else "无符合阈值的区间。"), "",
              "## 切点附近候选（未采纳）", "",
              "各内部切点仅在原点±0.6秒内寻找可用瞬态；0秒与120秒边界固定。原时间轴仍生效。帧号按30fps最近帧取整，误差是量化差，不是已知拍点误差。", "",
              "| 原切点 s | 候选原秒数 | 建议对齐帧 | 帧对应秒数 | 取整误差 ms |", "|---:|---:|---:|---:|---:|"]
    for c in d['cut_candidates']:
        p = c['suggested_candidate']
        lines.append(f"| {c['original_cut_sec']} | {p['analysis_time_sec'] if p else '固定边界'} | {p['nearest_frame'] if p else c['original_cut_frame']} | {p['aligned_time_sec'] if p else c['original_cut_sec']} | {p['alignment_error_ms'] if p else 0} |")
    lines += ["", "120秒是结束边界3600，不是画面中存在索引3600的一帧；实际末帧索引3599。", "",
              "## 每幕动作候选与阅读余量", "",
              "这些时刻可供路线起止、主体动作或单次强调选择。字幕应先保证稳定可读，再决定是否移到候选帧，不能为卡点频繁跳字。下表的阅读余量假设相邻切点建议同时被采纳，尚未改写分镜。", "",
              "| 幕 | 动作候选（秒 / 帧） | 原稳定阅读计划 s | 邻接候选切点后的幕长 s | 剩余转场余量 s |", "|---|---|---:|---:|---:|"]
    for s in d['scene_action_candidates']:
        choices = "；".join(f"{c['aligned_time_sec']:.3f} / {c['nearest_frame']}" for c in s['action_candidates'])
        lines.append(f"| {s['scene_id']} | {choices} | {s['planned_stable_reading_sec']} | {s['if_both_neighbor_cut_candidates_adopted_duration_sec']} | {s['remaining_transition_allowance_sec']} |")
    lines += ["", "## 方法与复现", "",
              "使用 FFmpeg 在临时目录解码单声道 22050Hz PCM；仅该分析副本作下混与重采样，原 M4A 未改。另以原采样率、原声道 float32 PCM 测峰值与 RMS，避免 s16 饱和掩盖采样越界。STFT 使用1024点Hann窗、220点步长，综合正向频谱通量与约50ms RMS上升量检测瞬态。没有用这些结果假称人工听审。临时文件退出时删除。", "",
              "在项目根目录运行；从其他工作目录运行时改用脚本的绝对路径，素材仍以脚本自身位置定位：", "",
              "```bash", "python 工程/analyze_audio.py", "```", "",
              "依赖 Python、NumPy、SciPy 以及 PATH 中的 ffmpeg/ffprobe。输出为本目录的 JSON 和本说明。脚本分析前后核验音轨SHA256，若锁定信息不符立即终止。", "",
              "最终需由制作方完整听审音乐，选择切点并结合文字预算；再在成片中听看核对转场、路线到达与字幕。当前所有候选均标为未采纳、未人工听审。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, default=ROOT / "配乐" / "固定BGM_用户指定_原音轨.m4a")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "数据")
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    if args.fps <= 0:
        parser.error("--fps must be positive")
    report = analyze(args.audio.resolve(), args.output_dir.resolve(), args.fps)
    print(json.dumps({"source_hash_matches_lock": report["source_hash_matches_lock"],
                      "decode_success": report["full_decode_success"],
                      "transient_candidate_count": report["detected_transient_candidate_count"],
                      "output": str(args.output_dir.resolve()), "listening_review": "pending"}, ensure_ascii=False))
