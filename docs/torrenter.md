# Torrenter

> Latest released version: **[v1.92.4](changes/2026-11-08-v1.92.4.md)**.

Torrenter is a Tlamatini workflow agent and the wrapped chat tool `chat_agent_torrenter`. It controls downloads in the separately installed Tlachihuani Jobs Windows service at `http://127.0.0.1:12064/api/v1`. Jobs owns the transfer, files and journal. You can close chat, the ACP or the browser and reconnect to the same job.

The signed-in page is carried with Tlamatini in `agent/torrenter_workspace/`.
Self-update replaces its HTML, JavaScript and CSS together with the controller.
A self-modification snapshot includes the same files for rebuilding. Jobs and XT
remain separately installed. Changes to their API must remain compatible with the
workspace protocol or provide a coordinated service update.

## Connect an account

1. Choose **Start Services** in the XT tray menu and sign in to Tlamatini.
2. Open **Panels → Torrenter workspace** to see the same downloads as chat. The XT panel opens this workspace too. If both editions are running, choose one. Refresh keeps your signed-in account. Signing out ends browser access to its queue.
3. Enable **Torrenter** in Configure Agents and **Chat-Agent-Torrenter** in Configure MCPs/Tools. Select them in Compact mode if enabled. Chat supports Multi-Turn, Ask Execs and Exec Report.

The server maps each Django account to a stable Jobs profile. The authenticated Windows control pipe issues the server an account-scoped credential. The browser uses its existing Django session and CSRF token. Each edition has its own session cookie.

## Files in Windows Downloads

The updated Jobs service publishes a hash-verified copy to the Windows operator's
actual Downloads folder under `Torrenter/<account UUID>/<job ID>/`. The account
heading identifies the signed-in Tlamatini user; the location above the queue and
**Verified output** show the destination. Windows folder redirection is respected.
The private service copy remains available for resume and recheck.

The ordinary local controller prepares only that account's output directory and
grants the Jobs service write access there. Neither edition needs administrator
rights for routine delivery. The private journal remains protected. An existing
completed job is copied on reconnect after the service update, without downloading
it again. Copies survive service shutdown, browser closure and record removal.
Explicit **Erase files** approval lists both the private and delivered copies.

`verified=true` in a delivered manifest means the copy was checked and published.
If Windows refuses Downloads, Jobs tries this edition’s
`content_generated/Torrenter/<account>/<job>/`. The workspace and agent log show
the actual destination. If both locations fail, the completion wait reports the
error and the private verified original remains available. A changed or missing user
copy is reported rather than silently overwritten or recreated. An older Jobs
version produces **Service update required**, not a claim that a private service
file was saved to Downloads.

The workspace fills the browser viewport and keeps its footer at the bottom. The
queue receives the unused height; selecting a transfer opens the details pane.
**Columns & view → Details pane height** adjusts that pane. Scrolling is retained
where the content actually exceeds the available pane or viewport.

Native credential calls are internal IPC and do not allocate console windows.

## Sort, filter and personalize the workspace

Every data column is sortable; **Select** remains fixed. Click a header to toggle ascending/descending; Shift-click adds another sorting priority. The arrows and priority numbers describe the active order. Numeric values and dates sort by their raw values, with unknown values last. Seeds / peers compares seeds first, then peers. **Reset sorting** returns to Name ascending.

Search matches all words across names, categories, tags, tracker hosts, paths and job IDs. Combine it with the sidebar filters and a progress-percentage range. **Clear filters** restores the full queue. The workspace reads all API pages before filtering or sorting, so transfers beyond row 250 remain available.

**Columns & view** controls visible columns, column order and minimum width, compact rows and details height. Select cannot be hidden, and one data column must remain visible. Display preferences, sorting and page size are stored per account and browser. **Restore default view** resets display settings without changing transfers; **Preferences** still controls transfer defaults.

Choose 25, 50, 100, 250 or All rows. The header checkbox selects the current page only; a banner identifies selections outside the current page after paging or filtering. Clear selection clears all checks. Click a row or press Enter to open its details, including when Name is hidden.
Development verification still runs in a visible foreground console and headed
Chrome. Full Tlamatini executables must be rebuilt to deliver frozen Python
changes; updating Jobs alone does not replace either Tlamatini executable.

## Start a transfer

Open **Panels → Torrenter Sources**. Choose a `.torrent` file or paste a magnet and click **Inspect metadata**. Copy the inspection ID to chat. You can also paste a magnet into a regular chat request. Tlamatini replaces it with a short-lived encrypted source reference before writing chat history or sending it to the model.

Example chat requests, in order:

1. “Use Torrenter to review inspection `<inspection_id>`. Show the file IDs and sizes.”
2. “Download file 0 from that inspection into downloads. Keep seeding off.”
3. “Check job `<job_id>`. Show the desired state, observed phase, selected bytes and verified bytes.”
4. “Show the verified manifest for that job, including the output location and SHA-256.”

A resolving magnet may need peers before any files are available. Inspect again using the same inspection ID. A published manifest with `verified=true` identifies completed output. A shared piece can be larger than the selected file. If the service reports excess piece bytes, Torrenter preserves that count in `engine_verified_bytes` and reports selected verified bytes only after publication. A zero rate, an accepted operation and a finished chat agent each describe different events.

When all four metadata lookup slots are occupied, Jobs can return `lookup_state: queued`. Keep polling the same inspection ID. File selection becomes available once the metadata resolves. The inspection queue is separate from a verified file delivery.

## Actions

### Recover an unfinished download

Read the current job and its revision before sending a recovery action. **Start**
continues an unfinished stopped job; **Resume** continues a paused job; **Recheck**
validates retained pieces and retries a failed job. A reported seed count is not a
connected seed count, and restarting cannot guarantee that missing peers return.
Do not repeatedly stop/recheck a healthy transfer just because its rate is zero.

The workspace enables actions only for eligible selected jobs. A mixed selection
leaves ineligible jobs unchanged and reports the skipped count. A finished download
remains **completed** when its peer session is stopped; Start and Cancel are not
offered for it. Its `desired_state` still records that the session was stopped.
Use **Reseed** for intentional sharing, or **Recheck** for an integrity check.
Stopped file-selection and source-list controls remain available after completion.

The client reports `download_complete`, `restart_action` and `recovery_note` in
status/list results. It separates an older service's stale `previous_error` from a
current transfer error. It never converts a delivery failure into successful saving:
the verified manifest and actual output path remain the evidence of delivery.

An empty or truncated session response is retried at most twice before displaying
a reconnect error. Torrent writes are never automatically replayed by this retry.

The coordinated Jobs source correction yields a stalled slot after 180 seconds
without payload progress **only when eligible queued work is blocked**. Partial
files and running intent are retained. Retry waits at least 60 seconds and moves
behind waiting work; the queue shows `queued · retry scheduled`. Progressing,
checking, verifying, intentionally stopped and paused jobs are not rotated.
Jobs also waits for libtorrent's disk-complete pause alert before hashing files.

These scheduler/disk fixes require updating the separately installed Tlachihuani
Jobs service. Updating either Tlamatini alone supplies the clearer reporting and
controls, but does not replace Jobs. The 10 November source checks did not build,
install or modify the live queue. See [the verification record](changes/2026-11-10-torrenter-recovery.md).

On the Agentic Control Panel, **Wait for complete download** defaults to **No**. The node returns its receipt and starts its connected agents as soon as Jobs accepts the transfer. Choose **Yes** to keep it running until Jobs publishes a verified manifest for the selected files. Pausing preserves the wait. A stopped, cancelled or failed transfer ends the wait with an error. The YAML setting is `wait_for_completion: true` or `false`.

Right-click the Torrenter node and open its log to see all available filenames, the selected files, sizes, full source magnet and the verified saved paths and hashes. Uploaded metadata has a generated magnet. The detailed activity file belongs to the account's flow. Chat results carry a separate machine-readable receipt.

Pass an `action` and an `arguments` object to the chat tool. On a canvas node put the same JSON object in the **arguments** field. Each invocation makes one logical Jobs request. A bounded wait polls the current job for up to 30 seconds. Continue observing with its job ID.

| Intent | Actions | Fields or behavior |
|---|---|---|
| Discover and inspect | `capabilities`, `list`, `inspect`, `inspection` | List supports filters, `limit` and `cursor`. Inspect accepts a public v1 `info_hash` or private `source_ref`. Inspection reads an `inspection_id`. |
| Admit a download | `download` | Supply `inspection_id`, `metadata_revision`, explicit `selected_file_ids` and `destination_root_id` (`downloads` or `archive`). Optional priorities, resume and seed policies retain explicit false and zero values. |
| Reconnect | `status`, `wait`, `operation`, `events` | Use a job ID for status or wait, an operation ID for the durable receipt, and an event cursor for events. Re-read the list on an expired cursor. |
| Inspect a job | `files`, `peers`, `trackers`, `web_seeds`, `statistics`, `manifest` | Supply its job ID. Jobs returns only published verified paths in a ready manifest. |
| Control | `pause`, `resume`, `stop`, `start`, `cancel`, `recheck`, `reseed`, `move` | Supply `job_id` and the latest `revision`. Pause pairs with resume. Stop retains partial data for start. Cancel ends an incomplete transfer permanently. Stop before moving to a different approved root. |
| Edit | `select`, `update`, `set_trackers`, `set_web_seeds` | Change selected IDs/priorities on a stopped job. Update labels, queue position, rates or policies. Prepare private source lists in Torrenter Sources and pass the opaque reference to the stopped job. |
| Account configuration | `categories`, `tags`, `label`, `settings`, `update_settings`, `totals` | Create, rename or remove a label by collection. Update defaults using their revision. Totals summarize this account. |
| Multiple jobs | `batch` | Pass `transition` (pause, resume, stop or start) and `jobs`, an array of job IDs with individual revisions. Inspect each outcome. |
| Remove a record | `remove_job` | Supply the ID and revision of a stopped, cancelled or completed job. Its files stay on disk. |
| Erase owned files | `delete_preview`, `delete_content` | Review exact files for a stopped or finished job, approve the matching preview in XT, then pass `preview_id` and the original revision. Poll the operation. A chat confirmation alone cannot authorize erasure. |

Durable writes accept an `operation_key` of 32 lowercase hex digits. Keep the key and arguments on an uncertain retry. Reusing them returns the original admission receipt. A changed request needs a fresh key and a stale revision needs a fresh read. The local chat `run_id` controls the short-lived client process. It is separate from the Jobs `job_id`, `inspection_id` and `operation_id`.

## Flows and diagnostics

Drop **Torrenter** on the Agentic Control Panel, open Configure and choose its action. For example, set **action** to `list` and **arguments** to `{"limit":10}`. Connect its output to a Parametrizer or Forker. Each activation writes one `INI_SECTION_TORRENTER` record with the action outcome and JSON response body. Fresh activations use fresh operation keys. Reanimation of an interrupted write reuses the saved key.

A search result passes its complete magnet, including trackers, as a private source reference. Poll the inspection until its file list is ready before submitting. For HTTP 401, check the signed-in account. For 403 check scopes or XT approval, for 404 check the owned ID, and for 412 re-read the revision. When Jobs is unavailable, check the XT Services panel. A transfer waiting for a peer remains a live service job.


## Repeat the development checks

Source references and activity logs belong in the edition’s private
`TorrenterData` directory. Jobs stages incomplete downloads in its own state
directory. Do not use Windows user profiles or `%TEMP%` as scratch space.
The final destination may contain a short-lived sibling file for an atomic write.

From a verified visible foreground PowerShell console, keep the server running in its own visible window. The live check opens headed Chrome, asks for the signed-in development account’s password, uploads a generated torrent, submits it through the real wrapped tool, replays its receipt and independently checks the SHA-256 of the published 13,936-byte fixture. It prints the completed job ID for inspection.

```powershell
Set-Location -LiteralPath 'C:\Development\XAIHT\Tlamatini\Tlamatini'
python manage.py test agent.test_torrenter agent.test_ask_execs_allowlist agent.test_agent_display_names agent.tests.ExecReportCaptureTests
python tests_e2e/torrenter_console_windows.py
python tests_e2e/torrenter_live.py --username YOUR_USERNAME --port 18084
```
