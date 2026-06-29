# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
import base64
import os

def convert_image_to_base64(image_path: str) -> str:
    """
    Converts an image file to a raw base64 encoded string.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # Read and encode
    with open(image_path, "rb") as image_file:
        # We perform the read and encode in one go
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    
    return encoded_string