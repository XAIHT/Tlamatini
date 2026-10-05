<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# 2026-10-04 — Graphical rich-text User Commentary

## User requirements, verbatim excerpts

```text
Sorry, but still horrible your fucking User Commentary:
-It cannot be resized, directly in the borders of the figure.
-The user does not now the ratio of the text and the size of the bubble, so the most stupid thing: let the user write the width and height by value of pixels!! (You really are an idiot!!).

REFACTOR COMPLETELLY THE DESIGN OF THAT STUPID MEDIOCRE "User Commentary" MAKE IT 100% AGAIN FROM SCRATCH YOU MAKE AN STUPID ENGINEER NOT LIKE A GRAPHICAL DESIGNER, GO AGAIN!

The text controls, FONT, COLOR, ITALIC, ETC... must be like Microsoft Word like Floating tool tip controls!!, not in the fucking configuration engineer dialog STUPID DUMB!!!

This User Commentary MUST NOT HAV A Configuration dialog it must be 100% modified graphically as a Microsoft Word Commentary or an Adobe professional commantary.

dont make me get mad, make a beyond perfection implementation

REMEMBER AN ELITE-LEVEL DESIGNER WOULD MAKE A CONTROL IN WHICH THE TEXT INSIDE THE SAME ASSEST CAN HAVE MULTIPLE TYPES OF STYLES!, SO WITHIN THE SAME USER COMMENTARY SOME PARTS OF THE TEXT COULD BE ITALICS OF ARIA FONT, OTHER WITH BIGGER SIZZER WITH VERDANA, ETC...

YOU STUPID MADE ME MAD, NOW FOR THAT REASON YOU MUST CREATE A BEYOND EXTRATERRESTRIAL LEVEL GOD-LEVEL DESIGNER JOB!!!!!!!!!!!!!!!

AND REMEMBER TO MAKE TESTS OF LOADING/WRITING .fmpt FILES THAT ALWAYS RENDER IDENTICALLY WHILE SAVING/LOADING, ETC.

OF COURSE WITH SEVERAL COMMENTARIES EXAMPLES

remember: don't commit!!!!!!!!!!
```

## Result and contract

Replaced the commentary form/textarea design with an inline rich-text bubble, a floating mini toolbar and direct resizing on eight edges/corners. No commentary configuration dialog or numeric width/height inputs remain. The existing Configure entry becomes Edit comment for this asset; executable operations retain their own settings dialogs. The selection outline is mint, corners/tail keep their proportions, and the shared Bootstrap placeholder class no longer paints a block over an empty note.

Selected passages support different fonts, sizes, text colors, bold, italic and underline inside the same note. Collapsed-caret choices style the next input; formatting outside the editor applies to the full note. Bubble color and alignment apply to the note. Clipboard operations between commentary editors preserve rich runs; unrecognized/external clipboard formatting falls back to literal text. Enter, Unicode deletion, composition input, local edit Undo/Redo, whole-edit Cancel, flow Undo/Redo, keyboard resizing and resize while typing share the same saved model. Text measures at the actual mixed fonts and wraps into automatic height without internal scrollbars. Fit text resets spare minimum height.

Version 2 keeps the existing schema identity and adds optional allowlisted `runs`: literal text with font_family, font_size, text_color, bold, italic and underline. Both validators normalize old plain version 2 notes and require concatenation to equal `config.text`, discard unknown keys, merge adjacent equal styles and reject unsupported values. Limits remain 100,000 characters, 10,000 runs per note and 5 MiB per file. Version 1 executable commentary still migrates to User Input. Static notes never enter context/history/playback and have no ports or Start state.

Frontend/backend/template, the bundled eight-asset example, current user/developer guides, assistant contracts, memories and mirrored maintenance instructions were updated. Dated 2026-10-03 records remain historical. STATIC_VERSION retains its environment/timestamp expression with suffix `-prompt-commentary-canvas-2`. No new dependency, database migration, backup/restore modification, release rebuild, Git commit or push.

Design references: Microsoft's [Mini toolbar](https://support.microsoft.com/en-au/word/use-the-mini-toolbar-to-format-text) and [selected-text formatting](https://support.microsoft.com/en-us/word/training/add-and-edit-text), plus Adobe's [text-box resizing and reflow](https://helpx.adobe.com/acrobat/desktop/edit-documents/edit-text-in-pdfs/adjust-text-boxes.html). These are public product interaction references, not a claim to have Microsoft Word's proprietary source code.

## Verification

Passed **29 diagram/runner tests**, **3 packaging carriage tests**, repository JavaScript lint/parse (zero errors; existing unrelated warnings), and **23 real foreground Chrome checkpoints**. The final browser run checks three differently styled comments through three real download/clear/open/save cycles, exact JSON equality and matching rendered line boxes/fonts/colors/geometry, plus draft reload, rich clipboard editing, editor/flow undo and Unicode deletion. Cancelled edits are excluded from draft writes even when zoom schedules persistence. The final checks also confirm that the bubble has no rectangular focus frame. Both source-carriage sweeps passed with only existing unrelated advisories; no executable/installer was built.

The current Markdown reference audit covers all applicable active contracts (**26 updated Markdown files**); historical change records remain intact. The scoped rollback patch and changed relative links, maintenance mirrors, Python syntax and source/collected-static byte parity are checked by the visible final verification script.

Earlier attempts are not counted as passes: Chrome closed during downloads in an old profile, and its breached-password modal blocked clicks for the reusable test credential. The harness now uses a fresh test profile and a random password for the **isolated port-8001 account only**. An overly broad unittest discovery invocation imported unrelated packages incorrectly; running the packaging regression module directly passed all three tests. The final browser run finished with no page errors. Logs, Shoter full-desktop photos, downloaded examples and rendered geometry are retained under `Temp/commentary-redesign/` and `Temp/prompt-commentary-redesign-visible/`. All workloads use verified visible foreground consoles and explicitly headed Chrome, monitored live. No live model is called by these checks.

## Rollback

[The adjacent patch](2026-10-04-commentary-graphical-redesign.patch) captures only this request's changes against before-copies under `Temp/commentary-redesign/before/`; it excludes unrelated local configuration edits and earlier dated patches. Inspect the exact affected blocks before reversing them. Do not reset entire files over later changes, alter Git history, or modify protected database mechanics.
