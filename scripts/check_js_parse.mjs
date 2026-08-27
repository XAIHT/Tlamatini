/*
 * Parse-gate every browser JS module with `node --check`.
 *
 * A JS file that does not parse at all (e.g. statements pasted into the middle
 * of an object literal during an agent addition -- create_new_agent.md Step 5b
 * touches SIX locations in acp-canvas-core.js, one of them the classMap object
 * literal) produces a completely dead page with no error visible anywhere until
 * you open the browser console. This costs one line to prevent.
 *
 * Exits non-zero on the first parse failure so a caller (npm run lint) fails.
 */
import { readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const here = dirname(fileURLToPath(import.meta.url));
const jsDir = join(here, "..", "Tlamatini", "agent", "static", "agent", "js");

let files;
try {
    files = readdirSync(jsDir).filter((f) => f.endsWith(".js"));
} catch (e) {
    console.error(`check_js_parse: cannot read ${jsDir}: ${e.message}`);
    process.exit(1);
}

let failed = 0;
for (const f of files) {
    try {
        execFileSync(process.execPath, ["--check", join(jsDir, f)], { stdio: "pipe" });
    } catch (e) {
        failed += 1;
        const msg = (e.stderr && e.stderr.toString()) || e.message;
        console.error(`PARSE FAIL: ${f}\n${msg}`);
    }
}

if (failed > 0) {
    console.error(`check_js_parse: ${failed} file(s) failed to parse.`);
    process.exit(1);
}
console.log(`check_js_parse: OK -- ${files.length} JS files parse cleanly.`);
