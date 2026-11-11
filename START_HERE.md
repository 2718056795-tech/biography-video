# 系列母版 V2.0：交给其他AI的入口

先完整解压目录，再让助手读取`SKILL.md`。不要只把“像杜甫”一句话或一张截图交给助手重新猜布局。

本包固定视频/封面的排版与字库；每个人物另做主题配色、背景、建筑、器物、光源与符合史料的内容。三图先看：

- [相同版位、不同人物主题与背景](assets/series/series-comparison.png)
- [视频逐像素坐标导览](assets/series/video-layout-guide.png)
- [封面固定字位导览](assets/series/cover-layout-guide.png)

## 复用规则

1. `assets/series/series_style.json`是唯一坐标母版，`series_manifest.json`锁定程序/字库；先运行`python scripts/verify_series_bundle.py`。
2. 新人物用`init_series_project.py`新建工作目录，明确给出本人物主题JSON；事实、引文与行程重新核查，艺术简报按12幕填写，不能复制杜甫背景或只改名。
3. 只在项目的美术provider实现无字、无地图的1080×1920实际动画。标题、页码、诗词、解读、地图和封面字层均交给包内固定程序，不改其坐标。
4. 先检查单帧/短动画和版位记录，再输出完整视频与1200×1500封面；源音轨完整保留。
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

当前字库与通用合成器已对杜甫V4做15个原生画面逐像素相等测试，地图另做108个时点相等测试；报告在`references/series-frame-final-check.json`与`series-map-check.json`。真实2秒管线测试不冒充整条新120秒成片。示意图中的李白/苏轼只作配色与环境设计参考，不是已考据完成的新人物视频。

## 解压

字体使用标准ZIP-LZMA无损压缩以减小包体。Python可直接完整解压：`python -m zipfile -e "包.zip" "解压目录"`。解压后直接使用四个OTF，不需要联网下载字库。
