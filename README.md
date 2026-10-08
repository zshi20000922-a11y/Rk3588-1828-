# RK3588 + RK1828 异构多模态推理平台

面向边缘设备多模态推理、双摄视觉和可复现实验的工程项目。RK3588 负责 Web/API、摄像头与视觉任务；通过 PCIe 连接的 RK1828 运行 Qwen2.5-Omni-3B RKNN3 推理。

> 项目仍在迭代。PC 开发配置默认使用 mock 推理后端；性能数据只适用于对应实验记录中的硬件、模型和配置。双摄高帧率配置仍有驱动稳定性限制，详见 [实验记录](experiments/) 和 [故障排查](docs/troubleshooting.md)。

## 功能

- FastAPI REST/SSE/WebSocket、SQLite 会话与审计。
- React/TypeScript 控制台，支持文本、图片、浏览器录音、流式回复、会话管理和设备状态查看。
- C++ Unix Socket 推理守护进程，管理 RKNN3 模型与多会话 Session/KV Cache。
- 摄像头选择、帧分析、检测/追踪控制和共享预览网关。
- RK3588 侧 V4L2、RKISP、RGA、MPP、RTSP/WebRTC 视觉链路及 YOLO 接口。
- 双摄全局搜索到硬件 ROI 的控制原型，启动前有设备绑定和标定误差检查。
- 可复现实验记录，包含配置、原始数据、统计指标和结论。

## 架构与职责

```text
Browser --HTTP/SSE/WS--> FastAPI --Unix Socket--> C++ inference-daemon
   |                         |                           |
 text/image/audio       SQLite + experiments       RKNN3 Session
                                                       |
                                                PCIe -> RK1828

IMX415 x2 -> CSI/RKISP/V4L2 -> RK3588 RGA / NPU / MPP -> RTSP/WebRTC
```

RK1828 当前没有可信的公开硬件利用率计数器；界面显示推理阶段和忙闲占空比时，不应将它解释成 NPU 百分比。RK3588 的采集 FPS、编码 FPS 和浏览器呈现 FPS 也分别统计。

## PC 开发启动

要求 Python 3.11+、Node.js/npm 和 Git。

```bash
git clone https://github.com/zshi20000922-a11y/Rk3588-1828-.git
cd Rk3588-1828-

python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cd frontend
npm ci
npm run build
cd ..

# 设一个仅供本机使用的随机令牌；启动时也可以用配置文件设置。
export RK_PLATFORM_ADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf '管理令牌：%s\n' "$RK_PLATFORM_ADMIN_TOKEN"
RK_PLATFORM_CONFIG=config/platform.yaml PYTHONPATH=backend \
  .venv/bin/python -m uvicorn rk_platform.app:app --host 127.0.0.1 --port 8080
```

打开 `http://127.0.0.1:8080`，把终端打印的管理令牌填入页面。也可以复制 `config/platform.yaml` 为被 `.gitignore` 忽略的 `config/platform.local.yaml`，填写本地令牌后通过 `RK_PLATFORM_CONFIG=config/platform.local.yaml` 启动。不要提交本机令牌或 `.env` 文件。

PC 配置使用 mock 后端，只用于验证页面和 API 生命周期；它不能代表 RK1828 的模型推理性能。

## RK3588/RK1828 部署

完整流程见 [部署文档](docs/deployment.md)。板端部署需要 RKNN3 SDK、RKNN3 模型产物、Tokenizer/Embedding 文件、RK3588 交叉编译工具链及相应系统库。这些 SDK、工具链和模型权重不包含在本仓库中，应按文档提供的路径或 CMake 参数单独安装。

```bash
# RKNN3 模型 Zoo 为独立外部目录，通过参数指定，不要求固定本机目录。
cmake -S native -B build-native \
  -DRKEDGE_WITH_RKNN3=ON \
  -DMODEL_ZOO=/path/to/rknn3-model-zoo
```

部署前请复制板端配置模板，设置唯一管理令牌、模型路径和媒体设备路径，并按实验记录验收目标摄像头链路。双摄 ROI Demo 与视觉服务默认不应以未经验证的高帧率配置开机自启。

## 文档索引

- [系统架构](docs/architecture.md)
- [板端部署](docs/deployment.md)
- [双摄视觉链路](docs/dual-camera.md)
- [双摄硬件 ROI Demo](docs/dual-roi-demo.md)
- [故障排查](docs/troubleshooting.md)
- [论文实验设计](docs/thesis-experiments.md)
- [简历素材和已验证指标](docs/resume-points.md)
- [更新记录](CHANGELOG.md)
- [实验目录](experiments/)

## 数据与安全

- 不提交模型权重、RKNN Runtime、厂商 SDK、板端数据库、用户上传文件、私钥、访问令牌或本地环境文件。
- `config/platform.board.yaml` 是路径示例。部署到设备前必须设置唯一管理令牌并核对服务监听地址。
- 实验图片仅为项目测试输入；请勿将含个人或敏感场景的相机图像放入公开仓库。
- 第三方 SDK、模型和运行时须遵守其各自的许可与分发条款；本仓库不包含这些材料。
