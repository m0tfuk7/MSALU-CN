from pathlib import Path
from unittest.mock import Mock, patch
import importlib

import yaml

from src.input.KeyBoardController import KeyBoardController
from src.input import InterceptionController


FAIL = []


def check(name, condition):
    print(f"  [{'OK ' if condition else 'FAIL'}] {name}")
    if not condition:
        FAIL.append(name)


def run_commands(commands, hooks=None, down_results=None, up_results=None):
    module = importlib.import_module("src.input.KeyBoardController")
    cfg_path = Path(__file__).resolve().parents[1] / "config" / "config_default.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["buff_skill"]["keys"] = []
    cfg["key"]["pickup"] = ""
    events = []
    frames = []
    down_results = iter(down_results or [])
    up_results = iter(up_results or [])

    def down(key):
        success = next(down_results, True)
        events.append(("down" if success else "down_failed", key))
        return success

    def up(key):
        success = next(up_results, True)
        events.append(("up" if success else "up_failed", key))
        return success

    with patch.object(module, "init_interception"), \
            patch.object(module.threading, "Thread"), \
            patch.object(module, "key_down", side_effect=down), \
            patch.object(module, "key_up", side_effect=up), \
            patch.object(module, "press_key",
                         side_effect=lambda key: events.append(("press", key))):
        kb = KeyBoardController(cfg)
        kb.is_game_window_active = Mock(return_value=True)
        kb._logged_first_key = True

        def next_frame():
            frames.append(list(events))
            index = len(frames)
            if index == len(commands):
                kb.is_terminated = True
                return
            if hooks and index in hooks:
                hooks[index](kb)
            kb.set_command(commands[index])

        kb.limit_fps = next_frame
        kb.set_command(commands[0])
        kb.run()
    return frames, events, kb


def main():
    for direction in ("left", "right", "up", "down"):
        command = (f"{direction} none none" if direction in ("left", "right")
                   else f"none {direction} none")
        frames, events, _ = run_commands([command] * 300)
        check(f"{direction}: 连续 300 轮只按下一次且中途不松开",
              frames[-1] == [("down", direction)])
        check(f"{direction}: 线程退出时释放方向键",
              ("up", direction) in events[len(frames[-1]):])

    frames, _, _ = run_commands(
        ["right up none", "right up none", "left down none",
         "none stop none", "none none none"])
    check("双轴可以同时保持按住", frames[1] == [("down", "right"), ("down", "up")])
    check("换向同轮先松旧方向再按新方向",
          frames[2][len(frames[1]):] == [
              ("up", "right"), ("down", "left"), ("up", "up"), ("down", "down")])
    check("none 和 stop 都立即松键且不重复发送",
          frames[3][len(frames[2]):] == [("up", "left"), ("up", "down")]
          and frames[4] == frames[3])

    frames, _, _ = run_commands(
        ["right none none"] * 3, hooks={1: lambda kb: kb.release_all_key()})
    check("外部释放后相同方向指令也会重新按下",
          frames[-1].count(("down", "right")) == 2)

    frames, _, _ = run_commands(
        ["right none none"] * 4,
        hooks={1: lambda kb: kb.toggle_enable(), 3: lambda kb: kb.toggle_enable()})
    check("热键暂停松键，恢复相同方向也不会漏按",
          frames[1] == frames[2] and frames[-1].count(("down", "right")) == 2)

    def lose_focus(kb):
        kb.is_game_window_active.return_value = False
        kb.foreground_window_title = Mock(return_value="test window")
        kb.t_last_fg_retry = float("inf")

    def regain_focus(kb):
        kb.is_game_window_active.return_value = True

    frames, _, _ = run_commands(
        ["right none none"] * 6, hooks={1: lose_focus, 4: regain_focus})
    check("失焦守卫释放方向，恢复焦点后相同方向重新按下",
          frames[3].count(("down", "right")) == 1
          and ("up", "right") in frames[3]
          and frames[-1].count(("down", "right")) == 2)

    frames, _, kb = run_commands(
        ["right none none"] * 4,
        hooks={1: lambda kb: kb.set_humanized_break(True),
               3: lambda kb: kb.set_humanized_break(False)})
    check("拟人停顿不按方向键，恢复后只补按一次",
          frames[1] == frames[2]
          and frames[-1].count(("down", "right")) == 2
          and not kb.humanized_break_active)

    for press_method in ("_press", "press_key"):
        frames, _, _ = run_commands(
            ["right none none"] * 3,
            hooks={1: lambda kb, method=press_method: getattr(kb, method)("RIGHT")})
        check(f"{press_method}: 点按同一方向键后不会误认为仍保持按住",
              frames[-1].count(("down", "right")) == 2)

    frames, _, kb = run_commands(
        ["right none none"] * 3, down_results=[False, True])
    check("按下失败会在下一轮重试，不缓存失败状态",
          frames[-1] == [("down_failed", "right"), ("down", "right")]
          and kb.n_key_sent == 1)

    frames, _, _ = run_commands(
        ["right none none", "left none none", "left none none"],
        up_results=[False, True])
    check("松开失败时不同时按反方向，下轮重试后再换向",
          frames[1] == [("down", "right"), ("up_failed", "right")]
          and frames[2][-2:] == [("up", "right"), ("down", "left")])

    with patch.object(InterceptionController, "interception") as driver, \
            patch.object(InterceptionController, "_report_key_failure") as report:
        check("驱动按下和松开入口返回成功状态",
              InterceptionController.key_down("left") is True
              and InterceptionController.key_up("left") is True)
        driver.key_down.side_effect = RuntimeError("test key down failure")
        driver.key_up.side_effect = RuntimeError("test key up failure")
        check("驱动失败返回失败状态且显式报告",
              InterceptionController.key_down("left") is False
              and InterceptionController.key_up("left") is False
              and report.call_count == 2)

    if FAIL:
        print(f"\nFAIL: {len(FAIL)} 项")
        return 1
    print("\n全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
