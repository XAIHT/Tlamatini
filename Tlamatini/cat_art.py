
import os
import sys
import time

# Determine the clear screen command based on the operating system
CLEAR_CMD = "cls" if os.name == "nt" else "clear"

# List of ASCII‑art cat frames
FRAMES = [
    r"""
 /\_/\  
( o.o ) 
 > ^ <  
""",
    r"""
 /\_/\  
( -.- ) 
 > ^ <  
""",
    r"""
 /\_/\  
( o.o ) 
 > ^ <  
""",
    r"""
 /\_/\  
( ^.^ ) 
 > ^ <  
""",
]

def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system(CLEAR_CMD)

def animate(frames, delay=0.3, repeat=True):
    """Display the frames as an animation."""
    try:
        while True:
            for frame in frames:
                clear_screen()
                print(frame)
                time.sleep(delay)
            if not repeat:
                break
    except KeyboardInterrupt:
        # Graceful exit on Ctrl‑C
        clear_screen()
        sys.exit(0)

if __name__ == "__main__":
    # Adjust the delay (seconds) between frames here
    frame_delay = 0.4
    animate(FRAMES, delay=frame_delay)
