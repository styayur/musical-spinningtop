/* SPDX-License-Identifier: AGPL-3.0-only
 * GitHub Pages adapter: Web Crypto draws + transactional, per-browser IndexedDB history.
 */
(() => {
  'use strict';
  const database = new Promise((resolve, reject) => {
    const open = indexedDB.open('musical-spinningtop-v2', 1);
    open.onupgradeneeded = () => {
      for (const name of ['daily', 'cycles', 'cache']) open.result.createObjectStore(name);
    };
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(new Error('无法打开浏览器存储，请允许此网站保存数据。'));
  });
  let library;
  let loading;
  let refreshPromise;
  const requestResult = request => new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  async function readCache() {
    const db = await database;
    return requestResult(db.transaction('cache').objectStore('cache').get('catalog'));
  }
  async function refreshData() {
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async () => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 12000);
      try {
        const response = await fetch('./data/site-catalog.json', { cache: 'no-cache', signal: controller.signal });
        if (!response.ok) throw new Error('片库下载失败，请检查网络后重试。');
        const next = await response.json();
        if (!Array.isArray(next.musicals) || !next.musicals.length || next.musicals.some(row => !row.id || !row.title)) {
          throw new Error('片库格式不正确，已保留之前的片库。');
        }
        const db = await database;
        await new Promise((resolve, reject) => {
          const tx = db.transaction('cache', 'readwrite');
          tx.objectStore('cache').put(next, 'catalog');
          tx.oncomplete = resolve;
          tx.onabort = () => reject(new Error('浏览器存储空间不足，无法保存片库。'));
        });
        library = next;
        return next;
      } finally { clearTimeout(timer); }
    })();
    try { return await refreshPromise; }
    finally { refreshPromise = null; }
  }
  async function loadLibrary() {
    if (library) return library;
    if (!loading) loading = (async () => {
      const cached = await readCache();
      if (cached && cached.musicals && cached.musicals.length) {
        library = cached;
        refreshData().catch(() => {}); // Last successful snapshot stays available offline.
        return cached;
      }
      return refreshData();
    })();
    try { return await loading; }
    catch (error) { loading = null; throw error; }
  }
  function today() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }
  function randomIndex(length) {
    if (!Number.isSafeInteger(length) || length < 1 || length > 0x100000000) throw new Error('片库为空或过大。');
    const bound = Math.floor(0x100000000 / length) * length;
    const buffer = new Uint32Array(1);
    do { crypto.getRandomValues(buffer); } while (buffer[0] >= bound);
    return buffer[0] % length;
  }
  async function draw(day) {
    const entries = (await loadLibrary()).musicals;
    const db = await database;
    const kind = day ? 'daily' : 'random';
    // The read/choose/write sequence uses one readwrite transaction, including across tabs.
    return new Promise((resolve, reject) => {
      const tx = db.transaction(['daily', 'cycles'], 'readwrite');
      let chosen;
      tx.oncomplete = () => resolve(chosen);
      tx.onabort = () => reject(new Error('抽取结果未能保存，请检查浏览器存储后重试。'));
      function select() {
        const cycles = tx.objectStore('cycles');
        const request = cycles.get(kind);
        request.onsuccess = () => {
          const cycle = request.result || { used: [], last: null };
          let used = new Set(cycle.used);
          let pool = entries.filter(row => !used.has(row.id));
          if (!pool.length) {
            used = new Set();
            pool = entries.filter(row => row.id !== cycle.last);
            if (!pool.length) pool = entries;
          }
          chosen = pool[randomIndex(pool.length)];
          used.add(chosen.id);
          cycles.put({ used: Array.from(used), last: chosen.id }, kind);
          if (day) tx.objectStore('daily').put(chosen, day);
        };
      }
      if (day) {
        const existing = tx.objectStore('daily').get(day);
        existing.onsuccess = () => { if (existing.result) chosen = existing.result; else select(); };
      } else select();
    });
  }
  function payload(entry, day = null, mode = 'daily') {
    return { ...entry, date: day, mode, total: library.musicals.length, detail_status: 'ready',
      intro_zh: entry.intro_zh || entry.intro_en || '', translator: entry.translator || 'none',
      fever_url: 'https://www.google.com/search?q=' + encodeURIComponent(entry.title + ' musical site:feverup.com'),
      search_url: 'https://www.google.com/search?q=' + encodeURIComponent(entry.title + ' musical official') };
  }
  async function api(path, options = {}) {
    const url = new URL(path, location.origin);
    await loadLibrary();
    if (url.pathname === '/api/catalog/refresh') {
      if (options.method !== 'POST') throw new Error('请使用更新按钮。');
      await refreshData();
      return { started: true, sync: { running: false } };
    }
    if (url.pathname === '/api/catalog') return {
      today: today(), total: library.musicals.length, updated_at: library.updated_at,
      sync: { running: false, done: 0, total: 0, error: null },
    };
    if (url.pathname === '/api/random') {
      if (options.method !== 'POST') throw new Error('请使用抽取按钮。');
      return payload(await draw(), null, 'random');
    }
    if (url.pathname === '/api/musical') {
      const day = url.searchParams.get('date') || today();
      const parsed = new Date(day + 'T12:00:00Z');
      if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== day || day < '1900-01-01' || day > '2200-12-31') {
        throw new Error('日期无效，请选择 1900 至 2200 年的日期。');
      }
      return payload(await draw(day), day);
    }
    throw new Error('不支持的请求。');
  }
  window.spinningTopStatic = { request: api };
})();
