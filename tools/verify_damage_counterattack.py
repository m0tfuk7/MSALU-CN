import time

from src.engine.MapleStoryAutoLevelUp import MapleStoryAutoBot
from src.utils.damage_counterattack import DamageCounterattack


FAIL = []


def check(name, condition):
    print(f"  [{'OK ' if condition else 'FAIL'}] {name}")
    if not condition:
        FAIL.append(name)


def counterattack(**overrides):
    cfg = {
        "enabled": True,
        "confirm_drops": 2,
        "detect_window_sec": 0.8,
        "min_single_drop_percent": 0.5,
        "min_total_drop_percent": 1.5,
        "quiet_exit_sec": 1.2,
        "max_duration_sec": 4.0,
        "direction_switch_sec": 0.8,
    }
    cfg.update(overrides)
    return DamageCounterattack.from_dict(cfg)


def decide(state, now, monsters=False, mode="aoe_skill", ready=True,
           direction="right", turn_frames=3):
    return state.decide(
        now=now,
        has_detected_monsters=monsters,
        attack_mode=mode,
        attack_ready=ready,
        current_direction=direction,
        turn_frames=turn_frames,
    )


def main():
    print("=== 重叠怪受击反击·自检 ===")

    state = counterattack()
    state.observe_hp(100.0, 0.0)
    state.observe_hp(99.0, 0.2)
    check("单次掉血不会误触", not decide(state, 0.2).active)
    state.observe_hp(98.0, 0.4)
    decision = decide(state, 0.4)
    check("连续两次且累计达阈值后进入反击", decision.active)
    check("AOE 反击暂停移动并攻击",
          decision.move_x == "none" and decision.should_attack)

    decision = decide(state, 0.5, monsters=True)
    check("重新识别到怪物后立即交还正常索敌",
          not decision.active and decision.event == "stopped")

    state = counterattack()
    state.observe_hp(100.0, 0.0)
    state.observe_hp(99.0, 0.2)
    state.observe_hp(98.0, 0.4)
    decide(state, 0.4)
    decision = decide(state, 1.61)
    check("超过静默时间未掉血后恢复巡逻",
          not decision.active and decision.reason == "持续未再掉血")

    state = counterattack()
    state.observe_hp(100.0, 0.0)
    state.observe_hp(None, 0.1)
    state.observe_hp(99.0, 0.2)
    state.observe_hp(98.8, 0.4)
    check("无效读数和小幅波动不会凑够触发条件",
          not decide(state, 0.4).active)

    state = counterattack(direction_switch_sec=0.5)
    state.observe_hp(100.0, 0.0)
    state.observe_hp(99.0, 0.1)
    state.observe_hp(98.0, 0.2)
    first = decide(state, 0.2, mode="directional", direction="left")
    switched = decide(state, 0.71, mode="directional", direction="left")
    check("方向攻击先沿当前朝向出招", first.should_attack)
    check("持续受击后换边时先转身、不同时出招",
          switched.move_x == "right" and not switched.should_attack)

    class BotStub:
        pass

    bot = BotStub()
    bot.cfg = {
        "bot": {"attack": "aoe_skill"},
        "directional_attack": {"turn_frames": 3},
    }
    bot.damage_counterattack = counterattack()
    bot.t_last_attack = 0.0
    bot.cmd_move_x = "left"
    bot.cmd_move_y = "down"
    bot.cmd_move_x_last = "left"
    bot.cmd_action = "none"
    bot._apply_damage_counterattack = (
        MapleStoryAutoBot._apply_damage_counterattack.__get__(bot))
    now = time.monotonic()
    bot.damage_counterattack.observe_hp(100.0, now - 0.3)
    bot.damage_counterattack.observe_hp(99.0, now - 0.2)
    bot.damage_counterattack.observe_hp(98.0, now - 0.1)
    applied = bot._apply_damage_counterattack(0.1)
    check("引擎接线会覆盖巡逻并生成攻击指令",
          applied
          and bot.cmd_move_x == "none"
          and bot.cmd_move_y == "none"
          and bot.cmd_action == "attack"
          and bot.t_last_attack > 0)

    if FAIL:
        print(f"\nFAIL: {len(FAIL)} 项")
        return 1
    print("\n全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
