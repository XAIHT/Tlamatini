/* Tlamatini Author Banner — Angela López Mendoza */
/* Run from a verified, visible foreground PowerShell -NoExit console.
 * Rebuilds the committed offline editor; application startup needs no npm. */
import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const destination = path.join(root, 'Tlamatini/agent/static/agent/vendor/canvas-editor');
await mkdir(destination, { recursive: true });
const result = await build({
    absWorkingDir: root,
    entryPoints: ['scripts/canvas_editor_entry.mjs'],
    outfile: path.join(destination, 'editor.js'),
    bundle: true, minify: true, format: 'iife', platform: 'browser', target: ['es2020'],
    metafile: true, legalComments: 'none',
    banner: { js: '/* Tlamatini Author Banner — Angela López Mendoza. CodeMirror 6; third-party licenses in LICENSES.txt. */' },
});

// pnpm resolves inputs through nested .pnpm/.../node_modules paths. The last
// package boundary identifies the actual dependency, not the .pnpm store.
const packages = new Map();
for (const input of Object.keys(result.metafile.inputs)) {
    const normalized = input.replaceAll('\\', '/');
    const match = [...normalized.matchAll(/node_modules\/((?:@[^/]+\/)?[^/]+)/g)].at(-1);
    if (match) packages.set(normalized.slice(0, match.index + match[0].length), match[1]);
}
const notices = [];
const versions = {};
for (const [location, name] of [...packages].sort(([a], [b]) => a.localeCompare(b))) {
    const directory = path.join(root, location);
    const metadata = JSON.parse(await readFile(path.join(directory, 'package.json'), 'utf8'));
    versions[name] = metadata.version;
    let license;
    for (const filename of ['LICENSE', 'LICENSE.md', 'LICENSE.txt']) {
        try { license = await readFile(path.join(directory, filename), 'utf8'); break; }
        catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    if (!license) throw new Error(`Missing bundled dependency license: ${name}`);
    notices.push(`${name} ${metadata.version}\n${'='.repeat(72)}\n${license.trim()}\n`);
}
await writeFile(path.join(destination, 'LICENSES.txt'), notices.join('\n'), 'utf8');
const bytes = await readFile(path.join(destination, 'editor.js'));
let lockFile = 'package-lock.json';
let lock;
try { lock = await readFile(path.join(root, lockFile)); }
catch (error) {
    if (error.code !== 'ENOENT') throw error;
    lockFile = 'pnpm-lock.yaml';
    lock = await readFile(path.join(root, lockFile));
}
await writeFile(path.join(destination, 'manifest.json'), JSON.stringify({
    source: 'scripts/canvas_editor_entry.mjs',
    build: 'node scripts/build_canvas_editor.mjs (visible foreground console)',
    bytes: bytes.length,
    sha256: createHash('sha256').update(bytes).digest('hex'),
    lock_file: lockFile,
    lock_sha256: createHash('sha256').update(lock).digest('hex'),
    packages: versions,
}, null, 2) + '\n');
console.log(`Bundled offline canvas editor: ${bytes.length} bytes, ${packages.size} licensed packages.`);
