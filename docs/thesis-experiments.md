# 论文实验规范

每个实验只改变一个主要变量，并保存 Git commit、模型哈希、固件、输入集、随机/采样参数和热身次数。至少报告 P50/P95，而不是只报告平均值。

基线顺序：一次性 CLI；常驻无历史；常驻 KV 复用；多 Session；KV 换出；KV 低精度；RK3588 小模型并发。质量实验必须与性能实验使用同一模型产物，INT8/FP8 与 INT4/FP4 分开结论。

系统监控每秒采样，推理事件精确记录排队、Vision、Audio、Prefill、TTFT、Decode 和总延迟。RK1828 无公开利用率时用 busy time / wall time 标为 `inference_duty_cycle`。

## 延迟指标统一定义

- TTFT：LLM Session Run 开始至第一个输出 Token，不包含模态 Encoder。
- Prefill TPS：本轮 RKNN3 `n_input_tokens / TTFT`；报告时必须同时给出文本提示词、视觉/音频 Token 和总输入 Token。
- TPOT：`(llm_ms - ttft_ms) / (n_output_tokens - 1)`。
- `ttft_ms`：仅统计 `rknn3_session_run` 到首个输出 Token，便于和既有基线比较。
- `end_to_end_ttft_ms`：从请求进入 C++ 推理服务开始，包含队列等待、取图、预处理、Vision/Audio Encoder、模态组装和 LLM Prefill。
- Token 报告同时保存原始 `prompt_tokens`、去除 `<image>/<audio>` 后的 `text_prompt_tokens`、视觉/音频 Token 与由 RKNN3 实际输入反推的 `input_overhead_tokens`。后者是系统提示词、Chat Template 和多模态边界的净开销，不用估算值替代。
- Decode TPS：`1000 / TPOT(ms)`，不能把首 Token 重复计入 Decode。
- 多模态端到端延迟必须拆出文件读取、预处理、Encoder、Embedding 拷贝/组装、LLM Prefill 和 Decode。
- 图像实验必须记录原始分辨率、模型输入分辨率、缩放/裁剪策略、文件哈希及视觉 Token 数。
