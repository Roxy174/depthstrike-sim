# 第三方依赖与模型

本项目实现交互系统，不声称提出新的骨架追踪或姿态估计算法。

| 组件 | 使用方式 | 来源 |
| --- | --- | --- |
| Orbbec Python SDK | RGB-D、同步、软件对齐、标定 | [官方仓库](https://github.com/orbbec/pyorbbecsdk/tree/v2-main) |
| MediaPipe Pose Landmarker | 预训练姿态检测与人体分割 | [官方文档及模型卡](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) |
| Open3D | 三维显示 | [官方文档](https://www.open3d.org/docs/release/) |
| OpenCV | 显式 LAB3 风格体验采集、图像解码、标定反投影与面板 | [官方文档](https://docs.opencv.org/4.x/) |
| NumPy / pytest | 数值计算与测试 | [NumPy](https://numpy.org/doc/) / [pytest](https://docs.pytest.org/) |

版本固定于 `pyproject.toml`，安装包、SDK 及模型各自保留其原有许可。模型从 Google 官方版本化地址显式下载，不随 Git 再分发。引用与使用不等于取得重新授权；团队发布二进制、模型或 SDK 文件前须核对对应分发条件。

演示轨迹、默认配置和测试夹具由本项目生成，不包含真实人像、付费素材或第三方角色模型。
