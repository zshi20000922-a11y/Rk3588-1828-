# 架构与数据流

平台分为浏览器、FastAPI 控制面和 C++ 推理数据面。控制面不持有 RKNN3 对象；Daemon 负责 Context、Session、串行设备队列和 KV 生命周期，避免 Web 重载导致权重重载。

每个 `conversation_id` 对应一个 Session。达到上限时按最后访问时间换出；删除会话时清空 KV。RK1828 没有公开可信占用率时只上报推理队列忙闲占空比与 RKNN3 内存，不伪造利用率。

摄像头通过 Provider 解耦。图片/视频/RTSP 用于第一阶段测试；真机阶段复用 `rk_vision_service` 的 V4L2、DMA-BUF、RGA、MPP 和 RTSP 链路。浏览器预览通过 GStreamer `mppvideodec` 和 `mppjpegenc` 转为 MJPEG；同一 Camera ID 只创建一个生产管线，各 HTTP 客户端通过容量为一的队列订阅最新帧，避免应用层短时延迟直接阻塞采集与编码。最后一个客户端离开两秒后释放 MPP 进程。Omni 只按需分析快照，不处理每帧。

视觉服务的 Mosaic/Focus 合成器采用新帧驱动：仅当 FrameHub 的 generation 增长时才执行 RGA 并向 MPP 提交帧。所有输入源停止后不再重复编码最后一帧，`status.media_idle` 在 250 ms 无新帧后变为 `true`；输入恢复时保留既有 MPP Context，由第一帧直接唤醒。该门控不改变在线摄像头的目标帧率，也不自动启用已禁用的输入源。

每个 Focus 合成器还会严格过滤自身配置的 `source_id`。其他摄像头的新帧不会唤醒该输出，因此禁用 cam1 时，cam0 不会再驱动 focus1 编码黑帧。

两路 Focus 输出支持 RGA 自动人像 ROI。Sensor 和 ISP 始终保持 3840×2160@60 FPS；每路从自己的 YOLO person 检测中选择最高置信度目标，按输出宽高比生成带余量的裁剪框，并用指数平滑降低 5 FPS 检测结果带来的画面跳动。目标连续 1.5 秒不可见时自动回到全画幅。ROI 只影响 `/focus/0` 和 `/focus/1`，Mosaic 仍显示完整画面，方便观察目标是否离开裁剪区。

运行时可通过 `set_roi_mode` 为 cam0/cam1 独立选择 `full` 或 `auto`。状态接口的 `roi` 数组返回模式、是否正在跟踪和 `[left, top, width, height]`；Web 摄像头卡片提供相同控制。该方案不修改 Sensor crop，不会产生硬件 ROI 的 ISP/DPHY 重配断流。

需要注意，容量为一的队列限制的是应用层生产者到 HTTP 生成器之间的积压；已经交给 ASGI/TCP 的数据仍可能进入内核和客户端接收缓冲。真机 30 秒限速实验未影响正常客户端，但也未触发应用层丢帧，因此 MJPEG 不能视为具备端到端流控。超过少量局域网客户端时应使用 WebRTC，录像/高延迟观看则使用 HLS。

RK3588 小模型通过插件注册，声明 `target_device` 和控制 Socket。第一版不与 RK1828 共享队列，但统一采集指标和请求 ID。

只读自然语言工具在控制面先做确定性意图路由，例如“查看 CPU/NPU 占用”“查看当前模型”“查看摄像头状态”。命中后执行白名单工具并审计，不进入 LLM。清理会话、切换模型和启停插件等有副作用工具不做自动路由，必须通过带确认字段的工具 API。
