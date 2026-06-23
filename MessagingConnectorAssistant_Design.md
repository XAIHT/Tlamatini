# MessagingConnectorAssistant — Design

**Goal (Angela's):** the user tells Tlamatini their phone number and *nothing else*; Tlamatini does every step to send/receive on **Telegram** and **WhatsApp**, even if it takes days. End state: Tlamatini says *"Everything's ready — what number do you want to message?"*

This document is honest about the **one wall that exists for everyone on Earth**, then designs the system that gets as close to "just the number" as physics and the platforms allow — **software now**, and a **hardware gadget you can sell** that removes even the last tap.

---

## 1. The one wall (and why it's not you, me, or a skill issue)

Telegram and WhatsApp **deliberately** require **one proof-of-ownership step** when a number is first connected:

- **Telegram:** a **login code** sent to that number (sometimes + a 2FA password).
- **WhatsApp:** a **6-digit code** (SMS/call) or a **QR scan** from the phone.

This step exists *on purpose* so that **no software — nobody's, anywhere — can silently take over a phone number.** If a program could fully claim a number with zero human proof, every scammer on Earth would empty everyone's accounts overnight. So "the user does literally nothing" is blocked **by design**, for everyone, not just us.

**So the real, achievable target is:** turn a *week of confusing setup* into **ONE tap** ("type the code Telegram just sent you" / "scan this QR"). And then — with hardware — into **ZERO taps** (insert SIM). That's the whole design.

---

## 2. What Tlamatini CAN fully automate (everything except that one proof)

The MessagingConnectorAssistant does ALL of this itself, in the background, no user involvement:

- Install/config dependencies (Telethon, the WhatsApp client, etc.).
- Open the connection, request the login code / QR.
- Catch the session and **save it** so it never has to log in again.
- Write the values into `config.json` / the agent config.
- Restart what needs restarting.
- Send a **test message** and confirm it worked.
- Retry, wait, and resume **over days** if a step is slow (verification review, rate limits) — and just tell the user *"still working, I'll ping you when it's ready."*

The user's total involvement shrinks to: **give the number → do one verification tap → done.**

---

## 3. Software system — `MessagingConnectorAssistant`

A **Step-by-Step wizard agent** (new) that orchestrates the existing Telegramer / Whatsapper / TeleTlamatini / WhatsTlamatini agents, plus **auto-detection** baked into those agents so they pick the right mode by themselves.

### 3a. Auto-detect "operation manner" (the smartness you asked for)
Whatsapper & WhatsTlamatini already have a `provider` switch. We extend the auto-pick so each agent, at launch, **detects what's configured and chooses the mode with zero user choice:**

| If it finds… | It uses… |
|---|---|
| Meta `phone_number_id` + `access_token` | **Meta Cloud API** |
| Twilio SID + token + from-number | **Twilio** (easiest official) |
| A linked WhatsApp-Web session | **Unofficial web** (free-form, ToS-risk) |
| Telegram session string | **Telethon user account** |
| Only a bot token | **Telegram bot** |
| Nothing | → launch the **wizard** to set one up |

So the user never says "use Meta" or "use Twilio" — Tlamatini figures it out.

### 3b. Telegram path (the *almost* fully-automatic one)
1. Tlamatini asks for the number.
2. It needs `api_id`/`api_hash` **once** (from my.telegram.org). Either the user pastes them once, OR Tlamatini ships a shared pair.
3. Tlamatini calls Telegram → Telegram sends a **login code** to the user's Telegram app.
4. **User's ONE step:** tells Tlamatini the code (+ 2FA password if set).
5. Tlamatini saves the session string → done forever. Sends a test.

### 3c. WhatsApp paths (pick by how much pain the user accepts)
- **Twilio (recommended easy):** user signs up, pastes **3 values** (SID, token, WhatsApp number). Free 2-min sandbox to test. Tlamatini does the rest.
- **Meta Cloud (cheapest at scale):** the full guide we already wrote.
- **Unofficial web (closest to "just works", ToS-risk):** Tlamatini shows a **QR**; user scans it once with their phone's WhatsApp → linked. ⚠️ Against WhatsApp's terms; risk of number ban. Offer it only with a clear warning.

### 3d. The 2 sample "fancy" prompts (Step-by-Step + Multi-Turn)
**Telegram:**
> Tlamatini, be my **Messaging Connector Assistant** and set up **Telegram** for me, one step at a time. Here's my number: `+__________`. Do everything yourself — install what's needed, request my login code, save my session, and send a test to me. Pause and wait for me only when you truly need the code or my password. Take as long as you need; if something is slow, tell me you'll continue and notify me. END-RESPONSE

**WhatsApp:**
> Tlamatini, be my **Messaging Connector Assistant** and set up **WhatsApp** for me, one step at a time. Here's my number: `+__________`. Detect the easiest method available, get the single key/QR you need from me, store it, and send a test. Do every other step yourself, in the background, even across days; just tell me the one thing you need and wait. END-RESPONSE

---

## 4. Hardware product — "Tlamatini Link" (removes even the last tap)

Your instinct was right, and here's the clever part: **the proof-code goes to the SIM.** If Tlamatini controls a small gadget that *holds the user's SIM*, it can **read the OTP itself** — so the user's only action becomes **"insert SIM."** Eureka, for real.

### The gadget
- A **microcontroller + cellular modem** holding the user's SIM:
  - **ESP32** (built-in WiFi — matches "wifi I don't know"; you already have the **ESP32er** agent) **or STM32F** (you have **STM32er**),
  - **+ a SIM/LTE modem module** (e.g. SIM7600 4G, or Quectel) with a SIM slot + antenna.
- Talks to Tlamatini over **USB-serial or WiFi**.
- Tlamatini drives it with **AT commands** to:
  - register on the network,
  - **auto-read the incoming verification SMS** (`AT+CMGL`/`CMGR`),
  - feed that code straight into the Telegram/WhatsApp login — **no human typing.**

### The user experience you wanted
1. User buys the **Tlamatini Link** dongle.
2. User **puts their SIM in it** (or a cheap second SIM dedicated to messaging).
3. Tells Tlamatini the number → Tlamatini reads the OTP off the modem and finishes everything.
4. **That's the only step.** True "just the number."

### Why this fits YOU specifically
- The firmware is written by your **own ESP32er / STM32er / Arduiner** agents — this is a product your ecosystem builds itself.
- A Python **host driver** (a new pool agent, e.g. `SimModemer`) drives the modem; the wizard calls it.
- BOM ~ $20–40 (board + LTE module + antenna). Genuinely sellable.

### Honest caveats
- Use a **4G** module (2G networks are being shut down).
- For **WhatsApp**, auto-OTP + a headless client is the **unofficial** route → **ToS / ban risk**; fine for the user's *own* number, not for abuse/mass sending.
- A SIM dedicated to the gadget avoids fighting the user's daily phone for the number.

---

## 5. Recommended build order (so we ship value fast, not a 6-month moonshot)

1. **Twilio "easy mode" in Whatsapper** + **auto-detect** provider/mode (half-day; biggest UX win for free).
2. **`MessagingConnectorAssistant` wizard agent** + the 2 sample prompts (the guided "give me your number" experience over the existing agents).
3. **Telegram auto-login** in the wizard (gets Telegram to "one tap").
4. **Spec + prototype "Tlamatini Link"** hardware (the SIM-modem dongle) → the "zero tap" product to sell.

---

## 6. The honest one-liner

- **Today (software):** "give your number → **one verification tap** → Tlamatini does everything else, even over days."
- **With the dongle (hardware):** "**insert your SIM** → Tlamatini does everything else." — the literal *"just the number"* dream, and a product with your name on it.

Not impossible. Just staged. 🚀
