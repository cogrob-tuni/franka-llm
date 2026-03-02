#!/usr/bin/env zsh
# Franka LLM System Startup Script
# Launches all required nodes in separate terminal windows

set -e

WORKSPACE_DIR="$HOME/franka-llm"
cd "$WORKSPACE_DIR"

echo "Starting Franka LLM System..."
echo "================================"

# Check if Ollama is already running
if ! pgrep -x "ollama" > /dev/null; then
    echo "[*] Starting Ollama..."
    gnome-terminal --title="Ollama Server" -- bash -c "ollama serve; exec zsh" &
    sleep 2
else
    echo "[OK] Ollama already running"
fi

# Terminal 1: Web UI Server (MUST BE FIRST!)
echo "[*] Starting Web UI Server..."
gnome-terminal --title="Web UI Server" --working-directory="$WORKSPACE_DIR/ui" -- bash -c "python3 -m http.server 8000; exec zsh" &
sleep 2

# Terminal 2: Rosbridge
echo "[*] Starting Rosbridge WebSocket..."
gnome-terminal --title="Rosbridge" --working-directory="$WORKSPACE_DIR" -- bash -c "source install/setup.zsh && ros2 run rosbridge_server rosbridge_websocket; exec zsh" &
sleep 2

# Terminal 3: Coordinator Node
echo "[*] Starting Coordinator..."
gnome-terminal --title="Coordinator Node" --working-directory="$WORKSPACE_DIR" -- bash -c "source install/setup.zsh && ros2 run franka_coordinator coordinator_node; exec zsh" &
sleep 1

# Terminal 4: Web Handler (AFTER Web UI!)
echo "[*] Starting Web Handler..."
gnome-terminal --title="Web Handler" --working-directory="$WORKSPACE_DIR" -- bash -c "source install/setup.zsh && ros2 run franka_coordinator web_handler; exec zsh" &
sleep 1

# Terminal 5: LLM Coordinator
echo "[*] Starting LLM Coordinator..."
gnome-terminal --title="LLM Coordinator" --working-directory="$WORKSPACE_DIR" -- bash -c "source install/setup.zsh && ros2 run franka_llm_planner llm_coordinator_node; exec zsh" &
sleep 1

# Terminal 6: VLM Agent
echo "[*] Starting VLM Agent..."
gnome-terminal --title="VLM Agent" --working-directory="$WORKSPACE_DIR" -- bash -c "source install/setup.zsh && ros2 run franka_vlm_agent vlm_node; exec zsh" &
sleep 1

# Terminal 7: Motion Executor
echo "[*] Starting Motion Executor..."
gnome-terminal --title="Motion Executor" --working-directory="$WORKSPACE_DIR" -- bash -c "source install/setup.zsh && ros2 run franka_motion_executor motion_executor_node; exec zsh" &
sleep 1

# Terminal 8: RealSense Cameras (optional, uncomment if needed)
# echo "[*] Starting Cameras..."
# gnome-terminal --title="RealSense Cameras" --working-directory="$WORKSPACE_DIR" -- bash -c "source install/setup.zsh && ros2 launch realsense_cameras ee_camera.launch.py; exec zsh" &

echo ""
echo "[OK] All nodes started!"
echo ""
echo "System Status:"
echo "  - Web Dashboard: http://localhost:8000"
echo "  - Ollama API: http://localhost:11434"
echo ""
echo "[INFO] Wait 5-10 seconds for all nodes to initialize"
echo "[INFO] To stop all nodes, run: ./stop_system.sh"
echo ""

# Wait a bit then check if nodes are running
sleep 3
echo "[*] Checking ROS2 nodes..."
source install/setup.zsh
ros2 node list 2>/dev/null || echo "[WARN] ROS2 nodes not yet visible (this is normal, wait a few seconds)"
