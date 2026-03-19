# VLM System - Quick Reference

## Architecture

```
PC Controller (Camera) --[ROS2 Network]--> Jetson (VLM Processing)
    Publishes:                                Analyzes with LLaVA 7B
    /cameras/ee/.../color/image_raw          Publishes:
    /cameras/.../compressed                   /vlm/explanation (descriptions)
                                              /vlm/status (health info)
```

## Setup

### Jetson (One-time)
```bash
ollama serve &
ollama pull llava:7b
cd ~/franka-llm
colcon build --packages-select franka_vlm_agent
```

### Run VLM on Jetson
```bash
export ROS_DOMAIN_ID=0
cd ~/franka-llm
source install/setup.zsh
ros2 run franka_vlm_agent vlm_node --ros-args \
  -p camera_topic:=/cameras/ee/ee_camera/color/image_raw \
  -p use_compressed:=True
```

### View Output on PC
```bar any machine) subscribes to /vlm/explanationsh
export ROS_DOMAIN_ID=0
cd ~/franka-llm
source install/setup.bash  # or setup.zsh
python3 view_vlm_output.py
```

## How It Works

1. **PC** publishes camera images (compressed to avoid DDS buffer issues)
2. **Jetson** subscribes to compressed images, analyzes with LLaVA 7B via Ollama
3. **Jetson** publishes scene descriptions to `/vlm/explanation`
4. **PC** (or any machine) subscribes to `/vlm/explanation` for analysis

**Analysis Rate:** 1 Hz (once per second)  
**Processing Time:** ~10-15 seconds per image on Jetson AGX Orin
