# 论文实验规范

每个实验只改变一个主要变量，并保存 Git commit、模型哈希、固件、输入集、随机/采样参数和热身次数。至少报告 P50/P95，而不是只报告平均值。

基线顺序：一次性 CLI；常驻无历史；常驻 KV 复用；多 Session；KV 换出；KV 低精度；RK3588 小模型并发。质量实验必须与性能实验使用同一模型产物，INT8/FP8 与 INT4/FP4 分开结论。

系统监控每秒采样，推理事件精确记录排队、Vision、Audio、Prefill、TTFT、Decode 和总延迟。RK1828 无公开利用率时用 busy time / wall time 标为 `inference_duty_cycle`。

