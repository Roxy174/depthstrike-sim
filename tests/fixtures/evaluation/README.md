# 解析评估场景

小型场景由 `src/depthstrike/evaluation_scenarios.py` 生成，不含人像、不下载数据。命中窗口由已知位置、0.14 m 的代理半径和有效直拳定义独立指定，不从待测输出生成。

| 场景 | 解析依据 | 检查点 |
| --- | --- | --- |
| depth_mismatch | 手深度 1.85 m，目标 1.50 m；横向移动进入投影 | 二维重叠可误触发，三维不接触 |
| fast_crossing | 0.1 s 内 z 从 1.85 到 1.15；接触入口在 0.03 s | 两端不接触，连续检测可发现穿越 |
| slow_extension | 0.05 m / 0.1 s = 0.5 m/s | 有接触，但不满足 0.65 m/s 的有效攻击定义 |
| contact_reentry | 收回至前伸量 0.32 m，未回到 guard | 重入不等于新的有效攻击 |
| stationary_contact | 首次进入后保持接触 | 接触基线也使用上升沿，不人为逐帧计分 |
| tracking_recovery | 丢失手肘，恢复时已伸手 | 断轨不桥接；重新收拳后才有合法攻击 |
| normal_left_right | 固定左右活动日程，先左后右 | 正常正例；各方法使用同一任务 |

这些场景用于规则与几何对比，不代表真实人体数据的准确率。生成报告见 `docs/EVALUATION.md`。
