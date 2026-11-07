/* Verified, content-addressed game files stay in this site's local browser storage. */
'use strict';
globalThis.RabbitLandsBrowser = (() => {
    const LIMIT = 64 * 1024 * 1024;
    const CACHE = 'rabbitlands-browser-assets-v1';
    let runtime, manifest, base, cache;
    let canWrite = true, cacheFailure = '';
    const stats = {hits: 0, hit_bytes: 0, network_files: 0, download_bytes: 0,
        saved_files: 0, storage_error: '', persistent: false,
        preload_mode: 'all', preload_state: 'idle', preload_total_files: 0, preload_total_bytes: 0,
        preload_completed_files: 0, preload_completed_bytes: 0, preload_attempts: 0,
        preload_failures: 0, preload_error: '', preload_active_files: 0, preload_max_active_files: 0};
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
        cacheFailure = stats.storage_error = String(error?.name || error || 'Browser storage unavailable');
        console.warn('rabbitlands_asset_storage', stats.storage_error);
    }
    async function download(row, reads) {
        let controller, deadline, reader, timedOut = false;
        const touch = () => {
            clearTimeout(deadline);
            deadline = setTimeout(() => {timedOut = true; controller.abort();}, 45000);
        };
        if (reads) {
            controller = new AbortController();
            reads.add(controller);
            touch();
        }
        try {
            const response = await fetch(new URL(row.file, base), {mode: 'cors', credentials: 'omit',
                ...(controller ? {signal: controller.signal} : {})});
            if (!response.ok) throw new Error(`Game download failed (${response.status}).`);
            if (!reads) return await response.arrayBuffer();
            if (!response.body) throw new Error('Game download is incomplete or outdated.');
            // Bound each in-flight download to its manifest size; activity,
            // rather than total transfer time, renews the network timeout.
            const bytes = new Uint8Array(row.bytes);
            let offset = 0;
            reader = response.body.getReader();
            for (;;) {
                touch();
                const chunk = await reader.read();
                if (chunk.done) break;
                if (offset + chunk.value.byteLength > bytes.byteLength) throw new Error('Game download is incomplete or outdated.');
                bytes.set(chunk.value, offset);
                offset += chunk.value.byteLength;
            }
            if (offset !== bytes.byteLength) throw new Error('Game download is incomplete or outdated.');
            return bytes.buffer;
        } catch (error) {
            controller?.abort();
            if (!timedOut) throw error;
            const timeout = new Error('A game file download timed out. Check your connection and retry.');
            timeout.name = 'AssetDownloadTimeoutError';
            throw timeout;
        } finally {
            if (reader) {
                try {reader.cancel().catch(() => {}); reader.releaseLock();} catch (_) { /* Already closed/aborted. */ }
            }
            if (controller) {clearTimeout(deadline); reads.delete(controller);}
        }
    }
    async function verified(row, requireSaved = false, beforeDownload, reads) {
        validate(row);
        const folder = globalThis.RabbitLandsAssetStorage;
        if (folder) {
            const bytes = await folder.read(row);
            if (bytes && await matches(bytes, row)) {
                folder.hit(row);
                stats.hits++;
                stats.hit_bytes += bytes.byteLength;
                return bytes;
            }
            if (bytes) folder.corrupt();
        }
        if (cache) {
            try {
                const saved = await cache.match(key(row));
                if (saved) {
                    const bytes = await saved.arrayBuffer();
                    if (await matches(bytes, row)) {
                        stats.hits++;
                        stats.hit_bytes += bytes.byteLength;
                        if (await folder?.write(row, bytes)) stats.saved_files++;
                        return bytes;
                    }
                    await cache.delete(key(row));
                }
            } catch (error) { storageError(error); }
        }
        beforeDownload?.();
        const bytes = await download(row, reads);
        if (!await matches(bytes, row)) throw new Error('Game download is incomplete or outdated.');
        stats.network_files++;
        stats.download_bytes += bytes.byteLength;
        const folderSaved = await folder?.write(row, bytes);
        let persisted = Boolean(folderSaved);
        if (folderSaved) stats.saved_files++;
        else if (cacheFailure) stats.storage_error = cacheFailure;
        if (!folderSaved && cache && canWrite) {
            try {
                // Store decoded bytes, without the remote response's compression
                // headers. Integrity is checked again before each local reuse.
                await cache.put(key(row), new Response(bytes, {headers: {'Content-Type': 'application/octet-stream'}}));
                stats.saved_files++;
                persisted = true;
            } catch (error) { canWrite = false; storageError(error); }
        }
        if (requireSaved && !persisted) {
            const error = new Error('Game files could not be saved on this device. Check free space or reconnect your asset folder.');
            error.name = 'AssetStorageError';
            throw error;
        }
        return bytes;
    }
    function catalog(libraries) {
        const unique = new Map();
        let totalBytes = 0;
        function add(row, extension) {
            validate(row);
            if (row.file !== `${row.sha256}.${extension}`) throw new Error('Invalid game payload type.');
            const previous = unique.get(row.sha256);
            if (previous && (previous.file !== row.file || previous.bytes !== row.bytes)) {
                throw new Error('Conflicting game download entries.');
            }
            if (!previous) {
                unique.set(row.sha256, row);
                totalBytes += row.bytes;
                if (!Number.isSafeInteger(totalBytes)) throw new Error('Invalid total game download size.');
            }
        }
        add(manifest.wasm, 'wasm');
        libraries.forEach(row => add(row, 'wasm'));
        let packageBytes = 0;
        manifest.pack.parts.forEach(row => { add(row, 'bin'); packageBytes += row.bytes; });
        if (packageBytes !== manifest.pack.bytes) throw new Error('Invalid game package length.');
        manifest.archives.forEach(row => add(row, 'zip'));
        for (const group of Object.values(manifest.groups || {})) group.archives.forEach(row => add(row, 'zip'));
        return {rows: [...unique.values()], total: unique.size, total_bytes: totalBytes, default_mode: 'all'};
    }
    async function openCache() {
        try {
            if (typeof caches === 'undefined') throw new Error('Browser storage unavailable');
            cache = await caches.open(CACHE);
        } catch (error) { cache = undefined; storageError(error); }
    }
    async function preloadAll(summary, callbacks) {
        const storage = globalThis.RabbitLandsAssetStorage;
        const mode = await storage?.preload_choice?.({total: summary.total, total_bytes: summary.total_bytes, default_mode: 'all'});
        stats.preload_mode = mode === 'needed' ? 'needed' : 'all';
        stats.preload_total_files = summary.total;
        stats.preload_total_bytes = summary.total_bytes;
        function report(state, error = '') {
            stats.preload_state = state;
            stats.preload_error = error;
            storage?.preload_progress?.({completed: stats.preload_completed_files, total: summary.total,
                completed_bytes: stats.preload_completed_bytes, total_bytes: summary.total_bytes, state, error});
        }
        if (stats.preload_mode === 'needed') { report('needed'); return; }
        for (;;) {
            stats.preload_attempts++;
            stats.preload_completed_files = 0;
            stats.preload_completed_bytes = 0;
            let next = 0, failure, cancelled = false, phase = 'checking';
            const reads = new Set();
            const abortReads = () => {for (const controller of reads) controller.abort();};
            const selectedFolder = storage?.status?.().mode === 'folder';
            function checkLocation() {
                if (selectedFolder && storage?.status?.().mode !== 'folder') {
                    const error = new Error('Your asset folder became unavailable. Reconnect it or choose browser storage, then retry.');
                    error.name = 'AssetStorageError';
                    throw error;
                }
            }
            const stop = () => {
                cancelled = cancelled || Boolean(storage?.preload_cancelled?.());
                try { checkLocation(); } catch (error) { failure ||= error; }
                if (cancelled || failure) abortReads();
                return cancelled || Boolean(failure);
            };
            report(phase);
            async function worker() {
                while (!stop() && next < summary.rows.length) {
                    const row = summary.rows[next++];
                    stats.preload_active_files++;
                    stats.preload_max_active_files = Math.max(stats.preload_max_active_files, stats.preload_active_files);
                    try {
                        // No array of payload bytes survives this await. Only two
                        // files can be read, verified and saved at any one time.
                        await verified(row, true, () => { phase = 'downloading'; report(phase); }, reads);
                        checkLocation();
                        stats.preload_completed_files++;
                        stats.preload_completed_bytes += row.bytes;
                        callbacks.onProgress?.(stats.preload_completed_bytes, summary.total_bytes);
                        report(phase);
                    } catch (error) { failure ||= error; abortReads(); }
                    finally { stats.preload_active_files--; }
                }
            }
            // Always settle both current saves before changing location, retrying
            // or starting the engine. No prefetch runs alongside gameplay.
            const cancellation = setInterval(stop, 100);
            try { await Promise.all([worker(), worker()]); }
            finally { clearInterval(cancellation); }
            stop();
            if (cancelled) {
                stats.preload_mode = 'needed';
                report('needed');
                return;
            }
            if (!failure) { report('complete'); return; }
            stats.preload_failures++;
            report('failed', failure.message);
            const choice = await storage?.preload_failure?.({name: failure.name, message: failure.message,
                completed: stats.preload_completed_files, total: summary.total,
                completed_bytes: stats.preload_completed_bytes, total_bytes: summary.total_bytes});
            if (choice === 'needed') {
                stats.preload_mode = 'needed';
                report('needed');
                return;
            }
            if (choice !== 'retry') throw failure;
            canWrite = true;
            cacheFailure = stats.storage_error = '';
            await openCache();
            if (storage?.status?.().mode === 'folder') stats.storage_error = '';
            // Recheck the current storage after recovery; never trust a saved
            // whole-catalog completion flag or assume the old folder is present.
        }
    }
    function takeFile(path, buffer) {
        // Our export hook allows MEMFS to adopt these immutable buffers. Other
        // engine callers retain the standard copy semantics.
        globalThis.RL_BROWSER_TAKE_BUFFER = true;
        try { runtime.copyToFS(path, buffer); }
        finally { delete globalThis.RL_BROWSER_TAKE_BUFFER; }
    }
    async function archive(rows, index, callback) {
        try {
            if (!runtime || !Array.isArray(rows) || !Number.isSafeInteger(index) || index < 0 || index >= rows.length) {
                throw new Error('Invalid game archive request.');
            }
            const bytes = await verified(rows[index]);
            takeFile('/tmp/rabbitlands-prototype-assets.zip', bytes);
            callback(true, '');
        } catch (error) { callback(false, error.message); }
    }
    async function fetch_archive(index, callback) { return archive(manifest.archives, index, callback); }
    async function fetch_group_archive(group, index, callback) {
        return archive(Object.hasOwn(manifest.groups || {}, group) ? manifest.groups[group].archives : null, index, callback);
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
        if (manifest.groups !== undefined) {
            if (!manifest.groups || typeof manifest.groups !== 'object' || Array.isArray(manifest.groups) ||
                    Object.keys(manifest.groups).length > 16384) throw new Error('Invalid game asset groups.');
            for (const [name, group] of Object.entries(manifest.groups)) {
                if (!/^[a-zA-Z0-9_.:-]{1,160}$/.test(name) || !Array.isArray(group.archives) ||
                        !Array.isArray(group.dependencies) || !Number.isSafeInteger(group.unpacked_bytes) || group.unpacked_bytes < 0 ||
                        group.dependencies.some(dep => !Object.hasOwn(manifest.groups, dep))) throw new Error('Invalid game asset group.');
                group.archives.forEach(validate);
            }
        }
        const libraries = manifest.libraries || [];
        if (!Array.isArray(libraries) || libraries.length > 16) throw new Error('Invalid browser libraries.');
        const names = new Set();
        for (const library of libraries) {
            validate(library);
            if (!/^[a-zA-Z0-9_.-]+\.wasm$/.test(library.name) || library.file !== `${library.sha256}.wasm` || names.has(library.name) ||
                    typeof library.extension !== 'boolean') throw new Error('Invalid browser library name.');
            names.add(library.name);
        }
        const downloads = catalog(libraries);
        await openCache();
        await globalThis.RabbitLandsAssetStorage?.prepare(manifest, cache);
        if (globalThis.RabbitLandsAssetStorage?.status().mode === 'folder') stats.storage_error = '';
        if (globalThis.navigator?.storage?.persist) {
            // Eviction protection is separate from saving files. A denial
            // still permits ordinary persistent-across-visits Cache storage.
            try { stats.persistent = await navigator.storage.persist(); }
            catch (_) { stats.persistent = false; }
        }
        await preloadAll(downloads, callbacks);
        let completed = 0;
        const total = manifest.pack.bytes + manifest.wasm.bytes + libraries.reduce((n, row) => n + row.bytes, 0);
        async function load(row) {
            const bytes = await verified(row);
            completed += bytes.byteLength;
            callbacks.onProgress?.(completed, total);
            return bytes;
        }
        const wasmURL = URL.createObjectURL(new Blob([await load(manifest.wasm)], {type: 'application/wasm'}));
        globalThis.RL_BROWSER_WASM_URL = wasmURL;
        globalThis.RL_BROWSER_ASSETS = {...manifest, base_url: base.href};
        const libraryURLs = new Map();
        const originalFetch = globalThis.fetch;
        try {
            for (const library of libraries) {
                const url = new URL(library.name, location.href).href;
                libraryURLs.set(url, URL.createObjectURL(new Blob([await load(library)], {type: 'application/wasm'})));
            }
            if (libraries.length) {
                // Preserve the engine's library names for dlopen, while its
                // initial dynamic linker fetches only already verified bytes.
                engine.config.update({gdextensionLibs: libraries.filter(row => row.extension).map(row => row.name)});
                globalThis.fetch = (input, options) => {
                    const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.href).href;
                    return originalFetch(libraryURLs.get(url) || input, options);
                };
            }
            await engine.init(config.executable);
        }
        finally {
            globalThis.fetch = originalFetch;
            for (const url of libraryURLs.values()) URL.revokeObjectURL(url);
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
    return {start, fetch_archive, fetch_group_archive, stats};
})();
