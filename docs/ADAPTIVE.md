# 可观测性驱动的交互扩展

Python 本地扩展，仍使用既有依赖。真人、空间精度与真实遮挡效果尚未验收；以下报告只验证合成输入下的软件行为。

## 启动

在 `D:\3D视觉` 的 PowerShell 中运行：

```powershell
.venv\Scripts\python.exe -m depthstrike --source demo --config configs/adaptive.json --view dual
.venv\Scripts\python.exe -m depthstrike --source demo --config configs/adaptive.json --headless --frames 600
```

演示自动完成校准和击球，不使用相机。合成输入没有 RGB-D 场景，因此不进行真实障碍检查，也不显示真实深度遮挡。

恢复真人测试后，体验入口可显式使用同一配置：

```powershell
.venv\Scripts\python.exe -m depthstrike --source opencv-camera --config configs/adaptive.json
```

OpenCV 后端仍是主机时间、型号默认内参和未验证 RGB-D 同步；不能用体验入口证明空间精度。默认配置继续使用完整双侧观测协议，`adaptive.json` 才启用局部交互。

## 技术行为

| 组件 | 实现与边界 |
| --- | --- |
| 掩膜深度融合 | 5×5 局部窗口，保留深度有效比例、表面离散度检查；中心空洞额外要求同名的近期直接观测。恢复点不能继续充当下一次空洞恢复的历史锚点。人体掩膜不区分不同身体部位，因此仍可能存在同深度表面歧义。 |
| 手部交互点 | 优先使用腕、食指、小指的有效观测，指点距腕不得超过 0.20 m；缺失时回退肘腕代理。来源改变取消当前攻击，需重新收拳。该点是表面交互代理。 |
| 滤波 | `exponential`、`one_euro`、`kalman` 可选。One Euro 根据速度改变截止频率；Kalman 使用位置—速度状态，按置信度和深度质量调节观测噪声。质量分数是工程权重，不是已标定概率。 |
| 显示预测 | 只在 adaptive 的局部追踪启用；最多预测 0.12 s，速度上限 5 m/s，可信度随缺失时间下降。HUD 空心灰点、三维灰线与观测分开。没有新的有效点时不延长预测，不进入碰撞。 |
| 逐侧校准 | 初始收拳仍需双侧肩部和交互点；前伸、收回、试击分别检查当前侧。对侧肩部若仍可见，继续检查站位偏移。丢点仅重置当前稳定采样段，保留已经完成的校准阶段。 |
| 局部击球 | 普通回合按活动手有效性计时和判定，另一侧缺失不清除当前侧攻击。活动手缺失后重现不能跨缺口计分。Motion Studio 挑战继续要求完整观测。 |
| 目标预览 | 校准期间根据肩部显示 `PREVIEW` 目标；不参与碰撞，正式目标仍需通过舒适触达校准。 |
| 深度遮挡 | 按相机射线与虚拟球体前表面求交，前方实测表面遮住虚拟球；无效深度保守不绘制该像素。只影响绘制，不改变计分几何。 |
| 路径检查 | 校准生成目标时，沿中立拳心到目标的路径按约 2 cm 步长采样中心与六个轴向偏移。初始手部占据体积被排除；遇到遮挡表面拒绝、超视野或缺深度返回未知。目标生成后固定，不在出拳途中移动。 |

路径检查仅使用当前视野的粗略采样，不是完整占据地图、连续体积碰撞证明或人身安全认证。桌面/墙面的语义识别、场景建图和自动重排目标不包含在此实现中。SDK 和 OpenCV 的几何证据限制随输入保留。

`Joint3D` 记录 `provenance`、`depth_quality`、`age_s`。旧 JSONL 缺少这些字段时按旧观测语义读取；新文件保留来源，标为 `predicted` 的输入在追踪边界被拒绝为物理观测。显示预测不写入原始骨架录制。

## 离线故障报告

```powershell
.venv\Scripts\python.exe -m depthstrike.robustness --output outputs/adaptive-report.json --image outputs/adaptive-preview.png
```

文件已存在时拒绝覆盖，请换新名称。核心报告仅依赖 NumPy；PNG 需要 OpenCV，不打开窗口。

报告比较默认与扩展配置的 600 帧合成序列：正常、左腕遮挡、右肘遮挡、左右腕交换、时间倒退；另比较中心深度空洞恢复和不匹配历史深度的拒绝。命中数只是该输入下的实际结果，没有独立真值标签，不作为准确率；腕交换用来暴露失败边界，尚无身份重识别模型。

对三种滤波方案进行进一步实验时，创建新的 JSON 配置并设置 `filter_mode`。不要同时串联多个滤波器；比较相同输入下的抖动、响应滞后、有效覆盖和错误接触。真实肢体定位须使用图像级数据与独立参考。

## 姿态模型对比入口

仅在准备比较时显式下载，不在程序启动时联网：

```powershell
.venv\Scripts\python.exe scripts/download_pose_model.py --variant full
.venv\Scripts\python.exe scripts/download_pose_model.py --variant heavy
```

默认仍为 lite。脚本使用 Google 官方版本 1 端点，保留 SHA256、变体与 URL，已有模型或 sidecar 不覆盖。在新的 JSON 配置中设置：

```json
{
  "model_path": "models/pose_landmarker_full.task",
  "fusion_mode": "masked",
  "fist_mode": "hand",
  "filter_mode": "one_euro",
  "partial_tracking": true,
  "preview_targets": true
}
```

模型选择接口已测试，本轮没有下载 Full/Heavy 或比较真实推理性能。RTMPose、CoTracker3、学习式三维补全与骨架逆运动学仍属后续备选，未作为依赖接入。
