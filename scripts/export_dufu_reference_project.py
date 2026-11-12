#!/usr/bin/env python3
"""Export a normalized Du Fu example from the supplied, researched V4 reference.

The result is a reproducible example, not an empty project for a different
person. It retains the reference's evidence boundaries and does no new research.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def relative(path,base):
    return Path(os.path.relpath(path,base)).as_posix()


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'assets/series/examples/dufu-project')
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args();out=args.output.expanduser().resolve()
    if out.exists() and any(out.iterdir()) and not args.overwrite:parser.error('Output is nonempty; use a fresh directory or explicit --overwrite')
    ref=ROOT/'assets/dufu-reference';style_path=ROOT/'assets/series/series_style.json'
    style=json.loads(style_path.read_text(encoding='utf-8'))
    screen=json.loads((ref/'数据/上屏文案.json').read_text(encoding='utf-8'))
    old_route=json.loads((ref/'数据/一生足迹.json').read_text(encoding='utf-8'))
    slots=style['video']['cut_frames'];scenes=[]
    for i,row in enumerate(screen['scenes']):
        scene=dict(row);meta=scene['meta'];parts=meta.split('｜',1)
        scene.update(index=i+1,kind='opening' if i==0 else 'ending' if i==11 else 'chapter',
                     stage_profile=style['dufu_stage_profiles'][i],start_frame=slots[i],end_frame=slots[i+1],
                     location_intro_sec=0 if i==0 else style['standard']['meta']['start'],
                     period=parts[0],place=parts[-1],event=scene.get('explanation') or scene.get('event_summary'),
                     source_ids=scene['claim_ids'],local_action='沿用本包杜甫参考的关节/物件实际动作，见工程与动作记录',
                     environment_action='沿用对应杜甫场景的实际风雨、舟桨或卷轴机制',
                     action_sample_frames=[slots[i]+30,slots[i]+90])
        scene.pop('end_frame_exclusive',None);scenes.append(scene)
    nodes=[]
    for row in old_route['nodes']:
        node=dict(row);node.update(lon=node['longitude'],lat=node['latitude'],precision='region_approx' if '区域' in node['label'] else 'city_approx')
        nodes.append(node)
    visits=[]
    for index,node_id in enumerate(old_route['sequence']):
        target=next((s for s in scenes[1:] if old_route['scenes'][s['id']]['end_index']>=index),scenes[-1])
        provenance=scenes[0] if index==0 else target
        visits.append({'id':f'v{index:02d}','node_id':node_id,'scene_id':target['id'],
                       'period':provenance['period'],'source_ids':provenance['source_ids']})
    per_scene={key:dict(value) for key,value in old_route['scenes'].items()}
    for scene in scenes:
        per_scene[scene['id']].pop('overview',None)
        per_scene[scene['id']]['location_intro_sec']=scene['location_intro_sec']
    per_scene[scenes[0]['id']].update(start_index=0,end_index=0,no_new_movement=True,route_caption='序章底图')
    for sid in (scenes[-2]['id'],scenes[-1]['id']):
        per_scene[sid].update(region_node_ids=['yueyang','tanzhou'],region_label='湖湘（范围）')
    per_scene[scenes[-1]['id']]['region_only']=True
    for scene in scenes:scene['visible_visit_ids']=[] if scene['kind']=='opening' else [v['id'] for v in visits[:per_scene[scene['id']]['end_index']+1]]
    route={'schema_version':style['schema_version']+'-example','nodes':nodes,'sequence':old_route['sequence'],'visits':visits,
           'segments':[{'from_visit':a['id'],'to_visit':b['id'],'schematic':True,'source_ids':b['source_ids']} for a,b in zip(visits,visits[1:]) if a['node_id']!=b['node_id']],
           'per_scene':per_scene,'scene_order':[s['id'] for s in scenes],'projection':old_route['projection'],
           'basemap_policy':'bundled_default',
           'legacy_coastline_reference':{'file':relative(ref/'素材/一生足迹/CHN.geo.json',out),'filter_bounds':[117.3,123,27,38.5],
                        'reference_only':True,'source_kind':'旧版经筛选的东部海岸局部，仅存档来源；2.1渲染采用包内海岸与河流，不表示古代疆域','source_url':old_route['base_geometry']['url']},
           'evidence_note':'杜甫既有核查记录的格式转换；未新增网络或纸本核查，约位和读源边界保留在nodes及参考史料中。'}
    settings=['草堂破檐下的书案','青年远行时的山体远景','长安城门前','赴奉先途中朱门与寒路','战乱长安的残墙','征役离别的村门','携家入蜀途中','成都草堂书案与竹雨','草堂秋风破檐下','夔州客居远眺','晚年湖湘江舟','卷轴与普通人居处的主题收束']
    buildings=['低矮草堂、破茅檐、木窗与桌','无建筑，层叠山体与远景','概括城门和平面屋顶，不指定真实官署','朱门、矮墙与路边灯','断壁、草丛与残城轮廓','村门与门帘','无建筑，山路与低矮岩体','草堂、台阶与竹丛','受风破损的草堂屋檐、木柱与木窗','无明确建筑，江峡与山崖','江舟及岸边民居轮廓','概括民舍与展开卷轴']
    props=['书案、纸页、笔与砚','布帽、长袍和行走支撑腿','手持书卷与风旗','行囊和灯笼','纸信，不写虚构具体信文','行囊、挥别手势与门帘','携家人物与包裹','书案纸笔、砚和竹叶','手按住的纸、掀起纸角与破茅草','手杖与秋叶','船桨、船夫、书页与水纹','卷轴、木轴、纸纤维与原创题字']
    backgrounds=[]
    for scene,setting,building,prop in zip(scenes,settings,buildings,props):
        backgrounds.append({'scene_id':scene['id'],'setting':setting,'buildings':building,
                            'props':prop,'light':'本幕既有低饱和纸色与平面明暗',
                            'source_basis':'杜甫已核查阶段与文学语境的风格化演绎，不是具体现场复原','source_ids':scene['source_ids']})
    audio=ROOT/'assets/fixed-bgm.m4a'
    project={'schema_version':style['schema_version'],'series_profile_id':style['profile_id'],'series_profile_sha256':hashlib.sha256(style_path.read_bytes()).hexdigest(),
             'name':'杜甫','person':{'name':'杜甫','film_title':'此心在人间','birth_death':'712—770','opening_meta':'一生风雨，心系人间'},
             'orientation':'portrait','width':1080,'height':1920,'duration_sec':120,'fps':30,'total_frames':3600,'cut_frames':slots,
             'theme':relative(ROOT/'assets/series/themes/dufu.json',out),'art_provider':'art/scene_provider.py',
             'art_dependencies':[relative(ref/name,out) for name in ('工程','数据','素材')],
             'storyboard':'data/storyboard.json','route':'data/life_route.json',
             'audio':{'path':relative(audio,out),'sha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'policy':'preserve_exact_audio_payload'},
             'map':{'show_title':False,'layout':'locked_series_panel','required':True,'basemap_policy':'bundled_default','readability_checks':'required'},
             'cover':{'required':True,'width':1200,'height':1500,'orientation':'portrait','format':'PNG','user_ratio_name':'5:4竖屏','long_short_ratio':'5:4','width_height_ratio':'4:5','path':'output/cover_1200x1500.png'},
             'art_direction':{'rationale':'此例复现杜甫已有民生关怀、草堂风雨与晚年漂泊的题材。其他人物必须新建方案，不能改名照搬。',
                              'motifs':['草堂与风雨','纸页与家书','晚年舟行'],'backgrounds':backgrounds},
             'example_scope':'Reference normalization, not newly researched historical work; this provider is Du Fu-only.'}
    write(out/'project.json',project);write(out/'data/storyboard.json',{'schema_version':style['schema_version'],'series_profile_id':style['profile_id'],'scenes':scenes});write(out/'data/life_route.json',route)
    provider=Path(__file__).with_name('dufu_art_provider_example.py')
    (out/'art').mkdir(parents=True,exist_ok=True);shutil.copy2(provider,out/'art/scene_provider.py')
    write(out/'art/reference_root.json',{'skill_root_relative':relative(ROOT,out/'art')})
    ledger=out/'references/source_ledger.csv';ledger.parent.mkdir(exist_ok=True)
    ids=sorted({sid for scene in scenes for sid in scene['source_ids']})
    with ledger.open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=['id','status','citation','url_or_path','claim','verification_note']);writer.writeheader()
        for sid in ids:
            document=ref/'史料'/('生平核查.md' if sid.startswith('B') else '诗句核查.md')
            writer.writerow({'id':sid,'status':'verified','citation':'本包已核查杜甫记录 '+sid,'url_or_path':relative(document,out),
                             'claim':'仅支持原核查记录中'+sid+'对应阶段或原文及其使用边界',
                             'verification_note':'沿用已有实际核查；本次仅格式转换，没有新网络查证。请读取所指MD中原来源、约年、争议与实际读取状态。'})
    (out/'README.md').write_text('# 杜甫规范化可运行示例\n\n此目录使用统一合成器与真实关节/环境代码复现杜甫。它不是给另一人物改名字就能用的美术内容。新人物从`init_series_project.py`建立自己的资料、调色与场景provider。\n\n在Skill根目录可运行2秒样例：\n\n```bash\npython scripts/render_series_video.py --project assets/series/examples/dufu-project/project.json --preview-scene S02 --preview-start 2.5 --preview-seconds 2 --output /path/to/dufu-sample.mp4 --report /path/to/dufu-sample.json\n```\n\n完整输出使用同一project，省略preview参数；完成后另跑视频、封面与双文件交付验收。详见`references/series-video-api.md`（Skill根目录）。\n\n路径相对本项目或由provider向上定位Skill，包内无需联网、系统字库或账户密钥。证据为原杜甫记录的继承，来源边界与约位精度没有因转换而升级。\n',encoding='utf-8')
    print(json.dumps({'project':str(out/'project.json'),'scenes':12,'visits':len(visits),'source_ledger_rows':len(ids)},ensure_ascii=False))


if __name__=='__main__':main()
