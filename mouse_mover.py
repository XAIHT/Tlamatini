import pyautogui
import time
import random
import math

# Optional: Add a fail-safe (moving your mouse to any of the 4 corners of the screen will raise an exception and stop the script)
pyautogui.FAILSAFE = True

def move_mouse_human_like():
    print("Mouse mover started. Press Ctrl+C to stop. Move mouse to a corner to trigger fail-safe.")
    
    try:
        while True:
            # Get current screen resolution
            screen_width, screen_height = pyautogui.size()
            
            # Generate a random destination on the screen
            target_x = random.randint(100, screen_width - 100)
            target_y = random.randint(100, screen_height - 100)
            
            # Generate a random duration for the movement (makes it look more human)
            # A duration between 0.5 and 2.0 seconds
            duration = random.uniform(0.5, 2.0)
            
            # Use PyAutoGUI's ease-in-out tweening to make the movement look natural (accelerating and decelerating)
            pyautogui.moveTo(
                target_x, 
                target_y, 
                duration=duration, 
                tween=pyautogui.easeInOutQuad
            )
            
            print(f"Moved mouse to ({target_x}, {target_y})")
            
            # Wait for a random amount of time before moving again (e.g., 2 to 10 seconds)
            sleep_time = random.uniform(2.0, 10.0)
            print(f"Waiting for {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        print("\nScript manually stopped by user.")
    except pyautogui.FailSafeException:
        print("\nFail-safe triggered! Mouse was moved to a screen corner. Stopping script.")

if __name__ == "__main__":
    # Give the user a brief moment before it starts
    time.sleep(2)
    move_mouse_human_like()
