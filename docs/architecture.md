# Franka LLM System Architecture

## Overview

Natural language control of Franka FR3 robot using LLM + VLM:

```
Web Dashboard → Web Handler → LLM Coordinator → VLM Agent → Coordinator → Motion Executor → Robot
                                                       ↓
                                                  RealSense Camera
```

## Core Components

### 1. Web Handler (`franka_coordinator/web_handler.py`)
- Bridges web dashboard with ROS2 system
- Handles user requests and responses
- Manages motion confirmation flow

### 2. LLM Coordinator (`franka_llm_planner/llm_coordinator_node.py`)
- Natural language understanding (LLaMA 3.1 8B)
- Routes commands to appropriate agents
- Generates responses

### 3. VLM Agent (`franka_vlm_agent/vlm_node.py`)
- Scene understanding and object detection (Qwen2.5-VL 32B)
- Visual grounding with bounding boxes
- Generates debug images

### 4. Coordinator (`franka_coordinator/coordinator_node.py`)
- Transforms camera coordinates to robot frame
- ArUco marker calibration
- Routes motion commands to executor

### 5. Motion Executor (`franka_motion_executor/motion_executor_node.py`)
- MoveIt2-based motion planning
- Pick, place, handover, go_home, dance primitives
- Gripper control via MoveIt action interface

### 6. RealSense Cameras (`realsense_cameras`)
- Intel RealSense D435i RGB-D camera
- Provides depth and color streams

## Data Flow

1. User sends command via web dashboard
2. LLM Coordinator parses intent and routes request
3. VLM Agent detects objects and provides 2D bounding box
4. Coordinator transforms 2D + depth → 3D robot coordinates
5. Motion confirmation sent to web dashboard
6. User approves → Motion Executor plans and executes
7. Status updates streamed back to dashboard

