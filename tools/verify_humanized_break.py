import importlib
import threading
from unittest.mock import Mock, patch

from src.engine.MapleStoryAutoLevelUp import MapleStoryAutoBot
from src.input.KeyBoardController import KeyBoardController
from src.states.hunting import HuntingState
from src.utils.damage_counterattack import DamageCounterattack
from src.utils.humanized_break import HumanizedBreak, HumanizedBreakConfig
from src.utils.potions import press_potion


FAIL = []


def check(name, condition):
    print(f"  [{'OK ' if condition else 'FAIL'}] {name}")
    if not condition:
        FAIL.append(name)


def fixed_uniform(low, high):
    return low


def last_choice(values):
    return values[-1]


def make_keyboard():
    kb = KeyBoardController.__new__(KeyBoardController)
    kb._input_lock = threading.RLock()
    kb._held_direction_keys = set()
    kb.humanized_break_active = False
    kb.cmd_left_right = "right"
    kb.cmd_up_down = "up"
    kb.cmd_action = "attack"
    kb.attack_key = "a"
    kb.n_key_sent = 0
    return kb


def verify_priority():
    bot = MapleStoryAutoBot.__new__(MapleStoryAutoBot)
    bot.humanized_break = HumanizedBreak(
        HumanizedBreakConfig(
            enabled=True,
            interval_min_sec=1.0,
            interval_max_sec=1.0,
            duration_min_sec=10.0,
            duration_max_sec=10.0,
            random_keys=("right", "f9"),
        ),
        uniform=fixed_uniform,
    )
    bot._humanized_break_started_at = None
    bot.damage_counterattack = DamageCounterattack.from_dict({"enabled": True})
    bot.is_using_home_route = True
    bot.home_enter_t = 90.0
    bot.t_last_attack = 95.0
    bot.t_watch_dog = 96.0
    bot.cmd_move_x = "right"
    bot.cmd_move_y = "up"
    bot.cmd_action = "attack"
    bot.kb = make_keyboard()
    bot.update_cmd_by_route = Mock()
    bot.check_reach_goal = Mock()
    bot.update_cmd_by_mob_detection = Mock()
    bot.is_player_stuck = Mock(return_value=False)
    bot.handle_stuck = Mock()
    state = HuntingState("hunting", bot)
    module = importlib.import_module("src.input.KeyBoardController")

    with patch.object(module, "key_up") as release, \
            patch.object(module, "key_down") as down, \
            patch.object(module, "press_key") as press, \
            patch("src.engine.MapleStoryAutoLevelUp.time.monotonic") as clock:
        clock.return_value = 100.0
        check("回正过程中仍会安排停顿", not bot.apply_humanized_break())
        bot.damage_counterattack.observe_hp(100.0, 100.0)
        bot.damage_counterattack.observe_hp(99.0, 100.2)
        bot.damage_counterattack.observe_hp(98.0, 100.4)
        bot.damage_counterattack.decide(
            now=100.4, has_detected_monsters=False, attack_mode="directional",
            attack_ready=True, current_direction="right", turn_frames=3)
        check("测试前反击确实已激活", bot.damage_counterattack.active)

        clock.return_value = 101.0
        state.on_frame()
        check("回正和反击不能阻止到点停顿",
              bot.humanized_break.active and bot.kb.humanized_break_active)
        check("停顿取消反击但保留回正状态",
              not bot.damage_counterattack.active and bot.is_using_home_route)
        check("进入停顿立即释放方向和攻击键",
              [call.args[0] for call in release.call_args_list]
              == ["left", "right", "up", "down", "a"])
        check("停顿清空所有移动攻击指令",
              (bot.cmd_move_x, bot.cmd_move_y, bot.cmd_action)
              == ("none", "none", "none")
              and (bot.kb.cmd_left_right, bot.kb.cmd_up_down, bot.kb.cmd_action)
              == ("none", "none", "none"))
        check("旧随机键配置不再发送", not press.called and not down.called)

        bot.damage_counterattack.observe_hp(97.0, 101.2)
        bot.damage_counterattack.observe_hp(96.0, 101.4)
        clock.return_value = 110.999
        state.on_frame()
        check("连续受击不会提前结束完整的十秒停顿",
              bot.humanized_break.active and bot.kb.humanized_break_active)
        check("停顿期间不推进路线、终点、索敌或卡死处理",
              not any(fn.called for fn in (
                  bot.update_cmd_by_route, bot.check_reach_goal,
                  bot.update_cmd_by_mob_detection, bot.is_player_stuck,
                  bot.handle_stuck)))
        check("持续停顿不反复释放按键", release.call_count == 5)

        bot.damage_counterattack.observe_hp(95.0, 110.999)
        bot.damage_counterattack.observe_hp(94.0, 110.9995)
        clock.return_value = 111.0
        state.on_frame()
        check("完整十秒结束后恢复正常决策",
              not bot.humanized_break.active and not bot.kb.humanized_break_active
              and all(fn.call_count == 1 for fn in (
                  bot.update_cmd_by_route, bot.check_reach_goal,
                  bot.update_cmd_by_mob_detection, bot.is_player_stuck)))
        check("回正和看门狗计时均排除十秒停顿",
              (bot.home_enter_t, bot.t_last_attack, bot.t_watch_dog)
              == (100.0, 105.0, 106.0))
        check("恢复时不遗留停顿期间的掉血反击",
              not bot.damage_counterattack.decide(
                  now=111.0, has_detected_monsters=False,
                  attack_mode="directional", attack_ready=True,
                  current_direction="right", turn_frames=3).active)

        bot.humanized_break = HumanizedBreak.from_dict(None)
        state.on_frame()
        check("功能关闭时正常路线仍执行",
              bot.update_cmd_by_route.call_count == 2
              and not bot.kb.humanized_break_active)


def verify_keyboard_gate():
    kb = make_keyboard()
    module = importlib.import_module("src.input.KeyBoardController")
    with patch.object(module, "key_up"), \
            patch.object(module, "key_down") as down, \
            patch.object(module, "press_key") as press:
        kb.set_humanized_break(True)
        kb._kd("right")
        for key in ("a", "space", "z", "f1"):
            kb._press(key)
        check("键盘发送层拦截方向、攻击、跳跃、拾取及普通点按",
              not down.called and not press.called and kb.n_key_sent == 0)
        kb.is_game_window_active = Mock(return_value=True)
        check("停顿时保留真实喝药入口", press_potion("home", kb=kb))
        check("只发送了药水键",
              [call.args[0] for call in press.call_args_list] == ["home"]
              and kb.n_key_sent == 1)
        kb.is_game_window_active.return_value = False
        check("停顿喝药仍遵守前台守卫",
              not press_potion("home", kb=kb) and press.call_count == 1)

        kb.is_enable = True
        kb.is_terminated = False
        kb.is_game_window_active.return_value = True
        kb._fg_miss_count = 0
        kb._fg_blocked = False
        kb._logged_first_key = True
        kb._try_pickup = Mock()
        kb.cfg = {"buff_skill": {"keys": ["f1"], "cooldown": [60],
                                "action_cooldown": 5}}
        kb.t_last_buff_cast = [0]
        kb.t_last_skill = 0
        kb.limit_fps = Mock(side_effect=lambda: setattr(kb, "is_terminated", True))
        with patch.object(module.time, "time", return_value=100.0) as clock:
            kb.run()
            check("停顿时仍按冷却施放 Buff，并跳过拾取和方向键",
                  not kb._try_pickup.called and not down.called
                  and kb.t_last_buff_cast == [100.0] and kb.t_last_skill == 100.0
                  and [call.args[0] for call in press.call_args_list] == ["home", "f1"])

            clock.return_value = 159.999
            kb.is_terminated = False
            kb.run()
            check("Buff 冷却未到不会重复按键", press.call_count == 2)

            kb.t_last_skill = 157.0
            for now in (160.0, 162.0):
                clock.return_value = now
                kb.is_terminated = False
                kb.run()
            check("Buff 冷却已到仍遵守技能间隔", press.call_count == 2)

            clock.return_value = 162.001
            kb.is_terminated = False
            kb.run()
            check("冷却和技能间隔都满足后再次施放 Buff",
                  press.call_count == 3 and press.call_args.args == ("f1",)
                  and kb.t_last_buff_cast == [162.001])

            kb.is_game_window_active.return_value = False
            kb._fg_miss_count = 2
            kb._handle_game_window_not_active = Mock()
            clock.return_value = 300.0
            kb.is_terminated = False
            kb.run()
            check("停顿 Buff 仍遵守既有前台守卫",
                  press.call_count == 3
                  and kb._handle_game_window_not_active.call_count == 1)
            check("Buff 不会结束停顿或放行拾取及方向键",
                  kb.humanized_break_active
                  and not kb._try_pickup.called and not down.called)

        kb.set_humanized_break(False)
        kb._kd("right")
        kb._press("a")
        check("停顿结束后恢复发键",
              down.call_count == 1 and press.call_count == 4
              and kb.n_key_sent == 5)


def verify_input_serialization():
    kb = make_keyboard()
    module = importlib.import_module("src.input.KeyBoardController")
    sending = threading.Event()
    finish_send = threading.Event()
    pause_requested = threading.Event()
    paused = threading.Event()
    events = []

    def send(key):
        sending.set()
        finish_send.wait(2.0)
        events.append(("down", key))

    def pause():
        pause_requested.set()
        kb.set_humanized_break(True)
        paused.set()

    with patch.object(module, "key_down", side_effect=send), \
            patch.object(module, "key_up",
                         side_effect=lambda key: events.append(("up", key))):
        sender = threading.Thread(target=kb._kd, args=("right",))
        pauser = threading.Thread(target=pause)
        sender.start()
        check("模拟方向键正在发送", sending.wait(2.0))
        pauser.start()
        check("停顿请求已发出", pause_requested.wait(2.0))
        try:
            check("已有发键未完成时，松键操作不会抢跑", not paused.wait(0.05))
        finally:
            finish_send.set()
            sender.join(2.0)
            pauser.join(2.0)
        check("发键线程和停顿交接均完成",
              not sender.is_alive() and not pauser.is_alive() and paused.is_set())
        kb._kd("right")
        check("已有发键先完成、随后释放，旧方向不会再次按下",
              events == [("down", "right"), ("up", "left"), ("up", "right"),
                         ("up", "up"), ("up", "down"), ("up", "a")])


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

    verify_priority()
    verify_keyboard_gate()
    verify_input_serialization()

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
