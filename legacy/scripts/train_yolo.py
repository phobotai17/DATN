"""
train_yolo.py
=============
Fine-tune YOLOv8s on the 4-class Vietnamese traffic dataset.

Run from repo root:
    python scripts/train_yolo.py
    python scripts/train_yolo.py --epochs 50 --imgsz 640 --device cpu
"""

import argparse
from pathlib import Path

from ultralytics import YOLO


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = REPO_ROOT / "vietnam-vehicle-detection-2" / "data.yaml"
DEFAULT_WEIGHTS = Path(__file__).resolve().parents[1] / "person_b/data/goi_ban_giao_B/models/best_v2.pt"


def main() -> None:
    ap = argparse.ArgumentParser(description="Fine-tune YOLOv8s for Vietnamese traffic")
    ap.add_argument("--data",    default=str(DEFAULT_DATA),    help="Path to data.yaml")
    ap.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="Pre-trained weights (.pt)")
    ap.add_argument("--epochs",  type=int, default=100,        help="Number of epochs")
    ap.add_argument("--imgsz",   type=int, default=640,        help="Input image size")
    ap.add_argument("--batch",   type=int, default=16,         help="Batch size (-1 = auto)")
    ap.add_argument("--device",  default="0",                  help="Device: 0 (GPU) or cpu")
    ap.add_argument("--name",    default="yolov8s_4class",     help="Run name under runs/detect/")
    ap.add_argument("--resume",  action="store_true",          help="Resume interrupted training")
    args = ap.parse_args()

    print(f"Loading model: {args.weights}")
    model = YOLO(args.weights)

    print(f"Training on: {args.data}")
    print(f"  epochs={args.epochs}, imgsz={args.imgsz}, batch={args.batch}, device={args.device}")

    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        name=args.name,
        resume=args.resume,
        # Augmentation — helps with the small dataset (~1k images)
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        flipud=0.0,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
        copy_paste=0.1,
        # Reproducibility
        seed=42,
        deterministic=True,
    )

    best = REPO_ROOT / "runs" / "detect" / args.name / "weights" / "best.pt"
    print(f"\nTraining complete. Best weights: {best}")
    print("Run validation:")
    print(f"  python scripts/validate_yolo.py --weights {best}")


if __name__ == "__main__":
    main()
