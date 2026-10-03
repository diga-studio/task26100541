"""候补分配器：进程内保存状态，由上层预订流程直接调用。"""

from __future__ import annotations

from .models import AllocationSnapshot, Request, Slot


class BookingAllocator:
    """场地预约候补分配器。

    - submit: 提交一份请求（整组接纳或整组候补）。
    - withdraw: 成批撤回请求（已分配与候补可混合）。
    - snapshot: 读取当前分配结果。
    """

    def __init__(self) -> None:
        self._requests: dict[str, Request] = {}
        self._allocated: set[str] = set()
        self._waitlist: list[str] = []
        self._next_seq: int = 0

    def submit(self, request_id: str, space: str, slots: list[tuple[int, int]]) -> None:
        """提交预约请求。slots 为 (start, end) 绝对秒时间列表。"""
        if request_id in self._requests:
            raise ValueError(f"duplicate request id: {request_id}")
        if not slots:
            raise ValueError("request must contain at least one slot")
        slot_objs = tuple(
            sorted((Slot(start, end) for start, end in slots), key=lambda s: s.start)
        )
        request = Request(
            request_id=request_id,
            space=space,
            slots=slot_objs,
            seq=self._next_seq,
        )
        self._next_seq += 1
        self._requests[request_id] = request
        # 新请求先排入候补末尾，再统一递补，
        # 保证它不会越过更早且当前可接纳的候补。
        self._waitlist.append(request_id)
        self._promote()

    def withdraw(self, request_ids: list[str]) -> None:
        """成批撤回请求，整批生效后按原始顺序递补。"""
        # 先让整批撤回全部生效，再做递补；
        # 用集合处理，批次内标识顺序不影响结果。
        for request_id in set(request_ids):
            if request_id not in self._requests:
                continue
            del self._requests[request_id]
            self._allocated.discard(request_id)
        if self._waitlist:
            withdrawn = set(request_ids)
            self._waitlist = [rid for rid in self._waitlist if rid not in withdrawn]
        self._promote()

    def snapshot(self) -> AllocationSnapshot:
        """读取当前分配结果。"""
        allocated = {
            rid: self._requests[rid]
            for rid in sorted(self._allocated, key=lambda r: self._requests[r].seq)
        }
        return AllocationSnapshot(allocated=allocated, waitlisted=list(self._waitlist))

    def _promote(self) -> None:
        """按候补原始顺序扫描：整组可接纳即接纳，否则跳过继续。"""
        if not self._waitlist:
            return
        occupancy: dict[str, list[tuple[int, int]]] = {}
        for rid in self._allocated:
            request = self._requests[rid]
            intervals = occupancy.setdefault(request.space, [])
            for slot in request.slots:
                intervals.append((slot.start, slot.occupied_until))
        remaining: list[str] = []
        for rid in self._waitlist:
            request = self._requests[rid]
            intervals = occupancy.setdefault(request.space, [])
            if all(
                not _intersects(slot.start, slot.occupied_until, busy_start, busy_end)
                for slot in request.slots
                for busy_start, busy_end in intervals
            ):
                # 本轮接纳结果立即可见，后续候补据此判断。
                for slot in request.slots:
                    intervals.append((slot.start, slot.occupied_until))
                self._allocated.add(rid)
            else:
                remaining.append(rid)
        self._waitlist = remaining


def _intersects(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    """半开区间 [start, end) 是否相交。"""
    return start_a < end_b and start_b < end_a
