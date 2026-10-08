# 双摄像头接入记录

## 页面能力

摄像头面板支持“摄像头 1”“摄像头 2”和“双路同屏”。单路模式只建立所选流的浏览器预览；双路模式同时建立两路独立预览，因此每路均可单独放大、抓帧和提交多模态分析。MPP 共享网关按摄像头 ID 复用解码结果，多个浏览器不会重复启动同一路硬件解码。

板端 RTSP 约定如下：

- 摄像头 1：`rtsp://127.0.0.1:8554/focus/0`
- 摄像头 2：`rtsp://127.0.0.1:8554/focus/1`
- 双摄拼接：`rtsp://127.0.0.1:8554/mosaic`

完整双摄视觉服务模板见 `config/vision-service.dual-camera.yaml`。部署前必须分别对两个 V4L2 节点执行 STREAMON 验证；不能仅凭 `/dev/video*` 文件存在判断摄像头在线。

板端已使用的物理接口与设备节点映射如下；部署到其他镜像或载板时，仍应以当前 media graph 为准重新核对：

- CSI3：`3-001a -> media2 -> rkisp0-vir0 -> /dev/video44`。
- CSI1：`7-001a -> media0 -> rkisp1-vir0 -> /dev/video62`。

设备节点编号与接口名受设备树和内核枚举影响。配置前应同时核对设备树、I2C 驱动绑定和 media graph，不能只根据连接器编号推断 CSI/DPHY 映射。

## 60 FPS Web 预览

页面视频链路采用以下结构：

`IMX415 4K60 -> ISP -> RGA 720p -> MPP H.264 60 FPS -> RTSP -> MediaMTX -> WebRTC -> 浏览器 video`

MediaMTX 仅转协议，不解码和重新编码 H.264。USB 调试页面使用共享 CPU MJPEG 降级流（640×360、5 FPS）；双路 MPP MJPEG 可能与主视觉服务竞争 RGA/RKVDEC，不作为稳定默认链路。局域网直连使用 MediaMTX WebRTC。YOLO 独立采样，不与页面预览帧率绑定。

“分析当前帧”会从对应独立 RTSP 流抓取一张 1280×720 JPEG，先作为用户消息图片插入当前对话，再将同一个文件路径提交给 RK1828 Vision。历史消息接口会把附件恢复为受管理员令牌保护的只读 URL，因此刷新页面后仍能确认模型分析的具体帧。
