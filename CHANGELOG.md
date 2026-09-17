# Changelog

## 0.1.0 - 2026-09-17

- 建立独立异构边缘 AI 平台工程。
- 增加 FastAPI、React、SQLite、SSE/WebSocket、媒体上传和设备监控。
- 增加会话/KV 控制协议、白名单工具、CameraProvider 和模型插件配置。
- 增加实验清单、原始指标和系统时间序列的标准目录。
- C++ Daemon 已接入真实 RKNN3 Context、多 Session、`keep_history=1`、停止、KV 清理及导入导出接口。
- 板端两轮文本实测确认权重只加载一次，第二轮 `n_reuse_tokens=63`。
- Runtime 查询发现本次 RKNN 产物仅含 1024-token KV group；平台如实将有效上下文由预期 8192 修正为 1024。
- 三栏页面改为各自独立滚动，中央多模态控制台滚动不再带动会话栏和监控栏。
- 接入 IMX415 → RK3588 视觉服务 → RTSP → FFmpeg/MJPEG 浏览器预览与按需抓帧分析链路。
- 补齐 WebSocket 运行依赖、RK1828 开机就绪等待，并修复流式中文 Token 跨 UTF-8 字节边界导致的 JSON 中断。
- 修复设备指标每秒刷新时改变摄像头 URL、反复创建 FFmpeg 预览进程并阻塞问答的问题；预览地址现在在页面生命周期内保持稳定。
- 将真实摄像头检测改为帧差门控：静止 1 FPS、运动最高 15 FPS，并修复缩小运动图错误使用 DMA-BUF 直接输入导致门控未实际运行的问题。
- 上下文面板改为读取模型注册表上限，显示剩余 Token 与 80%/95% 告警；会话 Token 数改为当前 RKNN 上下文量而非历史累计量。
