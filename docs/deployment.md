# 部署说明

## 板端依赖

板端已有 Python 3.11、Nginx、FFmpeg、GStreamer、V4L2 和 SQLite。首次安装：

```bash
cd /userdata/rk-edge-ai
python3 -m venv .venv
.venv/bin/pip install --no-index --find-links wheelhouse-aarch64 \
  fastapi 'uvicorn[standard]' websockets python-multipart pydantic PyYAML Pillow
```

在 PC 执行 `scripts/build.sh` 和 `scripts/deploy-board.sh`。修改 `config/platform.board.yaml` 的令牌后运行 `board-start.sh`。

板端 `/etc/init.d/S97rk-edge-ai` 会从 `config/platform.board.yaml` 的 `inference` 段读取 `max_sessions`、`max_context_tokens` 和 `max_new_tokens`，并分别传给 C++ 守护进程。修改这些值后必须重启 `S97rk-edge-ai`；上下文增大会增加 RK1828 KV Cache 内存，部署前应按 1024、2048、4096、8192 逐档做稳定性与内存实验。

板端真实 RKNN3 后端验收完成前保持 `inference.backend: mock`。完成后将其切换为 `rknn3`，并先启动 `/run/rk-edge-ai/inference.sock` 对应的 Daemon。

建议最后增加 Buildroot init 脚本，让 Daemon 先于 Web 服务启动；Nginx 只代理 `/api` 和静态目录，不直接开放 Unix Socket。

真实 IMX415 使用已有 `rk_vision_service` 采集 `/dev/video44`，并输出
`rtsp://127.0.0.1:8554/mosaic`。将它的启动脚本安装为
`/etc/init.d/S96rk-vision-service`，平台脚本使用 `S97rk-edge-ai`，确保摄像头源先于 Web 平台启动。

板端 `camera_preview.backend` 默认使用 `gstreamer_mpp`：RTSP H.264 经
`mppvideodec` 硬解码/缩放，再由 `mppjpegenc` 输出浏览器可显示的 MJPEG。
部署前可用 `gst-inspect-1.0 mppvideodec mppjpegenc` 检查插件。开发机没有
Rockchip MPP 时保持 `ffmpeg` 后端。每个浏览器预览连接当前对应一个网关进程，
客户端离开后服务会主动终止该进程。同一摄像头的所有页面共享一个 MPP
进程，可通过 `GET /api/v1/cameras/preview/status` 查看客户端数、进程 PID、
累计帧数、慢客户端丢帧和异常重启次数。

网口接入后先执行 `udhcpc -i eth0 -q -n`。如果没有 DHCP OFFER，不应猜测局域网网段；先在路由器配置 DHCP，或由管理员提供固定 IPv4、掩码和网关。USB 调试期间仍可使用 `adb forward tcp:18081 tcp:8080`。
