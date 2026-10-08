(() => {
  /*
   * Gráficas SVG reutilizables (torta y barras + tendencia).
   * Paleta alineada a styles.css (--color-primary, --accent, semánticos).
   */
  const PALETTE = ['#0074D9', '#005BB5', '#FF851B', '#10B981', '#7C3AED', '#EF4444', '#0EA5E9'];

  function colorFor(label, idx, explicit) {
    if (explicit) return explicit;
    const k = String(label || '').toLowerCase();
    if (/ge\s*[≥>=]+\s*19/.test(k) || /≥\s*19/.test(k)) return '#9F1239';
    if (/15\s*[≤<=].*19/.test(k)) return '#EA580C';
    if (/12\s*[≤<=].*15/.test(k)) return '#CA8A04';
    if (/ge\s*<\s*12/.test(k)) return '#0F766E';
    if (/(alto|alta|rojo|insuf|no cumple|crític)/.test(k) && !/ge/.test(k)) return '#EF4444';
    if (/(medio|amarillo|alerta|pendiente)/.test(k)) return '#FF851B';
    if (/(bajo|baja|verde|suficiente|aprob|cumple)/.test(k) && !/no cumple/.test(k)) return '#10B981';
    return PALETTE[idx % PALETTE.length];
  }

  function esc(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function polar(cx, cy, r, angleDeg) {
    const a = ((angleDeg - 90) * Math.PI) / 180;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  }

  function slicePath(cx, cy, r, startDeg, endDeg) {
    const [x0, y0] = polar(cx, cy, r, startDeg);
    const [x1, y1] = polar(cx, cy, r, endDeg);
    const large = endDeg - startDeg > 180 ? 1 : 0;
    return `M ${cx} ${cy} L ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
  }

  function pie(title, items) {
    const rows = (items || []).filter((i) => Number(i.value) > 0);
    const total = rows.reduce((s, i) => s + Number(i.value), 0);
    const cx = 100;
    const cy = 100;
    const r = 88;
    let acc = 0;
    const paths =
      rows.length === 1 && total
        ? `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${colorFor(rows[0].label, 0, rows[0].color)}"></circle>`
        : rows
            .map((item, idx) => {
              const v = Number(item.value) || 0;
              const start = total ? (acc / total) * 360 : 0;
              acc += v;
              const end = total ? (acc / total) * 360 : 0;
              const sweep = Math.max(end - start, total ? 0.4 : 0);
              return `<path d="${slicePath(cx, cy, r, start, start + sweep)}" fill="${colorFor(item.label, idx, item.color)}"></path>`;
            })
            .join('');
    const legend = rows
      .map((item, idx) => {
        const v = Number(item.value) || 0;
        const pct = total ? Math.round((v / total) * 100) : 0;
        return `<li><span class="sigtb-swatch" style="background:${colorFor(item.label, idx, item.color)}"></span>${esc(item.label)} <em>${esc(item.display ?? v)} (${pct}%)</em></li>`;
      })
      .join('');
    return `<div class="pm-chart sigtb-chart">
      <div class="pm-chart__title">${esc(title)}</div>
      <div class="sigtb-pie">
        <svg viewBox="0 0 200 200" width="168" height="168" role="img" aria-label="${esc(title)}">${paths || `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#E5E7EB"></circle>`}</svg>
        <ul class="sigtb-legend">${legend || '<li>Sin datos</li>'}</ul>
      </div>
    </div>`;
  }

  function linearTrend(values) {
    const n = values.length;
    if (n < 2) return values.map((v) => Number(v) || 0);
    let sumX = 0;
    let sumY = 0;
    let sumXY = 0;
    let sumX2 = 0;
    values.forEach((y, x) => {
      const yy = Number(y) || 0;
      sumX += x;
      sumY += yy;
      sumXY += x * yy;
      sumX2 += x * x;
    });
    const den = n * sumX2 - sumX * sumX;
    const slope = den ? (n * sumXY - sumX * sumY) / den : 0;
    const intercept = (sumY - slope * sumX) / n;
    return values.map((_, x) => intercept + slope * x);
  }

  function barTrend(title, items) {
    const rows = (items || []).slice(0, 12);
    const vals = rows.map((i) => Number(i.value) || 0);
    const max = Math.max(1, ...vals);
    const n = rows.length;
    const showTrend = n >= 5;
    const showValues = n > 0 && n <= 8;
    const w = 360;
    const padL = 28;
    const padR = 12;
    const padT = showValues ? 22 : 12;
    const padB = 16;
    const h = 168;
    const innerW = w - padL - padR;
    const innerH = h - padT - padB;
    const gap = n <= 4 ? 20 : 10;
    const barW = n
      ? Math.min(36, Math.max(14, (innerW - gap * (n + 1)) / n))
      : 20;
    const groupW = n * barW + (n + 1) * gap;
    const originX = padL + Math.max(0, (innerW - groupW) / 2);
    const bars = rows
      .map((item, i) => {
        const v = vals[i];
        const bh = Math.max(v > 0 ? 4 : 0, (v / max) * innerH);
        const x = originX + gap + i * (barW + gap);
        const y = padT + innerH - bh;
        const fill = colorFor(item.label, i, item.color);
        const cx = x + barW / 2;
        const label = String(item.display ?? v).replace(/\s*h$/i, '');
        const valueText =
          showValues && v > 0
            ? `<text class="sigtb-bar-value" x="${cx.toFixed(1)}" y="${Math.max(11, y - 5).toFixed(1)}" text-anchor="middle">${esc(label)}</text>`
            : '';
        return `<rect class="sigtb-bar" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(bh, 1).toFixed(1)}" rx="4" fill="${fill}"></rect>${valueText}`;
      })
      .join('');
    const trend = showTrend ? linearTrend(vals) : [];
    const pts = trend
      .map((v, i) => {
        const x = originX + gap + i * (barW + gap) + barW / 2;
        const y = padT + innerH - (v / max) * innerH;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
    const legend = rows
      .map(
        (item, i) =>
          `<li><span class="sigtb-swatch" style="background:${colorFor(item.label, i, item.color)}"></span><span class="sigtb-legend__text">${esc(item.label)}</span><em>${esc(item.display ?? vals[i])}</em></li>`
      )
      .join('');
    return `<div class="pm-chart sigtb-chart sigtb-chart--bar">
      <div class="pm-chart__title">${esc(title)}</div>
      <svg class="sigtb-bar-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(title)}">
        <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + innerH}" stroke="#D1D5DB"></line>
        <line x1="${padL}" y1="${padT + innerH}" x2="${w - padR}" y2="${padT + innerH}" stroke="#D1D5DB"></line>
        ${bars}
        ${pts ? `<polyline class="sigtb-trend" fill="none" stroke="#6B7280" stroke-width="1.2" stroke-dasharray="4 3" points="${pts}"></polyline>` : ''}
      </svg>
      <ul class="sigtb-legend sigtb-legend--compact">${legend || '<li>Sin datos</li>'}</ul>
    </div>`;
  }

  function pair(pieTitle, pieItems, barTitle, barItems) {
    return `<div class="pm-charts">${pie(pieTitle, pieItems)}${barTrend(barTitle, barItems)}</div>`;
  }

  window.AtlasOps = Object.assign(window.AtlasOps || {}, {
    charts: { pie, barTrend, pair, PALETTE },
  });
})();
