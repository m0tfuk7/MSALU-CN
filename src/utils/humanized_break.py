from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass(frozen=True)
class HumanizedBreakConfig:
    enabled: bool = False
    interval_min_sec: float = 180.0
    interval_max_sec: float = 480.0
    duration_min_sec: float = 2.0
    duration_max_sec: float = 6.0
    random_keys: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: dict | None) -> "HumanizedBreakConfig":
        raw = raw or {}
        raw_keys = raw.get("random_keys", ())
        if isinstance(raw_keys, str):
            raw_keys = raw_keys.replace("，", ",").split(",")
        if not isinstance(raw_keys, (list, tuple)):
            raise ValueError("humanized_break.random_keys 必须是按键列表")
        random_keys = tuple(dict.fromkeys(
            str(key).strip().lower() for key in raw_keys if str(key).strip()
        ))
        cfg = cls(
            enabled=bool(raw.get("enabled", False)),
            interval_min_sec=float(raw.get("interval_min_sec", 180.0)),
            interval_max_sec=float(raw.get("interval_max_sec", 480.0)),
            duration_min_sec=float(raw.get("duration_min_sec", 2.0)),
            duration_max_sec=float(raw.get("duration_max_sec", 6.0)),
            random_keys=random_keys,
        )
        values = {
            "interval_min_sec": cfg.interval_min_sec,
            "interval_max_sec": cfg.interval_max_sec,
            "duration_min_sec": cfg.duration_min_sec,
            "duration_max_sec": cfg.duration_max_sec,
        }
        invalid = [name for name, value in values.items() if value <= 0]
        if invalid:
            raise ValueError(
                "humanized_break 参数必须大于 0: " + ", ".join(invalid))
        if cfg.interval_min_sec > cfg.interval_max_sec:
            raise ValueError("humanized_break 触发间隔最小值不能大于最大值")
        if cfg.duration_min_sec > cfg.duration_max_sec:
            raise ValueError("humanized_break 停顿时间最小值不能大于最大值")
        return cfg


@dataclass(frozen=True)
class HumanizedBreakDecision:
    active: bool = False
    event: str | None = None
    reason: str = ""
    duration_sec: float = 0.0
    key_to_press: str | None = None
    next_interval_sec: float = 0.0


class HumanizedBreak:
    """Schedule non-blocking randomized breaks during normal patrol."""

    def __init__(
        self,
        config: HumanizedBreakConfig,
        uniform: Callable[[float, float], float] = random.uniform,
        choice: Callable[[Sequence[str]], str] = random.choice,
    ):
        self.config = config
        self._uniform = uniform
        self._choice = choice
        self._next_break_at: float | None = None
        self._active_until: float | None = None

    @classmethod
    def from_dict(cls, raw: dict | None) -> "HumanizedBreak":
        return cls(HumanizedBreakConfig.from_dict(raw))

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def active(self) -> bool:
        return self._active_until is not None

    @property
    def next_break_at(self) -> float | None:
        return self._next_break_at

    def decide(
        self,
        *,
        now: float,
        allow_break: bool,
    ) -> HumanizedBreakDecision:
        if not self.enabled:
            return HumanizedBreakDecision(reason="功能未启用")

        if self.active:
            if not allow_break:
                self._active_until = None
                interval = self._schedule_next(now)
                return HumanizedBreakDecision(
                    event="stopped",
                    reason="高优先级行为接管",
                    next_interval_sec=interval,
                )
            assert self._active_until is not None
            if now >= self._active_until:
                self._active_until = None
                interval = self._schedule_next(now)
                return HumanizedBreakDecision(
                    event="stopped",
                    reason="随机停顿结束",
                    next_interval_sec=interval,
                )
            return HumanizedBreakDecision(active=True, reason="随机停顿中")

        scheduled_interval = 0.0
        if self._next_break_at is None:
            scheduled_interval = self._schedule_next(now)

        assert self._next_break_at is not None
        if not allow_break:
            if now >= self._next_break_at:
                interval = self._schedule_next(now)
                return HumanizedBreakDecision(
                    event="rescheduled",
                    reason="当前正在执行高优先级行为",
                    next_interval_sec=interval,
                )
            return HumanizedBreakDecision(
                event="scheduled" if scheduled_interval else None,
                reason="当前状态不允许停顿",
                next_interval_sec=scheduled_interval,
            )
        if now < self._next_break_at:
            return HumanizedBreakDecision(
                event="scheduled" if scheduled_interval else None,
                reason="等待下次随机停顿",
                next_interval_sec=scheduled_interval,
            )

        duration = self._uniform(
            self.config.duration_min_sec,
            self.config.duration_max_sec,
        )
        key_to_press = (
            self._choice(self.config.random_keys)
            if self.config.random_keys
            else None
        )
        self._active_until = now + duration
        self._next_break_at = None
        return HumanizedBreakDecision(
            active=True,
            event="started",
            reason="开始随机停顿",
            duration_sec=duration,
            key_to_press=key_to_press,
        )

    def _schedule_next(self, now: float) -> float:
        interval = self._uniform(
            self.config.interval_min_sec,
            self.config.interval_max_sec,
        )
        self._next_break_at = now + interval
        return interval
