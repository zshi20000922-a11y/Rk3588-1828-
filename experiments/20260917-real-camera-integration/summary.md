# IMX415 真实摄像头接入记录

## 数据流

IMX415 经 CSI 输入 RK3588 ISP，`rk_vision_service` 从 `/dev/video44` 采集 3840×2160 NV12，编码并发布 `rtsp://127.0.0.1:8554/mosaic`。Web 后端仅在浏览器预览时转封装为 MJPEG；点击分析时抓取单帧 JPEG，通过 PCIe 上的 RK1828 Vision + LLM 推理，不连续占用大模型推理队列。

## 验证结果

- 摄像头驱动识别到传感器 ID `0000e0`，RTSP 端口 8554 正常监听。
- 浏览器网关 4 秒接收 794887 字节，首帧为有效 JPEG multipart 数据。
- WebSocket 系统指标成功返回 RK3588 内存和 RK1828 idle 状态。
- 模型读取真实抓拍并生成画面描述，证明 Capture → Upload → Vision → LLM → SSE 全链路可用。

## 发现与修复

长中文回答曾因 Tokenizer 将 UTF-8 字符拆到两个回调而中止。修复方式是在 C++ Daemon 中缓存不完整字节序列，只把完整 UTF-8 数据写入 JSON Lines。开机加载方面，代理进程创建早于 RK1828 固件完全就绪，因此在设备节点和代理就绪后增加 10 秒稳定窗口。

## 网络结论

以太网物理链路为 1Gbps，但本次 DHCP Discover 未收到租约。因此当前验收继续使用 ADB 端口转发；待路由器 DHCP 或固定 IPv4 参数明确后，再切换局域网 URL。
