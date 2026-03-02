#!/usr/bin/env python3
"""
VLM Node - Simplified Version
Permanently subscribes to camera and processes VLM requests as they arrive.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import Image, CompressedImage, CameraInfo
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
import cv2
import numpy as np
from cv_bridge import CvBridge
import json
from pathlib import Path
import yaml

# Import helper modules
from .vlm_api_client import OllamaVLMClient
from .image_utils import encode_image_to_base64, save_debug_image, parse_vlm_response
from .depth_utils import DepthProcessor


class VLMNode(Node):
    """Simplified VLM Node - always subscribed to camera"""

    def __init__(self):
        super().__init__('vlm_node')
        
        # Load configuration
        self._load_config()
        
        # Initialize components
        self.bridge = CvBridge()
        self.vlm_client = OllamaVLMClient(
            host=self.ollama_host,
            model=self.vlm_model,
            timeout=self.timeout,
            temperature=self.temperature,
            logger=self.get_logger()
        )
        self.depth_processor = DepthProcessor()
        
        # Image storage (always keep latest)
        self.latest_image = None
        self.latest_depth = None
        
        # Camera topics (from config)
        self.use_compressed = True
        
        # Setup debug directory
        if self.save_images and self.debug_dir_path:
            self.debug_dir = self.debug_dir_path
            self.debug_dir.mkdir(exist_ok=True, parents=True)
            self.get_logger().info(f'Debug images will be saved to: {self.debug_dir}')
        else:
            self.debug_dir = None
        
        # Setup ROS interfaces
        self._setup_subscribers()
        self._setup_publishers()
        
        # Check VLM health
        healthy, msg = self.vlm_client.check_health()
        if healthy:
            self.get_logger().info(f'✓ {msg}')
        else:
            self.get_logger().warn(f'⚠ {msg}')
        
        # Publish system info log
        self._publish_system_info()
        
        self.get_logger().info(
            f'VLM Node initialized:\n'
            f'  Model: {self.vlm_model}\n'
            f'  Ollama URL: {self.ollama_host}\n'
            f'  Temperature: {self.temperature}\n'
            f'  Timeout: {self.timeout}s\n'
            f'  Save images: {self.save_images}\n'
            f'  Color topic: {self.camera_topic}\n'
            f'  Depth topic: {self.depth_topic}\n'
            f'  Use compressed: {self.use_compressed}'
        )
    
    def _load_config(self):
        """Load configuration from config.yaml"""
        config_path = self._find_config_file()
        
        self.get_logger().info(f'Loading config from: {config_path}')
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # VLM settings
        self.vlm_model = config['vlm']['model']
        self.ollama_host = config['vlm']['ollama_url']
        self.timeout = config['vlm']['timeout']
        self.temperature = config['vlm'].get('temperature', 0.3)
        
        # Camera topics from config
        self.camera_topic = config['camera']['ee_camera_topic']
        self.depth_topic = config['camera']['depth_topic']
        self.camera_info_topic = config['camera']['camera_info_topic']
        
        # Debug settings
        self.save_images = config['debug']['save_images']
        
        # Paths
        workspace_root = Path(config['paths']['workspace_root']).expanduser()
        self.debug_dir_path = workspace_root / config['paths']['debug_images'] if self.save_images else None
    
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
    
    def _setup_subscribers(self):
        """Setup ROS subscribers - permanently subscribed"""
        # QoS for images
        image_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        # VLM request subscription
        self.request_sub = self.create_subscription(
            String,
            '/vlm_request',
            self._request_callback,
            10
        )
        
        # Image subscription (compressed or raw)
        if self.use_compressed:
            self.image_sub = self.create_subscription(
                CompressedImage,
                self.camera_topic + '/compressed',
                self._compressed_image_callback,
                image_qos
            )
        else:
            self.image_sub = self.create_subscription(
                Image,
                self.camera_topic,
                self._image_callback,
                image_qos
            )
        
        # Depth subscription
        self.depth_sub = self.create_subscription(
            Image,
            self.depth_topic,
            self._depth_callback,
            image_qos
        )
        
        # Camera info subscription
        self.camera_info_sub = self.create_subscription(
            CameraInfo,
            self.camera_info_topic,
            self._camera_info_callback,
            image_qos
        )
        
        self.get_logger().info('Subscribed to camera topics (permanently)')
    
    def _setup_publishers(self):
        """Setup ROS publishers"""
        self.explanation_pub = self.create_publisher(String, '/vlm/explanation', 10)
        self.position_pub = self.create_publisher(PoseStamped, '/vlm_center_position', 10)
        # NEW: Publish grounding info with bbox for coordinator
        self.grounding_pub = self.create_publisher(String, '/vlm_grounding', 10)
    
    def _image_callback(self, msg: Image):
        """Handle raw image messages"""
        try:
            self.latest_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f'Error in image callback: {e}')
    
    def _compressed_image_callback(self, msg: CompressedImage):
        """Handle compressed image messages"""
        try:
            np_arr = np.frombuffer(msg.data, np.uint8)
            self.latest_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        except Exception as e:
            self.get_logger().error(f'Error in compressed image callback: {e}')
    
    def _depth_callback(self, msg: Image):
        """Handle depth image messages"""
        try:
            depth_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            
            # Convert to meters if needed
            if depth_image.dtype == np.uint16:
                depth_image = depth_image.astype(np.float32) / 1000.0
            
            self.latest_depth = depth_image
            self.depth_processor.update_depth_image(depth_image)
        except Exception as e:
            self.get_logger().error(f'Error in depth callback: {e}')
    
    def _camera_info_callback(self, msg: CameraInfo):
        """Handle camera info messages"""
        if self.depth_processor.camera_intrinsics is None:
            self.depth_processor.update_intrinsics(msg)
            intrinsics = self.depth_processor.camera_intrinsics
            self.get_logger().info(
                f'Camera intrinsics loaded: '
                f'fx={intrinsics["fx"]:.1f}, fy={intrinsics["fy"]:.1f}, '
                f'ppx={intrinsics["ppx"]:.1f}, ppy={intrinsics["ppy"]:.1f}, '
                f'{intrinsics["width"]}x{intrinsics["height"]}'
            )
    
    def _request_callback(self, msg: String):
        """
        Handle VLM requests
        Format: JSON with "type" (describe/locate) and optional "object"
        """
        self.get_logger().info(f'[VLM REQUEST] {msg.data}')
        
        # Check if we have an image
        if self.latest_image is None:
            self.get_logger().warn('No image available yet')
            return
        
        try:
            # Parse request
            request_type, target_object = self._parse_request(msg.data)
            
            self.get_logger().info(f'Processing: type={request_type}, object={target_object}')
            
            if request_type == 'locate' and target_object:
                self._handle_locate_request(target_object)
            elif request_type == 'ground_location' and target_object:
                # target_object is actually the full request dict for ground_location
                self._handle_ground_location_request(target_object)
            else:
                self._handle_describe_request()
                
        except Exception as e:
            self.get_logger().error(f'Error handling request: {e}')
            import traceback
            self.get_logger().error(traceback.format_exc())
    
    def _parse_request(self, request_str: str) -> tuple:
        """Parse request string into (type, object_name or location or full request)"""
        try:
            # Try JSON format
            req = json.loads(request_str)
            req_type = req.get('type', 'describe')
            
            # Normalize type values
            if req_type in ['scene_description', 'describe', 'analyze', 'scene']:
                return 'describe', None
            elif req_type == 'locate':
                # Return full request dict to get action parameter
                return 'locate', req
            elif req_type == 'ground_location':
                # Return tuple with location and full request dict for placement params
                return 'ground_location', req
            else:
                return 'describe', None
                
        except json.JSONDecodeError:
            # Try simple text format
            text = request_str.strip()
            if text.upper().startswith('LOCATE '):
                return 'locate', text[7:].strip()
            else:
                return 'describe', None
    
    def _handle_ground_location_request(self, request_data):
        """Handle location grounding request"""
        # Extract location and placement parameters
        if isinstance(request_data, dict):
            location_description = request_data.get('location', '')
            placement_type = request_data.get('placement_type', 'direct')
            direction = request_data.get('direction', None)
        else:
            # Fallback for string format
            location_description = str(request_data)
            placement_type = 'direct'
            direction = None
        
        self.get_logger().info(f'Grounding location: "{location_description}" (type: {placement_type}, direction: {direction})...')
        
        # Encode image
        image_base64 = encode_image_to_base64(self.latest_image)
        
        # Pass actual image dimensions
        h, w = self.latest_image.shape[:2]
        
        # Query VLM
        result = self.vlm_client.ground_location(image_base64, location_description, img_width=w, img_height=h)
        
        if result:
            # Parse and normalize response
            parsed = parse_vlm_response(json.dumps(result))
            
            if parsed and parsed.get('center'):
                center = parsed['center']
                confidence = parsed.get('confidence', 'unknown')
                description = parsed.get('description', '')
                
                self.get_logger().info(
                    f'✓ Located "{location_description}" at pixel {center}\n'
                    f'  Confidence: {confidence}\n'
                    f'  Description: {description}'
                )
                
                # Get 3D position first (need depth for debug image)
                position_3d = self.depth_processor.get_3d_position(center[0], center[1])
                depth_value = position_3d['position'][2] if position_3d else None
                
                if position_3d:
                    pos = position_3d['position']
                    self.get_logger().info(
                        f'3D Position: X={pos[0]:.3f}m, Y={pos[1]:.3f}m, Z={pos[2]:.3f}m'
                    )
                
                # Save debug image BEFORE publishing so web_handler finds the right file
                if self.save_images and self.debug_dir:
                    try:
                        # Use location description as filename
                        saved_path = save_debug_image(
                            self.latest_image,
                            location_description.replace(' ', '_'),
                            center=center,
                            depth=depth_value,
                            debug_dir=self.debug_dir,
                            model_name=self.vlm_model
                        )
                        self.get_logger().info(f'✓ Saved debug image: {Path(saved_path).name}')
                    except Exception as e:
                        self.get_logger().error(f'Failed to save debug image: {e}')

                # Publish results
                self._publish_explanation(json.dumps(parsed))
                
                if position_3d:
                    self._publish_position(position_3d)
                    # Publish grounding with placement parameters for coordinator
                    self._publish_grounding(
                        location_description, 
                        center, 
                        'place',
                        placement_type=placement_type,
                        direction=direction
                    )
            else:
                self.get_logger().warn(f'✗ Could not ground location "{location_description}"')
                self._publish_explanation(f'Location "{location_description}" not found')
        else:
            # Check if this was a "not found" response vs actual VLM failure
            if result and result.get('not_found'):
                self.get_logger().warn(f'✗ VLM could not find location "{location_description}"')
                self._publish_explanation(f'I cannot find "{location_description}" in the camera view.')
            else:
                self.get_logger().error(f'✗ Failed to get response from VLM')
                self._publish_explanation('Vision system is not responding. Please try again.')
    
    def _handle_locate_request(self, request_data):
        """Handle object localization request"""
        # Extract object name and action from request
        if isinstance(request_data, dict):
            target_object = request_data.get('object', '')
            action = request_data.get('action', 'pick')  # Default to pick if not specified
        else:
            # Fallback for string format
            target_object = str(request_data)
            action = 'pick'
        
        self.get_logger().info(f'Locating "{target_object}" for action: {action}...')
        
        # Encode image
        image_base64 = encode_image_to_base64(self.latest_image)
        
        # Pass actual image dimensions so VLM coords are normalised correctly
        h, w = self.latest_image.shape[:2]
        
        # Query VLM
        result = self.vlm_client.locate_object(image_base64, target_object, img_width=w, img_height=h)
        
        if result:
            # Parse and normalize response
            parsed = parse_vlm_response(json.dumps(result))
            
            if parsed and parsed.get('center'):
                center = parsed['center']
                confidence = parsed.get('confidence', 'unknown')
                description = parsed.get('description', '')
                
                self.get_logger().info(
                    f'✓ Located "{target_object}" at pixel {center}\n'
                    f'  Confidence: {confidence}\n'
                    f'  Description: {description}'
                )
                
                # Get 3D position first (need depth for debug image)
                position_3d = self.depth_processor.get_3d_position(center[0], center[1])
                depth_value = position_3d['position'][2] if position_3d else None
                
                if position_3d:
                    pos = position_3d['position']
                    self.get_logger().info(
                        f'3D Position: X={pos[0]:.3f}m, Y={pos[1]:.3f}m, Z={pos[2]:.3f}m'
                    )
                
                # Save debug image BEFORE publishing so web_handler finds the right file
                if self.save_images and self.debug_dir:
                    try:
                        saved_path = save_debug_image(
                            self.latest_image,
                            target_object,
                            center=center,
                            depth=depth_value,
                            debug_dir=self.debug_dir,
                            model_name=self.vlm_model
                        )
                        self.get_logger().info(f'✓ Saved debug image: {Path(saved_path).name}')
                    except Exception as e:
                        self.get_logger().error(f'Failed to save debug image: {e}')

                # Publish results
                self._publish_explanation(json.dumps(parsed))
                
                if position_3d:
                    self._publish_position(position_3d)
                    # NEW: Publish grounding with bbox for coordinator
                    self._publish_grounding(target_object, center, action)
            else:
                self.get_logger().warn(f'✗ Could not locate "{target_object}"')
                # Special message for hand detection failure during handover
                if target_object.lower() == 'hand' and action == 'handover':
                    error_msg = "I don't see your hand. Please show your hand clearly in front of the camera."
                    self._publish_explanation(error_msg)
                else:
                    self._publish_explanation(f'Object "{target_object}" not found')
        else:
            # Check if this was a "not found" response vs actual VLM failure
            if result and result.get('not_found'):
                self.get_logger().warn(f'✗ VLM could not find "{target_object}"')
                # Special message for hand detection failure during handover
                if target_object.lower() == 'hand' and action == 'handover':
                    error_msg = "I don't see your hand. Please show your hand clearly in front of the camera."
                    self._publish_explanation(error_msg)
                else:
                    self._publish_explanation(f'I cannot find "{target_object}" in the camera view.')
            else:
                self.get_logger().error(f'✗ Failed to get response from VLM')
                self._publish_explanation('Vision system is not responding. Please try again.')
    
    def _handle_describe_request(self):
        """Handle scene description request"""
        self.get_logger().info('Analyzing scene...')
        
        # Encode image
        image_base64 = encode_image_to_base64(self.latest_image)
        
        # Query VLM
        description = self.vlm_client.describe_scene(image_base64)
        
        if description:
            self.get_logger().info(f'✓ Scene description:\n{description}')
            
            # Save image BEFORE publishing so web_handler finds the right file
            if self.save_images and self.debug_dir:
                try:
                    saved_path = save_debug_image(
                        self.latest_image,
                        'scene_description',
                        debug_dir=self.debug_dir,
                        model_name=self.vlm_model
                    )
                    self.get_logger().info(f'✓ Saved debug image: {Path(saved_path).name}')
                except Exception as e:
                    self.get_logger().error(f'Failed to save debug image: {e}')
            
            self._publish_explanation(description)
        else:
            self.get_logger().error('✗ Failed to get scene description')
    
    def _publish_explanation(self, text: str):
        """Publish explanation/result text"""
        msg = String()
        msg.data = text
        self.explanation_pub.publish(msg)
    
    def _publish_position(self, position_3d: dict):
        """Publish 3D position"""
        pose_msg = PoseStamped()
        pose_msg.header.stamp = self.get_clock().now().to_msg()
        pose_msg.header.frame_id = 'ee_d435i_color_optical_frame'
        pose_msg.pose.position.x = position_3d['position'][0]
        pose_msg.pose.position.y = position_3d['position'][1]
        pose_msg.pose.position.z = position_3d['position'][2]
        pose_msg.pose.orientation.w = 1.0
        
        self.position_pub.publish(pose_msg)
    
    def _publish_grounding(self, target_name: str, center: list, action: str, 
                          placement_type: str = 'direct', direction: str = None):
        """Publish grounding info with bbox around center pixel for coordinator"""
        # Create a small bbox around the center (±20 pixels)
        bbox_size = 40
        x1 = max(0, center[0] - bbox_size // 2)
        y1 = max(0, center[1] - bbox_size // 2)
        x2 = center[0] + bbox_size // 2
        y2 = center[1] + bbox_size // 2
        
        grounding_data = {
            "target": target_name,
            "bbox": [x1, y1, x2, y2],
            "center": center,
            "action": action,
            "placement_type": placement_type
        }
        
        # Add direction if specified
        if direction:
            grounding_data["direction"] = direction
        
        msg = String()
        msg.data = json.dumps(grounding_data)
        self.grounding_pub.publish(msg)
        
        placement_info = f" (type: {placement_type}"
        if direction:
            placement_info += f", direction: {direction}"
        placement_info += ")"
        
        self.get_logger().info(
            f'📤 Published grounding: {target_name} bbox=[{x1},{y1},{x2},{y2}]{placement_info} → /vlm_grounding'
        )
    
    def _publish_system_info(self):
        """Publish VLM system information on startup."""
        info = {
            'type': 'system_info',
            'component': 'vlm',
            'model': self.vlm_model,
            'config': {
                'temperature': self.temperature,
                'timeout': self.timeout,
                'save_images': self.save_images
            }
        }
        msg = String()
        msg.data = json.dumps(info)
        self.explanation_pub.publish(msg)
        self.get_logger().info(f'Published VLM system info: {self.vlm_model}')


def main(args=None):
    rclpy.init(args=args)
    node = VLMNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
