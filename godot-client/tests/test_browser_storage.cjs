const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createHash, webcrypto} = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// An override permits an isolated test worktree to qualify an integration's
// pending implementation without copying another agent's source into Git.
const source = fs.readFileSync(process.env.RL_BROWSER_STORAGE_SOURCE ||
    path.join(__dirname, '../src/platform/browser_storage.js'), 'utf8');
const failure = name => Object.assign(new Error('Private path must not escape: C:/Private/Player'), {name});
let uuidSequence = 0;
const nextId = () => `00000000-0000-4000-8000-${String(++uuidSequence).padStart(12, '0')}`;
function row(text = 'game bytes', extension = 'zip') {
    const bytes = Buffer.from(text);
    const sha256 = createHash('sha256').update(bytes).digest('hex');
    return {file: `${sha256}.${extension}`, bytes: bytes.length, sha256};
}
const fixture = row();
const manifest = {wasm: fixture, pack: {parts: []}, archives: [], groups: {}};

function idb(records = new Map(), options = {}) {
    const reads = [];
    const connection = {
        createObjectStore() {},
        transaction(_store, mode) {
            const transaction = {objectStore: () => ({
                get(key) { reads.push(key); return request(key); },
                put(value, key) { return request(key, value); }
            })};
            function request(key, value) {
                const request = {};
                queueMicrotask(() => {
                    if (options.failRead && mode === 'readonly' || options.failWrite && mode === 'readwrite') {
                        transaction.error = failure('QuotaExceededError');
                        transaction.onerror?.();
                    } else {
                        if (mode === 'readwrite') records.set(key, value);
                        request.result = records.get(key);
                        transaction.oncomplete?.();
                    }
                });
                return request;
            }
            return transaction;
        }
    };
    return {reads, records, open() {
        const request = {};
        queueMicrotask(() => {
            if (options.failOpen) { request.error = failure('UnknownError'); request.onerror?.(); }
            else { request.result = connection; request.onupgradeneeded?.(); request.onsuccess?.(); }
        });
        return request;
    }};
}

function folder(name = 'Private player folder', state) {
    state ||= {name, files: new Map(), children: new Map(), query: 'granted', request: 'granted',
        queries: [], requests: [], allocations: 0, opens: [], commits: 0, aborts: 0};
    return {name: state.name, state,
        async isSameEntry(other) { return other.state === state; },
        async queryPermission(options) { state.queries.push(options.mode); return state.query; },
        async requestPermission(options) { state.requests.push(options.mode); return state.request; },
        async getDirectoryHandle(name, options) {
            assert.equal(name, 'RabbitLandsAssets');
            assert.equal(options.create, true);
            if (state.directoryError) throw failure(state.directoryError);
            if (!state.children.has(name)) state.children.set(name, folder(name));
            return state.children.get(name);
        },
        async getFileHandle(name, options = {}) {
            state.opens.push({name, create: Boolean(options.create)});
            if (state.openError) throw failure(state.openError);
            if (!state.files.has(name) && !options.create) throw failure('NotFoundError');
            return {
                async getFile() {
                    const stored = state.files.get(name);
                    if (state.readError) throw failure(state.readError);
                    return {size: stored.size ?? stored.bytes.length, async arrayBuffer() {
                        state.allocations++;
                        return Uint8Array.from(stored.bytes).buffer;
                    }};
                },
                async createWritable() {
                    let staged;
                    return {
                        async write(bytes) {
                            if (state.writeError) throw failure(state.writeError);
                            staged = Buffer.from(bytes);
                        },
                        async close() {
                            if (state.closeError) throw failure(state.closeError);
                            state.files.set(name, {bytes: staged}); state.commits++;
                        },
                        async abort() { state.aborts++; }
                    };
                }
            };
        }
    };
}
const dataFolder = handle => handle.state.children.get('RabbitLandsAssets');

function session(options = {}) {
    const database = options.database || idb();
    const location = new URL(options.url || 'https://play.rabbitlandsgame.com/');
    const window = {};
    window.self = window; window.top = options.framed ? {} : window;
    const picks = [], warnings = [];
    const context = vm.createContext({URL, URLSearchParams, Blob, Response, window, location,
        isSecureContext: options.secure !== false,
        crypto: {subtle: webcrypto.subtle, randomUUID: nextId},
        indexedDB: options.noIdb ? undefined : database,
        history: {replaceState(_state, _title, url) { location.href = url; }},
        console: {warn(...args) { warnings.push(args); }},
        showDirectoryPicker: options.unsupported ? undefined : async pickerOptions => {
            picks.push(pickerOptions);
            if (options.pickerError) throw failure(options.pickerError);
            return options.handle;
        }});
    vm.runInContext(source, context);
    return {api: context.RabbitLandsAssetStorage, database, location, picks, warnings};
}

test('folder saves commit verified bytes, reuse disk, and never touch unrelated files', async () => {
    const handle = folder(); const s = session({handle});
    await s.api.prepare(manifest);
    assert.equal(await s.api.choose_folder(), true);
    assert.equal(s.picks[0].mode, 'readwrite');
    const target = dataFolder(handle);
    target.state.files.set('unrelated.txt', {bytes: Buffer.from('keep')});
    assert.equal(await s.api.write(fixture, Buffer.from('game bytes')), true);
    assert.equal(target.state.commits, 1);
    assert.equal(Buffer.from(await s.api.read(fixture)).toString(), 'game bytes');
    assert.equal(target.state.files.get('unrelated.txt').bytes.toString(), 'keep');
    assert.equal(s.api.status().mode, 'folder');
    assert.equal(s.api.status().remembered, true);
    assert.equal(s.api.status().folder_saves, 1);
});

test('a new visit restores a granted handle without picking or requesting permission', async () => {
    const handle = folder(); const first = session({handle});
    await first.api.prepare(manifest); await first.api.choose_folder();
    const id = first.database.records.get('active').id;
    const next = session({database: first.database, handle});
    await next.api.prepare(manifest);
    assert.equal(next.api.status().mode, 'folder');
    assert.equal(next.api.status().remembered, true);
    assert.equal(next.picks.length, 0);
    assert.deepEqual(handle.state.queries, ['readwrite']);
    assert.equal(handle.state.requests.length, 0);
    assert.equal(new URL(next.api.shortcut().url).hash, '#rl-assets=' + id);
});

test('remembered permission waits for explicit continuation and retains denied recovery', async () => {
    const handle = folder(); const database = idb(); const id = nextId();
    database.records.set('active', {mode: 'folder', id});
    database.records.set('folder:' + id, {id, handle});
    handle.state.query = 'prompt'; handle.state.request = 'denied';
    const s = session({database}); await s.api.prepare(manifest);
    assert.equal(s.api.status().needs_permission, true);
    assert.equal(handle.state.requests.length, 0);
    assert.equal(await s.api.continue_saved(), false);
    assert.equal(s.api.status().needs_permission, true);
    assert.equal(s.api.status().mode, 'browser');
    handle.state.request = 'granted';
    assert.equal(await s.api.continue_saved(), true);
    assert.deepEqual(handle.state.requests, ['readwrite', 'readwrite']);
    assert.equal(s.api.status().needs_permission, false);
    assert.equal(s.api.status().mode, 'folder');
});

test('cancelling a picker keeps an existing working folder and ID', async () => {
    const handle = folder(); const first = session({handle});
    await first.api.prepare(manifest); await first.api.choose_folder();
    const s = session({database: first.database, pickerError: 'AbortError'});
    await s.api.prepare(manifest);
    const before = s.api.shortcut().url;
    assert.equal(await s.api.choose_folder(), false);
    assert.equal(s.api.status().mode, 'folder');
    assert.equal(s.api.shortcut().url, before);
    assert.equal(s.api.status().folder_error, '');
});

test('same-entry aliases retain their stable storage ID', async () => {
    const original = folder(); const database = idb(); const id = nextId();
    database.records.set('active', {mode: 'folder', id});
    database.records.set('folder:' + id, {id, handle: original});
    const s = session({database, handle: folder('alias', original.state)});
    await s.api.prepare(manifest);
    assert.equal(await s.api.choose_folder(), true);
    assert.equal(database.records.get('active').id, id);
    assert.equal([...database.records.keys()].filter(key => key.startsWith('folder:')).length, 1);
});

test('reselecting a pending remembered folder keeps existing shortcuts valid', async () => {
    const original = folder(); const database = idb(); const id = nextId();
    original.state.query = 'prompt';
    database.records.set('active', {mode: 'folder', id});
    database.records.set('folder:' + id, {id, handle: original});
    const s = session({database, handle: folder('alias', original.state)});
    await s.api.prepare(manifest);
    assert.equal(s.api.status().needs_permission, true);
    assert.equal(await s.api.choose_folder(), true);
    assert.equal(database.records.get('active').id, id,
        'a new picker grant must reuse the remembered identity for the same entry');
});

test('invalid shortcut IDs never become IndexedDB folder lookups; unknown valid IDs need recovery', async () => {
    for (const value of ['../../private', '__proto__', 'C:/Private/Player', 'not-a-uuid']) {
        const s = session({url: 'https://play.rabbitlandsgame.com/#rl-assets=' + encodeURIComponent(value)});
        await s.api.prepare(manifest);
        assert.equal(s.api.status().mode, 'browser');
        assert.ok(s.database.reads.every(key => key === 'active'));
    }
    const id = nextId(); const s = session({url: 'https://play.rabbitlandsgame.com/#rl-assets=' + id});
    await s.api.prepare(manifest);
    assert.ok(s.database.reads.includes('folder:' + id));
    assert.equal(s.api.status().mode, 'browser');
    assert.equal(s.api.status().remembered, false);
});

test('wrong file sizes are rejected before allocation and invalid rows before filesystem access', async () => {
    const handle = folder(); const s = session({handle});
    await s.api.prepare(manifest); await s.api.choose_folder();
    const target = dataFolder(handle);
    target.state.files.set(fixture.file, {bytes: Buffer.from('huge'), size: 2 ** 40});
    assert.equal(await s.api.read(fixture), null);
    assert.equal(target.state.allocations, 0);
    assert.equal(s.api.status().folder_corrupt, 1);
    const opens = target.state.opens.length;
    for (const invalid of [{...fixture, file: '../secret'}, {...fixture, bytes: 64 * 1024 * 1024 + 1}]) {
        await assert.rejects(s.api.read(invalid), /Invalid saved game file/);
        await assert.rejects(s.api.write(invalid, Buffer.alloc(1)), /Invalid saved game file/);
    }
    assert.equal(target.state.opens.length, opens);
    assert.equal(await s.api.write(fixture, Buffer.alloc(1)), false);
    assert.equal(target.state.opens.length, opens);
});

test('missing files remain ordinary misses; read permission failure enables browser fallback', async () => {
    const handle = folder(); const s = session({handle});
    await s.api.prepare(manifest); await s.api.choose_folder();
    assert.equal(await s.api.read(fixture), null);
    assert.equal(s.api.status().mode, 'folder');
    dataFolder(handle).state.openError = 'NotAllowedError';
    assert.equal(await s.api.read(fixture), null);
    assert.equal(s.api.status().mode, 'browser');
    assert.equal(await s.api.write(fixture, Buffer.from('game bytes')), false);
    assert.equal(s.api.status().folder_error, 'NotAllowedError');
    assert.ok(!JSON.stringify(s.api.status()).includes('Private'));
});

test('failed close aborts saving, preserves prior file, and reports fallback without private paths', async () => {
    const handle = folder(); const s = session({handle});
    await s.api.prepare(manifest); await s.api.choose_folder();
    const target = dataFolder(handle);
    target.state.files.set(fixture.file, {bytes: Buffer.from('previous')});
    target.state.closeError = 'QuotaExceededError';
    assert.equal(await s.api.write(fixture, Buffer.from('game bytes')), false);
    assert.equal(target.state.files.get(fixture.file).bytes.toString(), 'previous');
    assert.equal(target.state.aborts, 1);
    assert.equal(s.api.status().folder_saves, 0);
    assert.equal(s.api.status().mode, 'browser');
    assert.equal(s.api.status().folder_error, 'QuotaExceededError');
    assert.ok(!JSON.stringify(s.api.status()).includes('Private'));
});

test('shortcut retains only origin/path and opaque selection, omitting folder names and URL secrets', async () => {
    const handle = folder('C:/Private/Player/My Games');
    const s = session({handle, url: 'https://play.rabbitlandsgame.com/play/?password=secret&server=private#token=secret'});
    await s.api.prepare(manifest); await s.api.choose_folder();
    const shortcut = s.api.shortcut();
    assert.equal(shortcut.filename, 'Rabbit Lands.url');
    assert.match(shortcut.url, /^https:\/\/play\.rabbitlandsgame\.com\/play\/#rl-assets=[a-f0-9-]{36}$/);
    assert.equal(shortcut.text, '[InternetShortcut]\r\nURL=' + shortcut.url + '\r\n');
    assert.ok(!/Private|password|secret|token|server/.test(shortcut.text));
    await s.api.use_browser();
    assert.equal(s.api.shortcut().url, 'https://play.rabbitlandsgame.com/play/#rl-assets=browser');
    assert.equal(s.database.records.get('active').mode, 'browser');
});

test('unremembered folders work for this visit but cannot generate misleading remembered shortcuts', async () => {
    for (const unavailable of [{database: idb(new Map(), {failWrite: true})},
            {database: idb(new Map(), {failOpen: true})}, {noIdb: true}]) {
        const s = session({handle: folder(), ...unavailable});
        await s.api.prepare(manifest);
        assert.equal(await s.api.choose_folder(), true);
        assert.equal(s.api.status().mode, 'folder');
        assert.equal(s.api.status().remembered, false);
        assert.equal(await s.api.write(fixture, Buffer.from('game bytes')), true);
        assert.throws(() => s.api.shortcut(), /could not remember/);
        await s.api.use_browser();
        assert.match(s.api.shortcut().url, /rl-assets=browser$/);
    }
});

test('browser shortcut overrides a saved folder without requesting or deleting its access', async () => {
    const handle = folder(); const database = idb(); const id = nextId();
    database.records.set('active', {mode: 'folder', id});
    database.records.set('folder:' + id, {id, handle});
    const s = session({database, url: 'https://play.rabbitlandsgame.com/#rl-assets=browser'});
    await s.api.prepare(manifest);
    assert.equal(s.api.status().mode, 'browser');
    assert.equal(s.api.status().needs_permission, false);
    assert.equal(handle.state.queries.length + handle.state.requests.length, 0);
    await s.api.use_browser();
    assert.ok(database.records.has('folder:' + id));
    assert.equal(database.records.get('active').mode, 'browser');
});

test('unsupported, insecure and framed contexts preserve the browser fallback without opening a picker', async () => {
    for (const option of [{unsupported: true}, {secure: false}, {framed: true}]) {
        const s = session(option); await s.api.prepare(manifest);
        assert.equal(s.api.status().supported, false);
        assert.equal(await s.api.choose_folder(), false);
        assert.equal(s.picks.length, 0);
        assert.equal(s.api.status().mode, 'browser');
    }
    assert.throws(() => session({framed: true}).api.shortcut(), /standalone/);
    assert.throws(() => session({url: 'http://example.test/'}).api.shortcut(), /secure/);
    assert.throws(() => session({url: 'https://name:password@play.rabbitlandsgame.com/'}).api.shortcut(), /secure/);
});

test('cache migration copies only manifest-listed, integrity-checked existing downloads', async () => {
    const handle = folder(); const s = session({handle});
    const tampered = row('expected bytes');
    const requests = [fixture.sha256, tampered.sha256, 'f'.repeat(64)].map(hash =>
        ({url: 'https://play.rabbitlandsgame.com/__rabbitlands_assets__/' + hash}));
    const cache = {keys: async () => requests, match: async url => new Response(
        String(url).includes(fixture.sha256) ? 'game bytes' : 'tampered bytes')};
    await s.api.prepare({...manifest, archives: [tampered]}, cache);
    assert.equal(await s.api.choose_folder(), true);
    assert.deepEqual([...dataFolder(handle).state.files.keys()], [fixture.file]);
    assert.equal(s.api.status().folder_saves, 1);
});

test('browser-cache migration errors cannot turn a working folder selection into failure', async () => {
    for (const failing of ['keys', 'match']) {
        const handle = folder(); const s = session({handle});
        const cache = {
            async keys() {
                if (failing === 'keys') throw failure('UnknownError');
                return [{url: 'https://play.rabbitlandsgame.com/__rabbitlands_assets__/' + fixture.sha256}];
            },
            async match() { throw failure('UnknownError'); }
        };
        await s.api.prepare(manifest, cache);
        assert.equal(await s.api.choose_folder(), true,
            'cache migration is optional after the folder has activated');
        assert.equal(s.api.status().mode, 'folder');
        assert.equal(s.api.status().remembered, true);
        assert.equal(await s.api.write(fixture, Buffer.from('game bytes')), true);
    }
});
