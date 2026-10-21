# 三维交互对比协议

评估对象是三维轨迹到接触／攻击事件的规则，不是姿态模型或 RGB-D 定位精度。无真实输入时报告必须标注 synthetic，不从合成分数推断人体准确率。

## 1. 入口

```powershell
.venv\Scripts\python.exe -m depthstrike.evaluation --suite synthetic --output outputs/comparison.json
.venv\Scripts\python.exe -m depthstrike.evaluation --input tests/fixtures/straight_punches.jsonl --labels tests/fixtures/evaluation/straight-punch-labels.json --output outputs/fixture-comparison.json
```

输出采用独占创建，不能覆盖旧报告。第二条使用手工核对的 4 帧合成夹具：左右直拳各一次，连续碰撞＋状态机应匹配 2 个窗口。不是读取记录中的 events 作为标签。

## 2. 受控方法

| 代号 | 规则 | 保持一致的条件 |
| --- | --- | --- |
| 2d_entry | 内参投影后的二维代理接触上升沿 | 同一骨架、平滑、拳心、半径、有效性和目标日程 |
| 3d_discrete_entry | 当前帧三维球体接触上升沿 | 同上 |
| 3d_swept_entry | 连续有效帧间球体扫掠进入 | 同上 |
| 3d_swept_punch | 连续进入且满足出拳／收拳状态，同一攻击一次结算 | 同上，增加攻击状态条件 |

接触基线均不是“每帧重叠就计分”；静止停留不应被故意构造成弱基线。二维基线以给定内参投影代理中心，按两轴焦距归一化，以半径/深度近似投影范围；不代表精确渲染球体轮廓。

四方法始终使用标签清单中的固定目标及活动手时间表，不随某个方法得分切换任务。激活目标、初始重叠、暂停或恢复追踪不凭空产生进入事件；断轨和忽略区间不桥接。扫掠时间使用线段交点在两帧间插值，单帧时间使用当前输入帧时间；这不是测得的真实接触时刻。

按各方法的候选接触时间检查活动区间，不要求两端采样帧都处于同一活动区间。所有目标在非活动期间仍更新几何接触历史，避免激活已经重叠的目标制造命中。离散检测与扫掠插值在日程边界可能给出不同结果，这是采样方法的区别。

评估不重演引导阶段。基础阈值来自录制配置；若要评价个体校准后的阈值，在标签清单的 `punch_thresholds` 中显式提供双手参数。全部参数进入报告，不能只保留最优结果。

## 3. 标签清单

可运行示例：[straight-punch-labels.json](../tests/fixtures/evaluation/straight-punch-labels.json)。顶层字段：

| 字段 | 内容 |
| --- | --- |
| schema_version | 整数 1 |
| evidence | synthetic 或 recorded；带 synthetic 来源的记录不能改标为 recorded |
| label_basis | 独立标注依据，不可写“模型认为命中” |
| unit / timestamp_unit / coordinates | m / s / camera_x_right_y_down_z_forward |
| intrinsics | width、height、fx、fy、cx、cy；可含 distortion_model 与 distortion |
| targets | 固定 target_id、hand、center[x,y,z]、radius |
| active_schedule | 非空、不重叠的 start_s、end_s、hand、target_id；左闭右开 |
| expected_windows | 独立定义的有效攻击命中窗口；同手同目标不重叠、不共用端点；闭区间 |
| ignore_windows | 不确定或无法独立判断的闭区间 start_s、end_s |
| punch_thresholds（可选） | left/right 各含 guard_extension_m、attack_extension_m、min_travel_m |

忽略区间内的预测和完全包含的标签排除；标签与忽略区间仅部分相交则拒绝，须人工拆分或重新界定。时间必须有限且 `0 <= start < end`，目标引用及深度范围必须有效，畸变模型不允许静默替换。manifest 限 4 MiB。

真人数据应在授权后录制，通过实测空间参照及独立观察标注有效直拳、未命中、重复接触和不确定区间。保留标注依据、参与者匿名标识、重复次数和调参／评价划分。recorded 仅说明使用录制数据，不等于标签已被外部核验。

## 4. 匹配与输出

按时间顺序，将同手同目标且位于窗口中的一条预测匹配一个未使用标签。额外预测记 FP，未匹配标签记 FN；落入已匹配窗口的额外预测也记 duplicates。输出 TP/FP/FN、precision/recall、重复数、样本数、追踪无效比例、逐场景预测、输入与标签 SHA-256、方法参数和证据类型。零分母为 null，不写成 100%。

sample_count 包含全部输入帧；evaluated_frame_count 排除暂停和忽略区间；tracking_invalid_ratio 以其为分母。比较窗口应覆盖目标任务，不能拿缺少相应输入的时间段包装算法性能。

内置 7 个解析场景用于区分深度错位、快速跨越、慢伸手、未收拳重入、静止停留、断轨恢复和正常左右拳，推导见 [夹具说明](../tests/fixtures/evaluation/README.md)。当前组合在这些刻意构造的场景上通过，不代表对真实运动的统计泛化。

软件计时使用 `--metrics`，口径见 [运行说明](RUNNING.md#5-软件耗时与对比实验)。没有同步的曝光／显示测量，不报告端到端延迟。
