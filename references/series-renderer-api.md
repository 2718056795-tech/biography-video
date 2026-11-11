# 固定版式合成器

`scripts/series_frame.py`直接读取`assets/series/series_style.json`中的像素坐标和字号。新人物替换内容、主题颜色及有生平依据的背景/道具；不重写排版函数，不在场景数据中传入自定坐标和字号。

此合成器接收已经动画化的原生艺术帧。它负责统一舞台、地图层、标题、诗句、事件和评价，不会自动研究史料，也不把一张静态图片伪装成动画。

## Python接口

```python
from series_frame import SeriesFrame

renderer = SeriesFrame(
    theme=theme_json,  # 含colors字典；按人物选择颜色，不改版式
    person={
        'name': '杜甫',
        'film_title': '此心在人间',
        'birth_death': '712—770',
        'opening_meta': '一生风雨，心系人间',
    },
    scene_count=12,
)
frame = renderer.compose(
    scene, t=3.5, duration=9.0,
    art_rgba=animated_art_frame,  # 1080×1920 RGBA；无文字、无地图
    map_rgba=animated_map_layer,  # 880×430 RGBA，已经投影；可用series_map生成
)
frame.save('preview.png')
report = renderer.last_report
```

`scene`字段：

- `id`：如`S02`。`index`为从1起的章节序号；若省略，可从`S02`解析为2。
- `kind`：`opening`、`chapter`、`ending`。省略时按首/末章节推导。
- `stage_profile`：只能选`room_high`、`gate_high`、`travel_wide`、`cottage_low`、`open_air`之一，依据这一幕建筑与人物高度选择，不能把所有人物套成山水。
- `title`、`meta`：对应章节题与简短年代/地点。开篇/收束仍保留这些数据，画面元信息使用人物的`opening_meta`/`birth_death`；可用`bookend_meta`明确替换文字内容。
- `quote_lines`：0—2行已核对的原文；`source_label`为完整作品出处。无引文时`explanation`应为1—2行简短串联；开篇/终章串联限制1行。
- `event_summary`、`assessment`：每幕必填，实际上屏；事件只允许34→33→32px的固定适配政策，评价始终30px。内容过长报错，先精简文字，不移动区域。

主题可直接传颜色角色，也可传`{'theme_id': ..., 'colors': {...}, 'motifs': [...], 'background_choices': [...]}`。合成器使用`paper`、`ink`、`muted`、`accent`、`assessment`五个角色；画面艺术与地图可使用更多主题色。人物身份、主题理由与背景元素方案保留在报告中。

人物场景的纸底可有同主题轻微色差。字幕底色取实际艺术帧左上角RGB，复现杜甫V4的逐幕纸色；它不是每帧随机噪声。终章画面淡出使用主题`paper`，原音轨不由本模块修改。

## 单帧命令

```bash
python "<SKILL_ROOT>/scripts/render_series_preview.py" \
  --project "<PROJECT_DIR>/project.json" --scene S02 --time 3.5 \
  --art "<PROJECT_DIR>/art/S02_phase.png" \
  --map "<PROJECT_DIR>/art/S02_map.png" \
  --output "<PROJECT_DIR>/qa/S02_locked_preview.png" \
  --report "<PROJECT_DIR>/qa/S02_layout.json"
```

项目可在`project.json`直接含`scenes`数组，或使用`data/storyboard.json`。`person`可嵌套为对象，也可使用顶层`name/film_title/birth_death/opening_meta`。主题可为内嵌字典或相对项目目录的JSON路径。场景用`start_frame/end_frame`（左闭右开）；旧字段`end_frame_exclusive`兼容。`--duration`仅供组件预览明确时长，不代表可改音乐时间轴。

没有地图时可省略`--map`以检查单个组件；报告会记`map_present:false`，这不能被当成已满足完整视频的累计足迹要求。单帧命令不构成实际视频交付。

## 不可随人物改动

位置、字号、字体、入场/出场时长、地图880×430承载区与五个舞台缩放组合来自同一契约。`title_x`、`layout_overrides`、`stage_scale`等场景覆盖参数直接报错。字体从包内固定OTF读取，缺失时失败，不静默换系统字体。报告逐项记录`profile_id/profile_sha256`、字体路径与哈希、主题角色、实际文字边界、地图位置和舞台组合，供版式检查器核对。

文学原文太长时选择有依据的完整短节选、合理断行或精简串联；人物姓名和片名太长时使用有依据的通行名称或更短片名，不能擅自缩字挤出另一套视觉风格。
