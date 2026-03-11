#!/usr/bin/env python3
"""
Web Handler Node - Bridge between web dashboard and ROS2
Handles:
- Publishing web requests to coordinator (LLM routing)
- Subscribing to coordinator and VLM responses
- Forwarding VLM images to web dashboard
- Handling motion confirmation flow
- Status monitoring
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import CameraInfo
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
import json
import time
from datetime import datetime
from threading import Lock
from pathlib import Path
import base64
import yaml
import requests


class WebHandler(Node):
    """Node that bridges web dashboard communication with ROS2."""
    
    def __init__(self):
        super().__init__('web_handler')
        self.status_lock = Lock()
        
        # Current system status
        self.status_cache = {
            'robot_state': 'Disconnected',
            'vision_state': 'Offline',
            'llm_state': 'Offline',
            'coordinator_state': 'Offline',
            'motion_state': 'Idle',
            'camera_state': 'Offline',
            'bridge_state': 'Online',
            'last_detection': 'None',
            'last_action': 'None',
            'timestamp': datetime.now().isoformat(),
            'config': {
                'llm_model': 'Loading...',
                'llm_temperature': 'Loading...',
                'vlm_model': 'Loading...',
                'vlm_temperature': 'Loading...',
                'ollama_url': 'Loading...',
                'aruco_offset_x': 'Loading...',
                'aruco_offset_y': 'Loading...',
                'aruco_offset_z': 'Loading...',
                'safe_height': 'Loading...',
                'grasp_height': 'Loading...',
                'handover_height': 'Loading...',
                'gripper_close': 'Loading...',
                'gripper_open': 'Loading...',
                'velocity_default': 'Loading...',
                'velocity_slow': 'Loading...',
                'velocity_fast': 'Loading...'
            }
        }
        # Per-component last-seen timestamps for staleness detection
        self._last_seen = {
            'llm': None,
            'vlm': None,
            'coordinator': None,
            'motion': None,
            'camera': None,
        }
        # Counter for periodic node-graph check (every 5s)
        self._node_check_counter = 0
        
        # Pending motion confirmation state
        self.pending_motion = None
        self.latest_robot_position = None  # Cached robot-frame coords from coordinator
        self.confirmation_pending = False  # Waiting for position before showing confirmation

        # Benchmark: wall-clock start time of the current perception-and-planning cycle
        self._bench_t_start: float = 0.0
        # Memory snapshots sampled at the moment each model finishes its work.
        # Capturing here (rather than at _bench_finish) prevents the problem where
        # loading the large VLM model evicts the LLM from VRAM before we read it.
        self._bench_llm_mem: float = 0.0
        self._bench_vlm_mem: float = 0.0
        # Per-request inference times from Ollama eval_duration — these actually vary!
        # Memory above is a fixed model property; inference time reflects prompt/complexity.
        self._bench_llm_infer_ms: float = 0.0
        self._bench_vlm_infer_ms: float = 0.0
        self.vlm_model_name = 'VLM'  # Default, updated from system info
        self.llm_model_name = 'LLM'  # Default, updated from system info
        
        # System configuration cache
        self.system_config = {
            'llm': {},
            'vlm': {},
            'camera': {}
        }
        
        # Load system configuration to get paths
        config = self._load_system_config()
        
        # Debug images directory from config
        workspace_root = Path(config['paths']['workspace_root']).expanduser()
        self.debug_images_dir = workspace_root / config['paths']['debug_images']
        
        # Publishers
        # Publish user commands directly to LLM coordinator
        self.user_command_pub = self.create_publisher(
            String, '/user_command', 10
        )
        
        # Subscriber to web requests from browser
        self.web_request_sub = self.create_subscription(
            String, '/web/request', self.handle_web_request, 10
        )
        
        # Publisher for status updates going to web
        self.web_status_pub = self.create_publisher(
            String, '/web/status', 10
        )
        
        # Publisher for chat responses going to web
        self.web_response_pub = self.create_publisher(
            String, '/web/response', 10
        )
        
        # Publisher for user confirmation responses to coordinator
        self.user_confirmation_pub = self.create_publisher(
            String, '/user_confirmation', 10
        )
        
        # Subscribers
        # Coordinator response - main chat responses
        self.coordinator_response_sub = self.create_subscription(
            String, '/coordinator_response', self.handle_coordinator_response, 10
        )
        
        # VLM grounding info with bbox
        self.vlm_grounding_sub = self.create_subscription(
            String, '/vlm_grounding', self.handle_vlm_grounding, 10
        )
        
        # VLM explanation text
        self.vlm_explanation_sub = self.create_subscription(
            String, '/vlm/explanation', self.handle_vlm_explanation, 10
        )
        
        # Subscriber to coordinator status
        self.coordinator_status_sub = self.create_subscription(
            String, '/coordinator/status', self.handle_coordinator_status, 10
        )
        
        # Subscriber to motion status
        self.motion_status_sub = self.create_subscription(
            String, '/motion/status', self.handle_motion_status, 10
        )
        
        # Subscriber to vision data
        self.vision_sub = self.create_subscription(
            String, '/vision/detections', self.handle_vision_data, 10
        )

        # Subscriber to robot-frame position info from coordinator
        self.target_position_info_sub = self.create_subscription(
            String, '/target_position_info', self.handle_target_position_info, 10
        )
        
        # Camera info subscription — BEST_EFFORT QoS to match RealSense
        _cam_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1
        )
        self.camera_info_sub = self.create_subscription(
            CameraInfo,
            '/cameras/ee/ee_camera/color/camera_info',
            self.handle_camera_info,
            _cam_qos
        )

        # Timer to publish status updates periodically
        self.status_timer = self.create_timer(1.0, self.publish_web_status)
        
        self.get_logger().info('Web Handler initialized - integrated with LLM Coordinator')
        
        # Load config to status immediately so it's available when status page loads
        self._load_config_to_status()
        
        # Send welcome message with system info after a short delay (one-shot)
        self.welcome_timer = self.create_timer(2.0, self._send_welcome_message_once)
    
    def _load_system_config(self) -> dict:
        """Load configuration from config.yaml."""
        try:
            config_path = self._find_config_file()
            self.get_logger().info(f'Loading config from: {config_path}')
            
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Cache specific sections
            self.system_config['llm'] = config.get('llm', {})
            self.system_config['vlm'] = config.get('vlm', {})
            self.system_config['camera'] = config.get('camera', {})
            self.llm_model_name = self.system_config['llm'].get('model', 'LLM')
            self.vlm_model_name = self.system_config['vlm'].get('model', 'VLM')
            
            self.get_logger().info(f'Loaded config: LLM={self.llm_model_name}, VLM={self.vlm_model_name}')
            return config
        except Exception as e:
            self.get_logger().warn(f'Could not load config.yaml: {e}')
            return {'paths': {'workspace_root': '~/franka-llm', 'debug_images': 'debug_images'}}
    
    def _find_config_file(self) -> Path:
        """Find config.yaml in workspace"""
        current_path = Path(__file__).resolve()
        
        # Try walking up the directory tree
        for parent in [current_path] + list(current_path.parents):
            candidate = parent / 'config.yaml'
            if candidate.exists():
                return candidate
        
        # Fallback to workspace root
        workspace_root = Path.home() / 'franka-llm'
        candidate = workspace_root / 'config.yaml'
        if candidate.exists():
            return candidate
        
        raise FileNotFoundError('Could not find config.yaml')
    
    def _send_welcome_message_once(self):
        """Send welcome message once and cancel timer."""
        try:
            self._send_welcome_message()
            # Cancel the timer so it doesn't repeat
            self.welcome_timer.cancel()
        except Exception as e:
            self.get_logger().error(f'Error in welcome timer: {e}')
    
    def _send_welcome_message(self):
        """Send welcome message with system configuration to web."""
        try:
            llm_cfg = self.system_config.get('llm', {})
            vlm_cfg = self.system_config.get('vlm', {})
            
            config_text = (
                f"👋 Welcome! I\'m your Franka robot assistant."
                f"I'm running **{llm_cfg.get('model', 'an LLM')}** as my language brain and "
                f"**{vlm_cfg.get('model', 'a VLM')}** as my vision system, paired with a RealSense D435i camera. "
                f"Tell me what you'd like to do — I can look at the scene, find objects, plan motions, and move the robot. "
                f"I'll always ask for your approval before executing anything."
            )
            
            welcome_message = {
                'type': 'message',
                'sender': 'robot',
                'agent_name': 'Franka Assistant',
                'message': config_text,
                'timestamp': datetime.now().isoformat()
            }
            
            self.web_response_pub.publish(
                String(data=json.dumps(welcome_message))
            )
            self.get_logger().info('Sent welcome message with system configuration')
            
        except Exception as e:
            self.get_logger().error(f'Error sending welcome message: {e}')
    
    def _load_config_to_status(self):
        """Load configuration details into status cache for status page display."""
        try:
            # Load full config
            config_path = self._find_config_file()
            with open(config_path, 'r') as f:
                full_config = yaml.safe_load(f)
            
            # Extract relevant config sections
            llm = full_config.get('llm', {})
            vlm = full_config.get('vlm', {})
            camera = full_config.get('camera', {})
            robot = full_config.get('robot', {})
            
            # Store in status cache for status page
            with self.status_lock:
                self.status_cache['config'] = {
                    'llm_model': llm.get('model', 'N/A'),
                    'llm_temperature': llm.get('temperature') if llm.get('temperature') is not None else 'N/A',
                    'llm_timeout': llm.get('timeout', 'N/A'),
                    'llm_url': llm.get('ollama_url', 'N/A'),
                    'vlm_model': vlm.get('model', 'N/A'),
                    'vlm_temperature': vlm.get('temperature') if vlm.get('temperature') is not None else 'N/A',
                    'vlm_timeout': vlm.get('timeout', 'N/A'),
                    'vlm_url': vlm.get('ollama_url', 'N/A'),
                    'aruco_offset_x': camera.get('aruco_offset_x', 'N/A'),
                    'aruco_offset_y': camera.get('aruco_offset_y', 'N/A'),
                    'aruco_offset_z': camera.get('aruco_offset_z', 'N/A'),
                    'safe_height': robot.get('safe_height', 'N/A'),
                    'grasp_height': robot.get('grasp_height', 'N/A'),
                    'handover_height': robot.get('handover_height', 'N/A'),
                    'gripper_close': robot.get('gripper_close_width', 'N/A'),
                    'gripper_open': robot.get('gripper_open_width', 'N/A'),
                    'velocity_default': robot.get('default_velocity_scaling', 'N/A'),
                    'velocity_slow': robot.get('slow_velocity_scaling', 'N/A'),
                    'velocity_fast': robot.get('fast_velocity_scaling', 'N/A')
                }
            
            self.get_logger().info('Loaded configuration details into status cache')
            
        except Exception as e:
            self.get_logger().error(f'Error loading config to status: {e}')
    
    def handle_web_request(self, msg: String):
        """Handle incoming requests from web dashboard."""
        try:
            request = json.loads(msg.data)
            req_type = request.get('type', 'chat')
            
            if req_type == 'chat':
                # Forward chat message to LLM coordinator
                user_message = request['data']['message']
                self.get_logger().info(f'Web chat: {user_message}')
                
                # Send log to web
                self._send_log_message('Web Handler', 'Request received, forwarding to Coordinator...')
                
                # Start benchmark timer the moment the user prompt is received
                self._bench_start()

                # Publish to coordinator
                command_msg = String()
                command_msg.data = user_message
                self.user_command_pub.publish(command_msg)
                
                # Confirm forwarding
                self._send_log_message('Web Handler', 'Sent to LLM Coordinator')
                
            elif req_type == 'confirmation':
                # Handle motion confirmation response from user
                confirmed = request.get('confirmed', False)
                self.handle_user_confirmation(confirmed)
                
        except Exception as e:
            self.get_logger().error(f'Error handling web request: {e}')
    
    def handle_coordinator_response(self, msg: String):
        """Forward coordinator response to web dashboard."""
        try:
            response_text = msg.data
            
            # Update LLM state as online
            with self.status_lock:
                self.status_cache['llm_state'] = 'Online'
                self._last_seen['llm'] = datetime.now()
            
            # Check if this is system info
            if response_text.startswith('{'):
                try:
                    info = json.loads(response_text)
                    if info.get('type') == 'system_info' and info.get('component') == 'llm':
                        self.llm_model_name = info.get('model', 'LLM')
                        self.system_config['llm'] = info.get('config', {})
                        self.get_logger().info(f'Updated LLM model name: {self.llm_model_name}')
                        return  # Don't forward system info to web
                except (json.JSONDecodeError, ValueError):
                    pass  # Not JSON, continue with normal processing
            
            # Check if this is a log message
            if response_text.startswith('[LOG]'):
                # Extract and forward log message
                log_data = json.loads(response_text[5:])

                # Capture LLM VRAM the instant the routing decision is published —
                # this is *before* the VLM loads, so the LLM is still resident in VRAM.
                agent_name = log_data.get('agent_name', '')
                if '\U0001f4ad LLM' in agent_name or agent_name.startswith('\U0001f4ad LLM'):
                    llm_cfg = self.system_config.get('llm', {})
                    self._bench_llm_mem = self._get_model_vram(
                        llm_cfg.get('ollama_url', 'http://localhost:11434'),
                        llm_cfg.get('model', '')
                    )
                    self.get_logger().debug(
                        f'[BENCH] LLM mem snapshot: {self._bench_llm_mem:.2f} GB'
                    )
                    # Capture per-request inference time sent by llm_coordinator_node
                    self._bench_llm_infer_ms = log_data.get('llm_infer_ms', 0.0)

                self.web_response_pub.publish(
                    String(data=json.dumps(log_data))
                )
                return
            
            # Detect which agent based on prefix
            agent_name = f'🧠 LLM Coordinator ({self.llm_model_name})'
            if response_text.startswith('[VLM]'):
                agent_name = f'🔍 Vision Agent ({self.vlm_model_name})'
                response_text = response_text[5:].strip()
            elif response_text.startswith('[Motion]'):
                agent_name = '⚙️ Motion Controller'
                response_text = response_text[8:].strip()
            
            web_message = {
                'type': 'message',
                'sender': 'robot',
                'agent_name': agent_name,
                'message': response_text,
                'timestamp': datetime.now().isoformat()
            }
            
            self.web_response_pub.publish(
                String(data=json.dumps(web_message))
            )
            
            self.get_logger().info(f'Forwarded coordinator response to web')
            
        except Exception as e:
            self.get_logger().error(f'Error handling coordinator response: {e}')
    
    def handle_vlm_explanation(self, msg: String):
        """Handle VLM explanation/description responses."""
        try:
            explanation = msg.data
            
            # Update vision state as online
            with self.status_lock:
                self.status_cache['vision_state'] = 'Online'
                self._last_seen['vlm'] = datetime.now()            
            # Check if this is system info
            try:
                info = json.loads(explanation)
                if info.get('type') == 'system_info' and info.get('component') == 'vlm':
                    self.vlm_model_name = info.get('model', 'VLM')
                    self.get_logger().info(f'Updated VLM model name: {self.vlm_model_name}')
                    return  # Don't forward system info to web
            except (json.JSONDecodeError, ValueError):
                pass  # Not JSON, continue with normal processing
            
            # Check if this is a hand detection error message - don't attach image
            is_hand_error = "I don't see your hand" in explanation
            
            # Only include image if this is a scene description (not JSON object detection)
            # and NOT a hand detection error
            latest_image = None
            formatted_message = explanation
            
            try:
                # If it parses as JSON, it's likely an object detection result
                detection_data = json.loads(explanation)
                
                # Format the JSON detection data nicely
                if isinstance(detection_data, dict):
                    center = detection_data.get('center', [])
                    description = detection_data.get('description', '')
                    confidence = detection_data.get('confidence', 'unknown')
                    
                    if center and len(center) == 2:
                        formatted_message = (
                            f"**Object detected** — {description}\n\n"
                            f"**Pixel:** ({center[0]}, {center[1]})  "
                            f"**Confidence:** {confidence}"
                        )
                    else:
                        formatted_message = f"**Detection Result**\n\n{description}\n\n**Confidence:** {confidence}"
                
                # Get most recent image (not object-specific to avoid old files)
                # Skip image for hand detection errors
                if not is_hand_error:
                    latest_image = self._get_latest_debug_image(None)
                self._send_log_message(f'Vision Agent ({self.vlm_model_name})', 'Object detection analysis complete')
            except (json.JSONDecodeError, ValueError):
                # It's a scene description - include the scene image
                # Skip image for hand detection errors
                if not is_hand_error:
                    latest_image = self._get_latest_debug_image('scene_description')
                self._send_log_message(f'Vision Agent ({self.vlm_model_name})', 'Scene analysis complete')
            
            web_message = {
                'type': 'message',
                'sender': 'vlm',
                'agent_name': f'Vision Agent ({self.vlm_model_name})',
                'message': formatted_message,
                'timestamp': datetime.now().isoformat()
            }
            
            if latest_image:
                web_message['image'] = latest_image
                self.get_logger().info(f'Image attached: {len(latest_image)} chars')
                
            json_str = json.dumps(web_message)
            self.get_logger().info(f'Publishing message: {len(json_str)} chars total')
                
            self.web_response_pub.publish(
                String(data=json_str)
            )
            
            self.get_logger().info(f'Forwarded VLM explanation to web')
            
        except Exception as e:
            self.get_logger().error(f'Error handling VLM explanation: {e}')
    
    def handle_vlm_grounding(self, msg: String):
        """Handle VLM grounding info (object detection with bbox)."""
        try:
            grounding_data = json.loads(msg.data)
            target = grounding_data.get('target', 'object')
            action = grounding_data.get('action', 'pick')
            bbox = grounding_data.get('bbox', [])
            center = grounding_data.get('center', [])

            # Capture VLM VRAM immediately after VLM finishes its analysis.
            # For skip_vlm actions (go_home, dance) the VLM was never invoked so
            # this will correctly return 0 (or the residual from a prior call).
            vlm_cfg = self.system_config.get('vlm', {})
            self._bench_vlm_mem = self._get_model_vram(
                vlm_cfg.get('ollama_url', 'http://localhost:11434'),
                vlm_cfg.get('model', '')
            )
            self.get_logger().debug(
                f'[BENCH] VLM mem snapshot: {self._bench_vlm_mem:.2f} GB'
            )
            # Capture per-request VLM inference time from grounding message
            self._bench_vlm_infer_ms = grounding_data.get('vlm_infer_ms', 0.0)

            self.get_logger().info(f'VLM grounding: {target} at {center}')
            
            # Store for motion confirmation
            self.pending_motion = {
                'target': target,
                'action': action,
                'bbox': bbox,
                'center': center
            }
            # Reset position so we don't show stale coords from previous detection
            self.latest_robot_position = None
            self.confirmation_pending = True
            
            with self.status_lock:
                self.status_cache['last_detection'] = f'{target} @ {datetime.now().strftime("%H:%M:%S")}'
            
            self._send_log_message('Motion Planner', 'Computing robot-frame position...')
            
            # Wait up to 1.5s for coordinator to publish robot position, then send confirmation
            self.create_timer(1.5, self._send_confirmation_once)
            
        except Exception as e:
            self.get_logger().error(f'Error handling VLM grounding: {e}')

    def _send_confirmation_once(self):
        """Send confirmation if still pending (fallback if position_info never arrived)."""
        if self.confirmation_pending and self.pending_motion:
            self.confirmation_pending = False
            pm = self.pending_motion
            self._request_motion_confirmation(pm['target'], pm['action'])
    
    def _request_motion_confirmation(self, target: str, action: str):
        """Request user confirmation before executing motion."""
        try:
            # Special messages for go_home and dance
            if action == 'go_home':
                confirmation_message = {
                    'type': 'confirmation_request',
                    'sender': 'system',
                    'agent_name': '🏠 Home Position',
                    'message': (
                        f'Ready to execute: **Return to Home Position**\n\n'
                        f'📋 Action plan:\n'
                        f'• Move robot to safe home configuration\n'
                        f'• Reset gripper to default state\n'
                        f'• Prepare for next task'
                    ),
                    'action': action,
                    'target': target,
                    'timestamp': datetime.now().isoformat()
                }
            elif action == 'dance':
                confirmation_message = {
                    'type': 'confirmation_request',
                    'sender': 'system',
                    'agent_name': '💃 Dance Sequence',
                    'message': (
                        f'Ready to execute: **Dance Performance**\n\n'
                        f'📋 Action plan:\n'
                        f'• Execute creative motion sequence\n'
                        f'• 7 coordinated movements\n'
                        f'• Duration: ~20 seconds\n'
                        f'• Returns to safe position when complete'
                    ),
                    'action': action,
                    'target': target,
                    'timestamp': datetime.now().isoformat()
                }
            else:
                # Standard position-based confirmation
                rp = self.latest_robot_position
                if rp and rp.get('x') is not None and rp.get('y') is not None and rp.get('z') is not None:
                    position_line = (
                        f"\n• Position: X={rp['x']:+.3f} m, Y={rp['y']:+.3f} m, Z={rp['z']:+.3f} m"
                    )
                else:
                    position_line = ''
                
                confirmation_message = {
                    'type': 'confirmation_request',
                    'sender': 'system',
                    'agent_name': '⚙️ Motion Controller',
                    'message': (
                        f'Ready to execute: **{action} {target}**\n\n'
                        f'📋 Action plan:\n'
                        f'• Approach object at detected location{position_line}\n'
                        f'• Execute {action} maneuver\n'
                        f'• Return to safe position'
                    ),
                    'action': action,
                    'target': target,
                    'timestamp': datetime.now().isoformat()
                }
            
            self.web_response_pub.publish(
                String(data=json.dumps(confirmation_message))
            )

            # Record end of perception-and-planning cycle and log benchmark results
            self._bench_finish(action, target)

            self.get_logger().info(f'Requested motion confirmation for: {action} {target}')
            
        except Exception as e:
            self.get_logger().error(f'Error requesting confirmation: {e}')
    
    def handle_target_position_info(self, msg: String):
        """Cache robot-frame position; if confirmation is still pending, send it now with coords."""
        try:
            rp = json.loads(msg.data)
            
            # Special handling for go_home and dance - no position info needed
            if rp.get('skip_vlm', False):
                self.get_logger().info(f'Handling {rp.get("action")} confirmation (no position)')
                # Don't cache this position since it has None values
                if self.confirmation_pending and self.pending_motion:
                    self.confirmation_pending = False
                    pm = self.pending_motion
                    self._request_motion_confirmation(pm['target'], pm['action'])
                return
            
            # Cache position for normal actions
            self.latest_robot_position = rp
            
            self.get_logger().info(
                f'Robot position cached: '
                f'X={rp["x"]:+.3f} Y={rp["y"]:+.3f} Z={rp["z"]:+.3f}'
            )
            # Send robot-frame coords as a chat log — timing-independent
            pos_message = {
                'type': 'log',
                'sender': 'system',
                'agent_name': '\U0001f4cd Robot Position',
                'message': (
                    f"**{rp['target']} \u2192 Robot Base Frame (fr3_link0):**\n"
                    f"\u2022 X: {rp['x']:+.3f} m  ({'forward' if rp['x'] > 0 else 'backward'})\n"
                    f"\u2022 Y: {rp['y']:+.3f} m  ({'left' if rp['y'] > 0 else 'right'})\n"
                    f"\u2022 Z: {rp['z']:+.3f} m  (height)"
                ),
                'timestamp': datetime.now().isoformat()
            }
            self.web_response_pub.publish(String(data=json.dumps(pos_message)))
            
            # If confirmation is still waiting, send it now with position included
            if self.confirmation_pending and self.pending_motion:
                self.confirmation_pending = False
                pm = self.pending_motion
                self._request_motion_confirmation(pm['target'], pm['action'])
        except Exception as e:
            self.get_logger().error(f'Error caching robot position: {e}')

    # ------------------------------------------------------------------
    # Benchmark helpers
    # ------------------------------------------------------------------

    def _bench_start(self):
        """Record the wall-clock start of a perception-and-planning cycle."""
        self._bench_t_start = time.monotonic()
        self._bench_llm_mem = 0.0
        self._bench_vlm_mem = 0.0
        self._bench_llm_infer_ms = 0.0
        self._bench_vlm_infer_ms = 0.0

    def _bench_finish(self, action: str, target: str):
        """Compute latency, report per-request inference times and fixed VRAM footprints."""
        elapsed = time.monotonic() - self._bench_t_start

        llm_mem = self._bench_llm_mem
        vlm_mem = self._bench_vlm_mem
        # Convert ms → s for display; these vary per request (reflect prompt/image complexity)
        llm_infer_s = self._bench_llm_infer_ms / 1000.0
        vlm_infer_s = self._bench_vlm_infer_ms / 1000.0

        # Full structured log for paper data collection — grep [BENCHMARK] in ROS logs
        self.get_logger().info(
            f'[BENCHMARK] action={action} target={target} '
            f'latency={elapsed:.2f}s '
            f'llm_infer={llm_infer_s:.2f}s vlm_infer={vlm_infer_s:.2f}s '
            f'llm_mem={llm_mem:.2f}GB vlm_mem={vlm_mem:.2f}GB'
        )

        # Web display — inference times vary per request; VRAM is a fixed system spec
        llm_infer_str = f'**{llm_infer_s:.2f} s**' if llm_infer_s > 0 else '**N/A**'
        vlm_infer_str = f'**{vlm_infer_s:.2f} s**' if vlm_infer_s > 0 else '**N/A**'
        llm_mem_str = f'{llm_mem:.2f} GB' if llm_mem > 0 else 'N/A'
        vlm_mem_str = f'{vlm_mem:.2f} GB' if vlm_mem > 0 else 'N/A'

        self._send_log_message(
            '\U0001f4ca Benchmark',
            f'Latency: **{elapsed:.2f} s** | LLM infer: {llm_infer_str} | VLM infer: {vlm_infer_str}\n'
            f'RAM \u2192 LLM: {llm_mem_str} | VLM: {vlm_mem_str}'
        )

    def _query_model_memory(self) -> tuple:
        """Return (llm_vram_gb, vlm_vram_gb) by querying each Ollama /api/ps endpoint."""
        llm_cfg = self.system_config.get('llm', {})
        vlm_cfg = self.system_config.get('vlm', {})

        llm_mem = self._get_model_vram(
            llm_cfg.get('ollama_url', 'http://localhost:11434'),
            llm_cfg.get('model', '')
        )
        vlm_mem = self._get_model_vram(
            vlm_cfg.get('ollama_url', 'http://localhost:11434'),
            vlm_cfg.get('model', '')
        )
        return llm_mem, vlm_mem

    def _get_model_vram(self, ollama_url: str, model_name: str) -> float:
        """Return total memory used by *model_name* in GB, via Ollama /api/ps.

        Uses 'size' (CPU+GPU combined) rather than 'size_vram' (GPU-only).
        size_vram fluctuates when Ollama dynamically shifts layers between CPU and GPU
        for models too large to fit entirely on GPU.  The total 'size' is stable.
        Returns 0 on failure.
        """
        try:
            resp = requests.get(f'{ollama_url}/api/ps', timeout=5)
            if resp.status_code == 200:
                prefix = model_name.split(':')[0].lower()
                for m in resp.json().get('models', []):
                    if m.get('name', '').lower().startswith(prefix):
                        return m.get('size', 0) / (1024 ** 3)
        except Exception as exc:
            self.get_logger().debug(f'Memory query failed for {model_name}: {exc}')
        return 0.0

    # ------------------------------------------------------------------

    def _send_log_message(self, agent_name: str, message: str):
        """Send a log message to the chat."""
        try:
            web_message = {
                'type': 'log',
                'sender': 'system',
                'agent_name': agent_name,
                'message': message,
                'timestamp': datetime.now().isoformat()
            }
            
            self.web_response_pub.publish(
                String(data=json.dumps(web_message))
            )
        except Exception as e:
            self.get_logger().error(f'Error sending log message: {e}')
    
    def handle_user_confirmation(self, confirmed: bool):
        """Handle user confirmation response."""
        try:
            if not self.pending_motion:
                self.get_logger().warn('No pending motion to confirm')
                return
            
            # Forward user confirmation to coordinator
            confirmation_msg = {
                'confirmed': confirmed,
                'motion': self.pending_motion,
                'timestamp': datetime.now().isoformat()
            }
            
            self.user_confirmation_pub.publish(
                String(data=json.dumps(confirmation_msg))
            )
            
            self.get_logger().info(f'User {"approved" if confirmed else "cancelled"} motion')
            
            # Send feedback to web
            if confirmed:
                with self.status_lock:
                    self.status_cache['last_action'] = (
                        f'{self.pending_motion.get("action","?")} {self.pending_motion.get("target","?")}'
                    )
                web_message = {
                    'type': 'message',
                    'sender': 'system',
                    'agent_name': 'User Approval',
                    'message': f'Motion approved. Executing {self.pending_motion["action"]} operation...',
                    'timestamp': datetime.now().isoformat()
                }
            else:
                web_message = {
                    'type': 'message',
                    'sender': 'system',
                    'agent_name': 'User Cancelled',
                    'message': 'Motion execution cancelled.',
                    'timestamp': datetime.now().isoformat()
                }
            
            self.web_response_pub.publish(
                String(data=json.dumps(web_message))
            )
            
            self.get_logger().info(f'Motion {"approved" if confirmed else "cancelled"}')
            
            # Clear pending motion
            if not confirmed:
                self.pending_motion = None
            
        except Exception as e:
            self.get_logger().error(f'Error handling confirmation: {e}')
    
    def _get_latest_debug_image(self, object_name: str = None) -> str:
        """Get the latest debug image as base64 data URL."""
        try:
            if not self.debug_images_dir.exists():
                return None
            image_files = list(self.debug_images_dir.glob('*.jpg'))
            if not image_files:
                return None
            latest_file = None
            # If object_name specified, try to find the most recent matching image
            if object_name:
                normalized_name = object_name.lower().replace(' ', '_')
                # Find all files containing the normalized name
                matching_files = [f for f in image_files if normalized_name in f.name.lower()]
                if matching_files:
                    # Pick the most recent matching file
                    latest_file = max(matching_files, key=lambda f: f.stat().st_mtime)
            # If no match or no object_name, and specifically for scene_description, try to get the most recent scene_description image
            if object_name == 'scene_description' and (not latest_file):
                scene_files = [f for f in image_files if 'scene_description' in f.name.lower()]
                if scene_files:
                    latest_file = max(scene_files, key=lambda f: f.stat().st_mtime)
            # Fallback: just get the most recent image
            if not latest_file:
                latest_file = max(image_files, key=lambda f: f.stat().st_mtime)
            # Read and encode as base64 (resize for web to keep message small)
            with open(latest_file, 'rb') as f:
                image_data = f.read()
                if not image_data:
                    self.get_logger().error(f'Empty image file: {latest_file.name}')
                    return None
                # Resize to max 640px wide to avoid ROSBridge message size limits
                import numpy as np
                import cv2 as _cv2
                nparr = np.frombuffer(image_data, np.uint8)
                img = _cv2.imdecode(nparr, _cv2.IMREAD_COLOR)
                if img is not None:
                    h, w = img.shape[:2]
                    max_w = 640
                    if w > max_w:
                        scale = max_w / w
                        img = _cv2.resize(img, (max_w, int(h * scale)), interpolation=_cv2.INTER_AREA)
                    _, buf = _cv2.imencode('.jpg', img, [_cv2.IMWRITE_JPEG_QUALITY, 80])
                    image_data = buf.tobytes()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                data_url = f'data:image/jpeg;base64,{image_base64}'
                self.get_logger().info(
                    f'Image encoding complete:\n'
                    f'  File: {latest_file.name}\n'
                    f'  Base64 length: {len(image_base64)}\n'
                    f'  Data URL length: {len(data_url)}'
                )
                return data_url
            
        except Exception as e:
            self.get_logger().error(f'Error loading debug image: {e}')
            return None
    
    def handle_coordinator_status(self, msg: String):
        """Handle status updates from coordinator."""
        try:
            status = json.loads(msg.data)
            now = datetime.now()

            with self.status_lock:
                self.status_cache['robot_state'] = status.get('robot_state', 'Unknown').title()
                self.status_cache['coordinator_state'] = 'Online'
                self.status_cache['bridge_state'] = 'Online'
                self.status_cache['timestamp'] = status.get('timestamp', now.isoformat())
                self._last_seen['coordinator'] = now

                # Propagate llm/vision state from coordinator — and keep staleness
                # tracking in sync so the staleness check doesn't immediately wipe them
                raw_llm = status.get('llm_state', 'offline').lower()
                raw_vis = status.get('vision_state', 'offline').lower()

                if raw_llm == 'online':
                    self.status_cache['llm_state'] = 'Online'
                    self._last_seen['llm'] = now
                elif self.status_cache.get('llm_state') != 'Online':
                    # Only overwrite if not already shown as online by handle_coordinator_response
                    self.status_cache['llm_state'] = raw_llm.title()

                if raw_vis == 'online':
                    self.status_cache['vision_state'] = 'Online'
                    self._last_seen['vlm'] = now
                elif self.status_cache.get('vision_state') != 'Online':
                    self.status_cache['vision_state'] = raw_vis.title()

            self.get_logger().debug(f'Status updated: {self.status_cache}')

        except Exception as e:
            self.get_logger().error(f'Error handling coordinator status: {e}')
    
    def handle_llm_response(self, msg: String):
        """Forward LLM response to web dashboard (legacy, now using coordinator_response)."""
        try:
            response = json.loads(msg.data)
            
            web_message = {
                'type': 'message',
                'sender': 'robot',
                'message': response.get('response', 'Task processing...'),
                'timestamp': datetime.now().isoformat()
            }
            
            self.web_response_pub.publish(
                String(data=json.dumps(web_message))
            )
            
            self.get_logger().info(f'Forwarded LLM response to web')
            
        except Exception as e:
            self.get_logger().error(f'Error handling LLM response: {e}')
    
    def handle_motion_status(self, msg: String):
        """Forward motion status to web dashboard and update status cache."""
        try:
            status = json.loads(msg.data)
            status_text = status.get('status', 'Unknown')

            # Map ROS status strings to display labels
            display_map = {
                'completed':  'Completed',
                'failed':     'Failed',
                'executing':  'Executing',
                'planning':   'Planning',
                'approaching':'Approaching',
                'idle':       'Idle',
            }
            display_state = display_map.get(status_text.lower(), status_text.title())

            # Update status panel
            with self.status_lock:
                self.status_cache['motion_state'] = display_state
                self._last_seen['motion'] = datetime.now()
                if status_text == 'completed':
                    self.status_cache['last_action'] = f'Completed at {datetime.now().strftime("%H:%M:%S")}'

            if status_text == 'completed':
                message = '✓ Motion sequence completed successfully'
                msg_type = 'message'
                self.pending_motion = None
            elif status_text == 'failed':
                message = f'✗ Motion failed: {status.get("error", "Unknown error")}'
                msg_type = 'message'
                self.pending_motion = None
            elif status_text == 'executing':
                message = 'Executing motion sequence...'
                msg_type = 'log'
            elif status_text == 'planning':
                message = 'Planning trajectory...'
                msg_type = 'log'
            elif status_text == 'approaching':
                message = 'Moving to approach position...'
                msg_type = 'log'
            else:
                message = f'Status: {status_text}'
                msg_type = 'log'

            web_message = {
                'type': msg_type,
                'sender': 'system',
                'agent_name': '⚙️ Motion Executor',
                'message': message,
                'timestamp': datetime.now().isoformat()
            }

            self.web_response_pub.publish(
                String(data=json.dumps(web_message))
            )

        except Exception as e:
            self.get_logger().error(f'Error handling motion status: {e}')
    
    def handle_vision_data(self, msg: String):
        """Handle vision detection data."""
        try:
            detections = json.loads(msg.data)
            with self.status_lock:
                self.status_cache['vision_state'] = 'Online'
        except Exception as e:
            self.get_logger().error(f'Error handling vision data: {e}')

    def handle_camera_info(self, msg: CameraInfo):
        """Track camera as online when CameraInfo messages arrive."""
        with self.status_lock:
            self.status_cache['camera_state'] = 'Online'
            self._last_seen['camera'] = datetime.now()
    
    def publish_web_status(self):
        """Publish status updates to web, with node-graph and staleness detection."""
        now = datetime.now()
        stale_threshold = 15  # seconds

        # ---- Node-graph check (every 5 timer ticks = 5s) -----------------
        self._node_check_counter += 1
        if self._node_check_counter >= 5:
            self._node_check_counter = 0
            try:
                node_names = [n for n, ns in self.get_node_names_and_namespaces()]
                with self.status_lock:
                    # Coordinator
                    if 'franka_coordinator' in node_names:
                        self.status_cache['coordinator_state'] = 'Online'
                        self._last_seen['coordinator'] = now
                    # VLM / Vision
                    if 'vlm_node' in node_names:
                        self.status_cache['vision_state'] = 'Online'
                        self._last_seen['vlm'] = now
                    # LLM
                    if 'llm_coordinator' in node_names or 'llm_node' in node_names:
                        self.status_cache['llm_state'] = 'Online'
                        self._last_seen['llm'] = now
                    # Motion executor
                    if 'motion_executor' in node_names:
                        # Only mark node-level presence; motion_state text comes from /motion/status
                        self._last_seen['motion'] = now
            except Exception as e:
                self.get_logger().debug(f'Node graph check failed: {e}')

        with self.status_lock:
            # Staleness: mark offline if no recent activity AND no node detected
            for component, key in [
                ('llm',         'llm_state'),
                ('vlm',         'vision_state'),
                ('coordinator', 'coordinator_state'),
                ('camera',      'camera_state'),
            ]:
                last = self._last_seen.get(component)
                if last is None or (now - last).total_seconds() > stale_threshold:
                    if self.status_cache.get(key) == 'Online':
                        self.status_cache[key] = 'Offline'

            last_motion = self._last_seen.get('motion')
            if not last_motion or (now - last_motion).total_seconds() > stale_threshold:
                if self.status_cache.get('motion_state') not in ('Idle', 'Completed', 'Failed'):
                    self.status_cache['motion_state'] = 'Idle'

            status_to_send = dict(self.status_cache)

        self.web_status_pub.publish(
            String(data=json.dumps(status_to_send))
        )
        
        # Debug log once to confirm config is being sent
        if not hasattr(self, '_logged_config_send'):
            self._logged_config_send = True
            if 'config' in status_to_send:
                self.get_logger().info(f'Status includes config: {list(status_to_send["config"].keys())}')
    
    def process_web_input(self, user_input: str):
        """
        Process input from web and send to coordinator.
        This method would be called by a web interface adapter.
        DEPRECATED: Now handled by handle_web_request
        """
        request = {
            'type': 'chat',
            'data': {
                'message': user_input,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        self.user_command_pub.publish(
            String(data=request['data']['message'])
        )


def main(args=None):
    rclpy.init(args=args)
    web_handler = WebHandler()
    
    try:
        rclpy.spin(web_handler)
    except KeyboardInterrupt:
        pass
    finally:
        web_handler.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
