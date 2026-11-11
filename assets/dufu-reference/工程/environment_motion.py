#!/usr/bin/env python3
"""Original articulated environment animation, native 1080x1920.

get_base_layers(sid) returns replacement RGBA layers, always full canvas size.
draw_environment mutates canvas; call back after BG and front after actors.
Nothing moves the whole background. No network or generated-image dependency.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / '素材' / '动画底层'
SOURCE = ROOT / '素材' / '图层'
W, H = 1080, 1920
INK = (30, 42, 38)
DARK = (69, 83, 71)
MOSS = (109, 124, 104)
LIGHT_MOSS = (167, 175, 150)
RUST = (163, 107, 78)
WHEAT = (197, 168, 107)
PAPER = (243, 235, 220)
SVG_NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG_NS)
Y0, Y1 = 724, 1460


def ease(value):
    p = max(0., min(1., value))
    return p*p*(3-2*p)


def boat_x(t, duration):
    """Shared exact trajectory with actor_motion.py (deck center)."""
    return 300. + 350. * ease(t / max(.01, duration))


def boat_y(t, duration):
    return 1215. + 3. * math.sin(t * 1.2)


def _color(color, alpha=255):
    return tuple(color) + (max(0, min(255, round(alpha))),)


def _rotate(points, pivot, angle):
    cs, sn = math.cos(angle), math.sin(angle)
    px, py = pivot
    return [(px+(x-px)*cs-(y-py)*sn, py+(x-px)*sn+(y-py)*cs) for x, y in points]


class Painter:
    """Scene-art ROI; no new full-frame allocation per environment pass."""
    def __init__(self):
        self.im = Image.new('RGBA', (W, Y1-Y0), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def polygon(self, points, color, alpha=255):
        self.d.polygon([(round(x), round(y-Y0)) for x, y in points], fill=_color(color, alpha))

    def line(self, points, color, width=2, alpha=255):
        self.d.line([(round(x), round(y-Y0)) for x, y in points], fill=_color(color, alpha), width=width, joint='curve')

    def ellipse(self, box, color, alpha=255):
        x0, y0, x1, y1 = box
        self.d.ellipse((round(x0), round(y0-Y0), round(x1), round(y1-Y0)), fill=_color(color, alpha))

    def finish(self, canvas):
        canvas.alpha_composite(self.im, (0, Y0))


def _edit_layer(sid, layer):
    """Delete only objects that this module redraws. Original SVGs stay intact."""
    tree = ET.parse(SOURCE / f'{sid}_{layer}.svg')
    group = next(x for x in tree.getroot() if x.get('id') == layer)
    if sid in ('S01', 'S09') and layer == 'mid':
        children = list(group)
        roof = children[0]
        # One thatch flap is removed from the static roof and later hinged.
        roof.set('d', 'M-40 800 L125 761 L275 797 L281 863 L467 897 L470 815 L570 793 L676 845 L788 807 L1120 885 L1120 944 L-40 876 Z')
        group.remove(children[1])  # static highlight would cross the moving gap
        for node in list(group):
            if node.tag.endswith('rect') and node.get('x') == '650':
                group.remove(node)  # warm window is drawn in back, frame stays
    elif sid == 'S08' and layer == 'mid':
        for node in list(group):
            if node.get('transform', '').startswith('translate(942'):
                group.remove(node)
    elif sid == 'S10' and layer == 'fg':
        for node in list(group):
            if node.get('fill') == '#A36B4E':
                group.remove(node)  # replace the two still leaves
    elif sid in ('S02','S05','S07') and layer == 'fg' or sid == 'S11' and layer in ('mid', 'fg'):
        group.clear()
        group.set('id', layer)
    ASSETS.mkdir(parents=True, exist_ok=True)
    svg = ASSETS / f'{sid}_{layer}.svg'
    png = ASSETS / f'{sid}_{layer}.png'
    tree.write(svg, encoding='utf-8', xml_declaration=True)
    result = subprocess.run(['inkscape', str(svg), '--export-type=png',
        '--export-filename', str(png), '--export-width=1080', '--export-height=1920'],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return Image.open(png).convert('RGBA')


@lru_cache(maxsize=12)
def get_base_layers(scene_id):
    """Only replacement layer keys are returned; all are native 1080x1920."""
    replacements = {
        'S01': ('mid',), 'S02': ('fg',), 'S05': ('fg',), 'S07': ('fg',), 'S08': ('mid',), 'S09': ('mid',),
        'S10': ('fg',), 'S11': ('mid', 'fg'),
    }
    return {key: _edit_layer(scene_id, key) for key in replacements.get(scene_id, ())}


def _window(p, t, sid):
    # Real window aperture; small continuous light change, no large overlay sweep.
    strength = .5 + .5*math.sin(t*1.3 + .3*math.sin(t*.7))
    alpha = 166 + 18*strength
    p.polygon([(650,985),(783,985),(783,1178),(650,1178)], WHEAT, alpha)
    p.polygon([(660,995),(773,995),(773,1168),(660,1168)], (214,179,116), 22+12*strength)


def _thatch(p, t, sid, duration):
    # Hinge attached at the left edge; S09 mid-scene gust lifts the right edge.
    if sid == 'S09':
        gust = math.exp(-((t-duration*.48)/max(1.,duration*.18))**2)
        angle = -.08 - .26*gust - .055*math.sin(t*2.4)
    else:
        angle = -.025 - .065*(.5+.5*math.sin(t*1.7))
    pivot = (280.,858.)
    flap = [(275,797),(374,764),(470,815),(467,897),(281,863)]
    p.polygon(_rotate(flap,pivot,angle), DARK)
    # Uneven, coherent straw fibers move with the flap, not isolated particles.
    for points in [[(293,817),(452,863)],[(311,798),(460,844)],[(287,847),(452,890)]]:
        p.line(_rotate(points,pivot,angle), WHEAT, 3, 74)
    # The free ends are long enough to read at phone size.
    ends=[[(424,836),(493,855)],[(433,850),(506,879)],[(417,855),(481,888)]]
    for points in ends:
        p.line(_rotate(points,pivot,angle), DARK, 7, 255)


def _rain(p, t, sid):
    speed = 330 if sid == 'S09' else 230
    count = 54 if sid == 'S09' else 32
    length = 38 if sid == 'S09' else 27
    slant = 23 if sid == 'S09' else 9
    # Deterministic cyclic drops with continuous positions and long travel.
    for k in range(count):
        y = 748 + ((k*87 + t*speed) % 654)
        x = (k*173 + 39 - (y-748)*slant/length) % 1180 - 50
        if sid in ('S01','S09') and 92 < x < 824 and y > 910:
            continue  # the open room stays sheltered; rain is outside
        p.line([(x,y),(x-slant,y+length)], DARK, 2, 70 if sid=='S09' else 44)
    if sid == 'S09':
        # A single roof leak is causal and stays away from the poet and paper.
        y = 938 + ((t*310) % 330)
        p.line([(206,y),(204,y+20)], DARK, 3, 88)


def _clouds(p, t):
    # Broad linked shapes (not floating bright dots), moving at different depths.
    for k, (base_x,base_y,speed,alpha) in enumerate([(-90,855,14,95),(440,945,-10,72)]):
        dx = base_x + speed*t
        top=[];bottom=[]
        for j in range(25):
            x=dx+j*25
            top.append((x,base_y+9*math.sin(j*.45)+4*math.cos(j*.91)))
            bottom.append((x,base_y+23+8*math.sin(j*.35+.6)))
        p.polygon(top+list(reversed(bottom)), PAPER, alpha)


def _banner(p,t):
    pole_x,pole_y=788,858
    p.line([(pole_x,pole_y-18),(pole_x,pole_y+240)], DARK, 6)
    sway=16*math.sin(t*1.75)
    pts=[(pole_x+4,pole_y),(pole_x+48,pole_y+5),(pole_x+88,pole_y+13+sway*.3),
         (pole_x+105+sway,pole_y+36),(pole_x+82+sway*.8,pole_y+119),
         (pole_x+39+sway*.3,pole_y+111),(pole_x+4,pole_y+107)]
    p.polygon(pts,MOSS)
    p.line([(pole_x+14,pole_y+11),(pole_x+29+sway*.2,pole_y+91)], WHEAT, 3, 100)


def _lantern(p,t):
    hinge=(447,853)
    angle=.16*math.sin(t*1.55)
    rope=_rotate([(447,853),(447,885)],hinge,angle)
    body=_rotate([(425,885),(467,885),(476,910),(465,949),(431,949),(418,910)],hinge,angle)
    p.line(rope,DARK,3)
    p.polygon(body,RUST)
    inner=_rotate([(432,890),(460,890),(467,911),(459,941),(435,941),(426,911)],hinge,angle)
    p.polygon(inner,WHEAT,230)
    p.line(_rotate([(447,949),(447,968)],hinge,angle),RUST,3)


def _grass(p,t):
    for i,(x,y) in enumerate([(136,1312),(164,1323),(802,1320),(831,1328)]):
        wind=18*math.sin(t*2.05+i*.55)
        for j,(off,high) in enumerate([(-16,61),(0,79),(16,49)]):
            pts=[]
            for q in range(12):
                u=q/11
                pts.append((x+off*u+wind*u*u, y-high*u))
            p.line(pts,INK,5 if j==1 else 4,225)


def _door_cloth(p,t):
    wind=18*math.sin(t*1.8)
    pts=[(142,887),(253,887),(252+wind*.3,957),(246+wind,1050),
         (216+wind*.8,1064),(186+wind*.6,1053),(147+wind*.3,1062)]
    p.polygon(pts,LIGHT_MOSS)
    for j in range(3):
        x=161+j*30
        p.line([(x,891),(x+wind*.25,971),(x+wind*.7,1048)],DARK,2,86)


def _bamboo(p,t):
    # Segmented trunks: accumulated bend grows towards the top, 25-45 px tips.
    for k,(bx,base,high) in enumerate([(924,1317,335),(970,1320,386),(888,1322,279)]):
        phase=t*1.55+k*.43
        amp=35*math.sin(phase)+8*math.sin(phase*1.8)
        points=[]
        for n in range(9):
            u=n/8
            points.append((bx+amp*u*u,base-high*u))
        p.line(points,MOSS,6,230)
        for n in range(1,8):
            x,y=points[n]
            p.line([(x-5,y),(x+5,y+1)],DARK,3,190)
        for j,u in enumerate([.35,.57,.76,.93]):
            x=bx+amp*u*u;y=base-high*u
            side=1 if (j+k)%2 else -1
            if x>925:
                side=-1  # keep complete leaf silhouettes inside the portrait
            tip=(x+side*72,y-34+11*math.sin(phase+j*.5))
            p.line([(x,y),tip],MOSS,3,220)
            for n in range(3):
                q=(n+1)/3
                lx=x+(tip[0]-x)*q;ly=y+(tip[1]-y)*q
                wig=8*math.sin(phase*1.3+j+n)
                leaf=[(lx,ly),(lx+side*(23+wig),ly-25),
                      (lx+side*(43+wig),ly-30),(lx+side*28,ly-8)]
                p.polygon(leaf,MOSS,220)
                leaf2=[(lx,ly),(lx+side*26,ly+8),(lx+side*(38+wig),ly+23),(lx+side*10,ly+14)]
                p.polygon(leaf2,MOSS,215)


def _water(p,t,sid):
    if sid=='S10':
        for k in range(8):
            y=1210+k*22
            left=550-max(0,y-1250)*.85
            right=690-max(0,y-1250)*.55
            span=max(50,right-left)
            x=left+((t*35+k*31) % max(1,span-35))
            pts=[(x+j*8,y+1.7*math.sin(j*.8+t*.9)) for j in range(6)]
            p.line(pts,(220,215,194),2,135)


def _leaves(p,t):
    for k in range(4):
        period=7.4+k*.45
        u=((t+k*1.65) % period)/period
        y=778+605*u
        x=715+k*57-90*u+24*math.sin(u*math.pi*3+k)
        center=(x,y)
        leaf=[(x-3,y-15),(x+9,y-3),(x+6,y+13),(x-7,y+8),(x-11,y-1)]
        angle=1.1*math.sin(u*math.pi*3+k)+u*2.3
        p.polygon(_rotate(leaf,center,angle),RUST,210)
        p.line(_rotate([(x,y-10),(x-1,y+9)],center,angle),DARK,1,120)


def _boat(p,t,duration):
    cx,cy=boat_x(t,duration),boat_y(t,duration)
    # An asymmetric actual hull translates 350 px over the scene.
    hull=[(cx-251,cy-4),(cx-161,cy+10),(cx+25,cy+12),(cx+177,cy-8),
          (cx+246,cy-30),(cx+212,cy+15),(cx+139,cy+45),(cx+42,cy+55),
          (cx-83,cy+49),(cx-181,cy+29)]
    p.polygon(hull,INK)
    # Stern shelter remains a flat cutout, leaving the old poet at cx-100 visible.
    canopy=[(cx+23,cy+8),(cx+33,cy-36),(cx+60,cy-59),(cx+96,cy-57),
            (cx+129,cy-33),(cx+147,cy-6)]
    p.polygon(canopy,DARK)
    p.line([(cx-222,cy+1),(cx-122,cy+17),(cx+10,cy+19),(cx+143,cy+1),(cx+219,cy-18)],WHEAT,3,140)
    # Mounted steering/rowing oar makes a slow power stroke and a return arc.
    ph=(t*.47) % 1
    ang=-.64 + 1.05*ease(ph/.64) if ph<.64 else .41-1.05*ease((ph-.64)/.36)
    pivot=(cx+163,cy+1)
    shaft=_rotate([(cx+154,cy-31),(cx+181,cy+97)],pivot,ang)
    blade=_rotate([(cx+174,cy+72),(cx+192,cy+78),(cx+204,cy+115),(cx+184,cy+111)],pivot,ang)
    # An anonymous small boatman operates this oar. Feet stay on the deck;
    # both grip points are interpolated ON the already rotated shaft.
    grips=[(shaft[0][0]+u*(shaft[1][0]-shaft[0][0]),
            shaft[0][1]+u*(shaft[1][1]-shaft[0][1])) for u in (.025,.14)]
    lean=(grips[0][0]-(cx+160))*.16
    hip=(cx+174,cy-44)
    shoulder=(cx+174+lean,cy-79)
    head=(cx+172+lean*1.25,cy-103)
    # Feet follow the existing rising bow-side deck surface, never the water.
    p.line([(cx+170,cy-42),(cx+160,cy-24),(cx+151,cy-4)],INK,10)
    p.line([(cx+179,cy-42),(cx+189,cy-28),(cx+196,cy-14)],INK,10)
    p.line([(cx+144,cy-3),(cx+159,cy-3)],INK,7)
    p.line([(cx+190,cy-13),(cx+203,cy-15)],INK,7)
    p.polygon([(shoulder[0]-12,shoulder[1]-4),(shoulder[0]+13,shoulder[1]-3),
               (hip[0]+15,hip[1]+3),(hip[0]-13,hip[1]+3)],INK)
    p.line([(shoulder[0],shoulder[1]-1),(head[0]+1,head[1]+12)],INK,10)
    p.ellipse((head[0]-9,head[1]-10,head[0]+10,head[1]+11),INK)
    # Plain cloth cap; no portrait detail or new historical identity claim.
    p.polygon([(head[0]-12,head[1]-8),(head[0]-8,head[1]-15),
               (head[0]+7,head[1]-16),(head[0]+12,head[1]-7)],INK)

    def elbow(a,b,upper=36.,lower=41.,side=1):
        dx,dy=b[0]-a[0],b[1]-a[1]
        distance=max(.01,math.hypot(dx,dy))
        reach=min(distance,upper+lower-.01)
        along=(upper*upper-lower*lower+reach*reach)/(2*reach)
        offset=math.sqrt(max(0.,upper*upper-along*along))
        return (a[0]+dx/distance*along-dy/distance*offset*side,
                a[1]+dy/distance*along+dx/distance*offset*side)

    for k,grip in enumerate(grips):
        joint=(shoulder[0]+(-5 if k==0 else 9),shoulder[1]+(0 if k==0 else 4))
        bend=elbow(joint,grip,side=-1 if k==0 else 1)
        p.line([joint,bend,grip],INK,8)
    p.line(shaft,RUST,7)
    p.polygon(blade,DARK)
    # Hands wrap OVER the shaft, making the contact unambiguous in each phase.
    for x,y in grips:
        p.ellipse((x-5,y-5,x+5,y+5),INK)


def _boat_water(p,t,duration):
    cx,cy=boat_x(t,duration),boat_y(t,duration)
    # Wake is lower than hull, plus a stern trail; it never crosses solid hull.
    for k in range(4):
        phase=(t*.68+k*.26)%1
        y=cy+67+k*15
        length=95+phase*75
        x=cx-200-phase*75-k*7
        pts=[(x+j*length/12,y+3*math.sin(j*.35+phase*3)) for j in range(13)]
        p.line(pts,MOSS,3,95*(1-phase*.65))
    for k in range(4):
        x=80+((t*31+k*237)%940)
        y=1338+k*21
        p.line([(x,y),(x+30,y-2),(x+72,y+1)],MOSS,2,86)


@lru_cache(maxsize=1)
def _scroll_letters():
    f=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc',60,index=2)
    letters=[]
    for char in '此心在人间':
        tile=Image.new('RGBA',(68,88),(0,0,0,0))
        ImageDraw.Draw(tile).text((4,8),char,font=f,fill=INK,anchor='lt')
        letters.append(tile)
    return tuple(letters)


def _scroll(p,t):
    # Width rises by >400px during 1-3.5 seconds. Both wood rollers travel.
    opening=ease((t-1)/2.5)
    width=70+510*opening
    left=535-width/2;right=535+width/2
    top,bottom=1099.,1283.
    # Sheet edges have broad irregularity, without changing the paper into CG.
    p.polygon([(left,top),(left+width*.24,top+8),(left+width*.49,top-3),
               (left+width*.76,top+3),(right,top-5),(right,bottom),
               (left+width*.72,bottom-4),(left+width*.44,bottom+5),
               (left+width*.2,bottom+7),(left,bottom-3)],PAPER)
    p.line([(left+17,top+19),(535,top+17),(right-17,top+12)],WHEAT,3,125)
    p.line([(left+18,bottom-18),(535,bottom-14),(right-17,bottom-18)],WHEAT,3,125)
    for x,sign in [(left,-1),(right,1)]:
        p.polygon([(x-11,top-8),(x+11,top-5),(x+13,bottom+5),(x-12,bottom+7)],RUST)
        p.ellipse((x-14,top-14,x+13,top+9),RUST)
        p.ellipse((x-13,bottom-5,x+13,bottom+15),RUST)
        p.line([(x+sign*5,top+15),(x+sign*6,bottom-6)],DARK,2,110)
    # Fixed fiber marks appear only inside the growing sheet; no screen sweep.
    if opening>.4:
        for k in range(6):
            x=left+31+k*max(1,width-65)/6
            p.line([(x,top+42+(k%2)*14),(x+11,top+42+(k%2)*14)],MOSS,1,30)
    # Real CJK glyphs, individually revealed across a cached ink mask.
    # The wipe does not invent stroke shapes or alter the stable title above.
    for k,tile in enumerate(_scroll_letters()):
        reveal=ease((t-3.55-k*.49)/.47)
        if reveal<=0:continue
        width_px=max(1,round(tile.width*reveal))
        visible=tile.crop((0,0,width_px,tile.height))
        p.im.alpha_composite(visible,(369+k*65,1146-Y0))


def draw_environment(canvas,scene_id,t,duration,stage='back'):
    if stage not in ('back','front'):
        raise ValueError(stage)
    if canvas.mode!='RGBA' or canvas.size!=(W,H):
        raise ValueError('draw_environment expects native 1080x1920 RGBA')
    if scene_id=='S07':
        return  # map is exclusively managed by the root renderer
    active_back=scene_id in ('S01','S02','S08','S09','S11')
    active_front=scene_id in ('S01','S03','S04','S05','S06','S08','S09','S10','S11','S12')
    if not (active_back if stage=='back' else active_front):
        return
    p=Painter()
    if stage=='back':
        if scene_id in ('S01','S09'):
            _window(p,t,scene_id);_rain(p,t,scene_id)
        elif scene_id=='S02':_clouds(p,t)
        elif scene_id=='S08':_rain(p,t,scene_id)
        elif scene_id=='S11':_boat(p,t,duration)
    else:
        if scene_id in ('S01','S09'):_thatch(p,t,scene_id,duration)
        elif scene_id=='S03':_banner(p,t)
        elif scene_id=='S04':_lantern(p,t)
        elif scene_id=='S05':_grass(p,t)
        elif scene_id=='S06':_door_cloth(p,t)
        elif scene_id=='S08':_bamboo(p,t)
        elif scene_id=='S10':_water(p,t,scene_id);_leaves(p,t)
        elif scene_id=='S11':_boat_water(p,t,duration)
        elif scene_id=='S12':_scroll(p,t)
    p.finish(canvas)


def _preview_frame(sid,t,duration):
    replacement=get_base_layers(sid)
    canvas=Image.open(SOURCE/f'{sid}_bg.png').convert('RGBA')
    draw_environment(canvas,sid,t,duration,'back')
    canvas.alpha_composite(replacement.get('mid') or Image.open(SOURCE/f'{sid}_mid.png').convert('RGBA'))
    # Diagnostic preview deliberately keeps S09's still poet; the actor module
    # replaces it in final rendering. S11 omits old subject to avoid static boat.
    if sid not in ('S11','S12'):
        canvas.alpha_composite(Image.open(SOURCE/f'{sid}_subject.png').convert('RGBA'))
    draw_environment(canvas,sid,t,duration,'front')
    canvas.alpha_composite(replacement.get('fg') or Image.open(SOURCE/f'{sid}_fg.png').convert('RGBA'))
    return canvas.convert('RGB')


def previews(sids):
    out=ROOT/'质检/动作预览';out.mkdir(parents=True,exist_ok=True)
    for sid in sids:
        duration=8.
        path=out/f'env_{sid}.mp4'
        proc=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y',
            '-f','rawvideo','-pix_fmt','rgb24','-s','540x960','-r','18','-i','pipe:0',
            '-an','-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p',
            '-movflags','+faststart',str(path)],stdin=subprocess.PIPE)
        times=[.2,2.6,4.3,7.5]
        sheet=Image.new('RGB',(1080,480),(220,210,188))
        for i,t in enumerate(times):
            tile=_preview_frame(sid,t,duration).crop((0,724,1080,1460)).resize((270,184),Image.Resampling.LANCZOS)
            sheet.paste(tile,(i*270,45))
            ImageDraw.Draw(sheet).text((i*270+8,18),f't={t:.1f}s',fill=INK)
        sheet.save(out/f'env_{sid}_motion_strip.png')
        for k in range(round(duration*18)):
            im=_preview_frame(sid,k/18,duration).resize((540,960),Image.Resampling.BILINEAR)
            proc.stdin.write(im.tobytes())
        proc.stdin.close()
        if proc.wait():raise RuntimeError(f'preview encode failed: {sid}')
        print(path,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--preview',nargs='+',default=['S09','S11'])
    args=parser.parse_args()
    previews(args.preview)
