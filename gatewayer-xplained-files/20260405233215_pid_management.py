
PID_FILE = "agent.pid"

def write_pid_file():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

def remove_pid_file():
    for _attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
