/* User-initiated sharing only. No SDKs, analytics, remote images or automatic posts. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  function preferredLanguage() {
    const values = [...(navigator.languages || []), navigator.language];
    for (const value of values) {
      try { if (typeof value === 'string' && value.trim()) return Intl.getCanonicalLocales(value)[0]; } catch (_) { /* Try the next valid preference. */ }
    }
    return 'en';
  }
  const language = preferredLanguage();
  const zh = /^zh(?:-|$)/i.test(language);
  const words = zh ? {
    invitation: '把今天，交给一场好戏。', share: '分享当前作品', close: '关闭分享',
    native: '使用设备分享', copy: '复制作品链接', save: '保存分享卡片', link: '当前作品链接',
    help: '平台预览可能不同。可保存卡片后手动附加图片。', loading: '正在准备分享…',
    unavailable: '该作品没有已发布的公开页面，无法分享。不会改抽其他作品。',
    failed: '分享资料加载失败，请关闭后重试。', copied: '链接已复制。',
    copyFailed: '复制失败，请选中链接手动复制。', saved: '分享卡片已准备下载。',
    imageFailed: '图片加载失败，请稍后重试保存。', cancelled: '已取消分享。',
    nativeFailed: '设备分享不可用，请使用平台链接或复制链接。',
    shared: '正在查看分享作品 · 只读。可主动返回今日或自由探索。',
  } : {
    invitation: 'Give today to a good show.', share: 'Share this work', close: 'Close sharing',
    native: 'Share with your device', copy: 'Copy work link', save: 'Save share card', link: 'Current work link',
    help: 'Previews vary by platform. Save the card to attach it manually.', loading: 'Preparing sharing…',
    unavailable: 'This work has no published public page. No replacement will be drawn.',
    failed: 'Sharing details could not load. Close and try again.', copied: 'Link copied.',
    copyFailed: 'Copy failed. Select the link and copy it manually.', saved: 'Share card ready to download.',
    imageFailed: 'Image could not load. Please try saving again later.', cancelled: 'Sharing cancelled.',
    nativeFailed: 'Device sharing is unavailable. Use a platform or copy the link.',
    shared: 'Shared work · read only. Return to today or explore when you choose.',
  };
  $('invitation').textContent = words.invitation;
  $('invitation').lang = zh ? language : 'en';
  $('shareDialog').lang = zh ? language : 'en';
  $('shareTitle').textContent = words.share;
  $('shareBtn').setAttribute('aria-label', words.share);
  $('shareBtn').title = words.share;
  $('shareClose').setAttribute('aria-label', words.close);
  for (const [id, key] of Object.entries({nativeShare:'native', copyShare:'copy', saveShare:'save', shareLinkLabel:'link', shareHelp:'help'})) $(id).textContent = words[key];
  $('sharedNotice').textContent = words.shared;
  $('sharedNotice').lang = zh ? language : 'en';
  let current = null, epoch = 0, active = null, restore = null;
  const status = key => { $('shareStatus').textContent = words[key] || ''; };
  const platforms = {shareX:'https://x.com/intent/tweet', shareFacebook:'https://www.facebook.com/sharer/sharer.php', shareWhatsApp:'https://wa.me/', shareThreads:'https://www.threads.com/intent/post'};
  function enabled(on) {
    for (const id of ['copyShare', 'saveShare']) $(id).disabled = !on;
    $('sharePlatforms').hidden = !on;
  }
  function safeInfo(info) {
    if (!info || !info.available) return false;
    try {
      const link = new URL(info.url);
      const image = new URL(info.image, document.baseURI);
      return link.origin === 'https://styayur.github.io' && /^\/musical-spinningtop\/works\/[A-Za-z0-9_-]+\.html$/.test(link.pathname) && !link.search && !link.hash &&
        image.origin === location.origin && /\/[a-f0-9]{64}\.png$/.test(image.pathname);
    } catch (_) { return false; }
  }
  async function prepare(row) {
    if (window.spinningTopStatic) {
      const response = await fetch(new URL('./data/share-index.json', document.baseURI), {cache:'no-cache'});
      if (!response.ok) throw new Error('index');
      return (await response.json())[row.id] || {available:false};
    }
    const response = await fetch('/api/share?id=' + encodeURIComponent(row.id), {cache:'no-store'});
    if (!response.ok) throw new Error('share');
    return response.json();
  }
  $('shareBtn').addEventListener('click', async () => {
    if (!current || current.unavailable) return;
    const token = ++epoch, row = {...current};
    restore = document.activeElement;
    active = null;
    enabled(false);
    $('nativeShare').hidden = true;
    $('shareLink').value = '';
    $('shareWorkTitle').textContent = row.title_zh || row.title || '';
    status('loading');
    $('shareDialog').showModal();
    $('shareClose').focus();
    try {
      const info = await prepare(row);
      if (token !== epoch || !$('shareDialog').open) return;
      if (!info.available) { status('unavailable'); return; }
      if (!safeInfo(info)) throw new Error('invalid sharing data');
      active = {...info, title:row.title_zh || row.title || 'Spinning Top'};
      $('shareLink').value = info.url;
      for (const [id, endpoint] of Object.entries(platforms)) {
        const url = new URL(endpoint);
        if (id === 'shareFacebook') url.searchParams.set('u', info.url);
        else if (id === 'shareWhatsApp') url.searchParams.set('text', active.title + '\n' + info.url);
        else { url.searchParams.set('text', active.title); url.searchParams.set('url', info.url); }
        $(id).href = url.href;
      }
      enabled(true);
      status('');
      try {
        $('nativeShare').hidden = !(navigator.share && navigator.canShare && navigator.canShare({title:active.title, url:active.url}));
      } catch (_) { $('nativeShare').hidden = true; }
    } catch (_) { if (token === epoch) status('failed'); }
  });
  $('nativeShare').addEventListener('click', async () => {
    if (!active) return;
    const token = epoch;
    try { await navigator.share({title:active.title, url:active.url}); }
    catch (error) { if (token === epoch) status(error.name === 'AbortError' ? 'cancelled' : 'nativeFailed'); }
  });
  $('copyShare').addEventListener('click', async () => {
    if (!active) return;
    const token = epoch;
    try { await navigator.clipboard.writeText(active.url); if (token === epoch) status('copied'); }
    catch (_) { if (token === epoch) { status('copyFailed'); $('shareLink').focus(); $('shareLink').select(); } }
  });
  $('saveShare').addEventListener('click', async () => {
    if (!active) return;
    const token = epoch, selected = {...active};
    $('saveShare').disabled = true;
    try {
      const response = await fetch(new URL(selected.image, document.baseURI));
      if (!response.ok || !(response.headers.get('Content-Type') || '').startsWith('image/png')) throw new Error('image');
      const blob = await response.blob();
      if (token !== epoch || !$('shareDialog').open) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'Spinning-Top-' + new URL(selected.url).pathname.split('/').pop().replace('.html', '.png');
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status('saved');
    } catch (_) { if (token === epoch) status('imageFailed'); }
    finally { if (token === epoch) $('saveShare').disabled = false; }
  });
  $('shareClose').addEventListener('click', () => $('shareDialog').close());
  $('shareDialog').addEventListener('click', event => { if (event.target === $('shareDialog')) $('shareDialog').close(); });
  $('shareDialog').addEventListener('close', () => { ++epoch; active = null; if (restore && restore.isConnected) restore.focus(); });
  window.spinningTopSharing = {setWork(row) {
    if (current && row && current.id !== row.id && $('shareDialog').open) $('shareDialog').close();
    current = row;
    $('shareBtn').disabled = !row || !row.id || row.unavailable;
  }};
})();
