# RK3588 + RK1828 项目简历素材采集文档

> 更新时间：2026-09-23
>
> 用途：集中保存项目事实、量化结果、个人贡献、简历候选表述及面试素材。
> 原则：真机验证内容写成“实现/达到”；原型功能写成“设计/搭建”；未验收功能标记为“待验收”。

## 1. 项目基本信息

### 推荐项目名称

**RK3588 + RK1828 异构边缘多模态推理平台**

备选名称：

- 基于 RKNN3 的端侧异构多模态大模型推理平台
- RK3588/RK1828 双 NPU 多模态智能终端
- 面向边缘设备的多模态大模型与实时视觉协同推理系统

### 项目定位

在 RK3588 主控板上构建常驻 Web 推理平台，通过 PCIe 使用 RK1828 加速多模态大模型；RK3588 同时承担摄像头采集、视觉小模型、音视频处理、Web 服务、任务调度与系统监控。项目覆盖模型部署、推理服务化、多会话 KV Cache、异构调度、双摄视觉链路、性能测试和故障恢复。

### 技术栈

| 分类 | 技术 |
| --- | --- |
| 硬件 | RK3588、RK1828、PCIe、双 IMX415、CSI、M.2 |
| 大模型 | Qwen2.5-Omni-3B、RKNN3 Runtime、Tokenizer、Embedding、KV Cache |
| RK3588 视觉 | RKNN、YOLOv5、V4L2、RKISP、RGA、MPP、RTSP、WebRTC |
| 后端 | C++、Python、FastAPI、Unix Domain Socket、SSE、WebSocket、SQLite |
| 前端 | React、TypeScript、Vite |
| 工程化 | CMake、交叉编译、Nginx、Linux init 脚本、Git、自动实验记录 |

## 2. 系统架构事实

### 设备职责

| 设备 | 已承担职责 |
| --- | --- |
| RK3588 | 系统主控、Web/API、请求编排、文件上传、摄像头采集、RGA/MPP 视频处理、RK3588 NPU YOLO、监控与实验记录 |
| RK1828 | 通过 PCIe 连接，运行 RKNN3 多模态大模型 Session，承担 Vision Encoder 和 LLM Prefill/Decode |
| 浏览器 | 文本/图片/音频输入、Token 流式输出、会话管理、摄像头预览、系统与模型状态展示 |

### 主要数据流

```text
浏览器 -> FastAPI -> Unix Domain Socket -> C++ inference-daemon
       -> RKNN3 Session -> PCIe -> RK1828 Vision Encoder / LLM
       -> Token 事件 -> SSE -> 浏览器

IMX415 x2 -> CSI / RKISP / V4L2 -> RGA
           -> RK3588 NPU YOLO 或 MPP 编码 -> RTSP / WebRTC / Web 页面
```

### 已实现的软件分层

- C++ `inference-daemon` 管理 RKNN3 模型、Session 和性能关键路径。
- Python/FastAPI 管理 Web API、会话元数据、附件、工具调用和实验编排。
- React/TypeScript 提供多模态对话、摄像头及设备监控页面。
- 推理服务与 Web 服务通过 Unix Domain Socket 隔离。
- SQLite 保存会话、审计和实验索引，大文件保存在独立目录。
- 双摄视觉服务与 RK1828 推理服务生命周期隔离。

## 3. 个人工作与技术贡献素材

### 3.1 多模态大模型部署

- 在 RK3588 + PCIe RK1828 真机环境完成 Qwen2.5-Omni-3B 的 RKNN3 部署。
- 验证文本、图像、音频和图音联合输入链路。
- 拆分并记录图片读取、图像预处理、Vision Encoder、Embedding、LLM TTFT、TPOT、Decode TPS 和端到端延迟。
- 修复无效图片路径导致厂商图片库退出、浏览器 WebM 与模型 WAV 输入不兼容、联合输入只读取首个附件等问题。
- 区分模型输入 Token、用户文字 Token、视觉 Token及模板/控制序列净开销，避免错误解释实验数据。

### 3.2 常驻服务与 KV Cache

- 将一次性命令行 Demo 重构为 C++ 常驻推理服务，模型在进程启动阶段加载一次。
- 使用 `conversation_id -> RKNN3 Session` 管理独立会话，实现真实 KV Cache 复用。
- 完成最多四个常驻 Session、容量保护、清理和错误隔离。
- 修复守护进程 SIGTERM 后阻塞在 `accept()`、热更新导致新 Context 初始化失败的问题。
- 验证 KV 主要降低 Prefill/TTFT，对 Decode TPOT 影响很小。

### 3.3 Web 多模态控制台

- 使用 FastAPI + React + TypeScript 实现局域网 Web 控制台。
- 支持文本、图片、浏览器录音、Token SSE 流式输出、停止生成和多会话切换。
- 使用 WebSocket 推送 RK3588 CPU、内存、温度、NPU 状态，以及 RK1828 在线状态和推理阶段。
- 展示当前模型、量化方式、上下文上限、KV 状态及请求阶段指标。
- 实现白名单工具注册和参数校验，不向模型开放任意 Shell；有影响操作保留确认与审计接口。

### 3.4 双摄与实时视觉

- 接入两路 IMX415，完成 V4L2/CSI/RKISP 设备绑定和 RK3588 NPU YOLO 链路。
- 实现摄像头选择、独立 ROI 控制、检测/追踪开关、截图进入对话框等页面功能。
- 基于 RGA、MPP、RTSP/WebRTC 构建浏览器预览链路，并实现 USB MJPEG 安全降级。
- 设计“Camera 0 全局搜索 -> 跨摄确认 -> Camera 1 硬件 ROI -> 丢失重捕获”状态机和 Web 控制接口。
- 通过服务互斥、设备图核验、九点标定门禁和失败回滚避免错误切换 Sensor ROI。

### 3.5 性能测试与问题定位

- 建立 `manifest.yaml + raw.jsonl + metrics.csv + system.csv + summary.md` 的可复现实验目录。
- 对 KV 复用、上下文长度、Session 数量、摄像头负载和视觉链路进行对照实验。
- 使用单变量方法隔离双摄运动场景卡死问题，分别测试传感器、双路采集、YOLO、HDMI、RGA 和 MPP。
- 发现双路 MPP MJPEG 30 秒产生 647 条 RGA/RKVDEC 错误，切换为 CPU MJPEG 后相同测试新增错误为 0。
- 明确“配置 FPS、采集 FPS、编码 FPS、浏览器呈现 FPS”是四种不同口径，禁止用配置值冒充实测值。

## 4. 已验证量化结果

### 4.1 四会话 100 次压力测试

| 指标 | 结果 |
| --- | ---: |
| 总请求 | 100 |
| 请求成功率 | 100% |
| KV 召回正确 | 80/80 |
| 会话串话 | 0 |
| Session 清理成功 | 20/20 |
| 全部请求 TTFT P50 / P95 | 96.94 / 183.40 ms |
| 平均 Decode TPS | 84.49 token/s |
| KV 召回相对首轮平均 LLM TTFT 降低 | 46.7% |

### 4.2 30 分钟四会话稳态实验

| 指标 | 结果 |
| --- | ---: |
| 有效推理 | 360 次 |
| 正确率 | 100% |
| 错误 / 会话串话 | 0 / 0 |
| Prime TTFT P50 / P95 | 179.28 / 185.68 ms |
| KV Recall TTFT P50 / P95 | 95.11 / 96.89 ms |
| Prime 端到端 TTFT P50 | 264.65 ms |
| KV Recall 端到端 TTFT P50 | 101.59 ms |
| KV 复用带来的端到端 TTFT P50 降幅 | 61.6% |
| Recall Decode TPS 均值 | 87.82 token/s |
| 板端温度均值 / 最大值 | 37.14 / 37.92 °C |

实验同时运行单路约 60 FPS 摄像头采集和 5 FPS YOLO；采集丢帧、超时和重连均为 0。该结论只适用于当时的单摄配置。

### 4.3 摄像头负载对 RK1828 推理的影响

| 指标 | Camera + YOLO | 关闭采集与 YOLO | 差异 |
| --- | ---: | ---: | ---: |
| Recall TTFT P50 | 95.110 ms | 94.973 ms | -0.14% |
| Recall TTFT P95 | 96.895 ms | 96.445 ms | -0.46% |
| Decode TPS 均值 | 87.823 | 89.385 | +1.78% |
| 视觉服务 CPU 均值 | 52.53% | 27.23% | -25.30 个百分点 |
| 温度均值 | 37.14 °C | 34.42 °C | -2.73 °C |

可支持的结论：RK3588 单摄采集与 5 FPS YOLO 对 RK1828 文本推理 TTFT 的影响小于 0.5%，但会明显增加 RK3588 CPU 和温度。

### 4.4 上下文扩展实验

| 实际输入 Token | 最大上下文配置 | LLM TTFT 均值 | Prefill TPS 均值 | TPOT 均值 |
| ---: | ---: | ---: | ---: | ---: |
| 650 | 1024 | 594.32 ms | 1093.96 | 13.09 ms |
| 650 | 2048 | 590.01 ms | 1101.68 | 12.99 ms |
| 650 | 4096 | 594.36 ms | 1093.64 | 13.02 ms |
| 1650 | 2048 | 1443.17 ms | 1143.34 | 13.08 ms |
| 3650 | 4096 | 3191.33 ms | 1143.75 | 13.67 ms |

结论：长输入 Prefill 吞吐约 1143 token/s，TTFT 随实际输入长度近似线性增长。但当前模型 KV Buffer 只编译到 1024，不能将长单轮 Prefill 成功描述成“完整支持 4096 多轮 KV”。

### 4.5 图像端到端指标口径验收

| 指标 | 单次验收结果 |
| --- | ---: |
| 原始 Prompt / 纯用户文字 | 11 / 8 Token |
| Vision Token | 196 |
| RKNN3 实际输入 | 246 Token |
| 模板及控制序列净开销 | 42 Token |
| 图片读取 | 46.85 ms |
| 图像预处理 | 5.72 ms |
| Vision 总计 | 232.35 ms |
| LLM TTFT | 306.55 ms |
| 端到端 TTFT | 685.90 ms |
| TPOT | 15.81 ms |
| Decode TPS | 63.25 token/s |

该组用于验证计时和 Token 口径，只是单次结果，不应在简历中写成统计均值。

### 4.6 双摄稳定性边界

- Camera 0 单路、Camera 1 单路以及双路纯采集/检测的 30 秒运动测试均无新增内核错误。
- `HDMI 720p15 + Mosaic 720p15 + 两路 Focus 720p30` 的分阶段运动测试通过。
- `双路 Focus 720p60` 即使关闭 HDMI 和 Mosaic 仍会导致媒体路径阻塞，当前不得宣称已实现稳定双路 60 FPS WebRTC。
- 双摄高速硬件 ROI 的状态机、接口和安全门禁已经完成，但九点映射验证、20 次切换和 30 分钟稳定性验收尚未完成。

## 5. 一页简历候选版本

### 通用版本

**RK3588 + RK1828 异构边缘多模态推理平台**

技术栈：C++、Python、FastAPI、React、RKNN3、PCIe、V4L2、RGA、MPP、WebRTC

- 在 RK3588 + PCIe RK1828 上完成 Qwen2.5-Omni-3B 端侧部署，将一次性 Demo 重构为 C++ 常驻推理服务，实现文本、图像、音频及联合输入。
- 基于独立 RKNN3 Session 实现四会话 KV Cache 隔离；100 次压力测试成功率 100%、串话 0 次，KV 复用使平均 LLM TTFT 降低 46.7%。
- 开发 FastAPI + React 多模态 Web 控制台，实现 SSE Token 流式输出、会话管理、模型上下文和 RK3588/RK1828 状态监控。
- 建立可复现性能实验体系；30 分钟完成 360 次推理且正确率 100%，KV Recall TTFT P50 为 95.11 ms，Decode 吞吐约 87.82 token/s。
- 基于 V4L2/RKISP/RGA/MPP 搭建双 IMX415 视觉链路，通过单变量实验定位双路高帧率 RGA/MPP 阻塞边界，并实现服务互斥、预检和失败回滚。

### 偏嵌入式 Linux/AI 部署岗位

- 完成 RK3588 与 RK1828 PCIe 异构平台搭建，适配 RKNN3 Runtime、模型加载、Session 生命周期和板端服务管理。
- 基于 V4L2、RKISP、RGA 和 MPP 搭建双路 IMX415 采集与编码链路，定位运动场景下 DMA/RGA/MPP 并发阻塞问题。
- 使用 C++ 常驻进程和 Unix Domain Socket 隔离推理生命周期，通过服务互斥、设备图核验、超时检测和失败回滚提升系统稳定性。
- 建立交叉编译、板端部署、自动测试和可复现实验流程，保存固件、模型哈希、配置、原始指标和系统时间序列。

### 偏大模型部署/推理优化岗位

- 将 Qwen2.5-Omni-3B 部署到 RK1828，拆分 Vision Encoder、Embedding、Prefill、TTFT、TPOT 和 Decode TPS 指标。
- 设计四 Session KV Cache 隔离和容量保护；100 次压力测试零错误、零串话，KV 召回平均 TTFT 相对首轮降低 46.7%。
- 完成 650–3650 Token 的上下文扩展实验，测得长输入 Prefill 吞吐约 1143 token/s，并识别运行时上下文配置与模型编译 KV 容量不一致的问题。
- 量化 RK3588 摄像头/YOLO 与 RK1828 大模型并行运行的干扰，单摄负载下 Recall TTFT P50/P95 变化均小于 0.5%。

## 6. 面试讲述素材

### 30 秒版本

这是一个 RK3588 和 RK1828 组成的异构边缘多模态平台。RK3588 负责 Web、摄像头、音视频处理和任务调度，RK1828 通过 PCIe 运行 Qwen2.5-Omni。我把原有一次性 Demo 改造成常驻 C++ 推理服务，完成了多会话 KV Cache、流式 Web 对话和系统监控。真机 100 次四会话压力测试零错误、零串话，KV 复用让平均 LLM TTFT 降低约 46.7%。

### 90 秒版本

项目的目标是在资源受限的边缘设备上同时运行多模态大模型和实时视觉任务。架构上，RK3588 负责摄像头采集、RGA/MPP、YOLO、FastAPI 和 React 页面，RK1828 专门运行 Vision Encoder 与 LLM。为了避免每次请求重复加载模型，我把命令行 Demo 重构成 C++ 常驻守护进程，并用 Unix Socket 与 Web 层解耦。每个会话对应独立 RKNN3 Session，通过四会话压力实验验证了 KV 不串话，100 次请求全部成功。性能方面，30 分钟完成 360 次推理，KV Recall TTFT P50 约 95 ms，Decode 约 88 token/s。项目中最难的问题是双路高帧率视频会把 RGA/MPP 驱动路径拖死，我使用单变量方法依次关闭检测、显示和编码，确认问题来自双路 60 FPS Focus 管线，并建立安全配置、禁止自启和失败回滚机制。

### STAR 故障案例

**Situation：** 双摄页面在快速运动约 5 秒后黑屏，随后网口失联，ADB 只能识别设备但不能执行 shell。

**Task：** 判断问题来自传感器、YOLO、RGA、MPP、HDMI 还是 WebRTC，并恢复可重复测试环境。

**Action：** 禁止视觉服务开机自启，分别测试 cam0、cam1、双路纯采集、HDMI、单路编码和多路编码；持续采集内核错误、进程状态、FPS 和内存。

**Result：** 排除传感器、CSI/ISP 和双路 YOLO，定位到双路 720p60 RGA→MPP 并发链路；稳定基线在 30 秒运动测试中新增内核错误为 0，并避免系统再次开机阻塞。

## 7. 严禁夸大的表述

- 当前真机报告对应 Qwen2.5-Omni-3B，不能写“Qwen3.5-Omni 已完成全部验收”。
- 当前编译模型 KV Buffer 实际为 1024，不能写“支持 8192 Token 多轮上下文”。
- 双路 Focus 720p60 已复现媒体路径阻塞，不能写“稳定实现双路 60 FPS WebRTC”。
- 高速硬件 ROI 尚未完成九点标定与循环验收，不能写“112 FPS 已稳定交付”。
- RK1828 没有可信公开利用率计数器，不能伪造 NPU 百分比。
- RK3588 宿主 RSS 不等同于 RK1828 设备侧 KV 内存。

## 8. 后续信息采集清单

### 个人信息

- [ ] 项目起止时间：`____年__月 - ____年__月`
- [ ] 项目性质：课程 / 科研 / 实习 / 个人项目 / 实验室项目
- [ ] 团队人数：`____人`
- [ ] 本人角色：负责人 / 核心开发 / 算法部署 / 嵌入式开发
- [ ] 本人代码量或主要模块：`________________`
- [ ] 目标岗位：嵌入式 Linux / AI 部署 / 推理优化 / 全栈 / 算法工程

### 工程规模

- [ ] C++、Python、TypeScript 代码行数
- [ ] API 数量、测试数量、自动化脚本数量
- [ ] 支持的模型和量化格式
- [ ] 从模型转换到板端部署的总耗时和自动化程度
- [ ] 冷启动时间、常驻模型加载时间和服务重启时间

### 待补性能数据

- [ ] 至少 5 次图像多模态测试的 P50/P95，而不是单次结果
- [ ] 图片分辨率、Prompt Token、Vision Token和实际总输入 Token
- [ ] 图片读取、预处理、Vision Encoder、Embedding、TTFT、TPOT、总耗时
- [ ] 2–8 小时常驻内存趋势和错误率
- [ ] 两路浏览器预览的真实采集、编码、WebRTC 接收和渲染 FPS
- [ ] 不同视频分辨率、帧率和码率下的 RGA/MPP 稳定边界
- [ ] 九点跨摄标定误差、ROI 切换成功率和切换耗时 P50/P95
- [ ] 功耗数据；没有外部功率计时不要估算整机能耗

### 成果证明

- [ ] 系统架构图
- [ ] Web 页面截图或 1–2 分钟演示视频
- [ ] Git 提交记录和 README
- [ ] 一键部署/恢复脚本
- [ ] 实验原始数据与论文图表
- [ ] 可公开的代码仓库或脱敏项目说明

## 9. 根据岗位选择内容

| 目标岗位 | 简历优先展示 |
| --- | --- |
| 嵌入式 Linux | PCIe、V4L2、RKISP、RGA、MPP、交叉编译、驱动故障定位、服务恢复 |
| 大模型部署 | RKNN3、模型转换、常驻服务、KV Cache、TTFT/TPOT、上下文容量 |
| 推理优化 | KV 对照实验、Prefill/Decode 拆分、P50/P95、内存和异构干扰分析 |
| 后端/平台 | FastAPI、Unix Socket、SSE/WebSocket、多会话、审计、监控与实验系统 |
| 计算机视觉 | 双 IMX415、YOLO、跨摄映射、追踪、ROI、RGA/MPP 视频链路 |

## 10. 原始证据索引

- `experiments/20260917-rknn3-resident-baseline/`
- `experiments/20260918-token-e2e-ttft-validation/`
- `experiments/20260918-context-scaling/`
- `experiments/20260918-resident-100-request-stress/`
- `experiments/20260919-steady-30m-single-camera/`
- `experiments/20260919-steady-30m-no-camera/`
- `experiments/20260919-camera-motion-freeze-isolation/`
- `experiments/20260919-dual-camera-global-to-roi-demo/`

修改简历数字前，应先回到对应实验目录核对 `manifest.yaml`、原始数据和指标口径。
