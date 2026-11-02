/* Player-selected asset storage. Directory permissions stay in this browser. */
'use strict';

globalThis.RabbitLandsAssetStorage = (() => {
    const DB = 'rabbitlands-asset-locations-v1';
    const STORE = 'settings';
    const FOLDER = 'RabbitLandsAssets';
    const ID = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;
    const LIMIT = 64 * 1024 * 1024;
    let database, directory, selected, pending, cache, prepared = false;
    let remembered = false, folderError = '', busy = false, waiting;
    let panel, startup = false;
    const rows = new Map();
    const statistics = {folder_hits: 0, folder_bytes: 0, folder_saves: 0,
        folder_saved_bytes: 0, folder_corrupt: 0, folder_error: ''};

    const framed = () => globalThis.window && window.self !== window.top;
    const supported = () => typeof globalThis.showDirectoryPicker === 'function' &&
        globalThis.isSecureContext !== false && !framed();
    function valid(row) {
        if (!row || !/^[a-f0-9]{64}$/.test(row.sha256) ||
                !['zip', 'wasm', 'bin'].some(ext => row.file === `${row.sha256}.${ext}`) ||
                !Number.isSafeInteger(row.bytes) || row.bytes <= 0 || row.bytes > LIMIT) {
            throw new Error('Invalid saved game file.');
        }
    }
    async function matches(bytes, row) {
        if (bytes.byteLength !== row.bytes) return false;
        const hash = await crypto.subtle.digest('SHA-256', bytes);
        return Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2, '0')).join('') === row.sha256;
    }
    function errorName(error) {
        return /^[A-Za-z]+Error$/.test(error?.name || '') ? error.name : 'StorageError';
    }
    function interrupted(error) {
        statistics.folder_error = errorName(error);
        folderError = 'Folder access was interrupted. Files will use browser storage until you reconnect the folder.';
        directory = undefined;
        render();
    }
    async function db() {
        if (!database) database = new Promise((resolve, reject) => {
            if (!globalThis.indexedDB) { reject(new Error('Storage unavailable')); return; }
            const request = indexedDB.open(DB, 1);
            request.onupgradeneeded = () => request.result.createObjectStore(STORE);
            request.onerror = () => reject(request.error);
            request.onblocked = () => reject(new Error('Storage busy'));
            request.onsuccess = () => resolve(request.result);
        });
        return database;
    }
    async function setting(key, value) {
        const connection = await db();
        return new Promise((resolve, reject) => {
            const tx = connection.transaction(STORE, value === undefined ? 'readonly' : 'readwrite');
            const store = tx.objectStore(STORE);
            const request = value === undefined ? store.get(key) : store.put(value, key);
            tx.oncomplete = () => resolve(request.result);
            tx.onerror = () => reject(tx.error);
            tx.onabort = () => reject(tx.error || new Error('Storage unavailable'));
        });
    }
    function requestedProfile() {
        const value = new URLSearchParams(location.hash?.slice(1) || '').get('rl-assets');
        return value === 'browser' || ID.test(value || '') ? value : null;
    }
    function updateAddress(id) {
        if (!globalThis.history?.replaceState) return;
        const url = new URL(location.href);
        const fragment = new URLSearchParams(url.hash.slice(1));
        fragment.set('rl-assets', id);
        url.hash = fragment.toString();
        history.replaceState(null, '', url.href);
    }
    async function use_browser() {
        directory = undefined;
        selected = undefined;
        pending = undefined;
        folderError = '';
        try { await setting('active', {mode: 'browser'}); } catch (_) { /* Optional preference. */ }
        remembered = false;
        updateAddress('browser');
        render();
    }
    async function activate(profile) {
        const folder = await profile.handle.getDirectoryHandle(FOLDER, {create: true});
        directory = folder;
        selected = profile;
        pending = undefined;
        folderError = '';
    }
    async function choose_folder() {
        // Invoke the native picker before awaiting anything: this is a direct
        // HTML click handler, never a deferred Godot frame callback.
        if (!supported()) return false;
        let handle;
        try { handle = await showDirectoryPicker({id: 'rabbitlands-assets', mode: 'readwrite'}); }
        catch (error) {
            if (error.name !== 'AbortError') folderError = 'This folder could not be selected. Try another location or use browser storage.';
            render();
            return false;
        }
        const previous = selected || pending;
        try {
            const same = previous && await handle.isSameEntry(previous.handle);
            const profile = {id: same ? previous.id : crypto.randomUUID(), handle};
            await activate(profile);
            remembered = false;
            try {
                await setting('folder:' + profile.id, profile);
                await setting('active', {mode: 'folder', id: profile.id});
                remembered = true;
                updateAddress(profile.id);
            } catch (_) {
                folderError = 'The folder works for this visit, but this browser could not remember it. Choose it again next time.';
            }
            render();
            // An unavailable browser cache must not invalidate a usable folder.
            // Files missed here will still be saved as the game requests them.
            try { await copy_saved_downloads(); }
            catch (_) {
                folderError = 'Your folder is ready. Some existing browser downloads could not be copied; they will be saved as you play.';
                render();
            }
            return true;
        } catch (error) {
            folderError = 'Game files could not be saved in that folder. Try another location or use browser storage.';
            statistics.folder_error = errorName(error);
            render();
            return false;
        }
    }
    async function continue_saved() {
        if (!pending) return false;
        const profile = pending;
        try {
            // requestPermission must be called directly by this button.
            if (await profile.handle.requestPermission({mode: 'readwrite'}) !== 'granted') {
                folderError = 'Folder access was not granted. Choose a folder or use browser storage.';
                render();
                return false;
            }
            await activate(profile);
            remembered = true;
            render();
            return true;
        } catch (_) {
            folderError = 'The saved folder is unavailable. Choose its current location or use browser storage.';
            render();
            return false;
        }
    }
    async function read(row) {
        valid(row);
        const target = directory;
        if (!target) return null;
        try {
            const handle = await target.getFileHandle(row.file);
            const file = await handle.getFile();
            // Reject a replaced/oversized file before allocating its bytes.
            if (file.size !== row.bytes) { statistics.folder_corrupt++; return null; }
            return await file.arrayBuffer();
        } catch (error) {
            if (error.name !== 'NotFoundError') interrupted(error);
            return null;
        }
    }
    async function write(row, bytes) {
        valid(row);
        const target = directory;
        if (!target || bytes.byteLength !== row.bytes) return false;
        let stream;
        try {
            const handle = await target.getFileHandle(row.file, {create: true});
            stream = await handle.createWritable();
            // Caller supplies bytes already checked against this manifest row.
            // close() atomically publishes them; incomplete writes are not used.
            await stream.write(bytes);
            await stream.close();
            statistics.folder_saves++;
            statistics.folder_saved_bytes += bytes.byteLength;
            return true;
        } catch (error) {
            try { await stream?.abort(); } catch (_) { /* Preserve the old file. */ }
            interrupted(error);
            return false;
        }
    }
    function hit(row) { statistics.folder_hits++; statistics.folder_bytes += row.bytes; }
    function corrupt() { statistics.folder_corrupt++; }
    async function copy_saved_downloads() {
        if (!cache?.keys || !directory) return;
        const keys = await cache.keys();
        const available = keys.map(request => {
            const url = new URL(request.url || request);
            return rows.get(url.pathname.match(/\/__rabbitlands_assets__\/([a-f0-9]{64})$/)?.[1]);
        }).filter(Boolean);
        const unique = [...new Map(available.map(row => [row.sha256, row])).values()];
        let count = 0;
        for (const row of unique) {
            if (!directory) break;
            notice(`Saving existing downloads to your folder… ${++count} of ${unique.length}`);
            const existing = await read(row);
            if (existing && await matches(existing, row)) continue;
            const response = await cache.match(new URL(`__rabbitlands_assets__/${row.sha256}`, location.origin).href);
            if (!response) continue;
            const bytes = await response.arrayBuffer();
            if (await matches(bytes, row)) await write(row, bytes);
        }
        render();
    }
    async function prepare(manifest, browserCache) {
        if (prepared) return;
        prepared = true;
        cache = browserCache;
        for (const row of [manifest.wasm, ...(manifest.libraries || []), ...(manifest.pack?.parts || []),
                ...(manifest.archives || []), ...Object.values(manifest.groups || {}).flatMap(group => group.archives)]) {
            if (row) { valid(row); rows.set(row.sha256, row); }
        }
        let active;
        const requested = requestedProfile();
        try { active = requested ? {mode: requested === 'browser' ? 'browser' : 'folder', id: requested} : await setting('active'); }
        catch (_) { /* File access and browser caching still work without IDB. */ }
        if (active?.mode === 'folder') {
            try {
                pending = await setting('folder:' + active.id);
                if (pending && supported() && await pending.handle.queryPermission({mode: 'readwrite'}) === 'granted') {
                    await activate(pending);
                    remembered = true;
                    return;
                }
                folderError = pending ? 'Continue to allow access to your saved game folder.' :
                    'This shortcut’s folder is not saved in this browser. Choose the folder again; existing game files will be reused.';
            } catch (_) { folderError = 'Choose your game folder again or use browser storage.'; }
        } else if (active?.mode === 'browser') {
            return;
        }
        if (globalThis.document) await show_settings(true);
    }
    function status() {
        return {mode: directory ? 'folder' : 'browser', remembered,
            needs_permission: Boolean(pending), supported: supported(), ...statistics};
    }
    function shortcut() {
        if (framed()) throw new Error('Open the standalone game to save a shortcut.');
        const url = new URL(location.href);
        if (url.username || url.password || !(url.protocol === 'https:' || url.protocol === 'http:' &&
                ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) throw new Error('Use a secure game address.');
        if (selected && !remembered) throw new Error('This browser could not remember the folder.');
        url.search = '';
        url.hash = 'rl-assets=' + (selected ? selected.id : 'browser');
        return {filename: 'Rabbit Lands.url', type: 'application/internet-shortcut',
            text: `[InternetShortcut]\r\nURL=${url.href}\r\n`, url: url.href};
    }
    function download_shortcut() {
        const data = shortcut();
        // Chromium renames direct .url downloads to .download. Package the
        // shortcut in a standard ZIP so it keeps its usable Windows filename.
        const name = new TextEncoder().encode(data.filename);
        const body = new TextEncoder().encode(data.text);
        let crc = 0xffffffff;
        for (const byte of body) {
            crc ^= byte;
            for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
        }
        crc = (crc ^ 0xffffffff) >>> 0;
        const localSize = 30 + name.length + body.length;
        const centralSize = 46 + name.length;
        const zip = new Uint8Array(localSize + centralSize + 22);
        const view = new DataView(zip.buffer);
        const u16 = (at, value) => view.setUint16(at, value, true);
        const u32 = (at, value) => view.setUint32(at, value, true);
        u32(0, 0x04034b50); u16(4, 20); u16(12, 33);
        u32(14, crc); u32(18, body.length); u32(22, body.length); u16(26, name.length);
        zip.set(name, 30); zip.set(body, 30 + name.length);
        const at = localSize;
        u32(at, 0x02014b50); u16(at + 4, 20); u16(at + 6, 20); u16(at + 14, 33);
        u32(at + 16, crc); u32(at + 20, body.length); u32(at + 24, body.length); u16(at + 28, name.length);
        zip.set(name, at + 46);
        const end = at + centralSize;
        u32(end, 0x06054b50); u16(end + 8, 1); u16(end + 10, 1);
        u32(end + 12, centralSize); u32(end + 16, localSize);
        const url = URL.createObjectURL(new Blob([zip], {type: 'application/zip'}));
        const link = document.createElement('a');
        link.href = url;
        link.download = 'Rabbit Lands shortcut.zip';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    const control = name => panel?.querySelector('[data-rl="' + name + '"]');
    function notice(text) { if (control('status')) control('status').textContent = text; }
    function render() {
        if (!panel) return;
        control('location').textContent = directory ? `${selected.handle.name} / ${FOLDER}` : 'Browser storage (automatic)';
        notice(folderError || (directory ? 'Your game files are saved in this folder. Only files you use are downloaded.' :
            'Game files are saved on this device by your browser.'));
        control('folder').disabled = busy || !supported();
        control('browser').disabled = busy;
        control('resume').hidden = !pending || !supported();
        control('resume').disabled = busy;
        control('shortcut').disabled = busy || framed() || Boolean(selected && !remembered) || Boolean(pending);
        control('continue').disabled = busy || Boolean(pending);
        control('continue').textContent = startup ? 'Continue to login' : 'Done';
        control('support').hidden = supported();
        control('support').textContent = framed() ?
            'Folder selection needs the game in its own browser tab. You can still use browser storage here.' :
            'Folder selection needs a supported desktop browser, such as Chrome or Edge. Browser storage remains available.';
        control('standalone').hidden = !framed();
    }
    async function action(callback) {
        if (busy) return;
        busy = true;
        render();
        try { await callback(); }
        catch (_) { folderError = 'That storage option is unavailable. Try again or use browser storage.'; }
        finally { busy = false; render(); }
    }
    function makePanel() {
        panel = document.createElement('dialog');
        panel.className = 'rl-storage';
        panel.setAttribute('aria-labelledby', 'rl-storage-title');
        panel.innerHTML = `<h1 id="rl-storage-title">Rabbit Lands</h1>
<h2>Game files</h2><p>Choose where to keep your downloaded game files.</p>
<div class="rl-storage-location" data-rl="location"></div>
<div class="rl-storage-actions"><button data-rl="folder">Choose asset folder</button>
<button data-rl="resume" hidden>Use saved folder</button>
<button data-rl="browser">Use browser storage</button></div>
<p data-rl="status" role="status" aria-live="polite"></p>
<p class="rl-storage-muted" data-rl="support" hidden></p>
<a data-rl="standalone" href="https://play.rabbitlandsgame.com/" target="_blank" rel="noopener" hidden>Open standalone game</a>
<p class="rl-storage-muted">A game-owned RabbitLandsAssets folder is created inside your chosen location.</p>
<hr><h2>Website shortcut</h2>
<p>Download and extract a Windows shortcut that reopens this website with your saved storage choice.</p>
<button data-rl="shortcut">Download Windows shortcut</button>
<p class="rl-storage-muted">Use the same browser profile. Your browser may ask for folder access again. Clearing site data or using another browser requires choosing the folder again. The shortcut uses your default browser; it does not set graphics options.</p>
<div class="rl-storage-footer"><button data-rl="continue">Continue to login</button></div>`;
        document.body.appendChild(panel);
        control('folder').addEventListener('click', () => action(choose_folder));
        control('browser').addEventListener('click', () => action(use_browser));
        control('resume').addEventListener('click', () => action(continue_saved));
        control('shortcut').addEventListener('click', () => {
            try { download_shortcut(); } catch (error) { notice(error.message); }
        });
        control('continue').addEventListener('click', async () => {
            if (busy || pending) return;
            if (!selected) await use_browser();
            panel.close();
            waiting?.();
            waiting = undefined;
            startup = false;
            document.getElementById('canvas')?.focus();
        });
        panel.addEventListener('cancel', event => { if (startup || busy) event.preventDefault(); });
    }
    function show_settings(beforeStart = false) {
        if (!globalThis.document) return Promise.resolve();
        if (!panel) makePanel();
        startup = startup || beforeStart;
        render();
        if (!panel.open) panel.showModal();
        return beforeStart ? new Promise(resolve => { waiting = resolve; }) : Promise.resolve();
    }
    return {prepare, read, write, hit, corrupt, choose_folder, continue_saved, use_browser,
        show_settings, shortcut, download_shortcut, status};
})();
