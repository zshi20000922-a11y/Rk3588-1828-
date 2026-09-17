# 双路 WebRTC 60 FPS 实验

原页面使用 RTSP 解码后重新编码 MJPEG，配置帧率仅 8 FPS。双路 4K60 输入、每路 15 FPS YOLO、三路 MPP 输出再叠加 MJPEG 网关时，页面出现卡死和 ADB 离线。

本次将两路独立输出改为 1280×720、H.264、60 FPS，并通过 MediaMTX WHEP/WebRTC 原码流转发。浏览器实测视频进入 `readyState=4`、`paused=false`、分辨率 1280×720；MediaMTX 日志确认两路 peer connection 均建立并分别读取 camera-1、camera-2。服务器端 `ffprobe` 确认两路为 60/1 FPS。

同时将 YOLO 从每路 15 FPS 调低为每路 5 FPS，使视觉服务进程 CPU 从约 173% 降至 109%–113%。双路 WebRTC 时 MediaMTX 约占 19% CPU，未创建 MJPEG GStreamer 子进程，内核未新增 RGA/DMA 错误。

结论：显示帧率和推理帧率必须解耦。WebRTC 可在不进行 JPEG 转码的情况下传送 720p60；目标检测维持 5 FPS 更适合异构推理平台的稳定常驻运行。
