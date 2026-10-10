from src.engine.MapleStoryAutoLevelUp import MapleStoryAutoBot
from src.utils.humanized_break import HumanizedBreak, HumanizedBreakConfig


FAIL = []


def check(name, condition):
    print(f"  [{'OK ' if condition else 'FAIL'}] {name}")
    if not condition:
        FAIL.append(name)


def fixed_uniform(low, high):
    return low


def last_choice(values):
    return values[-1]


def main():
    print("=== 拟人化随机停顿·自检 ===")

    state = HumanizedBreak(
        HumanizedBreakConfig(
            enabled=True,
            interval_min_sec=180.0,
            interval_max_sec=480.0,
            duration_min_sec=2.0,
            duration_max_sec=6.0,
            random_keys=("f9", "f10"),
        ),
        uniform=fixed_uniform,
        choice=last_choice,
    )
    scheduled = state.decide(now=10.0, allow_break=True)
    check("首次决策只安排下一次停顿",
          not scheduled.active and scheduled.event == "scheduled")
    check("排期事件包含下一次等待时间",
          scheduled.next_interval_sec == 180.0)
    check("固定随机源会安排在 3 分钟后",
          state.next_break_at == 190.0)
    started = state.decide(now=190.0, allow_break=True)
    check("到达触发时间后进入停顿",
          started.active and started.event == "started")
    check("停顿时长使用配置下限",
          started.duration_sec == 2.0)
    check("每次停顿只选择一个配置按键",
          started.key_to_press == "f10")
    during = state.decide(now=191.9, allow_break=True)
    check("停顿期间保持激活且不重复产生日志事件",
          during.active and during.event is None)
    stopped = state.decide(now=192.0, allow_break=True)
    check("停顿结束后交还正常逻辑",
          not stopped.active and stopped.event == "stopped")
    check("结束事件包含重新排期时间",
          stopped.next_interval_sec == 180.0)
    check("下一次间隔从停顿结束时重新计算",
          state.next_break_at == 372.0)

    state = HumanizedBreak(
        HumanizedBreakConfig(enabled=True),
        uniform=fixed_uniform,
    )
    state.decide(now=0.0, allow_break=True)
    state.decide(now=180.0, allow_break=True)
    interrupted = state.decide(now=180.5, allow_break=False)
    check("高优先级行为会立即结束停顿",
          not interrupted.active and interrupted.event == "stopped")

    state = HumanizedBreak(
        HumanizedBreakConfig(enabled=True),
        uniform=fixed_uniform,
    )
    state.decide(now=0.0, allow_break=False)
    rescheduled = state.decide(now=180.0, allow_break=False)
    check("到点时高优先级行为会跳过并重新排期",
          rescheduled.event == "rescheduled"
          and rescheduled.next_interval_sec == 180.0)

    class BotStub:
        pass

    bot = BotStub()
    bot.humanized_break = HumanizedBreak(
        HumanizedBreakConfig(
            enabled=True,
            interval_min_sec=0.1,
            interval_max_sec=0.1,
            duration_min_sec=2.0,
            duration_max_sec=2.0,
        ),
        uniform=fixed_uniform,
    )
    bot.is_using_home_route = False
    bot.damage_counterattack = type("Counterattack", (), {"active": False})()
    bot.cmd_move_x = "right"
    bot.cmd_move_y = "up"
    bot.cmd_action = "attack"
    bot.apply_humanized_break = (
        MapleStoryAutoBot.apply_humanized_break.__get__(bot))
    bot.apply_humanized_break()
    bot.humanized_break._next_break_at = 0.0
    applied = bot.apply_humanized_break()
    check("引擎接线会松开移动和攻击指令",
          applied
          and bot.cmd_move_x == "none"
          and bot.cmd_move_y == "none"
          and bot.cmd_action == "none")

    class KeyboardStub:
        def __init__(self):
            self.released = 0
            self.pressed = []

        def is_game_window_active(self):
            return True

        def release_all_key(self):
            self.released += 1

        def press_key(self, key):
            self.pressed.append(key)

    bot.kb = KeyboardStub()
    bot.humanized_break = HumanizedBreak(
        HumanizedBreakConfig(
            enabled=True,
            interval_min_sec=0.1,
            interval_max_sec=0.1,
            duration_min_sec=2.0,
            duration_max_sec=2.0,
            random_keys=("f9", "f10"),
        ),
        uniform=fixed_uniform,
        choice=last_choice,
    )
    bot.humanized_break.decide(now=0.0, allow_break=True)
    bot.humanized_break._next_break_at = 0.0
    applied = bot.apply_humanized_break()
    check("随机键发送前先释放已有按键",
          applied and bot.kb.released == 1)
    check("引擎只短按选中的一个键",
          bot.kb.pressed == ["f10"])

    parsed = HumanizedBreakConfig.from_dict(
        {"random_keys": " F9，f10, f9, "})
    check("字符串按键列表会清理、去重并统一小写",
          parsed.random_keys == ("f9", "f10"))

    for raw in (
        {"enabled": True, "interval_min_sec": 10, "interval_max_sec": 5},
        {"enabled": True, "duration_min_sec": 5, "duration_max_sec": 2},
    ):
        try:
            HumanizedBreakConfig.from_dict(raw)
        except ValueError:
            pass
        else:
            check("倒置的时间范围会被拒绝", False)
    check("倒置范围校验完成", True)

    if FAIL:
        print(f"\nFAIL: {len(FAIL)} 项")
        return 1
    print("\n全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
