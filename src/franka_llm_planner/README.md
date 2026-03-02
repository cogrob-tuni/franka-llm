# Franka LLM Planner Package

**Package**: `franka_llm_planner`  
**Description**: Natural language understanding layer using LLaMA 3.1 to interpret user commands and route them to appropriate agents (VLM, Motion, or direct response).

## Overview

The LLM planner package provides:
- Natural language command parsing and intent recognition
- Decision routing to VLM agent, motion executor, or direct responses
- Special handling for confirmation-required actions (go_home, dance)
- Conversational chat capabilities
- Status monitoring and error handling

## Architecture

```
User Command (Natural Language)
        ↓
llm_coordinator_node.py
        ↓
   [LLaMA 3.1 8B]
        ↓
    JSON Decision
        ↓
   ┌────┴────┐
   ↓         ↓
VLM Agent  Motion Executor
```

## Key Components

### llm_coordinator_node.py

Main LLM coordination node that:
- Receives natural language commands from users
- Queries local LLaMA model via Ollama API
- Parses LLM responses into structured JSON decisions
- Routes commands to appropriate agents
- Handles special cases for go_home and dance (confirmation flow)
- Publishes status and responses

**Topics:**
- Subscribes:
  - `/user_command` - User input from web dashboard
  - `/vlm/explanation` - VLM analysis results
  - `/vlm_center_position` - VLM object positions
  - `/motion/status` - Motion execution status
  
- Publishes:
  - `/vlm_request` - Requests to VLM for scene understanding
  - `/vlm_grounding` - Direct grounding for go_home/dance
  - `/motion_command` - Direct motion commands
  - `/coordinator_response` - Responses to user
  - `/coordinator/status` - Status updates

## LLM System Prompt

The LLM is configured with a detailed system prompt that defines:

1. **Available Agents**:
   - `VLM` - Vision-Language Model for object detection
   - `MOTION` - Direct motion commands (no confirmation)
   - `BOTH` - VLM + Motion with user confirmation
   - `NONE` - Direct response (greetings, questions)

2. **Action Types**:
   - `pick` - Pick up an object
   - `place` - Place object at location (direct/stacking/relative)
   - `handover` - Hand object to human
   - `go_home` - Return to safe home position (requires confirmation)
   - `dance` - Perform creative motion sequence (requires confirmation)

3. **Decision Format**:
```json
{
  "target_agent": "both",
  "action": "pick",
  "parameters": {
    "object": "blue cube",
    "location": "table"
  },
  "response": "I'll pick up the blue cube for you."
}
```

## Configuration

LLM settings from `/home/arash/franka-llm/config.yaml`:

```yaml
llm:
  model: "llama3.1:8b"
  base_url: "http://localhost:11434"
  temperature: 0.1
  max_tokens: 500
```

## Testing

### 1. Test LLM Coordinator Standalone

```bash
# Start the coordinator
cd ~/franka-llm
source install/setup.bash
ros2 run franka_llm_planner llm_coordinator_node

# In another terminal, send test command
ros2 topic pub --once /user_command std_msgs/msg/String \
  "data: 'pick up the red cube'"

# Check LLM response
ros2 topic echo /coordinator_response

# Expected output:
# - target_agent: "both"
# - action: "pick"
# - parameters: {"object": "red cube"}
```

### 2. Test Special Commands (go_home, dance)

```bash
# Test go_home with confirmation
ros2 topic pub --once /user_command std_msgs/msg/String \
  "data: 'go home'"

# Verify VLM grounding published with skip_vlm flag
ros2 topic echo /vlm_grounding --once

# Expected:
# {
#   "action": "go_home",
#   "target": "home_position",
#   "skip_vlm": true,
#   ...
# }
```

### 3. Test Conversational Responses

```bash
# Test greeting
ros2 topic pub --once /user_command std_msgs/msg/String \
  "data: 'hello robot'"

# Check response (should be direct, no agent routing)
ros2 topic echo /coordinator_response

# Expected:
# - target_agent: "none"
# - response: "Hello! I'm ready to help..."
```

### 4. Test Placement Types

```bash
# Test direct placement
ros2 topic pub --once /user_command std_msgs/msg/String \
  "data: 'place the cube on the table'"

# Test stacking
ros2 topic pub --once /user_command std_msgs/msg/String \
  "data: 'stack the cube on top of the red block'"

# Test relative placement  
ros2 topic pub --once /user_command std_msgs/msg/String \
  "data: 'place the cube next to the green block'"

# Check VLM requests include placement_type
ros2 topic echo /vlm_request
```

## Ollama Setup

### Install Ollama

```bash
# Download and install
curl -fsSL https://ollama.com/install.sh | sh

# Pull LLaMA 3.1 model
ollama pull llama3.1:8b

# Verify model is available
ollama list
```

### Start Ollama Service

```bash
# Start Ollama API server (runs on port 11434)
ollama serve

# Test with curl
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.1:8b",
  "prompt": "Hello",
  "stream": false
}'
```

### Change Model

Edit `config.yaml`:
```yaml
llm:
  model: "llama3.1:70b"  # Use larger model
  # or
  model: "mistral:latest"  # Try different model
```

## Development

### Modifying the System Prompt

Edit `llm_coordinator_node.py`, in the `__init__` method:

```python
self.system_prompt = """
Your updated system prompt here.

Add new actions, examples, or constraints.
"""
```

Rebuild:
```bash
colcon build --packages-select franka_llm_planner
```

### Adding New Action Types

1. **Update System Prompt** with new action:
```python
- **dance**: Perform creative motion sequence
  Target: BOTH (VLM + Motion)
  REQUIRES USER CONFIRMATION before execution
```

2. **Add Special Handling** if needed:
```python
# In command_callback after parsing decision
if action == 'your_new_action':
    # Custom routing logic
    self.route_to_custom_handler(decision)
```

3. **Update Motion Executor** to handle the action:
```python
# In franka_motion_executor/motion_executor_node.py
def handle_your_new_action_request(self, data):
    # Implementation
    pass
```

### Debugging LLM Responses

Enable detailed logging:
```python
# In llm_coordinator_node.py
self.get_logger().info(f'LLM raw response: {llm_response}')
self.get_logger().info(f'Parsed decision: {decision}')
```

Check LLM performance:
```bash
# Monitor response times
ros2 topic hz /coordinator_response

# Check for parsing errors in logs
ros2 run franka_llm_planner llm_coordinator_node --ros-args --log-level DEBUG
```

## Command Examples

### Pick and Place
- "pick up the blue cube"
- "grab the red ball"
- "place it on the table"
- "put the cube next to the green block"
- "stack the small cube on top of the large one"

### Handover
- "hand me the tool"
- "give me the red cube"
- "bring the object to me"

### Home and Dance
- "go home"
- "return to home position"
- "go back to start"
- "dance"
- "perform a dance"
- "do a dance move"

### Questions
- "what do you see?"
- "describe the scene"
- "what objects are on the table?"

### Greetings
- "hello"
- "hi robot"
- "how are you?"

## Dependencies

**Python packages:**
- rclpy
- std_msgs
- geometry_msgs
- requests (for Ollama API)
- json
- datetime
- PyYAML

**External services:**
- Ollama (local LLM server)
- LLaMA 3.1 8B model

## Troubleshooting

**Issue**: "Connection refused" to Ollama
- **Cause**: Ollama service not running
- **Fix**: 
  ```bash
  ollama serve
  # In another terminal
  ollama list  # Verify model exists
  ```

**Issue**: LLM responses are slow (>5 seconds)
- **Cause**: Model too large or CPU-only inference
- **Fix**:
  - Use smaller model: `ollama pull llama3.1:8b` (not 70b)
  - Enable GPU acceleration (CUDA/ROCm)
  - Reduce max_tokens in config.yaml

**Issue**: LLM not understanding commands
- **Cause**: System prompt unclear or model hallucinating
- **Fix**:
  1. Check examples in system prompt match your use case
  2. Add temperature: 0.0 for more deterministic responses
  3. Try different model: mistral, phi, etc.

**Issue**: JSON parsing errors
- **Cause**: LLM returning malformed JSON
- **Fix**:
  - Lower temperature (more deterministic)
  - Add explicit JSON format examples in prompt
  - Implement retry logic with error message

**Issue**: go_home/dance not showing confirmation
- **Cause**: VLM grounding publisher not configured
- **Fix**: Ensure `self.vlm_grounding_pub` exists in `__init__`
  ```python
  self.vlm_grounding_pub = self.create_publisher(String, '/vlm_grounding', 10)
  ```

## Performance

Typical response times on modern hardware:
- LLM inference: 0.5-2 seconds (8B model, GPU)
- Total command → response: 1-3 seconds

Optimization tips:
- Use GPU (CUDA) for 3-5x speedup
- Reduce max_tokens to 200-300 for faster responses
- Use smaller models (7B-8B) instead of 13B+
- Enable Ollama model caching

## Status Updates

The coordinator publishes status at 1 Hz:
- **vlm_active**: Whether VLM agent is responding
- **motion_active**: Whether motion executor is active
- **current_request**: Current command being processed
- **waiting_for_vlm**: Waiting for vision results
- **waiting_for_motion**: Waiting for motion completion

## Integration

The LLM coordinator integrates with:
1. **Web Handler** - Receives user commands
2. **VLM Agent** - Sends scene understanding requests
3. **Motion Executor** - Sends motion commands
4. **Coordinator** - Routes via VLM grounding for confirmation

Typical flow:
```
User: "pick up the red cube"
  ↓
LLM: {target_agent: "both", action: "pick", object: "red cube"}
  ↓
VLM: Detects cube at pixel (640, 480)
  ↓
Coordinator: Converts to 3D (0.5, 0.2, 0.15)
  ↓
Web: Shows confirmation dialog
  ↓
User: Clicks "Approve"
  ↓
Motion: Executes pick at (0.5, 0.2, 0.15)
```
