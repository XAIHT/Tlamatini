# Girl animation frames

Use the four PNGs in this folder for animation. Every frame is **1024 × 1024 RGB**, with identical scale, framing, and canvas origin. The PNG encoding is lossless; the source was a JPEG.

| File | Expression | Source quadrant |
| --- | --- | --- |
| `01_eyes_open_smiling.png` | Open eyes, smiling | Top left |
| `02_eyes_open_neutral.png` | Open eyes, neutral | Top right |
| `03_eyes_closed_smiling.png` | Closed eyes, smiling | Bottom left |
| `04_eyes_closed_neutral.png` | Closed eyes, neutral | Bottom right |

## Alignment

The source portraits have small global offsets. The animation PNGs are translation-registered against frame 1 using stable hair and armor regions, excluding the moving eyes and mouth. All frames use the same six-pixel inset on every side and the same small enlargement back to 1024 × 1024. This avoids padding or neighboring-quadrant pixels. Registration and resizing use a single Lanczos sampling operation. No face warping, expression replacement, or generative image editing was used.

The `exact_crops/` folder contains unresized, unaligned, pixel-exact quadrant crops from the decoded original. Their crop origins are (0, 0), (1024, 0), (0, 1024), and (1024, 1024). Use these if preserving every original pixel is more important than correcting the source offsets.

Global alignment does not eliminate slight non-rigid or lighting differences already present in the source artwork. Mouth and cheek movement is also part of the expression change. The four images are expression states, not a four-step chronological animation; blink with 1 → 3 → 1 or 2 → 4 → 2 (one-based numbering).

## HTML / JavaScript

Open `preview.html` locally, then click **Play animation**. It preloads and decodes all frames, uses a fixed 1024 × 1024 canvas, and draws every frame at (0, 0), so loading cannot cause flashing or layout movement. The preview includes an untouched-crop comparison and individual expression buttons. It needs no server, package installation, or network access.

For a sprite-based implementation, `sprite_2x2.png` is 2048 × 2048 with the four aligned frames in the original row-major order. With CSS `background-size: 200% 200%`, use positions `0% 0%`, `100% 0%`, `0% 100%`, and `100% 100%`. Do not interpolate the background position between cells.

`alignment.json` records source/output hashes, exact transforms, dimensions, and validation results. `build_frames.py` reproduces the outputs with Python, Pillow, NumPy, and OpenCV. The original JPEG is not modified.
