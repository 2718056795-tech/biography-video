#!/usr/bin/env python3
"""Six-second isolated S07 revision preview; never invokes full movie render."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

from render_dufu import Scene

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'输出/杜甫_事件说明与原创评述_6秒预览_v4.mp4'
QA=ROOT/'质检'
AUDIO=ROOT/'配乐/固定BGM_用户指定_原音轨.m4a'
FPS=30
FRAMES=180
LOCAL_START=.4
AUDIO_START=56.4


def main():
    QA.mkdir(parents=True,exist_ok=True)
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    scene=Scene(6)
    assert scene.sid=='S07' and scene.duration>6.4
    before=hashlib.sha256(AUDIO.read_bytes()).hexdigest()
    cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
         '-f','rawvideo','-pix_fmt','rgb24','-video_size','1080x1920','-framerate','30','-i','pipe:0',
         '-ss',str(AUDIO_START),'-t','6','-i',str(AUDIO),
         '-map','0:v:0','-map','1:a:0','-frames:v',str(FRAMES),
         '-c:v','libx264','-preset','fast','-crf','18','-threads','2',
         '-pix_fmt','yuv420p','-vf','setsar=1','-r','30','-video_track_timescale','15360',
         '-c:a','copy','-t','6','-movflags','+faststart',
         '-metadata','title=杜甫｜事件说明与原创评述｜6秒预览V4',str(OUTPUT)]
    start=time.monotonic()
    with (QA/'6秒预览_渲染日志.log').open('w') as log:
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log)
        try:
            for frame in range(FRAMES):
                im=scene.frame(LOCAL_START+frame/FPS)
                if frame==90:
                    im.save(QA/'S07_地图放大_样片第3秒.png')
                proc.stdin.write(im.tobytes())
                if (frame+1)%60==0:print(f'preview {frame+1}/{FRAMES}',flush=True)
        finally:
            proc.stdin.close()
            rc=proc.wait()
    if rc:raise RuntimeError((QA/'6秒预览_渲染日志.log').read_text())
    probe=subprocess.run(['ffprobe','-v','error','-count_frames','-show_streams','-show_format',
                          '-of','json',str(OUTPUT)],capture_output=True,text=True,check=True)
    result=json.loads(probe.stdout)
    video=next(s for s in result['streams'] if s['codec_type']=='video')
    audio=next(s for s in result['streams'] if s['codec_type']=='audio')
    assert (video['width'],video['height'])==(1080,1920)
    assert video['avg_frame_rate']=='30/1'
    assert int(video['nb_read_frames'])==180
    assert abs(float(video['duration'])-6)<.0001
    decode=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(OUTPUT),'-f','null','-'],
                          capture_output=True,text=True)
    assert decode.returncode==0 and not decode.stderr.strip(),decode.stderr
    assert hashlib.sha256(AUDIO.read_bytes()).hexdigest()==before
    result['validation']={'full_decode':True,'decoded_frames':180,'video_duration_seconds':6,
                          'audio_method':'AAC stream copy; excerpt only; no filter/fade/volume/time stretch',
                          'audio_excerpt_start_seconds':AUDIO_START,'requested_excerpt_seconds':6,
                          'fixed_audio_source_unchanged':True,'audio_source_sha256':before,
                          'elapsed_seconds':round(time.monotonic()-start,2),'sample_only':True}
    (QA/'6秒预览_媒体验收.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(OUTPUT),'video_duration':video['duration'],
                      'container_duration':result['format']['duration'],
                      'audio_duration':audio['duration'],'frames':video['nb_read_frames'],
                      'full_decode':True},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
