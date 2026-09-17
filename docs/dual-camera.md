# 双摄像头接入记录

## 页面能力

摄像头面板支持“摄像头 1”“摄像头 2”和“双路同屏”。单路模式只建立所选流的浏览器预览；双路模式同时建立两路独立预览，因此每路均可单独放大、抓帧和提交多模态分析。MPP 共享网关按摄像头 ID 复用解码结果，多个浏览器不会重复启动同一路硬件解码。

板端 RTSP 约定如下：

- 摄像头 1：`rtsp://127.0.0.1:8554/focus/0`
- 摄像头 2：`rtsp://127.0.0.1:8554/focus/1`
- 双摄拼接：`rtsp://127.0.0.1:8554/mosaic`

完整双摄视觉服务模板见 `config/vision-service.dual-camera.yaml`。部署前必须分别对两个 V4L2 节点执行 STREAMON 验证；不能仅凭 `/dev/video*` 文件存在判断摄像头在线。

## 2026-09-17 板端检查

- 系统枚举到 4 个 IMX415 I2C 设备：`2-001a`、`3-001a`、`4-001a`、`7-001a`。
- 只有 `3-001a` 出现在 media graph 并连接到 CSI2 DPHY、CIF 和 ISP；其有效输出是 `/dev/video44`。
- `/dev/video53`、`/dev/video62`、`/dev/video71` 是 ISP mainpath 节点，但没有上游 sensor link，STREAMON 均返回 `Operation not permitted`。
- 因此本次只安全启用摄像头 1 的 `/focus/0`；没有把 `/dev/video62` 伪装为在线摄像头 2，也没有部署会导致视觉服务整体启动失败的双摄配置。

第二路恢复标准：`media-ctl -p` 能看到第二个 IMX415 到 DPHY/CIF/ISP 的 ENABLED 链路，并且目标 V4L2 节点可连续采集至少 30 帧。满足后部署双摄模板，再检查 `/focus/0`、`/focus/1` 和 `/mosaic` 三个 RTSP 地址。
