# 💬 Whatsapper — How To Get Your WhatsApp Keys (super‑calm, tiny steps)

Read this if setup makes your brain feel like soup. **One tiny action per step.** Do it, tick the box, breathe, next. Stop and come back anytime — nothing breaks.

This uses **Meta (Facebook) directly** — no Twilio, no other company. **Getting the keys is free**, and your **first test message is free** too.

---

## 🎯 What you are getting (just TWO things)

1. **Phone number ID** — a long number (looks like `1179153071946453`).
2. **Access token** — a long secret (looks like `EAAG…`).

Those two are the ONLY things the **Whatsapper wizard** will ask you for. Get them, paste them, done.

> 🧠 "Phone number ID" is **not** your phone number. It's an ID Meta gives to a *sending* number. You don't type your own number for this — Meta gives you a free **test number** to start.

---

## Part 1 — Make the Meta app (5 min)

- [ ] **1.** Open a browser → go to **developers.facebook.com** → click **Log In** (top right) and log in with your normal **Facebook** account.
- [ ] **2.** If it's your first time, click **Get Started** and finish the short developer sign‑up (confirm email, accept terms).
- [ ] **3.** Go to **My Apps** (top menu) → click the green **Create App** button.
- [ ] **4.** It asks **"What do you want your app to do?"** → choose **Other** → click **Next**.
- [ ] **5.** App type → choose **Business** → **Next**.
- [ ] **6.** Type an **App name** (anything, e.g. **Tlamatini WhatsApp**), pick your business in **Business portfolio**, → click **Create app** (it may ask for your Facebook password).
- [ ] **7.** On the app's dashboard, find the **WhatsApp** box and click its **Set up** button.
   - ✨ Meta now auto‑creates a free **test number** and a test WhatsApp account for you. That's why the first message is free.

---

## Part 2 — Grab your TWO keys (3 min)

> Meta's menu changed recently — follow this exactly (it matches the current screens).

- [ ] **8.** In the **left menu**, click **Use cases**.
- [ ] **9.** Click the row **"Customize the Connect with customers through WhatsApp use case"** (the one with a **>** arrow). It opens a panel titled **Connect on WhatsApp**.
- [ ] **10.** In that panel's left menu, click **API Setup** (it sits just under **Quickstart**).
- [ ] **11.** Now you're on the **API Setup** page. Look at **Step 1: Select phone numbers**:
   - Under **From** you'll see **Test number: +1 …** and just below it **Phone number ID: ‹a long number›**.
   - 👉 **Copy that Phone number ID.** ✅ **That's key #1.**
- [ ] **12.** Scroll up to the **Access Token** box at the top → click the blue **Generate access token** button → a popup appears, click to allow/continue → the token fills the box → click **Copy**.
   - 👉 ✅ **That's key #2** (a `EAAG…` string).
   - ⚠️ **This one is a password.** Don't screenshot it or share it. (It expires in 24 hours — Part 4 makes it permanent.)

✅ You now have **both keys**. You could run the Whatsapper wizard right now.

---

## Part 3 — Let Meta send to your phone + free test (3 min)

The free test number can only message phones you've approved (up to 5).

- [ ] **13.** On the same **API Setup** page, find **To** → click **Manage phone number list** → type **your own mobile number** (with country code) → WhatsApp sends you a **6‑digit code** → type the code to verify.
- [ ] **14.** (Prove it works) Go to **Step 2: Send messages with the API** → click the blue **Send message** button → check your phone: a **"hello world"** WhatsApp arrives. 🎉

---

## Part 4 — Make the token permanent (so it doesn't die in 24h) (5 min)

The token from Part 2 dies in a day. Make a forever one:

- [ ] **15.** Go to **business.facebook.com/settings** (Business settings).
- [ ] **16.** Left menu → **Users** → **System users** → click **Add**.
- [ ] **17.** Give it a name (e.g. **tlamatini-bot**), role **Admin** → **Create**.
- [ ] **18.** Click **Assign assets** → assign **your App** and **your WhatsApp account**, with **Full control** turned on → **Save**.
- [ ] **19.** Click **Generate new token** → pick your **App** → set **Token expiration: Never** → tick these two boxes:
   - **whatsapp_business_messaging**
   - **whatsapp_business_management**
   → click **Generate token**.
- [ ] **20.** **Copy the token now** (Meta shows it only once). This permanent token **replaces** the temporary one.

---

## 🧙 When you run the Whatsapper wizard in Tlamatini

Tlamatini will ask you only for:
1. **Phone number ID** (from Part 2, step 11).
2. **Access token** (the permanent one from Part 4 — or the temporary one for a quick test).

Paste both. Tlamatini does everything else. **That's it.** 💚

> 📌 **One WhatsApp rule (not Tlamatini's fault):** a normal free‑text message only arrives if the person messaged you in the last **24 hours**. To message someone **cold**, Tlamatini uses an **approved template** (the free **hello_world** one works for testing). The wizard handles this for you.

---

## 🆘 If something feels wrong
- **No "WhatsApp" in the left menu?** Use **Use cases → "Customize the Connect with customers through WhatsApp use case" → API Setup** (Meta moved it there).
- **Token stopped working after a day?** That was the temporary one — do **Part 4** for the permanent token.
- **"recipient not in allowed list"?** Add that number in **Part 3, step 13**.
- **Message didn't arrive cold?** Use a **template** (hello_world) — see the rule above.

You did great. Two keys. That's all Tlamatini needed. 🌱
