# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Canvas/Interactor chapters shared by the v1.90.0 PDF and editable deck."""


def editor_sections(section):
    return [
        section("canvas_edit", "CANVAS EDITOR · v1.89.0", "Edit the document you are discussing",
                "A local CodeMirror 6 editor keeps text, code, JSON and Markdown Source editable in the chat canvas.",
                body=[
                    "Open or drop a file, make a change, and use the filename bar: Save, Save as, Undo, Redo, "
                    "Find/replace and Wrap. Copy and Use as context take the edited source. Ctrl/Cmd+S saves; "
                    "Ctrl/Cmd+Shift+S chooses a destination. Tab normally navigates; Ctrl+[ and Ctrl+] indent.",
                    "Markdown Preview is sanitized with the existing Marked/DOMPurify renderer. Source and Preview "
                    "share one buffer and undo history. HTML and SVG remain text, never an active web page. PDFs "
                    "remain read-only viewers and export their original bytes; flows and images keep their own routes.",
                    "The dirty marker survives failed or cancelled saves. Open, Clear and Refresh ask before "
                    "discarding edits. Unsaved text lives in memory, so save before closing. Automatic sizing "
                    "reserves 320 CSS pixels for the canvas and wraps controls; manual splits remain the user's choice.",
                ], points=[
                    ("One document", "Code, configuration and plain text share the same editing authority."),
                    ("Markdown", "Editable source and sanitized preview preserve undo history."),
                    ("Controls", "Save, Save as, Undo/Redo, Find/replace and Wrap."),
                    ("Layout", "A reserved canvas width and an editor that fills its available height."),
                ]),
        section("canvas_save", "NATIVE SAVING", "Save into the project folder you choose",
                "The local native Windows picker makes Downloads optional.",
                body=[
                    "Save uses a browser-granted writable handle or an already authorized native destination. "
                    "Without one, it asks. Save as and the navbar Save open a native Windows Save As dialog on "
                    "a local connection; subsequent toolbar Save writes there and Refresh reads it. PDF exports "
                    "stay copies. Remote browsers need their own supported File System Access picker.",
                    "A complete revision check refuses external changes. Writes stage on the destination volume, "
                    "flush and recheck before replacement. ReplaceFileW preserves existing Windows security, named "
                    "streams and creation time; partial failure retains a recoverable original. The protected "
                    "database backup/restore path is unchanged.",
                    "Unedited files keep exact bytes. Edited files retain encoding/BOM and existing line endings; "
                    "new lines use the original first terminator. UTF-8 and BOM-marked UTF-16 are decoded strictly. "
                    "Malformed/binary data is refused. Text editing and native saving are limited to 64 MiB.",
                ], points=[
                    ("Choose", "Native Save As to any writable local folder."),
                    ("Authorize", "Account/session-bound capability; 12 idle hours, lost on restart."),
                    ("Compare", "External disk changes refuse overwrite; Save As keeps a separate copy."),
                    ("Preserve", "Encoding, BOM, line endings and existing Windows metadata."),
                ]),
        section("interactor_tutor", "INTERACTOR · v1.90.0", "Teach inside the live, unsaved document",
                "Interactor is a module and a built-in tool, not a workflow agent or a terminal.",
                body=[
                    "Enable Multi-Turn, Interactor in Configure MCPs/Tools and Live editor above the canvas. "
                    "Ask: Help me create a Dockerfile for a Java servlet application using your text editor; "
                    "teach one step at a time. The English/Spanish editor aliases are taught in prompt.pmt.",
                    "First read the exact current buffer, selection, document ID and revision. With no requested "
                    "path, new creates an empty file under Temp/interactor/<account>/<random>/ using the requested "
                    "filename. Existing files are never overwritten. Tlamatini types a short known segment, then "
                    "guide hands the next field to the learner and prevents further mutations in that turn.",
                    "Continue sends a normal new chat request and reads again before reviewing the learner's "
                    "answer. Another hint and Explain selection also use normal chat without replacing an existing "
                    "draft. Typing does not save or execute code. The ordinary Use as context snapshot is separate "
                    "from Interactor's fresh read of unsaved text.",
                ], points=[
                    ("Read", "Exact unsaved text and selection, never a stale disk substitute."),
                    ("Type", "One small visible teaching segment; one undoable edit."),
                    ("Hand over", "Explain the learner's next field, then stop tool mutations."),
                    ("Review", "Continue starts a fresh read in a new chat turn."),
                ]),
        section("interactor_latency", "TUTOR COMPLETION", "Immediate help while the learner types",
                "The model plans the next field once; local matching avoids a model request on every keystroke.",
                body=[
                    "Ghost text appears only for a matching prefix among bounded choices prepared for the current "
                    "field. Tab accepts, Ctrl+Right accepts a word and Escape dismisses. Suggestions are optional; "
                    "the learner can write an alternative value. This is contextual teaching support, not a claim "
                    "of unrestricted predictive autocomplete or vendor benchmark latency.",
                    "User input, selection, Stop, Escape, chat cancellation and disconnect interrupt AI typing. "
                    "The typed prefix stays editable. A temporarily hidden or occluded tab pauses the same action "
                    "for up to two extra minutes and resumes at the exact next character when visible. Timeout "
                    "never replays a partial edit. Switching Markdown to Preview or hiding the canvas returns control.",
                    "Live tutoring accepts at most 262,144 UTF-16 units and checks document/revision before "
                    "mutations. A smaller configured tool-result/context budget can refuse the receipt. Oversized "
                    "content is refused explicitly, never truncated into misleading context.",
                ], points=[
                    ("Local matching", "Prepared field choices; no model call per key."),
                    ("Optional", "Accept a suggestion, take one word, dismiss it or type your own value."),
                    ("User priority", "Interruptions preserve the typed prefix and invalidate stale work."),
                    ("Honest latency", "New questions still wait on chat/model processing."),
                ]),
    ]


def bridge_section(section):
    return section("interactor_architecture", "LIVE EDITOR BRIDGE", "One authenticated tab, one exact buffer",
                   "The browser editor and the synchronous tool loop share an account/session-bound bridge.",
                   points=[
                       ("Browser", "CodeMirror is authoritative; bridge.js sends receipts/access/stop, not host-path commands."),
                       ("Transport", "ws/interactor/ authenticates the session and exact Origin/Host; the server issues tab identity."),
                       ("Tool context", "ContextVar carries tab/account/session identity into workers; read gets the live buffer."),
                       ("Hub", "Bounded queues, command IDs, deadlines, revision checks and full-buffer verification."),
                       ("Persistence", "Ask Execs gates new/save; loopback host access uses the existing path and file-capability guards."),
                       ("Carriage", "Migration 0218, tool_gate_table, prompt rules, frozen modules and offline source/static inventories."),
                   ], deck="list")


def wizard_section(section):
    return section("wizard_intent", "INTENT GUARDS · v1.90.0", "A password prompt must not divert the wizard",
                   "The account wizard launches createsuperuser through Executer and waits for input in its console.",
                   body=[
                       "The installed log showed two independent false positives. 'I will type it' referred to a "
                       "password but reserved all commands for the user. A completion phrase plus the optional "
                       "email field falsely created notification debt. These runtime guards overrode an initially "
                       "correct Executer selection and diverted the wizard.",
                       "Typing/entering ownership now requires a command object; ambiguous input is neutral. An "
                       "explicit assistant launch of a named program lifts a prior lesson. Genuine user-runs "
                       "tutorials still refuse command runners and keep Terminater's Enter disabled.",
                       "A completion notification requires a positive outbound instruction tied to completion "
                       "in the same sentence. Email fields, ordinary chat explanations, quoted examples, negations "
                       "and the user's DONE reply do not authorize sending. Passwords stay out of chat. The catalog "
                       "wizard creates an administrative superuser, not a restricted ordinary account.",
                   ], points=[
                       ("Launch", "Executer opens the interactive source or frozen command in a visible console."),
                       ("Input", "Username, optional email and password belong to the user's console interaction."),
                       ("Wait", "DONE / ERROR / NOWINDOW drive the next step; no automatic success claim."),
                       ("Notify", "Only an explicit outbound request creates completion-notification debt."),
                   ])


def release_sections(section, facts):
    return [
        section("release190", "CURRENT RELEASE · v1.90.0", "Edit, teach and preserve the learner's control",
                "v1.89.0 introduced editing and native saving; v1.90.0 carries Interactor and the intent corrections.",
                body=[
                    "The annotated v1.90.0 tag resolves to ebc5c3b4; this documentation refresh began at d274f89c, "
                    "the follow-up commit also present on origin/main. A tag and source tests do not establish that "
                    "a separately installed executable has been rebuilt or accepted.",
                    "Interactor adds one module tool, not a workflow-agent template. Migration 0218 seeds its "
                    "Tool row and catalog example. Full enabled-tool binding, Compact-mode selection and cost "
                    "labels share tool_gate_table. The offline editor bundle includes the tutoring extension.",
                ], points=[
                    ("Editing", "Native Save As, exact source, undo history and conflict-aware persistence."),
                    ("Tutoring", "Fresh unsaved reads, small typing segments, learner fields and local suggestions."),
                    ("Recovery", "Bounded tab-visibility pauses and usable narrow-canvas layout."),
                    ("Inventory", f"{facts['agents']} agents; {facts['wrapped']} wrapped; {facts['tools']} built-in tools; "
                     f"{facts['migrations']} migrations. Counts describe the inspected source."),
                ]),
        section("editor_evidence", "DATED VERIFICATION", "Keep source, model and frozen evidence separate",
                "These are recorded runs from October 21–22, not tests silently rerun by documentation generation.",
                table={"columns": ["Scope", "Recorded result and limit"], "widths": [0.30, 0.70], "rows": [
                    ["Canvas editing / Oct 21", "29 distinct visible checkpoints; native saving, file types, encoding, conflicts and PDF copies."],
                    ["Interactor / Oct 21", "35/35 checks including three configured real-model cases; later UI runs add interruption and recovery coverage."],
                    ["Final DEV modes / Oct 21", "19/19 visible checks; 136 passed + 2 skipped among 138 focused Django tests."],
                    ["Older frozen v1.89.0", "Real frozen-loader run: 16 passed, 2 failed after visual review (tab absence and narrow layout)."],
                    ["Wizard guards / Oct 22", "179 tests passed; exact installed-request replay passed. Controlled tool effects; no real account or notification."],
                    ["New v1.90.0 package", "No new installed-package acceptance is claimed by this documentation pass."],
                ]}, deck="table"),
    ]
