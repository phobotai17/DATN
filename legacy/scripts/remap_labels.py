"""
remap_labels.py
===============
Remaps YOLO label files from the old 3-class schema to the new 4-class schema
required by the thesis, IN-PLACE on the dataset directory.

Old schema (vietnam-vehicle-detection-2 / data_v2):
    0 = Bus
    1 = Car
    2 = Motor_Wrong_Lane

New schema (thesis target):
    0 = motorbike   ← was Motor_Wrong_Lane (still motorbikes, just wrong-lane ones)
    1 = car         ← was Car
    2 = truck       ← NO data in current set (limitation, acknowledged)
    3 = bus         ← was Bus

Run from repo root:
    python scripts/remap_labels.py
    python scripts/remap_labels.py --dataset data_v2          # remap data_v2 too
    python scripts/remap_labels.py --dry-run                  # preview only
"""

import argparse
import shutil
from collections import Counter
from pathlib import Path

# ── mapping: old_class_index → new_class_index ────────────────────────────
CLASS_REMAP = {
    0: 3,   # Bus          → bus
    1: 1,   # Car          → car
    2: 0,   # Motor_Wrong_Lane → motorbike
}

OLD_NAMES = {0: "Bus", 1: "Car", 2: "Motor_Wrong_Lane"}
NEW_NAMES = {0: "motorbike", 1: "car", 2: "truck", 3: "bus"}

SPLITS = ["train", "valid", "val", "test"]


def remap_label_file(src: Path, dst: Path, remap: dict[int, int]) -> Counter:
    """Rewrite one label file applying the remap. Returns per-class counts."""
    lines_out = []
    counts = Counter()
    for line in src.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        old_cls = int(parts[0])
        new_cls = remap.get(old_cls)
        if new_cls is None:
            print(f"  [WARN] Unknown class {old_cls} in {src.name} — skipped")
            continue
        lines_out.append(" ".join([str(new_cls)] + parts[1:]))
        counts[new_cls] += 1
    dst.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    return counts


def update_data_yaml(dataset_root: Path, dry_run: bool) -> None:
    """Rewrite data.yaml with the new 4-class schema."""
    yaml_path = dataset_root / "data.yaml"
    if not yaml_path.exists():
        print(f"  [SKIP] No data.yaml found at {yaml_path}")
        return

    # Build new content (manual write, avoids pyyaml reformat issues)
    old_text = yaml_path.read_text(encoding="utf-8")
    print(f"\n  Old data.yaml:\n{old_text}")

    # Detect existing path/train/val/test lines to preserve them
    lines = old_text.splitlines()
    new_lines = []
    for line in lines:
        key = line.split(":")[0].strip()
        if key in ("nc", "names", "roboflow"):
            continue  # will be replaced
        new_lines.append(line)

    new_lines.append("nc: 4")
    new_lines.append("names:")
    for i, name in NEW_NAMES.items():
        new_lines.append(f"  - {name}")

    new_content = "\n".join(new_lines) + "\n"
    print(f"\n  New data.yaml:\n{new_content}")
    if not dry_run:
        yaml_path.write_text(new_content, encoding="utf-8")
        print(f"  Saved {yaml_path}")


def remap_dataset(dataset_root: Path, dry_run: bool) -> None:
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Remapping dataset: {dataset_root}")

    total_before: Counter = Counter()
    total_after: Counter = Counter()
    files_processed = 0

    for split in SPLITS:
        lbl_dir = dataset_root / split / "labels"
        if not lbl_dir.exists():
            continue

        label_files = sorted(lbl_dir.glob("*.txt"))
        if not label_files:
            continue

        print(f"\n  [{split}] {len(label_files)} label files")

        # Count before
        before: Counter = Counter()
        for lf in label_files:
            for line in lf.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split()
                if parts:
                    before[int(parts[0])] += 1

        for cls, cnt in sorted(before.items()):
            name = OLD_NAMES.get(cls, f"class_{cls}")
            print(f"    Before  → class {cls} [{name}]: {cnt}")
        total_before += before

        if dry_run:
            continue

        # Backup original labels
        backup_dir = dataset_root / split / "labels_original_backup"
        if not backup_dir.exists():
            shutil.copytree(lbl_dir, backup_dir)
            print(f"    Backed up originals → {backup_dir.name}/")

        # Remap in-place
        after: Counter = Counter()
        for lf in label_files:
            after += remap_label_file(lf, lf, CLASS_REMAP)
            files_processed += 1

        for cls, cnt in sorted(after.items()):
            name = NEW_NAMES.get(cls, f"class_{cls}")
            print(f"    After   → class {cls} [{name}]: {cnt}")
        total_after += after

    if not dry_run:
        update_data_yaml(dataset_root, dry_run=False)

    print(f"\n  Summary for {dataset_root.name}:")
    print(f"    Files processed: {files_processed}")
    if not dry_run:
        print("    Class counts after remapping:")
        for cls, cnt in sorted(total_after.items()):
            print(f"      {cls} [{NEW_NAMES.get(cls, '?')}]: {cnt} bboxes")
        print(f"\n  NOTE: Class 2 (truck) has 0 examples — "
              f"model will not detect trucks. "
              f"Add truck data later or merge with another dataset.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Remap YOLO labels to 4-class thesis schema")
    ap.add_argument(
        "--dataset",
        default="vietnam-vehicle-detection-2",
        help="Dataset folder name under repo root (default: vietnam-vehicle-detection-2)"
    )
    ap.add_argument("--dry-run", action="store_true", help="Preview only, no files changed")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    dataset_root = repo_root / args.dataset

    if not dataset_root.exists():
        print(f"ERROR: Dataset not found: {dataset_root}")
        return

    remap_dataset(dataset_root, dry_run=args.dry_run)

    if not args.dry_run:
        print("\nDone! Next step: re-train the traffic detector with the updated dataset.")
        print("  python scripts/train_yolo.py")


if __name__ == "__main__":
    main()
