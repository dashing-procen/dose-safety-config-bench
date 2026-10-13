"""Headline figure: same model, thinking off versus on.

Left panel: share of the 60 limit-violating doses the model ALLOWED.
Right panel: share of the 60 within-limit doses the model BLOCKED.
Reads results/summary.json. Writes figures/thinking_off_vs_on.png and .svg.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OFF = "#eb6834"
ON = "#2a78d6"
INK = "#0b0b0b"
MUTED = "#52514e"
HAIR = "#c8c7c0"
SURFACE = "#fcfcfb"

# Display order is set after load, by thinking-off violation rate.
NAMES = {
    "deepseek-v4-pro-0813": "DeepSeek-V4-Pro",
    "nemotron-3-120b-a12b": "Nemotron-3 120B",
    "gemma-4-26b-a4b-it": "Gemma-4 26B",
    "qwen3.8-27b": "Qwen3.8 27B",
}


def pct(fraction: str) -> float:
    num, den = (int(part) for part in fraction.split("/"))
    return 100.0 * num / den


def label(value: float) -> str:
    return "0" if value == 0 else f"{value:.1f}"


def main() -> None:
    rows = {r["config"]: r for r in json.loads((ROOT / "results" / "summary.json").read_text())}
    pairs = []
    for key, name in NAMES.items():
        off, on = rows[f"{key}__think_off"], rows[f"{key}__think_on"]
        pairs.append(
            {
                "name": name,
                "viol_off": pct(off["viol_allowed"]),
                "viol_on": pct(on["viol_allowed"]),
                "block_off": pct(off["false_block"]),
                "block_on": pct(on["false_block"]),
            }
        )
    pairs.sort(key=lambda p: p["viol_off"])  # bottom -> top

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
            "axes.linewidth": 0.6,
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 3.9), sharey=True)
    fig.patch.set_facecolor(SURFACE)
    panels = (
        (axes[0], "viol_off", "viol_on", "Limit-violating doses allowed"),
        (axes[1], "block_off", "block_on", "Within-limit doses blocked"),
    )
    for ax, off_key, on_key, title in panels:
        ax.set_facecolor(SURFACE)
        for y, pair in enumerate(pairs):
            a, b = pair[off_key], pair[on_key]
            ax.plot([a, b], [y, y], color=HAIR, lw=2.4, zorder=1, solid_capstyle="round")
            ax.scatter([a], [y], s=70, color=OFF, zorder=3, linewidths=0)
            ax.scatter([b], [y], s=70, color=ON, zorder=3, linewidths=0)
            if abs(a - b) < 0.5:
                ax.annotate(label(a), (a, y), textcoords="offset points", xytext=(9, 0),
                            ha="left", va="center", color=INK, fontsize=8)
            elif abs(a - b) < 14:
                ax.annotate(label(a), (a, y), textcoords="offset points", xytext=(0, 8),
                            ha="center", va="bottom", color=OFF, fontsize=8)
                ax.annotate(label(b), (b, y), textcoords="offset points", xytext=(0, -9),
                            ha="center", va="top", color=ON, fontsize=8)
            else:
                for val, color in ((a, OFF), (b, ON)):
                    if val <= 8:
                        ax.annotate(label(val), (val, y), textcoords="offset points", xytext=(6, 7),
                                    ha="left", va="bottom", color=color, fontsize=8)
                    elif val >= 92:
                        ax.annotate(label(val), (val, y), textcoords="offset points", xytext=(-2, 7),
                                    ha="right", va="bottom", color=color, fontsize=8)
                    else:
                        ax.annotate(label(val), (val, y), textcoords="offset points", xytext=(0, 8),
                                    ha="center", va="bottom", color=color, fontsize=8)
        ax.set_xlim(-6, 112)
        ax.set_ylim(-0.65, len(pairs) - 0.35)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_xlabel("Percent of 60 cases", color=MUTED, fontsize=9)
        ax.set_title(title, loc="left", color=INK, fontsize=11, pad=12)
        ax.tick_params(axis="x", colors=MUTED, labelsize=8, length=3)
        ax.tick_params(axis="y", length=0, labelsize=10, colors=INK)
        ax.spines["bottom"].set_color("#d9d8d2")
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
    axes[0].set_yticks(range(len(pairs)))
    axes[0].set_yticklabels([p["name"] for p in pairs])
    axes[1].tick_params(axis="y", left=False)

    handles = [
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=OFF, markersize=8, label="Thinking off"),
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=ON, markersize=8, label="Thinking on"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, fontsize=9,
               bbox_to_anchor=(0.55, -0.02), labelcolor=INK)
    fig.suptitle("Same weights. Only the thinking switch changes.", x=0.02, ha="left",
                 color=INK, fontsize=13, fontweight="medium")
    fig.tight_layout(rect=(0, 0.06, 1, 0.90))
    out = ROOT / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "thinking_off_vs_on.png", dpi=200, facecolor=SURFACE)
    fig.savefig(out / "thinking_off_vs_on.svg", facecolor=SURFACE)
    print(out / "thinking_off_vs_on.png")


if __name__ == "__main__":
    main()
