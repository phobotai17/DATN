"""Compare five-minute forecasts on chronological real-video counts."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from evals.benchmark import read_csv, write_csv
from evals.metrics import errors
from src.forecast_truth import read_count_labels
from src.forecasting import TrafficRNN

HISTORY = 60
HORIZON = 300


def history_at(counts, origin):
    return np.asarray([counts[s] for s in range(origin-HISTORY+1, origin+1)], dtype=np.float32)


def fit_gru(counts, cutoff, epochs):
    origins = [t for t in sorted(counts) if t+HORIZON < cutoff and t+HORIZON in counts
               and all(s in counts for s in range(t-HISTORY+1, t+1))]
    if not origins:
        raise ValueError("Insufficient pre-cutoff observations to train a 5-minute forecast")
    scale = max(1., max(v for t, v in counts.items() if t < cutoff))
    inputs = torch.tensor(np.stack([history_at(counts, t) for t in origins])/scale).unsqueeze(-1)
    targets = torch.tensor([counts[t+HORIZON]/scale for t in origins], dtype=torch.float32)
    model = TrafficRNN("GRU", hidden_dim=16, num_layers=1, output_dim=1, dropout=0.)
    optimizer = torch.optim.Adam(model.parameters(), lr=.005)
    for _ in range(epochs):
        for indices in torch.randperm(len(inputs)).split(32):
            optimizer.zero_grad()
            loss = torch.nn.functional.mse_loss(model(inputs[indices]).flatten(), targets[indices])
            loss.backward()
            optimizer.step()
    return model.eval(), scale, len(inputs)


def evaluate(rows, labels, cutoff, epochs):
    zones = {}
    for row in rows:
        if row.get("observed", "true").lower() in {"true", "1"}:
            by_second = zones.setdefault(row["zone"], {})
            second = float(row["time_s"])
            if not second.is_integer() or int(second) in by_second:
                raise ValueError("Expected unique zone observations at integer video seconds")
            by_second[int(second)] = int(row["total"])
    results, training = [], {}
    for zone in sorted({zone for _, zone in labels}):
        counts = zones.get(zone, {})
        valid = [(target, actual) for (target, name), actual in sorted(labels.items())
                 if name == zone and target-HORIZON-HISTORY+1 >= cutoff]
        if not valid:
            raise ValueError(f"No held-out forecast windows for {zone}")
        model, scale, training[zone] = fit_gru(counts, cutoff, epochs)
        for target, actual in valid:
            origin = target-HORIZON
            recent = history_at(counts, origin)
            with torch.inference_mode():
                gru = max(0., model(torch.tensor(recent/scale).reshape(1, -1, 1)).item()*scale)
            results.append(dict(zone=zone, origin=origin, target=target, actual=actual,
                                persistence=float(recent[-1]), mean_60s=float(recent.mean()), gru=gru))
    scoring = {name: errors((r["actual"], r[name]) for r in results)
               for name in ("persistence", "mean_60s", "gru")}
    return results, {"metrics": scoring, "training_windows_by_zone": training}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--cutoff", type=int, required=True)
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.epochs <= 0 or args.cutoff < HISTORY+HORIZON:
        parser.error("Need positive epochs and a cutoff after the first training window")
    torch.manual_seed(42)
    torch.set_num_threads(1)
    with args.labels.open(encoding="utf-8-sig", newline="") as labels:
        truth = read_count_labels(labels)
    rows, report = evaluate(read_csv(args.observations, ("time_s", "zone", "total")),
                            truth, args.cutoff, args.epochs)
    report.update(history_seconds=HISTORY, horizon_seconds=HORIZON, cutoff=args.cutoff,
                  observations=str(args.observations), labels=str(args.labels), epochs=args.epochs)
    args.out.mkdir(parents=True)
    write_csv(args.out / "predictions.csv", rows, tuple(rows[0]))
    (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
