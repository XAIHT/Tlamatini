
import asyncio
import json
import websockets
import os

class MCPSystemClient:
    def __init__(self, uri=None, config_path=None):
        if uri is None:
            # Load URI from config.json
            if config_path is None:
                config_path = os.path.join(os.path.dirname(__file__), "config.json")

            with open(config_path, 'r') as f:
                config = json.load(f)

            self.uri = config.get("mcp_system_client_uri", "ws://127.0.0.1:8765")
        else:
            self.uri = uri

        self.websocket = None
    
    async def connect(self):
        """Establish connection to MCP server"""
        try:
            self.websocket = await websockets.connect(self.uri)
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    async def disconnect(self):
        """Close connection to MCP server"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
    
    async def _send_request(self, operation, params=None):
        """Send request to MCP server and return response"""
        if not self.websocket:
            raise Exception("Not connected to server")
        
        request = {
            "operation": operation,
            "params": params or {}
        }
        
        await self.websocket.send(json.dumps(request))
        response = await self.websocket.recv()
        return json.loads(response)
    
    async def get_resource(self, resource_name):
        """Get a specific resource value"""
        response = await self._send_request("get_resource", {"resource": resource_name})
        if response["status"] == "success":
            return response["data"][resource_name]
        else:
            raise Exception(response["message"])
    
    async def list_resources(self):
        """List all available resources"""
        response = await self._send_request("list_resources")
        if response["status"] == "success":
            return response["data"]
        else:
            raise Exception(response["message"])
    
    async def update_resource(self, resource_name, value):
        """Update a resource value"""
        response = await self._send_request("update_resource", {
            "resource": resource_name,
            "value": value
        })
        if response["status"] == "success":
            return response["message"]
        else:
            raise Exception(response["message"])
    
    async def get_system_time(self):
        """Get current system time from server"""
        response = await self._send_request("get_system_time")
        if response["status"] == "success":
            return response["data"]["time"]
        else:
            raise Exception(response["message"])

# Example usage
async def example():
    client = MCPSystemClient()
    
    if await client.connect():
        try:
            # List available resources
            resources = await client.list_resources()
            print(f"Available resources: {resources}")
            
            # Get a specific resource
            cpu = await client.get_resource("cpu_usage")
            print(f"CPU Usage: {cpu}%")
            
            # Update a resource
            await client.update_resource("cpu_usage", 55.5)
            print("Updated CPU usage")
            
            # Get system time
            time = await client.get_system_time()
            print(f"Server time: {time}")

            network_status = await client.get_resource("network_status")
            print(f"Network status: {network_status}")
            
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await client.disconnect()

if __name__ == "__main__":
    asyncio.run(example())
