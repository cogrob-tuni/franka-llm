# Running the System

## Quick Start (Automated)

Use the provided scripts to start all nodes:

```bash
cd ~/franka-llm

# Start all nodes in separate terminals
./start_system.sh

# Stop all nodes
./stop_system.sh
```

**Note:** Wait 15-20 seconds for all nodes to initialize (MoveIt and cameras take longer).

---

## Manual Startup (Step-by-Step)

Start each component in this order:

### Step 1: Start Ollama Server

```bash
# Terminal 1
ollama serve
```

### Step 2: Start Web UI Server (MUST BE FIRST!)

```bash
# Terminal 2
cd /home/arash/franka-llm/ui/web_chat_dashboard
python3 -m http.server 8000
```

### Step 3: Start ROSBridge WebSocket Server

```bash
# Terminal 3
source /opt/ros/jazzy/setup.bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

### Step 4: Start RealSense Camera

```bash
# Terminal 4
cd /home/arash/franka-llm
source install/setup.zsh
ros2 launch realsense_cameras ee_camera.launch.py
```

### Step 5: Start LLM Coordinator

```bash
# Terminal 5
cd /home/arash/franka-llm
source install/setup.zsh
ros2 run franka_llm_planner llm_coordinator
```

### Step 6: Start VLM Agent

```bash
# Terminal 6
cd /home/arash/franka-llm
source install/setup.zsh
ros2 run franka_vlm_agent vlm_node
```

### Step 7: Start Web Handler

```bash
# Terminal 7
cd /home/arash/franka-llm
source install/setup.zsh
ros2 run franka_coordinator web_handler
```

### Step 8: Start Coordinator Node (ArUco transform + motion routing)

```bash
# Terminal 8
cd /home/arash/franka-llm
source install/setup.zsh
ros2 run franka_coordinator coordinator_node
```

### Step 9: Start Motion Executor

```bash
# Terminal 9
cd /home/arash/franka-llm
source install/setup.zsh
ros2 run franka_motion_executor motion_executor
```

### Step 10: Launch MoveIt (real robot)

```bash
# Terminal 10
cd ~/franka_ros2_ws
source install/setup.zsh
ros2 launch franka_fr3_moveit_config moveit.launch.py robot_ip:=172.16.0.2 use_fake_hardware:=false
```

### Step 11: Open Browser

Navigate to: **http://localhost:8000**

You should see:
- ✅ "Connected" status in sidebar (green indicator)
- ✅ Chat interface ready
- ✅ Status cards showing system state

---

## Access Points

- **Web Dashboard**: http://localhost:8000
- **ROSBridge WebSocket**: ws://localhost:9090

---

## Restarting Individual Nodes

Use the restart script for specific components:

```bash
# Restart motion executor
./restart_node.sh motion

# Restart MoveIt (takes 15-20s to initialize)
./restart_node.sh moveit

# Restart RealSense cameras
./restart_node.sh camera

# Restart web UI server
./restart_node.sh ui
```

---

## Verifying System Status

### Check Running Nodes

```bash
ros2 node list
```

Expected nodes:
- `/llm_coordinator`
- `/vlm_node`
- `/web_handler`
- `/coordinator_node`
- `/motion_executor`
- `/move_group` (MoveIt)

### Check MoveIt Controllers

```bash
ros2 control list_controllers
```

Expected controllers (all `[active]`):
- `joint_state_broadcaster`
- `franka_robot_state_broadcaster`
- `fr3_arm_controller`
- `franka_gripper` (optional - may fail, see note below)

**If controllers not loaded:**

```bash
# Wait 15-20 seconds after launching MoveIt, then manually load:
ros2 control load_controller joint_state_broadcaster --set-state active
ros2 control load_controller franka_robot_state_broadcaster --set-state active
ros2 control load_controller fr3_arm_controller --set-state active

# Optional - gripper controller (often fails, not required)
ros2 control load_controller franka_gripper --set-state active
```

**Note about gripper controller:** The `franka_gripper` controller commonly fails to load ("Failed loading controller franka_gripper"). **This is expected and does not affect system operation.** The motion executor controls the gripper through MoveIt's action interface, not the ros2_control controller. You only need the three core controllers active:
- ✅ `joint_state_broadcaster`
- ✅ `franka_robot_state_broadcaster`
- ✅ `fr3_arm_controller`

### Check Topics

```bash
# Web communication topics
ros2 topic list | grep web

# Should show:
# /web/request
# /web/response
# /web/status
```

---

## Common Startup Issues

**Robot doesn't move:**
- Verify MoveIt is running: `ros2 node list | grep move_group`
- Check controllers: `ros2 control list_controllers`
- All controllers should show `[active]`
