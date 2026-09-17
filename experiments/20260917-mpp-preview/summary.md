# RK3588 MPP 浏览器预览实验

## 问题

原始 Web 预览为每个客户端启动 FFmpeg，使用 CPU 完成 1080p H.264 解码、缩放和 MJPEG 编码。真机观察到单进程接近占满一个 CPU 核且 RSS 超过 100 MB。

## 硬件能力探测

板端 FFmpeg 只暴露 `h264_v4l2m2m`，实测报 `Could not find a valid device`，因此不能将其当作可用硬解码路径。GStreamer 安装了 Rockchip `mppvideodec` 和 `mppjpegenc`，MPP 版本为 `18cf2ca`，完整 RTSP 管线可稳定运行。

## 方法

两组均输入同一路 1920×1080、25 FPS H.264 RTSP，输出 960×540、8 FPS MJPEG。预热三秒后连续采集五次进程 CPU 与 RSS。软件组使用 FFmpeg native decoder/scale/MJPEG，硬件组使用 GStreamer MPP decoder/JPEG encoder。

## 结果

| 管线 | 平均进程 CPU | 平均 RSS | CPU 降幅 | RSS 降幅 |
|---|---:|---:|---:|---:|
| FFmpeg 软件管线 | 95.98% | 115.37 MB | — | — |
| GStreamer MPP | 16.04% | 18.02 MB | 83.29% | 84.38% |

浏览器实测缩略图和双击放大画面均为 960×540 且加载完成。断连测试中进程集合由 `[10036]` 变为 `[10202, 10036]`，测试客户端退出后恢复为 `[10036]`，证明新增子进程已回收；保留进程来自另一条持续页面连接。

## 结论

MPP 管线显著降低了浏览器预览对 RK3588 CPU 与内存的占用，为同时运行 Qwen 多模态前处理和 RK3588 NPU 小模型腾出了资源。当前每个客户端仍启动一个 MPP 管线，下一实验应实现单路共享生产者和多客户端广播，比较 1/2/4 客户端资源增量。
