/*
 * www.lifeinvader.com — perfil, muro, amigos y acosados, como los arma el juego.
 *
 * Port de appinternet.sc func_8378..func_8423 (docs/gta-v.md): en el juego la web sólo
 * trae el marco; el script elige qué perfil se ve (iLocal_44), en qué pestaña (iLocal_46)
 * y rellena los slots:
 *   slot 0      cabecera (func_8416): nombre, foto grande (LARGE_n), ocupación (_OC),
 *               situación sentimental (_RP), las tres miniaturas MED_n de Fotos / Amigos /
 *               Acosando, el botón de volver al perfil propio y qué pestañas se pueden pulsar
 *   slot 4      título de la columna (func_8415): LFI_MSGHEADER / LFI_FRIENDHEAD / LFI_STLKHEADER, o
 *               LFI_PRIV1 / LFI_NOT_STLK
 *   slot 5...   muro (func_8400 -> func_8405): una fila [1, autor, LFI_POSTEDUPDATE,
 *               texto LFI_<M|F|T><bloque>_<n>, foto SMALL_n del autor, clicable]
 *               amigos (func_8397) y acosados (func_8395): filas [2, nombre, '', foto, clicable]
 *   detrás      barra lateral (func_8380): Family / Friends / Stalking con un destacado y
 *               el total (en las páginas de empresa, un número fijo de amigos y los destacados)
 * Las fotos son fotogramas SMALL_n/MED_n/LARGE_n del propio SWF de la web (texturas lfi_*).
 * Clics (func_8597/func_8598 con GET_CURRENT_SELECTION): 0 volver al perfil propio, 2 amigos,
 * 3 acosando, >= 4 la persona o empresa de esa fila (iLocal_48[fila]).
 *
 * Textos: los tres bloques del juego (lfi_m/lfi_f/lfi_t.gxt2) van dentro de este archivo
 * (D.text.M/F/T) y los pocos de global.gxt2 que no están en strings.json en D.text.G. Como
 * en el juego (func_8378 pide LFI_M, LFI_F o LFI_T según el personaje), sólo se usa el
 * bloque del personaje: cada uno tiene su propia red (Michael: su familia, Lester, Kyle...;
 * Franklin: Lamar, Tanisha, Devin, las empresas...; Trevor: Ron, Wade, Ludendorff).
 *
 * Personaje: ?char=michael|franklin|trevor (también m/f/t o 0/1/2); si no, el del host,
 * que en /v/ sale de ?personaje= (cambia además la piel del teléfono); por defecto Michael.
 *
 * PARTIDA ELEGIDA (en el juego sale de la partida guardada):
 *   * Historia terminada. El muro de cada perfil pone las publicaciones de cada misión en
 *     el orden en que se terminaron, de la más reciente a la más antigua (func_8400 recorre
 *     Global_114135.f_9089.f_330[m].f_3 y f_18578[r].f_3). Orden usado: D.order, el
 *     habitual de la historia con las misiones de personajes aleatorios detrás de la que
 *     las desbloquea (v/scriptdata/lifeinvader.py).
 *   * Bifurcaciones: joyería con los preparativos A, puerto con el minisubmarino (A),
 *     asalto al FIB con bomberos (3A), golpe final sutil (2A) y final C (C1/C2,
 *     no muere ninguno de los tres). Las dos rutas de cada golpe tienen las mismas
 *     publicaciones, así que la elección no cambia lo que se ve.
 *   * Todas las misiones de personajes aleatorios terminadas: por eso el perfil de Dom
 *     es visible (Extreme 1), Franklin tiene 17 amigos (Dom; Beverly, por Paparazzo 1;
 *     Devin, por "I Fought the Law") y Michael 7 (Lester, por "Friend Request"; Mary-Ann,
 *     por Fanatic 1). El muro de Dom acaba en su despedida (Extreme 4).
 *   * Global_114135.f_18578.f_383 (una publicación extra de Hayden Dubose) = -1: no se
 *     sabe qué lo pone, así que esa publicación no sale.
 * Diferencias con el juego, a propósito:
 *   * "Atrás" del juego (func_8508/8509) recorre los perfiles vistos; aquí el botón atrás
 *     del shell sale de la web (el host no tiene gancho de "atrás" para proveedores). Se
 *     guarda la pila igual (state.stack) por si se añade.
 *   * Sólo cambia de perfil un clic en una fila pulsable. Los anuncios la web los numera
 *     detrás de la última fila pulsable y el script usaría iLocal_48 de ese índice (al
 *     volver de la web del anuncio podría salir un perfil vacío, el 211).
 * Datos: los genera v/scriptdata/lifeinvader.py al compilar, ejecutando appinternet.ysc de
 * tu juego y leyendo sus GXT2 (lfi_m/lfi_f/lfi_t.gxt2); aquí sólo queda la plantilla vacía
 * entre @@DATA y @@END.
 */
(function () {
  'use strict';
  if (typeof GTAHOST === 'undefined') return;

  // @@DATA (filled at build time by v/scriptdata/ from your own game files; do not edit)
  const D = null;   // replaced by { order, profiles, text }
  // @@END

  const CH = ['M', 'F', 'T'];
  const NONE = 211;                       // valor de iLocal_48 sin perfil (func_115)

  // ---- la partida -------------------------------------------------------------
  const ORD = new Map(D.order.map((n, i) => [n, i + 1]));
  const missionDone = m => ORD.has('m' + m);
  const rcDone = r => ORD.has('r' + r);
  const rcOrder = r => ORD.get('r' + r) || 0;
  const RC383 = -1;                       // Global_114135.f_18578.f_383
  // func_129: misión de la historia terminada
  const func_129 = m => (m === 94 || m === -1) ? false : missionDone(m);
  // func_8386(x, 7): misión de personaje aleatorio terminada (bit 3 de f_18578[x])
  const rcFlag = r => rcDone(r);

  // ---- tablas (func_8391..8422) ---------------------------------------------
  const prof = p => D.profiles[p] || null;
  const nameLabel = p => 'LFI_' + (prof(p) ? prof(p).name : 'UNKNOWN');          // func_8392
  const pic = (p, k) => (prof(p) && prof(p)[k]) || 'BLANK';                        // func_8391/8422/8417-8419
  const isPage = p => !!(prof(p) && prof(p).page);                                 // func_8394
  function isOpen(p) {                                                             // func_8414
    if (p === 84 && !rcFlag(17)) return false;      // Dom: privado hasta Extreme 1
    return !!(prof(p) && prof(p).open);
  }
  const side = p => (prof(p) && prof(p).side) || [NONE, -1, NONE, -1, NONE, 0];
  function friendCount(p) {                                                        // func_8385
    if (p === 0) return 5 + (func_129(44) ? 1 : 0) + (rcFlag(21) ? 1 : 0);
    if (p === 1) return 14 + (rcFlag(17) ? 1 : 0) + (rcFlag(46) ? 1 : 0) + (func_129(8) ? 1 : 0);
    return side(p)[3];
  }

  // ---- textos -------------------------------------------------------------------
  function makeText(api, c) {
    const block = D.text[CH[c]] || {};
    // BEGIN_TEXT_COMMAND_SCALEFORM_STRING(label): bloque del personaje, global.gxt2
    // (D.text.G y luego strings.json del host); label inexistente -> '' (como el shell)
    return label => {
      if (!label) return '';
      const k = label.slice(4);
      let raw = block[k];
      if (raw == null) raw = D.text.G[k];
      if (raw != null) return GTAHOST.formatGxt(raw, true);
      if (api.has(label)) return api.html(label);
      api.log('lifeinvader: sin texto', label);
      return '';
    };
  }

  // ---- relleno (func_8379 con iParam1 = 1) --------------------------------------
  function fill(api, st) {
    const T = makeText(api, st.char);
    const p = st.profile, sub = st.sub;
    const L48 = st.L48 = [];
    const click = st.click = [];              // filas que la web deja pulsar (dataTextScope)
    const own = prof(p);

    // func_8416: cabecera
    let large = pic(p, 'large'), occ = '', rel = '';
    let mPhotos = pic(p, 'medPhotos'), mFriends = pic(p, 'medFriends'), mStalk = pic(p, 'medStalk');
    if (!isPage(p) && isOpen(p)) { occ = nameLabel(p) + '_OC'; rel = nameLabel(p) + '_RP'; }   // func_8421/8420
    const back = p >= 3 ? true : sub !== 0;
    let tabs = isOpen(p);
    if (p === 84 && !rcFlag(17)) {
      large = mPhotos = mFriends = mStalk = 'BLANK'; occ = rel = ''; tabs = false;
    }
    api.setDataSlot(0, T(nameLabel(p)), large, T(occ), T(rel), mPhotos, mFriends, mStalk,
      back, false, tabs, tabs);

    // func_8415: título de la columna
    let head;
    if (isOpen(p)) {
      head = ['LFI_MSGHEADER', 'LFI_FRIENDHEAD', 'LFI_STLKHEADER'][sub];
      if (p === 84 && !rcFlag(17)) head = 'LFI_PRIV1';
    } else head = isPage(p) ? 'LFI_NOT_STLK' : 'LFI_PRIV1';
    api.setDataSlot(4, 3, T(head));

    if (!isOpen(p)) return;
    let slot = 5;
    if (sub === 0) slot = wall(api, st, T, slot);
    else if (sub === 1) {
      // func_8397: lista de amigos (la última fila de un perfil ajeno no se pulsa: es el
      // "N friends with private profiles.")
      const list = own.friends || [];
      list.forEach((id, i) => {
        if (p === 0 && ((id === 7 && !rcFlag(21)) || (id === 6 && !func_129(44)))) return;
        if (p === 1 && ((id === 84 && !rcFlag(17)) || (id === 85 && !rcFlag(46)) || (id === 86 && !func_129(8)))) return;
        const can = !(i === list.length - 1 && p > 2);
        L48[slot] = id; click[slot] = can;
        api.setDataSlot(slot++, 2, T(nameLabel(id)), '', pic(id, 'small'), can);
      });
    } else {
      // func_8395: acosados
      for (const id of own.stalking || []) {
        L48[slot] = id; click[slot] = true;
        api.setDataSlot(slot++, 2, T(nameLabel(id)), '', pic(id, 'small'), true);
      }
    }
    sidebar(api, p, T, slot);
  }

  // func_8400: muro, de la misión terminada más reciente a la más antigua
  function wall(api, st, T, slot) {
    const p = st.profile, own = prof(p);
    const post = idx => {                                                          // func_8405
      const author = own.author[idx];
      st.L48[slot] = author; st.click[slot] = author !== p;
      api.setDataSlot(slot++, 1, T(nameLabel(author)), T('LFI_POSTEDUPDATE'),
        T('LFI_' + CH[st.char] + own.block + '_' + idx), pic(author, 'small'), author !== p);
    };
    for (let k = D.order.length; k > 0; k--) {
      const node = D.order[k - 1], id = +node.slice(1);
      if (node[0] === 'm') {
        const r = own.mission && own.mission[id];
        if (r) for (let i = 0; i < r[1]; i++) post(r[0] + i);
      } else {
        // Mary-Ann (Fanatic): las carreras 2 y 3 sólo cuentan si se hicieron en orden
        const skipRc = p === 0 && id === 22 && (!rcFlag(21) || rcOrder(22) < rcOrder(21));
        const r = !skipRc && own.rc && own.rc[id];
        if (r) for (let i = 0; i < r[1]; i++) {
          const idx = r[0] + i;
          if (p === 7 && id === 21 && idx === 6 && rcFlag(22) && rcOrder(22) < rcOrder(21)) continue;
          if (p === 7 && id === 22 && idx === 3 && rcFlag(23) && rcOrder(23) < rcOrder(22)) continue;
          post(idx);
        }
      }
      if (k === 1 && own.first) for (let i = own.first[0]; i <= own.first[1]; i++) post(i);
      if (p === 8 && RC383 !== -1 && k === RC383) post(7);
    }
    return slot;
  }

  // func_8380: Family / Friends / Stalking (o, en una página de empresa, su contador)
  function sidebar(api, p, T, slot) {
    const s = side(p);
    const rows = [[s[0], s[1], 'LFI_FAMILY'], [s[2], friendCount(p), 'LFI_FRIENDS'], [s[4], s[5], 'LFI_STALKING']];
    rows.forEach(([id, n, title], i) => {
      if (!isPage(p)) {
        api.setDataSlot(slot + i, 0, T(title), T(nameLabel(id)), pic(id, 'small'), n);
      } else {
        const head = i === 0 ? 'LFI_' + prof(p).cnt : '';                            // func_8381
        const nm = nameLabel(id) === 'LFI_UNKNOWN' ? '' : T(nameLabel(id));
        const ph = pic(id, 'small') === 'BLANK' ? '' : pic(id, 'small');
        api.setDataSlot(slot + i, 0, T(head), nm, ph);
      }
    });
  }

  // ---- personaje ------------------------------------------------------------
  // ?char= de la dirección. El host reescribe la URL al cargar la primera página
  // (replaceState a /v/<dominio>/index.html, sin la consulta), así que también se mira la
  // URL con la que se abrió la pestaña (performance, entrada "navigation").
  function pickCharacter(api) {
    const map = { michael: 0, m: 0, '0': 0, franklin: 1, f: 1, '1': 1, trevor: 2, t: 2, '2': 2 };
    const urls = [];
    try { urls.push(location.href); } catch (e) { /* sin location */ }
    try {
      const nav = performance.getEntriesByType('navigation')[0];
      if (nav && nav.name) urls.push(nav.name);
    } catch (e) { /* sin performance */ }
    // ?char= manda; si no, ?personaje= (el de las páginas de /v/, que además cambia la
    // piel del teléfono y ya llega al host como api.character)
    for (const key of ['char', 'personaje']) {
      for (const u of urls) {
        try {
          const v = (new URL(u).searchParams.get(key) || '').toLowerCase();
          if (v in map) return map[v];
        } catch (e) { /* URL rara */ }
      }
    }
    return api.character | 0;
  }
  const CHAR_NAME = ['Michael', 'Franklin', 'Trevor'];

  // func_8423: pila de perfiles vistos (la usa "atrás" en el juego)
  function push(st) {
    if (st.stack.length >= 19) st.stack.shift();
    st.stack.push([st.profile, st.sub]);
  }

  function ensureState(api) {
    const st = api.state;
    const c = pickCharacter(api);
    if (st.char !== c || st.profile == null) {
      // func_8378 la primera vez (o al cambiar de personaje): tu perfil, pestaña 0
      st.char = c; st.profile = c; st.sub = 0; st.stack = []; st.L48 = []; st.click = [];
      push(st);
    }
    return st;
  }

  GTAHOST.registerProvider('www.lifeinvader.com', {
    clearSlots: true,
    onPage(pageName, api) {
      if (pageName !== 'PAGE1') return;          // ERROR: sólo si browser.player == 1 (Online)
      const st = ensureState(api);
      fill(api, st);
      // U+2060 tras "?": que el aviso no parta "?char=" en dos en pantallas estrechas
      const others = [0, 1, 2].filter(c => c !== st.char).map(c => '?\u2060char=' + CHAR_NAME[c].toLowerCase());
      api.note('Lifeinvader de ' + CHAR_NAME[st.char] + ' con la historia terminada (en el juego ' +
        'depende de tu partida). Otro personaje: ' + others.join(' o ') + '.');
    },
    onSelect(sel, api) {
      if (api.page !== 'PAGE1') return;
      const st = ensureState(api);
      if (sel >= 4) {
        // func_8598: la persona o empresa de esa fila. Sólo filas pulsables: los anuncios
        // (la web los numera detrás de la última fila pulsable) no cambian de perfil
        const id = st.L48 && st.L48[sel];
        if (!(st.click && st.click[sel]) || id == null || id === NONE || !prof(id)) return;
        if (id === st.profile && st.sub === 0) return;        // (func_8379 no repinta)
        st.profile = id; st.sub = 0;
      } else if (sel === 0) { st.profile = st.char; st.sub = 0; }   // func_8597
      else if (sel === 2) st.sub = 1;
      else if (sel === 3) st.sub = 2;
      else if (sel !== 1) return;
      push(st);
      api.refresh();
    },
  });

  // Expuesto para las pruebas (estado y relleno de cada perfil)
  GTAHOST.lifeinvader = { D, fill, ensureState, pickCharacter };
})();
