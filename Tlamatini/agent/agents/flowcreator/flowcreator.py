# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# FlowCreator Agent - Uses an LLM to design and create agent flows automatically
# Action: Read prompt + agentic_skill.md -> Query LLM -> Parse response -> Write flow plan
#
# This agent produces two output files in its instance directory:
#   - flow_creation_script.txt : The intermediate LLM-parsed plan
#   - flow_result.json         : Structured JSON for the frontend to render

import os
import sys
import traceback

# -----------------------------------------------------------------------------
# EARLY INITIALIZATION & ERROR CATCHING
# -----------------------------------------------------------------------------
# Provide a fallback global just in case path parsing fails completely
CURRENT_DIR_NAME = "flowcreator_unknown"
LOG_FILE_PATH = "flowcreator.log"

# Latched by _write_error_result() / _write_flw_file(); drives the exit code so a
# failed run is reported as FAILED (not "completed") to the wrapped chat-agent.
_FAILED = False
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'

try:
    # FIX: Disable Intel Fortran runtime Ctrl+C handler
    os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

    # Set working directory to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Use directory name for log file
    CURRENT_DIR_NAME = os.path.basename(os.path.abspath(script_dir))
    LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

    # Reanimation detection: AGENT_REANIMATED=1 means resume from pause
    _IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
    if not _IS_REANIMATED:
        open(LOG_FILE_PATH, 'w').close()

    # Immediately ensure log file exists so we can write to it even if imports fail
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(f"--- FlowCreator Initialization Started in {script_dir} ---\n")

    # Redirect stderr to the log file so any unhandled exceptions are caught
    sys.stderr = open(LOG_FILE_PATH, "a", encoding="utf-8")

except Exception:
    # Absolute last resort fallback
    with open("flowcreator_early_startup_error.log", "a", encoding="utf-8") as f:
        f.write(f"FATAL EARLY STARTUP ERROR:\n{traceback.format_exc()}\n")

# Now it is safer to import complex modules
try:
    import re
    import time
    import yaml
    import json
    import logging
    import urllib.request
    import urllib.error
    from typing import Dict, List, Any

    # Configure the standard logger to be VERBOSE (DEBUG level)
    logging.basicConfig(
        filename=LOG_FILE_PATH,
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        encoding='utf-8'
    )

    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(console_handler)

    logging.debug("All modules successfully imported. Standard logging initialized.")
except Exception:
    # If an import fails, it prints to sys.stderr which is now our log file
    sys.stderr.write(f"FATAL IMPORT ERROR:\n{traceback.format_exc()}\n")
    sys.stderr.flush()
    sys.exit(1)


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logging.error(f"Error: {path} not found.")
        sys.exit(1)
    except Exception:
        logging.error(f"Error parsing {path}:\n{traceback.format_exc()}")
        sys.exit(1)


def load_agentic_skill() -> str:
    """Load the agentic_skill.md file that describes all available agents."""
    # First check in the current (instance) directory
    skill_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agentic_skill.md")
    if not os.path.exists(skill_path):
        # Fallback: check the template directory
        template_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "agents", "flowcreator"
        )
        skill_path = os.path.join(template_dir, "agentic_skill.md")

    if not os.path.exists(skill_path):
        logging.error(f"agentic_skill.md not found at {skill_path}")
        return ""

    with open(skill_path, "r", encoding="utf-8") as f:
        return f.read()


def query_ollama(host: str, model: str, prompt: str, num_ctx: int = 65536) -> str:
    """Send a prompt to an Ollama LLM and return the full response text."""
    url = f"{host.rstrip('/')}/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": 0}
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"Ollama HTTP {e.code}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {host}: {e.reason}") from e


def parse_flow_script(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse the LLM response into a list of agent definitions.

    Expected LLM output format (JSON array):
    [
      {
        "agent_type": "starter",
        "config": {
          "target_agents": ["raiser_2"],
          "exit_after_start": true
        }
      },
      ...
    ]

    The function tries to extract a JSON array from the LLM response,
    handling markdown code fences and other wrapping.
    """
    # Try to find JSON array in the response
    # First, strip markdown code fences if present
    cleaned = raw_text.strip()

    # Remove markdown code fence wrappers
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)```', cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # Try to find a JSON array
    bracket_start = cleaned.find('[')
    bracket_end = cleaned.rfind(']')

    if bracket_start == -1 or bracket_end == -1:
        logging.error("No JSON array found in LLM response")
        return []

    json_str = cleaned[bracket_start:bracket_end + 1]

    try:
        agents = json.loads(json_str)
        if not isinstance(agents, list):
            logging.error("Parsed JSON is not an array")
            return []
        return agents
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON from LLM response: {e}")
        logging.error(f"Attempted to parse: {json_str[:500]}")
        return []


def build_flow_result(agents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate against installed contracts before creating canvas connections."""
    from flow_knowledge import build_flow, load_catalog
    return build_flow(agents, load_catalog())


def improve_layout(flow_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Improve the layout using topological ordering for a left-to-right flow.
    Agents are placed in columns based on their depth in the dependency graph.
    Handles cycles gracefully and clamps positions to fit within a visible canvas.
    """
    nodes = flow_result.get("nodes", [])
    connections = flow_result.get("connections", [])

    if not nodes:
        return flow_result

    n = len(nodes)

    # Build adjacency list (forward edges)
    forward: Dict[int, List[int]] = {i: [] for i in range(n)}
    backward: Dict[int, List[int]] = {i: [] for i in range(n)}
    for conn in connections:
        src = conn.get("sourceIndex", -1)
        tgt = conn.get("targetIndex", -1)
        if 0 <= src < n and 0 <= tgt < n:
            forward[src].append(tgt)
            backward[tgt].append(src)

    # Compute depth via BFS from roots (nodes with no incoming edges)
    # Use a visited set to prevent cycles from inflating depth values
    depth: Dict[int, int] = {}
    roots = [i for i in range(n) if not backward[i]]
    if not roots:
        roots = [0]  # fallback

    from collections import deque
    queue: deque[int] = deque()
    visited: set = set()

    for r in roots:
        depth[r] = 0
        queue.append(r)
        visited.add(r)

    while queue:
        node = queue.popleft()
        for child in forward[node]:
            new_depth = depth[node] + 1
            if child not in visited:
                # First visit: assign depth and enqueue
                depth[child] = new_depth
                visited.add(child)
                queue.append(child)
            elif new_depth > depth[child] and new_depth < n:
                # Already visited but found a longer acyclic path — update
                # Cap at n-1 to prevent cycle inflation
                depth[child] = new_depth
                queue.append(child)

    # Assign depth 0 to any unvisited nodes
    for i in range(n):
        if i not in depth:
            depth[i] = 0

    # Group nodes by depth
    depth_groups: Dict[int, List[int]] = {}
    for node_idx, d in depth.items():
        depth_groups.setdefault(d, []).append(node_idx)

    # Layout parameters
    col_width = 160
    row_height = 80
    start_x = 50
    start_y = 50

    for d in sorted(depth_groups.keys()):
        group = depth_groups[d]
        for row_idx, node_idx in enumerate(group):
            x = start_x + d * col_width
            y = start_y + row_idx * row_height
            nodes[node_idx]["left"] = f"{x}px"
            nodes[node_idx]["top"] = f"{y}px"

    # Clamp/scale positions to fit within a visible canvas area
    max_canvas_w = 900
    max_canvas_h = 600

    # Find actual bounding box of all nodes
    max_x = 0
    max_y = 0
    for node in nodes:
        x_val = int(node["left"].replace("px", "").split(".")[0])
        y_val = int(node["top"].replace("px", "").split(".")[0])
        max_x = max(max_x, x_val)
        max_y = max(max_y, y_val)

    # Scale down if positions exceed the max canvas area
    scale_x = max_canvas_w / max_x if max_x > max_canvas_w else 1.0
    scale_y = max_canvas_h / max_y if max_y > max_canvas_h else 1.0

    if scale_x < 1.0 or scale_y < 1.0:
        for node in nodes:
            x_val = int(node["left"].replace("px", "").split(".")[0])
            y_val = int(node["top"].replace("px", "").split(".")[0])
            new_x = max(start_x, int(start_x + (x_val - start_x) * scale_x))
            new_y = max(start_y, int(start_y + (y_val - start_y) * scale_y))
            node["left"] = f"{new_x}px"
            node["top"] = f"{new_y}px"

    return flow_result


# PID Management
PID_FILE = "agent.pid"


def write_pid_file() -> None:
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write PID file: {e}")


def remove_pid_file() -> None:
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"Failed to remove PID file: {e}")
            return


def main() -> None:
    try:
        logging.debug("Loading config from config.yaml...")
        config = load_config()
        logging.debug("Loaded FlowCreator configuration")

        # Write PID file immediately
        logging.debug("Writing PID file...")
        write_pid_file()
    except Exception:
        sys.stderr.write(f"FATAL EARLY MAIN ERROR:\n{traceback.format_exc()}\n")
        sys.stderr.flush()
        sys.exit(1)

    try:
        prompt_text = config.get('prompt', '')
        flow_filename = config.get('flow_filename', 'untitled.flw')
        llm_config = config.get('llm', {})
        host = llm_config.get('host', 'http://localhost:11434')
        model = llm_config.get('model', 'gpt-oss:120b-cloud')

        if _IS_REANIMATED:
            logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
            logging.info("=" * 60)
        logging.info("FLOWCREATOR AGENT STARTED")
        logging.info(f"Model: {model} @ {host}")
        logging.info(f"Flow filename: {flow_filename}")
        logging.info("=" * 60)

        if not prompt_text.strip():
            logging.error("No prompt configured. Set the 'prompt' field in config.yaml.")
            # Write empty result to signal completion with error
            _write_error_result("No prompt configured. Please set the 'prompt' field.")
            return

        # Load the agentic skill document
        skill_content = load_agentic_skill()
        if not skill_content:
            logging.error("agentic_skill.md not found or empty.")
            _write_error_result("agentic_skill.md not found or empty.")
            return

        from flow_knowledge import load_catalog, roster_prompt, select_types, design_prompt
        catalog = load_catalog()
        num_ctx = int(llm_config.get('num_ctx', 65536))
        max_prompt_chars = int(llm_config.get('max_prompt_chars', 180000))
        if num_ctx < 8192 or max_prompt_chars < 1000:
            raise ValueError("Invalid FlowCreator context limits")
        selection_prompt = roster_prompt(catalog) + "\nUSER OBJECTIVE:\n" + prompt_text
        if len(selection_prompt) > max_prompt_chars:
            raise ValueError("Agent selection exceeds max_prompt_chars; raise the configured context budget")
        selected = select_types(query_ollama(host, model, selection_prompt, num_ctx), catalog)
        logging.info("Selected agent capabilities: %s", ", ".join(selected))
        skill_content = design_prompt(skill_content, catalog, selected)

        # Build the full prompt for the LLM
        full_prompt = (
            f"{skill_content}\n\n"
            f"---\n\n"
            f"## USER REQUEST\n\n"
            f"Create a flow to accomplish the following objective:\n\n"
            f"{prompt_text}\n\n"
            f"Remember: respond ONLY with the JSON array as specified in the output format above. "
            f"Do not include any explanation or text outside the JSON array."
        )

        if len(full_prompt) > max_prompt_chars:
            raise ValueError("Selected agent reference exceeds max_prompt_chars; split the objective or raise the context budget")
        logging.info(f"Sending prompt ({len(full_prompt)} chars) to {model}...")

        # Query LLM
        try:
            response_text = query_ollama(host, model, full_prompt, num_ctx)
        except RuntimeError as e:
            logging.error(f"LLM query failed: {e}")
            _write_error_result(f"LLM query failed: {e}")
            return

        # Log the raw response for debugging. Deliberately NOT an
        # INI_SECTION_FLOWCREATOR block: the single authoritative section is
        # emitted at the end of main() once the .flw actually exists, so
        # Parametrizer / the chat LLM never see two competing sections.
        logging.info(f"--- RAW LLM RESPONSE ---\n{response_text}\n--- END RAW LLM RESPONSE ---")
        logging.info(f"LLM response received ({len(response_text)} chars)")

        # Write the raw intermediate script
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flow_creation_script.txt")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(response_text)
        logging.info(f"Written flow_creation_script.txt ({len(response_text)} chars)")

        # Parse the response
        agents = parse_flow_script(response_text)
        if not agents:
            logging.error("Failed to parse any agents from LLM response.")
            _write_error_result("Failed to parse agents from LLM response. Check flow_creation_script.txt for details.")
            return

        logging.info(f"Parsed {len(agents)} agents from LLM response")

        from flow_knowledge import resolve
        repair_attempts = int(llm_config.get('repair_attempts', 2))
        if not 0 <= repair_attempts <= 3:
            raise ValueError("repair_attempts must be between 0 and 3")
        for attempt in range(repair_attempts + 1):
            try:
                used = {resolve(agent.get("agent_type", ""), catalog) for agent in agents if isinstance(agent, dict)}
                if not used.issubset(selected):
                    raise ValueError("Flow used unselected capabilities; use the selected catalog only")
                flow_result = build_flow_result(agents)
                break
            except ValueError as error:
                if attempt == repair_attempts:
                    raise
                repair_prompt = (full_prompt + "\nThe previous plan failed validation: " + str(error)
                                 + "\nRepair it and return only the complete JSON array. Previous plan:\n"
                                 + json.dumps(agents, ensure_ascii=False))
                if len(repair_prompt) > max_prompt_chars:
                    raise ValueError("Repair prompt exceeds max_prompt_chars") from error
                logging.warning("Plan validation failed; bounded repair %s: %s", attempt + 1, error)
                response_text = query_ollama(host, model, repair_prompt, num_ctx)
                agents = parse_flow_script(response_text)
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(response_text)

        # Improve layout with topological ordering
        flow_result = improve_layout(flow_result)

        # Add metadata
        flow_result["status"] = "success"
        flow_result["flow_filename"] = flow_filename
        flow_result["agent_count"] = len(agents)

        # Do not publish a successful canvas result until the .flw is written.
        flw_path = _write_flw_file(flow_result, flow_filename, config)
        if not flw_path:
            raise RuntimeError("Could not write the generated .flw")

        # Write flow_result.json
        result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flow_result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(flow_result, f, indent=2, ensure_ascii=False)
        logging.info(f"Written flow_result.json with {len(flow_result['nodes'])} nodes and {len(flow_result['connections'])} connections")

        # Emit the section AFTER the .flw exists so the KV header can carry its
        # path (Parametrizer + the chat LLM read this).
        logging.info(
            f"INI_SECTION_FLOWCREATOR<<<\n"
            f"model: {model}\n"
            f"status: success\n"
            f"flw_path: {flw_path or ''}\n"
            f"flow_filename: {flow_filename}\n"
            f"agent_count: {len(agents)}\n"
            f"connection_count: {len(flow_result['connections'])}\n"
            f"\n"
            f"Flow '{flow_filename}' created with {len(agents)} agents "
            f"and {len(flow_result['connections'])} connections.\n"
            f">>>END_SECTION_FLOWCREATOR"
        )

        logging.info("FlowCreator agent finished successfully.")

    except Exception as e:
        logging.error(f"FlowCreator agent error: {e}")
        _write_error_result(str(e))
    finally:
        time.sleep(0.4)
        remove_pid_file()
        if _FAILED:
            raise SystemExit(1)

    # Exit code MUST reflect reality: the wrapped chat-agent runtime maps
    # exit 0 -> "completed", so exiting 0 after a failure would report a flow
    # that was never created as a SUCCESS. The canvas path is unaffected (it
    # keys off flow_result.json + the PID file, never the exit code).
    sys.exit(1 if _FAILED else 0)


def _resolve_output_dir(config) -> str:
    """Where the .flw is written. Honours an explicit output_dir, else the
    application's own Temp directory (Rule 15 - never the system temp)."""
    explicit = str(config.get('output_dir', '') or '').strip()
    if explicit:
        return explicit
    app_temp = (os.environ.get('TLAMATINI_TEMP') or '').strip()
    if app_temp:
        return app_temp
    return os.path.dirname(os.path.abspath(__file__))


def _write_flw_file(flow_result, flow_filename, config):
    """Convert flow_result.json into a real, canvas-loadable .flw on disk.
    Never raises - a conversion failure degrades to 'no .flw' and is logged."""
    global _FAILED
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from result_to_flw import convert  # vendored next to this script
    except Exception as e:
        logging.error(f"Could not import the .flw converter: {e}")
        _FAILED = True
        return ""
    try:
        name = (flow_filename or '').strip() or 'untitled.flw'
        if not name.lower().endswith('.flw'):
            name += '.flw'
        out_dir = _resolve_output_dir(config)
        os.makedirs(out_dir, exist_ok=True)
        flw_path = os.path.join(out_dir, name)
        with open(flw_path, 'w', encoding='utf-8') as f:
            json.dump(convert(flow_result), f, indent=2, ensure_ascii=False)
        logging.info(f"Written .flw file: {flw_path}")
        return flw_path
    except Exception as e:
        logging.error(f"Failed to write the .flw file: {e}")
        _FAILED = True
        return ""


# NOTE: FlowCreator is a no_input/no_output system agent - it has no
# target_agents to trigger, so there is deliberately no downstream-launch
# helper here (the canvas never wires it, and a chat run has no successors).


def _write_error_result(message: str) -> None:
    """Write an error flow_result.json so the frontend knows the agent failed.
    Also latches _FAILED so main() can exit NON-ZERO - the wrapped chat-agent
    runtime derives completed/failed from the exit code, so a silent exit 0
    here would report a flow that was never created as a SUCCESS."""
    global _FAILED
    _FAILED = True
    logging.info(
        f"INI_SECTION_FLOWCREATOR<<<\n"
        f"status: error\n"
        f"flw_path: \n"
        f"agent_count: 0\n"
        f"\n"
        f"{message}\n"
        f">>>END_SECTION_FLOWCREATOR"
    )
    result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flow_result.json")
    try:
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({"status": "error", "message": message, "nodes": [], "connections": []}, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to write error result: {e}")


if __name__ == "__main__":
    main()
