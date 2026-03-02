#!/usr/bin/env python3
"""
Record video from the robot arm's RealSense camera
Press 'r' to start/stop recording, 'q' to quit
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage
from cv_bridge import CvBridge
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
import argparse


class ArmCameraRecorder(Node):
    def __init__(self, output_dir: str = None, compressed: bool = True):
        super().__init__('arm_camera_recorder')
        
        self.bridge = CvBridge()
        self.latest_frame = None
        self.recording = False
        self.video_writer = None
        self.frame_count = 0
        
        # Setup output directory
        if output_dir is None:
            # Try to load from config
            try:
                config = self._load_config()
                workspace_root = Path(config['paths']['workspace_root']).expanduser()
                output_dir = str(workspace_root / config['paths']['recordings'])
            except:
                # Fallback to default
                workspace_root = Path.home() / 'franka-llm'
                output_dir = str(workspace_root / 'recordings')
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Camera topic (end effector camera)
        camera_topic = "/cameras/ee/ee_camera/color/image_raw"
        
        # Subscribe to camera
        if compressed:
            self.get_logger().info(f'Subscribing to {camera_topic}/compressed')
            self.image_sub = self.create_subscription(
                CompressedImage,
                f'{camera_topic}/compressed',
                self.compressed_image_callback,
                10
            )
        else:
            self.get_logger().info(f'Subscribing to {camera_topic}')
            self.image_sub = self.create_subscription(
                Image,
                camera_topic,
                self.image_callback,
                10
            )
        
        self.get_logger().info(f'✅ Arm Camera Recorder initialized')
        self.get_logger().info(f'   Output directory: {self.output_dir}')
        self.get_logger().info(f'   Press "r" to start/stop recording')
        self.get_logger().info(f'   Press "q" to quit')
    
    def _load_config(self) -> dict:
        """Load configuration from config.yaml"""
        current_path = Path(__file__).resolve()
        
        # Try walking up the directory tree
        for parent in [current_path] + list(current_path.parents):
            candidate = parent / 'config.yaml'
            if candidate.exists():
                with open(candidate, 'r') as f:
                    return yaml.safe_load(f)
        
        # Fallback to workspace root
        workspace_root = Path.home() / 'franka-llm'
        candidate = workspace_root / 'config.yaml'
        if candidate.exists():
            with open(candidate, 'r') as f:
                return yaml.safe_load(f)
        
        raise FileNotFoundError('Could not find config.yaml')
    
    def image_callback(self, msg: Image):
        """Handle raw image messages"""
        try:
            self.latest_frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f'Error converting image: {e}')
    
    def compressed_image_callback(self, msg: CompressedImage):
        """Handle compressed image messages"""
        try:
            np_arr = np.frombuffer(msg.data, np.uint8)
            self.latest_frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        except Exception as e:
            self.get_logger().error(f'Error converting compressed image: {e}')
    
    def start_recording(self):
        """Start video recording"""
        if self.latest_frame is None:
            self.get_logger().warn('No frame available yet')
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = self.output_dir / f'arm_recording_{timestamp}.mp4'
        
        height, width = self.latest_frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(str(filename), fourcc, 30.0, (width, height))
        
        if not self.video_writer.isOpened():
            self.get_logger().error('Failed to open video writer')
            self.video_writer = None
            return
        
        self.recording = True
        self.frame_count = 0
        self.get_logger().info(f'🔴 Recording started: {filename.name}')
    
    def stop_recording(self):
        """Stop video recording"""
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
            self.get_logger().info(f'⏹️  Recording stopped - saved {self.frame_count} frames')
        
        self.recording = False
        self.frame_count = 0
    
    def process_frame(self):
        """Process current frame - record if active and display"""
        if self.latest_frame is None:
            return
        
        frame = self.latest_frame.copy()
        
        # Add recording indicator
        if self.recording:
            cv2.circle(frame, (30, 30), 10, (0, 0, 255), -1)
            cv2.putText(frame, 'REC', (50, 40), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.7, (0, 0, 255), 2)
            cv2.putText(frame, f'Frames: {self.frame_count}', (50, 70), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Write frame
            if self.video_writer is not None:
                self.video_writer.write(self.latest_frame)
                self.frame_count += 1
        else:
            cv2.putText(frame, 'Press R to record', (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Display
        cv2.imshow('Arm Camera (Press R=Record, Q=Quit)', frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('r') or key == ord('R'):
            if self.recording:
                self.stop_recording()
            else:
                self.start_recording()
        elif key == ord('q') or key == ord('Q'):
            if self.recording:
                self.stop_recording()
            raise KeyboardInterrupt


def main(args=None):
    parser = argparse.ArgumentParser(description='Record video from robot arm camera')
    parser.add_argument('--output-dir', type=str, default=None,
                       help='Output directory for recordings (default: from config or ~/franka-llm/recordings)')
    parser.add_argument('--no-compressed', action='store_true',
                       help='Use raw images instead of compressed')
    
    # Parse known args (ROS will handle the rest)
    parsed_args, unknown = parser.parse_known_args()
    
    rclpy.init(args=unknown)
    
    recorder = ArmCameraRecorder(
        output_dir=parsed_args.output_dir,
        compressed=not parsed_args.no_compressed
    )
    
    try:
        # Process frames in loop
        while rclpy.ok():
            rclpy.spin_once(recorder, timeout_sec=0.01)
            recorder.process_frame()
    
    except KeyboardInterrupt:
        pass
    
    finally:
        if recorder.recording:
            recorder.stop_recording()
        cv2.destroyAllWindows()
        recorder.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
