#!/usr/bin/env python3
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.webviz.server import run

if __name__ == "__main__":
    run("127.0.0.1", 8000)