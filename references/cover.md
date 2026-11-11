# 必交封面：固定系列母版

每条完整视频同时交付独立1200×1500 PNG。用户所称“5:4竖屏”指长短边5:4，实际宽高4:5；1500×1200是横图，不能颠倒，也不默认另送9:16或3:4。

使用`scripts/series_cover.py`与[series_style.json](../assets/series/series_style.json)，不凭参考图自由重写排版。四款随包字体及映射固定，不能自动替换字库、缩字、挪位或重断行：

| 信息 | 位置 | 字体/字号 |
|---|---|---|
| 人物姓名 | (80,50)，最大宽1040 | Serif Bold 240 |
| 本片片名 | (80,320)，最大宽1040 | Serif Bold 120 |
| 原创钩子句 | (130,485)，最大宽990 | Sans Regular 42 |
| 强调线 | 按母版固定坐标 | 本集accent token |

超宽时选择真实通用姓名和准确的短片名/短钩子，不造简称，不擅改姓名。上方文字母版保持一致，人物、道具与背景在预留画面区按本集艺术简报独立绘制：颜色适合本人物，场景与经历相关。共享粗块面剪影、固定纸感与信息层级，不是所有人物都配同一山景。不能从9:16视频截图或简单裁切充当封面。

[封面布局图](../assets/series/cover-layout-guide.png)用于看固定位置，[系列艺术方向](series-art-direction.md)说明可变配色/环境，[系列布局](series-layout.md)给出与视频的共同规则。示意图不代替实际封面。

实际输出PNG后查看姓名、片名、人物对应与缩略图可读性，再执行：

```bash
python "<SKILL_ROOT>/scripts/verify_cover.py" --cover "<COVER_PNG>" --report "<COVER_QA_JSON>"
python "<SKILL_ROOT>/scripts/check_delivery.py" --video "<FINAL_MP4>" --cover "<COVER_PNG>" --media-report "<MEDIA_QA_JSON>" --report "<DELIVERY_QA_JSON>"
```

封面检查验证真实PNG、像素解码、尺寸与SHA256，不认证中文内容、OCR或审美。交付检查要求视频和封面均存在，媒体报告通过并绑定当前视频哈希。用户明确修改全局封面要求时另立模板版本并同步验收参数；常规新人物只更新内容与主题。

[杜甫固定字层封面](../assets/series/examples/dufu-cover-locked.png)、[无字插画](../assets/series/examples/dufu-cover-art.png)与[版位检查](../assets/series/examples/dufu-cover-style-check.json)是当前可执行母版示例。姓名、片名和短句均由程序输出，不能用旧整图生成文字代替。
