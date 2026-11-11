# 人物生平动画 Skill · V2.0

供人物视频合集复用的 Agent Skill。固定视频、地图、文字与封面的版式，每位人物重新考据史料，并设计专属配色、环境、建筑、道具和动作。

**从 [START_HERE.md](START_HERE.md) 开始，再读取 [SKILL.md](SKILL.md)。**

## 已固定的系列规格

- 视频：9:16，1080×1920，30 fps，120 秒，固定 12 章；默认无旁白，使用随包原配乐。
- 字体和位置：随包四款字库；标题、年代地点、诗词、出处、说明、评价均由代码按固定坐标合成。
- 地图：透明累计行程，固定在 (96,150)，大小 880×430；不显示“一生足迹”标题。
- 动画：每章需要人物或物件的实际动作，粗块面、纸切剪影、克制纸纹；背景根据人物和事件重新绘制。
- 封面：独立 1200×1500 PNG。用户所称“5:4竖屏”按长短边理解，实际宽高为 4:5；字位、字号固定。

固定的是合集排版与视觉语法。**人物的颜色、背景与道具应当变化，不必都画山水。**

[人物配色与背景对照](assets/series/series-comparison.png) · [视频坐标图](assets/series/video-layout-guide.png) · [封面坐标图](assets/series/cover-layout-guide.png)

## 获取和安装

```bash
git clone https://github.com/2718056795-tech/biography-video.git historical-biography-video
cd historical-biography-video
python scripts/verify_series_bundle.py
```

克隆目录使用 `historical-biography-video`，与 Skill 名称一致。安装到助手支持的 skills 目录，保留全部子目录和素材；详见 [INSTALL.md](INSTALL.md)。也可让助手直接读取本仓库的 `SKILL.md`。调用示例：

> 使用 $historical-biography-video 做一集苏轼。沿用固定版式和配乐，重新考据史料，设计适合他的配色、背景与动作。

制作环境需要 Python 3、Pillow、NumPy、SciPy 和 FFmpeg/ffprobe；重建 SVG 素材另需 Inkscape。字体和固定音轨已经随仓库提供。不要用相似系统字体替换固定字库。

## 程序入口

| 用途 | 文件 |
| --- | --- |
| 新建人物项目 | [scripts/init_series_project.py](scripts/init_series_project.py) |
| 视频排版与地图 | [scripts/series_frame.py](scripts/series_frame.py)、[scripts/series_map.py](scripts/series_map.py) |
| 实际视频渲染 | [scripts/render_series_video.py](scripts/render_series_video.py) |
| 独立封面排字 | [scripts/series_cover.py](scripts/series_cover.py) |
| 固定程序与字库校验 | [scripts/verify_series_bundle.py](scripts/verify_series_bundle.py) |
| 媒体、封面与交付验收 | [scripts/verify_media.py](scripts/verify_media.py)、[scripts/verify_cover.py](scripts/verify_cover.py)、[scripts/check_delivery.py](scripts/check_delivery.py) |

主合成器接收每位人物独立制作的无字动画画面，统一叠加标题、地图和说明。完整接口和 2 秒实际动画示例见 [START_HERE.md](START_HERE.md)。

## 验证与素材说明

当前系列合成器以杜甫 V4 为基准，通过 15 个原生画面的逐像素一致性检查和 108 个地图时点检查，并完成了 2 秒有声视频管线验证。报告在 [references/](references/)；这些结果不代表所有新人物已经完成史料核查或整片制作。

`assets/dufu-reference/` 保留杜甫的动作、分层画面与史料案例；新人物使用系列合成器，不直接沿用旧工程排版。李白、苏轼示例是美术方向参考。

四款 Noto 字体的授权和来源见 [字体版权文件](assets/series/fonts/COPYRIGHT.txt) 与 [字体清单](assets/series/fonts_manifest.json)。固定音乐的来源记录见 [fixed-bgm-provenance.json](assets/fixed-bgm-provenance.json)；本仓库的提供不扩展第三方素材原有授权范围。
