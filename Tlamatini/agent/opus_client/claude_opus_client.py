"""
Claude Opus 4.5 Python Client
=============================
A comprehensive client for interacting with Claude Opus 4.5 via the Anthropic API.
Supports text, images, tools/functions, streaming, and conversation management.

Requirements:
    pip install anthropic httpx pillow

Usage:
    from claude_opus_client import ClaudeClient
    
    client = ClaudeClient(api_key="your-api-key")
    response = client.chat("Hello, Claude!")
"""

import base64
import mimetypes
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Generator, Optional, Union
from anthropic import Anthropic


try:
    import httpx
except ImportError:
    httpx = None

try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class Model(str, Enum):
    """Available Claude models."""
    OPUS_4_5 = "claude-opus-4-5-20251101"
    SONNET_4_5 = "claude-sonnet-4-5-20250929"
    HAIKU_4_5 = "claude-haiku-4-5-20251001"
    # Legacy models
    OPUS_3 = "claude-3-opus-20240229"
    SONNET_3_5 = "claude-3-5-sonnet-20241022"


@dataclass
class Message:
    """Represents a conversation message."""
    role: str  # "user" or "assistant"
    content: Union[str, list[dict]]
    
    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ToolResult:
    """Represents the result of a tool execution."""
    tool_use_id: str
    content: str
    is_error: bool = False
    
    def to_dict(self) -> dict:
        result = {
            "type": "tool_result",
            "tool_use_id": self.tool_use_id,
            "content": self.content
        }
        if self.is_error:
            result["is_error"] = True
        return result


@dataclass
class Tool:
    """Defines a tool/function that Claude can use."""
    name: str
    description: str
    input_schema: dict
    handler: Optional[Callable] = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }


@dataclass
class Conversation:
    """Manages a conversation with history."""
    messages: list[Message] = field(default_factory=list)
    system_prompt: Optional[str] = None
    
    def add_user_message(self, content: Union[str, list[dict]]) -> None:
        self.messages.append(Message(role="user", content=content))
    
    def add_assistant_message(self, content: Union[str, list[dict]]) -> None:
        self.messages.append(Message(role="assistant", content=content))
    
    def add_tool_result(self, tool_use_id: str, result: str, is_error: bool = False) -> None:
        tool_result = ToolResult(tool_use_id, result, is_error)
        self.messages.append(Message(role="user", content=[tool_result.to_dict()]))
    
    def to_messages(self) -> list[dict]:
        return [msg.to_dict() for msg in self.messages]
    
    def clear(self) -> None:
        self.messages.clear()


class ImageProcessor:
    """Handles image processing and encoding for the API."""
    
    SUPPORTED_FORMATS = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    MAX_SIZE = 20 * 1024 * 1024  # 20MB limit
    
    # Fallback mapping for Windows compatibility
    EXTENSION_TO_MIME = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    
    @classmethod
    def _get_mime_type(cls, file_path: Path) -> str:
        """Get MIME type with fallback for Windows compatibility."""
        mime_type, _ = mimetypes.guess_type(str(file_path))
        
        # Fallback to extension-based lookup if mimetypes fails
        if mime_type is None or mime_type not in cls.SUPPORTED_FORMATS:
            ext = file_path.suffix.lower()
            mime_type = cls.EXTENSION_TO_MIME.get(ext)
        
        return mime_type
    
    @classmethod
    def encode_from_file(cls, file_path: Union[str, Path]) -> dict:
        """Encode an image file for the API."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")
        
        mime_type = cls._get_mime_type(path)
        if mime_type not in cls.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported image format: {mime_type}. Supported: {cls.SUPPORTED_FORMATS}")
        
        file_size = path.stat().st_size
        if file_size > cls.MAX_SIZE:
            raise ValueError(f"Image file too large: {file_size} bytes. Max: {cls.MAX_SIZE} bytes")
        
        with open(path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")
        
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": image_data
            }
        }
    
    @classmethod
    def encode_from_url(cls, url: str, download: bool = True) -> dict:
        """
        Encode an image from a URL.
        
        Args:
            url: Image URL to fetch
            download: If True, downloads the image and sends as base64 (more reliable).
                      If False, passes URL directly to API (may fail for some URLs).
        """
        if not download:
            # Pass URL directly to API (may not work for all URLs)
            return {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": url
                }
            }
        
        # Download the image ourselves for better compatibility
        import urllib.request
        import urllib.error
        
        try:
            # Create request with User-Agent to avoid blocks
            request = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            
            with urllib.request.urlopen(request, timeout=30) as response:
                image_data = response.read()
                
                # Get content type from response headers
                content_type = response.headers.get('Content-Type', '').split(';')[0].strip()
                
                # Validate format
                if content_type not in cls.SUPPORTED_FORMATS:
                    # Try to guess from URL
                    mime_type, _ = mimetypes.guess_type(url)
                    if mime_type in cls.SUPPORTED_FORMATS:
                        content_type = mime_type
                    else:
                        raise ValueError(f"Unsupported image format from URL: {content_type}")
                
                # Validate size
                if len(image_data) > cls.MAX_SIZE:
                    raise ValueError(f"Image from URL too large: {len(image_data)} bytes")
                
                return {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": content_type,
                        "data": base64.standard_b64encode(image_data).decode("utf-8")
                    }
                }
                
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to download image from URL: {url}. Error: {e}")
    
    @classmethod
    def encode_from_bytes(cls, data: bytes, media_type: str) -> dict:
        """Encode raw image bytes for the API."""
        if media_type not in cls.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported image format: {media_type}")
        
        if len(data) > cls.MAX_SIZE:
            raise ValueError(f"Image data too large: {len(data)} bytes")
        
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.standard_b64encode(data).decode("utf-8")
            }
        }
    
    @classmethod
    def resize_if_needed(cls, file_path: Union[str, Path], max_dimension: int = 2048) -> bytes:
        """Resize an image if it exceeds max dimensions (requires PIL)."""
        if not PIL_AVAILABLE:
            raise ImportError("PIL/Pillow is required for image resizing: pip install Pillow")
        
        with Image.open(file_path) as img:
            if max(img.size) > max_dimension:
                ratio = max_dimension / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            format_map = {"JPEG": "JPEG", "PNG": "PNG", "GIF": "GIF", "WEBP": "WEBP"}
            save_format = format_map.get(img.format, "PNG")
            img.save(buffer, format=save_format, quality=85)
            return buffer.getvalue()


class DocumentProcessor:
    """Handles document (PDF) processing for the API."""
    
    @classmethod
    def encode_pdf_from_file(cls, file_path: Union[str, Path]) -> dict:
        """Encode a PDF file for the API."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        
        with open(path, "rb") as f:
            pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")
        
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_data
            }
        }
    
    @classmethod
    def encode_pdf_from_url(cls, url: str) -> dict:
        """Create a PDF reference from a URL."""
        return {
            "type": "document",
            "source": {
                "type": "url",
                "url": url
            }
        }


class ClaudeClient:
    """
    Main client for interacting with Claude Opus 4.5.
    
    Features:
        - Text and image inputs
        - Tool/function calling
        - Streaming responses
        - Conversation management
        - PDF document support
    
    Example:
        client = ClaudeClient(api_key="your-api-key")
        
        # Simple chat
        response = client.chat("What is the capital of France?")
        
        # With image
        response = client.chat_with_image("Describe this image", "photo.jpg")
        
        # With tools
        tools = [client.create_tool("get_weather", "Get weather info", {...}, handler)]
        response = client.chat("What's the weather?", tools=tools)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Union[str, Model] = Model.OPUS_4_5,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        system_prompt: Optional[str] = None,
        timeout: float = 600.0
    ):
        """
        Initialize the Claude client.
        
        Args:
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
            model: Model to use (default: Claude Opus 4.5)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)
            system_prompt: Default system prompt for all conversations
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        print("--- Anthropic API key: ", self.api_key)
        if not self.api_key:
            raise ValueError("API key required. Set ANTHROPIC_API_KEY or pass api_key parameter.")
        
        self.model = model.value if isinstance(model, Model) else model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system_prompt = system_prompt
        self.timeout = timeout
        
        self._client = Anthropic(api_key=self.api_key, timeout=timeout)
        self._tools: dict[str, Tool] = {}
    
    def chat(
        self,
        message: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[list[Tool]] = None,
        auto_execute_tools: bool = True
    ) -> str:
        """
        Send a simple text message and get a response.
        
        Args:
            message: The user's message
            system: Override system prompt for this request
            max_tokens: Override max tokens for this request
            temperature: Override temperature for this request
            tools: List of tools Claude can use
            auto_execute_tools: Automatically execute tools and continue conversation
        
        Returns:
            Claude's response text
        """
        messages = [{"role": "user", "content": message}]
        return self._send_request(
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            auto_execute_tools=auto_execute_tools
        )
    
    def chat_with_image(
        self,
        message: str,
        image: Union[str, Path, bytes, list],
        image_media_type: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Send a message with one or more images.
        
        Args:
            message: The user's message/question about the image(s)
            image: File path, URL, bytes, or list of any of these
            image_media_type: Media type if image is bytes
            system: Override system prompt
            max_tokens: Override max tokens
        
        Returns:
            Claude's response text
        """
        content = self._build_image_content(message, image, image_media_type)
        messages = [{"role": "user", "content": content}]
        return self._send_request(messages=messages, system=system, max_tokens=max_tokens)
    
    def chat_with_document(
        self,
        message: str,
        document: Union[str, Path],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Send a message with a PDF document.
        
        Args:
            message: The user's message/question about the document
            document: File path or URL to PDF
            system: Override system prompt
            max_tokens: Override max tokens
        
        Returns:
            Claude's response text
        """
        content = self._build_document_content(message, document)
        messages = [{"role": "user", "content": content}]
        return self._send_request(messages=messages, system=system, max_tokens=max_tokens)
    
    def chat_stream(
        self,
        message: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Generator[str, None, None]:
        """
        Send a message and stream the response.
        
        Args:
            message: The user's message
            system: Override system prompt
            max_tokens: Override max tokens
            temperature: Override temperature
        
        Yields:
            Response text chunks as they arrive
        """
        messages = [{"role": "user", "content": message}]
        yield from self._stream_request(
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature
        )
    
    def create_conversation(self, system_prompt: Optional[str] = None) -> "ConversationSession":
        """
        Create a new conversation session with history management.
        
        Args:
            system_prompt: System prompt for this conversation
        
        Returns:
            ConversationSession object for multi-turn conversations
        """
        return ConversationSession(
            client=self,
            system_prompt=system_prompt or self.system_prompt
        )
    
    def create_tool(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Optional[Callable] = None
    ) -> Tool:
        """
        Create a tool that Claude can use.
        
        Args:
            name: Tool name
            description: What the tool does
            parameters: JSON Schema for tool parameters
            handler: Function to execute when tool is called
        
        Returns:
            Tool object
        
        Example:
            def get_weather(location: str, unit: str = "celsius") -> str:
                return f"Weather in {location}: 22°{unit[0].upper()}"
            
            tool = client.create_tool(
                name="get_weather",
                description="Get current weather for a location",
                parameters={
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                    },
                    "required": ["location"]
                },
                handler=get_weather
            )
        """
        tool = Tool(
            name=name,
            description=description,
            input_schema=parameters,
            handler=handler
        )
        self._tools[name] = tool
        return tool
    
    def register_tool(self, tool: Tool) -> None:
        """Register a tool for auto-execution."""
        self._tools[tool.name] = tool
    
    def _build_image_content(
        self,
        message: str,
        image: Union[str, Path, bytes, list],
        media_type: Optional[str] = None
    ) -> list[dict]:
        """Build content array with text and images."""
        content = []
        
        images = image if isinstance(image, list) else [image]
        
        for img in images:
            if isinstance(img, bytes):
                if not media_type:
                    raise ValueError("media_type required when image is bytes")
                content.append(ImageProcessor.encode_from_bytes(img, media_type))
            elif isinstance(img, (str, Path)):
                img_str = str(img)
                if img_str.startswith(("http://", "https://")):
                    content.append(ImageProcessor.encode_from_url(img_str))
                else:
                    content.append(ImageProcessor.encode_from_file(img_str))
        
        content.append({"type": "text", "text": message})
        return content
    
    def _build_document_content(
        self,
        message: str,
        document: Union[str, Path]
    ) -> list[dict]:
        """Build content array with text and document."""
        content = []
        
        doc_str = str(document)
        if doc_str.startswith(("http://", "https://")):
            content.append(DocumentProcessor.encode_pdf_from_url(doc_str))
        else:
            content.append(DocumentProcessor.encode_pdf_from_file(doc_str))
        
        content.append({"type": "text", "text": message})
        return content
    
    def _send_request(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[list[Tool]] = None,
        auto_execute_tools: bool = True
    ) -> str:
        """Send a request to the API."""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": messages
        }
        
        if system or self.system_prompt:
            kwargs["system"] = system or self.system_prompt
        
        if temperature is not None or self.temperature != 1.0:
            kwargs["temperature"] = temperature if temperature is not None else self.temperature
        
        if tools:
            kwargs["tools"] = [t.to_dict() for t in tools]
        
        response = self._client.messages.create(**kwargs)
        
        # Handle tool use
        if response.stop_reason == "tool_use" and auto_execute_tools:
            return self._handle_tool_use(response, messages, kwargs, tools)
        
        # Extract text from response
        return self._extract_text(response)
    
    def _handle_tool_use(
        self,
        response,
        messages: list[dict],
        kwargs: dict,
        tools: Optional[list[Tool]]
    ) -> str:
        """Handle tool use responses."""
        # Add assistant's response to messages
        messages.append({"role": "assistant", "content": response.content})
        
        # Execute tools and gather results
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool = self._tools.get(block.name)
                if tool and tool.handler:
                    try:
                        result = tool.handler(**block.input)
                        tool_results.append(ToolResult(
                            tool_use_id=block.id,
                            content=str(result) if not isinstance(result, str) else result
                        ))
                    except Exception as e:
                        tool_results.append(ToolResult(
                            tool_use_id=block.id,
                            content=f"Error: {str(e)}",
                            is_error=True
                        ))
                else:
                    tool_results.append(ToolResult(
                        tool_use_id=block.id,
                        content=f"Tool '{block.name}' has no handler registered",
                        is_error=True
                    ))
        
        # Add tool results to messages
        messages.append({
            "role": "user",
            "content": [tr.to_dict() for tr in tool_results]
        })
        
        # Continue conversation
        kwargs["messages"] = messages
        new_response = self._client.messages.create(**kwargs)
        
        # Recursively handle if more tool use
        if new_response.stop_reason == "tool_use":
            return self._handle_tool_use(new_response, messages, kwargs, tools)
        
        return self._extract_text(new_response)
    
    def _stream_request(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Generator[str, None, None]:
        """Stream a response from the API."""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": messages
        }
        
        if system or self.system_prompt:
            kwargs["system"] = system or self.system_prompt
        
        if temperature is not None or self.temperature != 1.0:
            kwargs["temperature"] = temperature if temperature is not None else self.temperature
        
        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text
    
    def _extract_text(self, response) -> str:
        """Extract text content from API response."""
        texts = []
        for block in response.content:
            if hasattr(block, "text"):
                texts.append(block.text)
        return "\n".join(texts)


class ConversationSession:
    """
    Manages a multi-turn conversation with history.
    
    Example:
        session = client.create_conversation("You are a helpful assistant.")
        
        response1 = session.send("Hello!")
        response2 = session.send("What did I just say?")  # Has context
        
        # With image
        response3 = session.send_with_image("What's in this?", "photo.jpg")
    """
    
    def __init__(self, client: ClaudeClient, system_prompt: Optional[str] = None):
        self._client = client
        self._conversation = Conversation(system_prompt=system_prompt)
        self._tools: list[Tool] = []
    
    @property
    def messages(self) -> list[Message]:
        """Get conversation history."""
        return self._conversation.messages.copy()
    
    @property
    def system_prompt(self) -> Optional[str]:
        """Get the system prompt."""
        return self._conversation.system_prompt
    
    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        """Set the system prompt."""
        self._conversation.system_prompt = value
    
    def add_tools(self, tools: list[Tool]) -> None:
        """Add tools for this conversation."""
        self._tools.extend(tools)
        for tool in tools:
            self._client.register_tool(tool)
    
    def send(
        self,
        message: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> str:
        """
        Send a message and get a response.
        
        Args:
            message: User's message
            max_tokens: Override max tokens
            temperature: Override temperature
        
        Returns:
            Claude's response
        """
        self._conversation.add_user_message(message)
        
        response = self._client._send_request(
            messages=self._conversation.to_messages(),
            system=self._conversation.system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=self._tools if self._tools else None
        )
        
        self._conversation.add_assistant_message(response)
        return response
    
    def send_with_image(
        self,
        message: str,
        image: Union[str, Path, bytes, list],
        image_media_type: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Send a message with image(s).
        
        Args:
            message: User's message about the image
            image: Image file path, URL, bytes, or list
            image_media_type: Media type if image is bytes
            max_tokens: Override max tokens
        
        Returns:
            Claude's response
        """
        content = self._client._build_image_content(message, image, image_media_type)
        self._conversation.add_user_message(content)
        
        response = self._client._send_request(
            messages=self._conversation.to_messages(),
            system=self._conversation.system_prompt,
            max_tokens=max_tokens
        )
        
        self._conversation.add_assistant_message(response)
        return response
    
    def send_with_document(
        self,
        message: str,
        document: Union[str, Path],
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Send a message with a PDF document.
        
        Args:
            message: User's message about the document
            document: PDF file path or URL
            max_tokens: Override max tokens
        
        Returns:
            Claude's response
        """
        content = self._client._build_document_content(message, document)
        self._conversation.add_user_message(content)
        
        response = self._client._send_request(
            messages=self._conversation.to_messages(),
            system=self._conversation.system_prompt,
            max_tokens=max_tokens
        )
        
        self._conversation.add_assistant_message(response)
        return response
    
    def stream(
        self,
        message: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Generator[str, None, None]:
        """
        Send a message and stream the response.
        
        Args:
            message: User's message
            max_tokens: Override max tokens
            temperature: Override temperature
        
        Yields:
            Response text chunks
        """
        self._conversation.add_user_message(message)
        
        full_response = []
        for chunk in self._client._stream_request(
            messages=self._conversation.to_messages(),
            system=self._conversation.system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        ):
            full_response.append(chunk)
            yield chunk
        
        self._conversation.add_assistant_message("".join(full_response))
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation.clear()
    
    def get_history_as_text(self) -> str:
        """Get conversation history as formatted text."""
        lines = []
        for msg in self._conversation.messages:
            role = msg.role.upper()
            content = msg.content if isinstance(msg.content, str) else "[Complex content]"
            lines.append(f"{role}: {content}")
        return "\n\n".join(lines)


# Convenience functions for quick usage
def quick_chat(message: str, api_key: Optional[str] = None) -> str:
    """Quick one-off chat with Claude Opus 4.5."""
    client = ClaudeClient(api_key=api_key)
    return client.chat(message)


def quick_analyze_image(
    message: str,
    image_path: str,
    api_key: Optional[str] = None
) -> str:
    """Quick image analysis with Claude Opus 4.5."""
    client = ClaudeClient(api_key=api_key)
    return client.chat_with_image(message, image_path)


if __name__ == "__main__":
    # Example usage demonstration
    print("Claude Opus 4.5 Client - Example Usage")
    print("=" * 50)
    
    example_code = '''
# Basic Usage
from claude_opus_client import ClaudeClient, Model

# Initialize client
client = ClaudeClient(
    api_key="your-api-key",  # or set ANTHROPIC_API_KEY env var
    model=Model.OPUS_4_5,
    max_tokens=4096
)

# Simple chat
response = client.chat("Explain quantum computing in simple terms")
print(response)

# Chat with image
response = client.chat_with_image(
    "What's in this image?",
    "path/to/image.jpg"  # or URL
)

# Chat with PDF
response = client.chat_with_document(
    "Summarize this document",
    "path/to/document.pdf"
)

# Streaming response
for chunk in client.chat_stream("Write a poem about AI"):
    print(chunk, end="", flush=True)

# Multi-turn conversation
session = client.create_conversation(
    system_prompt="You are a helpful coding assistant."
)
response1 = session.send("What is Python?")
response2 = session.send("How do I install it?")  # Has context

# Using tools
def get_current_time(timezone: str = "UTC") -> str:
    from datetime import datetime
    return datetime.now().isoformat()

tool = client.create_tool(
    name="get_current_time",
    description="Get the current date and time",
    parameters={
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Timezone name"
            }
        },
        "required": []
    },
    handler=get_current_time
)

response = client.chat(
    "What time is it?",
    tools=[tool],
    auto_execute_tools=True
)
'''
    print(example_code)
