const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

function applyTheme() {
  if (!tg) return;
  const root = document.documentElement.style;
  const t = tg.themeParams || {};
  if (t.bg_color) root.setProperty('--bg', t.bg_color);
  if (t.text_color) root.setProperty('--text', t.text_color);
  if (t.hint_color) root.setProperty('--hint', t.hint_color);
  if (t.button_color) root.setProperty('--accent', t.button_color);
  if (t.button_text_color) root.setProperty('--accent-text', t.button_text_color);
  if (t.secondary_bg_color) root.setProperty('--card', t.secondary_bg_color);
}
applyTheme();
tg?.onEvent('themeChanged', applyTheme);

const initData = tg?.initData || '';
const startParam = tg?.initDataUnsafe?.start_param || null;
const myTgId = tg?.initDataUnsafe?.user?.id ?? null;

let META = { bot_username: '', webapp_url: '' };
let DEADLINE_OPTIONS = [];

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: 'tma ' + initData,
      ...(options.headers || {}),
    },
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error((data && data.detail) || `HTTP ${res.status}`);
  return data;
}

const app = document.getElementById('app');

function render(html) {
  app.innerHTML = html;
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s ?? '';
  return d.innerHTML;
}

function showError(err) {
  const msg = String(err.message || err);
  if (tg?.showAlert) tg.showAlert(msg);
  else alert(msg);
}

function setBack(handler) {
  if (!tg?.BackButton) return;
  tg.BackButton.offClick(setBack._last || (() => {}));
  if (handler) {
    setBack._last = handler;
    tg.BackButton.onClick(handler);
    tg.BackButton.show();
  } else {
    tg.BackButton.hide();
  }
}

async function loadMeta() {
  META = await fetch('/api/meta/config').then((r) => r.json());
  DEADLINE_OPTIONS = await api('/api/meta/deadline-options');
}

// ---------- Boot ----------

async function boot() {
  render('<p class="hint">Загрузка…</p>');
  try {
    await loadMeta();
    const me = await api('/api/me');
    if (!me.registered) renderOnboarding();
    else renderMenu(me);
  } catch (err) {
    render(`<p class="error">${escapeHtml(err.message)}</p>`);
  }
}

// ---------- Onboarding ----------

function renderOnboarding() {
  setBack(null);
  const invitedNote = startParam
    ? `<p class="hint">Вас пригласил партнёр (id ${escapeHtml(startParam)}) — вы будете связаны автоматически.</p>`
    : '';
  render(`
    <h2>Добро пожаловать в WishBook 🎁</h2>
    ${invitedNote}
    <form id="reg-form">
      <label>Как вас зовут?</label>
      <input name="name" required maxlength="200" placeholder="Ваше имя" />
      <button type="submit">Продолжить</button>
    </form>
  `);
  document.getElementById('reg-form').onsubmit = async (e) => {
    e.preventDefault();
    const name = new FormData(e.target).get('name').trim();
    if (!name) return;
    try {
      const me = await api('/api/register', {
        method: 'POST',
        body: JSON.stringify({ name, invited_by: startParam ? Number(startParam) : null }),
      });
      renderMenu(me);
    } catch (err) {
      showError(err);
    }
  };
}

// ---------- Menu ----------

function renderMenu(me) {
  setBack(null);
  const partnerLine = me.partner
    ? `💑 Партнёр: <b>${escapeHtml(me.partner.name)}</b>`
    : '👥 Партнёр ещё не подключён';
  render(`
    <h2>Привет, ${escapeHtml(me.name)}!</h2>
    <p class="hint">${partnerLine}</p>
    <div class="menu">
      <button data-go="add">➕ Добавить желание</button>
      <button data-go="mine">📋 Мои желания</button>
      <button data-go="partner">💝 Желания партнёра</button>
      <button data-go="invite" class="secondary">🔗 Пригласить партнёра</button>
    </div>
  `);
  app.querySelector('[data-go="add"]').onclick = () => renderAddWish(me);
  app.querySelector('[data-go="mine"]').onclick = () => renderWishList('mine', me);
  app.querySelector('[data-go="partner"]').onclick = () => renderWishList('partner', me);
  app.querySelector('[data-go="invite"]').onclick = () => renderInvite(me);
}

// ---------- Invite / pair ----------

function renderInvite(me) {
  setBack(() => renderMenu(me));
  const link = myTgId ? `https://t.me/${META.bot_username}?startapp=${myTgId}` : '';
  render(`
    <h2>Пригласить партнёра</h2>
    <p class="hint">Отправьте эту ссылку партнёру — как только он откроет её и зарегистрируется, вы будете связаны.</p>
    <div class="invite-box">${escapeHtml(link)}</div>
    <button id="share-btn">📤 Отправить ссылку</button>
    <p class="hint" style="margin-top:16px">Или партнёр уже пользуется ботом — введите его Telegram ID:</p>
    <form id="pair-form">
      <input name="partner_tg_id" type="number" placeholder="Telegram ID партнёра" required />
      <button type="submit" class="secondary">Связать</button>
    </form>
  `);
  document.getElementById('share-btn').onclick = () => {
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent('Присоединяйся ко мне в WishBook!')}`;
    if (tg?.openTelegramLink) tg.openTelegramLink(shareUrl);
    else window.open(shareUrl, '_blank');
  };
  document.getElementById('pair-form').onsubmit = async (e) => {
    e.preventDefault();
    const partnerTgId = Number(new FormData(e.target).get('partner_tg_id'));
    try {
      const updated = await api('/api/pair', {
        method: 'POST',
        body: JSON.stringify({ partner_tg_id: partnerTgId }),
      });
      renderMenu(updated);
    } catch (err) {
      showError(err);
    }
  };
}

// ---------- Add wish ----------

function renderAddWish(me) {
  setBack(() => renderMenu(me));
  const options = DEADLINE_OPTIONS.map((o) => `<option value="${o.value}">${escapeHtml(o.label)}</option>`).join('');
  render(`
    <h2>Новое желание</h2>
    <form id="add-form">
      <label>Что хотите получить?</label>
      <textarea name="title" required maxlength="2000" rows="3" placeholder="Опишите желание"></textarea>
      <label>Срок</label>
      <select name="deadline">${options}</select>
      <label>Видимость</label>
      <select name="visibility">
        <option value="private">👤 Только для себя</option>
        <option value="shared" ${me.partner ? '' : 'disabled'}>💑 Для партнёра${me.partner ? '' : ' (нет партнёра)'}</option>
      </select>
      <button type="submit">Добавить</button>
    </form>
  `);
  document.getElementById('add-form').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api('/api/wishes', {
        method: 'POST',
        body: JSON.stringify({
          title: fd.get('title').trim(),
          deadline: fd.get('deadline'),
          visibility: fd.get('visibility'),
        }),
      });
      tg?.HapticFeedback?.notificationOccurred('success');
      renderWishList('mine', me);
    } catch (err) {
      showError(err);
    }
  };
}

// ---------- Wish list ----------

async function renderWishList(kind, me) {
  setBack(() => renderMenu(me));
  render('<p class="hint">Загрузка…</p>');
  try {
    const wishes = await api(kind === 'mine' ? '/api/wishes/mine' : '/api/wishes/partner');
    const items = wishes.map((w) => wishCardHtml(w, kind === 'mine')).join('') || '<p class="hint">Пока пусто.</p>';
    render(`
      <h2>${kind === 'mine' ? '📋 Мои желания' : '💝 Желания партнёра'}</h2>
      <div class="wishes">${items}</div>
    `);
    if (kind === 'mine') wireWishActions(me);
  } catch (err) {
    showError(err);
  }
}

function wishCardHtml(w, mine) {
  const status = w.is_completed ? '✅' : w.is_expired ? '⌛' : '🔵';
  const visLabel = w.visibility === 'shared' ? '💑 Общее' : '👤 Личное';
  return `
    <div class="wish-card" data-id="${w.id}">
      <div class="wish-title">${status} ${escapeHtml(w.title)}</div>
      <div class="wish-meta">📅 ${escapeHtml(w.deadline_label)}${mine ? ` · ${visLabel}` : ''}</div>
      ${
        mine
          ? `<div class="wish-actions">
              <button data-act="complete">${w.is_completed ? '↩️' : '✅'}</button>
              <button data-act="visibility">${w.visibility === 'shared' ? '🙈' : '👁'}</button>
              <button data-act="edit">✏️</button>
              <button data-act="delete">🗑</button>
            </div>`
          : ''
      }
    </div>
  `;
}

function wireWishActions(me) {
  app.querySelectorAll('.wish-card').forEach((card) => {
    const id = card.dataset.id;

    card.querySelector('[data-act="complete"]').onclick = () =>
      api(`/api/wishes/${id}/complete`, { method: 'POST' })
        .then(() => renderWishList('mine', me))
        .catch(showError);

    card.querySelector('[data-act="visibility"]').onclick = () =>
      api(`/api/wishes/${id}/visibility`, { method: 'POST' })
        .then(() => renderWishList('mine', me))
        .catch(showError);

    card.querySelector('[data-act="delete"]').onclick = () => {
      const doDelete = () =>
        api(`/api/wishes/${id}`, { method: 'DELETE' })
          .then(() => renderWishList('mine', me))
          .catch(showError);
      if (tg?.showConfirm) tg.showConfirm('Удалить желание?', (ok) => ok && doDelete());
      else if (confirm('Удалить желание?')) doDelete();
    };

    card.querySelector('[data-act="edit"]').onclick = () => {
      const title = card.querySelector('.wish-title').textContent.replace(/^\S+\s/, '');
      renderEditWish(id, title, me);
    };
  });
}

// ---------- Edit wish ----------

function renderEditWish(id, currentTitle, me) {
  setBack(() => renderWishList('mine', me));
  render(`
    <h2>Изменить желание</h2>
    <form id="edit-form">
      <label>Текст</label>
      <textarea name="title" required maxlength="2000" rows="3">${escapeHtml(currentTitle)}</textarea>
      <button type="submit">Сохранить</button>
    </form>
  `);
  document.getElementById('edit-form').onsubmit = async (e) => {
    e.preventDefault();
    const title = new FormData(e.target).get('title').trim();
    if (!title) return;
    try {
      await api(`/api/wishes/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) });
      renderWishList('mine', me);
    } catch (err) {
      showError(err);
    }
  };
}

boot();
