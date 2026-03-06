# Claude Opus 4.5 Python Client

A comprehensive, production-ready Python client for interacting with Claude Opus 4.5 via the Anthropic API. Supports text, images, PDFs, tools/functions, streaming, and conversation management.

## Installation

```bash
# Required
pip install anthropic

# Optional (for image resizing and additional features)
pip install httpx pillow
```

## Quick Start

```python
from claude_opus_client import ClaudeClient

# Initialize (uses ANTHROPIC_API_KEY env var by default)
client = ClaudeClient()

# Simple chat
response = client.chat("Explain quantum computing")
print(response)
```

## Features

### 1. Basic Chat

```python
from claude_opus_client import ClaudeClient, Model

client = ClaudeClient(
    api_key="your-api-key",  # or set ANTHROPIC_API_KEY env var
    model=Model.OPUS_4_5,    # Claude Opus 4.5 is the default
    max_tokens=4096,
    temperature=0.7
)

response = client.chat("What is machine learning?")
```

### 2. System Prompts

```python
# Set at client level
client = ClaudeClient(
    system_prompt="You are a helpful coding assistant."
)

# Or override per request
response = client.chat(
    "Help me with Python",
    system="You are an expert Python developer."
)
```

### 3. Image Analysis

```python
# From local file
response = client.chat_with_image(
    "Describe what you see",
    "/path/to/image.jpg"
)

# From URL
response = client.chat_with_image(
    "What's in this image?",
    "https://example.com/image.png"
)

# Multiple images
response = client.chat_with_image(
    "Compare these images",
    ["image1.jpg", "image2.jpg", "https://example.com/image3.png"]
)

# From bytes (useful for programmatic image generation)
import io
image_bytes = some_image_data
response = client.chat_with_image(
    "Analyze this",
    image_bytes,
    image_media_type="image/png"
)
```

### 4. PDF Document Analysis

```python
# From local file
response = client.chat_with_document(
    "Summarize this document",
    "/path/to/document.pdf"
)

# From URL
response = client.chat_with_document(
    "What are the key points?",
    "https://example.com/report.pdf"
)
```

### 5. Streaming Responses

```python
# Stream text as it's generated
for chunk in client.chat_stream("Write a story about AI"):
    print(chunk, end="", flush=True)
```

### 6. Multi-Turn Conversations

```python
# Create a conversation session
session = client.create_conversation(
    system_prompt="You are a helpful tutor."
)

# Multiple turns with context maintained
response1 = session.send("I want to learn Python")
response2 = session.send("What should I start with?")  # Has context
response3 = session.send("Can you show me an example?")

# Stream within conversation
for chunk in session.stream("Explain it simply"):
    print(chunk, end="")

# Add images in conversation
session.send_with_image("What's this?", "diagram.png")

# Get conversation history
print(session.get_history_as_text())

# Clear history
session.clear_history()
```

### 7. Tool/Function Calling

```python
# Define a tool with a handler
def get_weather(location: str, unit: str = "celsius") -> str:
    # Your implementation
    return f"Weather in {location}: 22°C, sunny"

weather_tool = client.create_tool(
    name="get_weather",
    description="Get current weather for a location",
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City name"
            },
            "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"]
            }
        },
        "required": ["location"]
    },
    handler=get_weather  # Auto-executed when Claude calls it
)

# Use the tool (auto-execution enabled by default)
response = client.chat(
    "What's the weather in Paris?",
    tools=[weather_tool]
)

# Disable auto-execution if you want manual control
response = client.chat(
    "What's the weather?",
    tools=[weather_tool],
    auto_execute_tools=False
)
```

### 8. Multiple Tools

```python
def calculate(expression: str) -> str:
    return str(eval(expression))  # Use safe eval in production!

def get_time(timezone: str = "UTC") -> str:
    from datetime import datetime
    return datetime.now().isoformat()

calc_tool = client.create_tool(
    name="calculator",
    description="Perform math calculations",
    parameters={
        "type": "object",
        "properties": {
            "expression": {"type": "string"}
        },
        "required": ["expression"]
    },
    handler=calculate
)

time_tool = client.create_tool(
    name="get_time",
    description="Get current time",
    parameters={
        "type": "object",
        "properties": {
            "timezone": {"type": "string"}
        },
        "required": []
    },
    handler=get_time
)

# Claude will use whichever tools are needed
response = client.chat(
    "What's 15% of 200? Also what time is it?",
    tools=[calc_tool, time_tool]
)
```

### 9. Tools in Conversations

```python
session = client.create_conversation(
    system_prompt="You are a database assistant."
)

# Add tools to the session
session.add_tools([lookup_tool, search_tool])

# Tools are available throughout the conversation
response1 = session.send("Show me all users")
response2 = session.send("Find user with ID 123")
```

## Available Models

```python
from claude_opus_client import Model

# Claude 4.5 family
Model.OPUS_4_5    # claude-opus-4-5-20251101 (most capable)
Model.SONNET_4_5  # claude-sonnet-4-5-20250929 (balanced)
Model.HAIKU_4_5   # claude-haiku-4-5-20251001 (fastest)

# Or use string directly
client = ClaudeClient(model="claude-opus-4-5-20251101")
```

## Configuration Options

```python
client = ClaudeClient(
    api_key="your-key",           # API key (or use ANTHROPIC_API_KEY env var)
    model=Model.OPUS_4_5,         # Model to use
    max_tokens=4096,              # Max response tokens
    temperature=0.7,              # 0.0-1.0 (lower = more deterministic)
    system_prompt="...",          # Default system prompt
    timeout=600.0                 # Request timeout in seconds
)
```

## Convenience Functions

```python
from claude_opus_client import quick_chat, quick_analyze_image

# One-liner chat
answer = quick_chat("What is 2+2?")

# One-liner image analysis
description = quick_analyze_image("Describe this", "photo.jpg")
```

## Error Handling

```python
from anthropic import APIError, RateLimitError

try:
    response = client.chat("Hello")
except RateLimitError:
    print("Rate limited, please wait")
except APIError as e:
    print(f"API error: {e}")
except FileNotFoundError:
    print("Image/document not found")
except ValueError as e:
    print(f"Invalid input: {e}")
```

## Image Processing Utilities

```python
from claude_opus_client import ImageProcessor

# Encode from file
image_block = ImageProcessor.encode_from_file("photo.jpg")

# Encode from URL
image_block = ImageProcessor.encode_from_url("https://...")

# Encode from bytes
image_block = ImageProcessor.encode_from_bytes(data, "image/png")

# Resize large images (requires Pillow)
resized_bytes = ImageProcessor.resize_if_needed("large.jpg", max_dimension=2048)
```

## Document Processing Utilities

```python
from claude_opus_client import DocumentProcessor

# Encode PDF from file
pdf_block = DocumentProcessor.encode_pdf_from_file("report.pdf")

# Encode PDF from URL
pdf_block = DocumentProcessor.encode_pdf_from_url("https://.../doc.pdf")
```

## Complete Example

```python
from claude_opus_client import ClaudeClient, Model

def main():
    # Initialize client
    client = ClaudeClient(
        model=Model.OPUS_4_5,
        system_prompt="You are a helpful assistant.",
        temperature=0.7
    )
    
    # Create tools
    def search_database(query: str) -> str:
        return f"Found 5 results for '{query}'"
    
    search_tool = client.create_tool(
        name="search_database",
        description="Search the database",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        },
        handler=search_database
    )
    
    # Start conversation
    session = client.create_conversation()
    session.add_tools([search_tool])
    
    # Interactive loop
    while True:
        user_input = input("You: ")
        if user_input.lower() in ('quit', 'exit'):
            break
        
        response = session.send(user_input)
        print(f"Claude: {response}\n")

if __name__ == "__main__":
    main()
```

## API Reference

### ClaudeClient

| Method | Description |
|--------|-------------|
| `chat(message, ...)` | Send text message, get response |
| `chat_with_image(message, image, ...)` | Send message with image(s) |
| `chat_with_document(message, document, ...)` | Send message with PDF |
| `chat_stream(message, ...)` | Stream response |
| `create_conversation(system_prompt)` | Create conversation session |
| `create_tool(name, description, parameters, handler)` | Create a tool |
| `register_tool(tool)` | Register tool for auto-execution |

### ConversationSession

| Method | Description |
|--------|-------------|
| `send(message, ...)` | Send message in conversation |
| `send_with_image(message, image, ...)` | Send with image |
| `send_with_document(message, document, ...)` | Send with PDF |
| `stream(message, ...)` | Stream response |
| `add_tools(tools)` | Add tools to session |
| `clear_history()` | Clear conversation history |
| `get_history_as_text()` | Get formatted history |

## License

MIT License
