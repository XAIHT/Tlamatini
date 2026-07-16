# Proposal — Widen STM32er to the ENTIRE ST 32-bit line (Blue Pill → STM32N6)

**Author:** prepared for Angela López Mendoza, creator of Tlamatini
**Date:** 2026-07-15
**Status:** PROPOSAL (not yet implemented)
**Agent:** `STM32er` (mission-critical — robot firmware)

---

## 1. The one key fact

Today STM32er can really only build/flash **one** device — **STM32F407VG** — because it is welded to the single-device `STM32TemplateProjectMCP`, and its preflight **refuses** anything cross-family. It won't even flash a **Blue Pill (STM32F103)**. To cover the full ST line up to the **STM32N6**, STM32er must stop owning one hand-written template and instead **dispatch to a device-aware build backend that already knows every ST part.**

---

## 2. Where STM32er is welded shut today (verified in the code)

`agent/agents/stm32er/stm32er.py`:

```python
# The MCP template is configured for ONE family/device; the preflight validates
# the REQUESTED device against it and REFUSES a cross-family mismatch (fail-safe).
_STM32F_FAMILIES = ("STM32F0","STM32F1","STM32F2","STM32F3","STM32F4","STM32F7")

def _device_family(device): ...        # returns "" for ANY non-STM32F part
# _preflight: if requested_family != template_family -> family_supported = False -> REFUSE
```

Consequences:

1. `_device_family` only recognises **STM32F0–F7**. A `STM32G0`, `H7`, `L4`, `U5`, `WB`, `C0`, or `N6` maps to `""` — it can't even be modelled.
2. The preflight **refuses cross-family** — so the Blue Pill (F1) is rejected against the F407 (F4) template. It flashes exactly F407 and nothing else.
3. The `config.yaml` `device: ""` key exists but only picks *within* the one template's family.

This safety (never mis-target a linker script) is **correct and must be preserved** — but it currently doubles as a hard ceiling. The proposal keeps the guarantee and lifts the ceiling.

---

## 3. The core insight

You **cannot** hand-author per-family linker + startup + HAL templates for ~18 STM32 families. You must delegate build/flash to a backend that **already** contains every ST part's memory map, startup and HAL. Two production-grade backends exist:

| Backend | Coverage | Nature |
|---|---|---|
| **PlatformIO `ststm32`** | Blue Pill (F103) → F7, G0/G4, L0/L1/L4/L5, H7, U5, WB — ~1000+ boards | Same proven pattern **ESP32er already uses** (direct `pio` CLI, zero-config bootstrap). Lags newest silicon: H5 *in progress*, **no C0 / WBA / N6**. |
| **ST-native STM32CubeCLT + CubeMX (CMake)** | **Every** ST part, present & future — incl. C0, H5, U0/U5, WBA, WL, and **STM32N6** | ST's own all-in-one CLI: `arm-none-eabi-gcc` + `STM32_Programmer_CLI` + GDB + CMake/Ninja. ST ships new-silicon support here first. Heavier install; CubeMX headless generation is fiddlier; N6 adds signing/external-flash. |

Neither alone reaches everything — PlatformIO can't reach the N6; CubeCLT is heavier for the mainstream parts. **So use both, routed by device family.**

---

## 4. Recommended architecture — a pluggable "build backend" behind STM32er

STM32er becomes a **device-aware dispatcher**. The requested `device`/`board` picks the backend automatically:

| Backend | Reaches | How | New-code effort |
|---|---|---|---|
| **B1 — PlatformIO `ststm32`** *(new; mirrors ESP32er)* | Blue Pill (F103) → F7, G0/G4, L0/L1/L4/L5, H7, U5, WB | direct `pio run` with `board=<id>` | **LOW** — clone ESP32er |
| **B2 — Legacy Template MCP** *(kept)* | STM32F407VG exactly (today's flow) | existing `STM32TemplateProjectMCP` | **ZERO** — already there |
| **B3 — ST-native CubeCLT + CMake** *(new)* | Everything, incl. **H5, C0, WBA, and STM32N6** | CubeMX headless → CMake project → CubeCLT `cmake`/`gcc` build → `STM32_Programmer_CLI` flash (N6: + signing + external loader) | **HIGH** (esp. N6) |

A single **device → backend routing table** decides which backend runs; the preflight validates per-backend. B2 stays so nothing that works today regresses.

### Full ST 32-bit family coverage map (target end-state)

| Family | Core | Example board | Backend | Notes |
|---|---|---|---|---|
| STM32C0 | M0+ | STM32C0316-DK | B3 | ultra-low-cost; PIO lacks it |
| STM32F0 | M0 | STM32F0DISCOVERY | B1 | |
| STM32F1 | M3 | **Blue Pill `bluepill_f103c8`** | B1 | the low anchor |
| STM32F2 | M3 | Nucleo-F207 | B1 | |
| STM32F3 | M4 | STM32F3DISCOVERY | B1 | |
| STM32F4 | M4 | **F407 (today)**, Black Pill F411 | B1/**B2** | B2 = current template |
| STM32F7 | M7 | STM32F746G-DISCO | B1 | |
| STM32G0 | M0+ | Nucleo-G071RB | B1 | |
| STM32G4 | M4 | Nucleo-G474RE | B1 | |
| STM32L0/L1 | M0+/M3 | Nucleo-L053/L152 | B1 | |
| STM32L4/L4+ | M4 | Nucleo-L476RG | B1 | |
| STM32L5 | M33 (TrustZone) | Nucleo-L552ZE-Q | B1/B3 | |
| STM32U0 | M0+ | Nucleo-U083 | B3 | new; PIO partial/none |
| STM32U5 | M33 (TrustZone) | Nucleo-U575ZI-Q | B1/B3 | |
| STM32H5 | M33 | Nucleo-H563ZI | B3 | PIO *in progress* |
| STM32H7 | M7 (some dual M7+M4) | Nucleo-H743ZI, H747 | B1 | |
| STM32WB | M4+M0+ (BLE/Zigbee) | Nucleo-WB55 | B1 | |
| STM32WBA | M33 (BLE 5.x) | Nucleo-WBA52 | B3 | new; PIO none |
| STM32WL | M4+M0+ (LoRa) | Nucleo-WL55JC | B3 | |
| **STM32N6** | **Cortex-M55 @ 800 MHz + Neural-ART NPU** | **Nucleo-N657X0-Q / STM32N6570-DK** | **B3** | **the high anchor — see §6** |
| STM32MP1/MP2 | Cortex-A (Linux MPU) | — | **out of scope** | OpenSTLinux/U-Boot, not bare-metal firmware |

---

## 5. Phasing (Blue-Pill→H7 lands fast; N6 is the flagship finale)

**Phase 0 — De-weld the gate (small, immediate).** Broaden `_device_family` / `_STM32F_FAMILIES` to the full ST family map, and change the preflight from *"refuse cross-family"* to *"route to the backend that supports the requested family."* This alone stops the false refusals (Blue Pill stops being rejected).

**Phase 1 — PlatformIO backend B1.** New `stm32_backend: platformio`. Clone ESP32er's `pio` zero-config bootstrap + fail-safe preflight verbatim. Ship an `STM32PlatformIOTemplateProject` scaffold + a board catalog. **Delivers Blue Pill → H7/U5 — the 80% coverage win at ~20% of the effort.**

**Phase 2 — ST-native CubeCLT backend B3 (non-N6 first).** Zero-config bootstrap of STM32CubeCLT (+ CubeMX). CubeMX headless `.ioc`→CMake generation → CubeCLT build → `STM32_Programmer_CLI` flash. Prove on **H5 / C0 / WBA / U5** — the parts PlatformIO can't reach.

**Phase 3 — STM32N6 flagship.** On top of B3, add the N6 specials (§6). First cut: **build + sign + development-boot (run-from-RAM)**; full external-flash production boot is a stretch goal.

---

## 6. Why the STM32N6 is the hard part (and how we tame it)

The N6 is not "just another family." Confirmed from ST's docs:

1. **No internal user flash.** It boots via the **boot ROM** into a **development boot** (load-and-run into its large internal RAM) or from **external flash** (OSPI/XSPI). "Flashing" an N6 means external-memory programming with an **ExternalLoader**, or dev-boot into RAM.
2. **Secure-boot life cycle** (fuse-driven states: *Closed/Unlocked → Locked/Provisioned → RMA*). Even in the open dev state, the boot ROM expects an **FSBL** (First-Stage Boot Loader / ST-RSSE-FW); provisioned states **enforce authentication**.
3. **Signing.** The image needs a signed header (`STM32_SigningTool_CLI`) for the boot ROM to accept it.
4. **Cortex-M55 + Helium (MVE)** — needs a recent `arm-none-eabi-gcc` (v13+). **CubeCLT ships it.**
5. **Neural-ART NPU** — optional AI hook (`X-CUBE-N6-AI`), a stretch.

**N6 fail-safe (extends STM32er's mission-critical contract):** refuse to "flash" if `boot_mode=ext-flash` but no external loader is present, or if the image is unsigned when the life-cycle state requires it. The worst N6 outcome is bricking a secure-boot device — so we **refuse rather than guess**, exactly as STM32er already does for linker scripts.

---

## 7. New config surface (`config.yaml`)

```yaml
device: ""             # e.g. STM32F103C8, STM32H750VB, STM32N657X0 (blank = board/backend default)
board: ""              # e.g. bluepill_f103c8, nucleo_h743zi, STM32N6570-DK (implies device + backend)
stm32_backend: auto    # auto | platformio | template_mcp | cubeclt
# --- ST-native / N6 only ---
external_loader: ""    # ExternalLoader .stldr for N6 ext-flash (STM32CubeProgrammer)
boot_mode: dev         # dev (run-from-RAM) | ext-flash
sign: false            # sign the image with STM32_SigningTool_CLI (N6)
sign_key: ""
```

`board` is the friendliest knob (it implies both device and backend). `auto` routing keeps the LLM prompts simple ("build a Blue Pill blink" just works).

---

## 8. Surfaces touched (per the agent-creation contract)

- **`stm32er.py`** — full ST family map, backend **dispatcher**, three inline backend modules (no `agent.*` import, like ESP32er/acpxer), extended preflight, new actions (`list_boards`, `select_backend`, N6 `sign`).
- **`config.yaml`** — the keys in §7 + docs.
- **`config.json`** globals via `tools._seed_global_agent_defaults` (pio dir, CubeCLT dir, board-catalog path) — same pattern as `pio_executable` / `stm32_mcp_server_script`.
- **Bundled scaffolds** — `STM32PlatformIOTemplateProject`, `STM32CubeCMakeTemplate`, `STM32N6Template` (default parent `<app>/Templates`).
- **Docs** — `docs/claude/agents.md` STM32er entry, `agents_descriptions.md`, `README.md`, `create_new_agent.md` refs.
- **Demo prompts** — Catalog-of-Prompts entries: *Blue Pill blink*, *H7/U5 build*, *N6 validate+sign* (contiguous `idPrompt`, append at next free slot).
- **Tests** — unit tests for the family map + router + preflight, plus a **visible HIL demo per tier** (Blue Pill, a Nucleo, then N6) per Angela's "all tests visible" rule.
- **Exec Report / Ask-Execs** — already captured (wrapped `chat_agent_stm32er`); STM32er stays **tier C (no-ask)** — hardware, visible operation.

---

## 9. Honest risks

1. **N6 is genuinely hard** — secure boot, external flash, signing. First cut = build+sign+dev-boot; full ext-flash production boot is a stretch and needs a **real Nucleo-N657X0-Q / STM32N6570-DK in hand** to prove visibly.
2. **PlatformIO lags newest silicon** (H5 in progress; no C0/WBA/N6) — precisely why B3 exists.
3. **Install weight** — CubeCLT + CubeMX are ~1–2 GB; zero-config download is slow on first run (like the espressif32 first build).
4. **Hardware to validate each tier** — at minimum a Blue Pill + one Nucleo (H7/U5) + eventually an N6 DK, each proven with a visible flash + on-board evidence (LED/serial), never a stale log.

---

## 10. Recommendation

Adopt the **hybrid, phased** plan:

- **Phase 0 + 1** (family gate + PlatformIO) → Blue Pill through H7/U5 **fast and low-risk**, by cloning ESP32er's proven pattern.
- **Phase 2 + 3** (CubeCLT + N6) → the ST-native reach to H5/C0/WBA and the **STM32N6 flagship**.

This is the maximal-coverage answer that **actually reaches the N6**, while preserving STM32er's mission-critical *never-mis-target / never-flash-blind* guarantee.

---

*Sources for the tooling facts: STMicroelectronics STM32CubeCLT command-line toolset docs; PlatformIO `platformio/platform-ststm32` platform docs & board registry (Nucleo-U575ZI-Q supported; STM32H5 tracked in issue #758); ST STM32N6 boot/security life-cycle & FSBL documentation.*
