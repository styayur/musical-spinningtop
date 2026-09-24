/* Each selection has a generation token: stale network replies cannot replace the current card. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = { generation: 0, selected: null, controller: null, detailTimer: null, catalogTimer: null, busy: false };
  const labels = { wikipedia_zh: '中文维基百科', bundled: '内置中文摘要', none: '英文维基百科' };
  const controls = ['randomBtn', 'todayBtn', 'prevBtn', 'nextBtn', 'dateInput'];
  function text(id, value) { $(id).textContent = value || ''; }
  function link(id, value) {
    let url;
    try { url = new URL(value); } catch (_) { url = null; }
    const valid = url && ['https:', 'http:'].includes(url.protocol);
    $(id).hidden = !valid;
    if (valid) $(id).href = url.href;
    else $(id).removeAttribute('href');
  }
  async function api(url, options = {}) {
    if (window.spinningTopStatic) return window.spinningTopStatic.request(url, options);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    const abort = () => controller.abort();
    if (options.signal) options.signal.addEventListener('abort', abort, { once: true });
    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '请求失败，请重试。');
      return data;
    } finally {
      clearTimeout(timeout);
      if (options.signal) options.signal.removeEventListener('abort', abort);
    }
  }
  function flip(flipped) {
    $('card').classList.toggle('flipped', flipped);
    $('frontFace').inert = flipped;
    $('backFace').inert = !flipped;
    $('flipBtn').setAttribute('aria-pressed', String(flipped));
    text('flipBtn', flipped ? '返回简介' : '翻面看链接');
  }
  function render(data) {
    const title = data.title_zh && data.title_zh !== data.title ? `${data.title} · ${data.title_zh}` : data.title;
    text('title', title);
    text('backTitle', title);
    text('yearChip', data.year ? `${data.year} 年作品` : '音乐剧');
    text('composer', data.composer || '从片库中，偶然遇见');
    text('datePill', data.mode === 'random' ? '自由探索' : '每日随机');
    if (data.date) $('dateInput').value = data.date;
    text('intro', data.intro_zh || data.intro_en || (data.detail_status === 'loading' ? '已抽到这部剧，正在加载百科简介…' : '暂时没有可用简介，可以翻面阅读来源条目。'));
    text('translatorTag', data.intro_zh || data.intro_en ? labels[data.translator] || '百科资料' : '');
    text('introEn', data.intro_en);
    $('original').hidden = !data.intro_en || data.translator === 'none';
    link('introSource', data.intro_source || data.wiki_url);
    link('imageSource', data.image ? data.image_source : null);
    link('officialBtn', data.official_url);
    link('searchBtn', data.search_url);
    link('feverBtn', data.fever_url);
    link('wikiBtn', data.wiki_url);
    // Covers are optional: broken remote images retain the designed curtain artwork.
    const cover = data.image || '';
    if ($('hero').dataset.cover !== cover) {
      $('hero').dataset.cover = cover;
      $('hero').style.backgroundImage = '';
      $('hero').classList.remove('has-image');
      if (/^https:\/\//.test(cover)) {
        const img = new Image();
        img.onload = () => {
          if ($('hero').dataset.cover === cover) {
            $('hero').style.backgroundImage = `url(${JSON.stringify(cover)})`;
            $('hero').classList.add('has-image');
          }
        };
        img.src = cover;
      }
    }
    text('detailStatus', data.detail_status === 'loading' ? '剧目已保留 · 正在联网补充资料' : data.detail_status === 'offline' ? '暂时无法连接百科 · 已保留剧目及可用缓存' : data.image ? '资料来自百科 · 图片版权见来源页' : '该条目暂无可用封面');
    document.title = `${title} · 每日音乐剧`;
  }
  async function pollDetails(generation, attempts = 0) {
    if (generation !== state.generation || !state.selected) return;
    try {
      const data = await api(`/api/details?id=${encodeURIComponent(state.selected.id)}`);
      if (generation !== state.generation) return;
      state.selected = { ...state.selected, ...data, date: state.selected.date, mode: state.selected.mode };
      render(state.selected);
      if (data.detail_status === 'loading' && attempts < 44) {
        state.detailTimer = setTimeout(() => pollDetails(generation, attempts + 1), 2000);
      } else if (data.detail_status === 'loading') {
        text('detailStatus', '资料仍在后台加载，可以继续探索或稍后回看。');
      }
    } catch (_) {
      if (generation === state.generation) text('detailStatus', '资料暂时无法加载 · 剧目已保留，可稍后回看');
    }
  }
  async function load(mode = 'daily', selectedDate = '') {
    const generation = ++state.generation;
    clearTimeout(state.detailTimer);
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    state.busy = true;
    controls.forEach(id => $(id).disabled = true);
    $('card').classList.add('loading');
    $('card').setAttribute('aria-busy', 'true');
    $('retryBtn').hidden = true;
    text('notice', '');
    flip(false);
    try {
      const url = mode === 'random' ? '/api/random' : `/api/musical${selectedDate ? '?date=' + encodeURIComponent(selectedDate) : ''}`;
      const data = await api(url, { method: mode === 'random' ? 'POST' : 'GET', signal: state.controller.signal });
      if (generation !== state.generation) return;
      state.selected = data;
      state.followToday = mode === 'daily' && !selectedDate;
      $('frontBody').scrollTop = 0;
      $('original').open = false;
      render(data);
      if (data.detail_status === 'loading') state.detailTimer = setTimeout(() => pollDetails(generation), 1500);
    } catch (error) {
      if (generation !== state.generation) return;
      text('notice', error.name === 'AbortError' ? '请求超时，请确认程序正在运行后重试。' : error.message);
      $('retryBtn').hidden = false;
      if (!state.selected) { text('title', '暂未开场'); text('intro', '请确认本地程序正在运行，然后点击“重试加载”。'); }
      // A failed navigation must not display the new date beside the old card.
      if (state.selected && state.selected.date) $('dateInput').value = state.selected.date;
    } finally {
      if (generation === state.generation) {
        state.busy = false;
        controls.forEach(id => $(id).disabled = false);
        $('card').classList.remove('loading');
        $('card').setAttribute('aria-busy', 'false');
      }
    }
  }
  async function catalogStatus() {
    clearTimeout(state.catalogTimer);
    state.catalogTimer = null;
    try {
      const data = await api('/api/catalog');
      text('catalogCount', `${data.total.toLocaleString('zh-CN')} 部可探索`);
      $('syncBtn').disabled = data.sync.running;
      if (data.sync.running) {
        text('catalogStatus', `正在更新片库 ${data.sync.done} / ${data.sync.total || '…'} 个年份分类 · 可继续抽取`);
        state.catalogTimer = setTimeout(catalogStatus, 2500);
      } else {
        const updated = data.updated_at ? new Date(data.updated_at).toLocaleDateString('zh-CN') : '内置精选片单';
        text('catalogStatus', data.sync.error || `片库更新：${updated} · 收录英文维基百科按年份分类的音乐剧`);
      }
    } catch (_) { text('catalogStatus', '片库状态暂时无法读取，请确认程序正在运行。'); }
  }
  function moveDate(delta) {
    const date = new Date($('dateInput').value + 'T12:00:00');
    if (Number.isNaN(date.getTime())) return;
    date.setDate(date.getDate() + delta);
    load('daily', `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`);
  }
  $('randomBtn').addEventListener('click', () => load('random'));
  $('todayBtn').addEventListener('click', () => load());
  $('prevBtn').addEventListener('click', () => moveDate(-1));
  $('nextBtn').addEventListener('click', () => moveDate(1));
  $('dateInput').addEventListener('change', () => { if ($('dateInput').value) load('daily', $('dateInput').value); });
  $('retryBtn').addEventListener('click', () => load('daily', $('dateInput').value));
  $('flipBtn').addEventListener('click', () => flip(!$('card').classList.contains('flipped')));
  $('hero').addEventListener('click', () => flip(true));
  $('backFace').addEventListener('click', event => { if (!event.target.closest('a')) flip(false); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') flip(false); });
  $('syncBtn').addEventListener('click', async () => {
    $('syncBtn').disabled = true;
    try {
      const result = await api('/api/catalog/refresh', { method: 'POST' });
      if (!result.started && !result.sync.running) text('notice', '刚刚已尝试更新，请稍等一分钟再试。');
      await catalogStatus();
    } catch (_) { text('catalogStatus', '无法开始更新，请确认程序正在运行。'); }
    finally { if (!state.catalogTimer) $('syncBtn').disabled = false; }
  });
  // Follow the server's local date only while viewing today's card, never while browsing history.
  setInterval(async () => {
    if (!state.followToday || state.busy || document.hidden) return;
    try {
      const status = await api('/api/catalog');
      if (state.selected && state.selected.date !== status.today) load();
    } catch (_) { /* The visible card remains usable when the server is temporarily unavailable. */ }
  }, 60000);
  load();
  catalogStatus();
})();
