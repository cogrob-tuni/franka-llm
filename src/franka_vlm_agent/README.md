# Franka VLM Agent Package

**Package**: `franka_vlm_agent`  
**Description**: Vision-Language Model agent using Qwen2.5-VL for scene understanding, object detection with bounding boxes, and visual grounding of natural language references.

## Overview

The VLM agent package provides:
- Scene description and object detection
- Visual grounding of natural language object references
- Bounding box localization for objects
- Location grounding (spatial references like "on the table", "left side")
- Integration with Ollama for local VLM inference
- Debug image saving with visualizations

## Architecture

```
Image + Text Query → vlm_node.py
                         ↓
                [Qwen2.5-VL 32B]
                         ↓
                  Object Detection
                   + Bounding Box
                         ↓
               /vlm_grounding (topic)
```

## Key Components

### vlm_node.py

Main VLM processing node that:
- Subscribes to camera images
- Receives VLM requests (scene description, object grounding, location grounding)
- Queries Ollama VLM API with image + text prompt
- Parses VLM responses (bounding boxes, center coordinates)
- Publishes grounding results with pixel coordinates
- Saves debug images with visualizations

**Topics:**
- Subscribes:
  - `/vlm_request` - Requests from LLM coordinator
  - `/cameras/ee/ee_camera/color/image_raw` - RGB camera images
  
- Publishes:
  - `/vlm/explanation` - Text descriptions of scene
  - `/vlm_grounding` - Object detections with bbox and center
  - `/vlm/analysis` - Detailed analysis results

## Configuration

VLM settings from `~/franka-llm/config.yaml`:

```yaml
vlm:
  model: "qwen2.5vl:32b"
  base_url: "http://localhost:11434"
  temperature: 0.2
  max_tokens: 1000

debug:
  save_images: true
  debug_image_dir: "~/franka-llm/debug_images"
```

## VLM Request Types

### 1. Scene Description

Request:
```json
{
  "type": "scene_description",
  "timestamp": "ISO 8601"
}
```

Response:
- Published to `/vlm/explanation`
- Text description of visible objects and scene

### 2. Ground Object

Request:
```json
{
  "type": "ground_object",
  "object": "blue cube",
  "timestamp": "ISO 8601"
}
```

Response published to `/vlm_grounding`:
```json
{
  "target": "blue cube",
  "center": [640, 480],
  "bbox": [600, 450, 680, 510],
  "action": "pick",
  "timestamp": "ISO 8601"
}
```

### 3. Ground Location

Request:
```json
{
  "type": "ground_location",
  "location": "on the table",
  "placement_type": "direct",
  "timestamp": "ISO 8601"
}
```

Response:
- Center point of specified location
- Bounding box (if applicable)
- Action type (usually "place")

## Testing

### 1. Test VLM Node Startup

```bash
# Start VLM node
cd ~/franka-llm
source install/setup.bash
ros2 run franka_vlm_agent vlm_node

# Check for image subscription
ros2 topic info /cameras/ee/ee_camera/color/image_raw

# Verify debug directory
ls ~/franka-llm/debug_images/
```

### 2. Test Scene Description

```bash
# Send scene description request
ros2 topic pub --once /vlm_request std_msgs/msg/String \
  "data: '{\"type\": \"scene_description\"}'"

# Check response
ros2 topic echo /vlm/explanation --once

# Expected output:
# "I can see a blue cube, a red ball, and a green block on the table..."
```

### 3. Test Object Grounding

```bash
# Send object grounding request
ros2 topic pub --once /vlm_request std_msgs/msg/String \
  "data: '{\"type\": \"ground_object\", \"object\": \"blue cube\"}'"

# Check grounding result
ros2 topic echo /vlm_grounding --once

# Expected output:
# {
#   "target": "blue cube",
#   "center": [640, 480],
#   "bbox": [600, 450, 680, 510],
#   ...
# }
```

### 4. Test Debug Image Saving

```bash
# After grounding request, check debug images
ls -lt ~/franka-llm/debug_images/

# Should see files like:
# vlm_debug_2026-03-02_15-30-45.jpg
# vlm_debug_2026-03-02_15-31-12.jpg

# Open image to verify bounding box drawn
eog ~/franka-llm/debug_images/vlm_debug_*.jpg
```

### 5. Integration Test

```bash
# Full pipeline test:
1. Place a colorful object in camera view
2. Start all nodes
3. Use web UI: "pick up the red cube"
4. LLM routes to VLM
5. VLM detects object and publishes center
6. Coordinator converts to 3D
7. Web UI shows confirmation with position
8. Approve and watch robot execute
```

## Ollama Setup

### Install Ollama

```bash
# Download and install
curl -fsSL https://ollama.com/install.sh | sh

# Pull Qwen2.5-VL model (large model, ~20GB)
ollama pull qwen2.5vl:32b

# For faster inference with less accuracy:
ollama pull qwen2.5vl:7b

# Verify model is available
ollama list
```

### Start Ollama Service

```bash
# Start Ollama API server (runs on port 11434)
ollama serve

# Test VLM with image
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5vl:32b",
  "prompt": "Describe this image",
  "images": ["base64_encoded_image_here"],
  "stream": false
}'
```

### GPU Acceleration

Qwen2.5-VL 32B requires significant compute:
- **GPU recommended**: NVIDIA RTX 3090 or better
- **VRAM**: 24GB+ for 32B model, 8GB+ for 7B model
- **CPU fallback**: Very slow (30-60 seconds per query)

Enable CUDA:
```bash
# Check GPU is detected
nvidia-smi

# Ollama should automatically use GPU if available
# Check logs when running ollama serve
```

## Prompt Engineering

The VLM prompts are defined in `vlm_node.py`:

### Scene Description Prompt
```python
"Describe what objects you see in this image. List all visible objects with their colors and approximate positions."
```

### Object Grounding Prompt
```python
f"Locate the {object_name} in the image and provide its center coordinates and bounding box in format: [x, y, width, height]."
```

### Location Grounding Prompt
```python
f"Identify the center point of the location: {location_description}. Provide coordinates in format: [x, y]."
```

## Bounding Box Parsing

The VLM returns bounding boxes in various formats:
- `[x, y, width, height]` - XYWH format
- `[x1, y1, x2, y2]` - XYXY format
- `"Object at (x, y)"` - Center only

The node handles all formats and converts to:
```python
{
  "center": [cx, cy],      # Center pixel
  "bbox": [x1, y1, x2, y2] # XYXY format
}
```

## Debug Images

When `debug.save_images: true`, the VLM node saves images with:
- Original camera image
- Detected bounding box drawn in green
- Center point marked with red circle
- Object name label
- Timestamp

Location: `~/franka-llm/debug_images/vlm_debug_YYYY-MM-DD_HH-MM-SS.jpg`

## Development

### Changing VLM Model

Edit `config.yaml`:
```yaml
vlm:
  model: "llava:13b"        # Alternative vision model
  # or
  model: "bakllava:latest"  # Another option
```

Models to try:
- `qwen2.5vl:32b` - Best accuracy, slowest
- `qwen2.5vl:7b` - Good balance
- `llava:13b` - Faster, less accurate
- `bakllava:latest` - Alternative architecture

### Improving Object Detection

Modify prompts in `vlm_node.py`:
```python
# More specific prompt
prompt = f"""
Locate the {object_name} in the image.
Requirements:
- Provide exact bounding box coordinates
- Format: [x1, y1, x2, y2] where (x1,y1) is top-left, (x2,y2) is bottom-right
- Be precise with the object boundaries
"""
```

### Adding New Request Types

1. **Define new type** in `handle_vlm_request()`:
```python
if request_type == 'your_new_type':
    prompt = "Your custom prompt"
    result = self.query_vlm(prompt, image)
    self.publish_custom_result(result)
```

2. **Update LLM coordinator** to send new type

3. **Test with topic pub**

## Dependencies

**Python packages:**
- rclpy
- sensor_msgs (Image)
- std_msgs (String)
- cv_bridge
- opencv-python
- PIL (Pillow)
- requests (for Ollama API)
- json
- base64

**External services:**
- Ollama VLM server
- Qwen2.5-VL model

## Troubleshooting

**Issue**: "Connection refused" to Ollama
- **Cause**: Ollama service not running
- **Fix**: 
  ```bash
  ollama serve
  # In another terminal
  ollama list  # Verify model exists
  ```

**Issue**: Very slow VLM responses (30+ seconds)
- **Cause**: Running on CPU without GPU
- **Fix**:
  - Use smaller model: `qwen2.5vl:7b`
  - Enable GPU acceleration (NVIDIA CUDA)
  - Check GPU usage: `nvidia-smi`

**Issue**: "Model not found" error
- **Cause**: VLM model not pulled
- **Fix**: 
  ```bash
  ollama pull qwen2.5vl:32b
  # Or whichever model specified in config.yaml
  ```

**Issue**: Incorrect bounding boxes
- **Cause**: VLM hallucinating or image quality poor
- **Fix**:
  - Improve lighting in camera view
  - Use more specific prompts
  - Try different VLM model
  - Check debug images to verify detections

**Issue**: Debug images not saving
- **Cause**: Directory doesn't exist or no permissions
- **Fix**: 
  ```bash
  mkdir -p ~/franka-llm/debug_images
  chmod 755 ~/franka-llm/debug_images
  ```

**Issue**: Bounding box parsing fails
- **Cause**: VLM returning unexpected format
- **Fix**: Check logs for raw VLM response, update parsing logic

## Performance

Typical VLM query times:
- **GPU (RTX 4090)**: 1-3 seconds
- **GPU (RTX 3090)**: 2-5 seconds
- **CPU (high-end)**: 20-60 seconds

Optimization tips:
- Use GPU acceleration (critical for VLM)
- Reduce max_tokens to 500-800
- Use smaller model (7B instead of 32B)
- Reduce image resolution (resize before sending)

## Image Processing

The VLM node receives images and:
1. Converts from ROS Image to OpenCV format
2. Resizes if needed (optional)
3. Encodes as JPEG
4. Converts to base64 for Ollama API
5. Sends with text prompt

Image resolution affects:
- **Accuracy**: Higher resolution = better detection
- **Speed**: Lower resolution = faster inference
- **Memory**: Higher resolution = more VRAM

## Launch

```bash
# Standalone VLM node
ros2 run franka_vlm_agent vlm_node

# As part of main system
ros2 launch franka_coordinator main.launch.py
```

## VLM Response Format

The VLM typically responds in formats like:
```
"I can see a blue cube at coordinates (640, 480) with bounding box [600, 450, 680, 510]."
```

or

```
"Object detected at center (640, 480)"
```

The node parses these responses using regex:
```python
# Extract bounding box
bbox_match = re.search(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', response)

# Extract center
center_match = re.search(r'\((\d+),\s*(\d+)\)', response)
```

## Integration with System

VLM workflow in pick operation:
1. User: "pick up the blue cube"
2. LLM coordinator routes to VLM with object: "blue cube"
3. VLM node:
   - Captures current camera image
   - Queries Qwen2.5-VL: "Locate blue cube"
   - Parses response: center (640, 480), bbox [600, 450, 680, 510]
   - Publishes to `/vlm_grounding`
   - Saves debug image
4. Coordinator receives grounding, converts pixel to 3D
5. Web handler shows confirmation
6. Motion executor executes pick

## Status Updates

Monitor VLM processing:
```bash
# Watch VLM requests
ros2 topic echo /vlm_request

# Watch VLM results
ros2 topic echo /vlm_grounding

# Watch explanations
ros2 topic echo /vlm/explanation
```
