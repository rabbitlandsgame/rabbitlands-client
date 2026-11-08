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
    const calls = [], downloads = [], events = [], progress = [], cacheReads = [], digests = [];
    let activeDownloads = 0, maximumDownloads = 0;
    const timers = new Set();
    const storage = {
        prepare: async () => {}, status: () => ({mode: runOptions.folder && !runOptions.folderInterrupted ? 'folder' : 'browser'}),
        read: async row => {
            await runOptions.onFolderRead?.(row, {context, stored, events});
            return !runOptions.folderInterrupted && runOptions.folder?.get(row.sha256) || null;
        },
        write: async (row, bytes) => {
            if (!runOptions.folder || runOptions.folderFailure || runOptions.folderInterrupted) return false;
            runOptions.folder.set(row.sha256, bytes);
            events.push(['folder', row.file]);
            runOptions.onSaved?.(row);
            return true;
        },
        hit() {}, corrupt() {},
        // Legacy safety cases explicitly exercise the earlier on-demand mode.
        // A separate case omits the UI to prove ALL is the loader default.
        preload_choice: async summary => {runOptions.onChoice?.(summary); return runOptions.preloadMode || 'needed';},
        preload_progress: state => {progress.push({...state}); runOptions.onProgress?.(state);},
        preload_cancelled: () => Boolean(runOptions.cancelled?.()),
        ...(runOptions.onFailure ? {preload_failure: error => runOptions.onFailure(error, {context, stored, events})} : {})
    };
    const context = vm.createContext({URL, Blob, Response, AbortController,
        crypto: {subtle: {digest: async (algorithm, bytes) => {
            digests.push(bytes.byteLength); return webcrypto.subtle.digest(algorithm, bytes);
        }}},
        setTimeout: (callback, delay) => {
            const timeout = runOptions.fastTimeout === true ? 15 : runOptions.fastTimeout || delay;
            const timer = setTimeout(() => {timers.delete(timer); callback();}, timeout);
            timers.add(timer); return timer;
        },
        clearTimeout: timer => {timers.delete(timer); clearTimeout(timer);},
        setInterval: (callback, delay) => {const timer = setInterval(callback, delay); timers.add(timer); return timer;},
        clearInterval: timer => {timers.delete(timer); clearInterval(timer);},
        console: {warn() {}}, navigator: {storage: {persist: async () => {
            if (runOptions.denyPersist) throw new Error('Protection unavailable');
            return true;
        }}},
        caches: {open: async () => {
            if (runOptions.cacheUnavailable) throw new Error('Cache unavailable');
            return {
            match: async key => {cacheReads.push(key); return stored.has(key) ? new Response(stored.get(key)) : undefined;},
            put: async (key, response) => {
                if (typeof runOptions.quota === 'function' ? runOptions.quota() : runOptions.quota) {
                    throw Object.assign(new Error('quota'), {name: 'QuotaExceededError'});
                }
                stored.set(key, await response.arrayBuffer());
                events.push(['cache', key]);
                runOptions.onSaved?.(key);
            },
            delete: async key => stored.delete(key)
        };}},
        ...(runOptions.noStorageModule ? {} : {RabbitLandsAssetStorage: storage}),
        location: {href: 'http://127.0.0.1:8060/'},
        fetch: async (url, options) => {
            if (url === 'browser-assets.json') return new Response(JSON.stringify(manifest));
            if (String(url).startsWith('blob:')) return fetch(url);
            downloads.push({url: String(url), options});
            events.push(['fetch', String(url)]);
            runOptions.onFetch?.(url, options);
            activeDownloads++;
            maximumDownloads = Math.max(maximumDownloads, activeDownloads);
            try {
                if (runOptions.fetchDelay) await new Promise(resolve => setTimeout(resolve, runOptions.fetchDelay));
                if (typeof runOptions.blockNetwork === 'function' ? runOptions.blockNetwork(url) : runOptions.blockNetwork) {
                    throw new Error('Network blocked');
                }
                const payload = payloads.get(new URL(url).pathname.split('/').at(-1));
                if (runOptions.stall?.file === new URL(url).pathname.split('/').at(-1)) {
                    const aborted = reject => {
                        const fail = () => reject(options.signal.reason || new Error('Aborted'));
                        if (options.signal.aborted) fail();
                        else options.signal.addEventListener('abort', fail, {once:true});
                    };
                    if (runOptions.stall.phase === 'headers') await new Promise((_resolve, reject) => aborted(reject));
                    if (runOptions.stall.phase === 'body') return new Response(new ReadableStream({
                        start: controller => aborted(error => controller.error(error))
                    }));
                }
                if (runOptions.slowStream === new URL(url).pathname.split('/').at(-1)) {
                    const bytes = Buffer.from(payload);
                    let at = 0, ended = false;
                    return new Response(new ReadableStream({
                        async pull(controller) {
                            await new Promise(resolve => setTimeout(resolve, 8));
                            if (ended) return;
                            if (options.signal.aborted) {controller.error(options.signal.reason); ended = true; return;}
                            if (at === bytes.length) {controller.close(); ended = true; return;}
                            controller.enqueue(bytes.subarray(at, ++at));
                        },
                        cancel() {ended = true;}
                    }));
                }
                return new Response(payload ?? '', {status: payload === undefined ? 404 : 200});
            } finally { activeDownloads--; }
        }});
    const originalFetch = context.fetch;
    vm.runInContext(source, context);
    const engine = {config: {update: cfg => calls.push(['libraries', ...cfg.gdextensionLibs])},
        init: async exe => {
            events.push(['init']);
            assert.equal(timers.size, 0, 'no preload poll or deadline timer may survive into engine initialization');
            runOptions.onInit?.({stored, downloads, context});
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
        start: async cfg => {events.push(['start']); calls.push(['start', ...cfg.args]);}};
    let error;
    try {
        await context.RabbitLandsBrowser.start(engine, {executable: 'index', args: ['--verbose']});
        if (runOptions.archives) await new Promise((resolve, reject) =>
            context.RabbitLandsBrowser.fetch_archive(0, (ok, error) => ok ? resolve() : reject(new Error(error))));
        for (const group of runOptions.groupIds || []) await new Promise((resolve, reject) =>
            context.RabbitLandsBrowser.fetch_group_archive(group, 0, (ok, error) => ok ? resolve() : reject(new Error(error))));
    }
    catch (err) { error = err; }
    assert.equal(context.RL_BROWSER_TAKE_BUFFER, undefined);
    assert.equal(context.fetch, originalFetch);
    assert.equal(context.RL_BROWSER_WASM_URL, undefined);
    assert.equal(timers.size, 0, 'preload failure/exit also cleans every poll and deadline');
    return {calls, downloads, error, stats: context.RL_BROWSER_CACHE_STATS, events, progress,
        maximumDownloads, cacheReads, digests, bridge: context.RabbitLandsBrowser};
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

const addMap = (manifest, payloads) => {
    const row = describe('lazy map fixture', 'zip');
    manifest.groups = {'map:a': {archives:[row], dependencies:[], unpacked_bytes:16}};
    payloads.set(row.file, 'lazy map fixture');
};

test('map payloads are lazy and reuse verified disk entries across hosting changes', async () => {
    const idle = await run(addMap);
    assert.equal(idle.error, undefined);
    assert.equal(idle.downloads.length, 3, 'engine startup must not fetch the map');
    const stored = new Map();
    const first = await run(addMap, stored, {groupIds:['map:a']});
    assert.equal(first.error, undefined);
    assert.equal(first.downloads.length, 4);
    const second = await run((manifest, payloads) => {addMap(manifest, payloads); manifest.base_url = 'https://example.com/another-commit/';},
        stored, {groupIds:['map:a'], blockNetwork:true});
    assert.equal(second.error, undefined);
    assert.equal(second.downloads.length, 0);
    assert.equal(second.stats.hits, 4);
});

test('corrupt or unknown lazy groups never reach the runtime filesystem', async () => {
    const corrupted = await run((manifest, payloads) => {addMap(manifest,payloads); payloads.set(manifest.groups['map:a'].archives[0].file,'bad');},
        new Map(), {groupIds:['map:a']});
    assert.match(corrupted.error.message, /incomplete or outdated/);
    assert.equal(corrupted.calls.filter(call => call[2] === '/tmp/rabbitlands-prototype-assets.zip').length, 0);
    const unknown = await run(addMap, new Map(), {groupIds:['map:missing']});
    assert.match(unknown.error.message, /Invalid game archive/);
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

const addRepeatedMaps = (manifest, payloads) => {
    addMap(manifest, payloads);
    manifest.groups['map:b'] = {archives: [{...manifest.groups['map:a'].archives[0]}, {...manifest.archives[0]}],
        dependencies: ['map:a'], unpacked_bytes: 32};
};

test('ALL is the default and saves every unique catalog file before engine initialization', async () => {
    const stored = new Map();
    const result = await run(addRepeatedMaps, stored, {libraries: true, noStorageModule: true, fetchDelay: 5,
        onInit: () => assert.equal(stored.size, 7, 'all lazy files must be saved before engine.init')});
    assert.equal(result.error, undefined);
    assert.equal(result.downloads.length, 7, 'runtime, libraries, parts and repeated art deduplicate by SHA');
    assert.equal(result.stats.preload_mode, 'all');
    assert.equal(result.stats.preload_state, 'complete');
    assert.equal(result.stats.preload_total_files, 7);
    assert.equal(result.stats.preload_completed_files, 7);
    assert.equal(result.stats.preload_completed_bytes, result.stats.preload_total_bytes);
    assert.equal(result.maximumDownloads, 2);
    assert.equal(result.stats.preload_max_active_files, 2);
    assert.equal(result.stats.preload_active_files, 0);
    assert.equal(result.calls.filter(call => call[0] === 'archive').length, 0,
        'preloading must not place lazy archives in MEMFS or unpack all maps');
});

test('ALL reuses only the bounded verified engine payload, without reading or hashing it twice', async () => {
    const stored = new Map();
    await run(addRepeatedMaps, stored, {preloadMode: 'all', libraries: true});
    const warm = await run(addRepeatedMaps, stored, {preloadMode: 'all', libraries: true, blockNetwork: true});
    assert.equal(warm.error, undefined);
    assert.equal(warm.downloads.length, 0);
    assert.equal(warm.cacheReads.length, 7, 'each unique catalog entry is read exactly once before launch');
    assert.equal(warm.digests.length, 7, 'integrity still covers every file, without duplicate engine hashes');
    assert.equal(warm.stats.initial_reused_files, 5);
    const initialBytes = Buffer.byteLength('wasm fixtureengine side fixturecape fixturefirstsecond');
    assert.equal(warm.stats.initial_reused_bytes, initialBytes);
    assert.equal(warm.stats.initial_retained_peak_bytes, initialBytes, 'lazy map/startup ZIP buffers are not retained');
    assert.ok(warm.calls.some(call => call[0] === 'pack' && call[1] === 'firstsecond'));
});

test('repeated identical package parts retain their exact order and share one verification', async () => {
    const result = await run(manifest => {
        manifest.pack.parts[1] = {...manifest.pack.parts[0]};
        manifest.pack.bytes = 10;
    }, new Map(), {preloadMode: 'all'});
    assert.equal(result.error, undefined);
    assert.equal(result.digests.length, 3);
    assert.ok(result.calls.some(call => call[0] === 'pack' && call[1] === 'firstfirst'));
});

test('a verified archive handoff proof is exact, single-use and never persists across sessions', async () => {
    const result = await run(undefined, new Map(), {archives: true});
    const art = describe('art fixture', 'zip');
    assert.equal(result.error, undefined);
    assert.equal(result.bridge.archive_proof_version, 1);
    assert.equal(result.bridge.consume_archive_proof(art.sha256, art.bytes), true);
    assert.equal(result.bridge.consume_archive_proof(art.sha256, art.bytes), false);
    const mismatch = await run(undefined, new Map(), {archives: true});
    assert.equal(mismatch.bridge.consume_archive_proof(art.sha256, art.bytes + 1), false);
    assert.equal(mismatch.bridge.consume_archive_proof(art.sha256, art.bytes), false, 'a rejected proof is also consumed');
    const next = await run();
    assert.equal(next.bridge.consume_archive_proof(art.sha256, art.bytes), false);
});

test('lazy appearance source metadata admits only known groups and safe resource paths', async () => {
    const valid = await run((manifest, payloads) => {
        addMap(manifest, payloads);
        manifest.source_groups = {'res://assets/actors/native/rl_heads/hair/fixture.glb':['map:a']};
    });
    assert.equal(valid.error, undefined);
    for (const path of ['res://assets/actors/native/rl_heads/../private.glb', 'res://other/file.glb']) {
        const bad = await run(manifest => {manifest.source_groups = {[path]:['missing']};});
        assert.match(bad.error.message, /Invalid game source groups/);
        assert.equal(bad.downloads.length, 0);
    }
});

test('ALL rechecks saved files across visits, repairs only corrupt data and downloads only newly listed data', async () => {
    const stored = new Map();
    const first = await run(addRepeatedMaps, stored, {preloadMode: 'all'});
    assert.equal(first.error, undefined);
    assert.equal(stored.size, 5);
    const warm = await run(addRepeatedMaps, stored, {preloadMode: 'all', blockNetwork: true});
    assert.equal(warm.error, undefined);
    assert.equal(warm.downloads.length, 0);
    assert.equal(warm.stats.preload_completed_files, 5);
    const mapHash = describe('lazy map fixture', 'zip').sha256;
    stored.set([...stored.keys()].find(key => key.endsWith(mapHash)), Buffer.from('X'.repeat('lazy map fixture'.length)));
    const repaired = await run(addRepeatedMaps, stored, {preloadMode: 'all'});
    assert.equal(repaired.error, undefined);
    assert.equal(repaired.downloads.length, 1);
    assert.ok(repaired.downloads[0].url.includes(mapHash));
    const updated = await run((manifest, payloads) => {
        addRepeatedMaps(manifest, payloads);
        const row = describe('new map file', 'zip');
        manifest.groups['map:new'] = {archives:[row], dependencies:[], unpacked_bytes:12};
        payloads.set(row.file, 'new map file');
    }, stored, {preloadMode:'all'});
    assert.equal(updated.error, undefined);
    assert.equal(updated.downloads.length, 1);
    assert.equal(updated.stats.preload_completed_files, 6, 'a previous complete catalog never skips new manifest entries');
});

test('all modes reject conflicting size/type metadata and inconsistent package lengths before any payload fetch', async () => {
    const changes = [
        manifest => manifest.archives.push({...manifest.archives[0], bytes: manifest.archives[0].bytes + 1}),
        manifest => manifest.archives.push({...manifest.wasm, file: manifest.wasm.sha256 + '.zip'}),
        manifest => manifest.pack.bytes++,
        manifest => manifest.pack.parts[0].file = manifest.pack.parts[0].sha256 + '.zip'
    ];
    for (const preloadMode of ['all', 'needed']) for (const change of changes) {
        const result = await run(change, new Map(), {preloadMode});
        assert.ok(result.error);
        assert.equal(result.downloads.length, 0);
        assert.deepEqual(result.calls, []);
    }
});

test('ALL fails before gameplay when valid bytes cannot be persisted', async () => {
    for (const unavailable of [{quota:true}, {cacheUnavailable:true}]) {
        const result = await run(addRepeatedMaps, new Map(), {preloadMode:'all', ...unavailable});
        assert.equal(result.error.name, 'AssetStorageError');
        assert.equal(result.stats.preload_state, 'failed');
        assert.equal(result.stats.preload_completed_files, 0);
        assert.equal(result.stats.preload_active_files, 0);
        assert.deepEqual(result.calls, []);
        assert.ok(result.downloads.length <= 2, 'failure stops scheduling after bounded in-flight files');
    }
});

test('a selected folder alone can persist ALL without browser CacheStorage', async () => {
    const folder = new Map();
    const result = await run(addRepeatedMaps, new Map(), {preloadMode:'all', folder, cacheUnavailable:true});
    assert.equal(result.error, undefined);
    assert.equal(folder.size, 5);
    assert.equal(result.stats.preload_completed_files, 5);
    assert.equal(result.stats.preload_state, 'complete');
    assert.equal(result.stats.storage_error, '');
});

test('an interrupted folder cannot certify earlier folder-only files as still available', async () => {
    const folder = new Map([[describe('wasm fixture', 'wasm').sha256, Buffer.from('wasm fixture')]]);
    const options = {preloadMode:'all', folder, fetchDelay:5,
        onFolderRead: async (row, {context}) => {
            if (row.sha256 !== describe('first', 'bin').sha256) return;
            while (!context.RL_BROWSER_CACHE_STATS.preload_completed_files) await new Promise(resolve => setTimeout(resolve, 1));
            options.folderInterrupted = true;
        }};
    const result = await run(addRepeatedMaps, new Map(), options);
    assert.equal(result.error.name, 'AssetStorageError');
    assert.match(result.error.message, /folder became unavailable/);
    assert.equal(result.stats.preload_state, 'failed');
    assert.equal(result.stats.preload_active_files, 0);
    assert.deepEqual(result.calls, []);
});

test('folder-loss recovery rechecks from the beginning against the new persistent target', async () => {
    const folder = new Map([[describe('wasm fixture', 'wasm').sha256, Buffer.from('wasm fixture')]]);
    const stored = new Map();
    let recovered = false;
    const options = {preloadMode:'all', folder, fetchDelay:5,
        onFolderRead: async (row, {context}) => {
            if (recovered || row.sha256 !== describe('first', 'bin').sha256) return;
            while (!context.RL_BROWSER_CACHE_STATS.preload_completed_files) await new Promise(resolve => setTimeout(resolve, 1));
            options.folderInterrupted = true;
        },
        onFailure: (_error, {context, events}) => {
            assert.equal(context.RL_BROWSER_CACHE_STATS.preload_active_files, 0);
            assert.ok(!events.some(event => event[0] === 'init'));
            recovered = true;
            options.folder = undefined;
            options.folderInterrupted = false;
            return 'retry';
        }};
    const result = await run(addRepeatedMaps, stored, options);
    assert.equal(result.error, undefined);
    assert.equal(result.stats.preload_attempts, 2);
    assert.equal(result.stats.preload_failures, 1);
    assert.equal(result.stats.preload_completed_files, 5);
    assert.equal(stored.size, 5, 'earlier inaccessible folder files were copied/downloaded into the replacement cache');
    assert.equal(result.downloads.filter(row => row.url.endsWith(describe('wasm fixture', 'wasm').file)).length, 1);
});

test('explicit quota recovery resets sticky write failure and resumes verified saved files', async () => {
    let quota = true, recovered = false;
    const stored = new Map();
    const result = await run(addRepeatedMaps, stored, {preloadMode:'all', quota:()=>quota,
        onFailure: (_error, {context, events}) => {
            assert.equal(context.RL_BROWSER_CACHE_STATS.preload_active_files, 0);
            assert.ok(!events.some(event => event[0] === 'init'));
            assert.equal(recovered, false);
            quota = false; recovered = true;
            return 'retry';
        }});
    assert.equal(result.error, undefined);
    assert.equal(result.stats.preload_attempts, 2);
    assert.equal(result.stats.preload_failures, 1);
    assert.equal(result.stats.preload_state, 'complete');
    assert.equal(stored.size, 5);
    assert.equal(result.stats.storage_error, '');
});

test('an interrupted download resumes later without fetching its already verified files again', async () => {
    const stored = new Map();
    const first = await run(addRepeatedMaps, stored, {preloadMode:'all',
        blockNetwork:url=>String(url).endsWith(describe('art fixture', 'zip').file)});
    assert.ok(first.error);
    assert.ok(stored.size > 0 && stored.size < 5);
    const savedNames = new Set([...stored.keys()].map(key => key.split('/').at(-1)));
    const resumed = await run(addRepeatedMaps, stored, {preloadMode:'all'});
    assert.equal(resumed.error, undefined);
    assert.ok(resumed.downloads.every(row => !savedNames.has(row.url.split('/').at(-1).split('.')[0])));
    assert.equal(resumed.stats.preload_state, 'complete');
    assert.equal(stored.size, 5);
});

test('explicit on-demand recovery waits for in-flight preload work before engine initialization', async () => {
    const result = await run(addRepeatedMaps, new Map(), {preloadMode:'all', quota:true, fetchDelay:5,
        onFailure: (_error, {context, events}) => {
            assert.equal(context.RL_BROWSER_CACHE_STATS.preload_active_files, 0);
            assert.ok(!events.some(event => event[0] === 'init'));
            return 'needed';
        },
        onInit: ({context}) => assert.equal(context.RL_BROWSER_CACHE_STATS.preload_active_files, 0)});
    assert.equal(result.error, undefined);
    assert.equal(result.stats.preload_mode, 'needed');
    assert.equal(result.stats.preload_state, 'needed');
    assert.ok(result.calls.some(call => call[0] === 'start'));
});

test('a mid-download explicit needed choice drains at most two active files and schedules no more', async () => {
    let cancelled = false, afterCancel = 0;
    const stored = new Map();
    const result = await run(addRepeatedMaps, stored, {preloadMode:'all', fetchDelay:5,
        onSaved: () => {if (stored.size >= 2) cancelled = true;},
        cancelled: () => cancelled,
        onProgress: state => {if (cancelled && state.state !== 'needed') afterCancel++;},
        onInit: ({context, downloads}) => {
            assert.equal(context.RL_BROWSER_CACHE_STATS.preload_active_files, 0);
            assert.ok(downloads.length <= 3, 'only the other already-active file can finish after cancellation');
        }});
    assert.equal(result.error, undefined);
    assert.equal(result.stats.preload_mode, 'needed');
    assert.equal(result.stats.preload_state, 'needed');
    assert.ok(result.stats.preload_completed_files < result.stats.preload_total_files);
    assert.ok(afterCancel > 0);
    const init = result.events.findIndex(event => event[0] === 'init');
    assert.ok(result.events.slice(init).every(event => event[0] !== 'fetch'), 'no canceled preload downloads run during gameplay');
});

test('preload inactivity deadlines bound stalled headers and body reads without entering gameplay', async () => {
    for (const phase of ['headers', 'body']) {
        const result = await run(addRepeatedMaps, new Map(), {preloadMode:'all', fastTimeout:true,
            stall: {file:describe('wasm fixture', 'wasm').file, phase}});
        assert.equal(result.error.name, 'AssetDownloadTimeoutError');
        assert.equal(result.stats.preload_state, 'failed');
        assert.equal(result.stats.preload_active_files, 0);
        assert.deepEqual(result.calls, []);
    }
});

test('slow but active body progress renews the preload deadline instead of imposing a transfer limit', async () => {
    const result = await run(undefined, new Map(), {preloadMode:'all', fastTimeout:40,
        slowStream:describe('wasm fixture', 'wasm').file});
    assert.equal(result.error, undefined);
    assert.equal(result.stats.preload_state, 'complete');
    assert.equal(result.stats.preload_completed_files, 4);
});

test('explicit needed cancels a stalled lazy read promptly and leaves no prefetch timers during gameplay', async () => {
    let cancelled = false;
    const lazy = describe('lazy map fixture', 'zip').file;
    const result = await run(addRepeatedMaps, new Map(), {preloadMode:'all',
        stall: {file:lazy, phase:'body'}, cancelled:()=>cancelled,
        onFetch:url=>{if (String(url).endsWith(lazy)) cancelled = true;}});
    assert.equal(result.error, undefined);
    assert.equal(result.stats.preload_mode, 'needed');
    assert.equal(result.stats.preload_state, 'needed');
    assert.equal(result.stats.preload_active_files, 0);
    assert.ok(result.stats.preload_completed_files < result.stats.preload_total_files);
    assert.ok(result.calls.some(call => call[0] === 'start'));
});

test('preload streamed reads reject oversized and incomplete responses within the manifest allocation', async () => {
    for (const bytes of ['x', 'x'.repeat(1024 * 1024)]) {
        const result = await run((manifest, payloads)=>payloads.set(manifest.wasm.file, bytes), new Map(), {preloadMode:'all'});
        assert.match(result.error.message, /incomplete or outdated/);
        assert.equal(result.stats.preload_state, 'failed');
        assert.deepEqual(result.calls, []);
    }
});
