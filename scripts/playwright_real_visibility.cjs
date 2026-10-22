/* Tlamatini Author Banner — Angela López Mendoza */
// Opt-in preload for the visible Interactor harness only. Playwright's own CDP
// session forces every page visible; another CDP session cannot undo its override.
// Intercept that one command in the driver, leaving the installed package intact.
const Module = require('node:module');
const fs = require('node:fs');
const process = require('node:process');
const loadJavaScript = Module._extensions['.js'];
Module._extensions['.js'] = function (module, filename) {
    if (/[/\\](?:coreBundle|crPage)\.js$/.test(filename)) {
        const source = fs.readFileSync(filename, 'utf8');
        const forcedFocus = /(["']Emulation\.setFocusEmulationEnabled["'],\s*\{\s*enabled:\s*)true(\s*\})/g;
        const nativeVisibility = source.replace(forcedFocus, '$1false$2');
        if (nativeVisibility !== source) {
            process.stderr.write('VISIBLE TEST DRIVER: using native tab visibility.\n');
            module._compile(nativeVisibility, filename);
            return;
        }
    }
    loadJavaScript(module, filename);
};
