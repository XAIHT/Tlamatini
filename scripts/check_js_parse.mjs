/* Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 */
/*
 * Parse every owned JavaScript file and every shipped browser vendor file.
 * Run from a verified visible foreground console; no application code is executed.
 * Git supplies source scope; delivered self-modify snapshots use the same tree
 * walk with generated/runtime/user-data directories excluded.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const skipped = new Set([
    ".git", "Temp", "dist", "build", "python", "node_modules", "__pycache__",
    "output", "context_files", "content_generated", "doc_generated", "pools",
]);
const keptDirectories = new Set([
    "Tlamatini/agent/static/agent/vendor/pdfjs/build",
    "Tlamatini/agent/static/agent/vendor/frontend/bootstrap/dist",
    "Tlamatini/agent/static/agent/vendor/frontend/jquery/dist",
    "Tlamatini/agent/static/agent/vendor/frontend/dompurify/dist",
]);
const extension = /\.(?:js|mjs|cjs)$/i;
const files = new Set();
function walk(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
        if (entry.isSymbolicLink()) continue;
        const path = join(directory, entry.name);
        const name = relative(root, path).replaceAll("\\", "/");
        if (skipped.has(entry.name) && !keptDirectories.has(name)) continue;
        if (entry.isDirectory()) walk(path);
        else if (extension.test(entry.name)) files.add(path);
    }
}
if (existsSync(join(root, ".git"))) {
    const listed = execFileSync("git", ["ls-files", "-z", "--cached", "--others", "--exclude-standard"], {
        cwd: root, encoding: "utf8", maxBuffer: 32 * 1024 * 1024,
    });
    for (const name of listed.split("\0")) {
        const path = join(root, name);
        if (extension.test(name) && existsSync(path) && statSync(path).isFile()) files.add(path);
    }
} else {
    walk(root);
}
// Some reproducibly vendored browser files are ignored by Git but ship in pkg.zip.
walk(join(root, "Tlamatini", "agent", "static", "agent"));
if (!files.size) throw new Error("No JavaScript files found; refusing an empty parse gate.");
let failed = 0;
for (const path of [...files].sort()) {
    const name = relative(root, path).replaceAll("\\", "/");
    // PDF.js also delivers ES modules under .js filenames, including import.meta.
    const moduleSource = path.endsWith(".mjs") || name.includes("/vendor/pdfjs/");
    try {
        execFileSync(process.execPath, ["--check", "--input-type=" + (moduleSource ? "module" : "commonjs")], {
            input: readFileSync(path), stdio: ["pipe", "pipe", "pipe"],
        });
    } catch (error) {
        failed += 1;
        console.error("PARSE FAIL: " + name + "\n" + (error.stderr?.toString() || error.message));
    }
}
if (failed) {
    console.error("check_js_parse: " + failed + " file(s) failed to parse.");
    process.exit(1);
}
console.log("check_js_parse: OK -- " + files.size + " source, harness and vendor files parse cleanly.");
