/* Configuration is emitted by deployment.py, never inferred from an arbitrary URL. */
(() => {
  'use strict';
  const config = JSON.parse(document.getElementById('deploymentConfig').textContent);
  const origin = new URL(config.public_origin);
  if (config.schema_version !== 1 || origin.protocol !== 'https:' || origin.origin !== config.public_origin ||
      !/^\/(?:[a-z0-9-]+\/)+$/.test(config.base_path) ||
      config.public_base !== config.public_origin + config.base_path ||
      config.work_prefix !== 'works/' || !['', '.html'].includes(config.work_suffix) ||
      !['static', 'flask'].includes(config.mode) ||
      config.artwork_path !== (config.mode === 'static' ? './static/artwork/' : '/artwork/') ||
      config.local_card_path !== (config.mode === 'static' ? './static/share/' : '/share-cards/')) throw new Error('Invalid deployment configuration');
  const key = identity => btoa(Array.from(new TextEncoder().encode(identity), byte => String.fromCharCode(byte)).join(''))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const workURL = identity => config.public_base + config.work_prefix + key(identity) + config.work_suffix;
  function safeImage(value) {
    if (typeof value !== 'string' || /[\\%\s]/.test(value)) return false;
    try {
      const url = new URL(value, document.baseURI);
      const base = new URL(config.local_card_path, document.baseURI);
      return url.origin === location.origin && url.origin === base.origin && !url.username && !url.password &&
        !url.search && !url.hash && url.pathname.startsWith(base.pathname) &&
        /^[a-f0-9]{64}\.png$/.test(url.pathname.slice(base.pathname.length));
    } catch (_) { return false; }
  }
  window.spinningTopDeployment = Object.freeze({ ...config, workURL, safeImage });
})();
