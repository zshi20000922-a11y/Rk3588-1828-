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

## 开机后 Daemon 卡在 Vision `Weight sync`

原因是平台服务启动早于 `rknn3_transfer_proxy` 子进程完全就绪。代理进程出现也不代表固件与 DDR 已准备完成；启动脚本现在同时等待 PCIe 设备节点和 `rknn3_transfer_proxy_b98e6c51`，再留出 10 秒稳定时间后初始化 RK1828 模型。已经卡住的旧进程需要终止后重新启动，不能继续复用半初始化 Context。

## 摄像头长回答出现 UTF-8 解码错误

RKNN Tokenizer 可能把一个中文字符的 UTF-8 字节拆到两个回调。若每个回调直接封装成 JSON，Python 会在半个字符处报 `invalid continuation byte`。Daemon 现在缓存不完整字节序列，只发送可独立解码的 UTF-8 Token；这不是模型或摄像头故障。

## 网线已连接但没有 IPv4

`ethtool eth0` 显示 Link detected 和 1000Mb/s 只说明物理链路正常。执行 `udhcpc -i eth0 -q -n` 仍无租约，说明网络未提供 DHCP OFFER。此时只能使用 IPv6 link-local（需接口 zone）或按实际局域网参数配置固定 IPv4，不能随意指定地址。
