#!/usr/bin/env python3
"""
Coordinator Node - Main orchestrator for the Franka LLM pipeline
Handles:
- Web requests from the dashboard
- Routing between LLM, VLM, Vision Detection, and Motion Executor
- Status monitoring and reporting
- Request/response flow management
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from std_msgs.msg import String, Bool
from geometry_msgs.msg import PoseStamped, Point
from sensor_msgs.msg import Image, CameraInfo
import json
from datetime import datetime
from enum import Enum
import numpy as np
from cv_bridge import CvBridge
from pathlib import Path
import yaml
from .aruco_coordinate_transformer import ArucoCoordinateTransformer

# Message types (we'll use std_msgs.String with JSON for now)
class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FrankaCoordinator(Node):
    """Main coordinator node that orchestrates the robot pipeline."""
    
    def __init__(self):
        super().__init__('franka_coordinator')
        
        # Load configuration
        self.config = self._load_config()
        
        # Status tracking
        self.robot_status = "disconnected"
        self.vision_status = "offline"
        self.llm_status = "online"   # LLM coordinator is available whenever this node starts
        self.current_task = None
        self.task_status = TaskStatus.PENDING.value
        
        # Depth resolution data
        self.latest_depth_image = None
        self.camera_intrinsics = None
        self.bridge = CvBridge()
        
        # Stored for confirmation flow
        self.last_target_position = None
        self.last_target_name = None
        self.last_action = None
        
        # Coordinate transformer (pixel → robot frame) - ArUco-based
        workspace_root = Path(self.config['paths']['workspace_root']).expanduser()
        calibration_dir = workspace_root / self.config['paths']['calibration_dir']
        self.transformer = ArucoCoordinateTransformer(
            node=self,
            calibration_dir=str(calibration_dir),
            robot_offset_x=self.config['camera']['aruco_offset_x'],
            robot_offset_y=self.config['camera']['aruco_offset_y'],
            robot_offset_z=self.config['camera']['aruco_offset_z']
        )
        
        # Publisher for outgoing commands
        self.llm_request_pub = self.create_publisher(
            String, '/llm/request', 10
        )
        self.motion_command_pub = self.create_publisher(
            String, '/motion/command', 10
        )
        self.vlm_request_pub = self.create_publisher(
            String, '/vlm_request', 10  # Updated topic name
        )
        
        # Status publishers
        self.status_pub = self.create_publisher(
            String, '/coordinator/status', 10
        )
        
        # Publisher for 3D target position
        self.target_position_pub = self.create_publisher(
            PoseStamped, '/target_position', 10
        )

        # Publisher for robot-frame position info (String JSON for web display)
        self.target_position_info_pub = self.create_publisher(
            String, '/target_position_info', 10
        )
        
        # Subscriber for web dashboard requests
        self.web_request_sub = self.create_subscription(
            String, '/web/request', self.handle_web_request, 10
        )
        
        # Subscribers for pipeline responses
        self.llm_response_sub = self.create_subscription(
            String, '/llm/response', self.handle_llm_response, 10
        )
        self.vision_response_sub = self.create_subscription(
            String, '/vision/detections', self.handle_vision_response, 10
        )
        self.vlm_response_sub = self.create_subscription(
            String, '/vlm/analysis', self.handle_vlm_response, 10
        )
        self.vlm_grounding_sub = self.create_subscription(
            String, '/vlm_grounding', self.handle_vlm_grounding, 10
        )
        self.motion_status_sub = self.create_subscription(
            String, '/motion/status', self.handle_motion_status, 10
        )
        
        # Subscriber for user confirmation from web
        self.user_confirmation_sub = self.create_subscription(
            String, '/user_confirmation', self.handle_user_confirmation, 10
        )
        
        # Subscriber for robot state
        self.robot_state_sub = self.create_subscription(
            String, '/robot/state', self.handle_robot_state, 10
        )
        
        # QoS profile for RealSense camera (uses BEST_EFFORT reliability)
        camera_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10
        )
        
        # Subscribers for depth image and camera info
        self.depth_sub = self.create_subscription(
            Image,
            '/cameras/ee/ee_camera/aligned_depth_to_color/image_raw',
            self.depth_callback,
            camera_qos
        )
        self.camera_info_sub = self.create_subscription(
            CameraInfo,
            '/cameras/ee/ee_camera/color/camera_info',
            self.camera_info_callback,
            camera_qos
        )
        
        # Timer for periodic status checks
        self.status_timer = self.create_timer(0.5, self.publish_status)
        
        self.get_logger().info('Franka Coordinator initialized')
        self.publish_status()
    
    def _load_config(self) -> dict:
        """Load configuration from config.yaml"""
        config_path = self._find_config_file()
        self.get_logger().info(f'Loading config from: {config_path}')
        
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
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
    
    def handle_web_request(self, msg: String):
        """
        Handle incoming requests from the web dashboard.
        
        Expected message format:
        {
            "type": "chat" | "command" | "status",
            "data": {
                "message": "user input",
                ...
            }
        }
        """
        try:
            request = json.loads(msg.data)
            request_type = request.get('type', 'chat')
            data = request.get('data', {})
            
            self.get_logger().info(f'Web request: {request_type} - {data.get("message", "")}')
            
            if request_type == 'chat':
                # User asked something - send to LLM
                self.process_chat(data.get('message', ''))
            elif request_type == 'command':
                # Direct command - send to motion executor
                self.process_command(data.get('command', ''))
            elif request_type == 'clear':
                # Clear history - just log
                self.get_logger().info('Chat history cleared by user')
            
        except json.JSONDecodeError:
            self.get_logger().error(f'Invalid JSON in web request: {msg.data}')
        except Exception as e:
            self.get_logger().error(f'Error handling web request: {e}')
    
    def process_chat(self, message: str):
        """Send chat message to LLM for processing."""
        if not message.strip():
            return
        
        self.current_task = message
        self.task_status = TaskStatus.PROCESSING.value
        
        # Create LLM request
        llm_request = {
            'timestamp': datetime.now().isoformat(),
            'message': message,
            'task_id': hash(message + datetime.now().isoformat()) % 10000
        }
        
        # Publish to LLM
        self.llm_request_pub.publish(
            String(data=json.dumps(llm_request))
        )
        
        self.get_logger().info(f'LLM request sent: {message}')
    
    def process_command(self, command: str):
        """Send command directly to motion executor."""
        self.current_task = command
        self.task_status = TaskStatus.PROCESSING.value
        
        motion_cmd = {
            'timestamp': datetime.now().isoformat(),
            'command': command,
            'task_id': hash(command + datetime.now().isoformat()) % 10000
        }
        
        self.motion_command_pub.publish(
            String(data=json.dumps(motion_cmd))
        )
        
        self.get_logger().info(f'Motion command sent: {command}')
    
    def handle_llm_response(self, msg: String):
        """Handle response from LLM node."""
        try:
            response = json.loads(msg.data)
            self.llm_status = "online"
            self.get_logger().info(f'LLM response: {response.get("response", "")}')
            
            # If LLM returns a command, send it to motion executor
            if 'command' in response:
                self.process_command(response['command'])
            
            # Publish response back to web
            web_response = {
                'type': 'llm_response',
                'sender': 'robot',
                'message': response.get('response', ''),
                'timestamp': datetime.now().isoformat()
            }
            
            self.motion_command_pub.publish(
                String(data=json.dumps(web_response))
            )
            
        except Exception as e:
            self.get_logger().error(f'Error handling LLM response: {e}')
    
    def handle_vision_response(self, msg: String):
        """Handle vision detection results."""
        try:
            detections = json.loads(msg.data)
            self.vision_status = "online"
            self.get_logger().debug(f'Vision detections: {len(detections)} objects')
        except Exception as e:
            self.get_logger().error(f'Error handling vision response: {e}')
    
    def handle_vlm_response(self, msg: String):
        """Handle VLM analysis results."""
        try:
            analysis = json.loads(msg.data)
            self.get_logger().info(f'VLM analysis: {analysis.get("result", "")}')
        except Exception as e:
            self.get_logger().error(f'Error handling VLM response: {e}')
    
    def handle_motion_status(self, msg: String):
        """Handle motion executor status updates."""
        try:
            status = json.loads(msg.data)
            motion_status = status.get('status', 'unknown')
            
            if motion_status == 'completed':
                self.task_status = TaskStatus.COMPLETED.value
                self.get_logger().info('Task completed successfully')
            elif motion_status == 'failed':
                self.task_status = TaskStatus.FAILED.value
                self.get_logger().error('Task failed')
            elif motion_status == 'executing':
                self.task_status = TaskStatus.PROCESSING.value
            
        except Exception as e:
            self.get_logger().error(f'Error handling motion status: {e}')
    
    def handle_robot_state(self, msg: String):
        """Handle robot state updates."""
        try:
            state = json.loads(msg.data)
            self.robot_status = "connected" if state.get('connected', False) else "disconnected"
        except Exception as e:
            self.robot_status = "disconnected"
    
    def depth_callback(self, msg: Image):
        """Store latest depth image for 3D position resolution"""
        try:
            self.latest_depth_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            # Depth is in mm for RealSense, convert to meters
            if self.latest_depth_image.dtype == np.uint16:
                self.latest_depth_image = self.latest_depth_image.astype(np.float32) / 1000.0
        except Exception as e:
            self.get_logger().error(f'Error converting depth image: {e}')
    
    def camera_info_callback(self, msg: CameraInfo):
        """Store camera intrinsics for deprojection"""
        if self.camera_intrinsics is None:
            self.camera_intrinsics = {
                'fx': msg.k[0],
                'fy': msg.k[4],
                'ppx': msg.k[2],
                'ppy': msg.k[5],
                'width': msg.width,
                'height': msg.height
            }
            self.get_logger().info(f'Camera intrinsics loaded: {self.camera_intrinsics}')
            
            # Also update the transformer
            self.transformer.update_camera_intrinsics(msg)
    
    def handle_vlm_grounding(self, msg: String):
        """
        Handle VLM grounding results (center + target).
        Converts pixel center + depth → 3D robot coordinates.
        Publishes result for motion executor.
        """
        try:
            grounding = json.loads(msg.data)
            target = grounding.get('target', '')
            center = grounding.get('center', None)  # Use center directly from VLM
            action = grounding.get('action', 'locate')  # pick, place, locate
            
            if not center or self.latest_depth_image is None or self.camera_intrinsics is None:
                self.get_logger().warn(
                    f'⚠️  Cannot resolve 3D position for "{target}": '
                    f'center={center is not None}, depth={self.latest_depth_image is not None}, '
                    f'intrinsics={self.camera_intrinsics is not None}'
                )
                return
            
            self.get_logger().info(f'🎯 Processing VLM detection: {target}')
            self.get_logger().info(f'   Center pixel: {center}')
            self.get_logger().info(f'   Action: {action}')
            
            # Convert pixel + depth → robot frame using ArUco calibration
            position_robot = self._convert_pixel_to_robot_frame(center, target)
            
            if position_robot is None:
                self.get_logger().error(f'❌ Failed to compute 3D position for "{target}"')
                return
            
            # Apply offset based on placement type for place actions
            if action == 'place':
                import numpy as np
                
                # Get placement parameters from grounding message
                placement_type = grounding.get('placement_type', 'direct')
                direction = grounding.get('direction', None)
                
                if placement_type == 'offset' and direction:
                    # Apply offset in specified direction
                    offset_distance = self.config['robot']['offset_placement_distance']
                    
                    if direction == 'left':
                        # Left in robot frame is +Y
                        offset = np.array([0.0, offset_distance, 0.0])
                    elif direction == 'right':
                        # Right in robot frame is -Y
                        offset = np.array([0.0, -offset_distance, 0.0])
                    elif direction == 'top':
                        # Top/above in camera view is +X in robot frame (away from robot)
                        offset = np.array([offset_distance, 0.0, 0.0])
                    elif direction == 'bottom':
                        # Bottom/below in camera view is -X in robot frame (toward robot/camera)
                        offset = np.array([-offset_distance, 0.0, 0.0])
                    else:
                        offset = np.array([0.0, 0.0, 0.0])
                    
                    position_robot = position_robot + offset
                    self.get_logger().info(
                        f'   ⚡ OFFSET PLACEMENT: Applied 8cm offset in "{direction}" direction\n'
                        f'   Final position: X={position_robot[0]:+.4f}m, Y={position_robot[1]:+.4f}m, Z={position_robot[2]:+.4f}m'
                    )
                    
                elif placement_type == 'stack':
                    # Stacking: use detected Z (table+object height) and add object-being-placed height
                    # Z already includes the target object's height from depth camera
                    held_object_height = self.config['robot']['held_object_height']
                    clearance = self.config['robot']['placement_clearance']
                    offset = np.array([0.0, 0.0, held_object_height + clearance])
                    position_robot = position_robot + offset
                    self.get_logger().info(
                        f'   📚 STACKING: Target height Z={position_robot[2]-offset[2]:.3f}m + object height {held_object_height*1000:.0f}mm + clearance {clearance*1000:.0f}mm\n'
                        f'   Final position: X={position_robot[0]:+.4f}m, Y={position_robot[1]:+.4f}m, Z={position_robot[2]:+.4f}m'
                    )
                    
                else:  # placement_type == 'direct' or no type specified
                    # Direct placement: use exact detected position
                    self.get_logger().info(
                        f'   🎯 DIRECT PLACEMENT: Using exact detected position\n'
                        f'   Final position: X={position_robot[0]:+.4f}m, Y={position_robot[1]:+.4f}m, Z={position_robot[2]:+.4f}m'
                    )
            
            # HANDOVER: Override Z to fixed handover height
            elif action == 'handover':
                import numpy as np
                handover_height = self.config['robot']['handover_height']
                position_robot[2] = handover_height
                self.get_logger().info(
                    f'   🤝 HANDOVER: Using detected hand XY with fixed Z={handover_height}m\n'
                    f'   Final position: X={position_robot[0]:+.4f}m, Y={position_robot[1]:+.4f}m, Z={position_robot[2]:+.4f}m'
                )
            
            # Store position for republishing on user confirmation
            self.last_target_position = position_robot
            self.last_target_name = target
            self.last_action = action
            
            # Publish target position for motion executor preview
            self._publish_target_position(position_robot, target, action)

            # Publish robot-frame coords as JSON for web_handler display
            pos_info = {
                'target': target,
                'x': float(position_robot[0]),
                'y': float(position_robot[1]),
                'z': float(position_robot[2]),
            }
            self.target_position_info_pub.publish(
                String(data=json.dumps(pos_info))
            )
                
        except Exception as e:
            self.get_logger().error(f'Error handling VLM grounding: {e}')
    
    def _convert_pixel_to_robot_frame(self, center, target_name: str):
        """
        Convert center pixel to 3D coordinates in robot base frame.
        
        Args:
            center: [x, y] pixel coordinates (center of object from VLM)
            target_name: Object name for logging
            
        Returns:
            numpy array [x, y, z] in robot frame, or None if failed
        """
        pixel_u, pixel_v = center[0], center[1]
        
        # Get depth at center pixel (use small region for robustness)
        height, width = self.latest_depth_image.shape
        pixel_v = max(0, min(pixel_v, height - 1))
        pixel_u = max(0, min(pixel_u, width - 1))
        
        # Extract depth from small region around center (5x5)
        y1 = max(0, pixel_v - 2)
        y2 = min(height, pixel_v + 3)
        x1 = max(0, pixel_u - 2)
        x2 = min(width, pixel_u + 3)
        
        roi = self.latest_depth_image[y1:y2, x1:x2]
        valid_depths = roi[roi > 0]
        
        if len(valid_depths) == 0:
            self.get_logger().warn(f'No valid depth at pixel ({pixel_u}, {pixel_v})')
            return None
        
        # Use median depth for robustness
        import numpy as np
        depth_m = float(np.median(valid_depths))
        
        self.get_logger().info(
            f'   Pixel ({pixel_u}, {pixel_v}) → Depth: {depth_m:.3f}m (median of {len(valid_depths)} points)'
        )
        
        # Convert to robot frame using transformer
        position_robot = self.transformer.pixel_to_robot_frame(
            pixel_u=pixel_u,
            pixel_v=pixel_v,
            depth_m=depth_m
        )
        
        if position_robot is not None:
            self.get_logger().info(
                f'✅ "{target_name}" located in ROBOT FRAME:\n'
                f'   X = {position_robot[0]:+.4f} m  ({"forward" if position_robot[0] > 0 else "backward"})\n'
                f'   Y = {position_robot[1]:+.4f} m  ({"left" if position_robot[1] > 0 else "right"})\n'
                f'   Z = {position_robot[2]:+.4f} m  (height from base)'
            )
        
        return position_robot
    
    def _convert_bbox_to_robot_frame(self, bbox, target_name: str):
        """
        Convert bounding box to 3D coordinates in robot base frame.
        (Legacy method - kept for compatibility)
        
        Args:
            bbox: [x1, y1, x2, y2] pixel coordinates
            target_name: Object name for logging
            
        Returns:
            numpy array [x, y, z] in robot frame, or None if failed
        """
        position_robot = self.transformer.bbox_to_robot_frame(
            bbox=bbox,
            depth_image=self.latest_depth_image,
            method='median'  # Robust depth estimation
        )
        
        if position_robot is not None:
            self.get_logger().info(
                f'✅ "{target_name}" located in ROBOT FRAME:\n'
                f'   X = {position_robot[0]:+.4f} m  ({"forward" if position_robot[0] > 0 else "backward"})\n'
                f'   Y = {position_robot[1]:+.4f} m  ({"left" if position_robot[1] > 0 else "right"})\n'
                f'   Z = {position_robot[2]:+.4f} m  (height from base)'
            )
        
        return position_robot
    
    def _publish_target_position(self, position, target_name: str, action: str = 'locate'):
        """
        Publish target position for motion executor.
        
        Args:
            position: numpy array [x, y, z] in robot frame
            target_name: Object name
            action: Action type (pick, place, locate)
        """
        pose_msg = PoseStamped()
        pose_msg.header.stamp = self.get_clock().now().to_msg()
        pose_msg.header.frame_id = 'fr3_link0'  # FR3 robot base frame
        pose_msg.pose.position.x = float(position[0])
        pose_msg.pose.position.y = float(position[1])
        pose_msg.pose.position.z = float(position[2])
        
        # Default orientation (gripper pointing down)
        pose_msg.pose.orientation.w = 1.0
        pose_msg.pose.orientation.x = 0.0
        pose_msg.pose.orientation.y = 0.0
        pose_msg.pose.orientation.z = 0.0
        
        self.target_position_pub.publish(pose_msg)
        
        self.get_logger().info(
            f'📤 Published target position for "{target_name}" (action: {action})'
        )
    
    def _send_motion_command(self, action: str, target_name: str):
        """
        Send motion command to motion executor.
        
        Args:
            action: 'pick' or 'place'
            target_name: Object/location name
        """
        command = {
            'action': action,
            'parameters': {
                'object' if action == 'pick' else 'location': target_name
            }
        }
        
        msg = String()
        msg.data = json.dumps(command)
        self.motion_command_pub.publish(msg)
        
        self.get_logger().info(
            f'📤 Sent motion command: {action} "{target_name}"'
        )
    
    def resolve_3d_position(self, bbox, depth_image, camera_intrinsics):
        """
        Convert VLM bounding box to 3D coordinates in ROBOT BASE FRAME.
        Uses TF2 for proper camera-to-robot transformation.
        
        Args:
            bbox: [x1, y1, x2, y2] in pixel coordinates
            depth_image: numpy array with depth in meters
            camera_intrinsics: dict with fx, fy, ppx, ppy (not used if transformer available)
        
        Returns:
            [x, y, z] in meters in ROBOT BASE FRAME (fr3_link0), or None if invalid
        """
        try:
            # Use the new transformer with TF support!
            position_robot = self.transformer.bbox_to_robot_frame(
                bbox=bbox,
                depth_image=depth_image,
                method='median'  # Robust depth estimation
            )
            
            if position_robot is not None:
                self.get_logger().info(
                    f'🤖 ROBOT BASE FRAME: X={position_robot[0]:.3f}m, Y={position_robot[1]:.3f}m, Z={position_robot[2]:.3f}m'
                )
            
            return position_robot
            
        except Exception as e:
            self.get_logger().error(f'Error in 3D position resolution: {e}')
            self.get_logger().error(
                'Make sure camera TF is being published! '
                'Launch camera calibration: ros2 launch realsense_cameras ee_camera_tf.launch.py'
            )
            return None
    
    def publish_status(self):
        """Publish current status for monitoring."""
        status_msg = {
            'timestamp': datetime.now().isoformat(),
            'robot_state': self.robot_status,
            'vision_state': self.vision_status,
            'llm_state': self.llm_status,
            'bridge_state': 'online',  # If we're running, bridge is online
            'current_task': self.current_task,
            'task_status': self.task_status
        }
        
        self.status_pub.publish(
            String(data=json.dumps(status_msg))
        )
    
    def handle_user_confirmation(self, msg: String):
        """Handle user confirmation from web dashboard."""
        try:
            confirmation = json.loads(msg.data)
            confirmed = confirmation.get('confirmed', False)
            motion = confirmation.get('motion', {})
            
            if confirmed:
                # User approved - republish target position and send motion command
                target = motion.get('target', 'object')
                action = motion.get('action', 'pick')
                
                self.get_logger().info(f'✓ User approved motion: {action} {target}')
                
                # Republish target position to ensure motion executor has it
                if self.last_target_position is not None:
                    self.get_logger().info(f'Position stored: {self.last_target_position}')
                    self._publish_target_position(self.last_target_position, target, action)
                    self.get_logger().info('✓ Republished target position for motion executor')
                    
                    # Small delay to ensure position arrives before command
                    import time
                    time.sleep(0.1)
                else:
                    self.get_logger().error('✗ No stored position to republish!')
                
                # Send pick command
                self._send_motion_command(action, target)
                self.get_logger().info(f'✓ Sent motion command: {action}')
                # time.sleep(2.0)  # Wait for pick to complete
                # self._send_motion_command('place', 'drop_zone')
                
            else:
                self.get_logger().info('✗ User cancelled motion')
                
        except Exception as e:
            self.get_logger().error(f'Error handling user confirmation: {e}')


def main(args=None):
    rclpy.init(args=args)
    coordinator = FrankaCoordinator()
    
    try:
        rclpy.spin(coordinator)
    except KeyboardInterrupt:
        pass
    finally:
        coordinator.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
