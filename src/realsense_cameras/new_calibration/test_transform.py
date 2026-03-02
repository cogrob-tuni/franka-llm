#!/usr/bin/env python3
"""
Test script for ArUco-based pixel-to-robot transform
Tests the new calibration system before integration
"""

import pickle
import numpy as np
import pyrealsense2 as rs
from scipy.spatial.transform import Rotation as R
import cv2


class ArucoTransformer:
    """ArUco marker-based pixel to robot coordinate transformer"""
    
    def __init__(self, rotation_pkl='rotation_vector.pkl', translation_pkl='translational_vector.pkl'):
        """
        Load calibration data from pickle files
        
        Args:
            rotation_pkl: Path to rotation vector pickle file
            translation_pkl: Path to translation vector pickle file
        """
        # Load calibration vectors with compatibility for different numpy versions
        with open(rotation_pkl, 'rb') as f:
            self.rotation_vector = pickle.load(f)
        
        with open(translation_pkl, 'rb') as f:
            self.translation_vector = pickle.load(f)
        
        # Compute transformation matrices
        # R_cam_aruco: Rotation from ArUco to camera frame
        self.R_cam_aruco = R.from_rotvec(self.rotation_vector.squeeze()).as_matrix()
        
        # R_aruco_cam: Inverse rotation (camera to ArUco)
        self.R_aruco_cam = self.R_cam_aruco.T
        
        # t_aruco_cam: Translation from ArUco to camera
        self.t_aruco_cam = -self.R_aruco_cam @ self.translation_vector.squeeze()
        
        print("Calibration loaded:")
        print(f"   Rotation vector shape: {self.rotation_vector.shape}")
        print(f"   Translation vector: {self.translation_vector.squeeze()}")
        print(f"   ArUco → Camera translation: {self.t_aruco_cam}")
    
    def pixel_to_robot(self, u, v, z, camera_intrinsics, robot_offset_x=0.49, robot_offset_z=0.15):
        """
        Convert pixel coordinates to robot frame
        
        Args:
            u: Pixel x coordinate (horizontal)
            v: Pixel y coordinate (vertical)
            z: Depth in meters
            camera_intrinsics: pyrealsense2 intrinsics object
            robot_offset_x: X offset for robot calibration (default: 0.49m from config.yaml)
            robot_offset_z: Z offset for robot calibration (default: 0.15m from config.yaml)
        
        Returns:
            tuple: (robot_x, robot_y, robot_z) in meters
        
        Note: This is a standalone test utility. Main system loads these values from config.yaml
        """
        """
        # Step 1: Deproject pixel to camera frame
        X_cam = np.array([
            (u - camera_intrinsics.ppx) * z / camera_intrinsics.fx,
            (v - camera_intrinsics.ppy) * z / camera_intrinsics.fy,
            z
        ])
        
        print(f"\n📷 Camera frame: {X_cam}")
        
        # Step 2: Transform to ArUco frame
        X_aruco = self.R_aruco_cam @ X_cam + self.t_aruco_cam
        
        print(f"ArUco frame: {X_aruco}")
        
        # Step 3: Transform to robot frame
        # Based on calibration: robot frame is offset from ArUco marker
        robot_x = -X_aruco[1] + robot_offset_x
        robot_y = -X_aruco[0] - 0.01
        robot_z = X_aruco[2] + robot_offset_z
        
        print(f"Robot frame: X={robot_x:.3f}, Y={robot_y:.3f}, Z={robot_z:.3f}")
        
        return robot_x, robot_y, robot_z


def test_interactive():
    """Interactive testing with live camera feed"""
    print("\n" + "="*70)
    print("ARUCO TRANSFORM TESTER - Interactive Mode")
    print("="*70)
    
    # Initialize camera at calibration resolution (640x480)
    pipe = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    cfg.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    
    print("\nStarting camera at 640x480...")
    profile = pipe.start(cfg)
    
    # Get camera intrinsics
    color_profile = rs.video_stream_profile(profile.get_stream(rs.stream.color))
    intrinsics = color_profile.get_intrinsics()
    
    print(f"\nCamera Intrinsics:")
    print(f"   fx: {intrinsics.fx:.2f}")
    print(f"   fy: {intrinsics.fy:.2f}")
    print(f"   ppx: {intrinsics.ppx:.2f}")
    print(f"   ppy: {intrinsics.ppy:.2f}")
    print(f"   Resolution: {intrinsics.width}x{intrinsics.height}")
    
    # Load transformer
    transformer = ArucoTransformer()
    
    print("\n" + "="*70)
    print("CONTROLS:")
    print("   - Click on objects to get their robot coordinates")
    print("   - Press 'q' to quit")
    print("   - Press 's' to save current frame")
    print("="*70 + "\n")
    
    # Mouse callback for click testing
    clicked_point = [None, None]
    
    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            clicked_point[0] = x
            clicked_point[1] = y
    
    cv2.namedWindow('Camera Feed (640x480)')
    cv2.setMouseCallback('Camera Feed (640x480)', mouse_callback)
    
    frame_count = 0
    
    try:
        while True:
            # Get frames
            frames = pipe.wait_for_frames()
            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()
            
            if not color_frame or not depth_frame:
                continue
            
            # Convert to numpy arrays
            color_image = np.asanyarray(color_frame.get_data())
            depth_image = np.asanyarray(depth_frame.get_data())
            
            # Draw crosshair at clicked point
            display_image = color_image.copy()
            
            if clicked_point[0] is not None:
                u, v = clicked_point
                
                # Draw crosshair
                cv2.drawMarker(display_image, (u, v), (0, 255, 0), 
                             cv2.MARKER_CROSS, 20, 2)
                
                # Get depth
                depth_m = depth_frame.get_distance(u, v)
                
                if depth_m > 0:
                    # Transform to robot frame
                    robot_x, robot_y, robot_z = transformer.pixel_to_robot(
                        u, v, depth_m, intrinsics
                    )
                    
                    # Display info on image
                    info_text = [
                        f"Pixel: ({u}, {v})",
                        f"Depth: {depth_m:.3f}m",
                        f"Robot: ({robot_x:.3f}, {robot_y:.3f}, {robot_z:.3f})"
                    ]
                    
                    y_offset = 30
                    for i, text in enumerate(info_text):
                        cv2.putText(display_image, text, (10, y_offset + i*25),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                else:
                    cv2.putText(display_image, "Invalid depth!", (10, 30),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            
            # Show resolution info
            cv2.putText(display_image, "640x480", (10, color_image.shape[0] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            cv2.imshow('Camera Feed (640x480)', display_image)
            
            # Handle keyboard
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                filename = f'test_frame_{frame_count:03d}.jpg'
                cv2.imwrite(filename, color_image)
                print(f"\n💾 Saved: {filename}")
                frame_count += 1
    
    finally:
        pipe.stop()
        cv2.destroyAllWindows()
        print("\nCamera stopped")


def test_hardcoded():
    """Test with hardcoded pixel coordinates (no camera needed)"""
    print("\n" + "="*70)
    print("ARUCO TRANSFORM TESTER - Hardcoded Test")
    print("="*70)
    
    # Load transformer
    transformer = ArucoTransformer()
    
    # Mock camera intrinsics for 640x480
    class MockIntrinsics:
        def __init__(self):
            self.fx = 608.0
            self.fy = 608.0
            self.ppx = 320.0
            self.ppy = 240.0
            self.width = 640
            self.height = 480
    
    intrinsics = MockIntrinsics()
    
    print(f"\nUsing mock intrinsics (640x480)")
    
    # Test cases
    test_cases = [
        {"name": "Center", "u": 320, "v": 240, "z": 0.5},
        {"name": "Top-left object", "u": 605, "v": 87, "z": 0.50},
        {"name": "Right side", "u": 500, "v": 200, "z": 0.45},
    ]
    
    print("\n" + "="*70)
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['name']}")
        print(f"   Input: pixel=({test['u']}, {test['v']}), depth={test['z']:.2f}m")
        
        robot_x, robot_y, robot_z = transformer.pixel_to_robot(
            test['u'], test['v'], test['z'], intrinsics
        )
        
        print(f"   Result: Robot coordinates ready")


if __name__ == '__main__':
    import sys
    
    print("\n" + "="*70)
    print("ARUCO-BASED COORDINATE TRANSFORMER TEST")
    print("="*70)
    
    if len(sys.argv) > 1 and sys.argv[1] == '--hardcoded':
        test_hardcoded()
    else:
        try:
            test_interactive()
        except Exception as e:
            print(f"\nError: {e}")
            print("\nTo test without camera, run:")
            print("   python3 test_transform.py --hardcoded")
