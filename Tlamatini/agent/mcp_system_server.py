
import asyncio
import json
import websockets
import os
from datetime import datetime
import shutil
import subprocess
import platform
import ctypes

class MCPSystemHandler:
    def __init__(self):
        self.resources = { # Example static hardcoded resources...
            "cpu_usage": 45.2,
            "memory_usage": 68.7,
            "disk_space": 256.5,
        }

    def _format_value_with_units(self, key, value):
        try:
            if key in ("cpu_usage", "memory_usage"):
                return f"{float(value):.1f}%"
            if key == "disk_space":
                return f"{float(value):.1f} GB"
        except Exception:
            # If formatting fails, return as-is
            return value
        return value

    async def grab_resources(self):
        """Grab resources from the system"""
        # Run the potentially blocking system calls in a thread to avoid blocking the event loop
        def compute_resources():
            updated = dict(self.resources)

            # Try to prefer psutil if available for cross-platform metrics
            def cpu_percent_fallback(default_value: float) -> float:
                # Windows: use typeperf to sample CPU percentage once
                if platform.system().lower().startswith("win"):
                    try:
                        result = subprocess.run(
                            ["typeperf", r"\Processor(_Total)\% Processor Time", "-sc", "1"],
                            capture_output=True,
                            text=True,
                            timeout=4,
                        )
                        # Output example:
                        # "Time","\MACHINE\processor(_total)\% Processor Time"
                        # "11/08/2025 15:32:23.123","5.026774"
                        for line in result.stdout.splitlines():
                            line = line.strip()
                            if line.startswith('"') and "," in line:
                                last = line.split(",")[-1].strip().strip('"')
                                return round(float(last), 1)
                    except Exception:
                        pass
                # Linux/Mac fallback attempts could be added here if needed
                return default_value

            def memory_percent_fallback(default_value: float) -> float:
                # Use Windows GlobalMemoryStatusEx via ctypes when available
                try:
                    if platform.system().lower().startswith("win"):
                        class MEMORYSTATUSEX(ctypes.Structure):
                            _fields_ = [
                                ("dwLength", ctypes.c_ulong),
                                ("dwMemoryLoad", ctypes.c_ulong),
                                ("ullTotalPhys", ctypes.c_ulonglong),
                                ("ullAvailPhys", ctypes.c_ulonglong),
                                ("ullTotalPageFile", ctypes.c_ulonglong),
                                ("ullAvailPageFile", ctypes.c_ulonglong),
                                ("ullTotalVirtual", ctypes.c_ulonglong),
                                ("ullAvailVirtual", ctypes.c_ulonglong),
                                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                            ]
                        stat = MEMORYSTATUSEX()
                        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                            return round(float(stat.dwMemoryLoad), 1)
                except Exception:
                    pass
                return default_value

            def disk_free_gb_fallback(default_value: float) -> float:
                try:
                    # Check free space on the root of the current drive
                    drive, _ = os.path.splitdrive(os.getcwd())
                    root = (drive + os.sep) if drive else os.sep
                    usage = shutil.disk_usage(root)
                    free_gb = usage.free / (1024 ** 3)
                    return round(float(free_gb), 1)
                except Exception:
                    return default_value

            # Defaults if everything fails
            default_cpu = float(updated.get("cpu_usage", 0.0))
            default_mem = float(updated.get("memory_usage", 0.0))
            default_disk = float(updated.get("disk_space", 0.0))

            # Attempt psutil first for CPU and memory; fall back if not available
            cpu_percent = default_cpu
            mem_percent = default_mem
            try:
                import psutil  # type: ignore
                cpu_percent = round(float(psutil.cpu_percent(interval=0.2)), 1)
                mem_percent = round(float(psutil.virtual_memory().percent), 1)
            except Exception:
                cpu_percent = cpu_percent_fallback(default_cpu)
                mem_percent = memory_percent_fallback(default_mem)

            # Disk free GB via psutil if present, else shutil
            disk_free_gb = default_disk
            try:
                try:
                    import psutil  # type: ignore
                    drive, _ = os.path.splitdrive(os.getcwd())
                    root = (drive + os.sep) if drive else os.sep
                    du = psutil.disk_usage(root)
                    disk_free_gb = round(float(du.free) / (1024 ** 3), 1)
                except Exception:
                    disk_free_gb = disk_free_gb_fallback(default_disk)
            except Exception:
                disk_free_gb = default_disk

            updated["cpu_usage"] = cpu_percent
            updated["memory_usage"] = mem_percent
            updated["disk_space"] = disk_free_gb
            return updated

        if hasattr(asyncio, "to_thread"):
            updated_resources = await asyncio.to_thread(compute_resources)
        else:
            loop = asyncio.get_running_loop()
            updated_resources = await loop.run_in_executor(None, compute_resources)

        self.resources = updated_resources
        return updated_resources
    
    async def handle_request(self, request):
        try:
            data = json.loads(request)
            operation = data.get("operation")
            params = data.get("params", {})

            print("LLM is grabbing system metrics...\nActual system metrics:", self.resources)
            self.resources = await self.grab_resources()
            print("LLM has grabbed system metrics...\nActual system metrics:", self.resources)
            
            if operation == "get_resource":
                resource = params.get("resource")
                if resource in self.resources:
                    formatted = self._format_value_with_units(resource, self.resources[resource])
                    return {"status": "success", "data": {resource: formatted}}
                else:
                    return {"status": "error", "message": "Resource not found"}
            
            elif operation == "list_resources":
                return {
                    "status": "success",
                    "data": list(self.resources.keys())
                }
            
            elif operation == "update_resource":
                resource = params.get("resource")
                value = params.get("value")
                if resource in self.resources:
                    self.resources[resource] = value
                    return {"status": "success", "message": f"Updated {resource}"}
                else:
                    return {"status": "error", "message": "Resource not found"}
            
            elif operation == "get_system_time":
                return {
                    "status": "success",
                    "data": {"time": datetime.now().isoformat()}
                }
            
            else:
                return {"status": "error", "message": "Unknown operation"}
                
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

async def system_handler(websocket):
    """WebSocket handler - compatible with newer websockets library"""
    mcp = MCPSystemHandler()
    try:
        async for message in websocket:
            response = await mcp.handle_request(message)
            await websocket.send(json.dumps(response))
    except websockets.exceptions.ConnectionClosed:
        # Client disconnected, this is normal
        pass
    except Exception as e:
        print(f"Error in handler: {e}")

async def main(config_path=None):
    # Load server configuration from config.json
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")

    with open(config_path, 'r') as f:
        config = json.load(f)

    host = config.get("mcp_system_server_host", "127.0.0.1")
    port = config.get("mcp_system_server_port", 8765)

    server = await websockets.serve(system_handler, host, port)
    print(f"MCP Server started on ws://{host}:{port}")
    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.close()
        await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
