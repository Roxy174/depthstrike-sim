# Gemini 2 实机接入检查

日期：2026-10-23。当前分支 `codex/motion-challenge-prototype`。本次以实际连接设备检查采集适配，不保存或上传彩色／深度影像，也不录制骨架。设备注册与人体交互验收分开记录。

## 已确认

- SDK 枚举到一台 Orbbec Gemini 2，固件 `1.4.87`，连接类型 `USB3.0`。未升级固件。
- 当前环境：Python 3.12、pyorbbecsdk2 2.1.2、MediaPipe 0.10.32、OpenCV 4.11.0.86；官方 pose lite 模型可加载。
- 普通受限执行环境打开设备曾返回拒绝访问；经允许在沙箱外运行后设备可打开。这不等同于 Windows 隐私开关被关闭，未修改隐私设置。
- 彩色原始流 640×480@30、深度原始流 1280×800@30；软件 D2C 后 RGB 和深度均为 640×480。一次样本非零深度比例约 99.27%，不是人体关节有效率或定位精度。

## K6 标定兼容修复

实际彩色标定模型为 `OBCameraDistortionModel.BROWN_CONRADY_K6`，原采集适配只接受 `BROWN_CONRADY`，导致首帧转换失败。用户已同意修复。

该型号按八系数有理模型归一为内部 `brown_conrady`，不丢弃 k4、k5、k6，也不按无畸变近似。依据为 [Orbbec 原生坐标变换实现](https://raw.githubusercontent.com/orbbec/OrbbecSDK_v2/main/src/shared/utils/CoordinateUtil.cpp)、[SDK 枚举定义](https://orbbec.github.io/pyorbbecsdk/source/6_API_Reference/data_structures.html) 和 [OpenCV 标定模型](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)。

在本机已安装 SDK 中，以同一彩色相机的恒等外参做原生 2D→2D 去畸变，再做 2D→3D；与现有 OpenCV 八系数反投影比较五个像素位置：中心、两个中间位置和两个近边缘位置。在假定深度 1 m 下，最大三维计算差约 `1.34e-6 m`。这仅是计算路径的一致性检查，不是实测绝对精度。

回归测试覆盖两种 K6 枚举拼写、系数顺序和独立手算有理投影的反投影；逆 Brown／鱼眼模型仍拒绝。修复前 2 failed／20 passed，修复后适配与融合专项通过。

## 当前实机阻塞：零设备时间戳

兼容修复后运行原生 `CameraPoseSource` 约 12 s，仅接受首帧，后续 370 次被拒绝，未完成连续人体检测。单帧无人体结果不能用于评价检测模型。

进一步直接检查 24 组实际帧：帧序号递增，但 RGB、深度在对齐前后的设备毫秒／微秒时间戳均为 0。主机到达时间递增且两流存在约 85 ms 到达差，但它不是曝光时间，不能用来声称采集同步。

只读注册表检查发现当前连接相机各 UVC 接口缺少 `MetadataBufferSizeInKB0`。这与 [Orbbec 官方 Windows 元数据／时间戳说明](https://orbbec.github.io/pyorbbecsdk/source/7_FAQ/FAQ.html) 一致。程序现已对零设备时间戳给出注册 UVC 元数据的明确错误，不将 0／0 当作同步成功；该行为先由三个失败回归场景复现后修复。

用户已同意仅为当前连接设备运行官方元数据注册脚本。脚本需 Windows 管理员确认；启动或正常退出不能替代读回验证。注册项生效后还需重新插拔和重测，不改变固件、执行策略或隐私设置。

本次首次启动脚本后，读回仍见当前六个接口的元数据值缺失；带日志的管理员启动随后由 Windows 返回“操作已被用户取消”。因此停止重试，注册未通过验收，需用户在管理员终端完成后再测。

## 软件验证

`DEPTHSTRIKE_GUI_TESTS=1` 下完整测试为 **264 passed，13.09 s，无跳过**；`pip check` 无依赖冲突。新增七个场景保护 K6 适配、系数处理、其他模型拒绝及零设备时间戳拒绝。这不是硬件或真人验收结果。

## 验收边界

尚未确认连续有效 RGB-D、连续完整上肢三维骨架、引导校准、真人有效出拳和命中计分。上述项目不得因软件测试或单帧读入而标为通过。未运行付费服务，未上传人体数据，未推送代码。
