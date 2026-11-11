#!/usr/bin/env python3
"""Original native portrait animation renderer. No generative image is used as a scene.
Renders the SVG-derived layers at 1080x1920, preserving the locked AAC audio stream.
"""
from pathlib import Path
import argparse
from functools import lru_cache
import hashlib
import json
import math
import os
import subprocess
import time
from PIL import Image, ImageDraw, ImageFont
from actor_motion import draw_actor
from environment_motion import get_base_layers, draw_environment
from life_map import draw_life_map

ROOT = Path(__file__).resolve().parents[1]
W, H, FPS = 1080, 1920, 30
INK = '#1E2A26'
MUTED = '#62705D'
ACCENT = '#8A593E'
PAPER = '#DCD2BC'
DATA = json.loads((ROOT/'数据/上屏文案.json').read_text())
MUSIC_DATA = json.loads((ROOT/'数据/音乐节拍候选.json').read_text())
CUTS = [0] + [x['suggested_candidate']['nearest_frame'] for x in MUSIC_DATA['cut_candidates'][1:-1]] + [3600]
SCENES = DATA['scenes']
for i, s in enumerate(SCENES):
    s['start_frame'], s['end_frame_exclusive'] = CUTS[i], CUTS[i+1]
    s['start_sec'], s['end_sec'] = CUTS[i]/FPS, CUTS[i+1]/FPS


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t*t*(3-2*t)


def opacity(t, start, end, duration):
    return smooth((t-start)/duration) * smooth((end-t)/duration)


@lru_cache(maxsize=48)
def font(size, bold=False, sans=False):
    kind = 'Sans' if sans else 'Serif'
    weight = 'Bold' if bold else 'Regular'
    path = Path('/usr/share/fonts/opentype/noto')/f'Noto{kind}CJK-{weight}.ttc'
    if not path.is_file():
        raise FileNotFoundError(f'Need Chinese font {path}; install Noto CJK or edit the font() mapping.')
    return ImageFont.truetype(str(path), size, index=2)


def wrap(text, size, max_width=770, bold=False, sans=False):
    result, current = [], ''
    for ch in text:
        if ch == '\n':
            result.append(current); current = ''; continue
        if current and font(size,bold,sans).getlength(current+ch)>max_width:
            result.append(current); current=ch
        else: current += ch
    if current: result.append(current)
    return result


def sprite(text, size, color=INK, bold=False, sans=False):
    f = font(size,bold,sans)
    bounds=f.getbbox(text,anchor='lt')
    im=Image.new('RGBA',(math.ceil(f.getlength(text))+8,bounds[3]-bounds[1]+8))
    ImageDraw.Draw(im).text((4,4),text,font=f,fill=color,anchor='lt')
    return im


class Layer:
    def __init__(self, image):
        self.box=image.getbbox()
        self.image=image.crop(self.box) if self.box else None
        self.cache={}
    def paste(self, canvas, dx=0, dy=0):
        if self.image is None: return
        ix,iy=math.floor(dx),math.floor(dy)
        fx,fy=round((dx-ix)*4),round((dy-iy)*4)
        if fx==4:ix+=1;fx=0
        if fy==4:iy+=1;fy=0
        key=(fx,fy)
        if key not in self.cache:
            self.cache[key]=self.image.transform((self.image.width+2,self.image.height+2),Image.Transform.AFFINE,
                (1,0,-fx/4,0,1,-fy/4),Image.Resampling.BICUBIC)
        canvas.alpha_composite(self.cache[key],(self.box[0]+ix,self.box[1]+iy))


class Scene:
    def __init__(self, index):
        self.index=index
        self.data=SCENES[index]
        self.sid=self.data['id']
        folder=ROOT/'素材/图层'
        overrides=get_base_layers(self.sid) or {}
        self.bg=(overrides['bg'] if 'bg' in overrides else Image.open(folder/f'{self.sid}_bg.png')).convert('RGBA')
        assert self.bg.size==(W,H)
        self.layers={}
        for name in ['mid','subject','fg']:
            im=(overrides[name] if name in overrides else Image.open(folder/f'{self.sid}_{name}.png')).convert('RGBA')
            assert im.size==(W,H)
            self.layers[name]=Layer(im)
        self.duration=(self.data['end_frame_exclusive']-self.data['start_frame'])/FPS
        self.text=[]
        self.boxes=[]
        self.header=Image.new('RGBA',(W,H))
        d=ImageDraw.Draw(self.header)
        d.text((96,100),'杜甫 / 此心在人间',font=font(27,sans=True),fill=MUTED,anchor='lt')
        d.text((796,100),f'{index+1:02d} / 12',font=font(25,sans=True),fill=MUTED,anchor='lt')
        self.create_text()
        self.create_commentary()
        self.action_times=[]
        for entry in MUSIC_DATA['scene_action_candidates']:
            if entry['scene_id']==self.sid:
                self.action_times=[x['nearest_frame']/FPS-self.data['start_sec'] for x in entry['action_candidates']]
        # A major motion starts near an early transient; continuous cycles remain natural.
        early=[x for x in self.action_times if .25<=x<=min(3.1,self.duration-4)]
        self.motion_start=early[0] if early else .4
        self.motion_duration=self.duration-self.motion_start

    def add_text(self,text,size,x,y,start,color=INK,bold=False,sans=False,role='main'):
        im=sprite(text,size,color,bold,sans)
        if x+im.width>904 and role in ('main','event','assessment'):raise ValueError((self.sid,text,'text exceeds horizontal safe area'))
        if role in ('main','event','assessment') and y+im.height>1498:raise ValueError((self.sid,text,'text exceeds vertical safe area'))
        self.text.append((im,x-4,y-4,start))
        self.boxes.append({'text':text,'size_px':size,'bounds':[x,y,x+im.width-8,y+im.height-8],'role':role,'full_opacity_after_sec':start+.28,'fade_out_begins_sec':self.duration-.45})

    def create_text(self):
        s=self.data
        if self.sid in ('S01','S12'):
            self.add_text('杜甫',96,96,595,.08,bold=True)
            self.add_text(s['title'],64,98,717,.25,color=ACCENT)
            meta='712—770' if self.sid=='S12' else '一生风雨，心系人间'
            self.add_text(meta,30,100,809,.40,color=MUTED,sans=True)
            for i,line in enumerate(wrap(s['explanation'],44,760)):
                self.add_text(line,44,98,870+i*64,.55+i*.12)
            return
        self.add_text(s['title'],70,96,595,.1,bold=True)
        self.add_text(s['meta'],30,100,688,.3,color=MUTED,sans=True)
        if s['quote_lines']:
            for i,line in enumerate(s['quote_lines']):
                self.add_text(line,64,96,752+i*80,.50+i*.28)
            y=752+len(s['quote_lines'])*80+1
            for i,line in enumerate(wrap(s['source_label'],27,760,sans=True)):
                self.add_text(line,27,100,y+i*40,.9,color=MUTED,sans=True,role='source')
        else:
            for i,line in enumerate(wrap(s['explanation'],48,760)):
                self.add_text(line,48,96,760+i*68,.5+i*.14)
            if s['source_label']:
                self.add_text(s['source_label'],30,100,913,.85,color=ACCENT,sans=True,role='source')

    def create_commentary(self):
        # Narrative captions have their own stable reading area, even when
        # the main text is a poem. They are original prose, not quotations.
        event=self.data.get('event_summary','').strip()
        assessment=self.data.get('assessment','').strip()
        if not event or not assessment:
            raise ValueError((self.sid,'event_summary and assessment are required'))
        size=34
        while size>32 and font(size,True,True).getlength(event)>780:
            size-=1
        if font(size,True,True).getlength(event)>780 or font(30,False,True).getlength(assessment)>780:
            raise ValueError((self.sid,'shorten commentary to one readable line per role'))
        event_start,assessment_start=(.85,1.45) if self.sid=='S01' else (1.15,1.85)
        self.add_text(event,size,120,1400,event_start,bold=True,sans=True,role='event')
        self.add_text(assessment,30,120,1450,assessment_start,color='#4D5C4B',sans=True,role='assessment')
        # A soft paper wash prevents scenery from reducing caption contrast.
        # The actors and their supports end above this band.
        self.commentary_wash=Image.new('RGBA',(W,H-1360),(0,0,0,0))
        d=ImageDraw.Draw(self.commentary_wash)
        paper=self.bg.getpixel((0,0))[:3]
        for y in range(self.commentary_wash.height):
            a=min(1.,y/40.)
            d.line([(0,y),(W,y)],fill=paper+(round(245*max(0.,a)),))
        d.line([(96,40),(96,126)],fill=ACCENT,width=3)

    def stage_layout(self):
        # Reserve y1400..1485 for explanatory prose, above platform controls.
        # All scene objects keep one isotropic scale and shared translation.
        if self.sid in ('S01','S09'):return .60,540
        if self.sid in ('S03','S04','S05'):return .72,420
        if self.sid=='S07':return .74,270
        if self.sid=='S08':return .78,270
        return .83,275

    def art(self,t):
        canvas=self.bg.copy()
        motion_t=max(0.0,t-self.motion_start)
        environment_t=motion_t if self.sid=='S11' else t
        environment_duration=self.motion_duration if self.sid=='S11' else self.duration
        draw_environment(canvas,self.sid,environment_t,environment_duration,stage='back')
        self.layers['mid'].paste(canvas)
        actor=draw_actor(self.sid,motion_t,self.motion_duration)
        if actor is not None:
            assert actor.size==(W,H)
            canvas.alpha_composite(actor)
        draw_environment(canvas,self.sid,environment_t,environment_duration,stage='front')
        self.layers['fg'].paste(canvas)
        return canvas

    def fit_stage(self,art):
        # Recompose native portrait art as an isotropic stage below the persistent map.
        # Edge extension prevents a rectangular card or blank sidebars.
        scale,offset=self.stage_layout()
        pad=max(0,math.ceil((W/scale-W)/2)+2)
        bottom=max(0,math.ceil((H-offset)/scale)-H+2)
        expanded=Image.new('RGBA',(W+2*pad,H+bottom))
        expanded.paste(art,(pad,0))
        expanded.paste(art.crop((0,0,1,H)).resize((pad,H),Image.Resampling.NEAREST),(0,0))
        expanded.paste(art.crop((W-1,0,W,H)).resize((pad,H),Image.Resampling.NEAREST),(W+pad,0))
        expanded.paste(expanded.crop((0,H-1,expanded.width,H)).resize((expanded.width,bottom),Image.Resampling.NEAREST),(0,H))
        scaled=expanded.resize((round(expanded.width*scale),round(expanded.height*scale)),Image.Resampling.BILINEAR)
        stage=Image.new('RGBA',(W,H),self.bg.getpixel((0,0)))
        stage.alpha_composite(scaled,((W-scaled.width)//2,offset))
        return stage

    def frame(self,t,next_art=None):
        canvas=self.fit_stage(self.art(t))
        draw_life_map(canvas,self.sid,t,self.duration)
        canvas.alpha_composite(self.commentary_wash,(0,1360))
        # Scene cuts follow the selected music boundaries; action is inside each scene.
        canvas.alpha_composite(self.header)
        for im,x,y,start in self.text:
            a=opacity(t,start,self.duration-.12,.28)
            if a<=0:continue
            if a<.999:
                im=im.copy();im.putalpha(im.getchannel('A').point(lambda v:round(v*a)))
            yoff=round(6*(1-smooth((t-start)/.35)))
            canvas.alpha_composite(im,(x,y+yoff))
        if self.sid=='S12' and t>self.duration-.48:
            # Only picture fades. Original AAC end is unchanged.
            a=smooth((t-(self.duration-.48))/.48)
            canvas=Image.blend(canvas,Image.new('RGBA',(W,H),PAPER),a)
        return canvas.convert('RGB')


def preview(indices):
    folder=ROOT/'质检/逐幕原生帧';folder.mkdir(parents=True,exist_ok=True)
    boxes=[]
    for index in indices:
        scene=Scene(index)
        scene.frame(min(3.5,scene.duration*.5)).save(folder/f'{scene.sid}.png')
        boxes.append({'id':scene.sid,'text_boxes':scene.boxes})
        print('preview',scene.sid,flush=True)
    (ROOT/'质检/文字布局.json').write_text(json.dumps(boxes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if len(indices)==12:
        sheet=Image.new('RGB',(1080,2240),PAPER);d=ImageDraw.Draw(sheet)
        d.text((35,24),'杜甫｜此心在人间',font=font(42,bold=True),fill=INK)
        for i,s in enumerate(SCENES):
            im=Image.open(folder/f'{s["id"]}.png').convert('RGB');im.thumbnail((310,552),Image.Resampling.LANCZOS)
            x=35+(i%3)*350;y=98+(i//3)*530
            # Contact sheet thumbnails are reduced for review only; video remains native.
            im.thumbnail((278,494),Image.Resampling.LANCZOS)
            sheet.paste(im,(x,y))
            d.text((x,y+496),f'{i+1:02d}  {s["title"]}',font=font(21,sans=True),fill=INK)
        sheet.save(ROOT/'质检/杜甫_12幕分镜预览.png')


def render_signature(index):
    """A changed renderer, scene copy, map or SVG export invalidates the clip cache."""
    scene=SCENES[index]
    names=[scene['id']]
    if index+1<len(SCENES):names.append(SCENES[index+1]['id'])
    inputs=[Path(__file__),Path(__file__).with_name('actor_motion.py'),Path(__file__).with_name('environment_motion.py'),Path(__file__).with_name('life_map.py'),ROOT/'数据/一生足迹.json']
    for sid in names:
        inputs.extend(ROOT/'素材/图层'/f'{sid}_{name}.png' for name in ('bg','mid','subject','fg'))
        inputs.extend(sorted((ROOT/'素材/动画底层').glob(f'{sid}_*')))
        if sid=='S07':
            inputs.extend([ROOT/'素材/地图/routes.json',ROOT/'素材/地图/transparent_map.png'])
    inputs.extend(sorted((ROOT/'素材/一生足迹').glob('*')))
    hashes={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() if x.is_file() else None for x in inputs}
    return {'scene':scene,'next_scene':SCENES[index+1] if index+1<len(SCENES) else None,'inputs':hashes,'width':W,'height':H,'fps':FPS}


def assemble():
    clips=ROOT/'输出/片段'
    for scene in SCENES:
        path=clips/f"{scene['id']}.mp4"
        probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,nb_frames,avg_frame_rate','-of','json',str(path)],capture_output=True,text=True,check=True)
        stream=json.loads(probe.stdout)['streams'][0]
        assert (stream['width'],stream['height'])==(W,H)
        assert int(stream['nb_frames'])==scene['end_frame_exclusive']-scene['start_frame']
        assert stream['avg_frame_rate']=='30/1'
    listing=clips/'concat.txt'
    listing.write_text(''.join(f"file '{x['id']}.mp4'\n" for x in SCENES),encoding='utf-8')
    final=ROOT/'输出/杜甫_此心在人间_生平解读动画版_v4_1080p_120秒.mp4'
    audio=ROOT/'配乐/固定BGM_用户指定_原音轨.m4a'
    lock=json.loads((ROOT/'配乐/配乐锁定信息.json').read_text())
    assert hashlib.sha256(audio.read_bytes()).hexdigest()==lock['audio_sha256']
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),'-i',str(audio),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','copy','-movflags','+faststart','-metadata','title=杜甫｜此心在人间',str(final)],check=True)
    print('FINAL',final,flush=True)


def render(indices,resume):
    clips=ROOT/'输出/片段';clips.mkdir(parents=True,exist_ok=True)
    for index in indices:
        scene=Scene(index)
        count=scene.data['end_frame_exclusive']-scene.data['start_frame']
        target=clips/f'{scene.sid}.mp4'
        signature=render_signature(index)
        signature_path=clips/f'{scene.sid}.inputs.json'
        cache_matches=False
        if signature_path.is_file():
            try:cache_matches=json.loads(signature_path.read_text())==signature
            except (OSError,ValueError):pass
        if resume and target.is_file() and cache_matches:
            r=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=nb_frames','-of','csv=p=0',str(target)],capture_output=True,text=True)
            if r.returncode==0 and r.stdout.strip()==str(count):
                print('resume',scene.sid,count,flush=True);continue
        next_art=None
        tmp=clips/f'{scene.sid}.working.mp4'
        cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','18','-threads','2','-pix_fmt','yuv420p','-vf','setsar=1','-g','60','-video_track_timescale','15360','-movflags','+faststart',str(tmp)]
        started=time.monotonic()
        with (clips/f'{scene.sid}.log').open('w') as log:
            proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log)
            try:
                for f in range(count):
                    proc.stdin.write(scene.frame(f/FPS,next_art).tobytes())
                    if f and f%120==0:print('render',scene.sid,f,'/',count,f'{f/(time.monotonic()-started):.1f}fps',flush=True)
                proc.stdin.close()
                code=proc.wait()
                if code:raise RuntimeError(f'ffmpeg failed {scene.sid}; see log')
            except BaseException:
                proc.kill();proc.wait();raise
        tmp.replace(target)
        signature_path.write_text(json.dumps(signature,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('finished',scene.sid,count,f'{time.monotonic()-started:.1f}s',flush=True)
    if len(indices)==12:assemble()


def main():
    p=argparse.ArgumentParser();p.add_argument('--preview',action='store_true');p.add_argument('--render',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--assemble',action='store_true');p.add_argument('--scenes',default='all')
    args=p.parse_args()
    indices=list(range(12)) if args.scenes=='all' else [int(x)-1 for x in args.scenes.split(',')]
    if any(x<0 or x>=12 for x in indices):raise SystemExit('Scenes must be 1..12')
    timeline={'title':DATA['title'],'width':W,'height':H,'fps':FPS,'total_frames':3600,'duration_sec':120,'output_mode':'portrait','cut_frames':CUTS,'cut_method':'切幕沿用固定原音轨瞬态候选；角色关节和环境部件在幕内实际运动，主要动作采用前段候选启动；不冒称人工听审强拍','scenes':SCENES}
    (ROOT/'数据/最终时间轴.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.preview:preview(indices)
    if args.render:render(indices,args.resume)
    elif args.assemble:assemble()
    if not(args.preview or args.render or args.assemble):p.print_help()

if __name__=='__main__':main()
