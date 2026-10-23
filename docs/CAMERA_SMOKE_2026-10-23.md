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

## LAB3 路线对照与 OpenCV 体验接入

复查 LAB2／LAB3 后确认：LAB2 的 Gemini 验收为红外预览；LAB3 第 42 页明确要求用 OpenCV 替换 pyorbbecsdk，现有 `scanner.py` 使用 `CAP_OBSENSOR` 和同一次 `grab()` 后的两次 `retrieve()`，未验证设备时间戳。

本机按相同读法成功获得 30 组 640×480 RGB／深度，3 次初始缺帧，约 1.13 s，不保存影像。这证明该路径可读帧，不证明同曝光同步。

用户同意增加独立的 `--source opencv-camera` 体验入口，原 `--source camera` 保持严格检查、没有自动降级。前者明确标注主机时间、同步未经验证和近似几何；像素／米转换、数据有效性、资源释放及来源记录均保留。依据 [OpenCV 4.11 采集实现](https://raw.githubusercontent.com/opencv/opencv/4.11.0/modules/videoio/src/cap_obsensor_capture.cpp) 和 [Gemini 2 默认参数实现](https://raw.githubusercontent.com/opencv/opencv/4.11.0/modules/videoio/src/cap_obsensor/obsensor_uvc_stream_channel.cpp)，其默认内参不能声称是本机独立校准结果。

实际双窗口运行约 90 s，2664 帧，666 帧有姿态输出；没有一帧满足完整双肩／双肘／双腕三维有效条件，因此引导保持 HOLD_GUARD，正式命中 0、分数 0。随后约 20 s 的逐关节诊断读入 600 帧，其中 39 帧有姿态结果：双肩置信度中位数约 0.99，双肘约 0.22，双腕约 0.09–0.12，并出现肘／腕出画。用户确认当前空间暂时无法同时拍到全部六个上肢关节，停止真人校准和击球测试；不是已通过的游戏验收。

双窗口和后续诊断均已结束，摄像头、模型、显示资源已释放。未保存原始 RGB／深度、骨架轨迹或人像截图；仅保留汇总记录。

审查前完整软件测试为 274 passed；独立只读审查发现一项 Important：RGB-D 转骨架并再次录制后，限制仍保存在嵌套来源信息里，但体验模式画面提醒可能消失。已用三段转录／回放链路的失败测试复现，再修复为沿来源链识别 OpenCV 体验模式。

最终完整软件测试 **275 passed，10.34 s，无跳过**，包含体验入口的十一个新增场景；`pip check`、`compileall`、wheel 构建及隔离安装的核心演示检查通过。wheel SHA-256 为 `3312969edd19ff6c45eba0df92a3ab88f734190b4766d2313c5ad3f60046c483`。软件测试不替代真人验收。

独立审查未发现 Critical，另有 12 项定向测试通过；未复跑全套或访问设备。其未判断硬件同步、实际标定精度、曝光时间、端到端延迟和真人计分，主开发同意这些仍须独立证据。修复后未再请求第二次审查，以上最终全套由主开发执行。

另已定位前述官方脚本未执行的一项原因：Windows PowerShell 5.1 的本机策略为 AllSigned，会拒绝未签名脚本；未更改或绕过该策略，也未继续尝试注册表写入。

## 验收边界

OpenCV 体验路径的连续读帧与实际窗口已检查，但 RGB-D 设备同步、每台设备的完整标定、连续完整上肢三维骨架、引导校准、真人有效出拳和命中计分尚未验收。上述项目不得因软件测试或画面可显示而标为通过。未运行付费服务，未上传人体数据，未推送代码。
