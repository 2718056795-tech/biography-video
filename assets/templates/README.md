# 计划数据格式

这些文件是通用计划脚手架，不是通用渲染器的输入接口。参考工程的中文字段与本格式不同，制作时须明确转换或按新人物修改工程，不能只改姓名便声称完成。

初始化：`python scripts/init_project.py --name 杜甫 --output /path/to/new-project --audio /path/to/chosen.m4a`。默认120秒、30fps、1080×1920；明确需要横版时用`--orientation landscape`并重新构图。初始化拒绝覆盖非空目录。

`project.json`默认包含必交`cover`配置：`required:true,width:1200,height:1500,orientation:portrait,format:PNG,path:output/cover_1200x1500.png`。用户叫作“5:4竖屏”，这里是长边:短边5:4、实际宽:高4:5，不能交换尺寸。封面须沿用成片视觉但独立构图，不取视频截图直接裁切。计划预检只验证配置，不代表封面已经生成；视频与实际封面都须完成。只有用户明确要求另一规格时才记录`explicit_user_override`并更改配置及验收参数，不能擅自增发其他画幅。

预检：`python scripts/check_project.py /path/to/new-project --report /path/to/new-project/qa/planning-preflight.json`。空脚手架必定失败。预检通过只代表结构与证据声明齐全，不代表史料真实、真实动画已生成或最终视频通过检查。

`references/source_ledger.csv`字段为`id,status,citation,url_or_path,claim,verification_note`。实际查阅核实后才将status填为`verified`；记录标题、可定位URL或本地证据路径、所支持的主张及核查说明。预检不联网验证来源内容。

`data/storyboard.json`的scenes数组每项须含：`id,title,period,place,event,event_summary,assessment,start_frame,end_frame,source_ids,local_action,environment_action,action_sample_frames,visible_visit_ids`。时间窗为`[start_frame,end_frame)`，连续覆盖全片；action_sample_frames至少两个不同的幕内整数帧。每章标题对应人生节点；local_action描述手脚或物体真实局部变化，environment_action描述环境运动。文字描述和取样帧安排不是动画验收证据，最后仍须从成片解码复核。

`event_summary`和`assessment`必须分别是非空短句，前者说明事件，后者给出具体原创解读/评价，不能互相重复或用空泛赞语填充。事实内容由同幕`source_ids`指向的台账证据支持；原创解读与诗句、历史引文分别处理。两者都必须进入实际画面，即使同幕有`quote`也不能清空或跳过解释。按阅读预算分时显示事件、引文和解读，保持地图、角色动画与配乐连续，不把所有文字同时堆满。预检只能发现缺失、空白或直接重复，文案质量与实际绘制仍须看成片。

`data/life_route.json`的nodes项含`id,label,lon,lat,precision`，precision为`city_approx`、`region_approx`或有史料支持的`sourced_exact`。visits项含`id,node_id,scene_id,period,source_ids`。segments项含`from_visit,to_visit,schematic:true,source_ids`，按visits顺序只连接相邻异地访问，表示主要连接而非精确古道。每幕visible_visit_ids必须为全局visits的有序前缀，按时间累计，不能提前显示后续章节的访问，旧访问不消失；末幕按顺序保留全部已登记访问。相同地点回访使用不同visit，复用同一node。

地图默认不显示字面“一生足迹”标题，使用足够大的原生地理构图和可读地名；`map`只是布局意图，预检不可能用配置声明证明手机可读。音频path相对项目目录，sha256锁定输入；最终成片仍需验证AAC载荷或解码PCM一致。

封面成品检查：`python scripts/verify_cover.py --cover /path/to/cover.png --report /path/to/cover-qa.json`。双文件门禁：`python scripts/check_delivery.py --video /path/to/final.mp4 --cover /path/to/cover.png --media-report /path/to/media-qa.json --report /path/to/delivery-qa.json`。两项都读取实际封面并验证PNG与尺寸；双文件门禁还核对实际视频哈希与通过的媒体验收报告绑定。二者依赖Pillow，不能替代文字/构图/风格视觉复核。
