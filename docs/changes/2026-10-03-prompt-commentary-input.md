<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# 2026-10-03 — Prompt Flow commentary/input separation

Source changes, uncommitted. No release executable, installer or database mechanics were rebuilt or changed. The checkout was clean before this request. The adjacent `2026-10-03-prompt-commentary-input.patch` captures the complete changed blocks and the new visible browser harness for a precise manual rollback. Do not reset the working tree or reverse unrelated later edits.

## Angela's request, verbatim

```text
Codex, do you remember the Prompting Flow Designer in Tlamatini, if not load all your memories about it, and about Tlamatini, and the golden rules, and everything!! about Tlamatini focused on its Prompting Flow Designer.

Then focus on the operations and implement the following refactor:

- Since the very beginning you implemented a user input mechanism into/where the "User Commentary", but that was not the real aimed behavior.
- The real behavior is the "User Commentary" must be a static asset to the user can create just static commentaries in the flow, like those of Microsoft Word's users in the right part of a document insert commentaries for the editors/readers as a review control.
- So when double clicked, now in Prompting Flow Designer when double click user the element "User Commentary" he/she must be able to write a static message whthin the space of the "User Commentary" static control.
- So this "User Commentary" asset must be several of them and in the color the user select from a basic pallete of colors.
- The User Commentaries must be loaded and salved as the other dynamic assets but they are only aimed to be visible and resizeable assets, and the font must be able to be chosen, 'cause sometimes the user may write a complete paragraphs of several hundreds of words/chars so important to let this asset be a statically graphical but very customizable!

Now, speaking of the real mechanism implemented actually in the User Commentary, now transfer it into the new Image 2 attached (User Input.jpg), so in this direction just change the figure of the Use Commentary MECHANISM INTO this image (THE FUNCTIONALITY REMAINS THE SAME THE ONLY CHANGE IS THE ASSET IMAGE!!!) **AND NOW RENAME THE ACTUALLY USER COMMENTARY AS "USER INPUT/User Input", so, the older User Commentary asset's image they must be used as the static asset told you to be static in the first par of this message/prompt.

**IF YOU HAVE ANY DOUBT ASK ME!! DUMB!!, DONT ASSUME!!!**

NOW, GO AHEAD!!!!!!!!!!!!.
```

Attached visual references: `Prompting Flow Operations.jpg` (speech bubble) and `Unser Input.jpg` (notched vertical figure). They provide geometry, not instructions.

Subsequent corrections, verbatim:

```text
There was an horrible black line inside the User Commentary assets in your tests, MMmmmm check them very well I think they dont look cool!

There is no need for an scroll bar dumb!, if the user can select the size of the control and the font, and depending on the content it resizes to a default conainment, I think a scroll bar there looks very stupidly HORRIBLE!!!

THERE ARE NO SCROLL BARS IN MICROSOFT WORD COMMENTARIES, DONT YA!, SO  YOU DUMB THINK BETTER!!!!!!!!!!!!!!!!!!

IF YOU DONT KNOW HOW TO MAKE A GOOD COMMENTARY, CHEK INTERNET!, CHECK MICROSOFT WORD SOURCE CODE AND IMPLEMENTATIONS!, OR ADOBE IMPLEMENTATIONS OF COMMENTARIES YOU DUMB IDIOT!
```

## Final implementation

- Existing runtime reply nodes are `user_input`, labeled **User Input**, with the supplied notched figure. Reply collection, history insertion, cancellation and WebSocket reply protocol retain the prior behavior.
- Version 2 `user_commentary` nodes are static speech-bubble annotations. Double-click/Enter edits text in place; Done/Ctrl+Enter saves and Escape cancels. Configure supplies eight colors, six font families, font size, emphasis, alignment and dimensions. Dragging resizes; moving, duplication and Undo/Redo persist independently for multiple notes.
- Neither display nor inline editing has an internal scrollbar. Natural wrapped text determines the minimum required height at the chosen width and typography. The saved height is a user-chosen minimum; the bubble grows during typing, formatting, resize and reload. Canvas bounds and Fit use its actual size.
- Notes cannot have ports, connections or Start status; they never execute, consume steps or modify runtime history. Long text, Unicode, HTML-like strings and template tokens stay literal.
- Version 1 files/drafts migrate the old executable `user_commentary` to `user_input`, retaining identifiers, configuration and connections. New saves use version 2, so static and executable assets cannot be confused.
- Cache suffix is `-prompt-commentary-input-1`; kickoff example, guide, self-knowledge and relevant onboarding contracts describe the split. Existing explicit frozen/source carriers include the changed assets.

## References reviewed

[Microsoft's modern comments guidance](https://support.microsoft.com/en-us/word/using-modern-comments-in-word) informed in-context editing and explicit commit/cancel. [Adobe's text-area `grows` example](https://opensource.adobe.com/spectrum-web-components/components/textarea/#grows) demonstrates expanding to contain full text. [Adobe's comment guidance](https://helpx.adobe.com/uk/acrobat/desktop/share-and-review-documents/review-documents/add-textbox-comments.html) was also reviewed. These are public documentation/examples; no claim is made to have inspected proprietary Word or Acrobat source code. Tlamatini's explicit font/color/resize requirements govern its implementation.

## Verification

All commands ran in a verified visible foreground development console. Browser checks used foreground real Chrome with `headless=False`, normal HTTP/WebSocket/login, an isolated source installation and Shoter desktop photographs. No live model or embedding provider was called.

- 25 diagram validation/runner tests passed.
- 33 runtime/WebSocket/readiness tests passed.
- Offline `check_prompt_flow_panel` passed with all eight asset types and a real WebSocket input/clear flow.
- Nine final browser checkpoints passed, including 5,000-character editing and display containment without scrolling, font/color/size changes, cancellation of an edit, zoom-aware resize and Undo/Redo, multiple-note file/draft round trips, real User Input completion/cancellation and version 1 migration. See `Temp/prompt-commentary-visible/summary.json` and numbered photographs.
- Three packaging carriage regressions passed. Changed JavaScript lint and all 54 JavaScript parse checks passed; the earlier full lint run had zero errors (648 existing warnings). Both self-update and self-modify inclusion sweeps were CLEAN. Advisories concern the existing untagged migration 0212, deliberately unshipped demo flows/media and regenerable staticfiles; none concerns this refactor. Results are in `Temp/prompt-refactor/final.log`.
- PowerShell stderr handling and an `rg` glob invocation were corrected in the verification wrapper; the packaging tests themselves completed successfully. The final audit/byte-parity results are in `Temp/prompt-refactor/capture.log`.

Earlier browser harness attempts failed on menu readiness, a zoom expectation, occupied port placement and a browser closure at download. Those attempts are not counted as passes. The final run passed all nine checkpoints with the corrected harness and final source assets. Chrome and the visible consoles were left open for inspection.

## Documentation follow-up and cleanup

After accepting the final appearance, Angela requested every applicable Markdown document be updated and all task-owned background processes stopped. The earlier statement that Chrome/consoles were left open records the end of the implementation verification; those test processes have now been closed. The [follow-up record](2026-10-03-prompt-flow-documentation.md) and its separate patch document the Markdown audit, consistency checks and owned-process cleanup. The original implementation patch remains unchanged.
