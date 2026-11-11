# 系列封面排版API与布局记录

`assets/series/series_style.json`是固定几何与字体母版。人物的主题色与背景母题随人物重做，不能把杜甫的色盘或茅屋复制给所有人物；标题坐标、字号、字体角色与画布规格仍保持系列一致。

## 无字底图与确定性排字

先绘制1200×1500无字PNG，美术主体放在`cover.art_reserved_top`以下；顶部0—559像素为排字保留区，不放重要脸部或器物。不要让图片生成模型制作最终中文文字。合成器会覆盖整个顶部保留区，再用捆绑字体准确排字，不缩字体、不移动版位。

```bash
python "<SKILL_ROOT>/scripts/series_cover.py" --art "<TEXT_FREE_ART_PNG>" --name 杜甫 --title 此心在人间 --hook 写尽人间疾苦 --theme "<PERSON_THEME_JSON>" --output "<COVER_PNG>" --report "<COVER_LAYOUT_JSON>"
python "<SKILL_ROOT>/scripts/check_series_style.py" --report "<COVER_LAYOUT_JSON>" --profile "<SKILL_ROOT>/assets/series/series_style.json" --theme "<PERSON_THEME_JSON>" --output "<STYLE_QA_JSON>"
```

所有坐标与字号从母版读取，不能在调用方覆盖。文字超宽或进入下部美术区会失败，应缩短片名/钩子，或采用有依据的常用姓名；不能悄悄缩字体。合成器只清理顶部文字区，下部无字与内容正确仍要看图核对。实际输出为宽1200、高1500，用户所称“5:4竖屏”是长边:短边5:4，宽:高4:5。

## 人物主题

主题JSON包含`theme_id,person,rationale,colors,motifs,background_choices`，可有`paper_variants`。`colors`内排版必须有`paper,ink,muted,accent,assessment`，可带其他背景和地图色角色，所有值是`#RRGGBB`。人物间允许色值不同；排版元素只能使用母版指定的颜色角色。主题不能传坐标、字号或字体覆盖。人物与母题的历史依据另记，技术校验不证明它们适合该人物。

## 布局记录结构

封面与视频帧均采用：

```text
profile_id, profile_sha256, kind("cover"|"frame"), canvas:{width,height},
theme_tokens:{颜色角色:HEX}, fonts:{字体角色:{path,sha256}}, elements:[...]
```

每个文字元素含`role,text,x,y,font,size,color_role,anchor:"lt",bbox`。`x,y`是母版固定的左上锚点，不能当成基线；`bbox`是文字实际像素边界，二者分别记录。多行元素可含`line_index`，固定锚点y按母版`line_height`递增；动画时的实际边界可用`actual_bbox`记录，但固定锚点不能被瞬时滑入偏移替代。线段记录`x1,y1,x2,y2,width,color_role`；其他绘制元素使用对应母版属性。

封面角色为`cover.name,cover.film_title,cover.hook,cover.accent_line`，另含`art:{source_size,reserved_top,retained_bounds,top_overwritten}`和输入/输出哈希。字体路径相对母版目录，校验器读取真实捆绑字体并比对其SHA256。

视频帧角色使用`header.*,standard.*,bookend.*,footer.*`。帧记录须有完整`map`母版配置和`stage:{profile_name,scale,offset_y}`；舞台profile只能选母版已有的几种。事件说明字号允许母版的34、33、32三个整数，其余字号保持固定。`footer.event`与`footer.assessment`不可省略；标题/正文使用standard或bookend版位。若记录`motion`，其内容须与母版一致。

沿用V4的引用出处位置规则：`standard.source.y = standard.quote.y + 实际引文行数 × quote.line_height + 1`，其后多行再加`source.line_height × line_index`。两行引文时为913，一行时为833；检查器从引文元素数量推导，不能用任意出处坐标冒充合法变体。

布局校验只核对记录中的固定几何、字体文件、主题角色和母版绑定；不对比不同人物的色值、背景图片像素或美术母题，也不认证史实、审美或中文内容。最终仍用`verify_cover.py`验证实际PNG，用`verify_media.py`验证成片，用`check_delivery.py`核对实际视频与封面双文件交付。
