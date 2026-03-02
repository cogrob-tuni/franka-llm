# Franka Motion Executor Package

**Package**: `franka_motion_executor`  
**Description**: MoveIt2-based motion execution layer that controls the Franka Emika FR3 robot arm for pick, place, handover, home, and dance operations.

## Overview

The motion executor package provides:
- High-level motion primitives (pick, place, handover)
- MoveIt2 trajectory planning and execution
- Gripper control integration
- Collision avoidance
- Safe home position return
- Creative dance motion sequence
- Motion status publishing

## Architecture

```
Motion Command → motion_executor_node.py
                        ↓
                  MoveIt2 Planning
                        ↓
                  ┌─────┴─────┐
                  ↓           ↓
            Arm Control   Gripper Control
                  ↓           ↓
            FR3 Hardware   Franka Gripper
```

## Key Components

### motion_executor_node.py

Main motion execution node that:
- Receives motion commands with target positions
- Plans collision-free trajectories using MoveIt2
- Executes coordinated arm + gripper movements
- Maintains safety constraints (velocity, acceleration)
- Publishes execution status
- Implements special motions (go_home, dance)

**Topics:**
- Subscribes:
  - `/motion/command` - Motion commands with target position
  
- Publishes:
  - `/motion/status` - Execution status updates
  
**Services:**
- None (uses action clients internally for MoveIt2)

**Actions:**
- Uses `/fr3_arm_controller/follow_joint_trajectory` for arm
- Uses gripper action server for gripper control

## Configuration

Motion parameters from `/home/arash/franka-llm/config.yaml`:

```yaml
robot:
  # Motion heights (meters)
  safe_height: 0.60              # Safe navigation height above workspace
  grasp_height: 0.14             # Height to grasp objects (table + object)
  handover_height: 0.30          # Height for human handover
  
  # Object properties
  held_object_height: 0.10       # Typical object height for stacking
  placement_clearance: 0.02      # Clearance above target when placing
  
  # Gripper settings (meters)
  gripper_open_width: 0.08       # Fully open gripper width
  gripper_closed_width: 0.03     # Closed gripper width for grasping
  
  # Motion scaling
  default_velocity_scaling: 0.1  # Slow, precise movements (10%)
  safe_velocity_scaling: 0.5     # Medium speed for safe navigation (50%)
  fast_velocity_scaling: 0.8     # Faster movements for dance (80%)
  
  # MoveIt planning
  planning_time: 5.0             # Max planning time (seconds)
  num_planning_attempts: 10      # Number of planning retries
```

## Motion Primitives

### 1. Pick

Picks up an object at specified position:
```python
# Phases:
1. Move to safe_height above target
2. Move down to grasp_height
3. Close gripper
4. Move back up to safe_height
```

**Command format**:
```json
{
  "action": "pick",
  "target": "blue_cube",
  "position": {"x": 0.5, "y": 0.2, "z": 0.15}
}
```

### 2. Place

Places held object at specified location:
```python
# Phases:
1. Move to safe_height above target
2. Move down to placement height
3. Open gripper
4. Move back up to safe_height
```

**Command format**:
```json
{
  "action": "place",
  "target": "table",
  "position": {"x": 0.4, "y": -0.1, "z": 0.10},
  "placement_type": "direct"  // or "stacking" or "relative"
}
```

### 3. Handover

Hands object to human:
```python
# Phases:
1. Move to handover_height at target position
2. Open gripper
3. Wait 1 second
4. Return to safe_height
```

**Command format**:
```json
{
  "action": "handover",
  "target": "human_hand",
  "position": {"x": 0.3, "y": 0.0, "z": 0.30}
}
```

### 4. Go Home

Returns to safe home configuration:
```python
# Single operation:
- Move all joints to [0, 0, 0, -1.5708, 0, 1.5708, 0.7854]
- Uses safe_velocity_scaling (50%)
```

**Command format**:
```json
{
  "action": "go_home"
}
```

### 5. Dance

Performs creative 7-position motion sequence:
```python
# Positions (X, Y, Z in meters):
1. (0.40, +0.20, 0.50)  # Right
2. (0.40, -0.20, 0.50)  # Left
3. (0.30,  0.00, 0.40)  # Down center
4. (0.30,  0.00, 0.60)  # Up center
5. (0.50, +0.15, 0.45)  # Forward right
6. (0.50, -0.15, 0.45)  # Forward left
7. (0.35,  0.00, 0.55)  # Center mid
8. (0.50,  0.00, 0.60)  # Final position
```

**Command format**:
```json
{
  "action": "dance"
}
```

## Testing

### 1. Test Motion Executor Startup

```bash
# Start motion executor
cd ~/franka-llm
source install/setup.bash
ros2 run franka_motion_executor motion_executor_node

# Check logs for config loading:
# ✓ Robot Motion Configuration:
#   • safe_height: 0.60 m
#   • grasp_height: 0.14 m
#   ...
```

### 2. Test Go Home

```bash
# Send go_home command
ros2 topic pub --once /motion/command std_msgs/msg/String \
  "data: '{\"action\": \"go_home\"}'"

# Monitor status
ros2 topic echo /motion/status

# Expected:
# status: "executing" → "completed"
```

### 3. Test Pick Motion

```bash
# Send pick command
ros2 topic pub --once /motion/command std_msgs/msg/String \
  "data: '{\"action\": \"pick\", \"target\": \"test_object\", \"position\": {\"x\": 0.5, \"y\": 0.0, \"z\": 0.15}}'"

# Watch arm move through phases:
# 1. To (0.5, 0.0, 0.60) - safe height
# 2. To (0.5, 0.0, 0.14) - grasp height
# 3. Gripper closes
# 4. Back to safe height
```

### 4. Test Dance Sequence

```bash
# Send dance command
ros2 topic pub --once /motion/command std_msgs/msg/String \
  "data: '{\"action\": \"dance\"}'"

# Watch 7-position sequence (~20 seconds)
# Verify returns to (0.50, 0.0, 0.60) at end
```

### 5. Test Configuration Loading

```bash
# Modify config.yaml
nano ~/franka-llm/config.yaml

# Change: safe_height: 0.70

# Restart node and verify new height in logs:
ros2 run franka_motion_executor motion_executor_node
# Should show: safe_height: 0.70 m
```

### 6. Integration Test with Coordinator

```bash
# Full pick-and-place test:
1. Start all nodes (coordinator, motion_executor, vlm, etc.)
2. Use web UI: "pick up the blue cube"
3. Approve motion confirmation
4. Verify pick executes
5. Say: "place it on the table"
6. Approve motion confirmation
7. Verify place executes
```

## MoveIt2 Integration

The motion executor uses MoveIt2 for:
- **Planning group**: `fr3_arm` (7-DOF arm)
- **End effector**: `fr3_hand` (gripper)
- **Planning algorithm**: RRTConnect (default)
- **Collision checking**: Built-in MoveIt collision detection

### Planning Parameters

```python
move_group.set_planning_time(5.0)              # 5 seconds max
move_group.set_num_planning_attempts(10)        # Up to 10 retries
move_group.set_max_velocity_scaling_factor(0.1) # 10% of max velocity
move_group.set_max_acceleration_scaling_factor(0.1)
```

### Troubleshooting Planning Failures

If planning fails:
1. **Check joint limits**: Ensure target is reachable
2. **Check collisions**: Use RViz to visualize obstacles
3. **Increase planning time**: Edit config.yaml
4. **Change start state**: Move to home first
5. **Adjust velocity scaling**: Try higher values

## Gripper Control

The gripper is controlled via action client:

```python
# Open gripper
self.open_gripper()  # Sets width to gripper_open_width (0.08m)

# Close gripper
self.close_gripper()  # Sets width to gripper_closed_width (0.03m)
```

Gripper parameters:
- **Force**: 50N (configurable in launch file)
- **Speed**: 0.1 m/s
- **Grasp epsilon**: 0.01m (tolerance for grasp success)

## Safety Features

### 1. Velocity Scaling
- **Slow (0.1)**: Precise pick/place operations
- **Medium (0.5)**: Safe navigation between waypoints
- **Fast (0.8)**: Dance motions (no objects held)

### 2. Safe Height
- Always navigate at `safe_height` (0.60m) between operations
- Prevents collisions with workspace objects
- Configurable in config.yaml

### 3. Collision Avoidance
- MoveIt2 built-in collision checking
- Detects self-collisions and workspace obstacles
- Aborts motion if collision detected

### 4. Planning Validation
- Verifies plan exists before execution
- Checks for planning failures and reports errors
- Publishes failure status to `/motion/status`

## Development

### Adding New Motion Primitive

1. **Add handler method**:
```python
def handle_your_action_request(self, data):
    self.get_logger().info('Executing your_action')
    self._publish_status('executing', 'your_action in progress')
    
    # Your motion logic here
    success = self.your_motion_sequence()
    
    if success:
        self._publish_status('completed', 'your_action completed')
    else:
        self._publish_status('failed', 'your_action failed')
```

2. **Register in command callback**:
```python
def command_callback(self, msg):
    action = data.get('action', '')
    if action == 'your_action':
        self.handle_your_action_request(data)
```

3. **Update LLM prompt** in `franka_llm_planner`

### Modifying Motion Parameters

Edit `config.yaml`:
```yaml
robot:
  safe_height: 0.70  # Increase safe navigation height
  grasp_height: 0.12 # Lower grasp height for thinner objects
```

No code changes needed - motion executor loads config on startup.

### Custom Waypoints for Dance

Edit `handle_dance_request()` in `motion_executor_node.py`:
```python
dance_positions = [
    (0.40, 0.20, 0.50),  # Your custom positions
    (0.40, -0.20, 0.50),
    # ... add more
]
```

## Dependencies

**Python packages:**
- rclpy
- moveit_py (MoveIt2 Python interface)
- std_msgs
- geometry_msgs
- sensor_msgs
- trajectory_msgs
- control_msgs
- PyYAML

**ROS2 packages:**
- moveit2
- franka_ros2 (hardware interface)
- joint_trajectory_controller
- gripper_action_controller

## Troubleshooting

**Issue**: "Planning failed" errors
- **Cause**: Target position unreachable or in collision
- **Fix**: 
  ```bash
  # Visualize in RViz
  ros2 launch moveit_config demo.launch.py
  
  # Check target position is within workspace:
  # X: 0.2 to 0.8 m (forward)
  # Y: -0.5 to 0.5 m (left/right)
  # Z: 0.0 to 0.8 m (height)
  ```

**Issue**: Gripper not responding
- **Cause**: Gripper action server not running
- **Fix**: 
  ```bash
  # Check gripper controller
  ros2 control list_controllers
  
  # Should show: franka_gripper_controller
  # If not, load it:
  ros2 control load_controller franka_gripper_controller
  ros2 control set_controller_state franka_gripper_controller active
  ```

**Issue**: Robot moves too fast/slow
- **Cause**: Velocity scaling incorrect
- **Fix**: Adjust in config.yaml
  ```yaml
  robot:
    default_velocity_scaling: 0.2  # Increase from 0.1
  ```

**Issue**: Motion stops mid-execution
- **Cause**: Joint limit violation or trajectory timeout
- **Fix**:
  - Check RViz for joint states
  - Increase planning_time in config
  - Verify controller is running:
    ```bash
    ros2 control list_controllers
    # Should show: fr3_arm_controller [active]
    ```

**Issue**: Dance sequence not smooth
- **Cause**: Planning between waypoints takes time
- **Fix**:
  - Use joint-space planning instead of Cartesian
  - Add intermediate waypoints for smoother paths
  - Increase velocity_scaling for dance

## Status Messages

Motion status messages include:
```json
{
  "status": "executing" | "completed" | "failed",
  "message": "Descriptive message",
  "timestamp": "ISO 8601 timestamp"
}
```

Monitor status:
```bash
ros2 topic echo /motion/status
```

## Performance

Typical execution times:
- **Go Home**: 3-5 seconds
- **Pick**: 8-12 seconds (approach → grasp → return)
- **Place**: 8-12 seconds (approach → release → return)
- **Handover**: 5-8 seconds (approach → release → return)
- **Dance**: 18-25 seconds (7 positions)

## Launch

```bash
# Standalone motion executor
ros2 run franka_motion_executor motion_executor_node

# As part of main system
ros2 launch franka_coordinator main.launch.py
```

## Configuration at Startup

The motion executor logs all configuration on startup:
```
✓ Robot Motion Configuration:
  • safe_height: 0.60 m
  • grasp_height: 0.14 m
  • handover_height: 0.30 m
  • held_object_height: 0.10 m
  • placement_clearance: 0.02 m
  • gripper_open_width: 0.08 m
  • gripper_closed_width: 0.03 m
  • default_velocity_scaling: 0.10
```

This helps verify configuration is loaded correctly.
