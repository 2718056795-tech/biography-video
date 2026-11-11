# SeriesMap：固定版式、独立人物足迹

`scripts/series_map.py`提供通用累积足迹层。每个人物提供自己的史实节点、访问顺序、分幕关系、地理视窗及主题；代码没有杜甫姓名、特定节点ID或固定中国视窗。它不替代史料、古今地名、坐标基准或海岸数据的核查。

## 调用

```python
from series_map import SeriesMap

life_map = SeriesMap(route_data, style, theme, coastline_geojson=None)
tile = life_map.render(scene_id, t, duration)  # 幕内秒数、当前幕总秒数
canvas.alpha_composite(tile, life_map.position)
report = life_map.geometry_report()          # JSON可序列化字典
```

`route_data`、`style`、`theme`可传字典或本地JSON路径。`coastline_geojson`可传字典、本地GeoJSON路径或`None`；本模块不下载数据。返回的是透明RGBA图层，尺寸固定880×430，位置固定`(96,150)`，不跟随人物场景的缩放平移。

样式唯一来源为`assets/series/series_style.json`。面板、2倍超采样、`plot_box=[20,8,860,415]`、线宽、透明度规则、字号与时序保持锁定。传入样式与其冲突会报错；少量字段未提供时继承权威文件。地图标题、侧栏说明、图例始终不画。

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

## 序章与范围注记

`overview=true`：显示低亮度总览线与淡节点，不高亮当前地点。适合诗意预告，避免把故里标记叠到另一个时期的场景上。

范围注记由数据声明，不能硬编码某个人物的晚年地名：

```json
{
  "start_index": 4,
  "end_index": 6,
  "region_node_ids": ["region_reference_a", "region_reference_b"],
  "region_label": "晚年活动区域"
}
```

移动幕抵达`end_index`后显示范围注记，仍保留终点亮点；此前按当前城市显示标签。停留幕`start_index==end_index`默认只显示范围注记，适合不应暗示精确死亡点的结尾。可显式用`region_only=true`强制只显示范围。范围圈是注记，不能当作行政边界或精确历史活动范围。

注记靠近面板边缘时，圈半径会受边距约束、标签可改到左侧，并保持真实节点不动。长到无法在固定字号下一行放入面板的范围标签会报错。报告另列圈与文字边界，供验收检查。

## 投影与真实线稿

默认从本人物的节点范围生成留有边距的视窗，标准纬线和中央经线取视窗中点。可显式指定：

```json
{
  "projection": {
    "bounds": [103, 123, 27, 38.5],
    "standard_parallel": 32.75,
    "central_meridian": 113
  },
  "coastline": {
    "filter_bounds": [117.3, 123, 27, 38.5],
    "source_url": "本项目实际读取的本地线稿来源",
    "source_kind": "已核实为海岸的国家多边形局部"
  }
}
```

边界顺序固定为`[west,east,south,north]`；兼容原工程`bounds_west_east_south_north`及`projection.coast_filter_bounds`。上述视窗用于杜甫参考配置，不是所有人物的默认值。海外人物可设置自己的区域；本实现支持南北纬85°以内、不跨反经线的区域视窗。自动视窗不支持跨180°的全球航线，此类任务应划分区域镜头后显式提供视窗。

节点、海岸、曲线始终使用同一个局部等距圆柱近似投影和单一缩放系数。地图自然宽度不足面板时保留透明留白，不横纵分别拉伸。投影是局部制图近似，不宣称无地理畸变。

支持Feature/FeatureCollection中的LineString、MultiLineString、Polygon、MultiPolygon，输入应是与节点一致的WGS84经纬度数据，不混用GCJ-02、BD-09或以米为单位的投影坐标。国家Polygon没有显式海岸筛选框时会跳过，不能自动描出国界冒充海岸。**筛选框本身不能证明框内所有线都是海岸**，制作者仍须核对所选连续边段的真实含义并记录来源。为保持参考图一致，使用按顶点筛选的连续段，不凭空连接框边，也不生成河流、山体或随机轮廓。当前本地中国数据不适合某人物的地理范围时，可以传`None`，报告会明确无海岸线，而不借用不相关轮廓。

## 主题与字体

主读`theme["colors"]`，亦兼容`roles`、`palette`或直接角色字典。需要`map_ink`、`map_accent`、`map_halo`、`map_coast`、`paper`。标签描边颜色读`map_label_halo`，兼容`label_halo`，缺省继承本主题`paper`。角色颜色是RGB或十六进制RGB，透明度由系列样式控制。背景、焦点色随人物改变；没有固定杜甫RGB常量。

地图常规/粗体字形只从权威样式指定的打包文件读取：`assets/series/fonts/series-sans-regular.otf`与`series-sans-bold.otf`。缺文件直接报错，不静默退回系统字体。若需对比旧版Noto TTC索引2，测试进程可以显式注入旧字库；交付运行必须使用打包字体。同名字体但不同字形索引或版本不能宣称逐像素一致。

## 报告与验收

`geometry_report()`包含固定面板与样式、投影边界与尺度、每个节点的局部/全帧像素、精度说明及来源读取状态、访问序列与分幕索引、范围注记的圈/文字边界、91点曲线采样规则、同地点段抑制记录、视窗外节点、海岸可见段数和来源配置、字体路径、实际主题颜色。

该报告验证结构与绘图参数，不证明坐标有一手测绘认证、史实已全部核查或曲线代表真实古道。`nodes_outside_view`非空时，制作者须调整视窗或明确局部展示意图；不能只用文件生成成功判定地图合格。

同一杜甫参考配置需显式设置：原投影视窗与标准纬线、原东海岸筛选框、原节点和顺序、序章`overview`、晚年两幕的范围节点与“湖湘（范围）”标签，以及对应杜甫主题。使用同字库时，原旧线透明度、新段生长、光晕、当前点、28px标签、标签描边和Lanczos缩小均保留，便于做原始RGBA逐像素对照。通用人物不继承这份人物数据。

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
assert m.render("stay", 2, 8).tobytes() == m.render("stay", 6, 8).tobytes()
assert m.render("travel", 2, 8).mode == "RGBA"
assert m.geometry_report()["coastline"]["visible_runs"] == 0
different = deepcopy(theme)
different["colors"]["map_accent"] = "#2378A5"
other = SeriesMap(data, style, different)
assert m.points == other.points
assert m.render("travel", 2, 8).tobytes() != other.render("travel", 2, 8).tobytes()
print("series map structural check passed")
```
