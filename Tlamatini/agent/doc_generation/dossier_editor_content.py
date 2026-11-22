# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Canvas, Interactor and configuration chapters shared by the PDF and deck."""


def editor_sections(section):
    return [
        *canvas_document_sections(section),
        section("torrent_workspace", "TORRENTER", "From a magnet to verified files",
                "Chat, the Agentic Control Panel and XT share the account’s Jobs queue.",
                body=["Inspect the metadata and select file IDs. A job receipt lets you reconnect. Enable Wait for complete download in a flow when downstream nodes need the files.",
                      "A fifth magnet can wait for a metadata slot. Reuse its inspection ID. The verified manifest identifies the delivered copy in Downloads or the edition’s fallback folder."], deck_points=[
                    ('Inspect', 'Keep the inspection ID while queued.'),
                    ('Select', 'Choose the file IDs from the resolved metadata.'),
                    ('Follow', 'Reconnect with the Jobs job ID.'),
                    ('Verify', 'Read the delivered path and SHA-256 from the manifest.'),
                ]),
        section("interaction_settings", "CONFIGURATION · v1.91.0", "Choose how she types and teaches",
                "Config → Live Editor & Terminater opens one shared dialog on the chat and control panels.",
                body=[
                    "Live Editor controls 40–250 WPM, a 0–3 second pause after each segment, teaching detail, "
                    "field suggestions, ghost text versus choices, and following the typed cursor. Manual "
                    "scrolling suspends following for that segment. Font, line numbers and wrapping affect "
                    "the real editor. Teaching detail instructs the model; exact wording still varies.",
                    "Standard and Guided learning presets populate a draft. Preview types and speaks a harmless "
                    "sample without editing files or executing commands. Save applies behavior to the next action. "
                    "Cancel, Escape and Close discard the draft. Stop, mute and current-tab editor access are immediate.",
                ], points=[
                    ("Pace", "Separate speeds or a linked 40–250 WPM setting; no instant typing."),
                    ("Teaching", "Brief, balanced or detailed guidance with optional local suggestions."),
                    ("Appearance", "Editor and terminal presentation saved per account/browser."),
                    ("Account", "Behavior persists on the server; concurrent saves detect revision conflicts."),
                ]),
        section("terminal_settings", "TERMINATER SETTINGS", "A command follows the learner's controls",
                "One TerminalHub resolves account preferences across chat, ACP, Prompt Flow and browser actions.",
                body=[
                    "Choose 20–250 WPM, an available default shell, advisor for new terminals, a command wait "
                    "window, a no-output threshold and a user handoff wait. Shell and advisor defaults affect "
                    "new terminals. A wait timeout does not kill the process. Layout, font and cursor changes "
                    "apply to existing views; resized prompts retain honest screen-based read-back.",
                    "I always press Enter prevents automated submission, including aliases, encoded text and "
                    "control characters; the user's keyboard still works. New flows can use account defaults. "
                    "Older flow files retain explicit values. Manual Enter and narration remain account choices, "
                    "and typed chat preserves a shell explicitly requested by the task.",
                ], points=[
                    ("Type", "One key at a time, 20–250 WPM; no paste or instant mode."),
                    ("Submit", "Task-controlled execution or user-only Enter enforced by the hub."),
                    ("Wait", "Command, no-output and handoff windows have separate meanings."),
                    ("Inherit", "use_my_defaults applies account preferences without rewriting older flows."),
                ]),
        section("interaction_voice", "COMMAND AND LESSON VOICE", "Hear the step before the first key",
                "Narration uses the existing browser voice and a shared, cancellable speech queue.",
                body=[
                    "Enable narration independently for Terminater commands and Live Editor segments. Choose "
                    "an explanation, literal command/code or both, spoken before, during or after typing. When "
                    "waiting before typing is enabled, a real speech-completion receipt or explicit skip is "
                    "required. An unavailable voice offers Continue without voice or Stop.",
                    "A single focused account tab speaks each terminal event. Receipts belong to that exact "
                    "connection; disconnect, Stop and the bounded deadline can cancel before any key. A reconnect "
                    "never replays a command. Secret-marked text and user handoff values are excluded. Outcome "
                    "notices describe command-action status without reading terminal output aloud.",
                ], points=[
                    ("Shared voice", "Reuse voice choice, rate, volume and pitch from Config → Voice."),
                    ("Priority", "Global mute and microphone listening override narration."),
                    ("Timing", "Before/during/after; optional completion before typing."),
                    ("Control", "Escape stops speech; Ctrl+Shift+M toggles global mute."),
                ]),
        section("canvas_edit", "CANVAS EDITOR · v1.97.0", "Edit the document you are discussing",
                "A local CodeMirror 6 editor keeps text, code, JSON and Markdown Source editable in the chat canvas.",
                body=[
                    "Open or drop a file, make a change, and use the filename bar: Save, Save as, Undo, Redo, "
                    "Find/replace and Wrap. Copy and Use as context take the edited source. Ctrl/Cmd+S saves; "
                    "Ctrl/Cmd+Shift+S chooses a destination. Tab normally navigates; Ctrl+[ and Ctrl+] indent.",
                    "Markdown Preview is sanitized with the existing Marked/DOMPurify renderer. Source and Preview "
                    "share one buffer and undo history. HTML and SVG remain text, never an active web page. PDFs "
                    "remain read-only viewers and export their original bytes; flows and images keep their own routes.",
                    "Open and drop add documents without replacing other buffers. The dirty marker survives "
                    "failed or cancelled saves; closing or refreshing edited documents requires confirmation. "
                    "Unsaved text lives in memory, so save before closing. Automatic sizing "
                    "reserves 320 CSS pixels for the canvas and wraps controls; manual splits remain the user's choice.",
                ], points=[
                    ("Independent documents", "Each tab owns its buffer, undo history, revision and save target."),
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
                    "Continue and Another hint send normal tutoring requests. Explain selection uses a separate "
                    "read-only request: it captures unsaved ranges without depending on chat checkboxes or Live "
                    "editor, and preserves the draft. Typing does not save or execute code. The ordinary Use as "
                    "context snapshot remains separate from Interactor's fresh reads.",
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
                    "The typed prefix stays editable. A temporarily hidden or occluded browser tab pauses the same action "
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


def canvas_document_sections(section):
    return [
        section("canvas_documents", "MULTI-DOCUMENT CANVAS · v1.97.0", "Keep the whole task beside the conversation",
                "Open up to 32 documents in one Canvas; switching tabs does not change the chat context.",
                body=[
                    "Open, drop and generated text add tabs. Each document keeps its own text, undo/redo, "
                    "selection, scroll, encoding, revision and authorized destination. Identical basenames "
                    "remain separate documents. Save applies to the active file; other dirty tabs keep their asterisk.",
                    "Markdown retains its Source/Preview state. Each PDF retains its viewer, page, zoom, "
                    "rotation and scroll state. PDFs remain read-only and Save as exports original bytes. "
                    "Opening a document is neither a disk save nor a request to include it in the conversation.",
                    "A late save cannot silently clear newer edits. Pending saves block document switches; "
                    "cancelled or failed writes preserve dirty buffers. Generated text starts unsaved. "
                    "Tabs and unsaved edits are memory state, not crash recovery or a restored browser session.",
                ], points=[
                    ("32 tabs", "Keep text, source and PDF documents together without replacing buffers."),
                    ("Per document", "Independent undo, selection, view state and save destination."),
                    ("Save", "Write the active document; retain every other dirty indicator."),
                    ("PDF", "Keep the viewer state and export the unchanged original bytes."),
                ]),
        section("canvas_context_set", "EXPLICIT CONTEXT", "Select the sources that guide the answer",
                "Use as context selects a confirmed snapshot, independently of the active document.",
                body=[
                    "Open A, B and C. Select Use as context on A, then B: the selected set contains A and B; "
                    "opening or activating C does not add it. Tab badges and the context strip identify the "
                    "selected documents. Closing an editor tab keeps its selected snapshot until explicitly removed.",
                    "Editing a selected file, renaming a text document through Save as or refreshing a PDF marks the "
                    "snapshot as older. Update context explicitly replaces that snapshot. Remove one entry "
                    "without discarding the rest. PDF preparation asks about images, unchecked by default, "
                    "and uses an account-bound prepared token; reading a PDF alone prepares no chat context.",
                    "The server accepts up to 32 selected snapshots atomically within a shared 32 MiB UTF-8 "
                    "budget, including document labels. "
                    "A rejected update preserves the last confirmed set. Disconnect clears confirmed tab "
                    "indicators and reports uncertainty while preserving buffers; a late reply cannot certify "
                    "a newer selection. Confirm the restored context before relying on it.",
                ], points=[
                    ("Select", "Only explicit selections enter the shared context package."),
                    ("Recognize", "Tab badges and the context strip show the confirmed documents."),
                    ("Update", "An older snapshot stays older until Update context succeeds."),
                    ("Remove", "Remove one snapshot; closing its editor is a separate action."),
                ]),
        section("canvas_context_example", "THREE DOCUMENTS, TWO SOURCES", "Open is not the same as selected context",
                "Keep notes.md, main.py and manual.pdf open; only notes.md and manual.pdf guide this chat.",
                body=[
                    "Use as context on notes.md, then prepare manual.pdf with images unchecked and confirm. "
                    "Wait for the server acknowledgement before treating the new set as active. Switching "
                    "to main.py leaves it available for editing without adding it to the selected context.",
                    "Editing notes.md marks its selected snapshot as older. The confirmed old snapshot stays "
                    "in use until Update context succeeds; removing manual.pdf removes only that source.",
                ], visual="steps", visual_data={"steps": [
                    ("Open three", "notes.md + main.py + manual.pdf retain independent tabs and view state."),
                    ("Select two", "notes.md + manual.pdf enter the confirmed context set after acknowledgement."),
                    ("Edit freely", "main.py stays open but unselected. Edits to notes.md mark its context snapshot older."),
                    ("Update explicitly", "Update notes.md to replace its snapshot, or remove manual.pdf without clearing notes.md."),
                ]}, deck="visual"),
        section("canvas_navigation", "NAVIGATION AND UNSAVED WORK", "Switch documents and keep a clear exit warning",
                "Canvas shortcuts act inside the Canvas; browser shortcuts remain controlled by the browser.",
                body=[
                    "Click a document tab, or use Alt+PageUp and Alt+PageDown while focus is inside the Canvas, "
                    "including its active PDF viewer. Ctrl+Tab and Ctrl+Shift+Tab work only if the browser "
                    "delivers them. Windows Chrome reserves physical Ctrl+Tab for browser tabs; use the Alt shortcut there.",
                    "An asterisk marks every unsaved document, including inactive tabs. Closing a dirty tab "
                    "asks before discarding it. Leaving or reloading the page requests the browser's standard "
                    "warning whenever any tab is dirty or a save is pending. The browser decides whether to "
                    "show that warning, and the user can still leave or force-close it.",
                    "Save each edited file to persistent storage before leaving. No page can guarantee recovery "
                    "after a crash, forced exit or discarded browser warning. Keyboard events outside the Canvas "
                    "and messages from hidden PDF viewers do not switch its documents.",
                ], points=[
                    ("Navigate", "Click tabs or use Alt+PageUp / Alt+PageDown inside Canvas."),
                    ("Browser limit", "Ctrl+Tab cannot be stolen from Chrome's own tab navigation."),
                    ("Dirty marker", "Every unsaved tab shows an asterisk, even in the background."),
                    ("Leave safely", "Save all edited files; the browser owns the final departure warning."),
                ]),
        section("interactor_documents", "LIVE EDITOR ACROSS DOCUMENTS", "Teach in one file, then continue in another",
                "Interactor keeps account connection identity separate from each Canvas document ID.",
                body=[
                    "documents lists IDs, names, revisions, active/dirty/context flags and document kinds; "
                    "it does not expose file contents, host paths or write capabilities. read obtains the "
                    "current document and revision. activate names an exact target_document_id and returns "
                    "a verified target snapshot before the next type action can edit that document.",
                    "Switching preserves the source's unsaved edits. Interactor can open or create a text "
                    "document while a PDF is active; the PDF and other tabs remain open. Tool-origin activation "
                    "continues the same lesson. A manual tab switch gives control back to the user and interrupts "
                    "ongoing typing; stale commands cannot cross document or revision boundaries.",
                    "Explain selection reads the active document's exact unsaved ranges independently of "
                    "the selected chat-context snapshots. Live Editor permission, Stop, cancellation, Ask Execs "
                    "and native file authorization retain their existing responsibilities.",
                ], points=[
                    ("Discover", "documents lists metadata; read captures the active source revision."),
                    ("Activate", "Choose the exact document ID and verify the returned target."),
                    ("Continue", "Type into that target while retaining the other buffers."),
                    ("Take over", "A manual switch interrupts typing and preserves the written prefix."),
                ]),
    ]


def bridge_section(section):
    return section("interactor_architecture", "LIVE EDITOR BRIDGE", "One connection, distinct document identities",
                   "An authenticated browser connection carries exact document IDs and revisions for every action.",
                   points=[
                       ("Browser", "Canvas tabs retain independent editors and PDF viewers; the active document supplies the receipt."),
                       ("Transport", "ws/interactor/ authenticates the session and exact Origin/Host; the server issues tab identity."),
                       ("Tool context", "ContextVar carries connection/account/session identity; documents/read/activate select exact buffers."),
                       ("Hub", "Bounded queues, command IDs, deadlines, revision checks and full-buffer verification."),
                       ("Persistence", "Ask Execs gates new/save; loopback host access uses the existing path and file-capability guards."),
                       ("Carriage", "Migration 0218, tool_gate_table, prompt rules, frozen modules and offline source/static inventories."),
                   ], deck="list")


def wizard_section(section):
    return section("wizard_intent", "ACCOUNT WIZARD", "Create the account in this running instance",
                   "The known catalog card uses a native console handler rather than a model-generated command.",
                   body=[
                       "The handler launches createuserconsole, a narrow subclass of Django createsuperuser, "
                       "with the current runtime and database using shell=False. Normal account, duplicate-name "
                       "and password validation remain. Customized cards are preserved.",
                       "Chat yields while the user enters username, optional email and password in the owned "
                       "console. Passwords are neither chat content nor command arguments. Authentication, "
                       "Ask Execs, cancellation and owned-process identity remain enforced.",
                       "DONE/HECHO checks the newly persisted administrative account before reporting completion. "
                       "Username and status followups belong only to that wizard conversation; successful "
                       "completion retires its state. An email field or completion reply is not notification consent.",
                       "On November 9, the final visible cohorts created and authenticated ten English and ten "
                       "Spanish accounts, passing all 260 acceptance assertions. These are source-run results, "
                       "separate from installed-package acceptance.",
                   ], points=[
                       ("Launch", "Use the exact known card, current runtime and database; no model-built command."),
                       ("Input", "Keep username, optional email and password in the owned console."),
                       ("Confirm", "Verify the new administrative account after DONE/HECHO."),
                       ("Authorize", "Keep Ask Execs and cancellation; notification needs a separate request."),
                   ])


def release_sections(section, facts):
    return [
        section("release1970_canvas", f"RELEASED · v{facts['version']}", "Multiple documents, explicit context and safe handoffs",
                "The English and Spanish Canvas share the same document model and localized controls.",
                body=[
                    "Up to 32 tabs preserve independent text and PDF state. Explicit multi-document context "
                    "selection has visible badges, older-snapshot indicators, update and removal. Interactor "
                    "can list and activate documents without discarding unsaved work.",
                    "Verified on November 21, 2026: the English full browser run passed 28 checkpoints plus "
                    "a focused PDF-to-text Interactor check; the Spanish full run passed 29 checkpoints. "
                    "Each edition passed 46 context-transaction tests, 40 Interactor protocol/ownership tests "
                    "and targeted Python/JavaScript lint. Both PDF viewers were checked for actually rendered visible text.",
                    "Browser context acknowledgements were explicitly injected; backend ownership and atomic "
                    "persistence were tested separately with model/network boundaries substituted. Native disk "
                    "writes, PDF text preparation and authenticated Interactor actions used their actual local "
                    "implementations. This is source evidence, not live-model ingestion or installed-build acceptance.",
                ], deck_points=[
                    ("Documents", "32 tabs with independent buffers, undo and PDF view state."),
                    ("Context", "A+B selected, C only open; explicit update and removal."),
                    ("Teaching", "Interactor discovers and activates exact document IDs."),
                    ("Evidence", "Dated browser, backend and lint results with stated test boundaries."),
                ]),
        section("release1961_catalog", f"RELEASED · v{facts['version']}", "Voice moves to the microphone",
                "The Catalog of Prompts no longer has a Voice Commands section.",
                body=[
                    "The microphone button beside Send records, transcribes and sends a prompt directly, so the "
                    "two Voice Commands cards (prompts 121 and 122) left the Catalog of Prompts. "
                    "Migration 0226 hides them without renumbering, and the catalog now opens with Getting Started.",
                    "This release also carries the Tlamatini-RC work released as v1.94.0, v1.95.0 and v1.96.0: "
                    "hosted remote control, approval sync and hardening. Talker's default model is "
                    "legraphista/Orpheus:latest.",
                ], deck_points=[
                    ("Speak", "Use the microphone button beside Send."),
                    ("Catalog", "Voice Commands removed; Getting Started opens the catalog."),
                    ("Data", "Migration 0226 hides prompts 121 and 122 without renumbering."),
                    ("Remote", "Carries the Tlamatini-RC releases v1.94.0 to v1.96.0."),
                ]),
        section("release1935_selection", f"RELEASED · v{facts['version']}", "Explain exactly what is selected",
                "The canvas button works independently of the chat toolbar and Live editor switch.",
                body=[
                    "Explain selection captures every selected range from the unsaved editor at click time. "
                    "With no selection it explains the whole current file. Existing chat drafts, selections, "
                    "documents and checkbox settings are preserved.",
                    "The authenticated explanation request goes directly to the configured model without tools, "
                    "history, loaded context, internet, compacting or self-modification instructions. It remains "
                    "available while ordinary chat tooling is rebuilding. Cancellation, chat delivery and usage "
                    "accounting still use the normal application services.",
                    "Up to 64 ranges and 262,144 UTF-16 units are accepted, subject to the model's real context "
                    "capacity. A large unselected file does not consume the selection budget; excerpts are never "
                    "silently truncated. Interactor tutoring retains its separate complete-document contract.",
                    "On November 12, 58 regressions and all 256 checkbox combinations passed in each edition. "
                    "The configured model explained the unsaved selected value in both languages with zero tools. "
                    "These dated source checks do not certify a newly installed executable.",
                ], deck_points=[
                    ("Select", "Capture exact unsaved ranges; no selection means the whole file."),
                    ("Explain", "No checkbox dependency, tools, history or context side effects."),
                    ("Preserve", "Keep the draft, document, selection and saved settings."),
                    ("Bound", "64 ranges; 262,144 UTF-16 units; actual model capacity still applies."),
                ]),
        section("release1935_execution", f"RELEASED · v{facts['version']}", "Return when the launching script finishes",
                "Executer no longer waits for inherited output pipes held by a detached child shell.",
                body=[
                    "A Windows start command launched the original 90-second Rust cube, but captured output "
                    "arrived after the cube closed: subprocess capture waited for pipe EOF from the detached "
                    "child even though the outer script had finished.",
                    "The blocking-script path now directs stdout and stderr to unique retained files in its "
                    "isolated run directory, waits for the direct script, and reads a bounded snapshot through "
                    "separate read handles. Direct commands still block; explicitly detached children can continue. "
                    "The fix adds no workflow loop budget or model-based progress guard.",
                    "The November 12 replay used the same executable and embedded shaders through real MCP "
                    "Executer, Windower and Shoter calls. Observed return time changed from 100.50 seconds to "
                    "5.05 seconds in English and 5.06 seconds in Spanish, while the cube remained alive. "
                    "All 65 selected regressions passed in each edition.",
                    "The later final-response delivery gap in the original trace remains separately unresolved. "
                    "This capture correction does not establish its cause or claim to fix every possible repeated task. "
                    "The full replay evidence and limitations are in the November 12 Executer change record.",
                ], deck_points=[
                    ("Cause", "Inherited child pipe handles delayed delivery after the script exited."),
                    ("Correction", "File-backed capture; wait for the direct script and read its snapshot."),
                    ("Proof", "Same assets: about 100.50 seconds before, 5.05/5.06 seconds after."),
                    ("Scope", "65 tests per edition; separate final-response stall remains unresolved."),
                ]),
        section("release1935_voice", f"RELEASED · v{facts['version']}", "Keep speaking when the window loses focus",
                "Covered, hidden or minimized pages no longer pause speech or impose a 100-second message limit.",
                body=[
                    "The shared speech queue retries a failed browser chunk and can hand remaining text to "
                    "Windows host speech when the browser cannot continue. Closing or reloading a page hands off "
                    "remaining ordinary chat speech; interactive narration does not use that page-close handoff.",
                    "Host speech uses account-scoped settings and controls, keeps the female-voice policy and "
                    "the Spanish edition's language requirement, and creates no extra console. Silent mode, "
                    "Escape, clicking the avatar and cancellation remain explicit ways to stop speech.",
                    "Tlamatini must remain running and an appropriate audio voice must be available. A retry can "
                    "repeat part of a chunk, and the host request limit remains 20,000 text characters. "
                    "See the voice-playback guide for behavior, recovery and implementation limits.",
                ], deck_points=[
                    ("Continue", "Keep speaking when a page is covered, hidden or minimized."),
                    ("Recover", "Retry browser chunks, then hand remaining text to Windows speech."),
                    ("Control", "Explicit mute, Escape, avatar click and cancellation still stop speech."),
                    ("Limits", "Application and audio support must remain available; host text is bounded."),
                ]),
        section("release1935_downloads", f"RELEASED · v{facts['version']}", "Follow downloads with truthful state",
                "Sortable account views, recovery guidance and bounded completion waits make progress inspectable.",
                body=[
                    "The workspace supports sorting, multiple sort keys, filters, paging and saved per-account "
                    "views. A verified completed download remains completed when its peer session stops. "
                    "Historical verification errors are separated from current failures; actions apply only "
                    "to eligible selections and report skipped jobs.",
                    "A completion wait ends on pause, stop or cancellation. It tolerates an API outage for up "
                    "to 600 seconds, gives a delivery failure 180 seconds to recover, renews an expired "
                    "credential, and stops waiting after two hours without progress. Ending the wait does not "
                    "cancel the underlying Jobs transfer.",
                    "Empty or truncated session JSON reads receive bounded retries; torrent mutations are "
                    "never replayed automatically. Read the current revision before recovery and verify the "
                    "delivered path and SHA-256 manifest. Coordinated engine scheduling and disk-flush fixes "
                    "require the separate Tlachihuani Jobs service update.",
                ], deck_points=[
                    ("Inspect", "Sort, filter and page the account's queue; preserve saved views."),
                    ("Trust", "Keep completed status; distinguish old errors from current failures."),
                    ("Wait", "Pause/stop/cancel end the wait; timeouts do not cancel the transfer."),
                    ("Verify", "Use current revisions and delivered file hashes; service updates are separate."),
                ]),
        section("release1935_requests", f"RELEASED · v{facts['version']}", "Resolve narrow requests directly",
                "Account creation and pure directory-access questions use their explicit application contracts.",
                body=[
                    "The known account-wizard catalog card launches the current runtime's native createuserconsole "
                    "command against its own database. Chat yields for private console input; Ask Execs and "
                    "cancellation still apply. DONE/HECHO verifies a newly persisted administrative account "
                    "before completion is reported. Customized cards are preserved.",
                    "A pure question about allowed directories reads the current path-guard snapshot without "
                    "a classifier or disk scan. It grants no new permission. A mixed request continues through "
                    "normal processing rather than being mistaken for a directory-listing request.",
                    "Central defaults use deepseek-v4.1-flash:cloud for text and mistral-large-4:cloud plus "
                    "gemma4:cloud for vision; configured choices remain the settings authority. "
                    "legraphista/Orpheus:latest is the default speech model. On November 9, the "
                    "wizard's final visible cohorts "
                    "created and authenticated 20 accounts with 260 assertions across the two editions.",
                ], deck_points=[
                    ("Create", "Known wizard card uses the current runtime and private console input."),
                    ("Confirm", "Verify the persisted new account before reporting completion."),
                    ("List", "Pure access questions use existing allowed roots; no scan or new grant."),
                    ("Configure", "Central text and vision defaults respect explicit model settings."),
                ]),
        section("release1924", f"RELEASED · v{facts['version']}", "Matching versions before the build starts",
                "One predicted application version for English and Spanish, with explicit release identity.",
                body=[
                    "BuildTlamatinis.cmd calls each checkout's own resolver and previews its version emitter in memory. "
                    "It compares the actual number the executable will report; a tag on HEAD is not required. "
                    "The common value is pinned with --version before either complete wrapper starts.",
                    "Private or Public mode runs both editions in parallel with --self-modify. New ZIPs are "
                    "CRC-checked, SHA-256 hashed and moved to edition/type/start-minute folders. Each successful "
                    "edition keeps its archive even if the other fails; the overall command then reports failure.",
                    "Complete wrappers embed release_type in the generated version module. The application log "
                    "begins with version and Private/Public banners. Source and unspecified builds are labeled "
                    "explicitly; folder names, environment variables and credentials do not guess the type.",
                ], deck_points=[
                    ("Predict", "Use each real resolver/emitter before spending time on compilation."),
                    ("Pin", "One common --version; parallel builds with --self-modify."),
                    ("Deliver", "Separate English/Spanish and Private/Public ZIPs, with checksums."),
                    ("Identify", "Read the embedded release type in the first application-log lines."),
                ]),
        section("release1924_recovery", f"RELEASED · v{facts['version']}", "Recover safely and open readable Markdown",
                "Build dependency isolation and lossless text loading are part of the release contract.",
                body=[
                    "Standalone builds use application-owned Temp/build-env; the combined launcher supplies "
                    "separate caches under the release root. If dependency setup fails and no healthy isolated "
                    "environment exists, the build stops before the machine-Python NumPy purge or pip --user path. "
                    "A previously healthy isolated cache remains reusable.",
                    "Readable README.md files containing occasional control characters remain editable. Strict "
                    "BOM-aware decoding and byte-preserving saves stay intact. A decoded NUL, control-dominated "
                    "payload or malformed encoding still causes a refusal before the canvas is replaced.",
                    "Dated evidence: the November 8 complete-build campaign passed all four real builds and "
                    "packaged-executable checks at version 1.92.3, with correct release types. Integrity checks, "
                    "public-data audits, 26 build-isolation tests and focused lint passed. This document refresh "
                    "does not relabel those archives or claim a new install, reboot or live-model acceptance run.",
                ], deck_points=[
                    ("Cache", "Application-owned isolated environments; no user-profile scratch fallback."),
                    ("Failure", "Stop before touching ambient Python when no healthy cache exists."),
                    ("Canvas", "Preserve readable text and bytes; keep genuine binary refusal."),
                    ("Evidence", "Four real builds verified on November 8; retain their actual 1.92.3 identity."),
                ]),
        section("release1923", "CARRIED FROM v1.92.3", "Downloads, typing and Windows delivery",
                "Downloads, typing, updates and Windows execution",
                body=["Torrenter adds account-owned downloads to chat and the Agentic Control Panel. Live Editor and Terminater accept up to 250 WPM. The updater carries the uninstaller and preserves the vault. Release builds lease the Python environment for their requirements fingerprint.",
                      "Builds with different requirement fingerprints coexist. An OS lock protects preparation and the full build. The 1.92.3 update package includes the verified uninstaller and preserves existing data.keys."], deck_points=[
                    ('Typing', 'Live Editor 40–250 WPM. Terminater 20–250 WPM.'),
                    ('Downloads', 'Torrenter shares the signed-in Jobs queue across chat, ACP and XT.'),
                    ('Updates', 'Install the verified uninstaller and preserve the existing vault.'),
                    ('Builds', 'Lease the environment matching the requirements fingerprint.'),
                ]),
        section("release1911", "OCTOBER 2026 · v1.91.1", "Prompt Flow fixes and short tool names",
                "Tag 9915938a, dated October 27, 2026; published as the Latest release.",
                body=[
                    "A patch on v1.91.0. Every chain loads the history of its own conversation, so a Prompt "
                    "Flow run keeps its own memory and is never answered with another conversation.",
                    "An equals Decision accepts an answer that opens with the expected word, and the Prompt "
                    "before it asks for that word alone on the first line. A flow run's usage is recorded for "
                    "the account that owns it.",
                    "Telegrammer sends as the bot when the request says 'using the bot'. A wrapped agent "
                    "called by its short name is resolved and logged as [TOOL-ALIAS]. No agent, tool, skill "
                    "or migration was added.",
                ], points=[
                    ("History", "Each run and each user reads only its own conversation."),
                    ("Decisions", "'## YES - ...' equals YES; 'Yesterday' does not."),
                    ("Routing", "'Using the bot' sends as the bot; short tool names still run."),
                    ("Release inventory", "86 agents; 110 tools; 220 migrations; "
                     "64 JS modules; 29 stylesheets."),
                ]),
        section("release191", "CARRIED FROM v1.91.0", "Real settings for editor and terminal behavior",
                "Tag a771d27c, dated October 23, 2026, and published on GitHub that day.",
                body=[
                    "The Live Editor, Terminater and Voice tabs share one schema, authenticated account storage "
                    "and optimistic revisions. Migration 0220 adds InteractionSettings. Account behavior reaches "
                    "the actual editor and the one TerminalHub; browser/account appearance stays local.",
                    "October 23 source evidence: 17 visible browser checks passed, including genuine OS speech "
                    "finishing before the first terminal key. The implementation regression run passed 929 of "
                    "931 tests; two existing README documentation assertions failed. This documentation sweep "
                    "restores those sections; its 94 focused tests passed, including both README assertions.",
                    "v1.91.0 was published on GitHub on October 23, 2026. These regenerated documents do not "
                    "claim a new executable build or installed acceptance. The existing tag is preserved.",
                ], points=[
                    ("Dialog", "Pacing, teaching, terminal behavior, narration, appearance and draft previews."),
                    ("Runtime", "Real settings snapshots, revision checks and cancellable narration receipts."),
                    ("Compatibility", "Legacy explicit flows keep their values; new flows can inherit defaults."),
                    ("Release inventory", "86 agents; 110 tools; 220 migrations; "
                     "64 JS modules; 29 stylesheets."),
                ]),
        section("release190", "CARRIED FROM v1.90.0", "Edit, teach and preserve the learner's control",
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
                    ("Release inventory", "86 agents; 67 wrapped; 110 built-in tools; "
                     "219 migrations. Counts from the October 2026 review."),
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
