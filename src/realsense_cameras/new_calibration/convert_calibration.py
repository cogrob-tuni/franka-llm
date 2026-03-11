#!/usr/bin/env python3
"""
Convert old pickle calibration files to new numpy version
Run this if you get numpy compatibility errors
"""

import pickle
import numpy as np
import sys

print("Converting calibration pickle files to current numpy version...")
print(f"Current NumPy version: {np.__version__}")

# Try to load with allow_pickle and fix_imports
def load_old_pickle(filename):
    """Try multiple methods to load old pickle files"""
    methods = [
        lambda f: pickle.load(f),
        lambda f: pickle.load(f, fix_imports=True),
        lambda f: pickle.load(f, encoding='latin1'),
        lambda f: pickle.load(f, fix_imports=True, encoding='latin1'),
    ]
    
    for i, method in enumerate(methods, 1):
        try:
            with open(filename, 'rb') as f:
                data = method(f)
            print(f"Loaded {filename} with method {i}")
            return data
        except Exception as e:
            if i == len(methods):
                print(f"Failed to load {filename}: {e}")
                return None
            continue

# Load old files
rotation_vector = load_old_pickle('rotation_vector.pkl')
translation_vector = load_old_pickle('translational_vector.pkl')

if rotation_vector is None or translation_vector is None:
    print("\nCould not load calibration files!")
    print("You need to re-run camera_calibration.py to generate new files.")
    sys.exit(1)

# Convert to current numpy arrays
rotation_vector = np.array(rotation_vector, dtype=np.float64)
translation_vector = np.array(translation_vector, dtype=np.float64)

print(f"\nRotation vector shape: {rotation_vector.shape}")
print(f"Translation vector shape: {translation_vector.shape}")
print(f"Rotation values: {rotation_vector.squeeze()}")
print(f"Translation values: {translation_vector.squeeze()}")

# Save with current numpy version
with open('rotation_vector.pkl', 'wb') as f:
    pickle.dump(rotation_vector, f, protocol=pickle.HIGHEST_PROTOCOL)

with open('translational_vector.pkl', 'wb') as f:
    pickle.dump(translation_vector, f, protocol=pickle.HIGHEST_PROTOCOL)

print("\nCalibration files converted successfully!")
print("You can now run test_transform.py")
