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

重新上电后确认物理接口命名与设备树映射如下：

- CSI3：`3-001a -> media2 -> rkisp0-vir0 -> /dev/video44`。
- CSI1：`7-001a -> media0 -> rkisp1-vir0 -> /dev/video62`。

两颗传感器均识别为 IMX415（芯片 ID `0xE0`）。`/dev/video62` 以 3840×2160、NV12 连续采集 30 帧成功，因此已满足双路启用条件。此前把 CSI3 物理接口误对应到 DPHY3/I2C4，原因是混淆了板卡连接器编号与内核 DPHY 编号；后续必须以设备树 symbol、I2C 驱动绑定和 media graph 三者共同确认。

## 60 FPS Web 预览

不能把原 MJPEG 网关直接从 8 FPS 提升到 60 FPS。当前采用以下链路：

`IMX415 4K60 -> ISP -> RGA 720p -> MPP H.264 60 FPS -> RTSP -> MediaMTX -> WebRTC -> 浏览器 video`

MediaMTX 仅转协议，不解码和重新编码 H.264。页面只为当前选中的摄像头建立 WebRTC 会话；双路同屏时建立两路。YOLO 独立以每路 5 FPS 采样，不与视频帧率绑定。USB 调试需要转发 8889/TCP 与 8189/TCP；局域网访问直接使用板端地址和 8189/UDP。
