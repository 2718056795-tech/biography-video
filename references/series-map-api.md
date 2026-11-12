# SeriesMap V2.2：累计地名与统一路线

`scripts/series_map.py`提供通用累积足迹层，默认使用随包、有来源的真实海岸与主要河流。每个人物提供自己的史实节点、访问顺序、分幕关系、地理视窗及主题；代码没有杜甫姓名、特定节点ID或固定中国视窗。底图仅为概化的现代地理参照，不代表唐代河道、古代疆界或已考证古道，也不替代史料、古今地名或坐标基准的核查。

包版本 V2.2 的 profile 为 `biography-paper-cut-series-2.2`，记录用户要求的持续地名与统一路线笔画；标题/页脚/地图面板坐标、字形、字号、封面几何与时序保持原值。V2.1 的真实底图、来源、像素与实际背景可读性检查继续保留。

## 调用

```python
from series_map import SeriesMap, save_map_png, load_map_png, ensure_map_evidence

life_map = SeriesMap(route_data, style, theme,
                     coastline_geojson=None, basemap_geojson=None)
tile = life_map.render(scene_id, t, duration)  # 幕内秒数、当前幕总秒数
canvas.alpha_composite(tile, life_map.position)
report = life_map.geometry_report()          # JSON可序列化字典
evidence = ensure_map_evidence(tile, scene_id=scene_id, t=t, duration=duration)
save_map_png(tile, "map.png")                # PNG嵌入证据 + map.png.evidence.json
restored = load_map_png("map.png")           # 校验并恢复证据
```

`route_data`、`style`、`theme`可传字典或本地JSON路径。`coastline_geojson`兼容本地海岸输入；`basemap_geojson`指定地理底图，未指定时加载离线打包数据，不联网下载。返回的是透明RGBA图层，尺寸固定880×430，位置固定`(96,150)`，不跟随人物场景的缩放平移。返回值的 `image.info["series_map_evidence"]` 绑定引擎、政策、来源、几何、RGBA像素与当前场景时间；`SeriesFrame.compose()` 必须收到有效的官方地图图层，不能传空图或任意PNG。

样式唯一来源为`assets/series/series_style.json`。面板、2倍超采样、`plot_box=[20,8,860,415]`、字号与时序保持锁定。V2.2 将历史、增长中、完成路线的主笔画统一为2.1原生px、alpha210及同一光晕，当前点以圆环强调；薄海岸/河流底图不变。此项明确的地图样式变化纳入2.2 profile。地理底图、视窗、标签与可读性政策另见 `assets/series/map_policy.json`。传入样式与其冲突会报错；少量字段未提供时继承权威文件。地图标题、侧栏说明、图例始终不画。

## 节点与访问序列

```json
{
  "nodes": [
    {"id": "home", "label": "故里", "lon": 10.2, "lat": 45.1,
     "precision": "现代城市级参考点；坐标与古今对应须由本人物资料核实",
     "source": "本项目的可追溯来源"},
    {"id": "study", "label": "求学地", "lon": 12.4, "lat": 47.0,
     "precision": "城市级约位"}
  ],
  "sequence": ["home", "study", "home"],
  "per_scene": {
    "intro": {"start_index": 0, "end_index": 0, "overview": true},
    "depart": {"start_index": 0, "end_index": 1},
    "return": {"start_index": 1, "end_index": 2},
    "stay": {"start_index": 2, "end_index": 2}
  }
}
```

示例数字仅用于解释接口，不代表某个真实人物的行程。`start_index`、`end_index`均指访问序列的索引，包含端点。回访复用`node_id`及坐标，保留独立的访问次序；不能为了曲线分离而移动同一城市。

兼容已有工程的节点字段`longitude`/`latitude`及分幕字段`scenes`，但建议新项目使用`lon`/`lat`、`per_scene`。每个人物需重新建立节点，不能只替换杜甫的名字或字幕。

也可仅提供规范化访问表，由模块推导分幕：

```json
{
  "nodes": [
    {"id": "a", "label": "起点", "lon": 10.2, "lat": 45.1, "precision": "城市约位"},
    {"id": "b", "label": "下一站", "lon": 12.4, "lat": 47.0, "precision": "城市约位"}
  ],
  "visits": [
    {"id": "v1", "node_id": "a", "scene_id": "opening"},
    {"id": "v2", "node_id": "b", "scene_id": "journey"},
    {"id": "v3", "node_id": "b", "scene_id": "residence"}
  ],
  "scene_order": ["opening", "journey", "residence", "closing"]
}
```

访问表必须按实际叙事顺序排列，同一幕的访问记录需连续；模块不从日期或诗名猜测顺序。连续相同节点的停留记录会合并到同一地理序列索引，原访问ID保留在报告中。`scene_order`可加入没有新访问的停留幕，默认为访问表中的首次出现顺序。显式`sequence`中的同坐标相邻段不画装饰性回环。缺失节点、非法索引和未知幕ID均报错。

## 累计地名与统一路线

地名按访问序列与实际抵达状态显示：起点及已经抵达的节点保留地名，进入后续章节仍继续显示；增长段未抵达的新目的地不提前标名。回访按同一 `node_id` 复用一个标签，不因访问次数复制地名。同地多幕不增加装饰性迁移，也不移除此前已经到访的地名。顺序和抵达进度由路线/场景时间决定，不依赖渲染函数之前调用过哪些帧。

标签在项目地图初始化时按所有已知路线一次规划，之后各幕/各帧复用相同位置。规划完整路线仅用于避让，不提前显示未来地名。布局搜索优先让标签避开其他标签、已知整条路线、节点、范围注记及边缘；先尝试全路线零相交，密集条件下允许带惩罚的路线相交候选并记录交点数。文字最后绘在路线之上，以纸色描边保护字形；不能把算法尝试避让称为所有地名必然零相交。密集节点可把文字放在附近空处，用短引线连回真实坐标；移动的是标注位置，人物地点和路线端点不移动。不能用更小字号、手改节点坐标或每帧挪字解决拥挤。所有候选均无法容纳时明确报错，建议缩短但仍无歧义的地点标签、扩大视窗或拆成区域视图；不静默删除标签。

历史、增长中与完成段主笔画均使用2.1原生px、alpha210，光晕统一宽4.5px、alpha64，不以不同粗细暗示先后；行程仍按时间增长，当前点圆环承担焦点提示。地理底图的海岸/河流保持较细线条，不能把路线统一规则误用于底图。细节与本次实际检查见 [V2.2 说明](map-labels-v2.2.md)。

## 序章与范围注记

`overview=true` 用于序章全路线预览，路线仍采用统一笔画，不高亮已抵达城市，也不显示地点标签；正常章节才按实际抵达状态累计标名。

范围注记由数据声明，不能硬编码某个人物的晚年地名：

```json
{
  "start_index": 4,
  "end_index": 6,
  "region_node_ids": ["region_reference_a", "region_reference_b"],
  "region_label": "晚年活动区域"
}
```

移动幕抵达`end_index`后显示范围注记，仍保留终点亮点；此前按实际抵达进度显示地名。停留幕的范围注记适合不应暗示精确死亡点的结尾；`region_only=true` 控制当前范围提示，不应清除累计已到访地名。范围圈是注记，不能当作行政边界或精确历史活动范围。

注记靠近面板边缘时，圈半径会受边距约束、标签可改到左侧，并保持真实节点不动。长到无法在固定字号下一行放入面板的范围标签会报错。报告另列圈与文字边界，供验收检查。

## 投影、视窗与真实地理

默认从本人物全部节点范围建立有边距的视窗，最小经度跨度8°、纬度跨度5°，默认边距18%，标准纬线和中央经线取视窗中点。这保留人物周围的可读地理参照；不为拉入海岸而专门扩图。自动视窗在缺少实际可读地理要素时最多扩大两次，每次1.5倍；仍不足则报错。用户显式给出的视窗不静默改写，狭窄且无可用要素时应补充有来源的详细线数据，或重新选择合理的范围。

可显式指定：

```json
{
  "projection": {
    "bounds": [103, 123, 27, 38.5],
    "standard_parallel": 32.75,
    "central_meridian": 113
  }
}
```

边界顺序固定为`[west,east,south,north]`；兼容原工程`bounds_west_east_south_north`。上述为杜甫参考视窗，不是所有人物的默认范围。海外人物使用相应区域；本实现支持南北纬85°以内、不跨反经线的区域视窗。跨180°的全球航线应划分区域镜头后显式提供视窗。

节点、海岸、河流和路线始终使用同一个局部等距圆柱近似投影、视窗裁切与单一缩放系数。真实线段裁到面板范围，不连接不相邻的边段。地图自然宽度不足面板时保留透明留白，不横纵分别拉伸；投影是局部制图近似，不宣称无地理畸变。

默认数据位于 `assets/series/geography/natural_earth_basemap.geojson.gz`，来源为 Natural Earth v5.1.2 的1:5000万海岸与1:1000万河流/湖中线，包含间歇河流并排除运河。坐标使用WGS84；真实海岸和河流可有当地简化或缺漏，狭窄城市视窗尤其可能需更详细数据。完整上游地址、固定提交、来源哈希、转换方法、派生文件哈希与公有领域条款见 [provenance.json](../assets/series/geography/provenance.json) 和 [LICENSE.md](../assets/series/geography/LICENSE.md)。本包不绘行政边界、随机山纹、假河流或伪造海岸；内陆只要有可读河流等实际地理参照即可，不要求存在海岸。

自备底图可向 Python 的 `basemap_geojson` 传入字典或本地JSON/GeoJSON文件路径；视频/单帧项目通过 `project.json` 的 `basemap_geojson`（或路线 `basemap.file`）指定相对项目目录的路径。输入使用 GeoJSON FeatureCollection：每条 Feature 的 `properties.layer` 为 `coast` 或 `river`（兼容 `kind`），`geometry.type` 为 `LineString` / `MultiLineString`，坐标为WGS84 `[longitude,latitude]`。Collection 的 `provenance.source_url` 必须是实际可追踪的HTTP(S)来源地址，`provenance.license` 为非空许可说明；记录实际阅读与地理含义，不将未知来源写成公有领域。文件输入自动记录文件SHA256，提供的 `sha256` 指纹必须匹配地理集合；可选 `provenance.local_files` 中每项的 `path` / `sha256` 必须匹配本地文件。默认数据的许可不自动适用于自备数据。

自备底图替换默认底图；额外的 `coastline_geojson` 海岸可叠加，但也必须有可追踪来源。可见真实海岸/河流总长至少24个原生地图像素，点线行程本身不能满足地理参照要求。不能为满足阈值人工添加不存在的河流或连接线。

原 `coastline_geojson` / 路线 `coastline.file` 继续用于有来源的海岸线，不应输入国家多边形。Polygon/MultiPolygon 不能作为可靠海岸证明，国家轮廓不能冒充海岸；本版默认数据与自备地理底图采用真实的 LineString/MultiLineString。兼容的 `coastline.filter_bounds` / `projection.coast_filter_bounds` 仅裁取已有线段，不证明线段含义。各地理输入应与人物节点一致使用WGS84经纬度，不能混入GCJ-02、BD-09或以米为单位的投影坐标。

## 主题与字体

主读`theme["colors"]`，亦兼容`roles`、`palette`或直接角色字典。需要`map_ink`、`map_accent`、`map_halo`、`map_coast`、`paper`。标签描边强制使用本主题 `paper`；即使旧主题声明其他 `map_label_halo` / `label_halo`，本版有效色仍取纸色。`readability.label_halo` 记录请求色、有效色、`paper_matched:true`、alpha245和2px描边；标签统一使用28px粗体、alpha245。角色颜色是RGB或十六进制RGB，透明度由系列样式控制。背景、焦点色随人物改变；没有固定杜甫RGB常量。继续按主题纸底合成后的对比度，必要时将地图颜色向本主题 `ink`、再向黑/白适配，保证底图、旧线、新线与标签可读；保留请求色与有效色及测量结果。地图的适配不改其他UI主题色、字体或布局。合成器另用 `validate_map_background(map_image, background_image)` 检查经过舞台变换并合成到不透明纸底上的实际880×430艺术区域：按原生笔画核心像素计算底图、路线和所有已显示地名的对比度，排除抗锯齿边缘。可读性测量中保留的 `current_label` 名称在本版覆盖所有当前可见地名，并非只查当前位置。该函数返回 `passed/status` 与背景/地图哈希，失败时合成器拒绝继续；仍需查看手机大小的最终画面，不以自动计算替代视觉检查。

地图常规/粗体字形只从权威样式指定的打包文件读取：`assets/series/fonts/series-sans-regular.otf`与`series-sans-bold.otf`。缺文件直接报错，不静默退回系统字体。若需对比旧版Noto TTC索引2，测试进程可以显式注入旧字库；交付运行必须使用打包字体。同名字体但不同字形索引或版本不能宣称逐像素一致。

## 报告、证据与验收

`geometry_report()`包含固定面板与样式、投影边界与尺度、每个节点的局部/全帧像素、精度说明及来源状态、访问序列与分幕索引、范围注记的圈/文字边界、91点曲线采样规则、同地点段抑制记录、视窗外节点、地理来源与可见海岸/河流要素、字体及主题颜色，保留 `basemap` 与 `readability`，并记录项目级标签位置、标签布局指纹、当前可见标签及路线统一样式。自备来源和随包来源都须可追踪，不能只写“地图来自网络”。

`geometry_report()` 的 V2.2 字段包括：

| 字段 | 内容 |
| --- | --- |
| `label_layouts` | 按节点ID记录文字、`position/bounds`、28px粗体/2px描边、首次访问索引、真实 `node_pixel`、短引线与 `route_intersections`。 |
| `label_layout_sha256` | 整个项目标签布局的稳定指纹；不同场景/时刻复用。 |
| `label_layout_audit` | 全路线候选搜索、候选数量、范围注记保留框、考虑的路线边数与相交总数。 |
| `route_stroke_policy` | `width:2.1, alpha:210, halo_width:4.5, halo_alpha:64, all_segments_same:true, aging:false, preview_uses_same_stroke:true`。 |

`frame_state(scene_id,t,duration)` 返回纯时间状态，包括 `visible_label_ids`、`current_index`、`overview_preview`、`region_active/region_only` 与 `route_segment_states`。可见标签按首次抵达顺序去重；增长段沿用原进度阈值 `progress>=0.99` 记为抵达。每次渲染证据的 `schema_version` 为 `2.2`，含相同 `visible_label_ids`、`frame_state`、`label_layout_sha256` 与 `route_stroke_policy`，必须和官方同时间状态一致。

每次 `render()` 的证据含源文件、引擎/政策/几何/像素哈希、实际场景ID与时间及官方重绘所需配置。`ensure_map_evidence()` 校验图层，`validate_map_evidence()` 校验记录；PNG保存/载入应使用 `save_map_png()` / `load_map_png()`，保留嵌入证据与 `<PNG>.evidence.json` 侧车文件；二者同时存在时必须相符。单帧命令显式使用外部 `--map` 时要求侧车文件存在。缺地图、无来源、无可读地理要素、伪造或过期证据、全透明图以及像素与证据不符均须失败，不能仅以尺寸880×430判合格。失败后应按错误补齐数据、恢复正确输入或重新绘制官方地图，不手写通过记录。

使用实际地图PNG与合成RGB图运行 `check_series_style.py --frame <PNG> --map <PNG> --require-pixels`；完整参数见 [帧接口](series-renderer-api.md)。只核对记录的检查会明确 `actual_frame_pixels_verified:false` 和 `actual_map_pixels_verified:false`，不认证当前PNG。地图结构和像素检查仍不证明史料、古代地貌、真人听审或手机设备观感；须实际查看路线、当前点、标签和地理底图的手机大小可读性。视窗排除人物节点时构造会报错，须扩大视窗；`nodes_outside_view` 保留为报告核对字段。

旧杜甫配置仍显式设置其节点、顺序、序章 `overview` 及晚年范围注记。**HISTORICAL V2.0 evidence（历史 V2.0 证据）** 中的108时点和15画面逐像素相等报告仅属于旧版；V2.1 地理底图与对比度处理会改变地图像素。V2.1 的 [map-upgrade-check.json](map-upgrade-check.json) 保留为历史地理升级证据；当前 V2.2 实际检查见 [map-labels-check.json](map-labels-check.json)，不能把6秒短样片称为重渲完整120秒。

## 最小结构自测

在技能包根目录运行以下代码；数据是接口用的虚拟访问记录，不作为任何人物史料。测试不联网、不写图片、不使用系统字体。

```python
import json
import sys
from copy import deepcopy
from pathlib import Path
sys.path.insert(0, "scripts")
from series_map import SeriesMap

style = json.loads(Path("assets/series/series_style.json").read_text())
theme = json.loads(Path("assets/series/themes/sushi.json").read_text())
data = {
    "nodes": [
        {"id": "a", "label": "起点", "lon": -5, "lat": 48, "precision": "测试点"},
        {"id": "b", "label": "下一站", "lon": 2, "lat": 51, "precision": "测试点"}],
    "visits": [
        {"id": "v1", "node_id": "a", "scene_id": "begin"},
        {"id": "v2", "node_id": "b", "scene_id": "travel"},
        {"id": "v3", "node_id": "b", "scene_id": "stay"}]
}
m = SeriesMap(data, style, theme)
assert m.size == (880, 430) and m.position == (96, 150)
assert m.sequence == ["a", "b"]
assert m.per_scene["stay"] == {"start_index": 1, "end_index": 1}
assert m.frame_state("travel", 0, 8)["visible_label_ids"] == ["a"]
assert m.frame_state("travel", 7.5, 8)["visible_label_ids"] == ["a", "b"]
assert m.frame_state("stay", 0, 8)["visible_label_ids"] == ["a", "b"]
assert m.render("stay", 2, 8).tobytes() == m.render("stay", 6, 8).tobytes()
assert m.render("travel", 2, 8).mode == "RGBA"
assert m.render("travel", 2, 8).info["series_map_evidence"]
assert m.geometry_report()["basemap"]
assert m.geometry_report()["label_layout_sha256"] == m.render("stay", 2, 8).info["series_map_evidence"]["label_layout_sha256"]
assert m.geometry_report()["route_stroke_policy"]["all_segments_same"] is True
different = deepcopy(theme)
different["colors"]["map_accent"] = "#2378A5"
other = SeriesMap(data, style, different)
assert m.points == other.points
assert m.render("travel", 2, 8).tobytes() != other.render("travel", 2, 8).tobytes()
print("series map structural check passed")
```
