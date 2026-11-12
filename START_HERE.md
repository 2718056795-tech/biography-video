# 人物生平动画包 V2.2.1：交给其他AI的入口

先完整解压目录，再让助手读取`SKILL.md`。不要只把“像杜甫”一句话或一张截图交给助手重新猜布局。

本包 V2.2.1 修正开篇和地点引入前的行程提前泄露；profile `biography-paper-cut-series-2.2`、证据schema2.2与母版JSON/hash保持不变，已有2.2项目无需格式迁移，旧显示计划仍须预检。标题/页脚/地图面板坐标、字体、字号、封面几何与时间轴保持原值，V2.1 的底图/来源/可读性检查继续保留。本包固定视频/封面的排版与字库；每个人物另做主题配色、背景、建筑、器物、光源与符合史料的内容。三图先看：

- [相同版位、不同人物主题与背景](assets/series/series-comparison.png)
- [视频逐像素坐标导览](assets/series/video-layout-guide.png)
- [封面固定字位导览](assets/series/cover-layout-guide.png)

## 复用规则

1. `assets/series/series_style.json`是唯一坐标母版，`series_manifest.json`锁定程序/字库；先运行`python scripts/verify_series_bundle.py`，再用 `python scripts/series_basemap.py` 核对离线底图、来源与许可哈希。
2. 新人物用`init_series_project.py`新建工作目录，明确给出本人物主题JSON；事实、引文与行程重新核查，艺术简报按12幕填写，不能复制杜甫背景或只改名。
3. 只在项目的美术provider实现无字、无地图的1080×1920实际动画。标题、页码、诗词、解读、地图和封面字层均交给包内固定程序，不改其坐标。
4. 开篇所有时刻只显示海岸/河流底图，不画地名、城市点、行程线、路线光晕/增长尖端或引线；旧 `overview=true` 也不能恢复行程预览。地点引入后才显示新地点与行程，后续章节在引入前保留已有历史。已到访地名跨幕保留，不显示未来地名，回访不重复标签；地名字位统一规划后固定，必要时短引线指向未移动的真实坐标。历史/增长中/完成路线统一2.1px、alpha210及相同光晕，当前点用圆环提示。地图使用随包有来源的海岸与主要河流；内陆不强行绘海岸，不添加虚构地形。先检查实际合成底色上的地图可读性、单帧/短动画和版位记录，再输出完整视频与1200×1500封面；源音轨完整保留。
5. 渲染结束后还要跑媒体/封面/双文件验收。布局参数通过不等于史料、动作、阅读、真人听审或设备发布预览全部通过。

## 新建人物

```bash
python scripts/init_series_project.py --name 人物姓名 --title 本集短片名 --theme /path/to/本人物主题.json --output /path/to/新项目
python scripts/check_project.py /path/to/新项目
```

空事实/空来源/未实现的动画应当失败；先补齐计划和美术，不能把脚手架当成片。

## 快速确认程序能用

包内有规范化的已核查杜甫案例，下面只输出2秒有声预览，并不声称重新完成120秒：

```bash
python scripts/render_series_video.py --project assets/series/examples/dufu-project/project.json --preview-scene S02 --preview-start 2.5 --preview-seconds 2 --output /path/to/dufu_preview_2s.mp4 --report /path/to/preview_report.json
```

完整命令、provider接口、地图数据、封面排字见[视频入口](references/series-video-api.md)、[项目接口](references/series-project-api.md)、[地图接口](references/series-map-api.md)、[封面接口](references/series-cover-api.md)。

四款固定OTF已经随包提供，包含字体授权；无需寻找相似系统字体。当前字库保留源SC默认字形和横排度量，基本汉字/标点等覆盖见`fonts_manifest.json`，缺字会在样式检查中报错，不能偷偷换字库。使用有依据的常用写法或按相同源字库扩充，而非改字体风格。

## 一致性的实际证据

**HISTORICAL V2.0 evidence（历史 V2.0 证据）：** `references/series-frame-final-check.json` 的15个画面和 `references/series-map-check.json` 的108个地图时点只证明旧版基准。V2.1 增加真实地理要素和可读性处理，地图像素已变，不能沿用旧报告声称新地图逐像素相等。

V2.1 的 [map-upgrade-check.json](references/map-upgrade-check.json)、旧地理对照和3秒样片仅是历史 V2.1 证据。V2.2 的 [map-labels-check.json](references/map-labels-check.json) 与6秒样片也归为历史证据。当前 V2.2.1 检查见 [map-opening-check.json](references/map-opening-check.json)，范围、实际3秒开篇样片与未执行项以报告为准；短片不冒充整条新120秒成片。示意图中的李白/苏轼只作配色与环境设计参考，不是已考据完成的新人物视频。

随包底图是概化的现代地理参照，不是唐代河道、古代疆界或考证古道；狭窄地区可需补充更详细的有来源数据。完整说明见 [地图接口](references/series-map-api.md) 与 [V2.2.1 开场说明](references/map-opening-v2.2.1.md)。

## 解压

字体使用标准ZIP-LZMA无损压缩以减小包体。Python可直接完整解压：`python -m zipfile -e "包.zip" "解压目录"`。解压后直接使用四个OTF，不需要联网下载字库。
