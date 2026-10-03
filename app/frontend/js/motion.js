import { hasGSAP, reduceMotion } from './utils.js';

document.addEventListener('visibilitychange', () => {
  document.body.classList.toggle('anim-paused', document.hidden);
  if (document.hidden) {
    stopHeroBeatLoop();
    if (hasGSAP) gsap.globalTimeline.pause();
  } else {
    if (hasGSAP) gsap.globalTimeline.resume();
    startHeroBeatLoop();
  }
});

// 14 is about the limit before it starts looking like dust on the screen
export function spawnParticles() {
  if (reduceMotion) return;
  const host = document.getElementById('particles');
  const frag = document.createDocumentFragment();
  for (let i = 0; i < 14; i++) {
    const p = document.createElement('div');
    p.className = 'particle';
    const size = 2 + Math.random() * 3;
    p.style.width = size + 'px';
    p.style.height = size + 'px';
    p.style.left = Math.random() * 100 + 'vw';
    p.style.top = Math.random() * 100 + 'vh';
    p.style.setProperty('--dur', (12 + Math.random() * 14) + 's');
    p.style.setProperty('--delay', (Math.random() * 8) + 's');
    p.style.setProperty('--dx', (Math.random() * 70 - 35) + 'px');
    p.style.setProperty('--dy', (-25 - Math.random() * 55) + 'px');
    frag.appendChild(p);
  }
  host.appendChild(frag);
}

// wrap each word so it can't break mid-word, then one span per char
function splitHeroLetters() {
  const el = document.getElementById('heroText');
  if (!el) return null;
  const text = el.textContent;
  el.textContent = '';
  let idx = 0;
  const words = text.split(' ');
  words.forEach((word, wi) => {
    const wordSpan = document.createElement('span');
    wordSpan.style.display = 'inline-block';
    wordSpan.style.whiteSpace = 'nowrap';
    [...word].forEach((ch) => {
      const letter = document.createElement('span');
      letter.className = 'letter';
      letter.style.setProperty('--i', idx++);
      letter.textContent = ch;
      wordSpan.appendChild(letter);
    });
    el.appendChild(wordSpan);
    if (wi < words.length - 1) el.appendChild(document.createTextNode(' '));
  });
  return el;
}

let beatTimer = null;

// Beats stick to y/rotation, the breathing tween owns yPercent/scale.
// Different transform components, so GSAP composes them instead of one
// overwriting the other. Don't move either onto the other's props.
function beatWave(letters) {
  return gsap.timeline()
    .to(letters, { y: -12, rotation: 4, duration: 0.28, ease: 'power2.out', stagger: 0.018 })
    .to(letters, { y: 0, rotation: 0, duration: 0.5, ease: 'elastic.out(1, 0.55)', stagger: 0.018 }, '-=0.08');
}
function beatBounce(letters) {
  return gsap.timeline()
    .to(letters, { y: -18, duration: 0.24, ease: 'power2.out', stagger: 0.014 })
    .to(letters, { y: 0, duration: 0.55, ease: 'bounce.out', stagger: 0.014 }, '-=0.05');
}
function beatTilt(letters) {
  return gsap.timeline()
    .to(letters, { rotation: (i) => (i % 2 ? 7 : -7), duration: 0.3, ease: 'power2.out', stagger: 0.016 })
    .to(letters, { rotation: 0, duration: 0.6, ease: 'elastic.out(1, 0.5)', stagger: 0.016 }, '-=0.1');
}

// picked at random each time so it doesn't feel like a loop
const heroBeats = [beatWave, beatBounce, beatTilt];

function playHeroBeat() {
  const heroText = document.getElementById('heroText');
  if (!heroText || document.hidden) return;
  const letters = heroText.querySelectorAll('.letter');
  if (!letters.length) return;
  heroBeats[Math.floor(Math.random() * heroBeats.length)](letters);
}

function startHeroBeatLoop() {
  if (!hasGSAP || reduceMotion || document.hidden) return;
  stopHeroBeatLoop();
  if (!document.getElementById('heroText')) return;
  beatTimer = setInterval(playHeroBeat, 4000);
}

export function stopHeroBeatLoop() {
  if (beatTimer) { clearInterval(beatTimer); beatTimer = null; }
}

// re-run every time the empty state is remounted. matchMedia gives us the
// reduced-motion branch for free and reverts itself if the setting flips.
let heroMM = null;
export function initHeroAnimation() {
  if (heroMM) { heroMM.revert(); heroMM = null; }

  const el = splitHeroLetters();
  if (!el) { stopHeroBeatLoop(); return; }
  if (!hasGSAP) { startHeroBeatLoop(); return; }

  const letters = el.querySelectorAll('.letter');

  heroMM = gsap.matchMedia();
  heroMM.add({
    motionOk: '(prefers-reduced-motion: no-preference)',
    reduced: '(prefers-reduced-motion: reduce)',
  }, (ctx) => {
    if (ctx.conditions.reduced) return;

    // autoAlpha, not opacity, so an interrupted tween can't leave them
    // invisible but still hit-testable
    gsap.from(letters, {
      autoAlpha: 0, y: 28,
      duration: 0.6, stagger: 0.025, ease: 'power3.out',
    });

    gsap.to(letters, {
      yPercent: -5, scale: 1.03,
      duration: 1.8, ease: 'sine.inOut',
      repeat: -1, yoyo: true,
      stagger: { each: 0.05, from: 'start' },
    });

    // chips have a css transform transition for their hover lift, which
    // would smear the tween, so it's switched off until they've landed
    const extras = document.querySelectorAll('.empty-state .small, .empty-state .chip');
    gsap.set(extras, { transition: 'none' });
    gsap.from(extras, {
      autoAlpha: 0, y: 14,
      duration: 0.5, delay: 0.35, stagger: 0.06, ease: 'power3.out',
      clearProps: 'transform,opacity,visibility,transition',
    });
  });

  startHeroBeatLoop();
}

// one listener on document rather than rebinding on every remount
if (hasGSAP && !reduceMotion) {
  const px = gsap.quickTo('#heroWrap', 'x', { duration: 0.7, ease: 'power3' });
  const py = gsap.quickTo('#heroWrap', 'y', { duration: 0.7, ease: 'power3' });
  document.addEventListener('mousemove', (e) => {
    if (!document.getElementById('heroWrap')) return;
    px((e.clientX / window.innerWidth - 0.5) * 16);
    py((e.clientY / window.innerHeight - 0.5) * 11);
  });
}

export function applyMagnetic(btn, strength = 12) {
  if (!hasGSAP || reduceMotion) return;
  const moveX = gsap.quickTo(btn, 'x', { duration: 0.3, ease: 'power3' });
  const moveY = gsap.quickTo(btn, 'y', { duration: 0.3, ease: 'power3' });
  btn.addEventListener('mousemove', (e) => {
    const r = btn.getBoundingClientRect();
    moveX((e.clientX - (r.left + r.width / 2)) * (strength / 100));
    moveY((e.clientY - (r.top + r.height / 2)) * (strength / 100));
  });
  btn.addEventListener('mouseleave', () => { moveX(0); moveY(0); });
}
/* ---- ui motion ----
   everything below is a no-op (or an instant show/hide) without GSAP or
   with reduced motion on, so callers never have to branch on it */

const anim = hasGSAP && !reduceMotion;
const CLEAR = 'transform,opacity,visibility';
const BOX = 'height,paddingTop,paddingBottom,marginTop,marginBottom,overflow';

// first paint. the sidebar has a css transform transition (mobile drawer),
// so only its children move, a tween on it would fight the transition
export function playIntro() {
  if (!anim) return;
  const sidebarKids = document.querySelectorAll('#sidebar > :not(.conv-list)');
  gsap.timeline({ defaults: { ease: 'power3.out' } })
    .from('#sidebar', { autoAlpha: 0, duration: 0.5, clearProps: 'opacity,visibility' })
    .from(sidebarKids, { x: -14, autoAlpha: 0, duration: 0.45, stagger: 0.05, clearProps: CLEAR }, 0.1)
    .from('.main-header', { y: -10, autoAlpha: 0, duration: 0.5, clearProps: CLEAR }, 0.1)
    .from('.composer', { y: 34, scale: 0.97, autoAlpha: 0, duration: 0.8, ease: 'expo.out', clearProps: CLEAR }, 0.2)
    .from('.hint', { autoAlpha: 0, duration: 0.6, clearProps: 'opacity,visibility' }, 0.55);
}

// stagger a batch in. total spread is capped so a long list doesn't take
// forever to finish arriving
export function staggerIn(els, { y = 10, x = 0, amount = 0.45, each = 0.04, delay = 0 } = {}) {
  if (!anim) return;
  const list = [...els];
  if (!list.length) return;
  gsap.from(list, {
    autoAlpha: 0, y, x, delay,
    duration: 0.42, ease: 'power3.out',
    stagger: Math.min(each, amount / list.length),
    clearProps: CLEAR,
  });
}

export function fadeView(el) {
  if (!anim) return;
  gsap.fromTo(el, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.35, ease: 'power1.out', clearProps: 'opacity,visibility' });
}

// header title etc. blur-in reads as a crossfade without needing two nodes
export function swapText(el) {
  if (!anim) return;
  gsap.fromTo(el,
    { autoAlpha: 0, y: 6, filter: 'blur(4px)' },
    { autoAlpha: 1, y: 0, filter: 'blur(0px)', duration: 0.4, ease: 'power2.out', clearProps: CLEAR + ',filter' });
}

// x goes on .row-inner, not the row. rows are full width and shifting one
// sideways would flash a horizontal scrollbar on .messages
export function enterRow(row, role) {
  if (!anim) return;
  const inner = row.querySelector('.row-inner') || row;
  gsap.from(row, { autoAlpha: 0, duration: 0.45, ease: 'power2.out', clearProps: 'opacity,visibility' });
  gsap.from(inner, {
    y: 18, x: role === 'user' ? 16 : -16, filter: 'blur(6px)',
    duration: 0.55, ease: 'power3.out', clearProps: 'transform,filter',
  });
  const avatar = row.querySelector('.avatar');
  if (avatar) {
    gsap.from(avatar, {
      scale: 0, rotation: role === 'user' ? 30 : -30,
      duration: 0.5, delay: 0.12, ease: 'back.out(2.4)', clearProps: 'transform',
    });
  }
}

// little squash on the composer when a message goes out
export function sendPulse() {
  if (!anim) return;
  gsap.fromTo('.composer', { scale: 0.985 }, { scale: 1, duration: 0.6, ease: 'elastic.out(1, 0.5)', clearProps: 'transform' });
}

/* ---- modals + popovers ----
   the closing flag stops a second close (escape closes all three modals)
   from restarting the exit tween. opening kills the exit tween, so its
   onComplete can't hide a modal that was just reopened */

export function openModal(backdrop) {
  const modal = backdrop.querySelector('.modal');
  delete backdrop.dataset.closing;
  backdrop.hidden = false;
  if (!anim) return;
  gsap.killTweensOf([backdrop, modal]);
  gsap.fromTo(backdrop,
    { autoAlpha: 0, backdropFilter: 'blur(0px)' },
    { autoAlpha: 1, backdropFilter: 'blur(4px)', duration: 0.3, ease: 'power1.out', clearProps: 'opacity,visibility,backdropFilter' });
  gsap.fromTo(modal,
    { autoAlpha: 0, y: 26, scale: 0.94, rotationX: 9, transformPerspective: 900 },
    { autoAlpha: 1, y: 0, scale: 1, rotationX: 0, duration: 0.55, ease: 'back.out(1.35)', clearProps: CLEAR });
}

export function closeModal(backdrop) {
  if (backdrop.hidden || backdrop.dataset.closing) return;
  if (!anim) { backdrop.hidden = true; return; }
  const modal = backdrop.querySelector('.modal');
  backdrop.dataset.closing = '1';
  gsap.killTweensOf([backdrop, modal]);
  gsap.to(modal, { autoAlpha: 0, y: 14, scale: 0.96, duration: 0.18, ease: 'power2.in' });
  gsap.to(backdrop, {
    autoAlpha: 0, duration: 0.24, ease: 'power1.in',
    onComplete: () => {
      backdrop.hidden = true;
      delete backdrop.dataset.closing;
      gsap.set([backdrop, modal], { clearProps: CLEAR });
    },
  });
}

export function popIn(el, origin = 'bottom right') {
  el.hidden = false;
  if (!anim) return;
  gsap.killTweensOf([el, ...el.children]);
  gsap.fromTo(el,
    { autoAlpha: 0, y: 8, scale: 0.94, transformOrigin: origin },
    { autoAlpha: 1, y: 0, scale: 1, duration: 0.3, ease: 'back.out(1.7)', clearProps: CLEAR });
  gsap.from(el.children, { autoAlpha: 0, y: 6, duration: 0.25, delay: 0.05, stagger: 0.04, ease: 'power2.out', clearProps: CLEAR });
}

export function popOut(el) {
  if (el.hidden) return;
  if (!anim) { el.hidden = true; return; }
  gsap.killTweensOf([el, ...el.children]);
  gsap.to(el, {
    autoAlpha: 0, y: 6, scale: 0.96, duration: 0.15, ease: 'power2.in',
    onComplete: () => { el.hidden = true; gsap.set(el, { clearProps: CLEAR }); },
  });
}

/* ---- height ----
   padding goes to 0 with the height, otherwise a border-box element can't
   shrink past its own padding and the collapse stops short */

export function toggleHeight(el, open) {
  if (!anim) { el.hidden = !open; return; }
  gsap.killTweensOf(el);
  if (open) {
    el.hidden = false;
    // a reopen mid-collapse would otherwise measure the half-shut height
    gsap.set(el, { clearProps: BOX + ',opacity' });
    el.style.overflow = 'hidden';
    gsap.from(el, {
      height: 0, paddingTop: 0, paddingBottom: 0, opacity: 0,
      duration: 0.38, ease: 'power3.out', clearProps: BOX + ',opacity',
    });
  } else {
    if (el.hidden) return;
    el.style.overflow = 'hidden';
    gsap.to(el, {
      height: 0, paddingTop: 0, paddingBottom: 0, opacity: 0,
      duration: 0.26, ease: 'power2.inOut',
      onComplete: () => { el.hidden = true; gsap.set(el, { clearProps: BOX + ',opacity' }); },
    });
  }
}

// grow a freshly inserted block open from nothing
export function revealBlock(el) {
  if (!anim) return;
  el.style.overflow = 'hidden';
  gsap.from(el, {
    height: 0, paddingTop: 0, paddingBottom: 0, marginTop: 0, marginBottom: 0, autoAlpha: 0,
    duration: 0.45, ease: 'power3.out', clearProps: BOX + ',opacity,visibility',
  });
}

// slide out then fold the gap shut. resolves when done so the caller can
// remove the node without the list jumping
export function collapseOut(el) {
  if (!anim) return Promise.resolve();
  el.classList.add('leaving');
  el.style.pointerEvents = 'none';
  el.style.overflow = 'hidden';
  return new Promise((resolve) => {
    gsap.timeline({ onComplete: resolve })
      .to(el, { x: -14, autoAlpha: 0, duration: 0.2, ease: 'power2.in' })
      .to(el, { height: 0, paddingTop: 0, paddingBottom: 0, marginTop: 0, marginBottom: 0, duration: 0.24, ease: 'power2.inOut' });
  });
}

/* ---- sidebar ---- */

export function enterListItems(items, delay = 0) {
  if (!anim || !items.length) return;
  gsap.from(items, {
    autoAlpha: 0, x: -12, delay,
    duration: 0.4, ease: 'power3.out',
    stagger: Math.min(0.04, 0.5 / items.length),
    clearProps: CLEAR,
  });
}

// a pill that glides to the active chat. the list is rebuilt on every
// load, so the pill is too, and it starts from wherever the last one was
let indicatorY = null;
export function syncConvIndicator(list) {
  if (!anim) return;
  const ind = document.createElement('div');
  ind.className = 'conv-indicator';
  ind.setAttribute('aria-hidden', 'true');
  list.prepend(ind);
  list.classList.add('has-indicator');

  const active = list.querySelector('.conv-item.active');
  if (!active) { indicatorY = null; gsap.set(ind, { autoAlpha: 0 }); return; }
  const y = active.offsetTop;
  gsap.set(ind, { height: active.offsetHeight });
  if (indicatorY === null) {
    gsap.fromTo(ind, { y, autoAlpha: 0, scaleX: 0.9 }, { autoAlpha: 1, scaleX: 1, duration: 0.35, ease: 'power2.out' });
  } else {
    gsap.fromTo(ind, { y: indicatorY }, { y, duration: 0.45, ease: 'power3.out' });
  }
  indicatorY = y;
}

/* ---- agent panel ---- */

export function enterAgentRow(el) {
  if (!anim) return;
  gsap.from(el, { autoAlpha: 0, x: -8, duration: 0.3, ease: 'power2.out', clearProps: CLEAR });
}

export function popIcon(el) {
  if (!anim || !el) return;
  gsap.from(el, { scale: 0, rotation: -90, duration: 0.45, ease: 'back.out(3)', clearProps: 'transform' });
}

export function shake(el) {
  if (!anim) return;
  gsap.fromTo(el, { x: -5 }, { x: 0, duration: 0.6, ease: 'elastic.out(1, 0.3)', clearProps: 'transform' });
}

/* ---- analytics ---- */

// "1,234" / "98.5%" / "1.23 s": tween the number, keep the suffix, and put
// the exact original text back at the end so rounding can't leave it off
export function countUp(els) {
  if (!anim) return;
  for (const el of els) {
    const text = el.textContent.trim();
    const m = text.match(/^([\d,]*\.?\d+)(.*)$/);
    if (!m) continue;
    const target = parseFloat(m[1].replace(/,/g, ''));
    if (!Number.isFinite(target)) continue;
    const decimals = (m[1].split('.')[1] || '').length;
    const fmt = { minimumFractionDigits: decimals, maximumFractionDigits: decimals };
    const obj = { v: 0 };
    gsap.to(obj, {
      v: target, duration: 1.1, ease: 'power3.out',
      onUpdate: () => { el.textContent = obj.v.toLocaleString(undefined, fmt) + m[2]; },
      onComplete: () => { el.textContent = text; },
    });
  }
}

// scaleX, not width: the widths are inline percentages and a width tween
// would end on a fixed px value that stops tracking the modal size
export function growBars(els) {
  if (!anim) return;
  const list = [...els];
  if (!list.length) return;
  gsap.from(list, {
    scaleX: 0, transformOrigin: 'left center',
    duration: 0.9, ease: 'power3.out', stagger: { amount: 0.4 },
    clearProps: 'transform',
  });
}

/* ---- ambient ---- */

// css-only ripple, so it works without GSAP too
const RIPPLE_HOSTS = '.chip, .new-chat-btn, .docs-btn, .msg-action, .model-save, .source-head, .mode-menu-item, .load-earlier';
export function initRipples() {
  if (reduceMotion) return;
  document.addEventListener('pointerdown', (e) => {
    const host = e.target.closest(RIPPLE_HOSTS);
    if (!host || host.disabled) return;
    const r = host.getBoundingClientRect();
    const size = Math.max(r.width, r.height) * 2;
    const ripple = document.createElement('span');
    ripple.className = 'ripple';
    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = (e.clientX - r.left - size / 2) + 'px';
    ripple.style.top = (e.clientY - r.top - size / 2) + 'px';
    host.appendChild(ripple);
    ripple.addEventListener('animationend', () => ripple.remove());
  });
}

// soft light that follows the cursor across the background. rAF-throttled,
// and skipped on touch where there's no cursor to follow
export function initSpotlight() {
  if (reduceMotion || !window.matchMedia('(pointer: fine)').matches) return;
  const el = document.getElementById('spotlight');
  if (!el) return;
  let raf = null;
  let x = 0;
  let y = 0;
  document.addEventListener('pointermove', (e) => {
    x = e.clientX;
    y = e.clientY;
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = null;
      el.style.setProperty('--mx', x + 'px');
      el.style.setProperty('--my', y + 'px');
      el.classList.add('on');
    });
  });
  document.documentElement.addEventListener('mouseleave', () => el.classList.remove('on'));
}
