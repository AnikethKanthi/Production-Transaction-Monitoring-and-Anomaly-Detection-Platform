from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


def evaluate_scores(
    labels: NDArray[np.int64], scores: NDArray[np.float64], output_dir: Path, version: str
) -> dict[str, float | int]:
    normal = scores[labels == 0]
    anomalous = scores[labels == 1]
    if not len(normal) or not len(anomalous):
        raise ValueError("evaluation requires normal and anomalous rows")
    report: dict[str, float | int] = {
        "normal_count": int(len(normal)),
        "anomaly_count": int(len(anomalous)),
        "normal_mean_anomaly_score": float(normal.mean()),
        "anomaly_mean_anomaly_score": float(anomalous.mean()),
        "mean_score_lift": float(anomalous.mean() - normal.mean()),
        "anomaly_score_separation_rate": float(np.mean(anomalous[:, None] > normal[None, :])),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{version}.evaluation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_score_chart(normal, anomalous, output_dir / f"{version}.scores.svg")
    return report


def _write_score_chart(
    normal: NDArray[np.float64], anomalous: NDArray[np.float64], path: Path
) -> None:
    width, height, margin = 800, 420, 55
    values = np.concatenate((normal, anomalous))
    low, high = float(values.min()), float(values.max())
    if low == high:
        high = low + 1.0
    bins = np.linspace(low, high, 25)
    normal_hist, _ = np.histogram(normal, bins=bins)
    anomaly_hist, _ = np.histogram(anomalous, bins=bins)
    max_count = max(int(normal_hist.max()), int(anomaly_hist.max()), 1)
    plot_width, plot_height = width - 2 * margin, height - 2 * margin
    bar_width = plot_width / (len(bins) - 1)
    elements = []
    for index, (normal_count, anomaly_count) in enumerate(zip(normal_hist, anomaly_hist)):
        x = margin + index * bar_width
        normal_height = plot_height * int(normal_count) / max_count
        anomaly_height = plot_height * int(anomaly_count) / max_count
        elements.append(
            f'<rect x="{x:.2f}" y="{height - margin - normal_height:.2f}" '
            f'width="{bar_width:.2f}" height="{normal_height:.2f}" fill="#2563eb" opacity="0.65"/>'
        )
        elements.append(
            f'<rect x="{x:.2f}" y="{height - margin - anomaly_height:.2f}" '
            f'width="{bar_width:.2f}" height="{anomaly_height:.2f}" fill="#dc2626" opacity="0.65"/>'
        )
    horizontal_axis = (
        f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" '
        f'y2="{height - margin}" stroke="#111827"/>\n'
    )
    vertical_axis = (
        f'<line x1="{margin}" y1="{margin}" x2="{margin}" '
        f'y2="{height - margin}" stroke="#111827"/>\n'
    )
    low_label = (
        f'\n<text x="{margin}" y="{height - 15}" font-family="sans-serif" '
        f'font-size="12">{low:.3f}</text>\n'
    )
    high_label = (
        f'<text x="{width - margin}" y="{height - 15}" text-anchor="end" '
        f'font-family="sans-serif" font-size="12">{high:.3f}</text>\n'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        '<rect width="100%" height="100%" fill="white"/>\n'
        '<text x="400" y="28" text-anchor="middle" font-family="sans-serif" font-size="18">'
        "Isolation Forest anomaly-score distribution</text>\n"
        + horizontal_axis
        + vertical_axis
        + "\n".join(elements)
        + low_label
        + high_label
        + '<rect x="590" y="48" width="14" height="14" fill="#2563eb" opacity="0.65"/>'
        + '<text x="610" y="60" font-family="sans-serif" font-size="12">Normal</text>\n'
        + '<rect x="665" y="48" width="14" height="14" fill="#dc2626" opacity="0.65"/>'
        + '<text x="685" y="60" font-family="sans-serif" font-size="12">Anomalous</text>\n'
        + "</svg>\n"
    )
    path.write_text(svg, encoding="utf-8")
