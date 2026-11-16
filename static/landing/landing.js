// ChantierMobile presentation page: mobile menu, feature tabs, clips.
(function () {
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Mobile menu
  var toggle = document.querySelector('.menu-toggle');
  var menu = document.getElementById('menu');
  if (toggle && menu) {
    toggle.addEventListener('click', function () {
      var open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!open));
      menu.classList.toggle('open', !open);
    });
    menu.addEventListener('click', function (e) {
      if (e.target.closest('a[href^="#"]')) { toggle.setAttribute('aria-expanded', 'false'); menu.classList.remove('open'); }
    });
  }

  // Clips play only while visible, and never on their own when the visitor
  // asked for reduced motion (they get the poster and the native controls).
  function setupClip(v) {
    if (reduce) { v.removeAttribute('autoplay'); v.controls = true; return; }
    if (!('IntersectionObserver' in window)) { v.play().catch(function () {}); return; }
    new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var panel = v.closest('[role="tabpanel"]');
        if (en.isIntersecting && !(panel && panel.hidden)) { v.play().catch(function () {}); } else { v.pause(); }
      });
    }, { threshold: 0.35 }).observe(v);
  }
  document.querySelectorAll('video.clip').forEach(setupClip);

  // Feature tabs (WAI-ARIA tabs pattern: arrows, Home/End)
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.feat-tabs [role="tab"]'));
  function select(tab, focus) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      var panel = document.getElementById(t.getAttribute('aria-controls'));
      panel.hidden = !on;
      var v = panel.querySelector('video');
      if (v) {
        if (on && !reduce) { v.preload = 'auto'; v.currentTime = 0; v.play().catch(function () {}); }
        else v.pause();
      }
    });
    if (focus) tab.focus();
    if (tab.scrollIntoView && window.innerWidth <= 1080) tab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }
  tabs.forEach(function (tab, i) {
    tab.addEventListener('click', function () { select(tab, false); });
    tab.addEventListener('keydown', function (e) {
      var k = e.key, n = null;
      if (k === 'ArrowDown' || k === 'ArrowRight') n = tabs[(i + 1) % tabs.length];
      else if (k === 'ArrowUp' || k === 'ArrowLeft') n = tabs[(i - 1 + tabs.length) % tabs.length];
      else if (k === 'Home') n = tabs[0];
      else if (k === 'End') n = tabs[tabs.length - 1];
      if (n) { e.preventDefault(); select(n, true); }
    });
  });
})();
