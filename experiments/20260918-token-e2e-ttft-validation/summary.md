# Token 与端到端 TTFT 指标验收

## 结论

真实 RK1828 图像推理成功。原始 Prompt 为 11 Token，其中 `<image>` 占位符为 3 Token，去掉占位符后的用户文字为 8 Token。Vision Encoder 输出 196 Token，RKNN3 报告实际输入为 246 Token，因此系统提示、Chat Template、多模态边界及 RKNN3 内部控制序列的净开销为 42 Token。

不要把 42 全部称为“系统提示词”。独立 Tokenizer 统计显示，当前完整 System Prompt 字符串为 11 Token，User/Assistant 包装字符串合计为 8 Token；剩余差额还包含多模态边界和 RKNN3 内部组装行为。由于分段 Tokenize 与完整序列 Tokenize 不一定严格可加，论文正文以 `input_overhead_tokens = input_tokens - text_prompt_tokens - vision_tokens - audio_tokens` 作为可复现的净开销口径。

## 单次结果

| 指标 | 结果 |
| --- | ---: |
| 原始 Prompt Token | 11 |
| 纯用户文字 Token | 8 |
| Vision Token | 196 |
| 实际输入 Token | 246 |
| 输入净开销 Token | 42 |
| 图片读取 | 46.85 ms |
| 图像预处理 | 5.72 ms |
| Vision 总计 | 232.35 ms |
| LLM TTFT | 306.55 ms |
| 端到端 TTFT | 685.90 ms |
| TPOT | 15.81 ms |
| Decode TPS | 63.25 |

本次端到端 TTFT 从请求进入 C++ `generate` 开始，包含推理互斥锁等待、图片读取、图像预处理、Vision Encoder、模态组装和 LLM Prefill。LLM TTFT 继续只统计 `rknn3_session_run` 到首 Token，以保持和历史实验可比。

## 稳定性检查

先提交不存在的图片路径 `/tmp/does-not-exist.jpg`，服务返回错误且推理 Socket 仍在线；随后同一进程成功完成真实图片推理。这验证了附件存在性检查能够阻止厂商图片读取库因无效路径导致守护进程退出。

原始响应保存在 `raw.jsonl`。本次仅为功能与指标口径验收，不用单次结果作为性能均值；正式性能结论仍需预热并至少重复五次，报告均值、标准差、P50 和 P95。
