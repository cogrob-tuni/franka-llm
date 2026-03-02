# Franka LLM - Intelligent Robotic Manipulation System

**Project**: Natural language-driven robotic manipulation using Vision-Language Models and LLMs  
**Robot**: Franka Emika FR3 7-DOF arm with gripper  
**Framework**: ROS2 Jazzy, MoveIt2, Ollama (LLaMA 3.1 + Qwen2.5-VL)

## Overview

This system enables natural language control of a Franka FR3 robot arm for pick-and-place tasks. Users interact via a web dashboard, sending commands like "pick up the blue cube" or "place it next to the red block". The system uses:

- **LLM (LLaMA 3.1 8B)** - Command understanding and task routing
- **VLM (Qwen2.5-VL 32B)** - Visual object detection and grounding
- **MoveIt2** - Motion planning and collision avoidance
- **ArUco calibration** - Camera-to-robot coordinate transformation
- **Web dashboard** - Real-time monitoring and user confirmation

## Features

✅ Natural language command processing  
✅ Vision-guided object manipulation  
✅ User confirmation workflow for safety  
✅ Multiple placement types (direct, stacking, relative)  
✅ Handover to human capability  
✅ Special motions (go home, dance sequence)  
✅ Real-time web dashboard with status and configuration display  
✅ Centralized configuration in `config.yaml`  
✅ Debug image visualization  

## Architecture

```
┌─────────────────┐
│   Web Browser   │ ← User Interface (localhost:8000)
│   (Dashboard)   │
└────────┬────────┘
         │ WebSocket (rosbridge)
         ↓
┌─────────────────┐      ┌──────────────────┐
│  Web Handler    │ ←──→ │   Coordinator    │
└────────┬────────┘      └────────┬─────────┘
         │                        │
         ↓                        ↓
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│ LLM Coordinator │ ←──→ │   VLM Agent      │ ←──→ │ RealSense       │
│ (LLaMA 3.1 8B)  │      │ (Qwen2.5-VL 32B) │      │ Camera          │
└────────┬────────┘      └──────────────────┘      └─────────────────┘
         │
         ↓
┌─────────────────┐      ┌──────────────────┐
│ Motion Executor │ ───→ │   Franka FR3     │
│   (MoveIt2)     │      │   Robot Arm      │
└─────────────────┘      └──────────────────┘
```

## Packages

### 1. franka_coordinator
Main coordination layer that bridges all components. Handles VLM grounding, 3D coordinate transformations, user confirmations, and system status.

**Key files:**
- `coordinator_node.py` - Main coordination and 3D transforms
- `web_handler.py` - Web interface bridge
- `aruco_transformer.py` - Camera-robot calibration

[Full documentation](src/franka_coordinator/README.md)

### 2. franka_llm_planner
Natural language understanding using LLaMA 3.1. Parses user commands and routes to appropriate agents (VLM, Motion, or direct response).

**Key files:**
- `llm_coordinator_node.py` - LLM processing and routing

[Full documentation](src/franka_llm_planner/README.md)

### 3. franka_motion_executor
MoveIt2-based motion execution. Implements pick, place, handover, go_home, and dance primitives with safety constraints.

**Key files:**
- `motion_executor_node.py` - Motion planning and execution

[Full documentation](src/franka_motion_executor/README.md)

### 4. franka_vlm_agent
Vision-Language Model for scene understanding and object detection using Qwen2.5-VL.

**Key files:**
- `vlm_node.py` - VLM processing and object grounding

[Full documentation](src/franka_vlm_agent/README.md)

### 5. franka_vision_detection
(Legacy computer vision - being replaced by VLM)

### 6. realsense_cameras
Intel RealSense camera integration for RGB-D sensing.

## Quick Start

### Prerequisites

- Ubuntu 22.04 LTS
- Python 3.10+
- ROS2 Jazzy
- MoveIt2
- Ollama with models: `llama3.1:8b`, `qwen2.5vl:32b`
- NVIDIA GPU (recommended for VLM)

### Installation

```bash
# 1. Clone repository
git clone https://github.com/yourusername/franka-llm.git
cd franka-llm

# 2. Install Ollama and models
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
ollama pull qwen2.5vl:32b

# 3. Install Python dependencies (if any)
pip install -r requirements.txt  # if exists

# 4. Build ROS2 packages
colcon build --symlink-install

# 5. Source setup
source install/setup.zsh  # or .bash depending on your shell
```

### Configuration

All configuration is in `config.yaml`. Key parameters:

```yaml
llm:
  model: "llama3.1:8b"
  base_url: "http://localhost:11434"

vlm:
  model: "qwen2.5vl:32b"
  base_url: "http://localhost:11434"

camera:
  aruco_offset_x: 0.0    # Calibration offsets (meters)
  aruco_offset_y: 0.0
  aruco_offset_z: 0.0

robot:
  safe_height: 0.60      # Navigation height (meters)
  grasp_height: 0.14     # Grasp height
  handover_height: 0.30  # Handover height
  default_velocity_scaling: 0.1  # Movement speed (10%)
```

### Running the System

#### Option 1: Automated Scripts (Recommended)

Use the provided scripts to start/stop all nodes at once:

```bash
cd ~/franka-llm

# Start all nodes in separate terminals
./start_system.sh

# Stop all nodes
./stop_system.sh
```

The start script will:
- Launch Ollama server (if not running)
- Start web UI server on port 8000
- Start all ROS2 nodes in separate terminal windows
- Display system status and URLs

#### Option 2: Manual Startup

**IMPORTANT: Start in this order!**

```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Start web UI server (MUST BE FIRST!)
cd ~/franka-llm/ui
python3 -m http.server 8000

# Terminal 3: Start rosbridge
source ~/franka-llm/install/setup.zsh
ros2 run rosbridge_server rosbridge_websocket

# Terminal 4: Start coordinator
ros2 run franka_coordinator coordinator_node

# Terminal 5: Start web handler (AFTER web UI server!)
ros2 run franka_coordinator web_handler

# Terminal 6: Start LLM coordinator
ros2 run franka_llm_planner llm_coordinator_node

# Terminal 7: Start VLM agent
ros2 run franka_vlm_agent vlm_node

# Terminal 8: Start motion executor
ros2 run franka_motion_executor motion_executor_node

# Terminal 9: Start cameras (if not auto-launched)
ros2 launch realsense_cameras ee_camera.launch.py
```

### Access Web Dashboard

Open browser: **http://localhost:8000**

The dashboard provides:
- Chat interface for commands
- Real-time status display
- Motion confirmation dialogs
- System configuration view
- Camera feed (if enabled)

## Usage Examples

### Basic Commands

**Pick and place:**
```
User: "pick up the blue cube"
→ System detects cube, shows confirmation
→ User clicks "Approve"
→ Robot picks cube

User: "place it on the table"
→ System shows target position
→ User approves
→ Robot places cube
```

**Stacking:**
```
User: "stack the small cube on top of the red block"
→ System calculates stacking height
→ Shows confirmation with adjusted Z position
→ User approves
→ Robot places with offset
```

**Handover:**
```
User: "hand me the tool"
→ System detects hand position
→ Robot moves to handover height
→ Opens gripper
```

**Home and dance:**
```
User: "go home"
→ Confirmation: "Return to home position?"
→ User approves
→ Robot moves to safe configuration

User: "dance"
→ Confirmation: "Perform dance sequence?"
→ User approves
→ Robot performs 7-position creative motion
```

### Confirmation Flow

All pick/place/handover/go_home/dance actions require confirmation:

1. System analyzes command
2. For object operations: VLM detects object and computes 3D position
3. Web dashboard shows:
   - Action description
   - Target object/location
   - Robot-frame coordinates (X, Y, Z)
   - Approve/Reject buttons
4. User clicks "Approve" or "Reject"
5. If approved, motion executes
6. Status updates in real-time

## Testing

### Test Individual Packages

Each package has detailed testing instructions in its README:

- [Coordinator Testing](src/franka_coordinator/README.md#testing)
- [LLM Planner Testing](src/franka_llm_planner/README.md#testing)
- [Motion Executor Testing](src/franka_motion_executor/README.md#testing)
- [VLM Agent Testing](src/franka_vlm_agent/README.md#testing)

### Integration Test

```bash
# Full system test sequence:
1. Start all nodes (see "Running the System" above)
2. Place a colorful object in camera view
3. Open web dashboard (http://localhost:8000)
4. Send command: "pick up the [color] [object]"
5. Verify:
   - LLM processes command ✓
   - VLM detects object ✓
   - 3D position displayed ✓
   - Confirmation dialog appears ✓
6. Click "Approve"
7. Verify:
   - Motion executes ✓
   - Status updates ✓
   - Robot picks object ✓
8. Send command: "place it on the table"
9. Approve and verify place executes ✓
```

## Troubleshooting

### Common Issues

**Issue**: Web UI not loading
- **Fix**: Ensure web server started first: `cd ui && python3 -m http.server 8000`
- Check port not in use: `lsof -i :8000`

**Issue**: "Connection refused" to Ollama
- **Fix**: Start Ollama service: `ollama serve`
- Verify models: `ollama list`

**Issue**: VLM very slow (30+ seconds)
- **Fix**: 
  - Use GPU: Check `nvidia-smi`
  - Use smaller model: `qwen2.5vl:7b`
  - Check GPU memory

**Issue**: Robot doesn't move
- **Fix**:
  - Check MoveIt is running: `ros2 node list | grep move_group`
  - Check controllers: `ros2 control list_controllers`
  - Verify robot state: `ros2 topic echo /robot/state`

**Issue**: Confirmation not appearing
- **Fix**:
  - Restart web_handler (must start AFTER web UI server)
  - Check rosbridge: `ros2 node list | grep rosbridge`
  - Check browser console for errors

**Issue**: Incorrect 3D positions
- **Fix**:
  - Verify ArUco calibration exists: `ls ~/franka-llm/calibration/`
  - Adjust offsets in config.yaml:
    ```yaml
    camera:
      aruco_offset_x: 0.0  # Adjust these
      aruco_offset_y: 0.0
      aruco_offset_z: 0.0
    ```

### Debug Tools

```bash
# Check all topics
ros2 topic list

# Monitor specific topic
ros2 topic echo /motion/status

# Check node status
ros2 node list
ros2 node info /coordinator_node

# View debug images
ls ~/franka-llm/debug_images/
eog ~/franka-llm/debug_images/vlm_debug_*.jpg

# Check configuration loading
grep "Configuration" <(ros2 run franka_motion_executor motion_executor_node 2>&1)
```

## Development

### Branch Structure

- **`main`** - Stable baseline for milestone releases
- **`dev`** - Active development (current branch)
- **`demo-*`** - Demo snapshots for presentations

### Workflow

1. Develop features in `dev` branch
2. Test thoroughly
3. Create demo branch for presentations
4. Merge to `main` at milestones

### Adding New Features

1. **New action type**:
   - Update LLM prompt in `franka_llm_planner`
   - Add handler in `motion_executor_node.py`
   - Test with topic pub before full integration

2. **New placement type**:
   - Add logic in `coordinator_node.py` → `handle_vlm_grounding()`
   - Update LLM prompt to recognize new type
   - Add examples in system prompt

3. **Configuration changes**:
   - All changes go in `config.yaml`
   - No code modifications needed
   - Restart affected nodes

### Code Style

- Python: PEP 8
- ROS2: Follow ROS conventions
- Comments: Explain why, not what
- Logging: Use appropriate levels (info, warn, error)

## Performance

### Typical Latencies

- LLM inference: 0.5-2 seconds
- VLM inference: 1-5 seconds (GPU) / 20-60 seconds (CPU)
- Motion planning: 1-3 seconds
- Motion execution: 8-12 seconds (pick/place)
- **Total pick operation**: 12-20 seconds

### Optimization

- Use GPU for VLM (critical)
- Reduce image resolution for faster VLM
- Lower max_tokens in config
- Use faster models (llama3.1:8b, qwen2.5vl:7b)

## Safety

### Built-in Safety Features

1. **User Confirmation** - All motions require approval
2. **Velocity Scaling** - Slow, controlled movements (10-50%)
3. **Safe Height** - Navigate at 0.60m to avoid collisions
4. **Collision Avoidance** - MoveIt2 collision checking
5. **Planning Validation** - Verify trajectory before execution
6. **Emergency Stop** - Web dashboard has stop button

### Safety Recommendations

- Keep workspace clear of obstacles
- Monitor robot during operation
- Test new commands at low velocity first
- Use emergency stop if needed
- Maintain proper lighting for camera

## Documentation

- [Setup Guide](docs/setup.md)
- [Architecture](docs/architecture.md)
- [Evaluation](docs/evaluation.md)
- [ROS Topics](docs/ros_topics.md)
- [UI Review](docs/ui-review-and-hri-analysis.md)

## Citations & References

Based on research in:
- Vision-Language Models for robotics
- Natural language robot control
- Human-robot interaction
- Pick and place manipulation

See [Literature Review](docs/literature-review-and-roman2026.md) for details.

## Contributing

This is a research project. For questions or collaboration:
- Open GitHub issues
- Submit pull requests
- Contact project maintainers

## License

[Add your license here]

## Acknowledgments

- Franka Emika for FR3 robot platform
- ROS2/MoveIt2 community
- Ollama for local LLM/VLM inference
- Meta (LLaMA), Alibaba (Qwen2.5-VL) for open models
