"""
validate_yolo.py
================
Validate a trained YOLO model and print per-class mAP results.

Run from repo root:
    python scripts/validate_yolo.py
    python scripts/validate_yolo.py --weights person_b/data/goi_ban_giao_B/models/best_v2.pt
"""

import argparse
from pathlib import Path

from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEIGHTS = Path(__file__).resolve().parents[1] / "person_b/data/goi_ban_giao_B/models/best_v2.pt"
DEFAULT_DATA    = REPO_ROOT / "vietnam-vehicle-detection-2" / "data.yaml"


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate YOLOv8s on the 4-class dataset")
    ap.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="Path to best.pt")
    ap.add_argument("--data",    default=str(DEFAULT_DATA),    help="Path to data.yaml")
    ap.add_argument("--imgsz",   type=int, default=640,        help="Inference image size")
    ap.add_argument("--device",  default="0",                  help="Device: 0 or cpu")
    ap.add_argument("--split",   default="test",               help="Dataset split to evaluate")
    args = ap.parse_args()

    print(f"Validating: {args.weights}")
    model = YOLO(args.weights)

    metrics = model.val(
        data=args.data,
        imgsz=args.imgsz,
        device=args.device,
        split=args.split,
        verbose=True,
    )

    print("\n── Per-class mAP@0.5 ─────────────────────────")
    names = model.names
    ap_classes = metrics.box.ap_class_index if hasattr(metrics.box, 'ap_class_index') else list(range(len(metrics.box.ap50)))
    for idx, cls_idx in enumerate(ap_classes):
        p = metrics.box.p[idx]
        r = metrics.box.r[idx]
        map50 = metrics.box.ap50[idx]
        map_all = metrics.box.ap[idx]
        cls_name = names.get(cls_idx, f"class_{cls_idx}")
        print(f"  {cls_name:20s}  P={p:.3f}  R={r:.3f}  mAP50={map50:.3f}  mAP50-95={map_all:.3f}")

    print("\n── Overall ────────────────────────────────────")
    print(f"  mAP@0.5     : {metrics.box.map50:.4f}")
    print(f"  mAP@0.5:0.95: {metrics.box.map:.4f}")


if __name__ == "__main__":
    main()
