---
name: weather
description: Look up current weather and short forecast for a location via Open-Meteo (no API key required).
metadata:
  openclaw:
    emoji: "🌤"
    requires: { env: [] }
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_apirer"]
    requires_mcps: []
    budget:
      max_iterations: 2
      max_seconds: 20
      max_tokens: 4000
    permissions:
      filesystem: { read: [], write: [] }
      shell:     []
      network:   allow
      db:        deny
    inputs:
      - { name: latitude,  type: number, required: true }
      - { name: longitude, type: number, required: true }
    outputs:
      - { name: current,  type: object, required: true }
      - { name: hourly,   type: object, required: false }
    triggers:
      keywords: ["weather","forecast","temperature"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Weather skill

Base URL: `https://api.open-meteo.com/v1/forecast`.

Compose:
```
?latitude=${input.latitude}&longitude=${input.longitude}
&current=temperature_2m,weather_code,wind_speed_10m
&hourly=temperature_2m,precipitation
```

Issue with `chat_agent_apirer`. Return the parsed JSON's `current` and
`hourly` blocks. Open-Meteo is free for non-commercial use and does not
require an API key.
