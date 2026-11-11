#!/usr/bin/env python3
"""Original articulated, flat geometric Du Fu actors on a transparent 1080x1920 canvas.

Public interface: draw_actor(scene_id, t, duration) -> Pillow RGBA, local seconds.
No old subject bitmap is transformed. Limbs are rebuilt from shoulder/elbow/wrist
and hip/knee/ankle joints. The stance foot is planted at a world-space anchor;
the other foot follows a lifted swing arc. Clothes follow those joint positions.

S01 seated writing: head (470,1040), pen/forearm write on paper, occasional ink dip.
    Short non-letter draft marks accumulate along the pen path and survive the dip;
    they reset with the next 3.6s writing cycle rather than inventing quoted text.
S02 young walk x330->550, feet1300; final 2s plant feet and lift gaze.
S03 carry scroll walking x300->550 to the gate, feet1300.
S04 walk x760->540 with bundle, feet1300.
S05 x530 feet1300: unfold a blank letter, then lift gaze.
S06 x320 waving goodbye; another walker/bundle x600->850, feet1300.
S07 two small travellers x300->650 and x218->568, feet1450, about120px tall.
S08 seated writing/dipping: head(410,1070), paper above table1269.
S09 protect wind-blown paper: head(470,1040), wrist reach about70px, free corner curls.
S10 old actor/cane x330->480 feet1300; final2s stop and look up.
S11 elder seated at boat_x-100; feet near boat_y, blank pages open/turn.
    Boat geometry is deliberately absent. Import boat_x/boat_y in environment code.
S12 empty; environment owns closing scroll.

Run this file with --preview to write actor_S02_walk.mp4 and actor_S09_paper.mp4
under project/质检/动作预览. The preview background omits the old subject layer.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import math
import subprocess
from PIL import Image, ImageDraw

W,H=1080,1920
INK='#1E2A26'; FAR='#3D4C40'; GREEN='#6D7C68'; PAPER='#F3EBDC'; WARM='#C5A86B'
ROOT=Path(__file__).resolve().parents[1]
TAU=2*math.pi


def clamp(x,a=0.0,b=1.0): return max(a,min(b,x))
def ease(x):
    x=clamp(x)
    return x*x*(3-2*x)
def lerp(a,b,u):return a+(b-a)*u
def boat_x(t,duration):return 300+350*ease(float(t)/max(.001,float(duration)))
def boat_y(t,duration):return 1215+3*math.sin(float(t)*1.2)
def V(x,y):return (float(x),float(y))
def add(a,b):return (a[0]+b[0],a[1]+b[1])
def sub(a,b):return (a[0]-b[0],a[1]-b[1])
def length(a):return math.hypot(a[0],a[1])
def rotate(p,center,angle):
    x,y=p[0]-center[0],p[1]-center[1]
    return (center[0]+x*math.cos(angle)-y*math.sin(angle),center[1]+x*math.sin(angle)+y*math.cos(angle))


def ik(hip,ankle,l1,l2,bend=1):
    """Two rigid bones, knee/elbow chosen on the requested side of their target."""
    d=sub(ankle,hip);distance=max(.001,min(length(d),l1+l2-.001))
    ux,uy=d[0]/max(.001,length(d)),d[1]/max(.001,length(d))
    along=(l1*l1-l2*l2+distance*distance)/(2*distance)
    height=math.sqrt(max(0,l1*l1-along*along))
    return (hip[0]+ux*along-uy*height*bend, hip[1]+uy*along+ux*height*bend)


class Painter:
    def __init__(self,image,origin=(0,0),scale=1,face=1):
        self.im=image;self.d=ImageDraw.Draw(image);self.ox,self.oy=origin;self.s=scale;self.face=face
    def p(self,p):return (self.ox+self.face*p[0]*self.s,self.oy+p[1]*self.s)
    def poly(self,points,fill=INK):self.d.polygon([self.p(p) for p in points],fill=fill)
    def line(self,points,fill=GREEN,width=2):self.d.line([self.p(p) for p in points],fill=fill,width=max(1,round(width*self.s)),joint='curve')
    def joint(self,p,r,fill=INK):
        x,y=self.p(p);r=r*self.s;self.d.ellipse((x-r,y-r,x+r,y+r),fill=fill)
    def bone(self,a,b,wa,wb,fill=INK):
        delta=sub(b,a);norm=max(1,length(delta));nx=-delta[1]/norm;ny=delta[0]/norm
        self.poly([(a[0]+nx*wa,a[1]+ny*wa),(b[0]+nx*wb,b[1]+ny*wb),
                   (b[0]-nx*wb,b[1]-ny*wb),(a[0]-nx*wa,a[1]-ny*wa)],fill)
    def arm(self,shoulder,wrist,bend=1,shade=INK,upper=77,lower=79):
        elbow=ik(shoulder,wrist,upper,lower,bend)
        self.bone(shoulder,elbow,22,25,shade)
        self.joint(elbow,23,shade)
        self.bone(elbow,wrist,24,11,shade)
        self.joint(wrist,8,INK)
        seam=(lerp(elbow[0],wrist[0],.15),lerp(elbow[1],wrist[1],.15))
        self.line([seam,(lerp(elbow[0],wrist[0],.8),lerp(elbow[1],wrist[1],.8))],GREEN,1.3)
        return elbow


def head(p,center,age='middle',tilt=0):
    x,y=center
    pts=[(-18,-28),(-28,-16),(-27,1),(-19,12),(-14,22),(-13,31),
         (6,31),(9,20),(18,17),(20,9),(25,6),(18,0),(19,-12),(12,-26),(-2,-31)]
    pts=[rotate((x+a,y+b),center,tilt) for a,b in pts]
    p.poly(pts)
    neck=[(x-13,y+22),(x+6,y+24),(x+14,y+54),(x-16,y+54)]
    p.poly([rotate(q,center,tilt) for q in neck])
    cap=[(x-24,y-26),(x-19,y-44),(x+12,y-46),(x+25,y-27),(x+15,y-22)]
    p.poly([rotate(q,center,tilt) for q in cap])
    if age=='old':
        beard=[(x+7,y+17),(x+18,y+15),(x+14,y+35),(x+4,y+42),(x+1,y+25)]
        p.poly([rotate(q,center,tilt) for q in beard])
        p.line([rotate((x-20,y-28),center,tilt),rotate((x+14,y-30),center,tilt)],'#A7AF96',4)


def torso(p,hip,shoulder_center,age='middle',seated=False):
    hx,hy=hip;sx,sy=shoulder_center
    hem=hy+56 if not seated else hy+22
    points=[(sx-28,sy-8),(sx-43,sy+5),(sx-45,sy+32),(hx-32,hy-4),
            (hx-42,hem),(hx-4,hem+6),(hx+42,hem+2),(hx+29,hy-1),
            (sx+38,sy+24),(sx+32,sy+2),(sx+17,sy-8),(sx+3,sy+9),(sx-8,sy+5)]
    p.poly(points)
    p.line([(sx-17,sy-7),(sx-4,sy+15),(sx+15,sy-7)],'#A7AF96',2)
    p.line([(sx-4,sy+15),(hx-8,hy-13)],GREEN,1.4)
    p.line([(hx-28,hy),(hx+24,hy+2)],GREEN,1.3)


def shoe(p,ankle,face=1,shade=INK):
    x,y=ankle
    p.poly([(x-12,y-6),(x+12,y-7),(x+25,y+3),(x+22,y+10),(x-13,y+9)],shade)


def walker(im,t,duration,x0,x1,ground=1300,scale=1,age='middle',stop=0,bundle=False,scroll=False,period=1.28,cane=False):
    """World-space fixed stance anchors and lifted swing feet, with joint-driven sleeves."""
    face=1 if x1>=x0 else -1
    walk_d=max(.3,duration-stop)
    tt=min(max(0,t),walk_d)
    def body(at):return lerp(x0,x1,clamp(at/walk_d))
    x=body(tt)
    speed=(x1-x0)/walk_d
    settling=ease((t-walk_d)/.45) if t>=walk_d else 0
    active=(1-settling)
    phase=TAU*tt/period
    bounce=3.5*math.cos(2*phase)*active
    p=Painter(im,(x,ground),scale,face)
    # Coordinates below use scaled local units. Actual route is unscaled world motion.
    hip=(0,-121+bounce);shoulder=(5 if age=='old' else 0,-245+bounce)
    feet=[]
    for index,offset in enumerate((0,.5)):
        cycle=tt/period+offset;n=math.floor(cycle);u=cycle-n
        landed=(n-offset)*period
        ahead=abs(speed)*period*.30
        side=(-9 if index==0 else 10)
        def anchor(at):return body(at)+face*(ahead+side*scale)
        if u<.58:
            world_x=anchor(landed);lift=0
        else:
            q=(u-.58)/.42
            world_x=lerp(anchor(landed),anchor(landed+period),ease(q))
            lift=(23 if age!='old' else 16)*math.sin(math.pi*q)
        local_x=(world_x-x)/(scale*face)
        ankle=(lerp(local_x,side,settling),-8-lift*active)
        feet.append(ankle)
    # Far and near leg use distinct colour planes, then the robe follows their bends.
    for index in (0,1):
        h=(hip[0]+(-13 if index==0 else 13),hip[1])
        ankle=feet[index];knee=ik(h,ankle,58,59,bend=-1)
        shade=FAR if index==0 else INK
        p.bone(h,knee,23,23,shade);p.joint(knee,22,shade)
        p.bone(knee,ankle,22,12,shade);shoe(p,ankle,shade=shade)
        p.line([(knee[0]-2,knee[1]+6),(ankle[0]-3,ankle[1]-12)],GREEN,1)
    far_sh=(shoulder[0]-26,shoulder[1]+5)
    far_w=(far_sh[0]-13+28*math.sin(phase+.8)*active,shoulder[1]+128)
    p.arm(far_sh,far_w,-1,FAR,upper=62,lower=69)
    if bundle:
        p.poly([(-29,-245),(-66,-232),(-83,-198),(-69,-167),(-36,-170),(-22,-206)],FAR)
        p.line([(-25,-246),(17,-204)],GREEN,3)
    torso(p,hip,shoulder,age)
    near_sh=(shoulder[0]+29,shoulder[1]+7)
    if scroll:
        wrist=(58,-174+bounce+8*math.sin(phase)*active)
        p.poly([(43,-183),(98,-188),(104,-153),(45,-148)],PAPER)
        p.line([(49,-178),(97,-183)],WARM,2)
    elif cane:
        wrist=(72,-166+6*math.sin(phase)*active)
        # Cane remains planted over the stance part, then lifts and advances.
        u=(tt/1.65)%1;n=math.floor(tt/1.65)
        anchor0=body(n*1.65)+face*93*scale
        if u<.65:end_x=anchor0;end_y=-2
        else:
            q=(u-.65)/.35
            end_x=lerp(anchor0,body((n+1)*1.65)+face*93*scale,ease(q));end_y=-2-19*math.sin(math.pi*q)
        end_local=(lerp((end_x-x)/(face*scale),96,settling),end_y*active)
        p.line([(wrist[0]-10,wrist[1]-4),(wrist[0]+2,wrist[1]-8),end_local],INK,5)
    else:
        wrist=(near_sh[0]+10-32*math.sin(phase+.8)*active,shoulder[1]+126+8*math.cos(phase)*active)
    p.arm(near_sh,wrist,1,INK,upper=66,lower=71)
    look=-.18*ease((t-(duration-2))/1.1) if stop else 0
    headcenter=(shoulder[0]+(8 if age=='old' else 0),-291+bounce)
    head(p,headcenter,age,tilt=look)
    return (x,ground)


def blank_page(p,points,fold=0):
    p.poly(points,PAPER)
    p.line([points[0],points[1]],WARM,1.8)
    if fold:
        x,y=points[0]
        p.poly([(x,y),(x+30,y+fold),(x+14,y+24)],'#DCD2BC')


def seated(im,t,duration,x,head_y,mode='write',age='middle',scale=1):
    p=Painter(im,(x,head_y),scale)
    shoulder=(0,53);hip=(-5,160)
    # Folded legs, clear joint angles under the seated robe.
    p.bone((-16,151),(-62,204),28,26,INK);p.bone((-62,204),(20,228),25,20,INK)
    p.bone((15,153),(67,204),27,24,FAR);p.bone((67,204),(100,222),23,17,FAR)
    p.poly([(-38,144),(-78,199),(-65,235),(78,236),(104,221),(58,195),(27,151)],INK)
    torso(p,hip,shoulder,age,seated=True)
    head(p,(5,0),age,.10 if mode=='write' else .03*math.sin(t))
    if mode=='protect':
        reach=.5+.5*math.sin(TAU*t/2.6-.7)
        wrist=(125+70*reach,155+13*math.sin(TAU*t/2.6))
        flutter=19*math.sin(TAU*t/1.3)
        page=[(wrist[0]-157,wrist[1]+17-flutter),(wrist[0]+4,wrist[1]+5),
              (wrist[0]+16,wrist[1]+77),(wrist[0]-144,wrist[1]+87)]
        blank_page(p,page,fold=22+10*math.sin(t*3))
        left_w=(page[3][0]+30,page[3][1]-10)
        p.arm((-29,65),left_w,-1,FAR,upper=99,lower=101)
        p.arm((29,65),wrist,1,INK,upper=100,lower=100)
    elif mode=='read':
        phase=(t%4.3)/4.3
        open_u=ease(phase/.32) if phase<.32 else 1-ease((phase-.74)/.26) if phase>.74 else 1
        a=(-22,113);b=(129,105);c=(142,168);d=(-15,173)
        blank_page(p,[a,b,c,d])
        # Turning leaf hinges around the central spine rather than translating rigidly.
        angle=math.pi*open_u
        page_width=70*math.cos(angle);lift=36*math.sin(angle)
        p.poly([(58,110),(58+page_width,109-lift),(66+page_width,168-lift*.65),(66,170)],'#DCD2BC')
        p.line([(58,110),(66,170)],WARM,2)
        p.arm((-28,65),(-13,150),-1,FAR,upper=66,lower=68)
        p.arm((28,65),(127+8*math.sin(t*1.5),137),1,INK,upper=66,lower=68)
    else:
        # Paper surface is stable. The pen/hand alternates between short writing
        # strokes and a visible trip to the inkpot, using shoulder/elbow IK.
        table_y=243 if head_y<1050 else 199
        blank_page(p,[(25,table_y-39),(177,table_y-44),(186,table_y-3),(33,table_y+3)])
        cycle=(t%3.6)/3.6
        # Accumulated blank-draft strokes: each segment is revealed only after
        # the actual nib has passed it. These are abstract ink traces, not Hanzi
        # or an attributed verse. Keep them while the hand returns to the pot;
        # the next writing cycle starts a new draft surface.
        ink_progress=min(1.0,cycle/.72)
        for start,end in ((.03,.14),(.20,.30),(.37,.48),(.54,.68),(.76,.89),(.94,1.0)):
            stop=min(end,ink_progress)
            if stop<=start:continue
            steps=max(2,math.ceil((stop-start)*95))
            points=[]
            for k in range(steps+1):
                q=lerp(start,stop,k/steps)
                points.append((48+108*q,table_y-20+5*math.sin(q*TAU*3)))
            p.line(points,INK,1.8)
        if cycle<.72:
            q=cycle/.72
            tip=(48+108*q,table_y-20+5*math.sin(q*TAU*3))
        else:
            q=(cycle-.72)/.28
            hop=math.sin(math.pi*q)
            tip=(lerp(156,217,ease(q*2)) if q<.5 else lerp(217,50,ease((q-.5)*2)), table_y-23-34*hop)
        wrist=(tip[0]-13,tip[1]-29)
        p.poly([(203,table_y-15),(226,table_y-17),(233,table_y-4),(226,table_y+2),(204,table_y+1)],INK)
        p.arm((-28,65),(41,table_y-17),-1,FAR,upper=90,lower=92)
        p.arm((28,65),wrist,1,INK,upper=100,lower=101)
        p.line([(wrist[0]-10,wrist[1]-20),(tip[0],tip[1])],INK,4)
        p.line([(tip[0]-2,tip[1]-3),tip],WARM,2)


def letter_actor(im,t,duration):
    p=Painter(im,(530,1300))
    hip=(0,-116);shoulder=(0,-245)
    for side in (-1,1):
        p.bone((side*13,-116),(side*18,-63),23,25,FAR if side<0 else INK)
        p.bone((side*18,-63),(side*17,-8),24,13,FAR if side<0 else INK)
        shoe(p,(side*17,-8),shade=FAR if side<0 else INK)
    torso(p,hip,shoulder)
    width=32+152*ease(t/2.0)
    center=(35,-164)
    lift=5*math.sin(t*2)
    left=(center[0]-width/2,center[1]+lift)
    right=(center[0]+width/2,center[1]-4)
    blank_page(p,[(left[0],left[1]-16),(35,-183),(right[0],right[1]-17),(right[0]+5,-117),(34,-112),(left[0]+6,-111)])
    p.line([(35,-183),(34,-112)],WARM,2)
    p.arm((-28,-240),(left[0]+2,left[1]+13),-1,FAR,upper=71,lower=72)
    p.arm((29,-239),(right[0],right[1]+13),1,INK,upper=72,lower=73)
    head(p,(0,-291),'middle',-.09*ease((t-duration+2)/1.3))


def farewell(im,t,duration):
    p=Painter(im,(320,1300))
    hip=(0,-116);shoulder=(0,-245)
    for side in (-1,1):
        p.bone((side*13,-116),(side*16,-63),24,25,FAR if side<0 else INK)
        p.bone((side*16,-63),(side*17,-8),24,13,FAR if side<0 else INK)
        shoe(p,(side*17,-8),shade=FAR if side<0 else INK)
    torso(p,hip,shoulder)
    p.arm((-28,-239),(-43,-120),-1,FAR,upper=66,lower=69)
    lift=ease(t/.8)
    wrist=(lerp(55,84+25*math.sin(t*TAU/.95),lift),lerp(-125,-315+10*math.cos(t*TAU/.95),lift))
    p.arm((29,-238),wrist,-1,INK,upper=74,lower=77)
    head(p,(0,-291),'middle')
    walker(im,t,duration,600,850,1300,.92,'middle',bundle=True,period=1.25)


def draw_actor(scene_id:str,t:float,duration:float)->Image.Image:
    t=float(t);duration=float(duration)
    if not math.isfinite(t) or not math.isfinite(duration) or duration<=0:raise ValueError('finite t and positive duration required')
    t=clamp(t,0,duration)
    im=Image.new('RGBA',(W,H),(0,0,0,0))
    if scene_id=='S01':seated(im,t,duration,470,1040,'write')
    elif scene_id=='S02':walker(im,t,duration,330,550,1300,1.0,'young',stop=2,period=1.30)
    elif scene_id=='S03':walker(im,t,duration,300,550,1300,.93,'middle',scroll=True,period=1.27)
    elif scene_id=='S04':walker(im,t,duration,760,540,1300,.93,'middle',bundle=True,period=1.34)
    elif scene_id=='S05':letter_actor(im,t,duration)
    elif scene_id=='S06':farewell(im,t,duration)
    elif scene_id=='S07':
        walker(im,t,duration,300,650,1450,.36,'middle',bundle=True,period=1.23)
        walker(im,t-.2,duration,218,568,1450,.31,'middle',period=1.28)
    elif scene_id=='S08':seated(im,t,duration,410,1070,'write')
    elif scene_id=='S09':seated(im,t,duration,470,1040,'protect')
    elif scene_id=='S10':walker(im,t,duration,330,480,1300,.92,'old',stop=2,period=1.65,cane=True)
    elif scene_id=='S11':seated(im,t,duration,boat_x(t,duration)-100,boat_y(t,duration)-146,'read','old',scale=.68)
    elif scene_id=='S12':pass
    else:raise ValueError('Unknown scene '+str(scene_id))
    return im


def previews():
    dest=ROOT/'质检'/'动作预览';dest.mkdir(parents=True,exist_ok=True)
    for scene,duration,label in [('S02',9,'walk'),('S09',14,'paper')]:
        layers=ROOT/'素材'/'图层'
        bg=Image.open(layers/f'{scene}_bg.png').convert('RGBA')
        mid=Image.open(layers/f'{scene}_mid.png').convert('RGBA')
        fg=Image.open(layers/f'{scene}_fg.png').convert('RGBA')
        base=Image.alpha_composite(bg,mid)
        target=dest/f'actor_{scene}_{label}.mp4'
        command=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','540x960','-r','24','-i','-',
                 '-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(target)]
        proc=subprocess.Popen(command,stdin=subprocess.PIPE)
        assert proc.stdin is not None
        for i in range(96):
            frame=Image.alpha_composite(base,draw_actor(scene,i/24,duration))
            frame=Image.alpha_composite(frame,fg).convert('RGB').resize((540,960),Image.Resampling.LANCZOS)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        if proc.wait():raise RuntimeError('Preview encoder failed')
        print(target,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--preview',action='store_true');args=parser.parse_args()
    if args.preview:previews()
