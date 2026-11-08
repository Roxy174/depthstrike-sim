# 第三方依赖与模型

本项目实现交互系统，不声称提出新的骨架追踪或姿态估计算法。

| 组件 | 使用方式 | 来源 |
| --- | --- | --- |
| Orbbec Python SDK（pyorbbecsdk2 2.1.2） | Gemini 2 RGB-D、同步、软件对齐、标定 | [官方仓库](https://github.com/orbbec/pyorbbecsdk/tree/v2-main) |
| Orbbec OpenNI SDK 2.3.0.86 beta6 | 旧款 Astra 深度、出厂配准及标定；按官方 C 头文件使用 ctypes 绑定 | [官方 SDK 与驱动](https://www.orbbec.com/developers/openni-sdk/) / [官方文档仓库](https://github.com/orbbec/OpenNI_SDK) |
| cv2-enumerate-cameras 1.1.14 | 按 VID/PID 选择 Astra 独立彩色接口 | [项目源码](https://github.com/lukehugh/cv2_enumerate_cameras) |
| MediaPipe Pose Landmarker Full／Heavy／Lite | 预训练姿态检测与人体分割，默认 Full | [官方文档及模型卡](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) |
| Open3D | 三维显示 | [官方文档](https://www.open3d.org/docs/release/) |
| OpenCV | 显式 LAB3 风格体验采集、图像解码、标定反投影与面板 | [官方文档](https://docs.opencv.org/4.x/) |
| Pillow | 中文界面字体栅格化，使用操作系统提供的中文字体 | [官方文档](https://pillow.readthedocs.io/) |
| NumPy / pytest | 数值计算与测试 | [NumPy](https://numpy.org/doc/) / [pytest](https://docs.pytest.org/) |

Gemini 2 的 SDK／固件支持范围见 [官方兼容表](https://orbbec.github.io/pyorbbecsdk/source/1_overview/Introduction.html)。旧款 Astra 保留独立 OpenNI 后端，两套依赖可在同一 Python 环境中使用。

版本固定于 `pyproject.toml`，安装包、SDK 及模型各自保留其原有许可。模型从 Google 官方版本化地址显式下载，不随 Git 再分发。引用与使用不等于取得重新授权；团队发布二进制、模型或 SDK 文件前须核对对应分发条件。

演示轨迹、默认配置和测试夹具由本项目生成，不包含真实人像、付费素材或第三方角色模型。

## 程序化角色

上半身卡通角色由项目代码生成网格和轮廓，未使用外部角色模型、贴图或骨骼资源。主画面使用现有 OpenCV 绘制，立体窗口使用现有 Open3D 依赖。
