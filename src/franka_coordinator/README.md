# Franka Coordinator Package

**Package**: `franka_coordinator`  
**Description**: Main coordination layer that bridges the web interface, LLM planner, VLM agent, and motion executor. Handles vision-guided manipulation, 3D coordinate transformations, and user confirmation workflows.

## Overview

The coordinator package serves as the central hub that:
- Manages communication between all system components
- Performs ArUco-based camera-to-robot coordinate transformations
- Handles user confirmations for motion execution
- Maintains system status and publishes state updates
- Provides web dashboard interface for user interaction

## Architecture

```
Web UI (Browser)
    ↓
web_handler.py ←→ coordinator_node.py
                        ↓
                  ┌─────┴─────┐
                  ↓           ↓
            LLM Planner   Motion Executor
                  ↓
            VLM Agent
```

## Key Components

### 1. coordinator_node.py
Main coordination node that:
- Subscribes to LLM decisions, VLM grounding results, and motion status
- Converts pixel coordinates to robot frame using ArUco calibration
- Handles special placement types (direct, stacking, relative)
- Manages confirmation flow for go_home and dance commands
- Publishes target positions for motion execution

**Topics:**
- Subscribes:
  - `/web/request` - User commands from web dashboard
  - `/llm/response` - LLM processing results
  - `/vlm_grounding` - VLM object detection with pixel coordinates
  - `/motion/status` - Motion executor status updates
  - `/cameras/ee/ee_camera/depth/image_rect_raw` - Depth images
  - `/cameras/ee/ee_camera/depth/camera_info` - Camera intrinsics
  
- Publishes:
  - `/llm/request` - Requests to LLM coordinator
  - `/motion/command` - Commands to motion executor
  - `/vlm_request` - Requests to VLM agent
  - `/target_position` - 3D target positions (PoseStamped)
  - `/target_position_info` - Position info as JSON for web display
  - `/coordinator/status` - System status updates

### 2. web_handler.py
Web interface bridge that:
- Manages WebSocket connections via rosbridge
- Handles chat messages and user commands
- Implements motion confirmation workflow
- Publishes system status for dashboard display
- Manages pending motions and user approvals

**Topics:**
- Subscribes:
  - `/web/request` - User inputs from browser
  - `/llm/response` - LLM responses for chat
  - `/vlm_grounding` - VLM detections for confirmation
  - `/target_position_info` - Robot-frame coordinates
  - `/motion/status` - Motion execution status
  - `/robot/state` - Robot state for dashboard
  
- Publishes:
  - `/web/response` - Messages to web dashboard
  - `/user_command` - User commands to LLM
  - `/user_confirmation` - User approval/rejection
  - `/web/status` - System status with config

### 3. aruco_transformer.py
Coordinate transformation utility:
- Loads ArUco calibration data (hand-eye calibration)
- Converts pixel + depth → 3D camera frame
- Transforms camera frame → robot base frame
- Applies configurable offsets from config.yaml

## Configuration

All configuration is loaded from `~/franka-llm/config.yaml`:

```yaml
camera:
  aruco_offset_x: 0.0    # X offset from ArUco to robot base (m)
  aruco_offset_y: 0.0    # Y offset (m)
  aruco_offset_z: 0.0    # Z offset (m)

robot:
  safe_height: 0.60           # Safe navigation height (m)
  grasp_height: 0.14          # Object grasp height (m)
  handover_height: 0.30       # Human handover height (m)
  held_object_height: 0.10    # Typical object height for stacking (m)
  placement_clearance: 0.02   # Clearance above target for placement (m)
```

## Testing

### 1. Test Coordinate Transformation

```bash
# Terminal 1: Start coordinator
cd ~/franka-llm
source install/setup.bash
ros2 run franka_coordinator coordinator_node

# Terminal 2: Publish test VLM grounding
ros2 topic pub --once /vlm_grounding std_msgs/msg/String \
  "data: '{\"target\": \"test_object\", \"center\": [640, 480], \"action\": \"pick\"}'"

# Check if 3D position is published
ros2 topic echo /target_position
ros2 topic echo /target_position_info
```

### 2. Test Confirmation Flow

```bash
# Start web handler
ros2 run franka_coordinator web_handler

# In web UI, send: "go home"
# Check that confirmation request appears in browser
# Click Approve/Reject button
# Verify confirmation published to /user_confirmation
```

### 3. Test Status Publishing

```bash
# Echo web status
ros2 topic echo /web/status

# Should show system status with config parameters:
# - robot_status, vision_status, llm_status
# - current_task, task_status
# - config (LLM model, camera offsets, robot parameters)
```

### 4. Integration Test

```bash
# Full system test:
1. Start all nodes (see main README)
2. Open web UI (http://localhost:8000)
3. Send command: "pick up the blue cube"
4. Verify:
   - LLM processes request
   - VLM detects object
   - Coordinator converts to 3D
   - Position displayed in web UI
   - Confirmation dialog appears
   - Approve → motion executes
```

## Development

### Adding New Placement Types

Edit `coordinator_node.py`, in `handle_vlm_grounding()`:

```python
# Add new placement type handling
elif action == 'place':
    placement_type = grounding.get('placement_type', 'direct')
    
    if placement_type == 'your_new_type':
        # Add custom offset logic here
        offset = np.array([x, y, z])
        position_robot = position_robot + offset
```

Update LLM prompt in `franka_llm_planner` to recognize the new type.

### Debugging Coordinate Transformations

Enable detailed logging:
```python
# In coordinator_node.py
self.get_logger().set_level(rclpy.logging.LoggingSeverity.DEBUG)
```

Check calibration:
```bash
# Verify ArUco calibration files exist
ls ~/franka-llm/calibration/

# Should contain:
# - camera_info.yaml
# - hand_eye_calibration.yaml
```

## Dependencies

**Python packages:**
- rclpy
- sensor_msgs (Image, CameraInfo)
- geometry_msgs (PoseStamped)
- std_msgs (String)
- cv_bridge
- opencv-python
- numpy
- PyYAML

**ROS2 packages:**
- rosbridge_server (for web interface)
- tf2_ros (for transforms)

## Troubleshooting

**Issue**: "Cannot resolve 3D position" warning
- **Cause**: Missing depth image or camera intrinsics
- **Fix**: Ensure RealSense camera is streaming depth
  ```bash
  ros2 topic hz /cameras/ee/ee_camera/depth/image_rect_raw
  ```

**Issue**: Confirmation not appearing in web UI
- **Cause**: Web handler not running or WebSocket disconnected
- **Fix**: 
  1. Check rosbridge: `ros2 run rosbridge_server rosbridge_websocket`
  2. Restart web UI (refresh browser)
  3. Check browser console for errors

**Issue**: Incorrect 3D coordinates
- **Cause**: ArUco calibration offsets wrong
- **Fix**: Recalibrate or adjust offsets in config.yaml
  ```bash
  # Test with known object position
  # Adjust aruco_offset_x/y/z until accurate
  ```

## Launch Files

The coordinator can be launched as part of the main system:

```bash
ros2 launch franka_coordinator main.launch.py
```

Or individually:
```bash
# Coordinator only
ros2 run franka_coordinator coordinator_node

# Web handler only  
ros2 run franka_coordinator web_handler
```

## Status Updates

The coordinator publishes status at 1 Hz to `/web/status` containing:
- **robot_status**: "connected" | "disconnected" | "error"
- **vision_status**: "online" | "offline"
- **llm_status**: "online" | "offline"
- **current_task**: Current task description
- **task_status**: "pending" | "processing" | "completed" | "failed"
- **config**: All configuration parameters from config.yaml

## Web UI Integration

**IMPORTANT**: The web UI server must be started BEFORE the web_handler node.

```bash
# 1. Start web UI server first
cd ~/franka-llm/ui
python3 -m http.server 8000

# 2. Then start rosbridge
ros2 run rosbridge_server rosbridge_websocket

# 3. Finally start web_handler
ros2 run franka_coordinator web_handler
```

Access dashboard at: http://localhost:8000
