# Session容量保护验收

在禁用不稳定的自动LRU checkpoint后，依次建立四个独立会话并写入不同代号。第五个会话被立即拒绝，返回：

```text
session capacity reached; clear an idle conversation before retrying
```

随后重新询问第一个驻留会话，仍准确回答 `JADE-17`，说明容量拒绝没有破坏已有KV。所有实验会话均成功清理，守护进程Socket和Web健康检查保持在线。

当前策略牺牲自动无限会话体验，换取明确的资源边界和服务稳定性。Web层后续应在收到该错误时提示用户删除或清理一个闲置会话，而不是显示通用推理失败。
