# 姿态模型

使用 Google MediaPipe Pose Landmarker（float16，版本 1），默认 **Full**。本机三种模型已下载，权重不进入 Git。

新环境按需下载；已有文件不会被覆盖：

```powershell
python scripts/download_pose_model.py --variant full
python scripts/download_pose_model.py --variant heavy
python scripts/download_pose_model.py --variant lite
```

下载器仅访问 Google 官方版本化地址，记录来源、版本与 SHA-256；程序启动不联网下载。相机识别可用 `--pose-model full`、`heavy` 或 `lite` 切换。

| 变体 | 用途 | 字节数 | SHA-256 |
| --- | --- | --- | --- |
| Lite | 轻量对比 | 5777746 | `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` |
| Full | 默认实时识别 | 9398198 | `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1` |
| Heavy | 较大模型对比 | 30664242 | `64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b` |

摘要用于可复现性核对，不替代官方来源验证；录制元信息保存实际加载模型的摘要。

模型及模型卡：[官方入口](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker#models)。使用和分发按对应模型许可，仓库不重新授权第三方模型。
