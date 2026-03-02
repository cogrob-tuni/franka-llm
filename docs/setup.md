# System Setup Guide

## Prerequisites

- Ubuntu 22.04 LTS
- ROS2 Jazzy
- MoveIt2 (in separate workspace: `~/franka_ros2_ws`)
- Ollama with models: `llama3.1:8b`, `qwen2.5vl:32b`
- Python 3.10+

## Installation

### 1. Install Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
ollama pull qwen2.5vl:32b
```

### 2. Clone Repository
```bash
git clone https://github.com/Arashghsz/franka-llm.git
cd franka-llm
```

### 3. Build ROS2 Packages
```bash
colcon build --symlink-install
source install/setup.zsh
```

## Configuration

Edit `config.yaml` in workspace root:

```yaml
llm:
  model: "llama3.1:8b"
  base_url: "http://localhost:11434"

vlm:
  model: "qwen2.5vl:32b"
  base_url: "http://localhost:11434"

camera:
  aruco_offset_x: 0.0
  aruco_offset_y: 0.0
  aruco_offset_z: 0.0

robot:
  safe_height: 0.60
  grasp_height: 0.14
  default_velocity_scaling: 0.1
```

## Running

See **[RUNNING.md](../RUNNING.md)** for complete startup instructions.

**Quick start:**
```bash
./start_system.sh
```

**Access:** http://localhost:8000

## Verification

### Check nodes
```bash
ros2 node list
```

### Check controllers
```bash
ros2 control list_controllers
```

### Check topics
```bash
ros2 topic list | grep web
```

## Troubleshooting

**Ollama not running:**
```bash
ollama serve
```

**Controllers not loaded:**
```bash
ros2 control load_controller joint_state_broadcaster --set-state active
ros2 control load_controller franka_robot_state_broadcaster --set-state active
ros2 control load_controller fr3_arm_controller --set-state active
```

**Camera issues:**
```bash
./restart_node.sh camera
```

