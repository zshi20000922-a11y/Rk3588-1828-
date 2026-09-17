# 架构与数据流

平台分为浏览器、FastAPI 控制面和 C++ 推理数据面。控制面不持有 RKNN3 对象；Daemon 负责 Context、Session、串行设备队列和 KV 生命周期，避免 Web 重载导致权重重载。

每个 `conversation_id` 对应一个 Session。达到上限时按最后访问时间换出；删除会话时清空 KV。RK1828 没有公开可信占用率时只上报推理队列忙闲占空比与 RKNN3 内存，不伪造利用率。

摄像头通过 Provider 解耦。图片/视频/RTSP 用于第一阶段测试；真机阶段复用 `rk_vision_service` 的 V4L2、DMA-BUF、RGA、MPP 和 RTSP 链路。Omni 只按需分析快照，不处理每帧。

RK3588 小模型通过插件注册，声明 `target_device` 和控制 Socket。第一版不与 RK1828 共享队列，但统一采集指标和请求 ID。

只读自然语言工具在控制面先做确定性意图路由，例如“查看 CPU/NPU 占用”“查看当前模型”“查看摄像头状态”。命中后执行白名单工具并审计，不进入 LLM。清理会话、切换模型和启停插件等有副作用工具不做自动路由，必须通过带确认字段的工具 API。
