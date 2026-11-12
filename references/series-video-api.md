# 完整视频入口：固定版式与人物美术分离

`scripts/render_series_video.py`是实际MP4渲染入口。它逐帧调用本人物的美术provider，使用`SeriesMap`绘累计足迹，再由`SeriesFrame`合成固定坐标的标题、诗句、事件与评价。新人物只更换研究数据、主题和美术provider，不另写界面合成器。

本包版本为 V2.1，布局 profile 仍为 `biography-paper-cut-series-2.0`，地图内容与可读性升级会产生新地图像素。本版固定为母版的12槽、1080×1920、30fps、120秒和既定切帧。项目主动改变尺寸、时长、切点或槽类型会报错。需要另一个全局系列版式时，应明确建立新母版版本，不能让某一集自行漂移。

## 项目配置

```json
{
  "person": {
    "name": "人物姓名",
    "film_title": "本集短片名",
    "birth_death": "已核查的生卒年",
    "opening_meta": "简短开篇语"
  },
  "theme": "style/theme.json",
  "storyboard": "data/storyboard.json",
  "route": "data/life_route.json",
  "art_provider": "art/scene_provider.py",
  "art_dependencies": ["art"],
  "audio": {
    "path": "audio/locked-bgm.m4a",
    "sha256": "实际固定原件的SHA256"
  }
}
```

所有路径相对`project.json`所在目录。`theme`亦可直接内嵌完整主题对象。分镜为`{"scenes": [...]}`，字段沿用`SeriesFrame`及系列脚手架：12个唯一`id`、从1起的`index`、`opening/chapter/ending`、固定帧窗口、五选一的`stage_profile`、章节题/年代地点/原文或串联/事件/评价。`start_frame/end_frame`为左闭右开；兼容旧的`end_frame_exclusive`。画面正文和解释超出固定区域时应精简内容，不改坐标。

路线文件采用`SeriesMap`规范：本人物自己的节点、访问顺序、逐幕索引及可核查地理数据。默认离线读取随包 Natural Earth 真实海岸和主要河流；可在项目 `basemap_geojson` 或路线 `basemap.file` 声明本地地理线文件，兼容项目 `coastline_geojson` 或路线 `coastline.file` 的海岸输入。具体数据格式、来源要求及狭窄视窗失败处理见 [地图接口](series-map-api.md)。内陆不强塞海岸，不产生虚构地形。足迹节点、投影与素材依本人物史料建立，不继承杜甫路线；底图只作概化现代参照，不冒充唐代河道、疆界或考证古道。

## 人物美术provider

`art/scene_provider.py`必须定义：

```python
def draw_art(scene_id, local_t, full_scene_duration, theme):
    # 每帧根据真实动作相位重绘角色/道具/环境。
    # theme是完整人物主题，颜色在theme['colors']，母题和背景方案亦保留。
    return native_rgba_frame  # Pillow RGBA，严格1080×1920
```

输出应是舞台重排**之前**的原生艺术帧，不包含UI标题、页码、地图、诗句卡或下方解读。场景内既定物件文字（如收束卷轴上的原创片名）可以作为美术细节，但不能再绘另一份界面文字。合成器会按场景的五种舞台profile统一变换人物、建筑和支撑物；不要让provider自行挤压、裁切或改变固定文字区。

背景不固定为山水。新人物要依据所处时期、事件和身份重做环境、建筑、器物与光源；主题色同时用于艺术帧与UI，不能只给标题换颜色却保留另一人物的旧景物。用户允许的人物差异保留在美术方案中，固定的是剪影/粗块面画法及系列版式。

此入口要求provider逐帧执行，但它不通过“某个像素变了”认证真实动画。完成后仍须检查脚步、手与道具、风雨/屋檐、舟桨等的相对变化与接触关系。一个返回静图的函数不会因为编码成MP4就满足动画要求。

`art_dependencies`应列出provider在项目外使用的所有文件/目录。项目内`art/`默认参与缓存指纹；字体、母版、主题、路线、音轨、分镜与合成器代码也参加指纹。未记录的外部素材不应依赖`--resume`复用。

## 先跑有声短样例

```bash
python "<SKILL_ROOT>/scripts/render_series_video.py" \
  --project "<PROJECT_DIR>/project.json" \
  --preview-scene S02 --preview-start 2.5 --preview-seconds 2 \
  --output "<PROJECT_DIR>/output/preview_S02.mp4" \
  --report "<PROJECT_DIR>/qa/preview_S02_render.json"
```

示例从该幕2.5秒起输出2秒，逐帧渲染，原BGM从这幕全片起点加2.5秒摘取对应区间，以AAC流复制。`--preview-start`及秒数须对应整数帧且完全处于该幕。预览的音频包边界可能有约一包的容器首尾差，记录实际测量，不拿短片与整首音轨做全长相等检查；源音轨本身保持不变。

需要无声时用`--silent-preview`，文件名必须含`silent`或“无声”，防止将无声样例误当完整交付。预览报告明确`preview_only:true`，不认证120秒全片已完成。

## 渲染完整120秒

```bash
python "<SKILL_ROOT>/scripts/render_series_video.py" \
  --project "<PROJECT_DIR>/project.json" \
  --output "<PROJECT_DIR>/output/人物_完整片.mp4" \
  --report "<PROJECT_DIR>/qa/video_render.json"
```

逐幕片段暂存`output/.series-parts/`。编码为H.264/yuv420p、SAR1:1、30fps，全部3600帧合成后整条AAC原轨从0秒连续封装，完整片不截曲、不循环、不滤音量、不改速。已存在的最终文件默认保护；明确需要覆盖时用`--overwrite`，或选择新版本文件名。

中断后加`--resume`，仅复用源指纹、片段SHA及帧数一致的片段。`--scenes S02,S09`或`--scenes 2,9`只处理相应槽，报告`segments_rendered`，不会将两幕包装成完整片。之后用默认全槽及`--resume`完成其余部分并合成。

渲染报告包含真实输出哈希、ffprobe实际解码视频帧数、源音频哈希未变、地图几何报告和 `qa/series-layout/<SCENE>.json` 逐幕排版记录。顶层另有 `map_geometry_sha256`、`source_fingerprint` 及含摘要/报告路径的 `map_qa`；地图来源文件、引擎、几何与可读性证据参加恢复渲染指纹，旧无底图片段不能据原缓存冒充新版地图。

`qa/series-layout/<SCENE>.map-qa.json` 保存该幕实际渲染窗口首/中/末帧的 `before/mid/after` 地图检查；单帧窗口可共享一个采样。每个采样还记录 `background_readability`（对应帧报告的 `map_background_readability`），绑定实际艺术区域、地图哈希与对比度结果；不通过时中止渲染。选定检查时刻另保存 `<SCENE>.frame.png`、`<SCENE>.map.png` 与 `<SCENE>.map.png.evidence.json`，可与同目录布局记录运行实际像素核对。排版报告取该幕3.5秒/中点附近；短样片仅记录片段中真实调用的时刻。它记录参数与实际地图证据，不能替代实际编码后的视觉检查。章前、章中、抵达后仍须检查海岸/河流、累计线和当前点标签，以及手机大小下的可读性。

## 渲染后仍须验收与封面

```bash
python "<SKILL_ROOT>/scripts/verify_media.py" \
  --video "<FINAL_MP4>" --source-audio "<LOCKED_AUDIO>" --report "<MEDIA_QA_JSON>"
python "<SKILL_ROOT>/scripts/verify_cover.py" \
  --cover "<COVER_PNG>" --report "<COVER_QA_JSON>"
python "<SKILL_ROOT>/scripts/check_delivery.py" \
  --video "<FINAL_MP4>" --cover "<COVER_PNG>" \
  --media-report "<MEDIA_QA_JSON>" --report "<DELIVERY_QA_JSON>"
```

`video_render.json`不是`verify_media.py`的完整技术报告，不能拿渲染结束冒充AAC包/PCM一致性、实际动作、史料、主观听审或平台设备预览。还需实际1200×1500竖屏封面，并分别提供视频与封面。

## 包内杜甫规范化例子

`assets/series/examples/dufu-project/`已填好真实杜甫参考的数据转换、路线、主题路径和专用provider，可直接执行上述2秒命令。provider只调用旧工程的`Scene.art()`取原生角色/环境，不使用旧的UI、地图或字幕；固定字库与地图由新系列模块负责。它读取已准备图层，不重写Skill的SVG/PNG缓存，不需要系统中文字体。

此provider明确拒绝其他人物和与原美术不匹配的主题；不能将其改名当另一人的成片。新人物从`init_series_project.py`生成空稿，再实现自己有依据的画面与动作。V2.1 例子使用随包默认地理底图，旧中国海岸来源仅保留为 `legacy_coastline_reference`，其 `reference_only` 状态不表示正在参与本版绘图。例子的来源台账继承原B/Q核查记录，并保留现代约位、约年与未能打开来源等边界，没有因格式转换声称做了新研究。

若需要在Skill中重建该例子的规范化数据，可运行`export_dufu_reference_project.py --output <NEW_DIR>`；它只转换已有杜甫资料，不生成另一个人物，也不会自动把新研究标为完成。
