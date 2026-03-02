#!/usr/bin/env bash
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
    gnome-terminal --title="Ollama Server" -- zsh -c "ollama serve; exec zsh" &
    sleep 3
else
    echo "[OK] Ollama already running"
fi

# Terminal 1: Web UI Server (MUST BE FIRST!)
echo "[*] Starting Web UI Server..."
gnome-terminal --title="Web UI Server" --working-directory="$WORKSPACE_DIR/ui/web_chat_dashboard" -- zsh -c "python3 -m http.server 8000 --bind localhost; exec zsh" &
sleep 3

# Terminal 2: RealSense Cameras (MANDATORY - Start early!)
echo "[*] Starting RealSense Cameras..."
gnome-terminal --title="RealSense Cameras" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 launch realsense_cameras ee_camera.launch.py; exec zsh" &
sleep 4

# Terminal 3: Rosbridge
echo "[*] Starting Rosbridge WebSocket..."
gnome-terminal --title="Rosbridge" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 run rosbridge_server rosbridge_websocket; exec zsh" &
sleep 4

# Terminal 4: MoveIt (Real Robot - Start Early!)
echo "[*] Starting MoveIt for Franka FR3..."
gnome-terminal --title="MoveIt (Franka FR3)" --working-directory="$HOME/franka_ros2_ws" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 launch franka_fr3_moveit_config moveit.launch.py robot_ip:=172.16.0.2 use_fake_hardware:=false; exec zsh" &
sleep 5

# Terminal 5: Coordinator Node
echo "[*] Starting Coordinator..."
gnome-terminal --title="Coordinator Node" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 run franka_coordinator coordinator_node; exec zsh" &
sleep 3

# Terminal 6: Web Handler (AFTER Web UI!)
echo "[*] Starting Web Handler..."
gnome-terminal --title="Web Handler" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 run franka_coordinator web_handler; exec zsh" &
sleep 3

# Terminal 7: LLM Coordinator
echo "[*] Starting LLM Coordinator..."
gnome-terminal --title="LLM Coordinator" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 run franka_llm_planner llm_coordinator; exec zsh" &
sleep 3

# Terminal 8: VLM Agent
echo "[*] Starting VLM Agent..."
gnome-terminal --title="VLM Agent" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 run franka_vlm_agent vlm_node; exec zsh" &
sleep 3

# Terminal 9: Motion Executor (Wait for MoveIt to fully initialize!)
echo "[*] Starting Motion Executor (waiting 10s for MoveIt)..."
gnome-terminal --title="Motion Executor" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 10 && source install/setup.bash 2>/dev/null && ros2 run franka_motion_executor motion_executor; exec zsh" &
sleep 2

echo ""
echo "[OK] All nodes started!"
echo ""
echo "System Status:"
echo "  - Web Dashboard: http://localhost:8000"
echo "  - Ollama API: http://localhost:11434"
echo ""
echo "[INFO] Wait 15-20 seconds for all nodes to initialize (MoveIt takes longer)"
echo "[INFO] To stop all nodes, run: ./stop_system.sh"
echo ""

# Wait a bit then check if nodes are running
sleep 5
echo "[*] Checking ROS2 nodes..."
source install/setup.bash 2>/dev/null
ros2 node list 2>/dev/null || echo "[WARN] ROS2 nodes not yet visible (this is normal, wait a few seconds)"
