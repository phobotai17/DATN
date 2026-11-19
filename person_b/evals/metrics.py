"""Metrics for hand-labelled traffic observations."""
from collections import defaultdict
from math import sqrt
from statistics import mean


def errors(pairs):
    pairs = list(pairs)
    delta = [pred - actual for actual, pred in pairs]
    percent = [100 * abs(pred - actual) / abs(actual)
               for actual, pred in pairs if actual != 0]
    return {
        "samples": len(pairs),
        "mae": mean(map(abs, delta)) if delta else None,
        "rmse": sqrt(mean(d * d for d in delta)) if delta else None,
        "bias": mean(delta) if delta else None,
        "mape_percent": mean(percent) if percent else None,
        "mape_samples": len(percent),
    }


def event_scores(predictions, truth, tolerance):
    """Match once per event by kind and, when supplied, vehicle identity."""
    groups = defaultdict(lambda: [[], []])
    for side, events in enumerate((predictions, truth)):
        for kind, t, *identity in events:
            groups[(kind, *identity)][side].append(t)
    totals = [0, 0, 0]
    delays = []
    for predicted, actual in groups.values():
        p, a = sorted(predicted), sorted(actual)
        i = j = tp = 0
        while i < len(p) and j < len(a):
            if p[i] < a[j] - tolerance:
                i += 1
            elif p[i] > a[j] + tolerance:
                j += 1
            else:
                tp += 1
                delays.append(p[i] - a[j])
                i += 1
                j += 1
        totals[0] += tp
        totals[1] += len(p) - tp
        totals[2] += len(a) - tp
    tp, fp, fn = totals
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None,
        "mean_delay_s": mean(delays) if delays else None,
        "mean_absolute_timing_error_s": mean(map(abs, delays)) if delays else None,
    }
