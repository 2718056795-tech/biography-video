# V2.1 安装与调用

这是标准Agent Skills目录，入口为`historical-biography-video/SKILL.md`。完整保留`references/`、`scripts/`和`assets/`，尤其系列profile、四款字体、原BGM、`assets/series/geography/` 地理数据与参考资料。

1. 解压ZIP或tar.gz，保留完整目录结构。
2. 放入工具配置的skills目录；Codex个人技能通常为`~/.codex/skills/`。已有同名目录时先保留旧版。
3. 重新加载技能列表并启用；也可直接让助手读取`SKILL.md`与相关文件。本包创建与打包不等于已修改用户全局配置或发布到第三方。

调用示例：

> 使用 $historical-biography-video 做一集苏轼，按固定系列母版和原配乐，重新设计适合他的配色与场景。

> 使用 $historical-biography-video 修改杜甫，保留系列文字、地图与封面位置，先给我6秒实际动画预览。

包版本为 V2.1；布局 profile 仍为 `biography-paper-cut-series-2.0`，原坐标、字体、字号和时序保持不变。默认固定12槽、1080×1920、30fps、120秒、无旁白，必交独立1200×1500 PNG封面。字体、字号、坐标、时间轴和动效语法来自`assets/series/series_style.json`；新人物的资料、行程、配色、场景、道具与动作重新制作。主合成必须用`series_frame.py`、`series_map.py`和`series_cover.py`，不能只读“类似杜甫”后另写自由排版。用户明确改变全局规格时才创建新模板版本。

制作环境需Python3、Pillow、NumPy、SciPy、FFmpeg/ffprobe；SVG素材重建另需Inkscape。系列合成使用随包字体，不依赖接收机器自动替换字体。旧杜甫专用工程默认系统Noto路径，若重跑该案例需按其工程说明配置；它只作动作、史料与实现参考，不是新人物的系列排版入口。

地图默认使用随包离线的 Natural Earth 海岸与主要河流，运行时不需联网下载。安装后可运行 `python scripts/series_basemap.py` 核对数据、来源和许可文件哈希；丢失或被修改时应恢复完整发布包，不会静默换用简陋轮廓。完整保留底图文件及来源记录；内陆视窗不应强塞海岸，缺少可用要素的狭窄地区需提供有来源的详细地理数据。底图是现代地理参照，不是古代河道、疆界或考证古道，参见 [地图接口](references/series-map-api.md)。

项目预检只验证结构，不能证明研究、艺术或动画完成。完成后必须检查实际编码视频、固定原音轨、母版一致性与独立封面，分别提供两个真实下载链接；没有渲染工具时不能只返回文案并声称已出片。
