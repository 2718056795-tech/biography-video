#!/usr/bin/env python3
"""Cumulative life map, independent of the resized illustration/actor stage.

draw_life_map(canvas, scene_id, t, duration) overlays native 880x430 at (96,150).
All routes, coastlines, markers share one geographic transform. No network.
"""
from pathlib import Path
from functools import lru_cache
import json
import math
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'素材/一生足迹'
DATA=json.loads((ROOT/'数据/一生足迹.json').read_text())
NODES={n['id']:n for n in DATA['nodes']}
SEQUENCE=DATA['sequence']
W,H=880,430
POS=(96,150)
SS=2
LAT0=32.75
BOUNDS=(103.,123.,27.,38.5)
PLOT=(20.,8.,860.,415.)
INK=(69,83,71)
ACCENT=(138,89,62)
WHEAT=(197,168,107)


def ease(t):
    t=max(0.,min(1.,t));return t*t*(3-2*t)


def project(lon,lat):
    return ((lon-113.)*math.cos(math.radians(LAT0)),lat-LAT0)


X0,Y0=project(BOUNDS[0],BOUNDS[2]);X1,Y1=project(BOUNDS[1],BOUNDS[3])
SCALE=min((PLOT[2]-PLOT[0])/(X1-X0),(PLOT[3]-PLOT[1])/(Y1-Y0))
OX=(PLOT[0]+PLOT[2]-(X1-X0)*SCALE)/2
OY=(PLOT[1]+PLOT[3]-(Y1-Y0)*SCALE)/2


def pixel(lon,lat):
    x,y=project(lon,lat)
    return (OX+(x-X0)*SCALE,OY+(Y1-y)*SCALE)


POINTS=[pixel(NODES[k]['longitude'],NODES[k]['latitude']) for k in SEQUENCE]


@lru_cache(maxsize=16)
def font(size,bold=False):
    weight='Bold' if bold else 'Regular'
    return ImageFont.truetype(f'/usr/share/fonts/opentype/noto/NotoSansCJK-{weight}.ttc',size*SS,index=2)


def _line(d,pts,color,width=1):
    d.line([(round(x*SS),round(y*SS)) for x,y in pts],fill=color,width=max(1,round(width*SS)),joint='curve')


def _circle(d,x,y,r,fill=None,outline=None,width=1):
    d.ellipse(tuple(round(v*SS) for v in (x-r,y-r,x+r,y+r)),fill=fill,outline=outline,width=max(1,round(width*SS)))


def _text(d,xy,text,size=20,color=INK+(235,),bold=False):
    d.text((round(xy[0]*SS),round(xy[1]*SS)),text,font=font(size,bold),fill=color,anchor='lt')


def _curve(i):
    a,b=POINTS[i],POINTS[i+1]
    dx,dy=b[0]-a[0],b[1]-a[1]
    length=max(.01,math.hypot(dx,dy));nx,ny=-dy/length,dx/length
    bend=min(23.,max(5.,length*.14))*(1 if i%2==0 else -1)
    c1=(a[0]+dx/3+nx*bend,a[1]+dy/3+ny*bend)
    c2=(a[0]+dx*2/3+nx*bend,a[1]+dy*2/3+ny*bend)
    return [((1-t)**3*a[0]+3*(1-t)**2*t*c1[0]+3*(1-t)*t*t*c2[0]+t**3*b[0],
             (1-t)**3*a[1]+3*(1-t)**2*t*c1[1]+3*(1-t)*t*t*c2[1]+t**3*b[1]) for t in [j/90 for j in range(91)]]


CURVES=[_curve(i) for i in range(len(POINTS)-1)]


@lru_cache(maxsize=1)
def _base():
    im=Image.new('RGBA',(W*SS,H*SS),(0,0,0,0));d=ImageDraw.Draw(im)
    raw=json.loads((FOLDER/'CHN.geo.json').read_text())
    features=raw.get('features',[raw])
    # Keep only the recognizable eastern seacoast. No western/northern land
    # boundary is repurposed as ancient territory, and no fake river is drawn.
    for f in features:
        g=f['geometry']
        polygons=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
        for poly in polygons:
            run=[]
            for lon,lat in poly[0]:
                valid=117.3<=lon<=123 and 27<=lat<=38.5
                if valid:
                    run.append(pixel(lon,lat))
                else:
                    if len(run)>1:_line(d,run,(86,117,102,94),1.1)
                    run=[]
            if len(run)>1:_line(d,run,(86,117,102,94),1.1)
    return im


def _region(d,alpha=200):
    # Enclose the Yueyang/Changsha stage as a broad region, not a death pin.
    a=pixel(NODES['yueyang']['longitude'],NODES['yueyang']['latitude'])
    b=pixel(NODES['tanzhou']['longitude'],NODES['tanzhou']['latitude'])
    cx=(a[0]+b[0])/2;cy=(a[1]+b[1])/2
    radius=26*SCALE/(221/11.5)
    box=(cx-radius,cy-radius,cx+radius,cy+radius)
    d.ellipse(tuple(round(v*SS) for v in box),outline=ACCENT+(min(alpha,130),),width=2*SS)
    _text(d,(cx+radius+9,cy-4),'湖湘（范围）',26,ACCENT+(alpha,))


def render_map(scene_id,t,duration):
    plan=DATA['scenes'][scene_id]
    start,end=plan['start_index'],plan['end_index']
    im=_base().copy();d=ImageDraw.Draw(im)
    for i,key in enumerate(SEQUENCE):
        x,y=POINTS[i]
        _circle(d,x,y,1.9,INK+(30 if i>end else 65,))
    current=start
    segments=max(0,end-start)
    active_window=min(5.5,max(1.,duration*.6))
    slot=active_window/max(1,segments)
    for j,path in enumerate(CURVES):
        if j>=end:break
        if j<start:
            progress=1.
            age=end-j
            alpha=max(70,135-age*4)
            _line(d,path,ACCENT+(alpha,),1.3)
        else:
            progress=ease((t-.45-(j-start)*slot)/(slot*.85))
            if progress>0:
                n=max(2,min(len(path),round(1+progress*(len(path)-1))))
                alpha=210 if progress<1 else 165
                _line(d,path[:n],WHEAT+(64,),4.5)
                _line(d,path[:n],ACCENT+(alpha,),2.1)
                tip=path[n-1];_circle(d,*tip,2.7,ACCENT+(220,))
        if progress>=.99:current=j+1
    # Stopovers keep the same location; no duplicate city-to-itself travel.
    if segments==0:current=end
    if scene_id=='S01':
        # Poetic prelude shows no current hometown marker over the cottage.
        for path in CURVES:_line(d,path,ACCENT+(32,),.85)
    elif scene_id=='S12':
        _region(d)
    else:
        x,y=POINTS[current]
        _circle(d,x,y,8.5,outline=ACCENT+(110,),width=1)
        _circle(d,x,y,4.2,ACCENT+(245,))
        name=NODES[SEQUENCE[current]]['label']
        if scene_id=='S11' and SEQUENCE[current]=='tanzhou':
            _region(d)
        else:
            tx=x+13;ty=y-22
            width=font(28).getlength(name)/SS
            if tx+width>W-6:tx=x-width-12
            ty=max(4,min(H-54,ty))
            # Text follows point, with no opaque label card.
            d.text((round(tx*SS),round(ty*SS)),name,font=font(28,True),
                   fill=ACCENT+(245,),stroke_width=2*SS,stroke_fill=(220,210,188,155),anchor='lt')
    return im.resize((W,H),Image.Resampling.LANCZOS)


def draw_life_map(canvas,scene_id,t,duration):
    if canvas.mode!='RGBA' or canvas.size!=(1080,1920):
        raise ValueError('life map expects native 1080x1920 RGBA')
    canvas.alpha_composite(render_map(scene_id,t,duration),POS)


def export_checks():
    FOLDER.mkdir(parents=True,exist_ok=True)
    base=_base().resize((W,H),Image.Resampling.LANCZOS)
    base.save(FOLDER/'透明地理底图.png')
    panel=Image.new('RGB',(W*2,H*6),(220,210,188))
    for i in range(12):
        sid=f'S{i+1:02d}'
        tile=render_map(sid,8.5,9.)
        tile.save(FOLDER/f'{sid}_足迹.png')
        panel.paste(tile,((i%2)*W,(i//2)*H),tile)
    panel.save(FOLDER/'12幕累积足迹预览.png')
    result={'size':[W,H],'position':POS,'point_bounds':[min(p[0] for p in POINTS),min(p[1] for p in POINTS),max(p[0] for p in POINTS),max(p[1] for p in POINTS)],'nodes':[{'sequence_index':i,'id':key,'pixel':POINTS[i]} for i,key in enumerate(SEQUENCE)],'single_scale':SCALE,'no_death_marker':True}
    (FOLDER/'投影与像素核对.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':export_checks()
