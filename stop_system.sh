#!/usr/bin/env bash
# Franka LLM System Shutdown Script
# Stops all running nodes and services

set -e

echo "Stopping Franka LLM System..."
echo "================================"

# Function to kill process by name
kill_process() {
    local process_name=$1
    local display_name=$2
    
    if pgrep -f "$process_name" > /dev/null; then
        echo "[*] Stopping $display_name..."
        pkill -9 -f "$process_name" 2>/dev/null || true
        sleep 1
    else
        echo "[OK] $display_name not running"
    fi
}

# Stop ROS2 nodes
kill_process "coordinator_node" "Coordinator"
kill_process "web_handler" "Web Handler"
kill_process "llm_coordinator" "LLM Coordinator"
kill_process "vlm_node" "VLM Agent"
kill_process "motion_executor" "Motion Executor"
kill_process "rosbridge_websocket" "Rosbridge"

# Stop MoveIt and all its subprocesses
echo "[*] Stopping MoveIt..."
kill_process "franka_fr3_moveit_config" "MoveIt Launch"
kill_process "move_group" "MoveIt Move Group"
kill_process "rviz2" "RViz2"
kill_process "robot_state_publisher" "Robot State Publisher"
kill_process "joint_state_publisher" "Joint State Publisher"
kill_process "ros2_control_node" "ROS2 Control"
kill_process "franka_gripper" "Franka Gripper"
echo "[OK] All MoveIt processes stopped"

# Stop cameras if running
kill_process "ee_camera.launch.py" "RealSense Cameras"

# Stop web UI server (Python HTTP server on port 8000)
echo "[*] Stopping Web UI Server..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || echo "[OK] Web UI Server not running"

# Optionally stop Ollama (uncomment if you want to stop it)
# echo "[*] Stopping Ollama..."
# pkill -x "ollama" 2>/dev/null || echo "[OK] Ollama not running"

echo ""
echo "[OK] All nodes stopped!"
echo ""
echo "[*] Remaining ROS2 nodes (if any):"
source "$HOME/franka-llm/install/setup.bash" 2>/dev/null
ros2 node list 2>/dev/null || echo "  (No ROS2 nodes running)"
echo ""
echo "[INFO] To restart the system, run: ./start_system.sh"
