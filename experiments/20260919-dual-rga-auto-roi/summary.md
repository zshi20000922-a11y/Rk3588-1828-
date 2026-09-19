# 双路 RGA 自动人像 ROI 部署记录

## 目标与边界

在不改变两路 IMX415 Sensor、ISP、V4L2 4K60 工作模式的前提下，为 `/focus/0` 和 `/focus/1` 增加独立人像自动裁剪。此实现不是 640×640 Sensor ROI，不会重配 DPHY，也不会产生硬件模式切换的约 0.88 秒断流。

## 数据流

每路 4K NV12 DMA-BUF 同时进入全局 Mosaic、YOLO 5 FPS 采样和本路 Focus 合成器。Focus 根据本摄像头最新 person 框计算与 1280×720 输出同为 16:9 的裁剪区，RGA 从原始 DMA-BUF 裁剪并缩放，随后交给 MPP H.264 编码。两路状态和裁剪坐标相互独立。

裁剪高度至少 720 像素，并覆盖目标框约 1.8 倍高度；若目标过宽则扩大宽度。裁剪框限制在 3840×2160 内并偶数对齐。新检测以 `alpha=0.25` 平滑更新；超过 1.5 秒没有 person 后回退全画幅。

## 控制与页面

- `PATCH /api/v1/vision/pipeline`，请求 `{"roi_modes":{"cam0":"auto"}}` 或 `full`。
- 每路摄像头卡片显示“自动 ROI/全画幅”、跟踪状态和 ROI 坐标。
- `GET /api/v1/vision/pipeline` 的 `roi` 数组是可审计的运行时真实状态。
- 服务重启默认两路进入 `auto`，目标未出现时输出全画幅。

## 验证

- cam0：约 59.98 FPS，YOLO 约 4.98 FPS，零采集错误。
- cam1：约 59.99 FPS，YOLO 约 4.98 FPS，零采集错误。
- 两路 Focus 流分别在 4 秒内传输约 0.95 MB 和 0.92 MB，HTTP 200。
- cam0 已完成 `auto → full → auto` API 切换回归；cam1 保持 auto。
- 当前视野没有置信度达到 0.30 的 person，两路 `tracking=false`、保持全画幅，符合失目标回退设计。
- Python 测试 10/10 通过，TypeScript/Vite 生产构建通过。

## 待现场验收

人员分别进入两路画面后，确认 ROI 在一个检测周期内建立、人物移动时画面平滑跟随、离开 1.5 秒后回到全画幅。建议下一轮保存 ROI 坐标时间序列，统计中心误差、抖动、建立时间和丢失恢复时间。

