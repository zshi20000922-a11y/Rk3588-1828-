# Changelog

## 0.1.0 - 2026-09-17

- 建立独立异构边缘 AI 平台工程。
- 增加 FastAPI、React、SQLite、SSE/WebSocket、媒体上传和设备监控。
- 增加会话/KV 控制协议、白名单工具、CameraProvider 和模型插件配置。
- 增加实验清单、原始指标和系统时间序列的标准目录。
- C++ Daemon 已接入真实 RKNN3 Context、多 Session、`keep_history=1`、停止、KV 清理及导入导出接口。
- 板端两轮文本实测确认权重只加载一次，第二轮 `n_reuse_tokens=63`。
- Runtime 查询发现本次 RKNN 产物仅含 1024-token KV group；平台如实将有效上下文由预期 8192 修正为 1024。
