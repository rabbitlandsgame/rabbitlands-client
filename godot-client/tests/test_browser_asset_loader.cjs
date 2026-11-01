const {test} = require('node:test');
const assert = require('node:assert/strict');
const {webcrypto, createHash} = require('node:crypto');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../src/platform/browser_assets.js'), 'utf8');
const describe = (text, extension) => {
    const bytes = Buffer.from(text);
    const sha256 = createHash('sha256').update(bytes).digest('hex');
    return {file: `${sha256}.${extension}`, bytes: bytes.length, sha256};
};

async function run(change = () => {}) {
    const wasm = describe('wasm fixture', 'wasm');
    const parts = [describe('first', 'bin'), describe('second', 'bin')];
    const manifest = {schema: 1, base_url: 'https://raw.githubusercontent.com/example/assets/commit/',
        wasm, pack: {bytes: 11, parts}, archives: []};
    const payloads = new Map([[wasm.file, 'wasm fixture'], [parts[0].file, 'first'], [parts[1].file, 'second']]);
    change(manifest, payloads);
    const calls = [], downloads = [];
    const context = vm.createContext({URL, Blob, crypto: webcrypto,
        location: {href: 'http://127.0.0.1:8060/'},
        fetch: async (url, options) => {
            if (url === 'browser-assets.json') return new Response(JSON.stringify(manifest));
            downloads.push({url: String(url), options});
            const payload = payloads.get(new URL(url).pathname.split('/').at(-1));
            return new Response(payload ?? '', {status: payload === undefined ? 404 : 200});
        }});
    vm.runInContext(source, context);
    const engine = {init: async exe => calls.push(['init', exe]),
        preloadFile: async (buffer, name) => calls.push(['pack', Buffer.from(buffer).toString(), name]),
        start: async cfg => calls.push(['start', ...cfg.args])};
    let error;
    try { await context.RabbitLandsBrowser.start(engine, {executable: 'index', args: ['--verbose']}); }
    catch (err) { error = err; }
    return {calls, downloads, error};
}

test('verified cross-origin payloads start the ordinary package and preserve arguments', async () => {
    const result = await run();
    assert.equal(result.error, undefined);
    assert.deepEqual(result.calls, [['init', 'index'], ['pack', 'firstsecond', 'index.pck'],
        ['start', '--main-pack', 'index.pck', '--verbose']]);
    assert.equal(result.downloads.length, 3);
    assert.ok(result.downloads.every(d => d.url.startsWith('https://raw.githubusercontent.com/')));
    assert.ok(result.downloads.every(d => d.options.credentials === 'omit' && d.options.mode === 'cors'));
});

test('same-length corrupted bytes never reach the game', async () => {
    const result = await run((m, p) => p.set(m.pack.parts[0].file, 'wrong'));
    assert.match(result.error.message, /incomplete or outdated/);
    assert.ok(!result.calls.some(c => c[0] === 'pack' || c[0] === 'start'));
});

test('missing payloads and inconsistent package lengths never start the game', async () => {
    for (const change of [(m, p) => p.delete(m.pack.parts[1].file), m => m.pack.bytes++]) {
        const result = await run(change);
        assert.ok(result.error);
        assert.ok(!result.calls.some(c => c[0] === 'start'));
    }
});

test('remote plaintext asset hosting is refused before runtime initialization', async () => {
    const result = await run(m => m.base_url = 'http://assets.example.com/');
    assert.match(result.error.message, /HTTPS/);
    assert.deepEqual(result.calls, []);
});
