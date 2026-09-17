# 故障记录

## 页面可打开但无法读取 API

确认管理令牌与 YAML 一致，并检查浏览器请求是否携带 `Authorization: Bearer ...`。

## RK1828 显示离线

检查 `/dev/pcie-rkep-*`、`rknn3_transfer_proxy` 和 PCI ID `1d87:182a`。不要把代理进程 CPU 占用当成 NPU 利用率。

## 摄像头图片不显示

图片 Provider 的源文件必须存在。RTSP 不能由普通 `<img>` 直接播放，需要 HLS/WebRTC 网关；快照仍可通过 FFmpeg 获取。

## KV 看似没有复用

真实后端须设置 `keep_history=1`，并读取 `RKLLMRunState.n_reuse_tokens`。mock 数据只能验证 UI 和生命周期，不能作为性能结论。

## 为什么界面显示 1024 而不是转换日志中的 8192

板端 Runtime 初始化实际报告 LLM RKNN 只包含 `kvcache_buffer_lens=1024`，请求 8192 时会自动选择最接近的 1024 group。因此当前有效上下文必须按 1024 记录；要做 4K/8K 实验，需要重新转换包含相应 KV length group 的模型产物，不能只改界面数字。

## Daemon 热更新时 `MODEL_SETUP fail`

RK1828 Context 仍被旧进程占用时，新进程加载模型会收到 `ACK_FAIL`。初版信号处理只设置退出标志，但服务线程阻塞在 `accept()`，导致 SIGTERM 后未退出。现已在信号处理时关闭监听 FD，使进程完成 Context 析构；部署脚本必须确认旧 PID 消失后才能启动新版。
