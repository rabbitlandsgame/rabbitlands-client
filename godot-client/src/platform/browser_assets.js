/* The launch host serves this small loader; the asset host serves all payloads. */
'use strict';
globalThis.RabbitLandsBrowser = (() => {
    const LIMIT = 64 * 1024 * 1024;
    async function start(engine, config, callbacks = {}) {
        const response = await fetch('browser-assets.json', {cache: 'no-cache'});
        if (!response.ok) throw new Error('Cannot load the browser asset manifest.');
        const manifest = await response.json();
        const base = new URL(manifest.base_url, location.href);
        const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname);
        if ((base.protocol !== 'https:' && !(base.protocol === 'http:' && loopback)) || base.username || base.password) {
            throw new Error('Game assets require HTTPS or a local test server.');
        }
        if (manifest.schema !== 1 || !Array.isArray(manifest.pack?.parts) ||
                !Number.isSafeInteger(manifest.pack.bytes) || manifest.pack.bytes <= 0 || manifest.pack.bytes > 512 * 1024 * 1024) {
            throw new Error('Invalid browser asset manifest.');
        }
        let completed = 0;
        const total = manifest.pack.bytes + manifest.wasm.bytes;
        const progress = () => callbacks.onProgress?.(completed, total);
        async function verified(row) {
            if (!/^[a-f0-9]{64}\.(bin|wasm|zip)$/.test(row.file) || !/^[a-f0-9]{64}$/.test(row.sha256) ||
                    !Number.isSafeInteger(row.bytes) || row.bytes <= 0 || row.bytes > LIMIT) {
                throw new Error('Invalid game download entry.');
            }
            const download = await fetch(new URL(row.file, base), {mode: 'cors', credentials: 'omit'});
            if (!download.ok) throw new Error(`Game download failed (${download.status}).`);
            const bytes = await download.arrayBuffer();
            const digest = await crypto.subtle.digest('SHA-256', bytes);
            const hash = Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('');
            if (bytes.byteLength !== row.bytes || hash !== row.sha256) throw new Error('Game download is incomplete or outdated.');
            completed += bytes.byteLength;
            progress();
            return bytes;
        }
        // Keep the original executable name so worker scripts stay on the
        // launch origin. The verified WASM response alone uses a blob URL.
        const wasm = await verified(manifest.wasm);
        const wasmURL = URL.createObjectURL(new Blob([wasm], {type: 'application/wasm'}));
        globalThis.RL_BROWSER_WASM_URL = wasmURL;
        globalThis.RL_BROWSER_ASSETS = {...manifest, base_url: base.href};
        try {
            await engine.init(config.executable);
        } finally {
            URL.revokeObjectURL(wasmURL);
            delete globalThis.RL_BROWSER_WASM_URL;
        }
        let pack = new Uint8Array(manifest.pack.bytes);
        let offset = 0;
        for (const row of manifest.pack.parts) {
            const bytes = await verified(row);
            if (offset + bytes.byteLength > pack.byteLength) throw new Error('Invalid game package length.');
            pack.set(new Uint8Array(bytes), offset);
            offset += bytes.byteLength;
        }
        if (offset !== pack.byteLength) throw new Error('Incomplete game package.');
        await engine.preloadFile(pack.buffer, 'index.pck');
        pack = null;
        await engine.start({args: ['--main-pack', 'index.pck', ...config.args]});
    }
    return {start};
})();
