<!--
═══════════════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove
═══════════════════════════════════════════════════════════════════════════
-->

# ESPHomeTemplateProject

A known-good **ESPHome smart-home baseline** — two working devices, shared
configuration, and credentials kept out of git.

ESPHome devices are described in **YAML, not C++**: you declare what the device
*has* (a light, a sensor, a switch) and ESPHome generates, compiles and flashes
the firmware for you. This project is the shape ESPHomer scaffolds when you run
`action: scaffold_template`.

## What's in it

```
ESPHomeTemplateProject/
├── tlamatini-light.yaml      device #1 — a phone-controllable light (SELF-CONTAINED)
├── tlamatini-sensor.yaml     device #2 — a sensor node (packages + secrets)
├── common/base.yaml          shared logger / api / ota / wifi blocks
├── secrets.yaml.example      copy to secrets.yaml and fill in  (gitignored)
└── .gitignore                keeps secrets.yaml and .esphome/ out of git
```

### The two devices are deliberately different shapes

**`tlamatini-light.yaml` is self-contained.** Everything it needs is in the one
file, credentials included. Copy it anywhere and it works. That is the right
shape for your first device, when every extra moving part is one more thing that
can go wrong.

**`tlamatini-sensor.yaml` is the grown-up shape.** It pulls the connectivity
blocks from `common/base.yaml` via `packages:`, and reads credentials from
`secrets.yaml` via `!secret`. That is the right shape once you have more than one
device: adding a tenth is three lines, and changing your WiFi password is one
edit instead of ten.

Start with the first, graduate to the second. The sensor device uses **only
on-board sensors** (uptime, WiFi signal, internal temperature), so it compiles
and runs on a bare dev board with nothing wired to it.

> ⚠️ `!include` and `!secret` are ESPHome's own YAML tags, so `tlamatini-sensor.yaml`
> and `common/base.yaml` cannot be read by a plain `yaml.safe_load`. That is
> expected — ESPHome's loader understands them. Run `esphome config <file>` to
> see the fully resolved configuration.

## First run

1. **Copy the secrets file** and fill in your WiFi:
   ```bash
   cp secrets.yaml.example secrets.yaml
   ```
   `secrets.yaml` is already in `.gitignore`. Keep it that way.

2. **Check the config parses** before touching hardware:
   ```bash
   esphome config tlamatini-light.yaml
   ```

3. **Compile:**
   ```bash
   esphome compile tlamatini-light.yaml
   ```
   The first compile downloads the platform and toolchain (several hundred MB),
   once.

4. **Flash over USB** — the first flash *must* be wired:
   ```bash
   esphome upload tlamatini-light.yaml
   ```

5. **Watch it:**
   ```bash
   esphome logs tlamatini-light.yaml
   ```

6. **Adopt it** in Home Assistant (or any hub that speaks the ESPHome native
   API) and toggle the light from your phone.

After the first USB flash, every later update can go **over the air** — pass the
device's IP instead of a serial port.

## Driving it from Tlamatini (ESPHomer)

ESPHomer installs ESPHome itself on first use, so the only thing you install is
your board's USB-serial driver.

| `action` | What it does | Board needed? |
|---|---|---|
| `validate` | Preflight: is `esphome` resolvable, does the YAML exist, is a port or OTA host reachable? Refuses rather than mis-run. | no |
| `scaffold_template` | Copies **this whole project** into `project_dir`. | no |
| `new_config` | Generates ONE fresh device YAML from parameters (`name`, `platform`, `board`, `led_pin`). Set `use_secrets: true` to emit `!secret` + a `secrets.yaml`. | no |
| `config` | `esphome config` — resolve and validate the YAML. | no |
| `compile` | `esphome compile` — build the firmware. | no |
| `upload` | `esphome upload` — flash over USB, or OTA when `port` is an IP. | **yes** |
| `logs` | Bounded `esphome logs` for `monitor_seconds`. | **yes** |
| `run` | Upload, then tail the logs. | **yes** |
| `scaffold_compile_upload` | The whole lifecycle in ONE run. | optional |
| `write_config` / `read_config` | Author or read a device YAML directly. | no |

A natural chat prompt:

> *Using ESPHomer, scaffold the ESPHome template project into
> `C:\Development\MyHome`, then compile `tlamatini-light.yaml` and show me the result.*

## Retargeting another board

Change the platform block at the top of the device YAML:

```yaml
esp32:                 # or esp8266: / rp2040: / bk72xx:
  board: esp32dev      # d1_mini / rpipicow / generic-bk7231n-qfn32-tuya
```

…and move the LED pin if your board's LED is elsewhere (ESP8266 boards usually
GPIO2, RP2040 Pico W GPIO25).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Secret 'wifi_ssid' not defined` | No `secrets.yaml`. | `cp secrets.yaml.example secrets.yaml` and fill it in. |
| `Could not find file 'common/base.yaml'` | Ran ESPHome from another directory. | Run from the project root, or pass an absolute path. |
| Upload stalls at `Connecting...` | Board not in bootloader mode. | Hold **BOOT**, tap **EN/RST**, release **BOOT**, retry. |
| Device never joins WiFi | Wrong credentials, or 5 GHz-only network. | ESP32/ESP8266 are **2.4 GHz only**. Check the band. |
| OTA upload refused | Device offline, or wrong IP. | Confirm the IP from the hub, or re-flash over USB. |
| Board not listed at all | Missing USB-serial driver. | Install CP210x or CH34x, then re-plug. |

## License

MIT — see `LICENSE` in the standalone repository distribution.
