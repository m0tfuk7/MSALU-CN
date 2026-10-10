from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class DamageCounterattackConfig:
    enabled: bool = False
    confirm_drops: int = 2
    detect_window_sec: float = 0.8
    min_single_drop_percent: float = 0.5
    min_total_drop_percent: float = 1.5
    quiet_exit_sec: float = 1.2
    max_duration_sec: float = 4.0
    direction_switch_sec: float = 0.8

    @classmethod
    def from_dict(cls, raw: dict | None) -> "DamageCounterattackConfig":
        raw = raw or {}
        cfg = cls(
            enabled=bool(raw.get("enabled", False)),
            confirm_drops=int(raw.get("confirm_drops", 2)),
            detect_window_sec=float(raw.get("detect_window_sec", 0.8)),
            min_single_drop_percent=float(
                raw.get("min_single_drop_percent", 0.5)),
            min_total_drop_percent=float(
                raw.get("min_total_drop_percent", 1.5)),
            quiet_exit_sec=float(raw.get("quiet_exit_sec", 1.2)),
            max_duration_sec=float(raw.get("max_duration_sec", 4.0)),
            direction_switch_sec=float(raw.get("direction_switch_sec", 0.8)),
        )
        positive = {
            "confirm_drops": cfg.confirm_drops,
            "detect_window_sec": cfg.detect_window_sec,
            "min_single_drop_percent": cfg.min_single_drop_percent,
            "min_total_drop_percent": cfg.min_total_drop_percent,
            "quiet_exit_sec": cfg.quiet_exit_sec,
            "max_duration_sec": cfg.max_duration_sec,
            "direction_switch_sec": cfg.direction_switch_sec,
        }
        invalid = [name for name, value in positive.items() if value <= 0]
        if invalid:
            raise ValueError(
                "damage_counterattack 参数必须大于 0: " + ", ".join(invalid))
        return cfg


@dataclass(frozen=True)
class CounterattackDecision:
    active: bool = False
    should_attack: bool = False
    move_x: str = "none"
    event: str | None = None
    reason: str = ""


class DamageCounterattack:
    """Detect repeated HP loss and provide a temporary fallback attack decision."""

    def __init__(self, config: DamageCounterattackConfig):
        self.config = config
        self._previous_hp: float | None = None
        self._drops: deque[tuple[float, float]] = deque()
        self._active_since: float | None = None
        self._last_damage_at: float | None = None
        self._direction = "right"
        self._direction_since = 0.0
        self._turn_frames_left = 0

    @classmethod
    def from_dict(cls, raw: dict | None) -> "DamageCounterattack":
        return cls(DamageCounterattackConfig.from_dict(raw))

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    @property
    def active(self) -> bool:
        return self._active_since is not None

    def observe_hp(self, hp_percent: float | None, now: float) -> None:
        if not self.enabled or hp_percent is None:
            return
        hp = float(hp_percent)
        if not 0 < hp <= 100:
            return

        previous = self._previous_hp
        self._previous_hp = hp
        if previous is None:
            return

        delta = previous - hp
        if delta >= self.config.min_single_drop_percent:
            self._drops.append((now, delta))
            if self.active:
                self._last_damage_at = now
        elif delta <= -self.config.min_single_drop_percent:
            self._drops.clear()
        self._prune_drops(now)

    def decide(
        self,
        *,
        now: float,
        has_detected_monsters: bool,
        attack_mode: str,
        attack_ready: bool,
        current_direction: str,
        turn_frames: int,
    ) -> CounterattackDecision:
        if not self.enabled:
            return CounterattackDecision(reason="功能未启用")
        if has_detected_monsters:
            stopped = self.cancel()
            return CounterattackDecision(
                event="stopped" if stopped else None,
                reason="已恢复正常怪物索敌",
            )

        self._prune_drops(now)
        event = None
        if not self.active:
            if not self._damage_confirmed():
                return CounterattackDecision(reason="等待连续掉血确认")
            self._active_since = now
            self._last_damage_at = self._drops[-1][0]
            self._direction = (
                current_direction if current_direction in ("left", "right")
                else "right"
            )
            self._direction_since = now
            self._turn_frames_left = (
                0 if current_direction == self._direction
                else max(1, int(turn_frames))
            )
            self._drops.clear()
            event = "started"

        assert self._active_since is not None
        assert self._last_damage_at is not None
        if now - self._active_since >= self.config.max_duration_sec:
            self.cancel()
            return CounterattackDecision(
                event="stopped", reason="达到最长反击时间")
        if now - self._last_damage_at >= self.config.quiet_exit_sec:
            self.cancel()
            return CounterattackDecision(
                event="stopped", reason="持续未再掉血")

        if attack_mode == "aoe_skill":
            return CounterattackDecision(
                active=True,
                should_attack=attack_ready,
                event=event,
                reason="未识别到怪但检测到持续掉血",
            )

        if attack_mode != "directional":
            self.cancel()
            return CounterattackDecision(
                event="stopped",
                reason=f"不支持的攻击模式: {attack_mode}",
            )

        if now - self._direction_since >= self.config.direction_switch_sec:
            self._direction = "left" if self._direction == "right" else "right"
            self._direction_since = now
            self._turn_frames_left = max(1, int(turn_frames))

        if self._turn_frames_left > 0:
            self._turn_frames_left -= 1
            return CounterattackDecision(
                active=True,
                move_x=self._direction,
                event=event,
                reason=f"向{self._direction}侧转身反击",
            )

        return CounterattackDecision(
            active=True,
            should_attack=attack_ready,
            event=event,
            reason=f"向{self._direction}侧反击",
        )

    def cancel(self) -> bool:
        was_active = self.active
        self._active_since = None
        self._last_damage_at = None
        self._turn_frames_left = 0
        self._drops.clear()
        return was_active

    def _prune_drops(self, now: float) -> None:
        cutoff = now - self.config.detect_window_sec
        while self._drops and self._drops[0][0] < cutoff:
            self._drops.popleft()

    def _damage_confirmed(self) -> bool:
        return (
            len(self._drops) >= self.config.confirm_drops
            and sum(drop for _, drop in self._drops)
            >= self.config.min_total_drop_percent
        )
