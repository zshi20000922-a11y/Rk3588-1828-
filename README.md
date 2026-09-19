# RK3588 + RK1828 异构多模态推理平台

双摄专家演示的操作、数据流和恢复方法见 [双摄全局搜索与高速硬件 ROI Demo](docs/dual-roi-demo.md)。

面向边缘端多模态推理、工程展示和研究生论文实验的可观测平台。RK3588 负责 Web、预处理、摄像头和可扩展小模型，PCIe RK1828 负责 Qwen2.5-Omni-3B。

## 当前里程碑

- FastAPI REST/SSE/WebSocket API、SQLite 会话与审计；
- React 操作端：文字、文件、按住说话、流式输出、设备/模型/KV 面板；
- 真实视觉链路可在页面独立启停帧差、运动门控、YOLO 与追踪；摄像头支持双击放大和浏览器全屏；
- 网线直连使用 MediaMTX WebRTC；USB/ADB 使用低帧率 CPU MJPEG 降级流，避免双路 MPP 解码与主视觉服务争用 RGA/RKVDEC；
- 同一摄像头的多浏览器 MJPEG 预览共享一条管线，并提供客户端数、帧数、慢客户端丢帧和重启次数状态；
- CameraProvider（图片、视频、RTSP）和当前帧分析；
- 白名单工具注册表，不允许任意 Shell；
- 可复现实验目录生成器；
- C++ Unix Socket Daemon 协议和 LRU Session 管理；
- mock 后端可用于 PC/UI 测试。

RKNN3 真机后端合入前，配置明确使用 `backend: mock`；不能把 mock 结果当成 RK1828 实测结果。原始 Qwen2.5-Omni 板端 Demo 仍位于 `/userdata/rknn_Qwen2_5_Omni_demo`。

## PC 快速启动

```bash
cd /home/user/PycharmProjects/shize/RK3588/rk-heterogeneous-ai-platform
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cd frontend && npm install && npm run build && cd ..
RK_PLATFORM_CONFIG=config/platform.yaml PYTHONPATH=backend \
  .venv/bin/python -m uvicorn rk_platform.app:app --host 0.0.0.0 --port 8080
```

浏览器访问 `http://设备IP:8080`，默认开发令牌为 `SET_A_UNIQUE_TOKEN_BEFORE_START`，部署前必须修改。

## 数据流

```text
Browser --HTTP/SSE/WS--> FastAPI --JSONL/Unix Socket--> inference-daemon
   |                         |                              |
 audio/image             SQLite + experiments          RKNN3 sessions
   |                         |                              |
 camera preview        system telemetry       RK3588 --PCIe--> RK1828
```

详细说明见 `docs/`。历史模型转换与首次部署记录保留在 `/home/user/PycharmProjects/shize/RK3588/docs/qwen2.5-omni-rk1828`。
