# V2.2.1：开篇仅底图，地点引入后显示行程

V2.2.1 修正地图在地点尚未引入时提前透露行程的问题。开篇所有时刻只显示有来源的海岸/河流地理底图；不显示起点名、城市点、未来点、行程线、路线光晕、增长尖端、引线或范围注记。旧 `overview=true` 在任何场景中都不能恢复全路线预览。

这是程序行为补丁：profile 仍为 `biography-paper-cut-series-2.2`，地图证据schema仍为2.2，`series_style.json` 的SHA256仍为 `5b8c9cfbd50a3e249be24086d6e83a976f84f298d1a00f8bf75a2d3484566327`。标题/页脚/地图面板坐标、字体/字号、12槽时间轴、舞台、封面及原配乐均不变。已有2.2项目无需格式迁移，旧显示计划仍须预检，重新运行预检并生成地图/预览/验收即可；旧引擎或PNG证据不能认证补丁行为。

## 显示顺序

| 时段 | 允许显示的地图内容 |
| --- | --- |
| 开篇全时段 | 只有海岸/河流底图；不因旧overview、时间推进或节点配置而出现行程层。 |
| 首个实际地点章节，引入前 | 同样只有底图，无起点名/城市点、未来点或路线。 |
| 地点引入时，默认0.3秒 | 显示起点名和城市点。 |
| 引入后再延迟0.45秒 | 才开始路线增长；默认严格晚于0.75秒出现增长段。 |
| 抵达目的地 | 按原 `progress>=0.99` 门槛增加该地点的城市点与标签，随后持续保留。 |
| 后续章节，本幕地点引入前 | 保留此前已到访的地名、城市点和已完成路线；不提前显示新段或未来地点。 |

增长尖端是已开始的行程的一部分，不能在路线增长前出现。未来城市点也不能以低透明度预先摆出。范围注记只在相应地点引入并满足到达条件后显示，不用于填充开篇。

已到访地名继续跨章保留，回访按节点ID去重；标签一次规划、位置稳定、文字在路线之上并强制纸色描边。历史/增长中/完成路线仍统一2.1原生px、alpha210，光晕宽4.5px、alpha64，当前地点由圆环强调。底图薄海岸/河流、地理来源与许可/哈希、实际像素校验和背景可读性检查继续保留。现代概化底图不代表唐代河道、疆界或考证古道。

## 地点引入字段与校验

路线使用 `per_scene.<幕ID>.location_intro_sec`，默认读取母版 `standard.meta.start` 的0.3秒。非开篇值必须是有限数字、至少0.3秒且小于本幕实际时长；非法值会明确失败。分镜 scene 若也提供同名字段，必须匹配路线的有效值，不改变固定字幕时间轴。路线增长起点为该值加母版 `map_segment_delay=0.45` 秒。

旧计划若将起点访问显示关联放在S01或填写非空的 S01 `visible_visit_ids`，应将显示关联移到首次地点介绍章节并清空开篇显示列表；原事件年代、来源和研究记录保留。这是展示计划修正，不是profile/格式迁移，详见 [项目接口](series-project-api.md)。

开篇按路线 `scene_order` 的第一幕确定；未给出 `scene_order` 时使用 `per_scene` 插入顺序。开篇访问范围必须为0..0；开篇中的旅行访问应放入下一幕，后续每幕 `start_index` 必须接续前幕 `end_index`，不能跳过访问。`validate_scene_timings(scenes,fps)` 进一步核对分镜顺序、只有首幕为 `kind=opening`、有效帧窗和地点引入值，并核对首/末原生帧。移动幕须在末帧到达 `end_index`，引入过晚导致行程无法完成时明确失败，不能靠下一幕凭空补出历史；项目预检、单帧命令与整片入口都在渲染前执行此校验。

`frame_state()` 保留2.2接口并增加 `visible_marker_ids`、`is_opening`、`base_only`、`location_intro_sec` 和 `route_growth_start_sec`；`overview_preview` 恒为false。开篇 `current_index=None`、可见标签/城市点/路线段列表为空、`arrival_status=basemap_only`。首个地点引入前为 `awaiting_location_introduction`；已有历史或地点引入后的正常状态为 `cumulative_arrivals`。上述状态绑定官方地图重绘、来源、引擎/政策/几何和RGBA像素证据，不能通过修改报告伪造通过。

## 当前检查与实际文件

当前验证以 [map-opening-check.json](map-opening-check.json) 为准，本补丁展示文件为：

- [开篇与地点引入对照图](../assets/series/examples/map-opening-comparison.png)
- [杜甫3秒真实开篇样片](../assets/series/examples/map-opening-dufu-preview-3s.mp4)
- [开篇样片解码帧](../assets/series/examples/dufu-v2.2.1-opening-frame.png)

报告应分别记录开篇各时刻与纯底图像素一致、地点引入前/时、路线增长前/时、后续历史保留、无未来城市点，以及旧overview被忽略。视频逐幕QA在首/中/末帧、每次抵达前后，另采样 `before_location_intro/at_location_intro` 和 `before_route_growth/at_route_growth`；区间外门槛不伪造采样。

开篇样片验证开篇实际编码区间；地点引入和路线延迟由对应对照/检查证据验证，不能把只含开篇的3秒视频称作展示了后续章节全部行为。未执行的120秒完整渲染、真人完整听审或设备发布预览继续记为待检查。完整作品的真实MP4、独立1200×1500 PNG封面及来源/验收要求不变。

## 历史V2.2证据

**HISTORICAL V2.2 evidence（历史 V2.2 证据）** 固定于 [`8ee5191f70a7333b1d42b676d5d7c092f56612e1`](https://github.com/2718056795-tech/biography-video/commit/8ee5191f70a7333b1d42b676d5d7c092f56612e1)。当时的开篇全路线行为已被本补丁替换；历史报告的哈希不能认证当前程序或重新生成的QA。

- [V2.2原始检查报告](https://github.com/2718056795-tech/biography-video/blob/8ee5191f70a7333b1d42b676d5d7c092f56612e1/references/map-labels-check.json)
- [V2.2原始地图对照图](https://github.com/2718056795-tech/biography-video/blob/8ee5191f70a7333b1d42b676d5d7c092f56612e1/assets/series/examples/map-persistent-labels-comparison.png)
- [V2.2原始6秒样片](https://github.com/2718056795-tech/biography-video/blob/8ee5191f70a7333b1d42b676d5d7c092f56612e1/assets/series/examples/map-labels-dufu-preview-6s.mp4)
- [V2.2原始说明](https://github.com/2718056795-tech/biography-video/blob/8ee5191f70a7333b1d42b676d5d7c092f56612e1/references/map-labels-v2.2.md)

本包的V2.1和V2.0报告也只保留各自的历史范围。任何历史逐像素相等或短片结果，都不代表本次重渲了120秒完整视频。

## 样例证据归档

随附[S01完整QA记录](../assets/series/examples/dufu-project/qa/series-layout/S01.map-qa.json.gz)使用标准JSON.GZ无损保存；原始JSON字节数与SHA256见[检查报告](map-opening-check.json)。程序实际运行仍生成普通JSON。
