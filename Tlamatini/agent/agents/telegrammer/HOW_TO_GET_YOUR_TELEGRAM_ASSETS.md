# 📲 Telegrammer — How To Get Your Telegram Key (super‑calm, tiny steps)

Read this if setup makes your brain feel like soup. **One tiny action per step.** Do the step, tick the box, breathe, next. You can stop and come back anytime.

This uses **Telegram itself** — no other company, nothing to pay. **100% free.**

---

## 🎯 What you are getting (just ONE thing)

A **Bot Token**. It looks like this:

```
110201543:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
```

That single line is the ONLY thing the **Telegrammer wizard** will ask you for. Get it, paste it, done. (We'll also grab your "chat id" at the end, only for the test.)

---

## Part 1 — Make the bot (in the Telegram app, 2 minutes)

> You can do this on your **phone** Telegram OR **Telegram Desktop** — same steps.

- [ ] **1.** Open **Telegram**.
- [ ] **2.** Tap the **search bar** (🔍 at the top) and type: **BotFather**
- [ ] **3.** In the results, tap **@BotFather** — the one with the **blue check ✔️** (that's the official one; ignore look‑alikes).
- [ ] **4.** Tap the **Start** button at the bottom (or send the message **/start**). You'll see a list of commands.
- [ ] **5.** Send this exact message: **/newbot**
- [ ] **6.** BotFather replies asking for a **name**. This is just the display name — type anything, e.g. **My Tlamatini Bot** → send.
- [ ] **7.** Now it asks for a **username**. Two rules: it must be **unique** and it **must end in `bot`**. Example: **MyTlamatini_bot** → send.
   - 😬 If it says the name is taken, just add numbers/letters and try again (e.g. **MyTlamatini2026_bot**).
- [ ] **8.** 🎉 BotFather replies **"Done! Congratulations…"**. Look for the line:
   > *Use this token to access the HTTP API:*
   and **right under it is your token** (the `110201543:AAH…` line).
- [ ] **9.** **Copy that token.** Paste it somewhere safe (Notepad) for a minute.
   - 🔒 **This token is a password.** Never post it or screenshot it to anyone. If it ever leaks, send **/revoke** to BotFather to get a new one.

✅ **You now have the ONE asset the wizard needs.** You can stop here and run the Telegrammer wizard — it will ask for this token.

---

## Part 2 — (Only for the test) Find your "chat id"

To send a message, the bot needs to know **who** to send to. The easiest target is **you**. Telegram bots can only message people who **pressed Start on the bot first** (that's Telegram's anti‑spam rule — totally normal).

- [ ] **10.** In Telegram, open **your new bot** (tap the **t.me/MyTlamatini_bot** link BotFather gave you), then tap **Start** and send it any message, like **hi**.
- [ ] **11.** Open a web browser and go to this address — **replace `<TOKEN>` with your token**:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   (Example: `https://api.telegram.org/bot110201543:AAH…/getUpdates`)
- [ ] **12.** You'll see some text. Find **`"chat":{"id":`** followed by a number, e.g. `"chat":{"id":123456789,`. **That number (`123456789`) is your chat id.** Copy it.

✅ Now you have **token** + **your chat id** — enough to send yourself a test.

---

## 🧙 When you run the Telegrammer wizard in Tlamatini

Tlamatini will ask you only for:
1. **Bot Token** → paste the `110201543:AAH…` line.
2. **Who to message** → paste your **chat id** (the `123456789`) or a **@username** of someone who has pressed Start on your bot.

Then Tlamatini does the rest and sends the message. **That's it.** 💚

---

## 🆘 If something feels wrong
- **Can't find BotFather?** Make sure you tapped the one with the **blue check**.
- **"username invalid/taken"?** It must end in **bot** and be unique — add numbers.
- **Lost your token?** Send **/mybots** to BotFather → pick your bot → **API Token** (or send **/token**).
- **Want to start over?** Send **/deletebot** to BotFather, then **/newbot** again.
- **Bot won't message a friend?** They must open your bot and tap **Start** once first (Telegram rule).

You did great. One token. That's all Tlamatini needed. 🌱
