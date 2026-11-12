# V2.2：已到访地名持续显示与统一路线

V2.2 按用户要求改进地图阅读：地名抵达后持续保留，后续章节仍可读到此前地点；历史、增长中和已完成路线使用相同的主笔画与光晕。profile 更新为 `biography-paper-cut-series-2.2`，明确记录这次地图样式变化。标题/页脚/地图面板坐标、字体/字号、12槽时间轴、舞台、封面几何与原配乐保持原值；地图面板仍为(96,150)、880×430。

## 地名何时出现、放在哪里

标签按实际访问顺序和抵达状态显示。未抵达目的地不提前出现地名；已经到访的地点跨帧、跨幕保留。同一 `node_id` 的回访复用同一份标签，不叠出重复地名，也不因为当前点换地方而让旧地名消失。序章 `overview` 仍可预览全路线，使用相同笔画且不显示地点标签或已抵达城市强调；正常章节按上述规则累计。地图可直接渲染任意章节/时刻，显示状态由数据和时间计算，不依赖此前是否渲染过其他帧。

标签在一次项目地图构建时，按全部已知路线统一规划位置。规划未来路线只是为了避让，未来地名仍隐藏。搜索先尝试整条路线零相交，密集条件下可使用带惩罚的路线相交候选并保留审计记录，不能声称算法保证所有标注与路线几何零相交。各帧复用同一布局，地名不随路线生长跳动。文字绘在所有路线之上，28px粗体与2px描边保持固定，描边有效色强制为本主题纸色；密集地点可把文字放在邻近空处，用短引线连接真实地点；描边在最后一层保护文字，避免底下路线穿过字形。地图节点、路线端点和真实经纬度保持不变，不能通过移动城市、缩字号或每帧重新排字解决拥挤。

查看实际地图时，应核对文字彼此不相撞，可见路线不盖住文字字形，标注不出框，引线不误指。自动避让和像素证据不能替代手机大小的视觉检查。数据过密或名称过长时，应按实际错误调整有依据的标签或视窗；不能手写通过报告。

## 统一的是路线笔画

历史、增长中与已完成路线主笔画统一为2.1原生px、alpha210，光晕统一宽4.5px、alpha64；不会因变成历史段而变细，也不会靠加粗新段提示当前行程。路线仍按原时间规则增长，当前地点由圆环强调。海岸与河流仍是较细的地理底图线，不套用路线统一规则。

V2.1 的真实地理与验收继续保留：Natural Earth 离线底图、来源/许可/文件哈希、视窗与同一投影裁切、地图官方重绘与RGBA像素校验、实际艺术背景上的对比度检查。底图仅作概化现代地理参照，不代表唐代河道、疆界或考证古道；内陆不强塞海岸，狭窄地区默认数据不足仍须补充有来源的详细数据或合理扩大范围。数据接口见 [地图接口](series-map-api.md)。

## 本次实际证据

当前检查见 [map-labels-check.json](map-labels-check.json)。本次展示文件为：

- [累计地名与统一路线对照图](../assets/series/examples/map-persistent-labels-comparison.png)
- [杜甫6秒真实样片](../assets/series/examples/map-labels-dufu-preview-6s.mp4)
- [新版样片解码帧](../assets/series/examples/dufu-v2.2-labels-frame.png)

这些文件的实际生成结果、区间、哈希和未执行项以报告为准。验证应覆盖抵达前/后、后续章节、回访、任意顺序渲染，以及稠密标签和整条路线的关系。地图证据schema为2.2；`visible_label_ids`、`frame_state`、`label_layout_sha256` 与 `route_stroke_policy` 绑定同一时刻的官方状态。帧报告 `map_labels` 提供当前可见ID、稳定布局指纹/可见布局与路线政策，视频样本除首/中/末帧还覆盖每次抵达前后，预检检查跨章保留。官方地图或预览的像素改变后必须重新生成证据。

预览命令及 `check_series_style.py --frame <PNG> --map <PNG> --require-pixels` 继续使用原接口，详见 [帧接口](series-renderer-api.md) 与 [视频接口](series-video-api.md)。只核对JSON记录不认证实际图片；六秒短片不证明重新渲染完整120秒。真人完整听审、设备发布预览等若未执行，继续记为待检查。

已有V2.1项目可通过 `migrate_series_project.py --project <project.json>` 查看默认只读计划，使用 `--apply` 进行有备份的元信息迁移。它只接受已发布的已知契约，不改变史实、路线、艺术、配色或时序；迁移后重新生成地图和验收。完整参数见 [项目接口](series-project-api.md)。

封面的画布与字位几何未变，但当前封面布局记录仍须绑定2.2 profile及其哈希。旧profile记录、旧PNG侧车或旧缓存不认证新版地图状态。

## V2.1 历史文件与固定提交

**HISTORICAL V2.1 evidence（历史 V2.1 证据）** 固定于提交 [`bad0f061e6fdf87ab64a930ed0a8c85b8627aa60`](https://github.com/2718056795-tech/biography-video/commit/bad0f061e6fdf87ab64a930ed0a8c85b8627aa60)。本包保留的 [map-upgrade-check.json](map-upgrade-check.json) 是上一版地理升级归档；其中哈希对应当时文件，不能用于认证当前重新生成的程序、布局记录或图片。

要复核V2.1原始文件，请使用该提交中的固定链接：

- [V2.1检查报告](https://github.com/2718056795-tech/biography-video/blob/bad0f061e6fdf87ab64a930ed0a8c85b8627aa60/references/map-upgrade-check.json)
- [V2.1地理对照图](https://github.com/2718056795-tech/biography-video/blob/bad0f061e6fdf87ab64a930ed0a8c85b8627aa60/assets/series/examples/map-geography-comparison.png)
- [V2.1三秒样片](https://github.com/2718056795-tech/biography-video/blob/bad0f061e6fdf87ab64a930ed0a8c85b8627aa60/assets/series/examples/map-upgrade-dufu-preview-3s.mp4)
- [V2.1杜甫解码帧](https://github.com/2718056795-tech/biography-video/blob/bad0f061e6fdf87ab64a930ed0a8c85b8627aa60/assets/series/examples/dufu-v2.1-basemap-frame.png)

V2.0 的15画面、108地图时点相等报告也继续作为更早的历史证据。各历史报告不证明V2.2地图逐像素相同，也不证明本次完成了新的120秒全片。

## 样例证据归档

为减少包体积，随附的[S07完整QA记录](../assets/series/examples/dufu-project/qa/series-layout/S07.map-qa.json.gz)采用标准JSON.GZ无损归档；原始JSON的字节数与SHA256记录在[当前检查报告](map-labels-check.json)。程序实际运行时仍生成普通JSON。
