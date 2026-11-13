/*
 * Zoomable camera map for /flock/. Draws vector data stored on this site
 * (flock/data/map.json for the cameras, flock/data/wy-basemap.json for county
 * lines, highways and places). No outside requests: the site's content
 * security policy allows scripts and fetches from 'self' only.
 */
(function () {
  'use strict';
  var root = document.getElementById('wymap');
  if (!root) return;
  var svg = root.querySelector('svg.wymap-svg');
  var countEl = root.querySelector('.wymap-count');
  var statusEl = root.querySelector('.wymap-status');
  var NS = 'http://www.w3.org/2000/svg';

  function getJSON(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok) throw new Error(url + ' returned ' + r.status);
      return r.json();
    });
  }
  function el(name, attrs, parent) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }

  Promise.all([getJSON(root.getAttribute('data-map')), getJSON(root.getAttribute('data-base')).catch(function () { return null; })])
    .then(function (res) { start(res[0], res[1]); })
    .catch(function (e) { statusEl.textContent = 'The interactive map could not load (' + e.message + ').'; });

  function start(data, base) {
    var B = data.views.state;                       // [south, west, north, east]
    var K = Math.cos(((B[0] + B[2]) / 2) * Math.PI / 180);
    var SC = 100;
    var X = function (lon) { return (lon - B[1]) * K * SC; };
    var Y = function (lat) { return (B[2] - lat) * SC; };
    var WW = X(B[3]), WH = Y(B[0]);                 // world size in user units
    var vb = { x: 0, y: 0, w: WW };
    statusEl.textContent = '';

    // ---- static geometry, one path per layer
    function pathOf(lines) {
      var d = [];
      for (var i = 0; i < lines.length; i++) {
        var pts = lines[i].pts || lines[i];
        if (!pts || pts.length < 2) continue;
        var s = 'M' + X(pts[0][1]).toFixed(2) + ',' + Y(pts[0][0]).toFixed(2);
        for (var j = 1; j < pts.length; j++) s += 'L' + X(pts[j][1]).toFixed(2) + ',' + Y(pts[j][0]).toFixed(2);
        d.push(s);
      }
      return d.join('');
    }
    el('rect', { class: 'wm-state', x: 0, y: 0, width: WW, height: WH }, svg);
    var layers = {};
    if (base) {
      [['boundary', 'wm-county'], ['roads_major', 'wm-major'], ['roads_primary', 'wm-primary'], ['roads_detail', 'wm-detail']].forEach(function (L) {
        if (base[L[0]] && base[L[0]].length) layers[L[0]] = el('path', { class: L[1], d: pathOf(base[L[0]]) }, svg);
      });
    }
    var placeG = el('g', { class: 'wm-places' }, svg);
    var camG = el('g', { class: 'wm-cams' }, svg);

    // ---- places
    var rank = { city: 4, town: 3, village: 2, hamlet: 1, suburb: 1 };
    var minZ = { city: 0, town: 1.6, village: 3.5, hamlet: 8, suburb: 8 };
    var places = ((base && base.places) || []).map(function (p) {
      var g = el('g', { style: 'display:none' }, placeG);
      el('circle', { class: 'wm-pdot', r: 2 }, g);
      var t = el('text', { class: 'wm-ptext' + (p.type === 'city' ? ' big' : '') }, g);
      t.textContent = p.name;
      return { g: g, dot: g.firstChild, t: t, x: X(p.lon), y: Y(p.lat), name: p.name, type: p.type, pri: (rank[p.type] || 0) * 1e7 + (p.pop || 0) };
    }).sort(function (a, b) { return b.pri - a.pri; });

    // ---- cameras: [id, lat, lon, flags]; flags 1 = Cheyenne area, 2 = newly mapped
    var cams = data.cameras.map(function (c) {
      var a = el('a', { href: 'https://www.openstreetmap.org/node/' + c[0], target: '_blank', rel: 'noopener noreferrer' }, camG);
      var ring = (c[3] & 2) ? el('circle', { class: 'wm-new', cx: X(c[2]).toFixed(2), cy: Y(c[1]).toFixed(2) }, a) : null;
      var dot = el('circle', { class: 'wm-cam' + ((c[3] & 1) ? ' city' : ''), cx: X(c[2]).toFixed(2), cy: Y(c[1]).toFixed(2) }, a);
      el('title', {}, dot).textContent = 'Flock camera, OpenStreetMap node ' + c[0] + ' (' + c[1].toFixed(4) + ', ' + c[2].toFixed(4) + ')';
      return { dot: dot, ring: ring, x: X(c[2]), y: Y(c[1]) };
    });

    // ---- view handling
    function box() { return svg.getBoundingClientRect(); }
    function clamp() {
      var r = box(); var ratio = r.height / r.width;
      var maxW = Math.max(WW, WH / ratio) * 1.25;   // far enough out to fit the whole state in any viewport shape
      vb.w = Math.min(Math.max(vb.w, WW / 400), maxW);
      var h = vb.w * ratio;
      vb.x = Math.min(Math.max(vb.x, -vb.w * 0.5), WW - vb.w * 0.5);
      vb.y = Math.min(Math.max(vb.y, -h * 0.5), WH - h * 0.5);
    }
    var raf = 0;
    function apply() {
      var r = box(); if (!r.width) return;
      clamp();
      svg.setAttribute('viewBox', vb.x + ' ' + vb.y + ' ' + vb.w + ' ' + (vb.w * r.height / r.width));
      if (!raf) raf = requestAnimationFrame(function () { raf = 0; refresh(); });
    }
    function fit(bb) {   // bb = [south, west, north, east]
      var r = box(); if (!r.width) return;
      var x0 = X(bb[1]), x1 = X(bb[3]), y0 = Y(bb[2]), y1 = Y(bb[0]);
      var w = (x1 - x0) * 1.12, h = (y1 - y0) * 1.12, ratio = r.height / r.width;
      vb.w = Math.max(w, h / ratio);
      vb.x = (x0 + x1) / 2 - vb.w / 2;
      vb.y = (y0 + y1) / 2 - (vb.w * ratio) / 2;
      apply();
    }
    function zoomAt(factor, px, py) {   // px, py = fraction of the viewport (0..1)
      var r = box(); var h = vb.w * r.height / r.width;
      var wx = vb.x + px * vb.w, wy = vb.y + py * h;
      vb.w = vb.w * factor; clamp();
      var h2 = vb.w * r.height / r.width;
      vb.x = wx - px * vb.w; vb.y = wy - py * h2;
      apply();
    }

    function refresh() {
      var r = box(); if (!r.width) return;
      var u = vb.w / r.width, z = WW / vb.w, h = vb.w * r.height / r.width;
      svg.style.setProperty('--u', u);
      if (layers.roads_primary) layers.roads_primary.style.display = z >= 2.2 ? '' : 'none';
      if (layers.roads_detail) layers.roads_detail.style.display = z >= 12 ? '' : 'none';
      var rad = (z >= 12 ? 5 : z >= 4 ? 4 : 3) * u;
      var inView = 0;
      for (var i = 0; i < cams.length; i++) {
        var c = cams[i];
        c.dot.setAttribute('r', rad);
        if (c.ring) c.ring.setAttribute('r', rad * 1.9);
        if (c.x >= vb.x && c.x <= vb.x + vb.w && c.y >= vb.y && c.y <= vb.y + h) inView++;
      }
      countEl.textContent = inView + ' of ' + cams.length + ' cameras in view';
      var placed = [];
      for (var k = 0; k < places.length; k++) {
        var p = places[k], show = false;
        if (z >= (minZ[p.type] || 0) && p.x >= vb.x - 20 * u && p.x <= vb.x + vb.w + 20 * u && p.y >= vb.y && p.y <= vb.y + h) {
          var sx = (p.x - vb.x) / u, sy = (p.y - vb.y) / u, wpx = p.name.length * 6.4 + 12;
          var flip = sx + wpx > r.width;           // would run off the right edge: put the name left of the dot
          var b = flip ? [sx - wpx, sy - 15, sx, sy + 4] : [sx, sy - 15, sx + wpx, sy + 4];
          show = true;
          for (var m = 0; m < placed.length; m++) {
            var o = placed[m];
            if (!(b[2] < o[0] || b[0] > o[2] || b[3] < o[1] || b[1] > o[3])) { show = false; break; }
          }
          if (show) {
            placed.push(b);
            p.dot.setAttribute('cx', p.x); p.dot.setAttribute('cy', p.y); p.dot.setAttribute('r', 2 * u);
            p.t.setAttribute('x', p.x + (flip ? -5 : 5) * u); p.t.setAttribute('y', p.y - 4 * u); p.t.setAttribute('text-anchor', flip ? 'end' : 'start');
          }
        }
        p.g.style.display = show ? '' : 'none';
      }
    }

    // ---- input: drag, wheel, pinch, buttons, keyboard
    var ptrs = {}, drag = null, pinch = null, moved = false;
    svg.addEventListener('pointerdown', function (e) {
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
      var ids = Object.keys(ptrs);
      moved = false;
      if (ids.length === 1) drag = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y };
      if (ids.length === 2) {
        var a = ptrs[ids[0]], b = ptrs[ids[1]];
        pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), w: vb.w }; drag = null;
      }
    });
    window.addEventListener('pointermove', function (e) {
      if (!ptrs[e.pointerId]) return;
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
      var r = box(), ids = Object.keys(ptrs);
      if (ids.length === 1 && drag) {
        var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
        vb.x = drag.vx - dx * vb.w / r.width; vb.y = drag.vy - dy * vb.w / r.width;
        apply();
      } else if (ids.length === 2 && pinch) {
        var a = ptrs[ids[0]], b = ptrs[ids[1]], d = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch.d > 0) {
          var cx = ((a.x + b.x) / 2 - r.left) / r.width, cy = ((a.y + b.y) / 2 - r.top) / r.height;
          zoomAt((pinch.w / (d / pinch.d)) / vb.w, cx, cy);
        }
        moved = true;
      }
    });
    function end(e) {
      delete ptrs[e.pointerId];
      var ids = Object.keys(ptrs);
      if (ids.length === 0) { drag = null; pinch = null; }
      if (ids.length === 1) { var p = ptrs[ids[0]]; drag = { x: p.x, y: p.y, vx: vb.x, vy: vb.y }; pinch = null; }
    }
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
    svg.addEventListener('click', function (e) { if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; } }, true);
    svg.addEventListener('wheel', function (e) {
      e.preventDefault();
      var r = box();
      zoomAt(Math.exp(e.deltaY * 0.0015), (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
    }, { passive: false });
    svg.addEventListener('keydown', function (e) {
      var h = vb.w * box().height / box().width, step = 0.15;
      if (e.key === '+' || e.key === '=') zoomAt(0.7, 0.5, 0.5);
      else if (e.key === '-' || e.key === '_') zoomAt(1.4, 0.5, 0.5);
      else if (e.key === 'ArrowLeft') { vb.x -= vb.w * step; apply(); }
      else if (e.key === 'ArrowRight') { vb.x += vb.w * step; apply(); }
      else if (e.key === 'ArrowUp') { vb.y -= h * step; apply(); }
      else if (e.key === 'ArrowDown') { vb.y += h * step; apply(); }
      else return;
      e.preventDefault();
    });
    root.querySelectorAll('[data-view]').forEach(function (b) {
      b.addEventListener('click', function () { var v = data.views[b.getAttribute('data-view')]; if (v) fit(v); });
    });
    root.querySelectorAll('[data-zoom]').forEach(function (b) {
      b.addEventListener('click', function () { zoomAt(parseFloat(b.getAttribute('data-zoom')), 0.5, 0.5); });
    });
    window.addEventListener('resize', apply);
    fit(B);
  }
})();
