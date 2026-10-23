# 扩展验证记录 · 2026-10-23

环境：项目 `.venv`，Windows / Python 3.12。根目录本地工作树改动；本轮未运行摄像头、下载模型或推送远程。

## 软件验证

- 新增 `tests/test_adaptive.py`：深度空洞恢复、背景拒绝、来源往返、有限显示预测、One Euro、Kalman 质量加权、缺键失踪、单侧校准、局部击球、恢复禁止跨帧命中、工作空间拒绝、深度遮挡、预览、模型选择、正式回合故障注入，以及动作作者/评估一致性。
- 各批新增用例在实现前运行失败，再实现运行通过。
- 首次完整显示验证：`DEPTHSTRIKE_GUI_TESTS=1`，298 passed，21.86 s。
- 独立审查发现3项 Important，已用回归用例复现并修复；修复阶段完整验证302 passed，24.52 s。补充作者代理来源切换回归后，最终结果附后。
- 最终完整验证：`DEPTHSTRIKE_GUI_TESTS=1`，`pytest -q --basetemp=tmp/pytest-adaptive-verified --tb=short` → **303 passed in 23.03 s**，0 skipped。
- `compileall` 和 `pip check` 通过；`git diff --check` 无空白错误，仅提示已有文件的 LF/CRLF 转换。

## 独立审查

只读审查 `/root/adaptive_review` 针对修复前快照，没有启动相机。三项发现：

1. partial_tracking 下作者会跨失踪片段完成 pending 动作。修复为完整观测检查，并在交互点来源变化时取消待完成动作。
2. evaluation 固定使用肘腕代理，忽略 hand 配置。修复为与实时模拟共享 `estimate_hand`，来源切换中断接触历史，输入指纹包括来源与质量字段。
3. Kalman 未清除空关节字典中的历史，会制造虚假恢复运动。修复为缺键与显式无效相同处理，显示预测仍与观测独立。

未发现 Critical/Minor。最终修复由回归及全仓测试核验，没有第二轮审查。实机准确率、不同身体部位身份、模型性能、同步和连续空间覆盖不在这份合成证据中作结论。

## 可重复演示

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo --config configs/adaptive.json --headless --frames 600
.venv\Scripts\python.exe -m depthstrike.robustness --output outputs/my-adaptive-report.json --image outputs/my-adaptive-preview.png
```

第一条实测600帧、9次正式命中、90分、0采集超时。第二条需要新输出路径；本轮输出见 `outputs/adaptive-20261023-final/`（本地忽略文件，不进 Git）。

正式回合11–12秒注入故障，默认/扩展均使用600帧。正常均9次命中；非活动右肘丢失时默认7次、扩展9次；活动左腕丢失时均7次。扩展显示3帧短时预测，没有把预测作为观测补记得分。左右腕交换仍是已知失败边界，未接身份恢复模型。

局部深度合成探针30次：默认中心空洞恢复0次，掩膜+匹配历史恢复30次；与历史深度不一致时两种策略均拒绝30次。输入为手工构造的一致表面，不是人体定位准确率。

## 本轮边界

路径检查只拒绝不可用布局，不自动重新排靶、不建完整房间地图；粗采样不能证明整个体积无障碍。Full/Heavy 仅提供显式下载选择，RTMPose/CoTracker3/IK 尚未集成。真人追踪效果继续等待后续实测。
