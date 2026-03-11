#!/usr/bin/env python3
"""
VLM API Client for Ollama
Handles communication with Ollama API for vision-language tasks
"""

import requests
import json
from typing import Optional, Dict


class OllamaVLMClient:
    """Client for Ollama Vision-Language Model API"""
    
    def __init__(self, host: str, model: str, timeout: int = 30, temperature: float = 0.3, logger=None):
        """
        Initialize Ollama VLM client
        
        Args:
            host: Ollama server URL (e.g., "http://localhost:11434")
            model: Model name (e.g., "llava:7b", "gemma3:27b")
            timeout: Request timeout in seconds
            temperature: Sampling temperature (0.0-1.0)
            logger: ROS logger instance for logging
        """
        self.host = host
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.logger = logger
    
    def _log(self, message: str, level: str = 'info'):
        """Log message if logger is available"""
        if self.logger:
            if level == 'info':
                self.logger.info(message)
            elif level == 'warn':
                self.logger.warn(message)
            elif level == 'error':
                self.logger.error(message)
        # Also print to console for non-ROS environments
        elif level in ['warn', 'error']:
            print(f'[{level.upper()}] {message}')
    
    def check_health(self) -> tuple[bool, str]:
        """
        Check if Ollama server is running and model is available
        
        Returns:
            (is_healthy, message) tuple
        """
        try:
            response = requests.get(f'{self.host}/api/tags', timeout=5)
            
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                
                if self.model in model_names or any(self.model in m for m in model_names):
                    return True, f'Ollama running, {self.model} available'
                else:
                    return False, f'{self.model} not found. Available: {model_names}'
            else:
                return False, f'API error: {response.status_code}'
                
        except requests.exceptions.ConnectionError:
            return False, f'Cannot connect to {self.host}'
        except Exception as e:
            return False, f'Error: {str(e)}'
    
    def locate_object(self, image_base64: str, target_object: str,
                      img_width: int = 640, img_height: int = 480) -> Optional[Dict]:
        """
        Locate object in image and get its center coordinates
        
        Args:
            image_base64: Base64 encoded image
            target_object: Object to locate (e.g., "red dice")
            img_width: Actual image width in pixels
            img_height: Actual image height in pixels
            
        Returns:
            {
                "center": [x, y],
                "description": "...",
                "confidence": "high|medium|low"
            } or None if not found
        """
        self._log(f'Querying VLM to locate: {target_object}', 'debug')
        
        prompt = (
            f'In this image, I need to find the "{target_object}".\n'
            f'If you can see it, tell me:\n'
            f'1. Where is it located in the image? (describe position)\n'
            f'2. What are the approximate pixel coordinates of its center? '
            f'The image is {img_width}x{img_height} pixels.\n'
            f'Format your answer as: FOUND at pixel (x, y) - description\n'
            f'Example: FOUND at pixel (320, 240) - yellow dice on the right side\n'
            f'If you cannot find it, say: NOT FOUND'
        )
        
        result = self._query(prompt, image_base64, format_json=False)
        
        if result and 'response' in result:
            response_text = result['response']
            # total_duration = load_duration + prompt_eval_duration + eval_duration
            # For models split across CPU/GPU (like qwen2.5vl:32b at 137 GB),
            # load_duration captures the layer-shuffling overhead and is the dominant
            # cost — this is what accounts for the large gap vs eval_duration alone.
            eval_duration_ns = result.get('total_duration', 0)
            self._log(f'Raw VLM response: {response_text}', 'info')
            
            import re
            
            # Parse pixel coordinates — primary format is "pixel (x, y)"
            patterns = [
                r'pixel\s*\((\d+\.?\d*),\s*(\d+\.?\d*)\)',
                r'FOUND\s+at\s+\((\d+\.?\d*),\s*(\d+\.?\d*)\)',
                r'at\s*\((\d+\.?\d*),\s*(\d+\.?\d*)\)',
                r'\((\d+\.?\d*),\s*(\d+\.?\d*)\)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    fx, fy = float(match.group(1)), float(match.group(2))
                    # If the model returns fractions (≤ 1.0), scale to pixels
                    if fx <= 1.0 and fy <= 1.0:
                        x = int(fx * img_width)
                        y = int(fy * img_height)
                    else:
                        # Raw pixel coords — clamp to actual image bounds
                        x = max(0, min(img_width - 1, int(fx)))
                        y = max(0, min(img_height - 1, int(fy)))
                    return {
                        'center': [x, y],
                        'description': response_text[:150],
                        'confidence': 'high' if 'FOUND' in response_text.upper() else 'medium',
                        'eval_duration_ms': eval_duration_ns / 1e6
                    }
            
            # No coordinates found but object mentioned
            if target_object.lower() in response_text.lower() and 'not found' not in response_text.lower():
                return {
                    'center': None,
                    'description': response_text,
                    'confidence': 'low',
                    'eval_duration_ms': eval_duration_ns / 1e6
                }
            
            # Check if VLM explicitly said NOT FOUND
            if 'not found' in response_text.lower():
                return {
                    'center': None,
                    'description': response_text,
                    'confidence': 'none',
                    'not_found': True,
                    'eval_duration_ms': eval_duration_ns / 1e6
                }
        
        return None
    
    def ground_location(self, image_base64: str, location_description: str,
                       img_width: int = 640, img_height: int = 480) -> Optional[Dict]:
        """
        Ground a location description to pixel coordinates
        
        Args:
            image_base64: Base64 encoded image
            location_description: Location description (e.g., "left down side of the table", "next to the red cube")
            img_width: Actual image width in pixels
            img_height: Actual image height in pixels
            
        Returns:
            {
                "center": [x, y],
                "description": "...",
                "confidence": "high|medium|low"
            } or None if not found
        """
        self._log(f'Querying VLM to ground location: {location_description}', 'debug')
        
        prompt = (
            f'In this image, I need to find the location described as "{location_description}".\n'
            f'Look at the table and identify where this location is.\n'
            f'Tell me the approximate pixel coordinates of this location. '
            f'The image is {img_width}x{img_height} pixels.\n'
            f'Format your answer as: FOUND at pixel (x, y) - description\n'
            f'Example: FOUND at pixel (150, 350) - left down side of the table\n'
            f'If you cannot identify this location, say: NOT FOUND'
        )
        
        result = self._query(prompt, image_base64, format_json=False)
        
        if result and 'response' in result:
            response_text = result['response']
            eval_duration_ns = result.get('total_duration', 0)
            self._log(f'Raw VLM response: {response_text}', 'info')
            
            import re
            
            # Parse pixel coordinates
            patterns = [
                r'pixel\s*\((\d+\.?\d*),\s*(\d+\.?\d*)\)',
                r'FOUND\s+at\s+\((\d+\.?\d*),\s*(\d+\.?\d*)\)',
                r'at\s*\((\d+\.?\d*),\s*(\d+\.?\d*)\)',
                r'\((\d+\.?\d*),\s*(\d+\.?\d*)\)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    fx, fy = float(match.group(1)), float(match.group(2))
                    # If the model returns fractions (≤ 1.0), scale to pixels
                    if fx <= 1.0 and fy <= 1.0:
                        x = int(fx * img_width)
                        y = int(fy * img_height)
                    else:
                        # Raw pixel coords — clamp to actual image bounds
                        x = max(0, min(img_width - 1, int(fx)))
                        y = max(0, min(img_height - 1, int(fy)))
                    return {
                        'center': [x, y],
                        'description': response_text[:150],
                        'confidence': 'high' if 'FOUND' in response_text.upper() else 'medium',
                        'eval_duration_ms': eval_duration_ns / 1e6
                    }
        
        return None
    
    def describe_scene(self, image_base64: str) -> Optional[str]:
        """
        Get general scene description
        
        Args:
            image_base64: Base64 encoded image
            
        Returns:
            Description string or None
        """
        self._log('Querying VLM for scene description', 'debug')
        
        prompt = (
            'Analyze this table scene and describe what objects are on the table. '
            'Be specific about:\n'
            '1. What objects are present\n'
            '2. Their locations (left, center, right, front, back)\n'
            '3. Their colors and sizes\n'
            '4. Overall arrangement\n'
            'Be concise but informative.'
        )
        
        result = self._query(prompt, image_base64, format_json=False)
        return result.get('response') if result else None
    
    def _query(self, prompt: str, image_base64: str, format_json: bool = False) -> Optional[Dict]:
        """
        Internal method to query Ollama API
        
        Args:
            prompt: Text prompt
            image_base64: Base64 encoded image
            format_json: Whether to request JSON format response
            
        Returns:
            Parsed response or None
        """
        try:
            payload = {
                'model': self.model,
                'prompt': prompt,
                'images': [image_base64],
                'stream': False,
                'temperature': self.temperature,
            }
            
            if format_json:
                payload['format'] = 'json'
            
            self._log(f'Sending request to {self.host}/api/generate', 'debug')
            self._log(f'Model: {self.model}, Temperature: {self.temperature}', 'debug')
            
            response = requests.post(
                f'{self.host}/api/generate',
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if format_json:
                    # Parse JSON response
                    vlm_response = result.get('response', '{}')
                    self._log(f'VLM raw response: {vlm_response[:200]}...', 'debug')
                    try:
                        parsed = json.loads(vlm_response)
                        self._log(f'VLM parsed: {parsed}', 'debug')
                        return parsed
                    except json.JSONDecodeError as e:
                        self._log(f'JSON decode error: {e}', 'error')
                        return None
                else:
                    # Return full response
                    return result
            else:
                self._log(f'API error {response.status_code}: {response.text}', 'error')
                return None
                
        except requests.exceptions.Timeout:
            self._log(f'Request timeout after {self.timeout}s', 'error')
            return None
        except requests.exceptions.ConnectionError:
            self._log(f'Cannot connect to {self.host}', 'error')
            return None
        except Exception as e:
            self._log(f'Error in query: {str(e)}', 'error')
            return None
