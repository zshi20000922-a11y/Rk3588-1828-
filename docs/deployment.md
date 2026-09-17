# 部署说明

## 板端依赖

板端已有 Python 3.11、Nginx、FFmpeg、GStreamer、V4L2 和 SQLite。首次安装：

```bash
cd /userdata/rk-edge-ai
python3 -m venv .venv
.venv/bin/pip install --no-index --find-links wheelhouse-aarch64 \
  fastapi uvicorn python-multipart pydantic PyYAML Pillow
```

在 PC 执行 `scripts/build.sh` 和 `scripts/deploy-board.sh`。修改 `config/platform.board.yaml` 的令牌后运行 `board-start.sh`。

板端真实 RKNN3 后端验收完成前保持 `inference.backend: mock`。完成后将其切换为 `rknn3`，并先启动 `/run/rk-edge-ai/inference.sock` 对应的 Daemon。

建议最后增加 Buildroot init 脚本，让 Daemon 先于 Web 服务启动；Nginx 只代理 `/api` 和静态目录，不直接开放 Unix Socket。
