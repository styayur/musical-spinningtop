/* Each selection has a generation token: stale replies and image callbacks cannot replace the current card. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = { generation: 0, selected: null, controller: null, detailTimer: null, catalogTimer: null, busy: false, imageToken: 0, followToday: false };
  const controls = ['randomBtn', 'todayBtn', 'prevBtn', 'nextBtn', 'dateInput'];
  function text(id, value) { $(id).textContent = value || ''; }
  function fallbackArt() { return window.spinningTopStatic ? './static/artwork/base.svg' : '/artwork/base.svg'; }
  function isControlledArtwork(value) {
    if (typeof value !== 'string' || value.length > 240) return false;
    const path = value.split('?')[0];
    if (/^[a-z][a-z0-9+.-]*:/i.test(path)) return false;
    if (path.includes('\\') || path.includes('..')) return false;
    return /^(?:\.\/static\/artwork\/|\/artwork\/|\/static\/artwork\/)(?:[a-f0-9]{20}|base|[0-9A-Za-z]+-[0-9A-Za-z]+-[a-f0-9]{16}-[a-f0-9]{12})\.svg$/.test(path);
  }
  function isRemoteImage(value) {
    try {
      const url = new URL(value);
      return url.protocol === 'https:' || url.protocol === 'http:';
    } catch (_) { return false; }
  }
  function link(id, value, label) {
    let url;
    try { url = new URL(value); } catch (_) { url = null; }
    const valid = url && ['https:', 'http:'].includes(url.protocol);
    $(id).hidden = !valid;
    if (valid) {
      $(id).href = url.href;
      if (label) $(id).setAttribute('aria-label', label);
    } else $(id).removeAttribute('href');
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
  }
  function setImageState(name, message) {
    $('plate').dataset.state = name;
    $('imageState').dataset.imageState = name;
    text('imageState', message);
  }
  function artworkPath(value) {
    return (value || '').split('?')[0];
  }
  function bindPlateImage(img, url, generation, token) {
    let triedFallback = false;
    const base = fallbackArt();
    img.onload = () => {
      if (token !== state.imageToken || generation !== state.generation) return;
      const current = artworkPath(img.getAttribute('src'));
      img.dataset.artworkState = current.endsWith('base.svg') && !artworkPath(url).endsWith('base.svg') ? 'fallback' : 'ready';
    };
    img.onerror = () => {
      if (token !== state.imageToken || generation !== state.generation) return;
      const current = artworkPath(img.getAttribute('src'));
      if (triedFallback || current.endsWith('base.svg') || artworkPath(url).endsWith('base.svg')) {
        triedFallback = true;
        img.dataset.artworkState = 'failed';
        return;
      }
      triedFallback = true;
      img.dataset.artworkState = 'fallback';
      img.src = base;
    };
    img.dataset.artworkState = 'loading';
    img.src = encodeURI(url);
  }
  function showImages(data, generation) {
    const token = ++state.imageToken;
    const art = isControlledArtwork(data.artwork_url) ? data.artwork_url : fallbackArt();
    const plate = document.createElement('img');
    plate.id = 'artwork';
    plate.alt = '原创节目册插画';
    plate.width = 360;
    plate.height = 480;
    $('artwork').replaceWith(plate);
    bindPlateImage(plate, art, generation, token);
    $('cover').hidden = true;
    $('cover').removeAttribute('src');
    const original = data.display_image;
    if (!original) {
      setImageState('no-original', '无原图，主画面使用生成图。');
      return;
    }
    if (!isRemoteImage(original)) {
      setImageState('failed', '原图地址未通过校验，已保留生成图。');
      return;
    }
    setImageState('loading', '原图加载中，主画面仍为生成图。');
    const img = new Image();
    let settled = false;
    const active = () => !settled && token === state.imageToken && generation === state.generation;
    const timer = setTimeout(() => {
      if (!active()) return;
      settled = true;
      setImageState('failed', '原图加载超时，已保留生成图。');
    }, 8000);
    img.onload = () => {
      clearTimeout(timer);
      if (!active()) return;
      settled = true;
      img.id = 'cover';
      img.alt = $('cover').alt;
      $('cover').replaceWith(img);
      setImageState('loaded', '原图加载成功。');
    };
    img.onerror = () => {
      clearTimeout(timer);
      if (!active()) return;
      settled = true;
      setImageState('failed', '原图加载失败，已保留生成图。');
    };
    img.src = original;
  }
  function basisText(data) {
    const rows = Array.isArray(data.artwork_basis) ? data.artwork_basis : [];
    if (data.artwork_reason === 'removed') return '该作品已不在当前目录。已保留当时的记录，并使用安全的本地基础图。';
    if (data.artwork_reason === 'error') return '插画生成失败，已改用基础图。这与简介线索不足不是同一种情况。';
    if (data.artwork_kind === 'abstract' || data.artwork_kind === 'fallback') {
      const reason = data.artwork_reason === 'empty' ? '简介为空，使用抽象剧场构图。' : '简介线索不足或无法可靠判断，使用抽象剧场构图。';
      return reason + '这是原创抽象构图，不表示剧情中的人物、地点或事件，也不是剧照或海报。';
    }
    if (!rows.length) return '原创概念插画。没有足够的可展示依据，不把它说成剧情理解。';
    const bits = rows.map(row => `${row.label || row.motif}（${row.phrase}）`).join('、');
    return `依据简介中的${bits}。这是概念插画，不是剧照、海报或维基图片。`;
  }
  function applySynopsis(value) {
    const node = $('intro');
    const shown = (value || '').trim();
    node.textContent = shown || '暂时没有可用简介。';
    node.classList.remove('drop-cap', 'cjk');
    node.removeAttribute('lang');
    if (shown.length < 90) return;
    const first = shown[0];
    if ('"\'“‘«「『'.includes(first)) return;
    node.classList.add('drop-cap');
    if (/[\u4e00-\u9fff]/.test(first)) {
      node.classList.add('cjk');
      node.lang = 'zh-CN';
    } else if (/[A-Za-z]/.test(first)) node.lang = 'en';
  }
  function render(data) {
    if (window.spinningTopSharing) window.spinningTopSharing.setWork(data);
    const shared = data.mode === 'shared';
    $('sharedNotice').hidden = !shared;
    document.querySelector('.date-nav').hidden = shared;
    const title = data.title_zh && data.title_zh !== data.title ? `${data.title} · ${data.title_zh}` : (data.title || '未命名作品');
    text('title', title);
    text('backTitle', title);
    const year = Number.isInteger(data.year) ? String(data.year) : '';
    text('yearChip', year);
    $('yearChip').hidden = !year;
    const exploring = data.mode === 'random';
    text('datePill', exploring ? '自由探索' : '每日随机');
    $('dateCluster').dataset.mode = exploring ? 'random' : 'daily';
    $('randomBtn').setAttribute('aria-pressed', String(exploring));
    $('todayBtn').setAttribute('aria-pressed', String(!exploring && !shared));
    if (data.date) $('dateInput').value = data.date;
    applySynopsis(data.intro_zh || data.intro_en || (data.detail_status === 'loading' ? '已抽到这部剧，正在加载百科简介。' : ''));
    text('introEn', data.intro_en);
    $('original').hidden = !data.intro_en || data.translator === 'none' || data.intro_en === (data.intro_zh || '');
    link('introSource', data.intro_source || data.wiki_url, '阅读来源条目');
    link('officialBtn', data.official_url);
    link('searchBtn', data.search_url);
    link('feverBtn', data.fever_url);
    link('wikiBtn', data.wiki_url);
    $('card').dataset.id = data.id || '';
    $('card').dataset.artwork = data.artwork_url || '';
    showImages(data, state.generation);
    text('workSource', data.intro_source || data.wiki_url ? '简介来自该作品对应的百科条目。' : '没有可用的简介来源。');
    const metadata = ['image_credit', 'image_attribution', 'image_artist', 'image_license']
      .map(key => typeof data[key] === 'string' ? data[key].trim() : '')
      .filter((value, index, values) => value && values.indexOf(value) === index);
    const credit = (metadata.length ? metadata.join(' · ') + '。' : '') + (data.image_reuse === 'verified'
      ? '原图已标记可复用；许可与署名见来源。'
      : data.image_source ? '原图来源已记录。许可未核实的原图不作为主画面。'
      : '条目没有可显示的原图。主画面为原创插画。');
    text('imageCredit', credit);
    link('imageSource', data.image_source, '打开图片来源');
    link('imageLicense', data.image_license_url, '阅读原图许可');
    text('artworkBasis', basisText(data));
    $('creatorLine').hidden = !data.composer;
    text('creatorLine', data.composer ? `创作者：${data.composer}` : '');
    const technical = data.detail_status === 'loading' ? '剧目已保留，正在联网补充资料。'
      : data.detail_status === 'offline' ? '暂时无法连接百科，已保留剧目及可用缓存。' : '';
    text('techNote', technical);
    document.title = `${title} · Spinning Top`;
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
        text('techNote', '资料仍在后台加载，可以继续探索或稍后回看。');
      }
    } catch (_) {
      if (generation === state.generation) text('techNote', '资料暂时无法加载。剧目已保留，可稍后回看。');
    }
  }
  async function load(mode = 'daily', selectedDate = '') {
    if (document.getElementById('sharedWork')) {
      // Freeze the resolved base before changing the document URL; otherwise
      // "../" would escape the Pages subpath when leaving a work page.
      const base = document.querySelector('base');
      if (base) base.href = document.baseURI;
      history.replaceState(null, '', new URL('./', document.baseURI).pathname);
    }
    $('shareBtn').disabled = true;
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
      $('original').open = false;
      render(data);
      if (data.detail_status === 'loading') state.detailTimer = setTimeout(() => pollDetails(generation), 1500);
    } catch (error) {
      if (generation !== state.generation) return;
      text('notice', error.name === 'AbortError' ? '请求超时，请确认程序正在运行后重试。' : error.message);
      $('retryBtn').hidden = false;
      if (!state.selected) { text('title', '暂未开场'); text('intro', '请确认本地程序正在运行，然后重试。'); }
      if (state.selected && state.selected.date) $('dateInput').value = state.selected.date;
    } finally {
      if (generation === state.generation) {
        state.busy = false;
        controls.forEach(id => $(id).disabled = false);
        $('card').classList.remove('loading');
        $('card').setAttribute('aria-busy', 'false');
        if (window.spinningTopSharing) window.spinningTopSharing.setWork(state.selected);
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
        const updated = data.updated_at ? new Date(data.updated_at).toLocaleDateString('zh-CN') : '内置目录';
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
  function selectTab(name) {
    for (const tab of $('infoDialog').querySelectorAll('[role="tab"]')) {
      const on = tab.dataset.tab === name;
      tab.setAttribute('aria-selected', String(on));
      tab.tabIndex = on ? 0 : -1;
      $(tab.getAttribute('aria-controls')).hidden = !on;
    }
  }
  let restoreFocus = null;
  function openInfo() {
    restoreFocus = document.activeElement;
    selectTab('work');
    $('infoDialog').showModal();
    $('tabWork').focus();
  }
  function closeInfo() {
    if ($('infoDialog').open) $('infoDialog').close();
  }
  $('infoBtn').addEventListener('click', openInfo);
  $('infoClose').addEventListener('click', closeInfo);
  $('infoDialog').addEventListener('close', () => { if (restoreFocus && restoreFocus.focus) restoreFocus.focus(); });
  $('infoDialog').addEventListener('click', event => { if (event.target === $('infoDialog')) closeInfo(); });
  $('infoDialog').querySelectorAll('[role="tab"]').forEach(tab => {
    tab.addEventListener('click', () => selectTab(tab.dataset.tab));
    tab.addEventListener('keydown', event => {
      const tabs = [...$('infoDialog').querySelectorAll('[role="tab"]')];
      const index = tabs.indexOf(tab);
      let next = index;
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;
      event.preventDefault();
      selectTab(tabs[next].dataset.tab);
      tabs[next].focus();
    });
  });
  $('infoDialog').addEventListener('keydown', event => {
    if (event.key !== 'Tab' || !$('infoDialog').open) return;
    const items = [...$('infoDialog').querySelectorAll('button, a[href], input, [tabindex]')].filter(el => el.tabIndex >= 0 && !el.disabled && !el.closest('[hidden]'));
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  $('randomBtn').addEventListener('click', () => load('random'));
  $('todayBtn').addEventListener('click', () => load());
  $('prevBtn').addEventListener('click', () => moveDate(-1));
  $('nextBtn').addEventListener('click', () => moveDate(1));
  $('dateInput').addEventListener('change', () => { if ($('dateInput').value) load('daily', $('dateInput').value); });
  $('retryBtn').addEventListener('click', () => load('daily', $('dateInput').value));
  $('flipBtn').addEventListener('click', () => flip(!$('card').classList.contains('flipped')));
  $('plate').addEventListener('click', () => flip(true));
  $('backFace').addEventListener('click', event => { if (!event.target.closest('a')) flip(false); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('infoDialog').open) flip(false); });
  $('syncBtn').addEventListener('click', async () => {
    $('syncBtn').disabled = true;
    try {
      const result = await api('/api/catalog/refresh', { method: 'POST' });
      if (!result.started && !result.sync.running) text('notice', '刚刚已尝试更新，请稍等一分钟再试。');
      await catalogStatus();
    } catch (_) { text('catalogStatus', '无法开始更新，请确认程序正在运行。'); }
    finally { if (!state.catalogTimer) $('syncBtn').disabled = false; }
  });
  setInterval(async () => {
    if (!state.followToday || state.busy || document.hidden) return;
    try {
      const status = await api('/api/catalog');
      if (state.selected && state.selected.date !== status.today) load();
    } catch (_) { /* The visible card remains usable when the server is temporarily unavailable. */ }
  }, 60000);
  window.spinningTopMedia = { isControlledArtwork, isRemoteImage };
  const sharedNode = document.getElementById('sharedWork');
  if (sharedNode) {
    const data = JSON.parse(sharedNode.textContent);
    state.selected = data;
    state.generation++;
    render(data);
    $('card').setAttribute('aria-busy', 'false');
    text('catalogCount', data.total ? `${data.total.toLocaleString('zh-CN')} 部可探索` : '分享作品 · 只读');
  } else {
    load();
    catalogStatus();
  }
})();
