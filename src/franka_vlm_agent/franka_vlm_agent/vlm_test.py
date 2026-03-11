#!/usr/bin/env python3
"""
VLM Test - Test LLaVA with a sample image
Useful for debugging and verifying Ollama is running correctly
"""

import requests
import base64
import sys
import argparse
from pathlib import Path
import time


def test_ollama_connection(ollama_host):
    """Test if Ollama is running and accessible"""
    try:
        response = requests.get(f'{ollama_host}/api/tags', timeout=5)
        if response.status_code == 200:
            print(f'Ollama is running at {ollama_host}')
            models = response.json().get('models', [])
            if models:
                print(f'Available models:')
                for model in models:
                    print(f'  - {model.get("name")}')
                return True
            else:
                print('No models found. Pull a model first:')
                print('  ollama pull llava:7b')
                return False
        else:
            print(f'Ollama returned error: {response.status_code}')
            return False
    except requests.exceptions.ConnectionError:
        print(f'Cannot connect to Ollama at {ollama_host}')
        print('Make sure Ollama is running:')
        print('  ollama serve')
        return False
    except Exception as e:
        print(f'Error: {e}')
        return False


def test_vlm_with_image(ollama_host, model, image_path):
    """Test VLM by sending a sample image"""
    
    # Check if image exists
    if not Path(image_path).exists():
        print(f'Image not found: {image_path}')
        return False
    
    try:
        # Read and encode image
        print(f'Loading image: {image_path}')
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # Prepare request
        prompt = (
            'Describe what you see in this image. '
            'If this is a table scene, describe the objects on the table.'
        )
        
        payload = {
            'model': model,
            'prompt': prompt,
            'images': [image_data],
            'stream': False,
            'temperature': 0.7,
        }
        
        print(f'Sending image to {model}...')
        print(f'Prompt: {prompt}')
        print('-' * 50)
        
        # Send request
        start_time = time.time()
        response = requests.post(
            f'{ollama_host}/api/generate',
            json=payload,
            timeout=120
        )
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            explanation = result.get('response', 'No response')
            
            print(f'Response from {model}:')
            print('-' * 50)
            print(explanation)
            print('-' * 50)
            print(f'Time taken: {elapsed:.1f}s')
            print(f'Test successful!')
            return True
        else:
            print(f'API error: {response.status_code}')
            print(response.text)
            return False
            
    except requests.exceptions.Timeout:
        print(f'Request timed out after 120 seconds')
        return False
    except Exception as e:
        print(f'Error: {e}')
        return False


def create_test_image():
    """Create a simple test image if no image provided"""
    try:
        import cv2
        import numpy as np
        
        # Create a simple table scene image
        img = np.ones((480, 640, 3), dtype=np.uint8) * 200  # Light gray background
        
        # Draw a table outline
        cv2.rectangle(img, (50, 100), (590, 430), (139, 69, 19), 3)  # Brown table
        
        # Draw some objects on the table
        cv2.circle(img, (200, 200), 30, (0, 0, 255), -1)  # Red apple
        cv2.rectangle(img, (300, 180), (380, 220), (0, 255, 0), -1)  # Green cube
        cv2.ellipse(img, (480, 250), (40, 25), 0, 0, 360, (255, 0, 0), -1)  # Blue cup
        
        # Add text
        cv2.putText(img, 'Test Table Scene', (150, 50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
        
        # Save image
        test_image_path = '/tmp/vlm_test_image.jpg'
        cv2.imwrite(test_image_path, img)
        
        print(f'Created test image: {test_image_path}')
        return test_image_path
        
    except ImportError:
        print('OpenCV not available. Cannot create test image.')
        return None


def main():
    parser = argparse.ArgumentParser(description='Test VLM setup')
    parser.add_argument('--ollama-host', default='http://localhost:11434',
                       help='Ollama server host')
    parser.add_argument('--model', default='llava:7b',
                       help='Model to test')
    parser.add_argument('--image', default=None,
                       help='Image path to test (creates test image if not provided)')
    
    args = parser.parse_args()
    
    print('=' * 50)
    print('VLM Test')
    print('=' * 50)
    print()
    
    # Test Ollama connection
    if not test_ollama_connection(args.ollama_host):
        sys.exit(1)
    
    print()
    
    # Prepare image
    image_path = args.image
    if not image_path:
        image_path = create_test_image()
        if not image_path:
            print('Please provide an image path with --image')
            sys.exit(1)
    
    print()
    
    # Test with image
    if not test_vlm_with_image(args.ollama_host, args.model, image_path):
        sys.exit(1)
    
    print()
    print('=' * 50)
    print('All tests passed!')
    print('=' * 50)


if __name__ == '__main__':
    main()
