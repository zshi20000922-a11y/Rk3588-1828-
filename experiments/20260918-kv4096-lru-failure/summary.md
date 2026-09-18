# 4096配置下多会话KV/LRU故障实验

## 结论

当前Qwen2.5-Omni-3B RKNN模型不能安全地作为4096 Token多轮服务使用。RKNN3日志明确报告当前Attention KV Cache仅包含：

```text
kvcache_buffer_lens[0]: 1024
No exact kvcache group id found for max_context_len=4096
Using closest ... chosen kvcache_buffer_lens: 1024
```

此前3650 Token单轮Prefill能够结束，只能证明单轮输入路径可处理该长度，不能证明多轮KV Cache容量为4096。

## 实验经过

4096配置下，四个短历史会话隔离测试完成三轮且守护进程仍在线。随后使用约650 Token历史执行显式换出/恢复及五会话LRU测试。创建第五会话触发四会话池淘汰后，生成了约98 MB的 `kv4096-1.kv`，随后出现0字节 `kv4096-2.kv`，守护进程不再响应新的控制请求。

四会话短历史阶段共12次召回全部正确、串话为0；首轮写入TTFT均值183.12 ms，KV召回TTFT均值96.62 ms，平均复用65.25 Token，清理后TTFT恢复为183.57 ms且复用归零。也就是说，4096运行参数下的短历史KV仍可工作，故障集中出现在较长历史的换出/LRU路径。

这与运行参数4096和编译KV buffer lens 1024不匹配高度相关。为保护生产服务，板端默认上下文已回退至1024，并清理本实验产生的KV文件。用户态重启随后停在Vision权重同步，最终通过冷重启RK3588/RK1828恢复；冷重启后1024配置下的四会话隔离回归再次通过。

## 后续要求

重新转换模型时必须显式生成4096及计划中的8192 KV buffer lens，并在部署前检查模型/SDK日志是否选择精确组，而不是 `closest` 回退。验收顺序应为：单会话多轮、四会话隔离、显式换出恢复、第五会话LRU、100次稳定性测试。

代码侧新增 `compiled_kv_context_tokens` 安全上限。即便误把 `max_context_tokens` 配成4096，当前模型也会将实际会话参数钳制到编译容量1024；更换长KV模型时必须同步更新该字段。
