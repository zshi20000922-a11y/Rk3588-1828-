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

板端真实 RKNN3 后端验收完成前保持 `inference.backend: mock`。完成后将其切换为 `rknn3`，并先启动 `/run/rk-edge-ai/inference.sock` 对应的 Daemon。

建议最后增加 Buildroot init 脚本，让 Daemon 先于 Web 服务启动；Nginx 只代理 `/api` 和静态目录，不直接开放 Unix Socket。

真实 IMX415 使用已有 `rk_vision_service` 采集 `/dev/video44`，并输出
`rtsp://127.0.0.1:8554/mosaic`。将它的启动脚本安装为
`/etc/init.d/S96rk-vision-service`，平台脚本使用 `S97rk-edge-ai`，确保摄像头源先于 Web 平台启动。

网口接入后先执行 `udhcpc -i eth0 -q -n`。如果没有 DHCP OFFER，不应猜测局域网网段；先在路由器配置 DHCP，或由管理员提供固定 IPv4、掩码和网关。USB 调试期间仍可使用 `adb forward tcp:18081 tcp:8080`。
