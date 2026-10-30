# 旧款 Astra 接入

本入口支持本机实测的 Astra：OpenNI 深度接口 USB `2bc5:060f`，独立 UVC 彩色接口 `2bc5:050f`。其他 Astra 型号的协议和固件可能不同，不根据产品系列名称自动选用此适配器。

本次设备与运行证据见 [2026-10-31 验证记录](ASTRA_VERIFICATION_2026-10-31.md)。

## 运行

本机已建立 Python 3.12 的 `depthstrike` 环境，安装官方深度驱动、OpenNI 运行库和姿态模型。在项目根目录的 PowerShell 中执行：

```powershell
& "$env:USERPROFILE\.conda\envs\depthstrike\python.exe" -m depthstrike --source astra-camera --config configs/adaptive.json
```

增加 `--view dual` 显示三维辅助窗口。`空格` 暂停/继续，`R` 重新校准，`Q` / `Esc` 退出；关闭窗口会释放两个采集接口。窗口标题为“深度拳击｜体感交互”，来源提示为“奥比中光相机体验｜主机计时｜出厂深度对齐”。

调整取景，使双肩、双肘、双腕在画面内，按引导完成收拳、左右舒适前伸、收回、试击和倒计时。追踪条件不足时保留校准提示。所有关节置信度、深度质量和攻击阈值沿用现有配置。

## 在其他电脑准备环境

Python 3.12，Windows x64：

```powershell
python -m pip install -e ".[display,astra]"
python scripts/download_pose_model.py
```

安装适合设备的 [Orbbec 官方 Astra 驱动](https://www.orbbec.com/developers/openni-sdk/)。本机使用 4.3.0.22；安装后检查设备管理器中的 `ORBBEC Depth Sensor` 是否正常。安装器与内核驱动的签名不同：本次安装器无 Authenticode 签名，安装后的深度驱动由 Windows 报告为已签名。驱动安装由用户明确授权并通过交互安装器完成；应用启动不自动安装驱动或更改固件。

从同一官方页面下载 OpenNI SDK 2.3.0.86 beta6，解开外层及内层 ZIP，将 `Win64-Release/sdk/libs/` 的内容放入 `.cache/openni2/`，保留目录结构：

```text
.cache/openni2/
  OpenNI2.dll
  OpenNI2/Drivers/orbbec.dll
  OpenNI2/Drivers/orbbec.ini
  ...
```

也可通过 `--openni-dir PATH` 指定这些文件所在的目录。适配器的 C 结构布局按该版官方头文件绑定，启动时拒绝其他 SDK 版本。运行库与模型不纳入 Git 历史，分发前应核对原有许可。

## 数据与验证口径

- 深度使用 OpenNI `DEPTH_1_MM`，640×480、30 fps；读取前关闭深度镜像，开启深度到彩色配准并读回确认。每帧检查格式、裁剪、步长及缓冲区大小，拷贝后立即释放原生帧。
- 彩色使用 DirectShow，按 VID/PID 精确选择 Astra UVC 接口；多台匹配设备会报错。彩色为 640×480 BGR，转换为 RGB；深度毫米转换为米。错误尺寸会失败，不通过缩放深度图凑尺寸。
- 反投影及显示使用设备返回的彩色内参和五个 Brown–Conrady 畸变系数；出厂配准的实际空间精度尚未独立测量。
- 两个接口没有经过独立曝光同步验证。采样时间为两次主机读取完成时间的中点，只检查完成时间差不超过 `frame_sync_tolerance_s`；该限制不能证明曝光同步，也不是传感器到显示延迟。原生深度时间戳和帧号另行检查严格递增。
- 来源固定保留 `capture_backend=openni2_astra_uvc`、`evidence=unverified`。限制随 RGB-D/骨架转录和回放传递，画面继续显示体验模式提示。
- 默认不保存图像或人体轨迹。显式使用 `--record` / `--record-rgbd` 才录制；软件阶段统计可单独使用 `--metrics`。

这属于真实传感器输入下的体验入口。连续人体校准、真人命中计分、同步性能和定位准确率分别验收，不能用程序成功读帧替代这些结论。
