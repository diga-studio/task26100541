"""数据类型定义：预约请求与分配结果快照。"""

from __future__ import annotations

from dataclasses import dataclass, field


# 每个时段结束后额外占用 30 分钟（秒）。
BUFFER_SECONDS = 30 * 60


@dataclass(frozen=True)
class Slot:
    """一个具体时段，绝对秒时间，[start, end) 为活动本身。"""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("slot end must be greater than start")

    @property
    def occupied_until(self) -> int:
        """含缓冲的最终结束点（该时刻本身不占用）。"""
        return self.end + BUFFER_SECONDS


@dataclass
class Request:
    """一份预约请求：单一空间 + 若干互不冲突的时段。"""

    request_id: str
    space: str
    slots: tuple[Slot, ...]
    seq: int = 0


@dataclass
class AllocationSnapshot:
    """当前分配结果快照。"""

    allocated: dict[str, Request] = field(default_factory=dict)
    waitlisted: list[str] = field(default_factory=list)
