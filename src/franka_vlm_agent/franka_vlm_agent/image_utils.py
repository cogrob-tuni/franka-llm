#!/usr/bin/env python3
"""
Image utilities for VLM processing
Handles image encoding, saving, and marker drawing
"""

import cv2
import numpy as np
import base64
from pathlib import Path
from datetime import datetime


def encode_image_to_base64(image: np.ndarray) -> str:
    """
    Encode OpenCV image to base64 string
    
    Args:
        image: OpenCV image (BGR format)
        
    Returns:
        Base64 encoded string
    """
    _, buffer = cv2.imencode('.jpg', image)
    return base64.b64encode(buffer).decode('utf-8')


def draw_center_marker(image: np.ndarray, center: list, object_name: str = None,
                       depth: float = None, color=(0, 255, 255), size=50,
                       thickness=4) -> np.ndarray:
    """
    Draw a crosshair marker at the detected center point.
    Kept simple — detailed annotations are added by annotate_debug_image.
    """
    img_marked = image.copy()
    x, y = int(center[0]), int(center[1])

    CYAN    = (0, 255, 255)
    MAGENTA = (255, 0, 255)
    RED     = (0, 0, 255)
    WHITE   = (255, 255, 255)

    arm = size + 5
    # Magenta outline
    cv2.line(img_marked, (x - arm, y), (x + arm, y), MAGENTA, thickness + 4)
    cv2.line(img_marked, (x, y - arm), (x, y + arm), MAGENTA, thickness + 4)
    cv2.circle(img_marked, (x, y), size, MAGENTA, thickness + 4)
    # Cyan crosshair
    cv2.line(img_marked, (x - size, y), (x + size, y), CYAN, thickness)
    cv2.line(img_marked, (x, y - size), (x, y + size), CYAN, thickness)
    cv2.circle(img_marked, (x, y), size // 2, CYAN, thickness)
    # Center dot
    cv2.circle(img_marked, (x, y), 8, RED, -1)
    cv2.circle(img_marked, (x, y), 8, WHITE, 2)

    return img_marked


def annotate_debug_image(image: np.ndarray,
                         action: str,
                         object_name: str,
                         user_prompt: str = None,
                         center: list = None,
                         depth: float = None,
                         position_3d: list = None,
                         confidence: str = None,
                         llm_model: str = None,
                         vlm_model: str = None,
                         reasoning: str = None) -> np.ndarray:
    """
    Add a clean, static information panel to the bottom of the image.
    Suitable for IEEE paper figures.

    Panel layout (dark background strip):
      Row 1:  Action | Target object | Confidence
      Row 2:  Pixel: (x, y)  |  Depth: z m  |  Robot: X / Y / Z
      Row 3:  Prompt: "..."
      Row 4:  LLM Reasoning: "..."
      Row 5:  LLM: <model>  |  VLM: <model>
    """
    img = image.copy()
    h, w = img.shape[:2]

    # ---- colours & fonts ----------------------------------------
    BLACK      = (0,   0,   0)
    WHITE      = (255, 255, 255)
    CYAN       = (0,   255, 255)
    YELLOW     = (0,   255, 255)  # same as cyan in BGR for consistency
    LIGHT_GREY = (200, 200, 200)
    GREEN      = (80,  220, 80)
    ORANGE     = (0,   165, 255)

    FONT       = cv2.FONT_HERSHEY_SIMPLEX
    FONT_SM    = 0.52
    FONT_MD    = 0.60
    THICK_SM   = 1
    THICK_MD   = 2
    LINE_H     = 28   # pixels between rows
    PAD        = 10

    # ---- build text rows ----------------------------------------
    # Row 1
    action_str  = action.upper() if action else 'DETECT'
    conf_str    = f'Confidence: {confidence}' if confidence else ''
    row1_left   = f'{action_str}  →  {object_name}'
    row1_right  = conf_str

    # Row 2
    px_str  = f'Pixel: ({int(center[0])}, {int(center[1])})' if center else ''
    dep_str = f'Depth: {depth:.3f} m' if depth is not None else ''
    if position_3d and len(position_3d) == 3:
        rob_str = (f'Robot (fr3_link0):  '
                   f'X {position_3d[0]:+.3f} m  '
                   f'Y {position_3d[1]:+.3f} m  '
                   f'Z {position_3d[2]:+.3f} m')
    else:
        rob_str = ''
    row2 = '    '.join(filter(None, [px_str, dep_str, rob_str]))

    # Row 3
    prompt_display = user_prompt[:120] + '…' if user_prompt and len(user_prompt) > 120 else (user_prompt or '')
    row3 = f'Prompt: "{prompt_display}"' if prompt_display else ''

    # Row 4
    llm_str  = f'LLM: {llm_model}' if llm_model else ''
    vlm_str  = f'VLM: {vlm_model}' if vlm_model else ''
    row4_parts = list(filter(None, [llm_str, vlm_str]))
    row4 = '    |    '.join(row4_parts)

    rows = [r for r in [row1_left, row2, row3, row4] if r]
    n_rows = len(rows)
    panel_h = n_rows * LINE_H + 2 * PAD

    # ---- draw dark panel ----------------------------------------
    panel = np.zeros((panel_h, w, 3), dtype=np.uint8)
    panel[:] = (30, 30, 30)  # very dark grey
    # thin white top border
    cv2.line(panel, (0, 0), (w, 0), WHITE, 1)

    # ---- write rows into panel ----------------------------------
    def put(panel_img, text, row_idx, color, scale=FONT_SM, thick=THICK_SM):
        ty = PAD + row_idx * LINE_H + LINE_H - 6
        cv2.putText(panel_img, text, (PAD, ty), FONT, scale, color, thick,
                    cv2.LINE_AA)

    if rows:
        put(panel, row1_left,  0, CYAN,       FONT_MD, THICK_MD)
    if row1_right and rows:
        # right-align confidence
        (tw, _), _ = cv2.getTextSize(row1_right, FONT, FONT_SM, THICK_SM)
        cv2.putText(panel, row1_right, (w - tw - PAD, PAD + LINE_H - 6),
                    FONT, FONT_SM, GREEN, THICK_SM, cv2.LINE_AA)

    offset = 1
    if row2:
        put(panel, row2, offset, LIGHT_GREY); offset += 1
    if row3:
        put(panel, row3, offset, ORANGE);     offset += 1
    if row4:
        put(panel, row4, offset, CYAN);       offset += 1
    if row5:
        put(panel, row5, offset, LIGHT_GREY)

    # ---- stack panel below image --------------------------------
    return np.vstack([img, panel])


def save_debug_image(image: np.ndarray, object_name: str, center: list = None,
                     depth: float = None, debug_dir: Path = None,
                     model_name: str = None, llm_model: str = None,
                     action: str = None, user_prompt: str = None,
                     position_3d: list = None, confidence: str = None,
                     reasoning: str = None) -> str:
    """
    Save annotated debug image with a clean IEEE-quality info panel.

    Filename format:
      {action}_{object}_{llm_model}_{vlm_model}_{timestamp}.jpg
    """
    if debug_dir is None:
        current_file = Path(__file__).resolve()
        workspace_root = current_file.parents[4]
        debug_dir = workspace_root / 'debug_images'
    debug_dir.mkdir(exist_ok=True, parents=True)

    # Draw crosshair on a copy
    if center is not None:
        img_annotated = draw_center_marker(image, center, object_name=object_name, depth=depth)
    else:
        img_annotated = image.copy()

    # Add static info panel
    img_annotated = annotate_debug_image(
        img_annotated,
        action=action or 'detect',
        object_name=object_name,
        user_prompt=user_prompt,
        center=center,
        depth=depth,
        position_3d=position_3d,
        confidence=confidence,
        llm_model=llm_model,
        vlm_model=model_name,
        reasoning=reasoning
    )

    # Build filename
    timestamp_fn = datetime.now().strftime('%b%d_%H-%M-%S')
    safe_object = object_name.replace(' ', '_')[:40]
    action_prefix = (action or 'detect').lower()
    vlm_safe = model_name.replace(':', '-') if model_name else 'vlm'
    llm_safe = llm_model.replace(':', '-') if llm_model else None

    if llm_safe:
        filename = f'{action_prefix}_{safe_object}_{llm_safe}_{vlm_safe}_{timestamp_fn}.jpg'
    else:
        filename = f'{action_prefix}_{safe_object}_{vlm_safe}_{timestamp_fn}.jpg'

    filepath = debug_dir / filename
    cv2.imwrite(str(filepath), img_annotated)
    return str(filepath)


def parse_vlm_response(vlm_response: str) -> dict:
    """
    Parse VLM JSON response and handle different coordinate formats
    
    Args:
        vlm_response: JSON string from VLM
        
    Returns:
        Parsed dictionary with normalized center coordinates
    """
    import json
    
    try:
        data = json.loads(vlm_response)
    except json.JSONDecodeError:
        return None
    
    center = data.get('center')
    
    # Handle null/None center
    if center is None or (isinstance(center, list) and None in center):
        return None
    
    # Convert bounding box [x1, y1, x2, y2] to center [x, y]
    if isinstance(center, list) and len(center) == 4:
        x1, y1, x2, y2 = center
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        data['center'] = [center_x, center_y]
        data['bounding_box'] = [x1, y1, x2, y2]
        return data
    
    # Already in center format [x, y]
    elif isinstance(center, list) and len(center) == 2:
        return data
    
    return None
