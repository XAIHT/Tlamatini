# LLM Reflection — Research Findings

## What is LLM Reflection?

LLM Reflection is a technique where language models evaluate and improve their
own outputs through iterative self-correction. Instead of generating a single
response, the model produces an answer, critiques it, identifies errors or
gaps, and then generates an improved response. This cycle can repeat multiple
times, progressively refining the output quality.

## Key Research Papers

### 1. Reflexion: Language Agents with Verbal Reinforcement Learning (Shinn et al., 2023)
- Introduces Reflexion, a framework that reinforces language agents through
  verbal feedback rather than weight updates
- Agents reflect on task feedback, store reflections in an episodic memory
  buffer, and use them to improve subsequent attempts
- Key insight: self-reflection text serves as a lightweight alternative to
  traditional RL reward signals

### 2. Self-Refine: Iterative Refinement with Self-Feedback (Madaan et al., 2023)
- Proposes a single-model approach where the LLM generates, critiques, and
  refines its own output
- No additional training or fine-tuning required
- Shows 5-20% improvement across diverse tasks (code generation, math, dialogue)

### 3. SuperCorrect: Advancing Small LLM Reasoning (ICLR 2025)
- Uses thought template distillation and self-correction
- Small LLMs can achieve reasoning quality approaching larger models through
  structured self-correction patterns
- GitHub: YangLing0818/SuperCorrect-llm

### 4. CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing (Gou et al., 2023)
- Extends self-correction by allowing the model to use external tools to
  validate its outputs
- The model generates, critiques using tools (search, code execution), then
  corrects based on tool feedback

## Core Mechanisms

### Self-Evaluation
The model assesses its own output for:
- Factual accuracy
- Logical consistency
- Completeness
- Code correctness (compilation, test passing)
- Adherence to constraints

### Iterative Refinement Loop
```
Generate -> Evaluate -> Identify Issues -> Reflect -> Regenerate -> ...
```

### Memory-Augmented Reflection
- Store past reflections in an episodic memory buffer
- Retrieve relevant reflections for new tasks
- Accumulate learned lessons across attempts

## Tlamatini Self-Healing as LLM Reflection

Tlamatini self-healing layer (agent/self_healing.py) is a production
implementation of LLM Reflection:

### Tactic Ladder (the reflection cycle)
1. **normal** — full request (initial generation)
2. **retry** — same request again (transient blip recovery)
3. **patient-retry** — wait, then retry with more patience
4. **trim-context** — reduce context to essentials, retry
5. **minimal** — strip to last 6 messages, retry
6. **plain-summary** — LAST resort: drop tools, summarize gathered work

### Key Properties
- **Never hangs**: 80s watchdog per attempt, daemon thread abandoned on timeout
- **Never discards work**: graceful degraded answer from already-completed agents
- **Never lies**: recovery_preamble prepends truthful banner to final answer
- **Live narration**: user sees recovery status in real-time
- **Cancel-honoring**: user Cancel stops within 250ms, even mid-hang

### Configuration
- `unified_agent_llm_step_max_tactics` (default 4096) — max retry budget
- `unified_agent_llm_step_timeout_seconds` (default 80) — per-attempt watchdog
- `TLAMATINI_SELF_HEAL_FAULT_RATE` — inject faults for testing (default: off)
- `TLAMATINI_SELF_HEAL_FAULT_MODE` — error|hang|mix (default: off)

### Transient vs Non-Transient Errors
- **Transient** (network blips, 429/500/502/503/504, timeouts, resets):
  trigger tactic-switching and retry
- **Non-transient** (real bugs: KeyError, bad schema): raised immediately,
  never hidden by retry loops

## Connection to This Skill

The adding-external-mcp skill was created through a process that itself
demonstrates LLM Reflection: Tlamatini researched the topic, attempted to
create the skill, encountered failures (transient network errors causing
300+ retry loops), and then on the next attempt refined her approach to be
more surgical and efficient — avoiding the same failure mode.

The skill itself enables adding MCP servers that can provide additional
tools for reflection (like the sequential-thinking MCP server, which
provides structured reasoning capabilities).

## Sources

- Shinn, N., et al. "Reflexion: Language Agents with Verbal Reinforcement Learning." arXiv:2303.11366 (2023)
- Madaan, A., et al. "Self-Refine: Iterative Refinement with Self-Feedback." arXiv:2303.17651 (2023)
- Gou, Z., et al. "CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing." arXiv:2305.11738 (2023)
- YangLing0818/SuperCorrect-llm (ICLR 2025)
- Tlamatini agent/self_healing.py — production implementation
