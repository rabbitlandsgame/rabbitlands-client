/* Verified, content-addressed game files stay in this site's local browser storage. */
'use strict';
globalThis.RabbitLandsBrowser = (() => {
    const LIMIT = 64 * 1024 * 1024;
    const CACHE = 'rabbitlands-browser-assets-v1';
    let runtime, manifest, base, cache;
    let canWrite = true;
    const stats = {hits: 0, hit_bytes: 0, network_files: 0, download_bytes: 0,
        saved_files: 0, storage_error: '', persistent: false};
    globalThis.RL_BROWSER_CACHE_STATS = stats;

    function validate(row) {
        if (!row || !/^[a-f0-9]{64}$/.test(row.sha256) ||
                !['bin', 'wasm', 'zip'].some(ext => row.file === `${row.sha256}.${ext}`) ||
                !Number.isSafeInteger(row.bytes) || row.bytes <= 0 || row.bytes > LIMIT) {
            throw new Error('Invalid game download entry.');
        }
    }
    async function matches(bytes, row) {
        if (bytes.byteLength !== row.bytes) return false;
        const digest = await crypto.subtle.digest('SHA-256', bytes);
        return Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('') === row.sha256;
    }
    const key = row => new URL(`__rabbitlands_assets__/${row.sha256}`, location.origin || location.href).href;
    function storageError(error) {
        stats.storage_error = String(error?.name || error || 'Browser storage unavailable');
        console.warn('rabbitlands_asset_storage', stats.storage_error);
    }
    async function verified(row) {
        validate(row);
        if (cache) {
            try {
                const saved = await cache.match(key(row));
                if (saved) {
                    const bytes = await saved.arrayBuffer();
                    if (await matches(bytes, row)) {
                        stats.hits++;
                        stats.hit_bytes += bytes.byteLength;
                        return bytes;
                    }
                    await cache.delete(key(row));
                }
            } catch (error) { storageError(error); }
        }
        const response = await fetch(new URL(row.file, base), {mode: 'cors', credentials: 'omit'});
        if (!response.ok) throw new Error(`Game download failed (${response.status}).`);
        const bytes = await response.arrayBuffer();
        if (!await matches(bytes, row)) throw new Error('Game download is incomplete or outdated.');
        stats.network_files++;
        stats.download_bytes += bytes.byteLength;
        if (cache && canWrite) {
            try {
                // Store decoded bytes, without the remote response's compression
                // headers. Integrity is checked again before each local reuse.
                await cache.put(key(row), new Response(bytes, {headers: {'Content-Type': 'application/octet-stream'}}));
                stats.saved_files++;
            } catch (error) { canWrite = false; storageError(error); }
        }
        return bytes;
    }
    function takeFile(path, buffer) {
        // Our export hook allows MEMFS to adopt these immutable buffers. Other
        // engine callers retain the standard copy semantics.
        globalThis.RL_BROWSER_TAKE_BUFFER = true;
        try { runtime.copyToFS(path, buffer); }
        finally { delete globalThis.RL_BROWSER_TAKE_BUFFER; }
    }
    async function fetch_archive(index, callback) {
        try {
            if (!runtime || !Number.isSafeInteger(index) || index < 0 || index >= manifest.archives.length) {
                throw new Error('Invalid game archive request.');
            }
            const bytes = await verified(manifest.archives[index]);
            takeFile('/tmp/rabbitlands-prototype-assets.zip', bytes);
            callback(true, '');
        } catch (error) { callback(false, error.message); }
    }
    async function start(engine, config, callbacks = {}) {
        const response = await fetch('browser-assets.json', {cache: 'no-cache'});
        if (!response.ok) throw new Error('Cannot load the browser asset manifest.');
        manifest = await response.json();
        base = new URL(manifest.base_url, location.href);
        const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname);
        if ((base.protocol !== 'https:' && !(base.protocol === 'http:' && loopback)) || base.username || base.password) {
            throw new Error('Game assets require HTTPS or a local test server.');
        }
        if (manifest.schema !== 1 || !Array.isArray(manifest.pack?.parts) || !Array.isArray(manifest.archives) ||
                !Number.isSafeInteger(manifest.pack.bytes) || manifest.pack.bytes <= 0 || manifest.pack.bytes > 512 * 1024 * 1024) {
            throw new Error('Invalid browser asset manifest.');
        }
        [manifest.wasm, ...manifest.pack.parts, ...manifest.archives].forEach(validate);
        try {
            if (typeof caches === 'undefined') throw new Error('Browser storage unavailable');
            cache = await caches.open(CACHE);
        } catch (error) { storageError(error); }
        if (globalThis.navigator?.storage?.persist) {
            // Eviction protection is separate from saving files. A denial
            // still permits ordinary persistent-across-visits Cache storage.
            try { stats.persistent = await navigator.storage.persist(); }
            catch (_) { stats.persistent = false; }
        }
        let completed = 0;
        const total = manifest.pack.bytes + manifest.wasm.bytes;
        async function load(row) {
            const bytes = await verified(row);
            completed += bytes.byteLength;
            callbacks.onProgress?.(completed, total);
            return bytes;
        }
        const wasmURL = URL.createObjectURL(new Blob([await load(manifest.wasm)], {type: 'application/wasm'}));
        globalThis.RL_BROWSER_WASM_URL = wasmURL;
        globalThis.RL_BROWSER_ASSETS = {...manifest, base_url: base.href};
        try { await engine.init(config.executable); }
        finally {
            URL.revokeObjectURL(wasmURL);
            delete globalThis.RL_BROWSER_WASM_URL;
        }
        runtime = engine;
        let pack = new Uint8Array(manifest.pack.bytes);
        let offset = 0;
        for (const row of manifest.pack.parts) {
            const bytes = await load(row);
            if (offset + bytes.byteLength > pack.byteLength) throw new Error('Invalid game package length.');
            pack.set(new Uint8Array(bytes), offset);
            offset += bytes.byteLength;
        }
        if (offset !== pack.byteLength) throw new Error('Incomplete game package.');
        takeFile('index.pck', pack.buffer);
        pack = null;
        await engine.start({args: ['--main-pack', 'index.pck', ...config.args]});
    }
    return {start, fetch_archive, stats};
})();
