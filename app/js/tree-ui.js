/* Хроника рода · род · управление.
 *
 * Зум и панорама полотна, поиск, свёртывание, шторка человека.
 * Зависит: core, model, tree.
 * Классический скрипт без сборки: порядок подключения задан в index.html.
 */
'use strict';
/* ---------- дерево: зум и панорама ---------- */

function setupTree(canvas) {
  const svg = canvas.querySelector('svg.tree');
  const viewport = el('treeViewport');
  if (!svg || !viewport) return;
  const W = Number(svg.dataset.w) || 1200;
  const H = Number(svg.dataset.h) || 600;

  const apply = () => {
    // Трансформируем не слой CSS, а группу внутри SVG — текст остаётся вектором.
    viewport.setAttribute('transform', `translate(${state.tree.x} ${state.tree.y}) scale(${state.tree.scale})`);
  };

  const fit = () => {
    const box = canvas.getBoundingClientRect();
    const scale = Math.min((box.width - 40) / W, (box.height - 40) / H, 1.3);
    state.tree.scale = Math.max(0.12, scale);
    state.tree.x = (box.width - W * state.tree.scale) / 2;
    state.tree.y = Math.max(12, (box.height - H * state.tree.scale) / 2);
    apply();
  };

  const centerOn = (id) => {
    const g = svg.querySelector(`[data-person="${id}"] rect`);
    if (!g) return;
    const box = canvas.getBoundingClientRect();
    const x = Number(g.getAttribute('x')) + Number(g.getAttribute('width')) / 2;
    const y = Number(g.getAttribute('y')) + Number(g.getAttribute('height')) / 2;
    state.tree.scale = Math.max(state.tree.scale, 0.75);
    state.tree.x = box.width / 2 - x * state.tree.scale;
    state.tree.y = box.height / 2 - y * state.tree.scale;
    apply();
  };

  const zoom = (factor, cx, cy) => {
    const box = canvas.getBoundingClientRect();
    const px = cx ?? box.width / 2;
    const py = cy ?? box.height / 2;
    const next = Math.min(3, Math.max(0.15, state.tree.scale * factor));
    const k = next / state.tree.scale;
    state.tree.x = px - (px - state.tree.x) * k;
    state.tree.y = py - (py - state.tree.y) * k;
    state.tree.scale = next;
    apply();
  };

  const jump = state.tree.jumpTo;
  state.tree.jumpTo = null;
  if (jump) {
    state.tree.scale = Math.max(state.tree.scale, 0.55);
    seekTo(jump);
  }
  const startId = state.world.meta?.player?.id;
  if (!jump && startId && state.tree.focus == null) {
    state.tree.scale = 0.72;
    centerOn(startId);
  } else {
    fit();
  }

  el('zoomIn')?.addEventListener('click', () => zoom(1.25));
  el('zoomOut')?.addEventListener('click', () => zoom(0.8));
  el('zoomFit')?.addEventListener('click', () => { state.tree.focus = null; paintFocus(); fit(); });

  const paintFocus = () => {
    const focus = state.tree.focus ? ancestorsAndDescendants(state.tree.focus) : null;
    for (const node of svg.querySelectorAll('.node')) {
      const id = Number(node.dataset.person);
      node.classList.toggle('is-dim', Boolean(focus) && !focus.has(id));
      node.classList.toggle('is-focus', id === state.tree.focus);
    }
    const hint = el('treeFocusHint');
    if (hint) {
      hint.hidden = !state.tree.focus;
      if (state.tree.focus) {
        const person = ix.people.get(state.tree.focus);
        hint.textContent = `Родня: ${nameOf(person)} — родители и потомки.`;
      }
    }
  };

  canvas.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    const box = canvas.getBoundingClientRect();
    zoom(ev.deltaY > 0 ? 0.9 : 1.1, ev.clientX - box.left, ev.clientY - box.top);
  }, { passive: false });

  let drag = null;
  let moved = false;
  let pressedNode = null;
  canvas.addEventListener('pointerdown', (ev) => {
    if (ev.target.closest('.drawer')) return;
    moved = false;
    // Запоминаем узел под курсором: захват указателя перенаправит click на холст,
    // и тогда ev.target уже не будет узлом.
    pressedNode = ev.target.closest('[data-person]');
    drag = { x: ev.clientX - state.tree.x, y: ev.clientY - state.tree.y, sx: ev.clientX, sy: ev.clientY };
    if (canvas.setPointerCapture) canvas.setPointerCapture(ev.pointerId);
    canvas.classList.add('is-panning');
  });
  canvas.addEventListener('pointermove', (ev) => {
    if (!drag) return;
    // Панорама начинается только после заметного сдвига, иначе дрогнувшая мышь «съедала» клик.
    if (!moved && Math.abs(ev.clientX - drag.sx) + Math.abs(ev.clientY - drag.sy) <= 5) return;
    moved = true;
    state.tree.x = ev.clientX - drag.x;
    state.tree.y = ev.clientY - drag.y;
    apply();
  });
  canvas.addEventListener('pointerup', () => {
    const node = pressedNode;
    pressedNode = null;
    drag = null;
    canvas.classList.remove('is-panning');
    // Открываем человека прямо здесь: click после захвата указателя может не дойти.
    if (!moved && node) open(node);
  });
  canvas.addEventListener('pointercancel', () => { drag = null; pressedNode = null; canvas.classList.remove('is-panning'); });

  const open = (node) => {
    if (!node) return;
    state.personId = Number(node.dataset.person);
    const drawer = el('drawer');
    const person = ix.people.get(state.personId);
    drawer.innerHTML = personCard(person) + `
        <div class="drawer__actions">
          <button class="btn btn--ghost btn--small" type="button" id="focusKin">Показать родню</button>
        </div>`;
    drawer.hidden = false;
    drawer.querySelector('#closeDrawer')?.addEventListener('click', () => { drawer.hidden = true; });
    drawer.querySelector('#focusKin')?.addEventListener('click', () => {
      state.tree.focus = state.tree.focus === state.personId ? null : state.personId;
      paintFocus();
      if (state.tree.focus) centerOn(state.tree.focus);
    });
    for (const other of svg.querySelectorAll('.node')) other.classList.toggle('is-selected', other === node);
  };

  svg.addEventListener('click', (ev) => {
    // Мышь уже обработана на pointerup; сюда приходят только программные клики и клавиатура.
    if (moved) return;
    const node = ev.target.closest('[data-person]');
    if (node && !node.classList.contains('is-selected')) open(node);
  });
  svg.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    const node = ev.target.closest('[data-person]');
    if (!node) return;
    ev.preventDefault();
    open(node);
  });

  const search = el('treeSearch');
  const highlight = () => {
    const q = state.tree.query.trim().toLowerCase();
    for (const node of svg.querySelectorAll('.node')) {
      const match = q && (node.dataset.name || '').includes(q);
      node.classList.toggle('is-match', Boolean(match));
    }
    const hits = q ? [...svg.querySelectorAll('.node.is-match')] : [];
    const info = el('treeSearchHint');
    if (info) {
      info.hidden = !q;
      info.textContent = q ? `Найдено: ${hits.length}` : '';
    }
    if (hits.length) {
      const first = hits[0];
      centerOn(Number(first.dataset.person));
    }
    return hits.length;
  };
  // Поиск ищет по всему роду: если имя в другой линии, переключаемся на неё.
  const findElsewhere = () => {
    const q = state.tree.query.trim().toLowerCase();
    if (q.length < 2) return null;
    return (state.world.people || []).find(
      (p) => p.line != null && nameOf(p).toLowerCase().includes(q) && p.line !== state.tree.line
    );
  };
  search?.addEventListener('input', () => {
    state.tree.query = search.value;
    const hits = highlight();
    if (!hits && findElsewhere()) {
      const found = findElsewhere();
      state.tree.line = found.line;
      render();
      return;
    }
    if (!hits) {
      const info = el('treeSearchHint');
      if (info && state.tree.query.trim().length >= 2) {
        info.hidden = false;
        info.textContent = 'В этой линии такого имени нет';
      }
    }
  });
  if (state.tree.query) highlight();

}
// Навести взгляд на человека: полотно одно, поэтому «переход к линии» — это центрирование.
function seekTo(personId) {
  const canvas = el('treeCanvas');
  if (!canvas) return;
  const svg = canvas.querySelector('svg.tree');
  const viewport = el('treeViewport');
  if (!svg || !viewport) return;
  const rect = svg.querySelector(`[data-person="${personId}"] rect`);
  if (!rect) return;
  const box = canvas.getBoundingClientRect();
  const cx = Number(rect.getAttribute('x')) + Number(rect.getAttribute('width')) / 2;
  const cy = Number(rect.getAttribute('y')) + Number(rect.getAttribute('height')) / 2;
  const scale = Math.max(state.tree.scale, 0.55);
  state.tree.scale = scale;
  state.tree.x = box.width / 2 - cx * scale;
  state.tree.y = box.height / 2 - cy * scale;
  viewport.setAttribute('transform', `translate(${state.tree.x} ${state.tree.y}) scale(${scale})`);
}
function expandAncestors(personId) {
  const open = openSet();
  let cursor = personId;
  const guard = new Set();
  while (cursor && !guard.has(cursor)) {
    guard.add(cursor);
    const person = ix.people.get(cursor);
    if (!person) break;
    if (person.blood) open.add(person.blood);
    cursor = person.blood;
  }
  return open;
}
function setupOutline(root) {
  root.addEventListener('click', (ev) => {
    const toggle = ev.target.closest('[data-toggle]');
    if (toggle) {
      const id = Number(toggle.dataset.toggle);
      const open = openSet();
      if (open.has(id)) open.delete(id);
      else open.add(id);
      const top = window.scrollY || 0;
      render();
      try { window.scrollTo(0, top); } catch { /* jsdom */ }
      return;
    }

    const nameButton = ev.target.closest('.kin-name');
    if (!nameButton) return;
    const item = nameButton.closest('.kin-item');
    const existing = item.querySelector(':scope > .gen-card');
    if (existing) {
      existing.remove();
      return;
    }
    for (const card of root.querySelectorAll('.gen-card')) card.remove();
    state.personId = Number(nameButton.dataset.person);
    const card = document.createElement('div');
    card.className = 'gen-card';
    card.innerHTML = personCard(ix.people.get(state.personId));
    item.appendChild(card);
  });
}
function setupTreeToolbar() {
  for (const chip of document.querySelectorAll('.line-chip[data-line]')) {
    chip.addEventListener('click', () => {
      const id = Number(chip.dataset.line);
      state.tree.activeLine = id;
      state.tree.focus = null;
      const line = lineById(id);
      state.tree.jumpTo = line ? line.founderId : null;
      for (const other of document.querySelectorAll('.line-chip[data-line]')) {
        const on = Number(other.dataset.line) === id;
        other.classList.toggle('is-on', on);
        other.setAttribute('aria-pressed', String(on));
      }
      if (state.tree.jumpTo) seekTo(state.tree.jumpTo);
    });
  }

  el('treeMode')?.addEventListener('click', () => {
    state.tree.mode = (state.tree.mode || 'outline') === 'outline' ? 'canvas' : 'outline';
    render();
  });

  el('treeExpand')?.addEventListener('click', () => {
    state.tree.open = new Set(treePeople().map((p) => p.id));
    render();
  });

  el('treeCollapse')?.addEventListener('click', () => {
    state.tree.open = defaultOpen(treePeople());
    render();
  });

  const outlineRoot = el('outlineRoot');
  const outlineSearch = el('treeSearch');
  if (outlineRoot && outlineSearch) {
    outlineSearch.addEventListener('input', () => {
      state.tree.query = outlineSearch.value;
      const q = outlineSearch.value.trim().toLowerCase();
      let found = 0;
      if (q) {
        for (const person of treePeople()) {
          if (!nameOf(person).toLowerCase().includes(q)) continue;
          expandAncestors(person.id);
          found += 1;
        }
      }
      const top = window.scrollY || 0;
      render();
      try { window.scrollTo(0, q ? 0 : top); } catch { /* jsdom */ }
      const first = document.querySelector('.kin-row.is-match');
      if (first && first.scrollIntoView) {
        try { first.scrollIntoView({ block: 'center' }); } catch { /* jsdom */ }
      }
      const hint = el('treeSearchHint');
      if (hint) {
        hint.hidden = !q;
        hint.textContent = q ? `Найдено: ${found}` : '';
      }
    });
  }

  el('treeList')?.addEventListener('click', () => {
    state.tree.list = !state.tree.list;
    state.tree.focus = null;
    render();
  });

  el('treeKin')?.addEventListener('change', (ev) => {
    state.tree.kinOnly = ev.target.checked;
    state.tree.focus = null;
    render();
  });

  // В списке поиск не подсвечивает узлы, а отбирает строки.
  const search = el('treeSearch');
  const listRoot = el('treeListRoot');
  if (search && listRoot) {
    search.addEventListener('input', () => {
      state.tree.query = search.value;
      const q = search.value.trim().toLowerCase();
      let shown = 0;
      for (const block of listRoot.querySelectorAll('.gen-block')) {
        let visibleInBlock = 0;
        for (const item of block.querySelectorAll('li')) {
          const name = (item.textContent || '').toLowerCase();
          const visible = !q || name.includes(q);
          item.hidden = !visible;
          if (visible) visibleInBlock += 1;
        }
        block.hidden = visibleInBlock === 0;
        shown += visibleInBlock;
      }
      const hint = el('treeSearchHint');
      if (hint) {
        hint.hidden = !q;
        hint.textContent = q ? `Найдено: ${shown}` : '';
      }
    });
  }
}
function setupTreeList(root) {
  root.addEventListener('click', (ev) => {
    const button = ev.target.closest('[data-person]');
    if (!button) return;
    const item = button.closest('li');
    const already = item.querySelector('.gen-card');
    if (already) {
      already.remove();
      return;
    }
    for (const open of root.querySelectorAll('.gen-card')) open.remove();
    state.personId = Number(button.dataset.person);
    const card = document.createElement('div');
    card.className = 'gen-card';
    card.innerHTML = personCard(ix.people.get(state.personId));
    item.appendChild(card);
  });
}
