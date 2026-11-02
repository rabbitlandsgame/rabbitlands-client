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

async function run(change = () => {}, stored = new Map(), runOptions = {}) {
    const wasm = describe('wasm fixture', 'wasm');
    const parts = [describe('first', 'bin'), describe('second', 'bin')];
    const manifest = {schema: 1, base_url: 'https://raw.githubusercontent.com/example/assets/commit/',
        wasm, pack: {bytes: 11, parts}, archives: [describe('art fixture', 'zip')]};
    const payloads = new Map([[wasm.file, 'wasm fixture'], [parts[0].file, 'first'], [parts[1].file, 'second'], [manifest.archives[0].file, 'art fixture']]);
    if (runOptions.libraries) {
        manifest.libraries = [
            {...describe('engine side fixture', 'wasm'), name: 'index.side.wasm', extension: false},
            {...describe('cape fixture', 'wasm'), name: 'browser_cape.wasm', extension: true}];
        payloads.set(manifest.libraries[0].file, 'engine side fixture');
        payloads.set(manifest.libraries[1].file, 'cape fixture');
    }
    change(manifest, payloads);
    const calls = [], downloads = [];
    const context = vm.createContext({URL, Blob, Response, crypto: webcrypto,
        console: {warn() {}}, navigator: {storage: {persist: async () => {
            if (runOptions.denyPersist) throw new Error('Protection unavailable');
            return true;
        }}},
        caches: {open: async () => ({
            match: async key => stored.has(key) ? new Response(stored.get(key)) : undefined,
            put: async (key, response) => {
                if (runOptions.quota) throw Object.assign(new Error('quota'), {name: 'QuotaExceededError'});
                stored.set(key, await response.arrayBuffer());
            },
            delete: async key => stored.delete(key)
        })},
        location: {href: 'http://127.0.0.1:8060/'},
        fetch: async (url, options) => {
            if (url === 'browser-assets.json') return new Response(JSON.stringify(manifest));
            if (String(url).startsWith('blob:')) return fetch(url);
            downloads.push({url: String(url), options});
            if (runOptions.blockNetwork) throw new Error('Network blocked');
            const payload = payloads.get(new URL(url).pathname.split('/').at(-1));
            return new Response(payload ?? '', {status: payload === undefined ? 404 : 200});
        }});
    const originalFetch = context.fetch;
    vm.runInContext(source, context);
    const engine = {config: {update: cfg => calls.push(['libraries', ...cfg.gdextensionLibs])},
        init: async exe => {
            calls.push(['init', exe]);
            if (runOptions.libraries) {
                assert.equal(await (await context.fetch('index.side.wasm')).text(), 'engine side fixture');
                assert.equal(await (await context.fetch(new URL('browser_cape.wasm', context.location.href))).text(), 'cape fixture');
            }
            if (runOptions.initFailure) throw new Error('Initialization failed');
        },
        copyToFS: (name, buffer) => {
            assert.equal(context.RL_BROWSER_TAKE_BUFFER, true);
            calls.push([name === 'index.pck' ? 'pack' : 'archive', Buffer.from(buffer).toString(), name]);
        },
        start: async cfg => calls.push(['start', ...cfg.args])};
    let error;
    try {
        await context.RabbitLandsBrowser.start(engine, {executable: 'index', args: ['--verbose']});
        if (runOptions.archives) await new Promise((resolve, reject) =>
            context.RabbitLandsBrowser.fetch_archive(0, (ok, error) => ok ? resolve() : reject(new Error(error))));
    }
    catch (err) { error = err; }
    assert.equal(context.RL_BROWSER_TAKE_BUFFER, undefined);
    assert.equal(context.fetch, originalFetch);
    assert.equal(context.RL_BROWSER_WASM_URL, undefined);
    return {calls, downloads, error, stats: context.RL_BROWSER_CACHE_STATS};
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

test('dynamic arithmetic libraries reuse verified saved bytes across launches', async () => {
    const stored = new Map();
    const first = await run(undefined, stored, {libraries: true});
    assert.equal(first.error, undefined);
    assert.deepEqual(first.calls[0], ['libraries', 'browser_cape.wasm']);
    assert.equal(first.downloads.length, 5);
    const second = await run(undefined, stored, {libraries: true, blockNetwork: true});
    assert.equal(second.error, undefined);
    assert.equal(second.downloads.length, 0);
    assert.equal(second.stats.hits, 5);
});

test('corrupted arithmetic libraries never reach the dynamic linker', async () => {
    const result = await run((manifest, payloads) => payloads.set(manifest.libraries[0].file, 'corrupt'),
        new Map(), {libraries: true});
    assert.match(result.error.message, /incomplete or outdated/);
    assert.deepEqual(result.calls, []);
});

test('arithmetic library paths and aliases must be unambiguous', async () => {
    for (const name of ['../index.side.wasm', '/index.side.wasm', 'https://other.test/lib.wasm', 'browser_cape.wasm']) {
        const result = await run(manifest => manifest.libraries[0].name = name, new Map(), {libraries: true});
        assert.match(result.error.message, /library name/);
        assert.equal(result.downloads.length, 0);
    }
});

test('failed engine initialization restores normal fetch and temporary runtime URLs', async () => {
    const result = await run(undefined, new Map(), {libraries: true, initFailure: true});
    assert.match(result.error.message, /Initialization failed/);
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


test('a new browser session reuses runtime, package and art without network, even after a base URL change', async () => {
    const stored = new Map();
    const cold = await run(() => {}, stored, {archives: true});
    assert.equal(cold.error, undefined);
    assert.equal(cold.downloads.length, 4);
    assert.equal(stored.size, 4);
    const warm = await run(m => m.base_url = 'https://raw.githubusercontent.com/example/assets/new-commit/', stored,
        {archives: true, blockNetwork: true});
    assert.equal(warm.error, undefined);
    assert.equal(warm.downloads.length, 0);
    assert.equal(warm.stats.hits, 4);
    assert.equal(warm.calls.at(-1)[1], 'art fixture');
});

test('a corrupt cached part is fetched again and repaired without discarding other files', async () => {
    const stored = new Map();
    await run(() => {}, stored);
    const key = [...stored.keys()].find(k => k.endsWith(describe('first', 'bin').sha256));
    stored.set(key, Buffer.from('wrong'));
    const repaired = await run(() => {}, stored);
    assert.equal(repaired.error, undefined);
    assert.equal(repaired.downloads.length, 1);
    assert.equal(repaired.stats.hits, 2);
    const warm = await run(() => {}, stored, {blockNetwork: true});
    assert.equal(warm.error, undefined);
    assert.equal(warm.downloads.length, 0);
});

test('storage quota failure remains visible and does not stop a valid game load', async () => {
    const result = await run(() => {}, new Map(), {quota: true});
    assert.equal(result.error, undefined);
    assert.equal(result.stats.storage_error, 'QuotaExceededError');
    assert.ok(result.calls.some(c => c[0] === 'start'));
});

test('denied eviction protection still permits saving files across visits', async () => {
    const stored = new Map();
    const result = await run(() => {}, stored, {denyPersist: true});
    assert.equal(result.error, undefined);
    assert.equal(result.stats.storage_error, '');
    assert.equal(result.stats.persistent, false);
    assert.equal(stored.size, 3);
});
