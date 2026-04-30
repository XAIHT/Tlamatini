---
name: summarize
description: Summarize a long text or file into a tight, faithful brief at a target word count.
metadata:
  openclaw:
    emoji: "✂️"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_summarizer"]
    requires_mcps: []
    budget:
      max_iterations: 3
      max_seconds: 60
      max_tokens: 12000
    permissions:
      filesystem:
        read:  ["${input.file_path}"]
        write: []
      shell:   []
      network: deny
      db:      deny
    inputs:
      - { name: file_path,    type: string,  required: false,
          description: "Path of the file to summarize. Either file_path OR text must be provided." }
      - { name: text,         type: string,  required: false }
      - { name: target_words, type: integer, required: false, default: 150 }
    outputs:
      - { name: summary,      type: string,  required: true }
      - { name: word_count,   type: integer, required: true }
    triggers:
      keywords: ["summarize","tl;dr","brief","abstract"]
---

# Summarize

Reduce input to ~`${input.target_words}` words while preserving:
- the central claim or finding
- every named entity that drives the conclusion
- numbers and dates
- caveats and limitations explicitly noted

Forbid:
- adding facts not present in the source
- removing direct contradictions or risk language
- adopting a rhetorical tone different from the source

Return `{ summary, word_count }`.
