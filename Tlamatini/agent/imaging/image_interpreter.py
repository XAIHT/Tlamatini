import os
import json
import sys
import requests
from langchain.tools import tool
from .converter import convert_image_to_base64

def _get_config():
    """
    Robustly locates and loads the config.json file.
    
    Search Order:
    1. Frozen (PyInstaller): Directory of executable.
    2. Frozen (PyInstaller): 'agent' subdirectory of executable.
    3. Frozen (PyInstaller): _MEIPASS (temp dir) 'agent' subdirectory.
    4. Dev: Relative path '../config.json' from this file.
    """
    candidate_paths = []
    
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
        candidate_paths.append(os.path.join(base_dir, 'config.json'))
        candidate_paths.append(os.path.join(base_dir, 'agent', 'config.json'))
        
        if hasattr(sys, '_MEIPASS'):
             candidate_paths.append(os.path.join(sys._MEIPASS, 'agent', 'config.json'))
             
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_paths.append(os.path.abspath(os.path.join(current_dir, '..', 'config.json')))

    for path in candidate_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config
            except Exception:
                continue
    
    return {}

@tool
def opus_analyze_image(image_path: str = None, prompt: str = "Describe this image in detail.") -> str:
    """
    Analyzes and describes with Opus model the details of an image and returns a description based on the prompt using this tool.

    Examples of what to pass:
    - User says "Describe with Opus the image whatever.jpg located at desktop" → Check the 'Files Context' (if available) to see if 'whatever.jpg' was found. If yes, pass the full path found (e.g. C:\\Users\\User\\Desktop\\whatever.jpg), and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe with Opus the image whatever.jpg located at u:\\path\\filename.png" → Pass the provided path "u:\\path\\filename.png", and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe with Opus the image whatever.jpg" → Check the 'Files Context'. If 'whatever.jpg' is listed there with a full path, pass that full path (e.g. C:\\Data\\images\\whatever.jpg). If not found, pass "whatever.jpg", and pass the prompt adapted by you, depending on the user prompt
    - User says "Describe with Opus the image path\\agent.jpg" → pass the complete path of the image (path\\agent.jpg) and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe with Opus the image <image_name> located at <path>" → pass the <path>\\<image_name> and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe with Opus the image cat.gif" → pass only the image name (cat.gif), and pass the prompt adapted by you, depending on the user prompt.   

    Args:
        image_path (str, optional): The file-path to the image to analyze. If None, uses config value.
        prompt (str): The question or instruction for the model regarding the image. Defaults to "Describe this image in detail.".

    Returns:
        str: The model's response describing in detail the image.
    """
    # Import the ClaudeClient from the opus_client module
    try:
        from agent.opus_client.claude_opus_client import ClaudeClient
    except ImportError:
        try:
            from opus_client.claude_opus_client import ClaudeClient
        except ImportError:
            # Fallback for running directly
            import sys as _sys
            from pathlib import Path as _Path
            _parent = _Path(__file__).resolve().parent.parent
            if str(_parent) not in _sys.path:
                _sys.path.insert(0, str(_parent))
            from opus_client.claude_opus_client import ClaudeClient
    
    print("\n--- [Image Interpreter] opus_analyze_image tool invoked ---")
    print(f"--- [Image Interpreter] image_path argument: {image_path}")
    print(f"--- [Image Interpreter] prompt argument: {prompt}")
    
    try:
        config = _get_config()
        print(f"--- [Image Interpreter] Config loaded successfully. Keys: {list(config.keys())}")
    except Exception as e:
        print(f"--- [Image Interpreter] ERROR loading config: {str(e)}")
        return f"Error loading config: {str(e)}"
    
    # Get ANTHROPIC_API_KEY from config
    api_key = config.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("--- [Image Interpreter] ERROR: ANTHROPIC_API_KEY not found in config.json")
        return "Error: ANTHROPIC_API_KEY not found in config.json. Please add your API key."
    else:
        print(f"--- [Image Interpreter] ANTHROPIC_API_KEY found (length: {len(api_key)})")
    
    target_image_path = image_path
    if not target_image_path:
        target_image_path = config.get("image_interpreter_image_path", "")
        print(f"--- [Image Interpreter] Using config default image path: {target_image_path}")
    
    print(f"--- [Image Interpreter] Target image path: {target_image_path}")
    if not target_image_path or not os.path.exists(target_image_path):
        print(f"--- [Image Interpreter] ERROR: Image file not found at {target_image_path}")
        return f"Error: Image file not found at {target_image_path}"

    try:
        print("\n--- [Image Interpreter] Analyzing image with Claude Opus... ---")
        print(f"Image path: {target_image_path}")
        print(f"Prompt: {prompt}")
        
        # Create the Claude client with the API key from config
        client = ClaudeClient(api_key=api_key)
        
        # Use chat_with_image to analyze the image (same pattern as example_image_analysis)
        response = client.chat_with_image(
            message=prompt,
            image=target_image_path
        )
        
        print("\n--- [Image Interpreter] Analysis Complete ---\n")
        
        return response
    except FileNotFoundError as e:
        return f"Error: Image file not found - {str(e)}"
    except ValueError as e:
        return f"Error: Invalid image format - {str(e)}"
    except ConnectionError as e:
        return f"Error: Could not connect to Anthropic API - {str(e)}"
    except Exception as e:
        return f"Error analyzing image: {str(e)}"

@tool
def qwen_analyze_image(image_path: str = None, prompt: str = "Describe this image in detail.") -> str:
    """
    Analyzes and describes with Qwen model the details of an image and returns a description based on the prompt using this tool.

    Examples of what to pass:
    - User says "Describe the image whatever.jpg located at desktop" → Check the 'Files Context' (if available) to see if 'whatever.jpg' was found. If yes, pass the full path found (e.g. C:\\Users\\User\\Desktop\\whatever.jpg), and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe with Qwen the image whatever.jpg located at desktop" → Check the 'Files Context' (if available) to see if 'whatever.jpg' was found. If yes, pass the full path found (e.g. C:\\Users\\User\\Desktop\\whatever.jpg), and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe the image whatever.jpg located at u:\\path\\filename.png" → Pass the provided path "u:\\path\\filename.png", and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe with Qwen the image whatever.jpg located at u:\\path\\filename.png" → Pass the provided path "u:\\path\\filename.png", and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe the image whatever.jpg" → Check the 'Files Context'. If 'whatever.jpg' is listed there with a full path, pass that full path (e.g. C:\\Data\\images\\whatever.jpg). If not found, pass "whatever.jpg", and pass the prompt adapted by you, depending on the user prompt
    - User says "Describe with Qwen the image whatever.jpg" → Check the 'Files Context'. If 'whatever.jpg' is listed there with a full path, pass that full path (e.g. C:\\Data\\images\\whatever.jpg). If not found, pass "whatever.jpg", and pass the prompt adapted by you, depending on the user prompt
    - User says "Describe the image path\\agent.jpg" → pass the complete path of the image (path\\agent.jpg) and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe with Qwen the image path\\agent.jpg" → pass the complete path of the image (path\\agent.jpg) and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe the image <image_name> located at <path>" → pass the <path>\\<image_name> and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe with Qwen the image <image_name> located at <path>" → pass the <path>\\<image_name> and pass the prompt adapted by you, depending on the user prompt.
    - User says "Describe the image cat.gif" → pass only the image name (cat.gif), and pass the prompt adapted by you, depending on the user prompt.       
    - User says "Describe with Qwen the image cat.gif" → pass only the image name (cat.gif), and pass the prompt adapted by you, depending on the user prompt.   

    Args:
        image_path (str, optional): The file-path to the image to analyze. If None, uses config value.
        prompt (str): The question or instruction for the model regarding the image. Defaults to "Describe this image in detail.".

    Returns:
        str: The model's response describing in detail the image by a Qwen model.
    """
    
    try:
        config = _get_config()
    except Exception as e:
        return f"Error loading config: {str(e)}"
    base_url = config.get("image_interpreter_base_url", "http://localhost:11434").rstrip('/')
    model = config.get("image_interpreter_model", "llama3.2-vision:11b")
    
    target_image_path = image_path
    if not target_image_path:
        target_image_path = config.get("image_interpreter_image_path", "")
    
    if not target_image_path or not os.path.exists(target_image_path):
        return f"Error: Image file not found at {target_image_path}"

    try:
        image_base64 = convert_image_to_base64(target_image_path)
        if not image_base64:
            return "Error: Failed to convert image to base64"
        else:
            print(f"Image converted to base64, size: {len(image_base64)} bytes.")
        
        full_content = prompt

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": full_content,
                    "images": [image_base64]
                }
            ],
            "stream": True,
            "options": {
                "temperature": 0.0,
                "num_ctx": 32768,
                "repeat_penalty": 1.85,
                "top_p": 0.95,
                "top_k": 50,
                "stop": ["<|end_of_text|>", "<|eot_id|>", "assistant", "</html>", "</body>"]
            }
        }

        print(f"\n--- [Image Interpreter] Sending request to {model}... ---")
        
        headers = {}
        token = config.get("ollama_token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.post(f"{base_url}/api/chat", json=payload, headers=headers, stream=True)
        response.raise_for_status()
        full_description = []
        print("--- [Image Interpreter] Streaming Response: ---")
        
        for line in response.iter_lines():
            if line:
                try:
                    json_chunk = json.loads(line.decode('utf-8'))
                    content = ""
                    if "message" in json_chunk:
                        content = json_chunk["message"].get("content", "")
                    elif "response" in json_chunk:
                        content = json_chunk.get("response", "")
                    
                    if content:
                        print(content, end="", flush=True)
                        
                    full_description.append(content)
                    
                    if json_chunk.get("done", False):
                        print("\n--- [Image Interpreter] Stream Complete ---\n")
                except json.JSONDecodeError:
                    continue

        return "".join(full_description)
    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to Ollama at {base_url}. Check if the server is running."
    except Exception as e:
        return f"Error analyzing image: {str(e)}"
