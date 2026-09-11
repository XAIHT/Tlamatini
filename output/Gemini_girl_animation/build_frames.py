"""Deterministically split and register the supplied 2x2 portrait sheet."""
from pathlib import Path
import hashlib
import json
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
SOURCE = Path(r"C:\Users\angel\OneDrive\Pictures\Gemini_Generated_Image_2_be_splitted.jpg")
NAMES = [
    "01_eyes_open_smiling.png",
    "02_eyes_open_neutral.png",
    "03_eyes_closed_smiling.png",
    "04_eyes_closed_neutral.png",
]


def main():
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    source = Image.open(SOURCE).convert("RGB")
    assert source.size == (2048, 2048), source.size
    exact_dir = ROOT / "exact_crops"
    exact_dir.mkdir(exist_ok=True)
    boxes = [(x, y, x + 1024, y + 1024) for y in (0, 1024) for x in (0, 1024)]
    frames = [np.array(source.crop(box)) for box in boxes]
    grays = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255 for f in frames]

    # Estimate only translation from stable hair and armor, not moving eyes/mouth.
    mask = np.zeros((1024, 1024), dtype=np.uint8)
    mask[35:995, 70:950] = 255
    mask[240:725, 270:720] = 0
    inset = 6
    sample_scale = (1024 - 2 * inset) / 1024
    metadata = []
    registered = []
    for i, (frame, name, box) in enumerate(zip(frames, NAMES, boxes)):
        Image.fromarray(frame).save(exact_dir / name, optimize=True)
        warp = np.eye(2, 3, dtype=np.float32)
        score = 1.0
        if i:
            score, warp = cv2.findTransformECC(
                grays[0], grays[i], warp, cv2.MOTION_TRANSLATION,
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-7),
                mask, 5,
            )
        dx, dy = (float(v) for v in warp[:, 2])
        # Every image uses the SAME six-pixel inset and SAME output scale.
        # Pixel-center mapping combines registration and resizing in one sample.
        mapping = np.array([
            [sample_scale, 0, inset + (sample_scale - 1) / 2 + dx],
            [0, sample_scale, inset + (sample_scale - 1) / 2 + dy],
        ], dtype=np.float32)
        # Four-pixel Lanczos support stays inside the original quadrant.
        corners = np.array([[0, 0, 1], [1023, 1023, 1]], np.float32) @ mapping.T
        assert corners.min() >= 3 and corners.max() <= 1020, corners
        aligned = cv2.warpAffine(
            frame, mapping, (1024, 1024),
            flags=cv2.INTER_LANCZOS4 | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REFLECT_101,
        )
        Image.fromarray(aligned).save(ROOT / name, optimize=True)
        registered.append(aligned)
        check = np.array(Image.open(ROOT / name))
        assert check.shape == (1024, 1024, 3)
        assert np.array_equal(check, aligned)
        assert np.array_equal(np.array(Image.open(exact_dir / name)), frame)
        metadata.append({
            "file": name, "width": 1024, "height": 1024,
            "source_crop_box_xyxy": box,
            "source_offset_from_reference_px": [dx, dy],
            "applied_translation_before_common_scale_px": [-dx, -dy],
            "stable_region_correlation": float(score),
            "output_to_source_sampling_matrix": mapping.tolist(),
            "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
        })

    # Sprite has the same row-major ordering as the original supplied sheet.
    sprite = Image.new("RGB", (2048, 2048))
    for i, arr in enumerate(registered):
        sprite.paste(Image.fromarray(arr), ((i % 2) * 1024, (i // 2) * 1024))
    sprite.save(ROOT / "sprite_2x2.png", optimize=True)
    for i, arr in enumerate(registered):
        tile = np.array(sprite.crop(boxes[i]))
        assert np.array_equal(tile, arr)

    sheet = Image.new("RGB", (832, 896), "#161720")
    draw = ImageDraw.Draw(sheet)
    for i, arr in enumerate(registered):
        x = 8 + (i % 2) * 416
        y = 8 + (i // 2) * 448
        sheet.paste(Image.fromarray(arr).resize((400, 400), Image.Resampling.LANCZOS), (x, y))
        draw.text((x + 8, y + 410), NAMES[i].removesuffix(".png"), fill="white")
    sheet.save(ROOT / "contact_sheet.jpg", quality=94)
    report = {
        "source": str(SOURCE), "source_sha256": source_hash,
        "frame_size": [1024, 1024], "reference_frame": NAMES[0],
        "common_inset_px_each_edge": inset,
        "common_enlargement": 1024 / (1024 - 2 * inset),
        "method": "Translation-only ECC registration on hair/armor, shared inset, one Lanczos sample; no generative edits, facial warp, or expression compositing.",
        "source_artwork_note": "Small non-rigid and lighting differences in the source illustrations remain. Registration removes global offset, not all source differences.",
        "frames": metadata,
        "validation": {
            "all_frames_same_dimensions": True,
            "all_exact_crops_pixel_identical_to_decoded_source": True,
            "sprite_tiles_pixel_identical_to_registered_frames": True,
            "source_unchanged": hashlib.sha256(SOURCE.read_bytes()).hexdigest() == source_hash,
        },
    }
    (ROOT / "alignment.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    assert report["validation"]["source_unchanged"]
    archive = ROOT.parent / "Gemini_girl_animation.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(ROOT.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                z.write(path, str(Path(ROOT.name) / path.relative_to(ROOT)))
    print(json.dumps(report, indent=2))
    print("ZIP:", archive)


if __name__ == "__main__":
    main()
