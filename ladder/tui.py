"""Coloured terminal output. Degrades to plain text when piped or NO_COLOR."""
from __future__ import annotations

import os
import sys

_ON = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _ON else s


def dim(s):    return _c("2", s)
def bold(s):   return _c("1", s)
def gold(s):   return _c("38;5;214", s)
def green(s):  return _c("38;5;41", s)
def red(s):    return _c("38;5;203", s)
def blue(s):   return _c("38;5;75", s)


def rule(title: str = "", width: int = 58) -> str:
    if not title:
        return dim("─" * width)
    pad = max(0, width - len(title) - 3)
    return dim("── ") + bold(title) + " " + dim("─" * pad)


def ladder_bars(rung: int, max_rung: int, base: float, decimal: float) -> str:
    """Staircase of rungs, widths proportional to stake."""
    stakes, s = [], base
    for _ in range(max_rung):
        stakes.append(s)
        s *= decimal
    top = stakes[-1] or 1.0
    out = []
    for i in range(max_rung - 1, -1, -1):
        w = max(1, round(stakes[i] / top * 26))
        label = f"${stakes[i]:>9,.2f} -> ${stakes[i]*decimal:>10,.2f}"
        if i < rung:
            out.append(f"  {green('R%d' % i)} {green('█' * w)}{dim('·' * (26-w))}  {label}")
        elif i == rung:
            out.append(f"  {gold('R%d' % i)} {gold('▓' * w)}{dim('·' * (26-w))}  "
                       f"{bold(label)}  {gold('<- next')}")
        else:
            out.append(f"  {dim('R%d' % i)} {dim('░' * w)}{dim('·' * (26-w))}  {dim(label)}")
    return "\n".join(out)


def probbar(p: float, width: int = 22, breakeven: float | None = None) -> str:
    filled = max(0, min(width, round(p * width)))
    bar = ("█" * filled) + ("·" * (width - filled))
    col = green if (breakeven is None or p >= breakeven) else gold
    return col(bar)
