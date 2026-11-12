# 固定系列的新人物项目

本包 V2.2 的 profile 为 `biography-paper-cut-series-2.2`，记录累计地名与统一路线样式；标题/页脚/地图面板坐标、字体、字号、封面几何与时序保持不变。新人物使用系列脚手架，不能把旧版杜甫工程改姓名后直接出片。版位、捆绑字形、字号、1080×1920画布、30fps、120秒和12槽时间窗来自`assets/series/series_style.json`。主题色、背景、建筑、器物、光源和动作须为本人物重新设计，不因固定排版而固定成杜甫的茅屋与深绿色。

```bash
python "<SKILL_ROOT>/scripts/init_series_project.py" --name 苏轼 --title 人间有味 --theme sushi --output "<NEW_PROJECT_DIR>"
python "<SKILL_ROOT>/scripts/check_project.py" "<NEW_PROJECT_DIR>" --report "<NEW_PROJECT_DIR>/qa/planning.json"
```

`--theme`必须明确提供，可以是包内`libai`、`sushi`、`dufu`，或自行写出的新主题JSON路径。主题`person`必须对应本人物；新人物可由助手直接选择适合的配色与母题，无需另加确认流程。主题应写明`rationale`、颜色角色、`motifs`与`background_choices`，历史内容有来源，艺术选择作为设计说明，不冒充史实。

初始化默认复制系列固定配乐并记录SHA256，拒绝覆盖非空目录。脚手架填入12个固定帧窗、opening/chapter/ending类型与可选舞台profile，但所有人物事实、各章标题、年代地点、事件说明、评价、引文、来源和路线均留空。初始化后预检失败是预期结果，不能把空稿叫作完成视频。

## 主要输入

- `project.json`：`series_profile_id`与`series_profile_sha256`绑定包内母版；`person`含`name,film_title,birth_death,opening_meta`。人物姓名另在`name`镜像，须一致。未知年代可诚实写约年或范围，不能编造精确值。
- `theme`为`style/theme.json`相对路径；实际拷贝所选人物主题。颜色可以变化，不能加入项目坐标、字体或字号覆盖。
- `storyboard`和`route`分别为`data/storyboard.json`与`data/life_route.json`。每章填写`meta`、`period/place/event`、`title`、`event_summary`、`assessment`、来源与动作计划；有引文时填`quote_lines`与`source_label`，无引文时填简短`explanation`。两种情况都保留页底事件与原创解读。
- `art_direction`是本人物的实际美术方向对象：`rationale`、1—3个`motifs`及12条`backgrounds`。每条关联`scene_id`，说明`setting,buildings,props,light,source_basis,source_ids`。没有建筑可明确写“无建筑”，不要留空，也不要为凑字段虚构建筑。校验字段存在不证明美术适合人物；不会仅因山水主题重复而自动判错。
- 地理底图默认从随包 Natural Earth 离线数据读取，无需在新项目复制杜甫海岸。`basemap_geojson` 可在项目中指定自备地理线文件的相对路径（兼容路线 `basemap.file`）；来源、坐标和分类要求见 [地图接口](series-map-api.md)。`coastline_geojson` 兼容原海岸输入，不应再以国家多边形冒充海岸。底图是概化现代地理参照，人物足迹仍按本项目史料独立核查。地名按节点ID去重、抵达后跨幕保留；未来地名不提前显示。全项目一次规划标签位置，短引线只移动标注而不移动真实坐标，详见 [V2.2说明](map-labels-v2.2.md)。
- `art_provider`为`art/scene_provider.py`；`art_dependencies`显式登记美术依赖供恢复渲染指纹使用。默认`art/`整树也参与指纹，项目外依赖须显式列出。

## 真实动画提供者

```python
def draw_art(scene_id, local_t, full_scene_duration, theme):
    # 返回原生1080×1920 RGBA Pillow图像，包含实际人物/物件与环境动作。
    # 不含最终文字，不把静图推移当成角色动画。
    ...
```

初始化的实现只抛出`NotImplementedError`，明确阻止空稿渲染。完成逐幕素材和真实动作后再接入`render_series_video.py`。`theme`是完整原始主题对象，人物背景与符号由本期提供者决定，排版由固定系列合成器决定。

## 预检与边界

系列预检核对固定画幅、时长、帧率、12个切点、各章类型与舞台profile枚举；禁止任意项目或逐幕版位覆盖。它还检查分章、事件与原创评价、证据记录、累计路线和美术方向缺项；地图构建同时要求有来源的可用地理要素及可读性证据，不能用无背景点线或透明空图通过。默认数据在狭窄地区缺少要素时，应补充详细本地数据或合理扩大视窗，不为内陆强加海岸。预检还检查实际抵达状态和跨章标签保留、同一布局指纹及统一路线笔画；不能把一幅静图当作完整时间行为证据。若系列或字体锁定manifest存在，布局检查同时核对实际母版与字体哈希。

预检不认证史料真伪、文案质量或真实动画。完整视频仍须实际渲染、抽帧与连续动作检查、媒体验收和独立1200×1500封面制作，再经过双文件交付检查。

## 已有V2.1项目迁移

```bash
python "<SKILL_ROOT>/scripts/migrate_series_project.py" --project "<PROJECT_DIR>/project.json"
python "<SKILL_ROOT>/scripts/migrate_series_project.py" --project "<PROJECT_DIR>/project.json" --apply
python "<SKILL_ROOT>/scripts/check_project.py" "<PROJECT_DIR>" --report "<PROJECT_DIR>/qa/planning_v2_2.json"
```

默认只向标准输出写JSON计划；`--apply` 才更新列出的文件，并将修改前的项目内文件逐字节备份到 `.migration-backups/2.2/`。结果状态为 `dry_run`、`migrated` 或无变化时的 `already_current`；已有备份内容不同时拒绝覆盖。外部共享分镜/主题若需变更profile元信息，先写入项目内的副本再更新相对引用，不修改共享原件。

迁移接受已发布V2.1的 `biography-paper-cut-series-2.0` 与 SHA256 `43deba6023e50ff117e5b74ceccbc8d4bb4f5b08e1e4aa9f0982465bd9b5e6f0` 绑定，或当前2.2绑定；核对画幅、帧率、时长、12槽切帧、允许的舞台和布局/字体契约。未知版本、被改动的绑定或覆盖参数会明确拒绝。迁移更新项目schema/profile/hash，以及关联分镜和主题的profile元信息；已有史实、路线、艺术、颜色和时间窗保留，不替代研究或视频重渲。

迁移后重新运行预检并生成官方地图、预览及布局/像素报告。标题/页脚/封面几何不变仍需记录当前profile与哈希，不能把旧记录直接称为2.2通过。详细行为与证据边界见 [V2.2说明](map-labels-v2.2.md)。
