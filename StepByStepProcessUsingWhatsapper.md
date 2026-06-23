# Step‑By‑Step: Make Tlamatini's Whatsapper Send a Real WhatsApp Message

**Goal:** go from *nothing* to Tlamatini sending a WhatsApp like
*"Tlamatini, send a WhatsApp to Ana Ricardo Lazcano telling her I'll see her at lunch tomorrow."*

Whatsapper now runs on **Meta's official WhatsApp Cloud API** (the professional, enterprise backbone — the same one WhatsTlamatini uses). No third‑party gateway, **no BSP middleman needed** (despite what BSP blogs claim — Meta's Cloud API is directly usable).

By the end you will have just **two values** that Tlamatini needs:

| Value | What it is |
|---|---|
| `whatsapp_phone_number_id` | The ID of the WhatsApp number that **sends** (NOT the phone number itself — a long numeric ID) |
| `whatsapp_access_token` | A token that authorizes sending (start with a 24‑hour test token, then make it permanent) |

> ⏱️ Time: ~20–30 min for the first **free test message**. Going fully "production with my own number" adds business verification (can take a day or two and may involve Meta).

---

## 💰 The money truth (read this first — it's not what blogs scare you with)

- **Creating everything and getting the API is FREE.** Meta does not charge for the app, the API, or the test number.
- **Your FIRST test message is FREE** — we'll use Meta's **test number** + the pre‑approved **`hello_world`** template sent to your own phone. Test numbers don't bill. **No credit card needed for the test.**
- **You only pay once you use your OWN business number in production**, and even then:
  - **Service messages = FREE** — any reply you send within **24 hours** of the other person messaging you costs **$0**.
  - **Template messages (cold, business‑initiated) are billed per delivered message.** Authentication template to the US ≈ **$0.004**; Marketing varies by country (≈ $0.009 in India up to ≈ $0.12 in Germany); Utility is much cheaper than Marketing.
  - You add a payment method (card) **later**, only when you switch to a real number. You'll get a small free allowance to start.

**Bottom line:** follow Parts A–E and you'll send a real WhatsApp **for free, today**. Parts F–G are for "permanent + my own number."

Sources: [Meta — WhatsApp Cloud API Get Started](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/), [WhatsApp Business pricing (2026)](https://www.engagelab.com/blog/whatsapp-business-api-pricing), [Cloud API setup & cost guide 2026](https://chatarmin.com/en/blog/whatsapp-cloudapi).

---

# PART A — Accounts you need (5 min)

You need a normal Facebook login and a Meta **Business** portfolio. You do NOT need a Facebook Page or to post anything.

- [ ] **A1.** Have a Facebook account (any personal account works as the login). If you don't, create one at <https://www.facebook.com/>.
- [ ] **A2.** Create a Meta Business portfolio (free): go to <https://business.facebook.com/> → it will offer to **create a business account** → give it a business name (anything, e.g. "XAIHT") + your name + your email → **Create**.
  - This is just an organizational container. It's free and instant.

---

# PART B — Create the developer app and add WhatsApp (5 min)

- [ ] **B1.** Go to **Meta for Developers**: <https://developers.facebook.com/> → click **Get Started** (top right) and finish the quick developer registration (verify your account, accept terms).
- [ ] **B2.** Go to **My Apps**: <https://developers.facebook.com/apps/> → **Create App**.
- [ ] **B3.** App type: when asked *"What do you want your app to do?"*, the simplest path is to pick **Other** → **Next** → choose app type **Business** → **Next**.
  - Give the app a name (e.g. `Tlamatini WhatsApp`) → pick your **Business portfolio** from Part A → **Create app** (it may ask for your password).
- [ ] **B4.** On the app dashboard, find the **WhatsApp** product and click **Set up**.
  - It will auto‑create a **test WhatsApp Business Account** and a **test business phone number** for you. 🎉 This is what makes the first message free.

---

# PART C — Grab your two values + the test number (3 min)

- [ ] **C1.** In the app's left menu: **WhatsApp → API Setup**.
- [ ] **C2.** On that page you'll see:
  - **"From" — a test phone number** with a **Phone number ID** under it → **this is your `whatsapp_phone_number_id`. Copy it.**
  - A **WhatsApp Business Account ID** (save it too; handy later).
  - A **Temporary access token** with a **Generate access token** button → click it → **this is your `whatsapp_access_token` for testing. Copy it.**
    - ⚠️ The temporary token **expires in 24 hours**. Fine for today's test; Part F makes it permanent.

You now have both values. Keep them somewhere safe for a moment.

---

# PART D — Add YOUR phone as a test recipient (2 min)

The test number can only message phone numbers you've verified (up to 5).

- [ ] **D1.** Still on **API Setup**, find the **"To"** field → **Manage phone number list** (or "Add recipient").
- [ ] **D2.** Enter the phone number you want to receive the test (e.g. your own mobile, with country code) → Meta sends it a **6‑digit code** on WhatsApp → enter the code to verify.
  - Add Ana's number here too if you want to test sending to her.

---

# PART E — Send your FIRST message (free) — two ways

### Way 1 — Prove it works straight from Meta (30 seconds)
- [ ] **E1.** On the **API Setup** page there's a **"Send message"** sample (a `curl` snippet, pre‑filled with your token, phone_number_id, and the `hello_world` template). Click **Send**.
- [ ] **E2.** Check the recipient phone → a "Hello World" WhatsApp arrives. ✅ Meta side works.

### Way 2 — Send it through Tlamatini's Whatsapper (the real goal)

- [ ] **E3. Put the two values into Tlamatini.** Open `Tlamatini/agent/config.json` and set:
  ```json
  "whatsapp_phone_number_id": "PASTE_YOUR_PHONE_NUMBER_ID",
  "whatsapp_access_token": "PASTE_YOUR_TOKEN",
  ```
  (Leave `whatsapp_graph_base` and `whatsapp_api_version` as they are.)
  - 🔒 The token is a secret. `config.json` is the established home for secrets in Tlamatini (like the Anthropic key). If you'd rather not put it in the file, you can instead set Windows environment variables `WHATSAPP_PHONE_NUMBER_ID` and `WHATSAPP_ACCESS_TOKEN` — Whatsapper reads those too.
- [ ] **E4. Add the person to the Contacts book.** Open `contacts.json` (next to `config.json`) and add an entry (create the file if it doesn't exist):
  ```json
  {
    "contacts": [
      { "name": "Ana Ricardo Lazcano",
        "aliases": ["Ana", "Ana Lazcano"],
        "whatsapp": "+52 1 555 555 0000" }
    ]
  }
  ```
  (Use the **real** number, with country code. The leading `+` and spaces are fine — Whatsapper strips them.)
- [ ] **E5. Restart Tlamatini** (close and relaunch the app, or restart `runserver`). Credentials and the prompt are read at boot, so this step is required.
- [ ] **E6. Send it from chat.** In the chat, tick **Multi‑Turn ON**, then type:

  **If the person messaged your number in the last 24 hours (warm):**
  > Tlamatini, send a WhatsApp to Ana Ricardo Lazcano telling her I'll see her at lunch tomorrow.

  **If it's a COLD message (most first sends — the person hasn't messaged you):** WhatsApp policy blocks free‑form cold text. Use the pre‑approved test template:
  > Tlamatini, send a WhatsApp to Ana Ricardo Lazcano using template `hello_world` with template_language `en_US`.

  ✅ A WhatsApp arrives. **You just made Tlamatini send a WhatsApp.**

> **Why two cases?** This is a hard WhatsApp rule, not a Tlamatini limit: a normal free‑form message only delivers inside the **24‑hour window** after the person last messaged you. To start a **cold** conversation you must send an **approved template** (Part G covers making your own custom templates, e.g. a real "lunch tomorrow" message).

---

# PART F — Make the token PERMANENT (so it doesn't die in 24h) (5 min)

The temporary token from Part C dies in a day. Replace it with a permanent **System User** token.

- [ ] **F1.** Go to **Business Settings**: <https://business.facebook.com/settings> .
- [ ] **F2.** Left menu → **Users → System users** → **Add** → name it (e.g. `tlamatini-bot`) → role **Admin** → **Create**.
- [ ] **F3.** Click **Assign assets** → assign:
  - your **App** (toggle **Full control** / Manage), and
  - your **WhatsApp Account** (the WABA) (toggle **Full control** / Manage).
- [ ] **F4.** Click **Generate new token** → pick your **App** → set **Token expiration: Never** → tick these permissions:
  - `whatsapp_business_messaging`
  - `whatsapp_business_management`
  - → **Generate token** → **COPY IT NOW** (Meta shows it only once).
- [ ] **F5.** Paste this permanent token into `whatsapp_access_token` in `config.json` (replacing the temporary one) → **restart Tlamatini**.

Now Whatsapper keeps working indefinitely.

---

# PART G — Go to production with YOUR OWN number (when you outgrow the test number)

Do this when you want to message anyone (not just your 5 verified test numbers) and send your own custom messages/templates.

- [ ] **G1. Add your real business phone number.** App → **WhatsApp → API Setup → Add phone number**. Use a number that is **NOT** currently on a personal/Business WhatsApp app (or be ready to migrate it). Verify it by SMS/voice code.
  - Its **new** Phone number ID replaces the test one in `config.json` (then restart).
- [ ] **G2. Business verification (this is the "talk to Meta if needed" part).** Meta requires verifying your business to lift limits. In **Business Settings → Business info / Security Center → Start verification**, submit business details/documents. Most of it is a form; if Meta needs more, they prompt you in the **Support / Help** inbox there. Until verified you're on lower limits (you can still message a small number of users/day).
- [ ] **G3. Add a payment method.** In **WhatsApp Manager** (<https://business.facebook.com/wa/manage/>) → your WABA → **Billing / Payment settings** → add a card. This is when (and only when) per‑message charges apply. Service replies (within 24h) stay free.
- [ ] **G4. Create your own message templates** (for cold messages with real content). In **WhatsApp Manager → Message Templates → Create template**:
  - Category: **Utility** (cheapest, for things like reminders) or **Marketing**.
  - Write the body, e.g. with a variable: `Hi {{1}}, I'll see you at lunch tomorrow morning.`
  - Submit → Meta approves it (usually minutes to a few hours).
  - Then from Tlamatini chat:
    > Tlamatini, send a WhatsApp to Ana Ricardo Lazcano using template `lunch_reminder` with template_language `en_US` and template_params `Ana`.

---

# PART H — Exactly what Tlamatini reads (cheat sheet)

| Where | Key | Example |
|---|---|---|
| `config.json` | `whatsapp_phone_number_id` | `123456789012345` |
| `config.json` | `whatsapp_access_token` | `EAAG...` (permanent token from Part F) |
| `config.json` | `whatsapp_graph_base` | leave `https://graph.facebook.com` |
| `config.json` | `whatsapp_api_version` | leave `v20.0` |
| `contacts.json` | a contact's `whatsapp` | `+52 1 555 555 0000` |
| Chat (Multi‑Turn ON) | warm send | `send a WhatsApp to <Name> saying <text>` |
| Chat (Multi‑Turn ON) | cold send | `send a WhatsApp to <Name> using template <name> with template_language en_US` |

**Always restart Tlamatini after editing `config.json`.** `contacts.json` is re‑read per send, so contact edits don't need a restart.

---

# 🛠️ Troubleshooting (what the errors mean)

Whatsapper logs a clear reason; here are the common ones:

- **"phone_number_id or access_token missing"** → you didn't set the two values, or didn't restart. Re‑check Part E3/E5.
- **Error `131047` / "re‑engagement" / "outside 24‑hour window"** → you tried a free‑form `message` on a **cold** contact. Use a **template** instead (Part E6 / G4).
- **"recipient phone number not in allowed list" / `131030`** → (test number only) add+verify that number in Part D.
- **Token/`190` "expired"** → the 24‑hour test token died. Do Part F for a permanent token.
- **`132000` / template name/language mismatch** → the template name or `template_language` code is wrong, or the template isn't approved yet. Check WhatsApp Manager → Message Templates.
- **`100` invalid parameter** → usually the recipient number format; Whatsapper strips `+`/spaces automatically, but make sure the number includes the **country code**.

Check the live log at `Tlamatini/tlamatini.log` (or the Whatsapper run log) — the failure line and the `INI_SECTION_WHATSAPPER` block show provider, recipient, status, and the exact Meta error.

---

# ✅ Quick recap (the shortest path to a sent message)

1. Make a Meta Business account + a developer app, add the **WhatsApp** product. *(Parts A–B)*
2. Copy the **Phone number ID** + **temporary token**; verify your phone as a recipient. *(Parts C–D)*
3. Put both into `config.json`, add the contact to `contacts.json`, **restart**. *(Part E3–E5)*
4. In chat (Multi‑Turn ON): send via **template** if cold, or plain text if within 24h. *(Part E6)*
5. Later: permanent token *(Part F)*, your own number + verification + payment + custom templates *(Part G)*.

That's it — from nothing to a real WhatsApp. 🚀
