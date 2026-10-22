# Motion Studio 本地试做

版本 `0.3.0.dev0`。在既有 guided 流程上试验“动作生成关卡”和“三维局部反事实复盘”。以下命令在仓库根目录的 PowerShell 中运行，使用已有 `.venv`；依赖安装见 [运行说明](RUNNING.md)。

## 一键体验

```powershell
.venv\Scripts\python.exe -m depthstrike.studio demo --output outputs/studio-try
```

该命令生成一段合成作者动作、九靶关卡和带三处横向偏差的合成挑战者，随后显示挑战画面。回合结束后打开逐靶复盘窗口，默认选中第一个有局部修正的未命中。数据都是合成示例，不读取相机。

额外显示三维辅助场景：

```powershell
.venv\Scripts\python.exe -m depthstrike.studio demo --output outputs/studio-dual --view dual
```

挑战窗口：`Space` 暂停判定，`Q` / `Esc` 退出。回放来源在暂停判定期间仍继续读取；中断窗口不生成空间修正，需重新运行命令从头开始。回放中的 `R` 仅重新校准判定，并不倒带原始输入；固定录制演示建议重新启动。

复盘窗口：`A` / 左箭头、`D` / 右箭头切换靶位，`Space` 播放／暂停轨迹，`R` 从头播放当前轨迹，`Q` / `Esc` 关闭。

每次 demo 使用一个新目录，已有目录拒绝覆盖。默认参数下示例得到九靶、六次命中、三次空间未命中；三处偏差是预设的，不能作为算法准确率。

## 无窗口生成及再次查看

```powershell
.venv\Scripts\python.exe -m depthstrike.studio demo --output outputs/studio-batch --headless
.venv\Scripts\python.exe -m depthstrike.studio review --input outputs/studio-batch/review.json --trial 2
.venv\Scripts\python.exe -m depthstrike.studio review --input outputs/studio-batch/review.json --trial 2 --image outputs/studio-batch/review.png
```

无窗口链路只使用核心 NumPy；查看及 PNG 导出需要 OpenCV，dual 另需 Open3D。图片也采用独占创建。`--trial` 从 1 开始。

输出目录包括：

| 文件 | 内容 |
| --- | --- |
| author.jsonl | 原始合成骨架示范，含正常 guided 校准及完整收拳 |
| challenge.json | 身体相对靶位、峰值节奏、活动时间窗及作者来源 |
| player.jsonl | 同源合成挑战者，正式回合第 2、5、8 靶加入横向偏差 |
| review.json | 逐靶结果、原始轨迹、最近点、可选局部修正及实际挑战者校准尺度 |

## 自己的录制转关卡

输入须包含完整 guided 校准、试击、倒计时，以及正式回合中至少一拳有效出拳并收回。只截取出拳片段的旧文件不满足要求。

```powershell
.venv\Scripts\python.exe -m depthstrike.studio author --input recordings/guided-session.jsonl --output outputs/my-challenge.json
.venv\Scripts\python.exe -m depthstrike --source replay --input recordings/guided-session.jsonl --challenge outputs/my-challenge.json --review-output outputs/my-review.json
```

后续相机接入可使用同一关卡入口：

```powershell
.venv\Scripts\python.exe -m depthstrike --source camera --challenge outputs/my-challenge.json --review-output outputs/camera-review.json
```

相机入口复用了既有采集流程，本轮未作真实 Gemini 2／人体测试。

提取过程重新计算拳心和攻击状态，不读取录制 events 作为标签。只收录正式阶段中完成收回的攻击；失效、暂停或长间隔打断的攻击舍弃。正式阶段出现 reset 须先拆分文件；暂不支持同时出拳或超过 32 靶／120 s 的长关卡。

关卡以作者参考肩部为原点，x/y 按肩宽归一化，z 按该手舒适前伸量归一化。挑战者完成自己的校准后反变换一次，靶位固定于相机空间。映射时检查有效深度、中立拳心分离和舒适触达距离；检查失败直接报告，不自动扩大目标或移动靶位。

## 复盘含义

- `hit`：有效出拳在活动时间窗内发生观测到的接触进入。
- `miss / spatial_miss`：窗口完整可观测且有有效攻击，但有效轨迹未接触目标。
- `miss / no_valid_attack`：没有可结算的有效出拳；慢伸手、未收拳或同次攻击已得分均不会得到空间修正。
- `unobserved`：窗口内观测不完整，不能将失败归因于玩家。
- `incomplete`：退出／EOF 时该窗口尚未结束；不按未命中统计。

正面图使用相机 X/Y，侧面图使用 Z/Y。蓝色为观测轨迹；绿色实圈为目标球，浅圈为目标半径加拳心半径的接触范围；紫色为局部修正段。图上的轨迹是拳心代理中心，不是人体表面网格。

局部修正将最近的有效线段向球心平移，加入 1 mm 接触余量。两端需满足深度和测得触达球约束，并重新进行连续碰撞核验。它仅表示固定时机与攻击状态下的局部几何接触；不生成完整人体动作，不证明关节可执行性，也不评价专业拳击动作。没有满足约束的局部修正时保留空值。

生成关卡属于派生内容，不是独立标注真值；作者自回放命中不能证明真实定位精度。跨体型体验效果、反馈是否改善学习以及真实遮挡表现仍需另行采样和用户实验。
