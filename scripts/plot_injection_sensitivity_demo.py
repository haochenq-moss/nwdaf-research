#!/usr/bin/env python3
"""Create an illustrative preview of the planned injection-sensitivity plots."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt


def main() -> None:
    output = Path("docs/injection_sensitivity_preview.png")
    output.parent.mkdir(parents=True, exist_ok=True)

    short_levels = list(range(1, 11))
    short_percentages = [5.2, 3.1, 3.4, 3.8, 4.6, 4.3, 3.1, 4.9, 4.8, 6.0]
    extended_levels = list(range(1, 31))
    extended_percentages = [
        11.8, 12.0, 17.5, 11.2, 13.0, 10.5, 9.0, 11.7, 12.0, 13.8,
        11.0, 8.8, 13.5, 15.8, 14.8, 10.0, 15.0, 16.0, 14.0, 17.0,
        22.5, 27.2, 16.8, 18.0, 20.0, 26.8, 28.2, 16.0, 20.0, 31.5,
    ]

    figure, axes = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)
    for axis, levels, percentages, title in zip(
        axes,
        (short_levels, extended_levels),
        (short_percentages, extended_percentages),
        ("10-level preview", "30-level preview"),
    ):
        axis.bar(levels, percentages, color="#f2a23a", width=0.78)
        axis.set_title(title)
        axis.set_xlabel("Injection")
        axis.set_ylabel("Anomalies Percentage (%)")
        axis.set_ylim(0, 35)
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)

    figure.suptitle("Illustrative injection-sensitivity preview", fontsize=13)
    figure.text(
        0.5,
        -0.02,
        "Illustrative values only; replace with measured campaign data.",
        ha="center",
        fontsize=9,
        color="#666666",
    )
    figure.savefig(output, dpi=180, bbox_inches="tight")
    print(output)


if __name__ == "__main__":
    main()