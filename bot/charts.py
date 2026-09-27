"""Графіки для /week і /weight (PNG у памʼяті)."""

import io
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
GREEN, ORANGE, RED, INK, MUTED = "#2a9d62", "#e9a23b", "#d1495b", "#1f2933", "#8a94a6"


def _finish(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


def _style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=INK)


def week_chart(days: list[tuple[date, float]], target: float | None) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = [f"{WEEKDAYS[d.weekday()]}\n{d.day:02d}.{d.month:02d}" for d, _ in days]
    values = [v for _, v in days]
    colors = []
    for v in values:
        if not target or v == 0:
            colors.append(GREEN if v else MUTED)
        elif abs(v - target) <= target * 0.1:
            colors.append(GREEN)
        elif v < target:
            colors.append(ORANGE)
        else:
            colors.append(RED)
    bars = ax.bar(labels, values, color=colors, width=0.6)
    for bar, v in zip(bars, values):
        if v:
            ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.0f}",
                    ha="center", va="bottom", fontsize=9, color=INK)
    if target:
        ax.axhline(target, color=INK, linestyle="--", linewidth=1)
        ax.text(len(days) - 0.5, target, f" норма {target:.0f}", va="bottom",
                ha="right", fontsize=9, color=INK)
    ax.set_title("Калорії за тиждень", color=INK, fontsize=13, loc="left")
    ax.set_ylabel("ккал", color=INK)
    _style(ax)
    return _finish(fig)


def weight_chart(history: list[tuple[date, float]]) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(7, 4))
    xs = [d for d, _ in history]
    ys = [kg for _, kg in history]
    ax.plot(xs, ys, color=GREEN, marker="o", linewidth=2)
    ax.annotate(f"{ys[-1]:.1f} кг", (xs[-1], ys[-1]), textcoords="offset points",
                xytext=(0, 8), ha="center", color=INK)
    ax.set_title("Динаміка ваги", color=INK, fontsize=13, loc="left")
    ax.set_ylabel("кг", color=INK)
    fig.autofmt_xdate()
    _style(ax)
    return _finish(fig)
