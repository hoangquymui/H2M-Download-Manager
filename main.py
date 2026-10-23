"""Main launcher script for HDM (H2M Download Manager).
"""

import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hdm.app import main

if __name__ == "__main__":
    main()
