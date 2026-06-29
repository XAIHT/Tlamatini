<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# ESPHome Template Project (Tlamatini)

A minimal, ready-to-flash [ESPHome](https://esphome.io) device config that Tlamatini's
**ESPHomer** agent uses as the canonical "first device" sample: a phone-controlled light.

ESPHome turns ESP32 / ESP8266 / RP2040 / BK72xx boards into smart-home devices from a
simple YAML file — no C++. ESPHomer drives the `esphome` CLI directly (validate /
compile / upload / logs / clean) and can also **generate** a config like this one via
`action='new_config'`.

## Files

- `tlamatini-light.yaml` — an on/off light on the board's onboard LED (GPIO2 on ESP32),
  exposed over the ESPHome native API so a hub (e.g. Home Assistant) can control it.

## Use it through ESPHomer (from chat)

1. `action='write_config'` with `config_path='<folder>/tlamatini-light.yaml'` and the
   contents of this file — or `action='new_config'` to generate a fresh one.
2. Edit `wifi: ssid/password` to your network.
3. `action='compile'` to build the firmware (first compile downloads the toolchain).
4. Connect the board over USB, then `action='upload'`. After the first USB flash you can
   upload over-the-air by passing `port='<device-ip>'`.
5. Adopt the device into your hub and toggle **"Tlamatini Light"** from your phone.

> The WiFi credentials here are placeholders. Replace them before flashing.
