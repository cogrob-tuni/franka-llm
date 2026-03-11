#!/usr/bin/env python3
"""
ArUco Calibration-Based Coordinate Transformer
Replaces TF2-based transformation with direct ArUco marker calibration
"""

import pickle
import numpy as np
from typing import Optional, Tuple
from scipy.spatial.transform import Rotation as R
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo
import os


class ArucoCoordinateTransformer:
    """
    Transforms coordinates using ArUco marker calibration.
    Replaces the old TF2-based CoordinateTransformer.
    
    Usage:
        transformer = ArucoCoordinateTransformer(node, calibration_dir='/path/to/calibration')
        point_robot = transformer.pixel_to_robot_frame(pixel_x=320, pixel_y=240, depth_m=0.5)
    """
    
    def __init__(self, 
                 node: Node,
                 calibration_dir: str = None,
                 robot_offset_x: float = 0.49,
                 robot_offset_y: float = 0.0,
                 robot_offset_z: float = 0.15):
        """
        Initialize ArUco-based coordinate transformer.
        
        Args:
            node: ROS 2 node for logging
            calibration_dir: Directory containing rotation_vector.pkl and translational_vector.pkl
            robot_offset_x: X offset for robot calibration (default: 0.49m)
            robot_offset_y: Y offset for robot calibration (default: 0.0m)
            robot_offset_z: Z offset for robot calibration (default: 0.15m)
        """
        self.node = node
        self.robot_offset_x = robot_offset_x
        self.robot_offset_y = robot_offset_y
        self.robot_offset_z = robot_offset_z
        
        # Camera intrinsics (will be set from CameraInfo)
        self.fx = None
        self.fy = None
        self.ppx = None
        self.ppy = None
        self.width = None
        self.height = None
        
        # Determine calibration directory
        if calibration_dir is None:
            # Default to new_calibration directory
            pkg_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            calibration_dir = os.path.join(pkg_dir, 'realsense_cameras', 'new_calibration')
            # If the derived path doesn't exist (e.g. running from install/),
            # fall back to workspace root
            if not os.path.isdir(calibration_dir):
                workspace_root = os.path.expanduser('~/franka-llm')
                calibration_dir = os.path.join(workspace_root, 'src', 'realsense_cameras', 'new_calibration')
        
        self.calibration_dir = calibration_dir
        
        # Load calibration data
        self._load_calibration()
        
        self.node.get_logger().info(
            f'ArUco Coordinate Transformer initialized'
        )
        self.node.get_logger().info(
            f'   Calibration dir: {calibration_dir}'
        )
        self.node.get_logger().info(
            f'   Robot offsets: X={robot_offset_x}m, Y={robot_offset_y}m, Z={robot_offset_z}m'
        )
    
    def _load_calibration(self):
        """Load rotation and translation vectors from pickle files"""
        rotation_path = os.path.join(self.calibration_dir, 'rotation_vector.pkl')
        translation_path = os.path.join(self.calibration_dir, 'translational_vector.pkl')
        
        if not os.path.exists(rotation_path):
            raise FileNotFoundError(f'Rotation vector not found: {rotation_path}')
        if not os.path.exists(translation_path):
            raise FileNotFoundError(f'Translation vector not found: {translation_path}')
        
        with open(rotation_path, 'rb') as f:
            self.rotation_vector = pickle.load(f)
        
        with open(translation_path, 'rb') as f:
            self.translation_vector = pickle.load(f)
        
        # Compute transformation matrices
        # R_cam_aruco: Rotation from ArUco to camera frame
        self.R_cam_aruco = R.from_rotvec(self.rotation_vector.squeeze()).as_matrix()
        
        # R_aruco_cam: Inverse rotation (camera to ArUco)
        self.R_aruco_cam = self.R_cam_aruco.T
        
        # t_aruco_cam: Translation from ArUco to camera
        self.t_aruco_cam = -self.R_aruco_cam @ self.translation_vector.squeeze()
        
        self.node.get_logger().info(
            f'   Calibration loaded: rotation shape={self.rotation_vector.shape}'
        )
    
    def update_camera_intrinsics(self, camera_info: CameraInfo):
        """
        Update camera intrinsics from CameraInfo message.
        
        Args:
            camera_info: sensor_msgs/CameraInfo message
        """
        self.fx = camera_info.k[0]
        self.fy = camera_info.k[4]
        self.ppx = camera_info.k[2]
        self.ppy = camera_info.k[5]
        self.width = camera_info.width
        self.height = camera_info.height
        
        self.node.get_logger().info(
            f'Camera intrinsics updated: fx={self.fx:.1f}, fy={self.fy:.1f}, '
            f'ppx={self.ppx:.1f}, ppy={self.ppy:.1f}, size={self.width}x{self.height}'
        )
    
    def pixel_to_camera_frame(self, 
                              pixel_u: int, 
                              pixel_v: int, 
                              depth_m: float) -> Optional[np.ndarray]:
        """
        Convert pixel coordinates + depth to 3D point in camera frame.
        Uses pinhole camera model.
        
        Args:
            pixel_u: Horizontal pixel coordinate (x, column)
            pixel_v: Vertical pixel coordinate (y, row)
            depth_m: Depth in meters
            
        Returns:
            3D point [x, y, z] in camera frame (meters), or None if invalid
        """
        if None in [self.fx, self.fy, self.ppx, self.ppy]:
            self.node.get_logger().error('Camera intrinsics not set! Call update_camera_intrinsics() first')
            return None
        
        if depth_m <= 0 or np.isnan(depth_m) or np.isinf(depth_m):
            self.node.get_logger().warn(f'Invalid depth value: {depth_m}')
            return None
        
        # Clamp pixel coordinates to image bounds
        pixel_u = max(0, min(pixel_u, self.width - 1))
        pixel_v = max(0, min(pixel_v, self.height - 1))
        
        # Pinhole camera model
        x_cam = (pixel_u - self.ppx) * depth_m / self.fx
        y_cam = (pixel_v - self.ppy) * depth_m / self.fy
        z_cam = depth_m
        
        point_cam = np.array([x_cam, y_cam, z_cam], dtype=np.float64)
        
        self.node.get_logger().debug(
            f'Pixel ({pixel_u}, {pixel_v}) @ {depth_m:.3f}m → '
            f'Camera frame: [{x_cam:.3f}, {y_cam:.3f}, {z_cam:.3f}]'
        )
        
        return point_cam
    
    def camera_frame_to_robot_frame(self, 
                                     point_camera: np.ndarray) -> Optional[np.ndarray]:
        """
        Transform 3D point from camera frame to robot base frame using ArUco calibration.
        
        Args:
            point_camera: 3D point [x, y, z] in camera frame (meters)
            
        Returns:
            3D point [x, y, z] in robot frame (meters), or None if invalid
        """
        if point_camera is None or len(point_camera) != 3:
            return None
        
        # Transform to ArUco frame
        point_aruco = self.R_aruco_cam @ point_camera + self.t_aruco_cam
        
        # Transform to robot frame
        # Based on calibration: robot frame is offset from ArUco marker
        robot_x = -point_aruco[1] + self.robot_offset_x
        robot_y = -point_aruco[0] + self.robot_offset_y
        robot_z = point_aruco[2] + self.robot_offset_z
        
        point_robot = np.array([robot_x, robot_y, robot_z], dtype=np.float64)
        
        self.node.get_logger().debug(
            f'Camera [{point_camera[0]:.3f}, {point_camera[1]:.3f}, {point_camera[2]:.3f}] → '
            f'ArUco [{point_aruco[0]:.3f}, {point_aruco[1]:.3f}, {point_aruco[2]:.3f}] → '
            f'Robot [{robot_x:.3f}, {robot_y:.3f}, {robot_z:.3f}]'
        )
        
        return point_robot
    
    def pixel_to_robot_frame(self,
                             pixel_u: int,
                             pixel_v: int,
                             depth_m: float) -> Optional[np.ndarray]:
        """
        One-step conversion: pixel + depth → robot frame coordinates.
        
        Args:
            pixel_u: Horizontal pixel coordinate
            pixel_v: Vertical pixel coordinate
            depth_m: Depth in meters
            
        Returns:
            3D point [x, y, z] in robot frame, or None if conversion fails
        """
        # Step 1: Pixel → Camera frame
        point_camera = self.pixel_to_camera_frame(pixel_u, pixel_v, depth_m)
        if point_camera is None:
            return None
        
        # Step 2: Camera frame → Robot frame
        point_robot = self.camera_frame_to_robot_frame(point_camera)
        
        if point_robot is not None:
            self.node.get_logger().info(
                f'Pixel ({pixel_u}, {pixel_v}) @ {depth_m:.3f}m -> '
                f'Robot frame: X={point_robot[0]:.3f}m, Y={point_robot[1]:.3f}m, Z={point_robot[2]:.3f}m'
            )
        
        return point_robot
    
    def bbox_to_robot_frame(self,
                            bbox: Tuple[int, int, int, int],
                            depth_image: np.ndarray,
                            method: str = 'median') -> Optional[np.ndarray]:
        """
        Convert bounding box + depth image to 3D point in robot frame.
        Uses bbox centroid and robust depth estimation.
        
        Args:
            bbox: Bounding box [x1, y1, x2, y2] in pixels
            depth_image: Depth image array (float32, meters)
            method: Depth estimation method ('median', 'min', 'center')
            
        Returns:
            3D point [x, y, z] in robot frame, or None if invalid
        """
        x1, y1, x2, y2 = bbox
        
        # Get bbox centroid
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        
        # Clamp bbox to image bounds
        height, width = depth_image.shape
        cy = max(0, min(cy, height - 1))
        cx = max(0, min(cx, width - 1))
        y1 = max(0, min(int(y1), height - 1))
        y2 = max(0, min(int(y2), height - 1))
        x1 = max(0, min(int(x1), width - 1))
        x2 = max(0, min(int(x2), width - 1))
        
        # Extract depth from ROI
        roi = depth_image[y1:y2, x1:x2]
        valid_depths = roi[roi > 0]  # Filter invalid (zero) depths
        
        if len(valid_depths) == 0:
            self.node.get_logger().warn('No valid depth values in bounding box ROI')
            return None
        
        # Robust depth estimation
        if method == 'median':
            depth_m = float(np.median(valid_depths))
        elif method == 'min':
            depth_m = float(np.min(valid_depths))
        elif method == 'center':
            depth_m = float(depth_image[cy, cx])
            if depth_m <= 0:
                depth_m = float(np.median(valid_depths))  # Fallback
        else:
            depth_m = float(np.median(valid_depths))
        
        self.node.get_logger().info(
            f'Bbox [{x1}, {y1}, {x2}, {y2}] → Centroid ({cx}, {cy}), '
            f'Depth: {depth_m:.3f}m ({method})'
        )
        
        # Convert to robot frame
        return self.pixel_to_robot_frame(cx, cy, depth_m)
