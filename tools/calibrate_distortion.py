#!/usr/bin/env python3
"""
Interactive distortion calibration tool for yacht parking assistant.

This tool helps find the optimal k1 and k2 distortion coefficients
by allowing real-time adjustment while viewing the video stream.

The goal is to make straight lines (door frames, yacht hulls, masts)
appear straight in the output video for accurate human perception.

Usage:
    # Run with current pipeline settings
    python src/tools/calibrate_distortion.py

    # Start with specific k1 value
    CAM_DISTORTION_K1=-0.3 python src/tools/calibrate_distortion.py

    # Interactive controls:
    #   UP/DOWN arrows: Adjust k1 by ±0.05
    #   LEFT/RIGHT arrows: Adjust k1 by ±0.01 (fine tune)
    #   PAGE_UP/PAGE_DOWN: Adjust k2 by ±0.05
    #   HOME/END: Adjust k2 by ±0.01 (fine tune)
    #   SPACE: Print current values
    #   S: Save current values to .env file
    #   R: Reset to defaults (k1=-0.2, k2=0.0)
    #   Q/ESC: Quit

Visual Guide:
    - If straight lines curve INWARD (barrel): Decrease k1 (more negative)
    - If straight lines curve OUTWARD (pincushion): Increase k1 (less negative)
    - k2 handles higher-order distortion (usually keep at 0.0)
"""

import sys
import os
from pathlib import Path

# Add parent directory to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

print("""
╔═══════════════════════════════════════════════════════════════╗
║         Interactive Distortion Calibration Tool              ║
║                Yacht Parking Assistant                        ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  Goal: Make straight lines appear straight in video stream   ║
║                                                               ║
║  CONTROLS:                                                    ║
║    ↑/↓        Adjust k1 by ±0.05                             ║
║    ←/→        Adjust k1 by ±0.01 (fine)                      ║
║    PgUp/PgDn  Adjust k2 by ±0.05                             ║
║    Home/End   Adjust k2 by ±0.01 (fine)                      ║
║    SPACE      Print current values                           ║
║    S          Save to environment variable commands          ║
║    R          Reset to defaults                              ║
║    Q/ESC      Quit                                            ║
║                                                               ║
║  TIPS:                                                        ║
║    • Look at door frames, window edges, walls                ║
║    • Lines curve inward? → More negative k1                  ║
║    • Lines curve outward? → Less negative k1                 ║
║    • Usually k2 can stay at 0.0                              ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
""")

# Get current distortion values
current_k1 = float(os.getenv('CAM_DISTORTION_K1', '-0.2'))
current_k2 = float(os.getenv('CAM_DISTORTION_K2', '0.0'))

print(f"\nStarting values:")
print(f"  k1 = {current_k1:.3f}")
print(f"  k2 = {current_k2:.3f}")
print("\nTo apply these values, run:")
print(f"  export CAM_DISTORTION_K1={current_k1}")
print(f"  export CAM_DISTORTION_K2={current_k2}")
print(f"  python src/i_can_see.py")

print("\n" + "="*60)
print("INTERACTIVE MODE")
print("="*60)
print("\nThis tool provides a framework for interactive calibration.")
print("For full interactivity, this needs to be integrated with the")
print("live GStreamer pipeline with keyboard event handling.")
print("\nCurrent approach: Iterative testing")
print("\n1. Observe the current output video")
print("2. Decide adjustment needed based on line curvature")
print("3. Set new values via environment variables")
print("4. Restart pipeline and repeat")

def print_adjustment_guide():
    """Print visual guide for distortion adjustment."""
    print("\n" + "="*60)
    print("DISTORTION ADJUSTMENT GUIDE")
    print("="*60)
    print("""
Barrel Distortion (lines curve inward):
    |  )        → Decrease k1 (more negative)
    | (         Example: -0.2 → -0.3
    |  )

Pincushion Distortion (lines curve outward):
    | (         → Increase k1 (less negative)
    |  )        Example: -0.2 → -0.1
    | (

No Distortion (ideal):
    |           → Current k1 is optimal
    |
    |

Typical values:
  Wide angle cameras: k1 = -0.1 to -0.4 (barrel)
  Normal lenses:      k1 = -0.05 to +0.05
  Telephoto lenses:   k1 = 0.0 to +0.2 (pincushion)

For Radxa 4K cameras (75° FOV):
  Expected range: k1 = -0.15 to -0.3
  Start value:    k1 = -0.2
""")

def save_calibration(k1: float, k2: float):
    """Save calibration values to commands for easy copying."""
    print("\n" + "="*60)
    print("SAVE CALIBRATION VALUES")
    print("="*60)
    print("\nRun these commands to apply calibration:\n")
    print(f"export CAM_DISTORTION_K1={k1:.3f}")
    print(f"export CAM_DISTORTION_K2={k2:.3f}")
    print(f"python src/i_can_see.py")
    print("\nOr add to your .env file:")
    print(f"CAM_DISTORTION_K1={k1:.3f}")
    print(f"CAM_DISTORTION_K2={k2:.3f}")

    # Optionally write to a calibration file
    cal_file = Path("config/distortion_calibration.txt")
    cal_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cal_file, 'w') as f:
        f.write(f"# Distortion calibration for yacht parking assistant\n")
        f.write(f"# Generated by calibrate_distortion.py\n")
        f.write(f"export CAM_DISTORTION_K1={k1:.3f}\n")
        f.write(f"export CAM_DISTORTION_K2={k2:.3f}\n")

    print(f"\n✓ Saved to {cal_file}")

def interactive_calibration():
    """Interactive calibration loop."""
    k1 = current_k1
    k2 = current_k2

    print("\nStarting interactive calibration...")
    print_adjustment_guide()

    print("\n" + "="*60)
    print("CALIBRATION WORKFLOW")
    print("="*60)
    print("""
Step 1: Observe current distortion
  • Run the pipeline and look at straight edges
  • Door frames, window edges, and walls are good references

Step 2: Determine adjustment direction
  • Lines curve inward (barrel)? → More negative k1
  • Lines curve outward (pincushion)? → Less negative k1

Step 3: Apply new values and test
  • Use commands below to set new k1 value
  • Restart pipeline and observe
  • Iterate until lines are straight

Step 4: Fine-tune
  • Make smaller adjustments (±0.01)
  • Verify across entire frame (center and edges)

Step 5: Save final values
  • Document the optimal k1 and k2
  • Add to configuration management
""")

    print("\nEnter commands (h for help, q to quit):")

    while True:
        try:
            cmd = input(f"\nk1={k1:.3f}, k2={k2:.3f} > ").strip().lower()

            if not cmd:
                continue

            if cmd in ['q', 'quit', 'exit']:
                print("Exiting calibration tool.")
                break

            elif cmd == 'h' or cmd == 'help':
                print("\nCommands:")
                print("  ++      Increase k1 by 0.05")
                print("  +       Increase k1 by 0.01")
                print("  --      Decrease k1 by 0.05")
                print("  -       Decrease k1 by 0.01")
                print("  k2++    Increase k2 by 0.05")
                print("  k2+     Increase k2 by 0.01")
                print("  k2--    Decrease k2 by 0.05")
                print("  k2-     Decrease k2 by 0.01")
                print("  set K1  Set k1 to specific value")
                print("  r       Reset to defaults")
                print("  s       Save current values")
                print("  p       Print current values")
                print("  g       Show adjustment guide")
                print("  q       Quit")

            elif cmd == '++':
                k1 += 0.05
                print(f"k1 increased to {k1:.3f}")

            elif cmd == '+':
                k1 += 0.01
                print(f"k1 increased to {k1:.3f}")

            elif cmd == '--':
                k1 -= 0.05
                print(f"k1 decreased to {k1:.3f}")

            elif cmd == '-':
                k1 -= 0.01
                print(f"k1 decreased to {k1:.3f}")

            elif cmd == 'k2++':
                k2 += 0.05
                print(f"k2 increased to {k2:.3f}")

            elif cmd == 'k2+':
                k2 += 0.01
                print(f"k2 increased to {k2:.3f}")

            elif cmd == 'k2--':
                k2 -= 0.05
                print(f"k2 decreased to {k2:.3f}")

            elif cmd == 'k2-':
                k2 -= 0.01
                print(f"k2 decreased to {k2:.3f}")

            elif cmd.startswith('set '):
                try:
                    val = float(cmd.split()[1])
                    k1 = val
                    print(f"k1 set to {k1:.3f}")
                except (IndexError, ValueError):
                    print("Invalid value. Usage: set -0.25")

            elif cmd == 'r' or cmd == 'reset':
                k1 = -0.2
                k2 = 0.0
                print("Reset to defaults: k1=-0.2, k2=0.0")

            elif cmd == 's' or cmd == 'save':
                save_calibration(k1, k2)

            elif cmd == 'p' or cmd == 'print':
                print(f"\nCurrent values:")
                print(f"  CAM_DISTORTION_K1={k1:.3f}")
                print(f"  CAM_DISTORTION_K2={k2:.3f}")
                print(f"\nTo test:")
                print(f"  export CAM_DISTORTION_K1={k1:.3f}")
                print(f"  export CAM_DISTORTION_K2={k2:.3f}")
                print(f"  python src/i_can_see.py")

            elif cmd == 'g' or cmd == 'guide':
                print_adjustment_guide()

            else:
                print(f"Unknown command: {cmd}")
                print("Type 'h' for help")

        except KeyboardInterrupt:
            print("\n\nInterrupted. Saving current values...")
            save_calibration(k1, k2)
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    try:
        interactive_calibration()
    except KeyboardInterrupt:
        print("\n\nCalibration tool terminated.")
        sys.exit(0)
