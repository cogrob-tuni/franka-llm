#!/usr/bin/env python3
"""
Simple Terminal Chat Interface for LLM Coordinator
Routes user commands through the new LLM coordinator architecture
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
import sys
import select


class CoordinatorChatNode(Node):
    
    def __init__(self):
        super().__init__('coordinator_chat')
        
        # Publisher for user commands
        self.command_pub = self.create_publisher(String, '/user_command', 10)
        
        # Subscriber for coordinator responses
        self.response_sub = self.create_subscription(
            String,
            '/coordinator_response',
            self.response_callback,
            10
        )
        
        # Subscriber for VLM positions (for display)
        self.position_sub = self.create_subscription(
            PoseStamped,
            '/vlm_center_position',
            self.position_callback,
            10
        )
        
        self.get_logger().info('=' * 60)
        self.get_logger().info('LLM Coordinator Chat Interface')
        self.get_logger().info('=' * 60)
        self.get_logger().info('Commands are routed through intelligent LLM coordinator')
        self.get_logger().info('  - Scene queries → VLM agent')
        self.get_logger().info('  - Manipulation → Motion agent (with VLM assist)')
        self.get_logger().info('')
        self.get_logger().info('Type your commands below:')
        self.get_logger().info('=' * 60)
    
    def response_callback(self, msg: String):
        """Handle coordinator response"""
        print(f'\n{msg.data}')
        print('\n' + '=' * 60)
        print('Ready for next command')
        print('> ', end='', flush=True)
    
    def position_callback(self, msg: PoseStamped):
        """Handle VLM position updates"""
        x = msg.pose.position.x
        y = msg.pose.position.y
        z = msg.pose.position.z
        
        print(f'\n[3D Position] Center of scene in {msg.header.frame_id}:')
        print(f'[3D Position] X: {x:>7.3f} m, Y: {y:>7.3f} m, Z: {z:>7.3f} m')
    
    def send_command(self, text: str):
        """Send command to coordinator"""
        msg = String()
        msg.data = text
        self.command_pub.publish(msg)
        
        print(f'[You] {text}')
        print('[Coordinator] Processing...')


def main(args=None):
    rclpy.init(args=args)
    chat = CoordinatorChatNode()
    
    # Give time for connections
    import time
    time.sleep(1)
    
    print('\n> ', end='', flush=True)
    
    # Input thread
    import threading
    
    def input_thread():
        while rclpy.ok():
            if select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.readline().strip()
                if line:
                    if line.lower() in ['quit', 'exit', 'q']:
                        print('Goodbye!')
                        rclpy.shutdown()
                        break
                    chat.send_command(line)
    
    thread = threading.Thread(target=input_thread, daemon=True)
    thread.start()
    
    try:
        rclpy.spin(chat)
    except KeyboardInterrupt:
        print('\nShutting down...')
    finally:
        chat.destroy_node()
        try:
            rclpy.shutdown()
        except:
            pass


if __name__ == '__main__':
    main()
