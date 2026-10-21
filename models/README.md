# 姿态模型

使用 MediaPipe Pose Landmarker Lite（float16，模型版本 1）。权重不进入 Git。

```powershell
.venv\Scripts\python.exe scripts/download_pose_model.py
```

下载器仅访问 Google 官方模型地址，不覆盖已有模型，并生成来源、版本与 SHA-256 元信息。程序启动不会联网下载。

已核对的版本 1 文件大小为 5,777,746 bytes，SHA-256：
`59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`。
该摘要用于可复现性核对，不替代官方来源验证。相机录制元信息另保存实际加载模型的摘要。

模型及模型卡：[官方入口](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker#models)。使用、修改和分发前核对模型卡及对应许可；仓库不重新授权第三方模型。
