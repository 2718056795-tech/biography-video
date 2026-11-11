#!/usr/bin/env python3
"""Original Du Fu geometric silhouette scene layers. No text, no source-image edits.
Rebuild SVGs and full-canvas PNG layers with the locally installed Inkscape CLI.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SCENES=ROOT/'素材'/'原生场景'
LAYERS=ROOT/'素材'/'图层'
W,H=1080,1920
C={'paper':'#DCD2BC','light':'#F3EBDC','ink':'#1E2A26','green':'#6D7C68',
   'pale':'#A7AF96','clay':'#A36B4E','warm':'#C5A86B','roof':'#455347',
   'soft':'#C8C6AD','bluegreen':'#85958A'}


def path(d,fill,opacity=1,stroke=None,sw=2):
    attrs=f' fill="{fill}" opacity="{opacity}"'
    if stroke:attrs+=f' stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"'
    return f'<path d="{d}"{attrs}/>'


def rect(x,y,w,h,fill,opacity=1):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" opacity="{opacity}"/>'


def group(content,x=0,y=0,s=1,flip=False):
    return f'<g transform="translate({x} {y}) scale({-s if flip else s} {s})">{content}</g>'


def dufu(x,y,s=1,age='middle',pose='stand',flip=False):
    # A simple cloth head-wrap and a closed modest robe. Age changes posture/head shape.
    old=age=='old';young=age=='young'
    head=path('M-20 -34 L-17 -51 L11 -52 L21 -35 L15 -27 L-18 -27 Z',C['ink'])
    head+=path('M-17 -31 C-29 -25 -27 -7 -20 1 L-16 12 L-16 21 L3 26 L9 14 C17 13 19 8 17 2 L21 -1 L16 -6 C18 -23 7 -33 -5 -34 Z',C['ink'])
    if old:
        head+=path('M8 13 C17 18 11 31 6 39 L-1 31 L0 17 Z',C['ink'])
        head+=path('M-20 -35 L10 -37 L15 -31 L-19 -29 Z',C['soft'],.75)
    if pose in ('sit','protect'):
        body=path('M-18 19 C-41 24 -60 43 -66 67 L-76 110 L-61 126 L-29 102 L-14 142 C-45 157 -75 180 -95 211 L-79 234 L58 237 L76 218 C45 200 34 188 24 169 L27 93 L68 107 L81 90 C69 72 47 52 25 38 L2 22 L-6 49 Z',C['ink'])
        if pose=='protect':
            body+=path('M-42 60 C-18 74 14 78 50 75 L96 55 L106 67 C75 95 37 107 -8 100 L-42 84 Z',C['ink'])
            body+=path('M80 57 L105 45 L121 46 L123 54 L106 65 L92 69 Z',C['ink'])
        body+=path('M-16 28 L-6 51 L10 30 M-6 51 L-13 110 M-16 145 L25 169 M-42 185 L17 190', 'none',.4,C['green'],2)
    elif pose=='depart':
        body=path('M-17 20 C-46 27 -61 46 -65 72 L-72 120 L-52 129 L-30 97 L-35 185 L-66 288 L-11 295 L6 222 L23 294 L65 286 L33 180 L31 100 L72 87 L64 67 L26 35 L4 22 L-5 47 Z',C['ink'])
        body+=path('M-14 29 L-5 48 L10 29 M-5 48 L-12 114 M-31 176 L31 178','none',.35,C['green'],2)
        body+=path('M-61 67 C-86 36 -105 42 -118 70 C-130 94 -109 113 -77 109 Z',C['roof'])
    else:
        body=path('M-18 20 C-42 26 -55 45 -59 69 C-67 93 -71 115 -62 132 C-51 140 -39 133 -32 118 L-31 184 C-33 220 -44 255 -47 289 C-17 299 22 300 57 291 C45 256 37 222 32 186 L29 109 C41 118 54 121 63 113 C70 99 66 84 55 70 C43 54 29 36 4 23 L-5 48 Z',C['ink'])
        body+=path('M-15 29 L-5 49 L10 30 M-5 49 L-12 114 M-30 177 C-8 184 12 181 31 177 M-25 199 L-36 282 M7 200 L24 284','none',.4,C['green'],2)
    person=head+body
    if old:person=f'<g transform="rotate(6 0 80)">{person}</g>'
    if young:
        # A compact young silhouette, no beard or bent posture.
        person=person.replace('M-20 -34 L-17 -51 L11 -52 L21 -35 L15 -27 L-18 -27 Z','M-19 -36 L-15 -47 L12 -48 L20 -34 L14 -28 L-18 -28 Z')
    return group(person,x,y,s,flip)


def villager(x,y,s=1,pose='stand',flip=False):
    head=path('M-17 -28 C-29 -15 -24 1 -13 8 L-10 23 L9 26 L14 11 C23 5 23 -5 20 -15 C13 -29 -4 -35 -17 -28 Z',C['ink'])
    robe=path('M-12 18 C-42 27 -58 55 -63 89 L-70 126 L-48 133 L-28 97 L-32 183 L-55 274 L60 279 L32 181 L29 95 L59 111 L74 95 L34 43 L8 21 L-2 43 Z',C['ink'])
    if pose=='reach':robe+=path('M23 54 L83 42 L103 29 L117 35 L106 51 L73 62 L38 79 Z',C['ink'])
    return group(head+robe,x,y,s,flip)


def paper(x,y,w=130,h=75,rotate=-6):
    return f'<g transform="translate({x} {y}) rotate({rotate})">'+path(f'M0 3 L{w-5} 0 L{w} {h-4} L7 {h} Z',C['light'])+path(f'M12 16 L{w-15} 12 M14 29 L{w-28} 26','none',.18,C['green'],2)+'</g>'


def cottage(x,y,s=1,broken=False):
    roof='M-330 93 L-212 52 L-40 -26 L5 -44 L49 -24 L218 52 L337 102 L310 115 L-306 110 Z'
    if broken:roof='M-330 92 L-204 45 L-72 -10 L-44 0 L-21 -29 L4 -43 L51 -20 L97 5 L111 34 L155 28 L212 60 L340 104 L315 118 L-305 111 Z'
    content=path('M-268 99 L267 107 L265 317 L-269 317 Z',C['clay'])
    content+=path(roof,C['roof'])
    content+=path('M-310 106 L-185 63 L-36 -3 L8 -26 L58 -5 L221 69 L317 107','none',.32,C['paper'],3)
    content+=rect(-216,145,110,101,C['ink'])+rect(65,143,118,111,C['warm'],.9)
    content+=path('M121 144 L121 254 M66 197 L183 197','none',.5,C['roof'],5)
    content+=rect(-27,161,59,155,C['ink'])
    content+=path('M-285 320 L284 324 L300 340 L-301 338 Z',C['roof'])
    return group(content,x,y,s)


def bamboo(x,y,s=1):
    d=path('M0 270 L-2 20 M60 280 L57 -11 M-39 284 L-43 82','none',.7,C['green'],6)
    d+=path('M0 59 C-47 27 -78 45 -86 66 C-42 48 -22 78 0 79 Z M58 34 C88 -3 112 -12 133 -2 C105 19 91 44 59 52 Z M-1 125 C34 82 54 78 78 84 C54 111 33 137 0 140 Z M-41 146 C-87 115 -109 128 -121 145 C-83 137 -65 165 -42 164 Z M60 160 C102 118 131 118 149 132 C110 153 88 177 60 177 Z',C['green'],.8)
    return group(d,x,y,s)


def houses(y=1100):
    return path(f'M75 {y+60} L167 {y+4} L246 {y+63} L231 {y+65} L231 {y+167} L95 {y+167} L95 {y+64} Z M720 {y+73} L810 {y+26} L896 {y+75} L880 {y+76} L880 {y+168} L738 {y+168} L738 {y+76} Z',C['green'])+rect(150,y+92,27,40,C['warm'])+rect(794,y+105,25,34,C['warm'])


def background(scene_id):
    fill={'S05':'#CFD0B9','S09':'#D1CDB7','S10':'#D4D0BB','S11':'#D2D1BC'}.get(scene_id,C['paper'])
    # Quiet stationary paper pattern, not animated noise or random particles.
    content=rect(0,0,W,H,fill)
    # The quiet ground continues to the bottom; only the action stays above y1370.
    ground={'S01':C['soft'],'S02':C['roof'],'S03':C['soft'],'S04':C['green'],
            'S05':C['green'],'S06':C['soft'],'S07':C['green'],'S08':C['soft'],
            'S09':C['soft'],'S10':C['bluegreen'],'S12':C['soft']}.get(scene_id)
    if ground:
        content+=path('M-40 1310 C188 1290 330 1330 531 1309 C758 1286 953 1321 1120 1299 L1120 1920 L-40 1920 Z',ground)
    content+=rect(0,0,W,H,'url(#papergrain)',.48)
    return content


def compose(scene_id):
    bg=background(scene_id);mid='';subject='';fg=''
    if scene_id in ('S01','S09'):
        mid+=path('M-40 800 L125 761 L275 797 L374 764 L470 815 L570 793 L676 845 L788 807 L1120 885 L1120 944 L-40 876 Z',C['roof'])
        mid+=path('M-40 874 L126 823 L280 854 L390 823 L491 867 L579 843 L684 893 L803 866 L1120 930','none',.2,C['paper'],5)
        mid+=rect(794,906,31,407,C['roof'])+rect(88,904,29,407,C['roof'])
        mid+=rect(650,985,133,193,C['warm'],.7)
        mid+=path('M713 990 L713 1174 M652 1073 L780 1074','none',.4,C['roof'],5)
        mid+=path('M-30 1310 C260 1297 497 1320 720 1301 C900 1285 999 1284 1110 1301 L1110 1361 L-30 1361 Z',C['soft'])
        subject+=dufu(469,1072,.94,pose='protect')
        subject+=paper(512,1166,142,77,-12)
        fg+=path('M210 1283 L738 1286 L758 1304 L210 1304 Z M242 1304 L261 1304 L255 1358 L237 1358 Z M694 1304 L714 1304 L721 1357 L705 1357 Z',C['ink'])
        rain='M180 928 L162 977 M297 941 L279 991 M920 1001 L899 1060 M974 1102 L952 1164 M865 1195 L844 1255'
        if scene_id=='S09':rain+=' M387 908 L365 968 M584 941 L565 997 M1040 954 L1017 1019'
        # Rain is animated by the final renderer; no frozen rain marks here.
    elif scene_id=='S02':
        bg+=path('M-40 1083 L81 984 L201 1007 L333 894 L453 937 L597 838 L654 856 L731 758 L825 825 L905 792 L1120 935 L1120 1370 L-40 1370 Z',C['pale'])
        mid+=path('M-40 1191 L98 1073 L183 1095 L260 988 L320 1028 L397 962 L505 1108 L628 1037 L715 919 L803 1003 L864 974 L1120 1150 L1120 1368 L-40 1368 Z',C['green'])
        mid+=path('M-40 1270 C118 1220 223 1178 356 1191 L494 1153 L611 1222 C752 1212 917 1174 1120 1256 L1120 1367 L-40 1367 Z',C['roof'])
        subject+=dufu(510,1008,1.01,age='young')
        fg+=path('M325 1319 L448 1284 L520 1298 L595 1285 L672 1328 L664 1353 L314 1354 Z',C['ink'])
    elif scene_id=='S03':
        mid+=path('M65 849 L191 849 L192 804 L858 807 L860 853 L988 853 L988 1299 L65 1299 Z',C['clay'])
        mid+=path('M135 839 L192 791 L853 795 L918 841 L890 858 L162 856 Z',C['roof'])
        mid+=path('M410 963 L671 966 L672 1300 L410 1300 Z',C['ink'])
        mid+=path('M430 981 L652 982 L652 1302 L430 1302 Z',C['paper'])
        mid+=rect(228,912,79,16,C['roof'],.6)+rect(759,915,76,16,C['roof'],.6)
        subject+=dufu(550,1065,.76)
        subject+=paper(578,1122,77,56,-16)
        fg+=path('M430 1301 L651 1301 L789 1357 L274 1357 Z',C['soft'])
    elif scene_id=='S04':
        mid+=path('M90 816 L450 816 L472 842 L454 1292 L80 1292 Z',C['roof'])
        mid+=path('M152 893 L395 898 L394 1277 L150 1277 Z',C['warm'])
        mid+=rect(263,898,22,380,C['clay'])
        mid+=path('M-40 1303 C274 1269 608 1315 1120 1272 L1120 1358 L-40 1358 Z',C['green'])
        subject+=dufu(674,1070,.77,pose='depart',flip=True)
        subject+=path('M526 1263 C548 1252 574 1257 588 1271 L576 1291 L540 1291 Z',C['ink'])
        fg+=path('M0 1342 C313 1332 679 1310 1080 1348','none',.5,C['clay'],4)
    elif scene_id=='S05':
        bg+=path('M-40 1115 L173 1085 L272 1004 L328 1015 L415 952 L490 1024 L568 993 L669 1079 L827 1050 L1120 1108 L1120 1357 L-40 1357 Z',C['pale'])
        mid+=path('M-40 818 L76 834 L135 803 L179 853 L171 1023 L260 1015 L291 1078 L285 1297 L-40 1297 Z M823 882 L891 866 L915 922 L1120 901 L1120 1302 L816 1302 Z',C['roof'])
        mid+=path('M281 1279 C402 1161 616 1169 831 1294 L831 1357 L281 1357 Z',C['green'])
        subject+=dufu(530,1059,.84)
        subject+=paper(549,1131,109,66,7)
        fg+=path('M122 1309 L136 1244 L150 1302 L181 1264 L170 1321 M782 1309 L804 1241 L810 1294 L842 1261 L829 1326','none',.85,C['ink'],7)
    elif scene_id=='S06':
        mid+=path('M75 827 L308 827 L308 1279 L75 1279 Z',C['clay'])
        mid+=rect(123,875,159,398,C['roof'])
        mid+=path('M-40 1308 C223 1290 452 1305 649 1282 C824 1264 962 1287 1120 1298 L1120 1361 L-40 1361 Z',C['soft'])
        subject+=villager(382,1071,.87,pose='reach')
        subject+=dufu(662,1065,.85,pose='depart',age='young')
        subject+=path('M480 1115 L531 1109 L549 1118 L539 1130 L498 1133 Z',C['ink'])
        fg+=path('M156 1281 L322 1279 L340 1300 L155 1303 Z',C['roof'])
    elif scene_id=='S07':
        bg+=path('M-40 1190 L48 1158 L78 1193 L122 1153 L157 1213 L112 1265 L195 1313 L-40 1370 Z M1120 1207 L1036 1177 L1011 1218 L969 1178 L917 1247 L991 1292 L899 1356 L1120 1370 Z',C['pale'],.65)
        mid+=path('M-40 1351 C190 1309 287 1364 440 1327 C639 1281 817 1365 1120 1324 L1120 1368 L-40 1368 Z',C['green'])
        subject+=dufu(423,1302,.20,pose='depart')
        subject+=villager(481,1313,.16)
        fg+=path('M333 1353 C432 1332 572 1347 691 1355','none',.7,C['roof'],4)
    elif scene_id=='S08':
        mid+=cottage(551,841,.93)
        mid+=bamboo(942,1010,.77)
        mid+=path('M-40 1302 C271 1290 595 1306 1120 1292 L1120 1360 L-40 1360 Z',C['soft'])
        subject+=dufu(407,1100,.80,pose='sit')
        subject+=paper(438,1195,106,68,-4)
        fg+=path('M360 1269 L674 1271 L689 1286 L361 1286 Z M383 1286 L400 1286 L396 1344 L379 1344 Z M642 1286 L661 1286 L667 1344 L650 1344 Z',C['roof'])
        fg+=path('M569 1239 C585 1229 609 1232 618 1243 L610 1254 L580 1254 Z',C['clay'])
    elif scene_id=='S10':
        bg+=path('M-40 1096 L75 1009 L152 1042 L282 927 L358 975 L456 893 L560 974 L673 932 L777 1012 L902 904 L1120 1050 L1120 1370 L-40 1370 Z',C['pale'])
        mid+=path('M-40 1172 L127 1082 L200 1112 L291 1018 L384 1153 L430 1257 L266 1365 L109 1920 L-40 1920 Z M1120 1041 L991 984 L940 1032 L874 1014 L802 1160 L731 1255 L812 1364 L951 1920 L1120 1920 Z',C['green'])
        mid+=path('M430 1113 C595 1101 743 1168 748 1232 C680 1267 630 1301 611 1364 C566 1525 663 1738 804 1920 L195 1920 C245 1651 379 1413 289 1364 C436 1317 526 1291 564 1258 C608 1211 515 1160 430 1113 Z',C['bluegreen'])
        subject+=dufu(430,1092,.75,age='old')
        fg+=path('M288 1320 L378 1287 L459 1300 L522 1281 L578 1332 L555 1358 L279 1358 Z',C['roof'])
        fg+=path('M736 1081 L751 1088 L742 1106 L729 1098 Z M844 1248 L861 1254 L852 1271 L839 1266 Z',C['clay'],.65)
    elif scene_id=='S11':
        bg+=houses(971)
        bg+=path('M-40 1163 C219 1136 407 1160 560 1153 C787 1142 948 1124 1120 1146 L1120 1920 L-40 1920 Z',C['bluegreen'],.42)
        mid+=path('M-40 1258 C293 1237 728 1240 1120 1257','none',.5,C['green'],4)
        boat=path('M-335 37 C-159 59 112 67 333 14 C283 75 160 107 -26 102 C-179 98 -278 78 -335 37 Z',C['ink'])
        boat+=path('M-77 40 C-53 1 13 -14 74 2 C111 13 133 34 142 51 Z',C['roof'])
        boat+=path('M-310 40 C-111 62 106 62 313 21','none',.55,C['warm'],3)
        subject+=group(boat,551,1195,1)
        subject+=dufu(392,1102,.54,age='old',pose='sit')
        subject+=paper(421,1160,88,48,-9)
        fg+=path('M235 1328 C422 1345 636 1349 831 1326 M322 1357 C485 1369 669 1366 739 1356','none',.45,C['green'],3)
    elif scene_id=='S12':
        bg+=houses(942)
        mid+=path('M-40 1253 C257 1234 525 1266 1120 1233 L1120 1365 L-40 1365 Z',C['soft'])
        subject+=path('M250 1099 C341 1119 435 1100 524 1096 C640 1085 731 1111 815 1090 L818 1283 C714 1302 638 1278 528 1285 C403 1295 329 1292 250 1280 Z',C['light'])
        subject+=path('M250 1099 C222 1105 220 1129 247 1143 L254 1281 C230 1296 209 1278 214 1255 L210 1129 C208 1098 227 1086 250 1099 Z M814 1091 C842 1080 862 1095 856 1117 L855 1264 C858 1289 838 1300 817 1283 L817 1123 C840 1126 843 1104 814 1091 Z',C['clay'])
        subject+=path('M273 1119 C396 1141 575 1101 790 1110 M276 1260 C441 1282 616 1247 791 1268','none',.35,C['warm'],3)
        fg+=path('M167 1320 C390 1308 692 1310 897 1322','none',.45,C['roof'],4)
    else:raise ValueError(scene_id)
    # Extend ground polygons, rather than leaving a horizontal illustration strip.
    for edge in (1357,1360,1361,1364,1365,1367,1368,1370):
        for left in (-40,-30):
            mid=mid.replace(f'L1120 {edge} L{left} {edge}',f'L1120 1920 L{left} 1920')
            bg=bg.replace(f'L1120 {edge} L{left} {edge}',f'L1120 1920 L{left} 1920')
    return {'bg':bg,'mid':mid,'subject':subject,'fg':fg}


def svg_doc(groups):
    defs='''<defs><pattern id="papergrain" width="113" height="79" patternUnits="userSpaceOnUse"><path d="M7 16 L59 15 M80 38 L106 39 M24 65 L76 64" fill="none" stroke="#6D7C68" stroke-width=".6" opacity=".12"/></pattern></defs>'''
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{defs}'+''.join(f'<g id="{name}">{content}</g>' for name,content in groups.items())+'</svg>'


def export(renderer,svg,png,env,layer=None):
    cmd=[renderer,str(svg),'--export-type=png','--export-area-page','--export-width=1080','--export-height=1920','--export-background-opacity=0','--export-filename='+str(png)]
    if layer:cmd += ['--export-id='+layer,'--export-id-only']
    result=subprocess.run(cmd,capture_output=True,text=True,env=env)
    if result.returncode:raise RuntimeError(result.stderr)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenes',nargs='+',default=['all'])
    parser.add_argument('--svg-only',action='store_true')
    args=parser.parse_args()
    renderer=shutil.which('inkscape')
    if not args.svg_only and not renderer:raise SystemExit('Inkscape is required on PATH')
    wanted=[f'S{i:02}' for i in range(1,13)] if args.scenes==['all'] else args.scenes
    SCENES.mkdir(parents=True,exist_ok=True);LAYERS.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ);env['XDG_CONFIG_HOME']='/tmp/dufu_inkscape_config';env['XDG_CACHE_HOME']='/tmp/dufu_inkscape_cache'
    for scene in wanted:
        layers=compose(scene)
        svg=SCENES/(scene+'.svg');svg.write_text(svg_doc(layers),encoding='utf-8')
        if not args.svg_only:export(renderer,svg,SCENES/(scene+'_full.png'),env)
        for layer,content in layers.items():
            (LAYERS/f'{scene}_{layer}.svg').write_text(svg_doc({layer:content}),encoding='utf-8')
            if not args.svg_only:export(renderer,svg,LAYERS/f'{scene}_{layer}.png',env,layer)
        print(scene,flush=True)
    index={'width':1080,'height':1920,'scene_ids':[f'S{i:02}' for i in range(1,13)],'layers':['bg','mid','subject','fg'],
           'upper_text_area':[96,210,880,700],'lower_text_area':[96,1370,880,1490],
           'recommended_text_color':C['ink'],'lower_text_color':{f'S{i:02}':(C['light'] if i in (2,4,5,7) else C['ink']) for i in range(1,13)},'paper_color':C['paper'],'palette':C,
           'note':'Original geometric scene artwork without text. Story, quotations, maps and timing are separate. Layer PNGs are full canvas, transparent except bg. S07 leaves map area quiet; secondary travellers below y1280.'}
    (SCENES/'场景索引.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
