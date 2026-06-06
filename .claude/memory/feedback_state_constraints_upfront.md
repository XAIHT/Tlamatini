---
name: feedback_state_constraints_upfront
description: Surface hard platform/architectural constraints + real options UP FRONT as a decision for the user — never discover them by trial-and-error.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 89ce9f3d-0cfd-4f8e-9841-c69b3a70eade
---

When a request hits a **hard platform or architectural constraint** (something that makes the obvious approach structurally impossible, not just hard), STATE the constraint and the real options up front as a decision for the user — do NOT chase it through trial-and-error patches.

**Why:** On the Notifier toast (2026-05) I burned a lot of the user's tokens chasing `ToastNotifier.Show()` → "succeeds but no banner" → self-drawn window → DPI/detached-spawn fixes, each looking like the missing piece. The real blocker was knowable on day one: **an *unpackaged* Windows app cannot guarantee an OS toast** (needs MSIX/AppX/sparse-package identity + code signing). I even had a memory note saying exactly that and still kept trying variations. The user was (rightly) angry: "Why you did not say that since the beginning instead of wasting my tokens?"

**How to apply:**
- Before implementing, ask myself: "Is there a prerequisite that makes this structurally impossible/unreliable?" If yes, lead with it.
- Present it as a SHORT decision: the constraint, then 2-4 concrete real options with their costs (e.g. "needs a signed MSIX / sparse package / Store submission — all require a code-signing cert"), and let the user choose BEFORE I write code.
- When something "succeeds" (API returns OK) but doesn't visibly work, STOP and find why it *structurally* can't work — don't patch the symptom in a loop.
- Check memory for an existing note about the constraint first; if one exists, surface it immediately instead of re-deriving.

Related: [[feedback_dont_overbuild_exec_safety]] (don't reconstruct discarded work; prove the real fix), [[project-native-toast]] (the toast that triggered this).
