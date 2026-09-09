"""
main.py - Single-Command Launch Entry Point for AURA-PHEV Smart Dashboard
Starts the simulation physics engine, real-time virtual CAN-FD bus,
and automatically opens the interactive digital dashboard in your browser.
"""

import sys
import os

# Ensure project root is in Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from server import run_server

if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("   AURA-PHEV // SMART HYBRID EMBEDDED DASHBOARD & SIMULATION")
    print("=" * 70)
    print(" - Physics Rate      : 50 Hz (20ms step)")
    print(" - Virtual CAN-FD    : 500 kbps (Arbitration IDs 0x100 - 0x7E0)")
    print(" - Auto-Opening      : Launching your default web browser...")
    print("=" * 70 + "\n")

    run_server()