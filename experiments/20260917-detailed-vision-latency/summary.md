# 图像多模态端到端分阶段性能报告

## 1. 实验目的与指标口径

本实验不只记录一个笼统的端到端延迟，而是把 RK3588→RK1828 图像问答链路拆分到可解释阶段。固定提示词为：

```text
<image>请用一句话描述图像中的主要内容。
```

Tokenizer 对该原始提示词计数为 11 Token。Vision Encoder 固定输入为 392×392 RGB888，输出为 196×2048 FP16，即 196 个视觉 Token、802,816 字节视觉 Embedding。加入 Chat Template、视觉起止标记等后，RKNN3 报告本轮总输入为 246 Token。

指标定义：

- `TTFT`：从 `rknn3_session_run` 开始到收到第一个输出 Token；不包含图片读取和 Vision Encoder。
- `Prefill TPS`：本轮 `input_tokens / TTFT`，用于相同输入结构下比较；它包含 RKNN3 LLM Prefill，但不含此前的图像编码。
- `TPOT`：`(llm_ms - ttft_ms) / (output_tokens - 1)`，即首 Token 之后每个 Token 的平均时间。
- `Decode TPS`：`1000 / TPOT(ms)`。
- `Total`：从 Session 获取开始，包含图片读取、预处理、Vision Encoder、Embedding 组装、LLM Prefill 和 Decode。

## 2. 输入数据

三张图片来自同一时刻的 IMX415 画面，内容相同，分别缩放为 640×360、1280×720 和 1920×1080。文件、哈希和原始结果均随实验保存。每档分辨率运行五次，每次使用新 Session 且结束后完全清理，因此 `reused_tokens=0`。

## 3. 主要结果

| 原始分辨率 | JPEG大小 | 读取均值 | 预处理均值 | Vision Encoder | Vision总计 | TTFT | Prefill TPS | TPOT | Decode TPS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 640×360 | 27.9 KB | 5.13 ms | 6.41 ms | 219.91 ms | 233.53 ms | 284.63 ms | 864.46 | 11.50 ms | 87.26 |
| 1280×720 | 62.5 KB | 8.38 ms | 5.15 ms | 217.37 ms | 229.28 ms | 281.24 ms | 874.74 | 11.59 ms | 86.38 |
| 1920×1080 | 111.0 KB | 13.04 ms | 4.85 ms | 218.36 ms | 230.31 ms | 282.57 ms | 870.78 | 11.51 ms | 87.12 |

Vision 输入拷贝均值约 0.09 ms，输入同步约 2.27–2.76 ms，输出同步约 4.09–4.37 ms，视觉 Embedding 拷贝约 0.23–0.28 ms，模态结构组装低于 0.001 ms。固定 392×392 模型输入使 Vision Encoder 时间基本不随原始分辨率变化；原始分辨率主要影响 JPEG 读取解码，640×360 到 1920×1080增加约 7.9 ms。

## 4. 输出长度与总延迟说明

三档输入的输出分别稳定为 17、118、16 Token。1280×720版本识别到了画面中的玩偶和电脑机箱，生成了更长的描述，因此端到端总耗时约 1.97 s；另外两档约 0.78–0.80 s。这个差异来自输出长度，不是 Vision Encoder 变慢。比较模型计算时应优先使用 TTFT、TPOT 和 Decode TPS，而不能只比较总耗时。

同一帧不同缩放版本导致描述细节明显变化，说明固定 392×392预处理对缩放采样敏感。后续质量实验应增加统一插值算法、保持宽高比/Letterbox 与中心裁剪对照，不能仅以速度选择输入分辨率。

## 5. 数据流与计时位置

```text
JPEG文件(640/1280/1920)
  → RK3588读取与JPEG解码
  → resize/color convert到392×392 RGB888
  → 输入内存拷贝与同步
  → PCIe/RK1828 Vision Encoder
  → 输出同步
  → RK3588复制196×2048 FP16视觉Embedding
  → 组装多模态Tensor + 文本Embedding lookup
  → RK1828 LLM Prefill（TTFT终点）
  → RK1828 Decode（TPOT/Decode TPS）
```

## 6. 可复现性与限制

每次请求的完整提示词、回答、图片路径、Token 数、所有阶段原始时延及清理结果保存在 `raw.jsonl`。当前时间来自 RK3588 进程的单调时钟；`rknn3_run` 是同步调用，因此 Vision Encoder 数值包含 RKNN3 调用和 PCIe 命令往返，不能解释为纯 NPU kernel 时间。若厂商后续开放设备侧 profiling，应再增加 NPU kernel 与 PCIe DMA 的细分时间。
