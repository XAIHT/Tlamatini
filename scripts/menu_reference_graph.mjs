/* Tlamatini Author Banner — Angela López Mendoza
 * Run only in the verified visible test console. Never imports application JS.
 * Scope-aware static references, including callback/function owners and writes.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
// Resolve through ESLint's own dependency directory, including pnpm layouts.
const require = createRequire(import.meta.url);
const eslintRequire = createRequire(require.resolve('eslint/package.json'));
const espree = eslintRequire('espree');
const scope = eslintRequire('eslint-scope');

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const directory = path.join(root, 'Tlamatini/agent/static/agent/js');
const output = process.argv[2];
if (!output) throw new Error('Supply an output JSON path from the visible test runner.');
const symbols = [], references = [], functions = [], pending = [], fileHashes = {}, interfaceReferences = [];
const { createHash } = await import('node:crypto');
const globals = new Map();
function walk(node, visit, parent = null) {
    if (!node || typeof node.type !== 'string') return;
    visit(node, parent);
    for (const [key, value] of Object.entries(node)) {
        if (['loc', 'range', 'tokens', 'comments'].includes(key)) continue;
        if (Array.isArray(value)) value.forEach(child => walk(child, visit, node));
        else if (value && typeof value === 'object') walk(value, visit, node);
    }
}
for (const filename of fs.readdirSync(directory).filter(name => name.endsWith('.js')).sort()) {
    const absolute = path.join(directory, filename), source = fs.readFileSync(absolute, 'utf8');
    const file = path.relative(root, absolute).replaceAll('\\', '/');
    fileHashes[file] = createHash('sha256').update(source).digest('hex');
    const ast = espree.parse(source, { ecmaVersion: 'latest', sourceType: 'script', loc: true, range: true });
    const parents = new Map(), localFunctions = [];
    walk(ast, (node, parent) => {
        parents.set(node, parent);
        if (/Function/.test(node.type) && !node.type.endsWith('Body')) {
            const name = node.id?.name || parent?.id?.name
                || (parent?.type === 'AssignmentExpression' ? source.slice(parent.left.start ?? parent.left.range[0], parent.left.end ?? parent.left.range[1]) : null)
                || parent?.key?.name || `<callback@${node.loc.start.line}>`;
            const entry = { id: `${file}:${node.range[0]}:function`, file, name, kind: 'function',
                line: node.loc.start.line, start: node.range[0], end: node.range[1] };
            localFunctions.push(entry); functions.push(entry);
        }
    });
    const owner = identifier => localFunctions.filter(fn => fn.start <= identifier.range[0] && fn.end >= identifier.range[1])
        .sort((a, b) => (a.end - a.start) - (b.end - b.start))[0]?.id || `${file}:module`;
    walk(ast, (node, parent) => {
        if (node.type !== 'Literal' || typeof node.value !== 'string') return;
        const key = parent?.type === 'Property' ? (parent.key.name || parent.key.value) : null;
        const method = parent?.type === 'CallExpression' ? parent.callee.property?.name : null;
        if (/^\/(agent|ws)\//.test(node.value) || ['type', 'action', 'event'].includes(key)
                || ['getElementById', 'querySelector', 'querySelectorAll', 'addEventListener'].includes(method)) {
            interfaceReferences.push({ from: owner(node), file, line: node.loc.start.line,
                name: node.value, kind: key ? 'protocol-literal' : method ? 'DOM-or-event-literal' : 'route-literal' });
        }
    });
    symbols.push({ id: `${file}:module`, file, line: 1, name: filename, kind: 'module' });
    const manager = scope.analyze(ast, { ecmaVersion: 2022, sourceType: 'script', optimistic: true });
    for (const current of manager.scopes) for (const variable of current.variables) {
        if (!variable.identifiers.length) continue;
        const identifier = variable.identifiers[0];
        const entry = { id: `${file}:${identifier.range[0]}:${variable.name}`, file, line: identifier.loc.start.line,
            name: variable.name, kind: variable.defs[0]?.type || 'variable', bindingKind: variable.defs[0]?.parent?.kind,
            scope: current.type, owner: owner(identifier),
            declarations: variable.identifiers.map(i => i.loc.start.line) };
        symbols.push(entry);
        if (current.type === 'global') globals.set(variable.name, [...(globals.get(variable.name) || []), entry.id]);
        for (const ref of variable.references) references.push({ from: owner(ref.identifier), to: entry.id,
            file, line: ref.identifier.loc.start.line, name: variable.name, read: ref.isRead(), write: ref.isWrite(),
            call: parents.get(ref.identifier)?.type === 'CallExpression' && parents.get(ref.identifier).callee === ref.identifier,
            resolution: 'lexical' });
    }
    for (const ref of manager.globalScope.through) pending.push({ from: owner(ref.identifier), file,
        line: ref.identifier.loc.start.line, name: ref.identifier.name, read: ref.isRead(), write: ref.isWrite(),
        call: parents.get(ref.identifier)?.type === 'CallExpression' && parents.get(ref.identifier).callee === ref.identifier });
}
const unresolved = [];
for (const ref of pending) {
    const targets = globals.get(ref.name) || [];
    if (!targets.length) unresolved.push(ref);
    for (const to of targets) references.push({ ...ref, to,
        resolution: targets.length === 1 ? 'shared-script-global' : 'ambiguous-global-candidate' });
}
const roots = symbols.filter(s => /Menu|menu|spinner|titleBusy|inLongOperation|lapseLoadingContext|contextEnabled|reConnectEnabled|userCancelledRun/.test(s.name));
const byId = new Map(symbols.map(s => [s.id, s]));
const crossFileConstWrites = references.filter(r => r.write && byId.get(r.to)?.bindingKind === 'const'
    && byId.get(r.to)?.file !== r.file).map(r => ({ ...r, declaration: byId.get(r.to) }));
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, JSON.stringify({ schema: 1, fileHashes, roots: roots.map(s => s.id), symbols, functions, references, unresolved, crossFileConstWrites, interfaceReferences,
    limitations: ['Static references are not proof of execution.', 'Dynamic property dispatch and cross-language string routes are listed separately by the Python runner.',
        'Unresolved browser/library globals and ambiguous names are retained, never silently counted as covered.'] }, null, 2));
console.log(`Reference graph: ${symbols.length} symbols, ${functions.length} functions, ${references.length} references; ${output}`);
