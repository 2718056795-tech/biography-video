#!/usr/bin/env python3
"""Render an illustrative theme/background comparison, not new biography episodes."""
from pathlib import Path
import sys,json
from PIL import Image,ImageDraw,ImageFont
from series_frame import SeriesFrame
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'assets/series'
LEGACY=ROOT/'assets/dufu-reference/工程'
sys.path.insert(0,str(LEGACY))
import render_dufu as old

def f(size,bold=False,sans=False):
 role=('sans_' if sans else 'serif_')+('bold' if bold else 'regular')
 return ImageFont.truetype(str(BASE/'fonts'/('series-'+role.replace('_','-')+'.otf')),size)
old.font=f

def palette(key):return json.loads((BASE/'themes'/f'{key}.json').read_text())
def demo_map(theme):
 c=theme['colors'];im=Image.new('RGBA',(880,430));d=ImageDraw.Draw(im)
 pts=[(125,300),(280,180),(470,280),(690,110)]
 d.line(pts,fill=c['map_accent'],width=2)
 for xy in pts:d.ellipse((xy[0]-4,xy[1]-4,xy[0]+4,xy[1]+4),fill=c['map_accent'])
 return im

def art_libai(c):
 im=Image.new('RGBA',(1080,1920),c['paper']);d=ImageDraw.Draw(im)
 d.ellipse((580,920,940,1280),fill=c['light'])
 d.rectangle((0,1260,1080,1920),fill=c['bluegreen'])
 # City tower and a boat: this demonstrator deliberately uses no mountain layer.
 d.polygon([(120,1010),(320,900),(510,1010)],fill=c['roof'])
 d.rectangle((170,1010,460,1260),fill=c['soft'])
 for x in [205,290,375]:d.rectangle((x,1040,x+34,1120),fill=c['warm'])
 d.polygon([(145,1150),(320,1080),(485,1150)],fill=c['roof'])
 for x in [205,290,375]:d.rectangle((x,1170,x+34,1258),fill=c['paper'])
 d.polygon([(520,1265),(655,1310),(935,1310),(995,1260),(800,1280)],fill=c['roof'])
 # Angular silhouette and robe, with a clear arm/hand gesture.
 d.polygon([(726,1110),(755,1084),(784,1104),(783,1140),(771,1150),(769,1168),(739,1167),(737,1146),(721,1133)],fill=c['roof'])
 d.polygon([(719,1110),(727,1082),(768,1073),(794,1095),(783,1106)],fill=c['roof'])
 d.polygon([(738,1160),(711,1185),(700,1230),(720,1245),(730,1220),(720,1290),(785,1294),(774,1217),(804,1219),(817,1200),(770,1172)],fill=c['roof'])
 d.line((781,1193,827,1162),fill=c['roof'],width=13)
 for y in [1340,1370,1400]:d.line((250,y,1000,y-6),fill=c['pale'],width=2)
 return im

def art_sushi(c):
 im=Image.new('RGBA',(1080,1920),c['paper']);d=ImageDraw.Draw(im)
 # Interior bookshelf, a writing table and bamboo shadow: no mountain layer.
 d.rectangle((0,1300,1080,1920),fill=c['soft'])
 d.rectangle((710,975,990,1300),fill=c['clay'])
 for y in [995,1090,1180,1280]:d.rectangle((720,y,980,y+10),fill=c['roof'])
 for row,y in enumerate([1015,1110,1200]):
  for j in range(7):
   x=735+j*33;d.polygon([(x,y+55),(x+23,y+55),(x+20,y),(x-2,y+3)],fill=[c['green'],c['warm'],c['pale']][(j+row)%3])
 d.line((110,1290,125,1000),fill=c['green'],width=6)
 for y in [1050,1120,1190]:
  d.polygon([(122,y),(75,y-25),(60,y-12),(115,y+7)],fill=c['green'])
  d.polygon([(122,y+12),(170,y-18),(182,y-9),(128,y+28)],fill=c['green'])
 d.polygon([(374,1040),(392,1020),(419,1025),(434,1050),(422,1076),(410,1084),(410,1102),(384,1102),(384,1082),(369,1064)],fill=c['ink'])
 d.polygon([(369,1040),(374,1017),(409,1005),(436,1027),(434,1040)],fill=c['ink'])
 d.polygon([(384,1094),(350,1124),(340,1180),(356,1210),(372,1180),(358,1250),(405,1285),(470,1288),(485,1260),(434,1220),(430,1140),(410,1100)],fill=c['ink'])
 d.polygon([(413,1128),(440,1141),(472,1200),(542,1221),(537,1238),(460,1228),(407,1170)],fill=c['ink'])
 d.polygon([(438,1235),(566,1227),(585,1272),(446,1277)],fill=c['light'])
 d.line((531,1222,550,1254),fill=c['ink'],width=4)
 d.rectangle((300,1280,650,1295),fill=c['roof']);d.polygon([(320,1295),(335,1295),(327,1340),(313,1340)],fill=c['roof']);d.polygon([(610,1295),(625,1295),(634,1340),(618,1340)],fill=c['roof'])
 return im

def main():
 out=BASE/'examples';out.mkdir(exist_ok=True)
 # Only Du Fu is an actual verified biography scene. Other two are art-layout samples.
 ref=old.Scene(8);themes=[palette(k) for k in ['dufu','libai','sushi']]
 subjects=[{'name':'杜甫','film_title':'此心在人间'},{'name':'李白','film_title':'山河为卷'},{'name':'苏轼','film_title':'日常自有天地'}]
 scenes=[dict(ref.data,index=9,kind='chapter',stage_profile='room_high'),
 {'id':'S09','index':9,'kind':'chapter','title':'远游与赠别','meta':'版式示例｜江舟与城楼','quote_lines':['孤帆远影碧空尽，','唯见长江天际流。'],'source_label':'《黄鹤楼送孟浩然之广陵》节选','explanation':'','event_summary':'事件说明在这里交代人物的具体经历。','assessment':'原创解读在这里说明这一阶段的意义。','stage_profile':'open_air'},
 {'id':'S09','index':9,'kind':'chapter','title':'书斋与日常','meta':'版式示例｜书案与竹影','quote_lines':[],'source_label':'','explanation':'场景随人物经历设计。','event_summary':'事件说明在这里交代人物的具体经历。','assessment':'原创解读在这里说明这一阶段的意义。','stage_profile':'open_air'}]
 arts=[ref.art(3.5),art_libai(themes[1]['colors']),art_sushi(themes[2]['colors'])]
 frames=[]
 for key,subject,theme,scene,art in zip(['dufu','libai','sushi'],subjects,themes,scenes,arts):
  renderer=SeriesFrame(theme=theme,person=subject,scene_count=12)
  frame=renderer.compose(scene,3.5,ref.duration,art,demo_map(theme))
  frame.save(out/f'{key}-series-layout-example.png')
  (out/f'{key}-series-layout-report.json').write_text(json.dumps(renderer.last_report,ensure_ascii=False,indent=2)+'\n')
  frames.append(frame)
 sheet=Image.new('RGB',(1500,1120),'#F5F3ED');d=ImageDraw.Draw(sheet)
 d.text((30,20),'相同版位 · 不同人物主题与背景',font=f(34,True,True),fill='#1E2A26',anchor='lt')
 labels=['杜甫｜草堂风雨','李白｜江舟与月夜','苏轼｜书案与竹影']
 for i,(frame,theme,label) in enumerate(zip(frames,themes,labels)):
  x=30+i*500;sheet.paste(frame.resize((432,768),Image.Resampling.LANCZOS),(x,90))
  d.text((x,880),label,font=f(27,True,True),fill='#1E2A26',anchor='lt')
  for j,role in enumerate(['paper','ink','muted','accent','assessment']):
   xx=x+j*82;d.rectangle((xx,930,xx+65,975),fill=theme['colors'][role])
   d.text((xx,985),role,font=f(14,False,True),fill='#1E2A26',anchor='lt')
 d.text((30,1050),'系列样式示意；李白/苏轼背景为美术候选，路线为版位占位，不是新人物史实成片。',font=f(22,False,True),fill='#1E2A26',anchor='lt')
 sheet.save(BASE/'series-comparison.png')
 print('Three theme/background examples use the same locked compositor; no new biography film claimed.')
if __name__=='__main__':main()
