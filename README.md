# task26100541

场地预约候补分配库（纯进程内状态，无外部服务依赖）。

## 用法

```python
from booking import BookingAllocator

allocator = BookingAllocator()

# 提交请求：一个空间 + 若干 (start, end) 绝对秒时段，整组接纳或整组候补
allocator.submit("req-1", "hall-a", [(1_700_000_000, 1_700_003_600)])

# 成批撤回：已分配与候补可混合，批次内顺序不影响结果
allocator.withdraw(["req-1", "req-2"])

# 读取当前分配结果
snap = allocator.snapshot()
snap.allocated   # dict[request_id, Request]，按提交顺序
snap.waitlisted  # list[request_id]，候补原始顺序
```

## 规则

- 每个时段占用 `[start, end + 30min)`，最终结束点本身不占用；恰好 30 分钟后开始的下一活动可接纳。
- 同一空间内不同请求的占用区间不能相交；不同空间互不影响。
- 每次提交/撤回结束后立即按候补原始顺序递补：整组可接纳即接纳，否则跳过继续扫描；已获得的占用不会被收回。

## 测试

```bash
python3 -m pytest tests/ -q
```
