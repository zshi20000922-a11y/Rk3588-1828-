# RK3588 媒体链路空闲门控与 Focus 隔离

## 问题

摄像头源停止后，Mosaic/Focus 合成器仍按目标帧率处理保存的最后一帧，并持续送入 MPP。因此上一轮“关闭采集和 YOLO”实验中视觉服务仍占用约 27.23% 单核 CPU。

检查还发现 Focus 合成器消费全局 FrameHub 时没有过滤绑定源。cam1 禁用后，cam0 的帧仍会唤醒 focus1，使其持续编码黑帧。这既浪费 RGA/MPP 资源，也会让离线通道表现为有编码数据但画面为黑色。

## 改进

- 合成器仅在绑定源的 generation 增长时标记 dirty 并产生输出。
- 没有新帧时保留 RGA DMA 池和 MPP Context，只让工作线程等待。
- Focus 严格过滤配置的 `source_id`，其他摄像头不能唤醒本输出。
- 连续 250 ms 没有绑定源新帧后报告 idle。
- 状态接口增加 `media_idle`、`mosaic_idle` 和 `focus_idle`，Web 面板显示媒体链路状态。
- cam1 的 `enabled: false` 已持久化，防止服务重启后短暂抢占用户的另一用途摄像头。

## 板端结果

cam0 在线、cam1 禁用时的 10 秒计数增量为：Mosaic 250 帧、focus0 600 帧、focus1 0 帧，分别符合 25/60/0 FPS 预期。两路输入均停用后，5 秒内 Mosaic 和三个 MPP 编码器计数增量全部为 0，`media_idle=true`。

空闲视觉进程 CPU 由旧版 30 分钟均值 27.23% 降至首轮 30 秒测量约 9.4%，下降约 65.5%。剩余占用来自常驻服务、Wayland/GStreamer 和控制线程；后续可将 5 ms 轮询改为 FrameHub 条件变量等待继续降低。

cam0 从禁用到首帧约 337 ms，恢复后实测约 60 FPS，YOLO 约 5 FPS。浏览器 MJPEG 验证返回 HTTP 200 并在 5 秒收到约 1.28 MB；平台健康检查和 RK1828 推理服务均保持在线。

## 风险与回滚

热启停 V4L2 时曾累计一次非致命 `VIDIOC_QBUF: Invalid argument`，随后摄像头正常在线且持续出帧。生产环境如出现恢复失败，可重启视觉服务；旧二进制保留在清单所列路径，可直接回滚。

