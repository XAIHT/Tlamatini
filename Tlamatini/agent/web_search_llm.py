# Updated web_search_llm.py to allow custom Ollama server IP and port
from langchain_ollama import OllamaLLM
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from typing import Dict, Any, Optional, List
import os
import sys
import json
import re
import certifi
import ssl

_CONFIG_CACHE: Optional[Dict[str, Any]] = None

def _find_config_path() -> Optional[str]:
    env_path = os.environ.get("CONFIG_PATH", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path
    try:
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            p = os.path.join(exe_dir, 'config.json')
            if os.path.isfile(p):
                return p
    except Exception:
        pass
    try:
        module_dir = os.path.dirname(os.path.abspath(__file__))
        p2 = os.path.join(module_dir, 'config.json')
        if os.path.isfile(p2):
            return p2
    except Exception:
        pass
    return None

def _load_config() -> Dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    path = _find_config_path()
    cfg: Dict[str, Any] = {}
    if path and os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    _CONFIG_CACHE = cfg
    return cfg

# Set the certificate bundle path
config = _load_config()
ssl_cert_file = config.get('ssl_cert_file', '')
requests_ca_bundle = config.get('requests_ca_bundle', '')

os.environ['SSL_CERT_FILE'] = ssl_cert_file if ssl_cert_file else certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = requests_ca_bundle if requests_ca_bundle else certifi.where()

# This is insecure, but it will disable SSL certificate verification globally
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    # Legacy Python that doesn't verify HTTPS certificates by default
    pass
else:
    # Handle target environment that doesn't support HTTPS verification
    ssl._create_default_https_context = _create_unverified_https_context

def create_ollama_agent(
    model: str = "llama3.2:latest",
    verbose: bool = True,
    host: str = "localhost",
    port: int = 11434,
    max_iterations: int = 10,
    ollama_token: str = "",
    streaming: bool = True
):
    """
    Creates and returns a LangChain agent that can query an Ollama server
    running on the specified host and port.
    """
    print(f"Initializing LLM with model: {model}")
    # 0.0.0.0 is valid for binding, not for clients. Prefer localhost.
    used_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    if used_host != host:
        print(f"Note: Replacing client host '{host}' with '{used_host}' for connectivity.")
    # Pass the base URL to OllamaLLM so it knows where to talk to

    token = ollama_token
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    client_kwargs = {"headers": headers}
    llm = OllamaLLM(
        model=model, 
        base_url=f"http://{used_host}:{port}",
        client_kwargs=client_kwargs,
        streaming=streaming,
        additional_kwargs={
            "options": {
                "temperature": 0,
                "num_gpu": 999 
            }
        }
        )

    print("Setting up tools...")
    cfg = _load_config()
    search_name = str(cfg.get('web_search_tool_name', 'web_search'))
    search_desc = str(cfg.get('web_search_tool_description', (
        "A tool for searching the internet for current events, real-time information, or facts you do not know. Do NOT use this for creative writing."
    )))
    tools = [
        DuckDuckGoSearchRun(
            name=search_name,
            description=search_desc,
            api_wrapper=DuckDuckGoSearchAPIWrapper()
        )
    ]

    prompt_template = """Answer the following questions as best you can.
You have access to the following tools: {tools}

Use the following format:
Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat up to {max_iterations} times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
{agent_scratchpad}"""

    # Let the agent fill in tool descriptions and names; only provide the template
    # Bind max_iterations for display in the prompt
    prompt = PromptTemplate.from_template(prompt_template).partial(
        max_iterations=str(max_iterations)
    )

    agent = create_react_agent(
        llm=llm,
        tools=tools,
        prompt=prompt
    )
    return AgentExecutor(agent=agent, tools=tools, max_iterations=max_iterations, verbose=verbose)


class WebSearchLLM:
    """
    Minimal, dependable web-search component that:
    - Executes a DuckDuckGo query for the user's input
    - Optionally performs a second, query expansion if requested
    - Summarizes findings with an Ollama LLM into a compact context block
    - Returns external_context and extracted source links for fusion
    """

    def __init__(self, base_url: str, model: str = "llama3.2:latest", token: str = "", max_chars: int = 6000):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.summarizer = OllamaLLM(
            model=model,
            base_url=base_url,
            client_kwargs={"headers": headers},
            streaming=False,
        )
        cfg = _load_config()
        search_name = str(cfg.get('web_search_tool_name', 'web_search'))
        search_desc = str(cfg.get('web_search_tool_description', (
            "A tool for searching the internet for current events, real-time information, or facts you do not know. Do NOT use this for creative writing."
        )))
        self.search = DuckDuckGoSearchRun(
            name=search_name, 
            description=search_desc,
            api_wrapper=DuckDuckGoSearchAPIWrapper()
        )
        self.max_chars = max(1000, int(max_chars))

    def _summarize(self, question: str, raw_blurb: str) -> str:
        prompt = (
            "You are a precise research assistant. Summarize the following web search findings into a concise, "
            "factual context that could help answer the user's question. Include inline citations by keeping URLs in parentheses.\n\n"
            "Rules:\n"
            "- Be objective, avoid speculation.\n"
            "- Prioritize authoritative sources.\n"
            "- Keep it under 400-600 words.\n"
            "- Do not add content not present in the findings.\n\n"
            f"Question: {question}\n\nFindings:\n{raw_blurb}\n\nContext:"
        )
        out = self.summarizer.invoke(prompt)
        text = getattr(out, "content", str(out))
        if len(text) > self.max_chars:
            text = text[: self.max_chars] + "…"
        return text

    @staticmethod
    def _extract_urls(text: str) -> List[str]:
        urls = re.findall(r"https?://[^\s)]+", text)
        # Deduplicate while preserving order
        seen = set()
        ordered: List[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                ordered.append(u)
        return ordered[:10]

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        question = payload.get("input", "")
        if not isinstance(question, str) or not question.strip():
            return {"external_context": "", "sources": []}

        # Execute primary search
        primary = self.search.run(question)

        # Optionally perform a very light expansion (heuristic)
        expansion_needed = len(question.split()) < 6
        expanded = ""
        if expansion_needed:
            expanded = self.search.run(f"site:wikipedia.org {question}")

        joined = (primary or "")
        if expanded:
            joined += "\n\n" + expanded

        context = self._summarize(question, joined)
        sources = self._extract_urls(joined + "\n\n" + context)
        return {"external_context": context, "sources": sources}


def build_web_search_llm(httpx_client_instance: Optional[Any] = None) -> WebSearchLLM:
    """
    Factory used by the RAG router. Attempts to infer Ollama base_url from:
    1) httpx_client_instance.base_url if provided
    2) ollama_base_url from config.json
    3) OLLAMA_HOST/OLLAMA_PORT env vars
    4) Defaults to http://127.0.0.1:11434
    """
    cfg = _load_config()
    base_url = None
    if httpx_client_instance is not None:
        try:
            base_url = str(getattr(httpx_client_instance, "base_url", "")).rstrip("/")
        except Exception:
            base_url = None
    if not base_url:
        base_url = str(cfg.get('ollama_base_url', '')).strip()
    if not base_url:
        host = os.environ.get("OLLAMA_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = os.environ.get("OLLAMA_PORT", "11434").strip() or "11434"
        base_url = f"http://{host}:{port}"
    token = str(cfg.get('ollama_token', os.environ.get("OLLAMA_TOKEN", "")))
    model = str(cfg.get('web_summarizer_model', os.environ.get("WEB_SUMMARIZER_MODEL", "llama3.2:latest")))
    max_chars = int(cfg.get('web_context_max_chars', int(os.environ.get("WEB_CONTEXT_MAX_CHARS", "6000"))))
    return WebSearchLLM(base_url=base_url, model=model, token=token, max_chars=max_chars)

# Example of how to invoke the agent with custom host/port
if __name__ == "__main__":
    # Replace with your Ollama server's reachable IP and port (client side)
    # If your server listens on 0.0.0.0, connect via 127.0.0.1 or the machine's LAN IP
    agent = create_ollama_agent(host="127.0.0.1", port=11434, max_iterations=10, ollama_token="", streaming=True)
    while True:
        question = input("\nAsk a question: ")
        if question.lower() in {"quit", "exit"}:
            break
        result = agent.invoke({"input": question})
        print("\nResult:\n", result.get("output", "No output found"))
