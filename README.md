# task26100541
## venue_booking

进程内场地预约候补分配库，由上层预订流程直接调用。

- 每个时段从开始占用到结束后 30 分钟（半开区间，终点本身不占用）。
- 请求整组成功或整组候补，不允许部分成功。
- 候补按提交顺序扫描：全部时段空闲即整组接纳，否则跳过继续看后面的。
- 每次提交/撤回后立即完成递补；撤回批次整体先生效再递补，批次内顺序无关。

```python
from venue_booking import BookingRequest, Slot, VenueAllocator

allocator = VenueAllocator()
allocator.submit(BookingRequest("req-1", "hall-a", (Slot(0, 3600),)))
allocator.withdraw(["req-1"])
snap = allocator.snapshot()  # snap.allocated / snap.waitlist
```

运行测试：`python3 -m pytest tests/ -q`
