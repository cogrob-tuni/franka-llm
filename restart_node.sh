#!/usr/bin/env bash
# Helper script to restart a single node

WORKSPACE_DIR="$HOME/franka-llm"

show_usage() {
    echo "Usage: ./restart_node.sh <node_name>"
    echo ""
    echo "Available nodes:"
    echo "  ui              - Web UI server (port 8000)"
    echo "  camera          - RealSense cameras"
    echo "  rosbridge       - Rosbridge WebSocket server"
    echo "  moveit          - MoveIt motion planning"
    echo "  coordinator     - Franka coordinator"
    echo "  web_handler     - Web interface handler"
    echo "  llm             - LLM coordinator"
    echo "  vlm             - VLM agent"
    echo "  motion          - Motion executor"
    echo "  ollama          - Ollama server"
    echo ""
    echo "Example: ./restart_node.sh motion"
}

if [ -z "$1" ]; then
    show_usage
    exit 1
fi

NODE=$1

case $NODE in
    ui)
        echo "[*] Restarting Web UI Server..."
        lsof -ti:8000 | xargs kill -9 2>/dev/null || true
        sleep 1
        gnome-terminal --title="Web UI Server" --working-directory="$WORKSPACE_DIR/ui/web_chat_dashboard" -- zsh -c "python3 -m http.server 8000 --bind localhost; exec zsh" &
        echo "[OK] Web UI restarted at http://localhost:8000"
        ;;
    
    ollama)
        echo "[*] Restarting Ollama Server..."
        pkill -9 -x "ollama" 2>/dev/null || true
        sleep 1
        gnome-terminal --title="Ollama Server" -- zsh -c "ollama serve; exec zsh" &
        echo "[OK] Ollama restarted at http://localhost:11434"
        ;;
    
    camera)
        echo "[*] Restarting RealSense Cameras..."
        pkill -9 -f "realsense_cameras.*ee_camera" 2>/dev/null || true
        sleep 1
        cd "$WORKSPACE_DIR"
        gnome-terminal --title="RealSense Cameras" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 launch realsense_cameras ee_camera.launch.py; exec zsh" &
        echo "[OK] Cameras restarted"
        ;;
    
    rosbridge)
        echo "[*] Restarting Rosbridge..."
        pkill -9 -f "rosbridge_server.*rosbridge_websocket" 2>/dev/null || true
        sleep 1
        gnome-terminal --title="Rosbridge" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 run rosbridge_server rosbridge_websocket; exec zsh" &
        echo "[OK] Rosbridge restarted"
        ;;
    
    moveit)
        echo "[*] Restarting MoveIt (killing all subprocesses)..."
        pkill -9 -f "franka_fr3_moveit_config" 2>/dev/null || true
        pkill -9 -f "move_group" 2>/dev/null || true
        pkill -9 -f "rviz2" 2>/dev/null || true
        pkill -9 -f "robot_state_publisher" 2>/dev/null || true
        pkill -9 -f "joint_state_publisher" 2>/dev/null || true
        pkill -9 -f "ros2_control_node" 2>/dev/null || true
        pkill -9 -f "franka_gripper" 2>/dev/null || true
        sleep 3
        gnome-terminal --title="MoveIt (Franka FR3)" --working-directory="$HOME/franka_ros2_ws" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 launch franka_fr3_moveit_config moveit.launch.py robot_ip:=172.16.0.2 use_fake_hardware:=false; exec zsh" &
        echo "[OK] MoveIt restarting (wait 15-20s for full initialization)"
        echo "[INFO] After startup, manually load controllers:"
        echo "       ros2 control load_controller joint_state_broadcaster --set-state active"
        echo "       ros2 control load_controller franka_robot_state_broadcaster --set-state active"
        echo "       ros2 control load_controller fr3_arm_controller --set-state active"
        ;;
    
    coordinator)
        echo "[*] Restarting Coordinator..."
        pkill -9 -f "franka_coordinator.*coordinator_node" 2>/dev/null || true
        sleep 1
        gnome-terminal --title="Coordinator Node" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 run franka_coordinator coordinator_node; exec zsh" &
        echo "[OK] Coordinator restarted"
        ;;
    
    web_handler)
        echo "[*] Restarting Web Handler..."
        pkill -9 -f "franka_coordinator.*web_handler" 2>/dev/null || true
        sleep 1
        gnome-terminal --title="Web Handler" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 run franka_coordinator web_handler; exec zsh" &
        echo "[OK] Web Handler restarted"
        ;;
    
    llm)
        echo "[*] Restarting LLM Coordinator..."
        pkill -9 -f "franka_llm_planner.*llm_coordinator" 2>/dev/null || true
        sleep 1
        gnome-terminal --title="LLM Coordinator" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 run franka_llm_planner llm_coordinator; exec zsh" &
        echo "[OK] LLM Coordinator restarted"
        ;;
    
    vlm)
        echo "[*] Restarting VLM Agent..."
        pkill -9 -f "franka_vlm_agent.*vlm_node" 2>/dev/null || true
        sleep 1
        gnome-terminal --title="VLM Agent" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 6 && source install/setup.bash 2>/dev/null && ros2 run franka_vlm_agent vlm_node; exec zsh" &
        echo "[OK] VLM Agent restarted"
        ;;
    
    motion)
        echo "[*] Restarting Motion Executor..."
        pkill -9 -f "franka_motion_executor.*motion_executor" 2>/dev/null || true
        sleep 1
        gnome-terminal --title="Motion Executor" --working-directory="$WORKSPACE_DIR" -- zsh -c "sleep 10 && source install/setup.bash 2>/dev/null && ros2 run franka_motion_executor motion_executor; exec zsh" &
        echo "[OK] Motion Executor restarted (10s delay for MoveIt)"
        ;;
    
    *)
        echo "[ERROR] Unknown node: $NODE"
        show_usage
        exit 1
        ;;
esac

echo ""
echo "[INFO] Check with: ros2 node list"
