# Franka LLM Web Dashboard

Modern web interface for controlling the Franka FR3 robot with natural language. Integrated with ROS2 for real-time task execution, VLM image display, and motion confirmation.

## Features

✨ **Chat Interface**
- Natural language command processing
- VLM scene descriptions with images
- Motion confirmation dialogs with coordinates
- Real-time status updates

🤖 **LLM + VLM Integration**
- LLaMA 3.1 8B for command understanding
- Qwen2.5-VL 32B for object detection
- Debug image visualization
- 3D position display

🔒 **Safety**
- User approval required for all motions
- Shows target coordinates before execution
- Emergency stop capability
- Real-time status monitoring

## Quick Start

See **[/RUNNING.md](../../RUNNING.md)** for complete system startup.

**Start web server:**
```bash
cd ~/franka-llm/ui/web_chat_dashboard
python3 -m http.server 8000
```

**Access:** http://localhost:8000

**Requirements:**
- ROSBridge WebSocket running on port 9090
- Web Handler and other ROS nodes running
- See main RUNNING.md for full startup sequence

## Usage Examples

**Scene inspection:**
```
User: "What do you see on the table?"
→ VLM analyzes scene → Returns description with image
```

**Pick and place:**
```
User: "Pick up the yellow dice"
→ VLM detects object with image → Shows confirmation with 3D coords
→ User clicks "Approve" → Robot executes
```

**Stacking:**
```
User: "Stack the small cube on top of the red block"
→ System calculates Z offset → User approves → Robot stacks
```

**Special commands:**
```
"go home" → Robot returns to home position
"dance" → Robot performs sequence
"hand me the tool" → Handover to human
```

## ROS Topics

**Web → ROS2:**
- `/web/request` - User commands and confirmations

**ROS2 → Web:**
- `/web/response` - Chat responses, images, confirmations
- `/web/status` - System status updates

## File Structure

```
ui/web_chat_dashboard/
├── index.html           # Main HTML structure
├── styles.css           # Modern dark theme styling
├── app.js               # Application initialization & navigation
├── rosbridge.js         # ROSBridge WebSocket client
├── modules/
│   ├── chat.js          # Chat message handling
│   ├── camera.js        # Camera feed display
│   ├── status.js        # Status monitoring
│   ├── confirm.js       # Confirmation dialogs
│   └── utils.js         # Utility functions
├── assets/
│   └── logo.png         # Dashboard logo
└── README.md            # This file
```

## Development

### Adding New Features

1. **New View:**
   - Add HTML container in index.html
   - Add CSS styles in styles.css
   - Create module in modules/ if needed
   - Add nav button and route in app.js

2. **New ROS Topic:**
   - Subscribe in appropriate module
   - Handle in message callback
   - Update status display if needed

3. **New Status Indicator:**
   - Add status-card HTML
   - Initialize in status.js constructor
   - Update in handleCoordinatorStatus()

### Debugging

**Check browser console:**
```javascript
console.log('Debug: ' + variable);
```

**Check ROS topics:**
```bash
ros2 topic list              # List all topics
ros2 topic echo /topic/name  # View messages
```

**Check coordinator logs:**
```bash
ros2 run franka_coordinator coordinator_node --ros-args --log-level debug
```

## Troubleshooting

## Troubleshooting

**"Disconnected" status:**
- ROSBridge not running: `ros2 launch rosbridge_server rosbridge_websocket_launch.xml`
- Wrong WebSocket URL (check: ws://localhost:9090)

**Messages not appearing:**
- Web Handler not running: `ros2 run franka_coordinator web_handler`
- Check browser console (F12) for errors

**Images not showing:**
- VLM not saving debug images
- Check `~/franka-llm/debug_images/` directory

**Confirmation dialog not appearing:**
- Web Handler must start AFTER web server
- Restart web handler if needed

## File Structure

```
web_chat_dashboard/
├── index.html           # Main HTML structure
├── styles.css           # Dark theme styling
├── app.js               # Application initialization
├── rosbridge.js         # ROSBridge WebSocket client
├── modules/
│   ├── chat.js          # Chat and image display
│   ├── status.js        # Status monitoring
│   ├── confirm.js       # Motion confirmation dialogs
│   └── utils.js         # Utility functions
└── README.md            # This file
```

## Browser Support

- Chrome/Chromium 90+ (recommended)
- Firefox 88+
- Safari 14+
- Edge 90+

---

For full system documentation, see [main README](../../README.md)
