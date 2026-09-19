# 双摄运动画面卡死隔离实验

## 故障现象

原配置同时运行双路 3840×2160@60 采集、1920×1080@25 HDMI 双画面、
1920×1080@25 Mosaic 编码以及两路 1280×720@60 Focus 编码。画面中出现
快速运动后约 5 秒，视频和板端用户态同时失去响应，ADB 只剩 transport 可见。

## 安全措施

- 双摄 ROI Demo 保持禁止开机自启。
- 普通视觉服务也临时移出 `/etc/init.d`，所有实验均手动启动。
- 每阶段监测服务存活、ADB 响应及 `size err`、RGA timeout、DMA map、
  RKVDEC reset 等内核错误。

## 单变量结果

| 阶段 | Camera | HDMI | MPP 输出 | 运动测试 | 新增内核错误 |
|---|---|---|---|---|---:|
| A | cam0 4K60 | 关闭 | 无 | 30 s 通过 | 0 |
| B | cam1 4K60 | 关闭 | 无 | 30 s 通过 | 0 |
| C | 双路 4K60 | 关闭 | 无 | 30 s 通过 | 0 |
| D | 双路 4K60 | 720p15 | 无 | 30 s 通过 | 0 |
| E | 双路 4K60 | 720p15 | Mosaic 720p15 | 30 s 通过 | 0 |
| F | 双路 4K60 | 720p15 | Mosaic 15 + Focus0 30 | 30 s 通过 | 0 |
| G | 双路 4K60 | 720p15 | Mosaic 15 + Focus0/1 30 | 30 s 通过 | 0 |

## 稳定配置与观测

稳定配置为 `config/rk-vision-test-dual-hdmi-mosaic-focus0.yaml`。三路 RTSP
均能串行读取，分辨率为 1280×720，平均帧率分别为 15/30/30 FPS。

运行时状态显示 cam0/cam1 实际采集约 16/25 FPS，并存在 V4L2 timeout，说明
在当前处理路径下并未维持两路真实 60 FPS。不能把编码器配置中的 30/60 FPS
当成实测采集或页面显示帧率。

## 结论

传感器、单路 CSI/ISP、双路纯采集以及双路 YOLO 均未复现卡死。故障由原始
HDMI/RGA/MPP 高并发组合触发。当前先使用 720p15 HDMI、15 FPS Mosaic 和
两路 30 FPS Focus；在修复采集 timeout、RGA 调度和首次并发 IDR 竞争前，禁止
恢复两路 Focus 60 FPS，也不恢复视觉服务开机自启。
