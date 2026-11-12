# V2.1 地图升级与证据边界

本页记录V2.1地理升级。**当前开场以 [V2.2.1说明](map-opening-v2.2.1.md) 为准：开篇全程仅底图，地点引入前不画新地点/行程，旧overview不恢复预览。** 底图来源与现代地理含义继续适用，本页旧报告/图片/短片仅作历史证据。

V2.1 在固定880×430地图面板内加入有来源的海岸和主要河流、地图对比度适配及实际像素证据。布局 profile 仍为 `biography-paper-cut-series-2.0`；地图位置(96,150)、其他文字坐标、字体/字号、12槽时间轴、舞台、封面和原配乐规则保持不变。地图内容改变意味着新地图像素与V2.0不同，不能再把旧逐像素相等报告当作当前地图验收。

## 地理数据与历史含义

默认底图来自 Natural Earth v5.1.2：1:5000万海岸与1:1000万河流/湖中线，含间歇河流并排除运河。固定上游提交为 `f1890d9f152c896d250a77557a5751a93d494776`，使用WGS84经纬度，转换后的真实线数据离线随包提供：

- [natural_earth_basemap.geojson.gz](../assets/series/geography/natural_earth_basemap.geojson.gz)
- [provenance.json](../assets/series/geography/provenance.json)：上游地址、固定版本、输入与派生文件哈希及转换说明。
- [LICENSE.md](../assets/series/geography/LICENSE.md)：上游公有领域条款。

可在包根目录运行 `python scripts/series_basemap.py` 离线核对底图、来源与许可完整性；损坏或缺失应恢复完整发布包。

这些线是概化的现代地理参照，用于让读者辨认人物行程所处区域。它们不复原唐代或其他时代的河道、海岸及疆界，不证明古今地名对应，也不证明点间曲线是可考古道。人物足迹须另有史料来源，底图许可不替代人物研究。

地图不绘国家边界或装饰性假地形，不以随机轮廓冒充山脉。内陆视窗可无海岸，有可读真实河流等地理参照即可。默认数据是概化数据；某个窄地区缺少河流或细节时，须补充有来源的更详细线数据或合理扩大视窗，不能为凑轮廓借用无关海岸。输入与失败处理见 [地图接口](series-map-api.md)。

## 绘图与可读性

地点、路线、海岸和河流共用一个投影、裁切范围和等比缩放。默认视窗从全部人物节点建立，提供最小区域跨度及有限的自动扩大；显式视窗不静默改写。累计访问、停留、回访与晚年范围注记由人物自己的路线数据控制；开篇和地点引入门槛采用当前V2.2.1规则，不使用全路线总览。

地图按主题纸底合成后的对比度适配有效地图颜色，并保留请求色、有效色及测量记录。浅底、深底均应实际查看最终画面：旧线、当前增长段、当前点和地名必须可辨，河流与路线应可区分。合成器还会测量实际艺术区域背景上的原生笔画核心对比度，报告 `map_background_readability` 绑定背景与地图哈希；失败阻止继续。计算结果不代替手机大小的视觉检查，不认证人物动作、史实或听审。

## 可复验的地图与画面

`SeriesMap.render()` 返回带 `image.info["series_map_evidence"]` 的880×430 RGBA。证据绑定来源、引擎、政策、几何、当前场景时间和原始地图像素；固定合成器拒绝缺地图、透明空图、无来源或与像素不匹配的图层。使用 `save_map_png()` / `load_map_png()` 保存和恢复证据，保存时同时保留 `<PNG>.evidence.json`；二者同时存在时必须一致，单帧命令外部 `--map` 要求侧车存在。

单帧命令默认从项目路线生成官方地图，可用 `--map-output` 保存地图以核对实际文件。`check_series_style.py --frame <合成PNG> --map <地图PNG> --require-pixels` 强制核对当前RGB画面、RGBA地图和合成后地图区哈希；只校验记录时明确 `actual_frame_pixels_verified:false` 和 `actual_map_pixels_verified:false`。完整调用见 [帧接口](series-renderer-api.md) 和 [视频接口](series-video-api.md)。

V2.1历史升级结果见 [map-upgrade-check.json](map-upgrade-check.json)，不认证当前补丁行为。V2.1杜甫短片解码帧为 [dufu-v2.1-basemap-frame.png](../assets/series/examples/dufu-v2.1-basemap-frame.png)；`dufu-v4-native-reproduction.png` 保留为历史V2.0参考，不作为当前新底图样图。对照图为 [map-geography-comparison.png](../assets/series/examples/map-geography-comparison.png)，真实短视频为 [map-upgrade-dufu-preview-3s.mp4](../assets/series/examples/map-upgrade-dufu-preview-3s.mp4)；执行范围、生成结果、哈希与待检查项按该报告阅读。对照场景或海外区域是地图适用性验证，不意味着已经研究或制作对应的新人物生平。

## 旧报告保留什么意义

**HISTORICAL V2.0 evidence（历史 V2.0 证据）：** [series-frame-final-check.json](series-frame-final-check.json) 的15个原生画面、[series-map-check.json](series-map-check.json) 的108个地图时点及旧有声短片管线报告保留当时V2.0的回归记录。它们不证明V2.1地图逐像素相同，也不证明新版本的120秒整片已经渲染。

本次短片证明对应的实际编码区间，抽帧证明对应画面；完整120秒渲染、真人完整听审与抖音设备发布预览若未执行，应继续记为待检查。完整作品仍须交付真实MP4、独立1200×1500 PNG封面和本次来源/验收报告。
