# 杜甫规范化可运行示例

此目录使用统一合成器与真实关节/环境代码复现杜甫。它不是给另一人物改名字就能用的美术内容。新人物从`init_series_project.py`建立自己的资料、调色与场景provider。

在Skill根目录可运行2秒样例：

```bash
python scripts/render_series_video.py --project assets/series/examples/dufu-project/project.json --preview-scene S02 --preview-start 2.5 --preview-seconds 2 --output /path/to/dufu-sample.mp4 --report /path/to/dufu-sample.json
```

完整输出使用同一project，省略preview参数；完成后另跑视频、封面与双文件交付验收。详见`references/series-video-api.md`（Skill根目录）。

路径相对本项目或由provider向上定位Skill，包内无需联网、系统字库或账户密钥。证据为原杜甫记录的继承，来源边界与约位精度没有因转换而升级。

[当前V2.2实际6秒有声样片](../map-labels-dufu-preview-6s.mp4) · [V2.2地名常驻检查](../../../../references/map-labels-check.json)。当前示例使用随包海岸与河流，已到地名常驻、行程线等粗，原海岸裁片配置仅作历史来源记录。

[历史V2.1底图检查](https://github.com/2718056795-tech/biography-video/blob/bad0f061e6fdf87ab64a930ed0a8c85b8627aa60/references/map-upgrade-check.json)对应旧提交，不能用其中旧引擎或样图哈希校验本版本重生成的文件。

[历史V2.0的2秒有声样例](qa/smoke_preview_2s.mp4) · [历史V2.0字库/版式检查](qa/normalized_layout_check.json)保留当时结果，不作为V2.1地图验收。这些局部管线实跑不代表重新渲染过完整120秒。
