<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# About Usage

**Status: source implementation verified on 2026-10-10; rebuild and installed-release
acceptance are pending.** The published v1.77.0 release predates this change. A
version number alone does not prove that an installation contains the dialog.

## Open and read the dialog

Choose **About → Usage** in the chat navbar. The heading is **ABOUT USAGE**.
It remains available while Tlamatini answers a request. The three tabs are:

| Tab | What it measures |
|---|---|
| Cloud credits | The configured Ollama account's reported credit balance, monthly allowance and usage, next refill, plus reported rolling cloud requests, spend and tokens. |
| Chat activity | Completed, measured main-chat model calls recorded for the signed-in Tlamatini user since recording began. |
| Models | Per-model recorded chat calls, input/output tokens, peak UTC dates, and the configured server's model inventory and loaded-model information. |

Choose **7 days** or **30 days** for activity. Changing this range does not change
the monthly balance. The cloud API's daily range includes seven or thirty
complete UTC days plus today so far; the local ledger shows seven or thirty
calendar dates including today. These are different scopes, not interchangeable
totals. Neither view promises lifetime token history.

The dialog uses the shared Tlamatini theme, normal-sized text and clearly
bordered buttons. Its desktop box is `80vw × 74dvh` (59.2% of client area,
maximum width 1440 px); narrow screens use `94vw × 63dvh` (59.22%). The body
scrolls while tabs and footer controls remain reachable. Body text is `.88rem`
and the heading `1rem`. Money has two decimal places; other fractional values
have at most two, and full token/request counts remain integers. Colorful charts
provide pointer and keyboard-focus tooltips and exact table values.

**Refresh** requests an update. Gauge updates, reopening, returning focus and the
visible-dialog timer also refresh the view. Requests are coalesced, and Ollama
account snapshots are cached for 60 seconds; clicking Refresh does not bypass
that interval. New cloud usage may also be delayed upstream. Check the displayed
timestamps and stale-data notice. Escape, the titlebar close button and **Close**
use the same dismissal path; clicking outside does not dismiss the dialog.

## Credits come from the account

`GET /api/balance` is the authoritative balance source. Monthly credits used are
the returned allowance minus returned included balance. Available credits are
the returned included balance plus returned purchased balance, only when both
are present. Calculation retains precision until display. Signed balances are
not silently clamped. A zero allowance does not invent a percentage.

The refill caption uses the returned UTC `included.period.until`, with weeks
and a date, or days when less than a week remains. There is no assumed 30-day
billing cycle. Purchased credits are shown separately when reported. The API
does not provide individual purchased-credit expiry dates, the auto-reload
setting or a complete website billing breakdown; the dialog does not invent them.
See Ollama's [balance contract](https://docs.ollama.com/api/balance).

### Plans and layouts

The layout follows returned fields, not a table of hardcoded plan names or
allowances. The plan badge is shown only when Ollama supplies it.

| Account response | Dialog behavior |
|---|---|
| Monthly included balance and allowance | Credit cards, actual usage percentage when the allowance is positive, and refill information when supplied. Free, Pro and Max can use this shape. |
| Legacy session/weekly limits | Reported remaining percentages and reset times; no conversion of quota percentages into dollars. Cost/token panels and columns are omitted when absent. |
| Purchased balance only | Purchased balance only; no assumed monthly entitlement. |
| Missing, unsupported or failed response | Loading or an explanatory unavailable/stale state, Refresh, and **Ollama Usage ↗**. Missing data is not a zero balance. |

As checked on **2026-10-10**, Ollama lists Free, Pro, Max, Team and Enterprise.
Free includes starter usage; Pro includes $60 monthly credits, Max $300, and
Team $1,000 shared credits. There is no listed cloud subscription named
“Unlimited”; unlimited local execution is different from unlimited cloud
credits. These dated commercial facts are not implementation constants. See
[current Ollama pricing](https://ollama.com/pricing). Tlamatini's documented
Pro-or-higher baseline for full cloud workloads remains separate from the
dialog's ability to report other account types.

Team members share balances. This implementation requests the default cloud
usage scope (`self`), not the administrator-only `scope=team`; it must not claim
organization-wide usage from a member's totals. Enterprise or future plans are
displayed only to the extent that their actual response uses a supported shape.

## Honest coverage and unavailable data

Cloud activity comes from `GET /api/usage?range=7d` and `range=30d`. It can report
requests, USD spend, input tokens, cached input tokens and output tokens. Cached
input is part of input, not an extra amount to add again. Legacy history can
omit cost and token fields. Per-model, per-key and custom-range cloud breakdowns
are not available through the documented API as checked on 2026-10-10. Consult
the [cloud usage contract](https://docs.ollama.com/api/cloud-usage) and
[Ollama Settings → Usage](https://ollama.com/settings) for website-only details.

Local model graphs are explicitly **recorded Tlamatini chat activity**. They do
not reconstruct earlier history or include external applications, child agents,
unmeasured calls or every call made by the Ollama account. Recording starts with
this feature. Missing output measurements and failed/pending ledger writes are
reported. A missing model name is described as “Model name not reported”, never
guessed. Blank inventory metadata is omitted instead of labeled “Unknown”.

The cloud account is the one reached through Tlamatini's configured Ollama
endpoint and credentials, which can differ from a browser login. Signing into
the website alone does not change the daemon's account. Local ledger data is
scoped to the Tlamatini user; cloud account data follows the server configuration.
Credentials stay server-side. A changed browser session hides the old user's
view and requires reload. A failed refresh can retain a dated snapshot only
after the same Ollama account identity is verified again.

## Implementation and delivery

- `usage_provider.py`: bounded parallel read-only requests to `/api/me`,
  `/api/balance`, both usage ranges, `/api/tags`, `/api/ps` and `/api/version`;
  validated responses, timeouts, response-size limits, single-flight caching,
  credential-safe redirect refusal and account-aware stale data.
- `context_governor.py` registers a usage sink through `apps.py`.
  `record_call_usage` emits real completed-call counts; at-rest gauge probes
  do not create ledger entries. `usage_tracking.py` queues writes without
  blocking inference. Model `UsageDaily`, migration `0213_usage_ledger`, groups
  by user, model and UTC date. It stores counters and timestamps, not prompts,
  response text or credentials. The bounded queue is best-effort accounting,
  not a billing ledger; abrupt termination can lose queued writes.
- `usage_views.py` serves authenticated, read-only, non-cacheable
  `GET /agent/usage/?range=7d|30d`. Local and cloud failures are independent.
  There is no manual allowance editor or settings POST endpoint.
- `usage_dialog.html`, `usage_dashboard.js` and `usage_dashboard.css` are
  included by `agent_page.html`. Keep the About entry outside long-operation
  locks and preserve focus handling, session checks, escaping and shared theme.
- `build.py`, `build_runtime_assets.py` and `copy_source_assets.py` explicitly
  carry the backend modules, migration, template, static assets and relevant
  source tests/harnesses. The cache suffix is `-usage-2`. Existing migration and
  database backup/restore mechanisms are unchanged.

## Verification and limits

The 2026-10-10 source verification passed **18 Usage tests**, **202 existing
regressions** and **24 visible browser checks**, plus collected-static byte
parity. The browser compared a signed-in Pro account with the live Ollama
website before and after a real model request, and opened/refreshed Usage while
that request ran. Geometry measured 59.2%, body text 14.08 px and heading 16 px.
Other plan layouts, failures, zero values, missing metrics and account changes
used explicitly synthetic fixtures, not live Free/Max/Unlimited accounts.

Both self-modify and self-update inclusion sweeps passed. Those checks prove
source/asset carriage, not a rebuilt executable or installed update. No
installer, real self-update or self-rebuild was run for this feature. The
isolated browser run had an unavailable System-Metrics sidecar; its real model
answer and Usage checks completed, but this does not certify the full product.

For reproduction, follow the repository's [visible execution policy](../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md)
first: verified foreground console, explicit headed browser and live monitoring.
The focused suite is `agent.test_usage`; the headed harness is
`scripts/usage_dashboard_visible.py`, with live and synthetic checks in its two
companion modules. Use an isolated test database. Do not run `build.py` merely
to validate documentation: it deletes the source database and wipes `dist/`.

Local evidence is retained under `Temp/usage-visible/` and
`Temp/usage-revision-v2/`; it contains account observations and is not a public
documentation asset. No private balance, account name or authenticated screenshot
is embedded in this guide, the PDF or the presentation.
