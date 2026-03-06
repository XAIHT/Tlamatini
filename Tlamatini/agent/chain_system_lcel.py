import asyncio
import sys
import os
import json

# Handle both relative import (when used as module) and direct import (when run as script)
try:
    from .mcp_system_client import MCPSystemClient
except ImportError:
    # If relative import fails, try importing from the same directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from mcp_system_client import MCPSystemClient

from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

class SystemRAGChain:
    def __init__(self, config_path=None):
        # Load configuration from config.json
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")

        with open(config_path, 'r') as f:
            config = json.load(f)

        # Initialize Ollama LLM with values from config
        ollama_base_url = config.get("ollama_base_url", "http://127.0.0.1:11434")
        ollama_model = config.get("chained-model", "gpt-oss:20b-cloud")
        ollama_token = config.get("ollama_token", "")
        
        client_kwargs = {}
        if ollama_token:
            client_kwargs["headers"] = {"Authorization": f"Bearer {ollama_token}"}

        self.llm = OllamaLLM(
            base_url=ollama_base_url,
            model=ollama_model,
            client_kwargs=client_kwargs
        )

        # Initialize MCP client with URI from config
        mcp_uri = config.get("mcp_system_client_uri", "ws://127.0.0.1:8765")
        self.mcp_client = MCPSystemClient(uri=mcp_uri)

        # Available resources cache (fetched once)
        self.available_resources = None

        # Create routing prompt to decide if system context is needed
        self.routing_prompt = PromptTemplate.from_template(
            """Classify if this question needs system data to answer.

Available resources: {resources}

Question: {question}

Examples:
Q: "What is bigger 8.795 or 8.80?" → NO (math question)
Q: "What is the current CPU usage?" → YES (needs system data)
Q: "Is there enough disk space?" → YES (needs system data)
Q: "How is the system performing?" → YES (needs system data)
Q: "What is 2+2?" → NO (general knowledge)
Q: "What is the memory usage?" → YES (needs system data)

Does this question need the available system resources to answer?
Answer ONLY with YES or NO:"""
        )

        # Create main answer prompt template
        self.answer_prompt = PromptTemplate.from_template(
            "Context: {context}\n\nQuestion: {question}\n\nAnswer:"
        )

        # Build LCEL chain with intelligent routing
        self.chain = (
            RunnablePassthrough()  # Pass through input as dict with 'question' key
            | RunnableLambda(self.intelligent_context_fetch)  # Intelligently fetch context
            | self.answer_prompt  # Format prompt with context and question
            | self.llm  # Run LLM
            | StrOutputParser()  # Parse output to string
        )
    
    async def get_available_resources(self):
        """Get list of available resources from MCP server (cached)"""
        if self.available_resources is not None:
            return self.available_resources

        # Connect to MCP server
        if not await self.mcp_client.connect():
            raise Exception("Failed to connect to MCP server")

        try:
            # Get and cache available resources
            self.available_resources = await self.mcp_client.list_resources()
            return self.available_resources
        except Exception as e:
            print(f"Error fetching available resources: {e}")
            return []

    async def should_fetch_system_context(self, question):
        """Use hybrid approach to decide if system context is needed for this question"""
        question_lower = question.lower()

        # Keywords that strongly indicate system context is needed
        system_keywords = [
            'cpu', 'memory', 'ram', 'disk', 'storage', 'process', 'performance',
            'system', 'usage', 'load', 'network', 'bandwidth', 'resource',
            'running', 'available', 'free', 'used', 'consuming'
        ]

        # Keywords that indicate NO system context is needed
        general_keywords = [
            'what is', 'how to', 'why', 'explain', 'define', 'calculate',
            'bigger', 'smaller', 'larger', 'best', 'difference between'
        ]

        # Check for strong system indicators
        has_system_keyword = any(keyword in question_lower for keyword in system_keywords)

        # Check if it's clearly a general knowledge question
        is_general = any(keyword in question_lower for keyword in general_keywords)

        # Hybrid decision logic
        if has_system_keyword:
            # Strong indicator: needs system context
            return True
        elif is_general and not has_system_keyword:
            # Clearly general knowledge, no system context needed
            return False
        else:
            # Ambiguous case - use LLM to decide
            resources = await self.get_available_resources()
            resources_str = ", ".join(resources) if resources else "None available"

            routing_chain = self.routing_prompt | self.llm | StrOutputParser()
            decision = await routing_chain.ainvoke({
                "question": question,
                "resources": resources_str
            })

            decision_clean = decision.strip().upper()
            needs_context = "YES" in decision_clean

            return needs_context

    async def fetch_system_context(self):
        """Fetch actual system context from MCP server"""
        # Connect to MCP server if not already connected
        if not await self.mcp_client.connect():
            raise Exception("Failed to connect to MCP server")

        try:
            # Get system resources
            resources = await self.get_available_resources()

            # Collect resource values
            context_parts = []
            for resource in resources:
                try:
                    value = await self.mcp_client.get_resource(resource)
                    context_parts.append(f"{resource}: {value}")
                except Exception as e:
                    context_parts.append(f"{resource}: Error retrieving value ({e})")

            return "\n".join(context_parts)
        except Exception as e:
            return f"Error fetching system context: {e}"

    async def intelligent_context_fetch(self, input_data):
        """Intelligently decide whether to fetch system context based on the question"""
        question = input_data.get('question', '')

        # Use LLM to decide if we need system context
        needs_context = await self.should_fetch_system_context(question)

        if needs_context:
            print(f"[INFO] Fetching system context for question: {question}")
            context = await self.fetch_system_context()
        else:
            print(f"[INFO] No system context needed for question: {question}")
            context = "No system context required for this question."

        return {
            "context": context,
            "question": question
        }
    
    async def run(self, question):
        """Run the RAG chain with system context using LCEL"""
        # Execute the chain
        result = await self.chain.ainvoke({"question": question})
        return result

# Example usage
async def main():
    chain = SystemRAGChain()
    
    # Example questions
    questions = [
        "What is bigger 8.79 or 8.8?",
        "What is the current CPU usage?",
        "Is there enough disk space available?",
        "How is the system performing overall?"
    ]
    
    for question in questions:
        print(f"\nQuestion: {question}")
        try:
            answer = await chain.run(question)
            print(f"Answer: {answer}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())