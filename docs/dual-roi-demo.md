# 双摄全局搜索与高速硬件 ROI Demo

## 演示数据流

Camera 0 始终以 3840×2160@60 FPS 做全局搜索。检测到最高置信度的 `person` 后，服务利用固定机位的单应矩阵在 Camera 1 中寻找同一目标；只有 Camera 1 自身检测也通过位置、尺寸、外观和时间约束，才允许把 Camera 1 切换到 640×640@112 FPS Sensor ROI。ROI 内检测上限为 60 FPS，目标偏离中心 64 px 时以最高 10 Hz 移动裁剪窗口。

状态机为：

```text
GLOBAL_SEARCH -> CROSS_CAMERA_MATCH -> SWITCHING_TO_ROI
              -> ROI_TRACK -> TARGET_LOST -> GLOBAL_REACQUIRE
```

目标丢失 1.5 秒后 Camera 1 自动恢复全画幅。Camera 0 不切换模式，因此始终保留全局视野。

## Web 操作

页面“全局搜索 / 高速 ROI”面板提供启动、退出、解除目标、恢复全画幅和演示辅助投影开关。投影 fallback 默认关闭，防止仅凭旧标定切到错误区域。Camera 1 模式切换期间页面冻结末帧并显示切换状态。

Demo 与普通 `rk_vision_service` 互斥：启动 Demo 时先停止普通视觉服务，再启动 `rknn_dual_camera_detector`；退出或启动失败时恢复普通视觉服务。RK1828 推理服务不参与切换。

双摄 ROI 服务脚本只安装在 `/userdata/rknn-dual-detector/`，不得以 `S*` 名称放入 `/etc/init.d/`。该 Demo 只能由 Web 白名单接口按需启动，防止开机阶段抢占摄像头、RGA、MPP 或阻塞用户态启动。

## 专家演示步骤

1. 使用网线专网访问页面，优先使用 WebRTC；USB 页面只提供 640×360@5 FPS CPU MJPEG 降级预览。
2. 确认预检为通过、两路相机在固定安装位置且画面存在重叠区域。
3. 点击“启动 Demo”，等待状态进入 `GLOBAL_SEARCH`。
4. 单人进入 Camera 0 视野，同时确保 Camera 1 能看见该人员。
5. 观察跨摄匹配、Camera 1 硬件 ROI 切换、112 FPS 采集和 60 FPS 局部检测。
6. 人员离开后确认 1.5 秒内进入重捕获并恢复全画幅。
7. 演示结束点击“退出 Demo”，确认普通双摄服务恢复。

## 九点标定预检

旧单应矩阵仅适用于 2026-08-24 的固定机位。正式演示前应让单人依次站在 Camera 0 的中心、四角和四边，保存 Camera 0 中心、Camera 1 预测中心及实际中心。P95 映射误差必须不超过 160 px；超限时禁止硬件 ROI，并重新拟合单应矩阵。

将九点数据保存在部署设备的配置目录中，例如 `/userdata/rknn-dual-detector/config/homography-nine-point.csv`，然后执行：

```bash
python3 scripts/validate-homography.py /userdata/rknn-dual-detector/config/homography-nine-point.csv \
  --calibration /userdata/rknn-dual-detector/config/stereo_calibration.yaml \
  --output /userdata/rknn-dual-detector/config/homography_validation.json
```

少于九点或 P95 超过 160 px 时，Web 的“启动 Demo”按钮保持禁用。

## 故障恢复

- Demo 启动失败：控制器会停止双摄检测进程并恢复 `rk_vision_service`。
- Camera 1 模式切换失败：检测进程会回滚到 3840×2160 全画幅。
- 页面没有视频但状态正常：优先检查 MediaMTX 的 `demo-global` 和 `demo-roi`；不要并行启动额外 MPP MJPEG 解码器。
- 出现 `rga timeout`、`map dma buffer error` 或 `rkvdec reset`：立即退出 Demo，保存 pstore/dmesg，并按故障恢复流程检查设备。
