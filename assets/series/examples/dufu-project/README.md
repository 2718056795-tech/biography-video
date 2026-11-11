# 杜甫规范化可运行示例

此目录使用统一合成器与真实关节/环境代码复现杜甫。它不是给另一人物改名字就能用的美术内容。新人物从`init_series_project.py`建立自己的资料、调色与场景provider。

在Skill根目录可运行2秒样例：

```bash
python scripts/render_series_video.py --project assets/series/examples/dufu-project/project.json --preview-scene S02 --preview-start 2.5 --preview-seconds 2 --output /path/to/dufu-sample.mp4 --report /path/to/dufu-sample.json
```

完整输出使用同一project，省略preview参数；完成后另跑视频、封面与双文件交付验收。详见`references/series-video-api.md`（Skill根目录）。

路径相对本项目或由provider向上定位Skill，包内无需联网、系统字库或账户密钥。证据为原杜甫记录的继承，来源边界与约位精度没有因转换而升级。

[实际已渲染的2秒有声样例](qa/smoke_preview_2s.mp4) · [当前字库/版式记录检查](qa/normalized_layout_check.json)。这是局部管线实跑，不代表重新渲染过完整120秒。
