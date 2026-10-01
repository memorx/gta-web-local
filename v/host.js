/*!
 * host.js — "lado juego" del navegador web de GTA V (modo historia) para Ruffle.
 *
 * En el juego, el navegador (web_browser.gfx) es la película principal y carga
 * dentro de sí cada web (www_*.gfx). Todo lo que en el juego resuelve el motor
 * (C++) o el script appinternet.sc lo hace aquí JS:
 *
 *   película  ──ExternalInterface.call──▶  funciones globales de este archivo
 *     (GameInterface.call: SET_TEXT_WITH_TRANSLATION, REQUEST_GFX_STREAM,
 *      REQUEST_TXD_AND_ADD_REF, GFX_READY, PLAY_SOUND, ...)
 *
 *   este archivo ──HOST_INVOKE(ruta, método, args)──▶ película
 *     (GO_TO_WEBPAGE, STREAM_RESPONSE, INITIALISE_WEBSITE, TXD_HAS_LOADED,
 *      SET_MOUSE_INPUT, SET_INPUT_EVENT, SET_ANALOG_STICK_INPUT, UPDATE_TEXT...)
 *
 * HOST_INVOKE / HOST_SET / HOST_GET y el parche de GameInterface.call los añade
 * el shim AS2 inyectado en web_browser.swf (v/host/host_pre.as).
 * Resumen de la API de proveedores en docs/gta-v.md.
 *
 * Uso mínimo:
 *   const host = GTAVHost.create({ container: el, start: 'www.lifeinvader.com' });
 *   host.on('navigate', info => ...); host.go('www.bleeter.biz'); host.back();
 *
 * Todo corre en local: no hay peticiones fuera del propio servidor.
 */
(function (global) {
  'use strict';

  // ════════════════════════════════════════════════════════════════════════
  // Configuración por defecto (todo se puede sobreescribir en create()).
  // ════════════════════════════════════════════════════════════════════════
  const DEFAULTS = {
    container: null,                       // elemento donde va el reproductor
    base: '/v',                            // raíz de la colección GTA V
    browserSwf: '/v/_host/web_browser.swf',// navegador con el shim del host
    fontLib: '/v/gfxfontlib.swf',          // gfxfontlib.swf (fuentes importadas)
    texBase: '/v/_tex/',                   // img://<txd>/<tex> -> texBase + txd/tex.png
    stringsUrl: '/v/_host/strings.json',   // textos del juego (uno o varios JSON); se esperan antes de arrancar
    // Tabla COMPLETA por hash (global.gxt2 base + parche, como la tiene el juego). Se
    // carga en segundo plano: cubre los labels que las webs arman en tiempo de
    // ejecución y no están en strings.json; los campos que ya se pintaron con un
    // label que faltaba se rellenan en cuanto llega. null = no usarla.
    stringsFallbackUrl: '/v/_host/strings_all.json',
    dataUrl: '/v/_host/host_data.json',    // datos portados de appinternet.sc (precios, noticias, bleets)
    // Proveedores de datos en archivos aparte (lo que el script del juego pone en
    // cada web dinámica): <providersUrl>index.json + <dominio>.js. null = <base>/_lib/providers/
    providersUrl: null,
    sitesUrl: '/v/_sites.json',            // lista de webs disponibles (opcional)
    sites: null,                           // o la lista directa: ['www.bleeter.biz', ...]
    // URL del .swf de una web a partir de su id (WWW_BLEETER_BIZ):
    siteSwf: null,                         // fn(siteId, domain) -> url
    // URL de la página "shell" de una web (para la barra de direcciones/historial):
    pageUrl: null,                         // fn(domain, page) -> url
    start: null,                           // 'www.lifeinvader.com', 'WWW_BLEETER_BIZ', ...
    home: 'WWW_EYEFIND_INFO',              // botón "inicio" (igual que en el juego)
    skin: 0,                               // SET_BROWSER_SKIN: 0 iFruit, 2 Badger, 3 Facade
    character: 0,                          // 0 Michael, 1 Franklin, 2 Trevor (datos dinámicos)
    hideGameCursor: true,                  // usar el cursor del sistema en vez del del juego
    missingText: 'label',                  // texto que falta: 'label' | 'empty'
    onBackKey: null,                       // fn() para la tecla Retroceso (null = GO_BACK del juego)
    // fn(dir) que mueve el historial de la página contenedora (dir -1 atrás, +1 adelante). Si
    // está, atrás/adelante de la barra DEL JUEGO (y host.back/forward) lo usan en vez del
    // historial interno del navegador; el estado de esos botones lo da setHistoryState().
    onHistory: null,
    ruffle: {},                            // opciones extra para Ruffle
    debug: false,                          // registra en consola cada llamada
  };

  // Tamaños del navegador del juego (WEB_BROWSER_PARENT)
  const STAGE_W = 1280, STAGE_H = 720;
  const CONTENT_Y = 48 + 45;      // safeFrameY + barra de herramientas
  const CONTENT_H = 627;          // alto visible de la web

  // ════════════════════════════════════════════════════════════════════════
  // Valores JS -> película. Ruffle convierte en la cadena "null" toda cadena
  // vacía o solo de espacios ('', ' ', '\n'...) que va de JS a ActionScript
  // (comprobado con test/empty_probe2.mjs): "NULL BMX" en pandmcycles, el botón
  // SELL de la bolsa que debía quedar oculto, etc. Esas cadenas (y las que ya
  // empiezan por \u0001) viajan con el prefijo \u0001 y el shim lo quita
  // (_global.__HOST.dec en host_pre.as). Se aplica a todo: argumentos de
  // HOST_INVOKE/HOST_SET y lo que devuelven las funciones que llama la película.
  // ════════════════════════════════════════════════════════════════════════
  const EMPTY_MARK = '\u0001';
  let encodeEmpty = true;         // false si el shim es anterior a la v3 (no sabría quitar la marca)
  function toMovie(v) {
    if (typeof v === 'string') return (encodeEmpty && (/^\s*$/.test(v) || v.charCodeAt(0) === 1)) ? EMPTY_MARK + v : v;
    if (Array.isArray(v)) return v.map(toMovie);
    if (v && typeof v === 'object' && Object.getPrototypeOf(v) === Object.prototype) {
      const o = {};
      for (const k in v) o[k] = toMovie(v[k]);
      return o;
    }
    return v;
  }
  /**
   * Respuesta "del juego" en cuanto termine la llamada actual (microtarea): nunca
   * dentro de un ExternalInterface.call (Ruffle está bloqueado) y sin depender de
   * setTimeout, que con la máquina cargada o la pestaña en segundo plano puede
   * tardar más que el pingTimer de 3 s del navegador (-> página de error de eyefind).
   */
  function soon(fn) {
    queueMicrotask(() => { try { fn(); } catch (e) { console.error(e); } });
  }

  // ════════════════════════════════════════════════════════════════════════
  // Nombres: el juego usa ids tipo WWW_LIFEINVADER_COM_S_PROFILE
  //   "_S_" = "/", "_D_" = "-", "_" = "."   (WEB_BROWSER.PARSE_FILENAME_TO_TEXT)
  // ════════════════════════════════════════════════════════════════════════
  function idToText(id) {
    return String(id).split('_S_').join('/').split('_D_').join('-').split('_').join('.').toLowerCase();
  }
  function textToId(text) {
    return String(text).split('.').join('_').split('/').join('_S_').split('-').join('_D_').toUpperCase();
  }
  /** Normaliza cualquier forma de dirección a un fullURL del juego. */
  function toFullUrl(input) {
    if (input == null) return null;
    let s = String(input).trim();
    if (!s) return null;
    if (/^[A-Z0-9_]+$/.test(s) && s.indexOf('_') >= 0) return s;       // ya es un id
    s = s.replace(/^[a-z]+:\/\//i, '').replace(/[?#].*$/, '').replace(/\/+$/, '');
    // Nuestras propias URLs: /v/<dominio>/index.html?page=X
    const m = /^\/?v\/([^/]+)\/(?:index\.html)?$/i.exec(s);
    if (m) s = m[1];
    const parts = textToId(s).split('_S_');
    // Igual que ENTER en la barra del juego (URL_HAS_SUBDOMAIN): si el dominio
    // no tiene subdominio ("maze-bank.com"), se antepone WWW_
    const host = parts[0].split('_D_').join('-');
    if (host.indexOf('_') === host.lastIndexOf('_')) parts[0] = 'WWW_' + parts[0];
    return parts.join('_S_');
  }
  /** "<tf:/WWW_X/CONTENT/campo>" (TextField._target) -> "_level0.WWW_X.CONTENT.campo" (HOST_SET/GET) */
  function fieldPath(desc) {
    const m = /^<(?:tf|mc):\/?(.*)>$/.exec(String(desc));
    return m ? '_level0' + (m[1] ? '.' + m[1].split('/').join('.') : '') : null;
  }
  /** Separa "WWW_X_COM_S_PAGE" en {siteId, page} como hace GO_TO_WEBPAGE. */
  function splitFullUrl(full) {
    const i = full.indexOf('_S_');
    if (i < 0) return { siteId: full, page: 'PAGE1' };
    return { siteId: full.slice(0, i), page: full.slice(i + 3) || 'PAGE1' };
  }

  // ════════════════════════════════════════════════════════════════════════
  // Textos: JOAAT del label en minúsculas -> cadena (GXT2)
  // ════════════════════════════════════════════════════════════════════════
  function joaat(str) {
    const bytes = new TextEncoder().encode(String(str).toLowerCase());
    let h = 0;
    for (let i = 0; i < bytes.length; i++) {
      h = (h + bytes[i]) >>> 0;
      h = (h + (h << 10)) >>> 0;
      h = (h ^ (h >>> 6)) >>> 0;
    }
    h = (h + (h << 3)) >>> 0;
    h = (h ^ (h >>> 11)) >>> 0;
    h = (h + (h << 15)) >>> 0;
    return h;
  }

  // Colores de los códigos ~x~ (HUD_COLOUR_* del juego)
  const GXT_COLOURS = {
    r: '#E03232', g: '#72CC72', b: '#5DB6E5', y: '#F0C850', o: '#FF8555',
    p: '#8466E2', q: '#CB3694', c: '#9B9B9B', m: '#4D4D4D', u: '#000000',
    l: '#000000', w: '#FFFFFF', f: '#FF8555', t: '#9B9B9B', d: '#C0C0C0',
  };

  function escapeHtml(s) {
    return s.replace(/&(?![a-z]+;|#\d+;)/gi, '&amp;');
  }

  /**
   * ADD_TEXT_COMPONENT_*: rellena en orden los huecos ~a~ (texto), ~1~ (entero) y
   * ~f~ (decimal) de una cadena GXT. Cada parte puede ser: cadena (tal cual), número
   * (entero con separador de miles, como ADD_TEXT_COMPONENT_FORMATTED_INTEGER(n, true)),
   * {label: 'X'} (texto de otro label: ADD_TEXT_COMPONENT_SUBSTRING_TEXT_LABEL),
   * {int: n, commas: false} o {float: n, decimals: 2}.
   */
  function substitute(str, parts, L) {
    if (!parts || !parts.length) return String(str);
    let i = 0;
    return String(str).replace(/~(a|1|f\d?|a_\d+|1_\d+)~/gi, all => (i < parts.length ? partText(parts[i++], L) : all));
  }
  function partText(p, L) {
    if (p == null) return '';
    if (typeof p === 'number') return Math.trunc(p).toLocaleString('en-US');
    if (typeof p === 'object') {
      if (p.label != null) return L(p.label);
      if (p.int != null) return p.commas === false ? String(Math.trunc(p.int)) : Math.trunc(p.int).toLocaleString('en-US');
      if (p.float != null) return Number(p.float).toFixed(p.decimals == null ? 2 : p.decimals);
    }
    return String(p);
  }

  /**
   * Convierte una cadena GXT (con ~n~, ~r~, ~h~, <C>…) al formato de un
   * TextField de Flash. html=true -> htmlText; html=false -> texto plano.
   */
  function formatGxt(str, html) {
    if (str == null) return '';
    let s = String(str);
    s = s.replace(/<\/?C>/g, '');                 // fuente condensada: sin equivalente
    if (!html) {
      return s.replace(/~n~/gi, '\n')
        .replace(/~[a-z0-9_]+~/gi, '')
        .replace(/<br\s*\/?>/gi, '\n');
    }
    s = escapeHtml(s);
    let open = [];
    s = s.replace(/~([a-z0-9_]+)~/gi, (all, code) => {
      const c = code.toLowerCase();
      if (c === 'n') return '<br/>';
      if (c === 'h' || c === 'bold') { open.push('</b>'); return '<b>'; }
      if (c === 'italic') { open.push('</i>'); return '<i>'; }
      if (c === 's') { const close = open.reverse().join(''); open = []; return close; }
      if (GXT_COLOURS[c]) { open.push('</font>'); return `<font color="${GXT_COLOURS[c]}">`; }
      return '';                                  // ~a~, ~1~, ~BLIP_x~, etc.
    });
    return s + open.reverse().join('');
  }

  // Colores HUD (GET_HUD_COLOUR): r, g, b, a(0-100). Subconjunto de hudcolor.dat
  const HUD_COLOURS = {
    0: [255, 255, 255], 1: [240, 240, 240], 2: [0, 0, 0], 3: [155, 155, 155],
    4: [205, 205, 205], 5: [77, 77, 77], 6: [224, 50, 50], 7: [240, 153, 153],
    8: [112, 25, 25], 9: [93, 182, 229], 10: [174, 219, 242], 11: [47, 92, 115],
    12: [240, 200, 80], 13: [254, 235, 169], 14: [126, 107, 41], 15: [255, 133, 85],
    16: [255, 194, 170], 17: [127, 66, 42], 18: [114, 204, 114], 19: [185, 230, 185],
    20: [57, 102, 57], 21: [132, 102, 226], 22: [192, 179, 239], 23: [67, 57, 111],
    24: [203, 54, 148], 116: [45, 110, 185], 117: [0, 0, 0], 134: [0, 71, 133],
  };

  // Llamadas de alta frecuencia que no se registran en el log
  const QUIET = new Set(['SET_MOUSE_INPUT', 'SET_ANALOG_STICK_INPUT', 'SCROLL_WEBPAGE_PIXELS', 'hitTestButtons', 'IS_KEYBOARD_ACTIVE']);

  // Páginas donde en el juego se gastaría dinero del personaje. Las compras no pasan
  // por GameInterface: appinternet.sc vigila el id de página y cobra al entrar en la
  // página de "compra pendiente"/confirmación. Lista sacada de PAGE_NAMES de las 81
  // webs (las de resultado, *_SUCCESS/*_FAILED, y TRANSACTIONS del banco, que solo
  // muestra movimientos, quedan fuera a propósito).
  const MONEY_PAGE = new RegExp('^(' + [
    'PURCHASE', 'PURCHASE(CAR|PLANE|BIKE|STOCK)',          // webs de vehículos (VehicleWebsite)
    'PURCHASE_D_CONFIRM',                                   // dynasty8, hushsmush, realitymill, iwillsurvive
    '(TRUCK|SUB|YACHT)_D_PURCHASE', '(AVENGER|HACKERTRUCK)_D_BUY',  // warstock/docktease (Online)
    'STOCK_TRADE_(BUY|SELL|CONFIRM)', 'CONFIRMED',          // bawsaq, lcn-exchange
    'PURCHASETRANSACTION', 'DONATIONTRANSACTION', 'MAKEDONATION',  // epsilonprogram
    'DEPOSIT',                                              // fleeca, maze-bank, bank of liberty
  ].join('|') + ')$');
  const MONEY_NOTICE = 'En el juego esto usaría el dinero del personaje';
  // Labels que ya no existen en los GXT2 actuales y cuyo texto sigue en el juego con otra
  // clave: pandmcycles 2013 (web_x64b) pide PAM_PG1_BODY (el párrafo de presentación); la versión
  // de update.rpf usa PAM_PG1_BODY1 con el mismo texto. Sólo se usan si el label no existe.
  const LABEL_ALIASES = { PAM_PG1_BODY: 'PAM_PG1_BODY1' };
  // Labels que en texto plano conservan el "<BR>" literal (las categorías de eyefind; ver
  // SET_TEXT_WITH_TRANSLATION). En el resto de campos no HTML el <BR> pasa a salto de línea.
  const KEEP_BR_LABELS = /^EF_(MEDIAANDENT|FOODANDDRINK|MONEYANDSERV|TRAVELANDTRANS|FASHIONANDHEALTH)$/;
  // Página de error del navegador (WEB_BROWSER.SHOW_ERROR_PAGE)
  const ERROR_SITE = 'WWW_EYEFIND_INFO';
  const ERROR_PAGE = ERROR_SITE + '_S_ERROR';

  // Estado único (ExternalInterface llama a funciones globales: un host por página)
  let H = null;

  // ════════════════════════════════════════════════════════════════════════
  // Host
  // ════════════════════════════════════════════════════════════════════════
  class Host {
    constructor(opts) {
      this.o = Object.assign({}, DEFAULTS, opts || {});
      this.o.ruffle = Object.assign({}, opts && opts.ruffle);
      this.strings = {};
      this.missing = new Set();
      this.fallbackLoaded = false;         // ¿llegó la tabla completa (stringsFallbackUrl)?
      this.unfilled = new Map();           // campo "<tf:/ruta>" -> {label, html} pintado sin texto
      this.knownSites = null;              // Set de siteIds disponibles (null = todas)
      this.listeners = {};
      this.flags = {};                     // SET_GLOBAL_ACTIONSCRIPT_FLAG
      this.player = null;
      this.ready = false;                  // HOST_BROWSER_READY recibido
      this.state = { fullURL: null, siteId: null, page: null, websiteId: 0, pageId: 0 };
      this.pending = null;                 // última navegación pedida desde fuera {from, full, t}
      this.scrollVel = 0;                  // rueda: misma inercia que appinternet.sc
      this.lastMouse = null;
      this.txdQueue = [];                  // REQUEST_TXD_AND_ADD_REF pendientes (se responden en tanda)
      this.streams = [];                   // últimos REQUEST_GFX_STREAM {uid, siteId, ok, page, ready, retry, t}
      this.retryTarget = null;             // web que se está reintentando (retryStream)
      this.queuedGo = null;                // go() pedido mientras cargaba otra web (runQueuedGo)
      this.log = [];                       // registro para pruebas (últimas 500 llamadas)
      this.providers = Host.providers;     // siteId -> proveedor (los de archivo se registran aquí)
      this.providerState = {};             // siteId -> objeto que el proveedor conserva entre páginas
      this.providerLoads = {};             // siteId -> promesa de carga de su archivo
      this.providerFiles = {};             // archivo -> promesa (una sola carga por archivo)
      this.manifest = undefined;           // providers/index.json (null = no hay índice)
      this.notes = {};                     // siteId -> aviso del proveedor bajo el visor
      this.pageSeq = 0;                    // cuenta de páginas mostradas (descarta rellenos viejos)
      this.lastSelection = -1;             // GET_CURRENT_SELECTION del último clic
      this.fallbackReady = new Promise(ok => { this._fallbackDone = ok; });
      this._raf = this._raf.bind(this);
    }

    // ---- eventos para la página contenedora --------------------------------
    on(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); return this; }
    emit(ev, data) { (this.listeners[ev] || []).forEach(fn => { try { fn(data); } catch (e) { console.error(e); } }); }
    trace(kind, name, args, extra) {
      const rec = { t: Math.round(performance.now()), kind, name, args };
      if (extra !== undefined) rec.ret = extra;
      this.log.push(rec);
      if (this.log.length > 500) this.log.shift();
      if (this.o.debug) console.log(`[gtav-host] ${kind} ${name}`, ...(args || []), ...(extra !== undefined ? ['→', extra] : []));
      this.emit('trace', rec);
    }

    // ---- arranque -----------------------------------------------------------
    async init() {
      await Promise.all([this.loadStrings(), this.loadSites(), this.loadData(), this.loadProviderManifest()]);
      // El proveedor de la web de arranque (si tiene archivo) se pide ya, en paralelo con Ruffle
      const first = toFullUrl(this.o.start || this.o.home);
      if (first) this.ensureProvider(splitFullUrl(first).siteId, false);
      this.mountPlayer();
      this.loadFallbackStrings();          // en segundo plano, sin retrasar el arranque
      requestAnimationFrame(this._raf);
      return this;
    }

    /**
     * Tabla completa de textos (por hash). Suele llegar antes de que la película pida
     * el primer texto; si no, los campos que se pintaron con un label que faltaba se
     * rellenan ahora (el juego nunca muestra el label: su tabla ya está en memoria).
     */
    async loadFallbackStrings() {
      const url = this.o.stringsFallbackUrl;
      // Sin tabla completa (desactivada o no publicada) no hay nada que esperar: se deja
      // de apuntar campos pendientes (fallbackLoaded = "ya no llegará nada más")
      const settle = () => { this.fallbackLoaded = true; this.unfilled.clear(); this._fallbackDone(); };
      if (!url) { settle(); return; }
      try {
        const r = await fetch(url);
        if (!r.ok) throw new Error(r.status);
        const j = await r.json();
        const table = j.strings || j;
        for (const k in table) if (!(k in this.strings)) this.strings[k] = table[k];
        this.fallbackLoaded = true;
        this._fallbackDone();
        this.refillMissing();
      } catch (e) {
        console.warn('[gtav-host] sin tabla completa de textos', url, e.message);
        settle();
      }
    }

    // ---- proveedores en archivo (providers/index.json + <dominio>.js) -------
    providersBase() {
      const u = this.o.providersUrl != null ? this.o.providersUrl : (this.o.base ? this.o.base + '/_lib/providers/' : null);
      return u ? u.replace(/\/?$/, '/') : null;
    }
    /**
     * index.json: {"providers": {"www.bawsaq.com": {"deps": ["_stock_market.js"]}, ...}}
     * (o una lista de dominios). Sólo se cargan las webs que aparecen. Sin índice (404)
     * se prueba <dominio>.js en las webs dinámicas (IS_SITE_DYNAMIC = 1).
     */
    async loadProviderManifest() {
      const base = this.providersBase();
      this.manifest = null;
      if (!base) return;
      try {
        const r = await fetch(base + 'index.json', { cache: 'no-cache' });
        if (!r.ok) throw new Error(r.status);
        const j = await r.json();
        const list = j.providers || j;
        const m = {};
        const add = (domain, v) => {
          const id = siteKey(domain);
          if (id) m[id] = { domain: idToText(id), file: v && v.file, deps: (v && v.deps) || [] };
        };
        if (Array.isArray(list)) list.forEach(d => add(d, null));
        else Object.keys(list).forEach(d => { if (d[0] !== '_') add(d, list[d]); });
        this.manifest = m;
      } catch (e) { /* sin índice */ }
    }
    /**
     * Pide el archivo del proveedor de una web (si hay). Devuelve una promesa si hay
     * que esperar la carga, o null si no hay nada que cargar.
     */
    ensureProvider(siteId, dynamic) {
      const base = this.providersBase();
      if (!base || !siteId) return null;
      if (this.providerLoads[siteId]) return this.providerLoads[siteId].done ? null : this.providerLoads[siteId];
      let entry = this.manifest ? this.manifest[siteId] : null;
      if (!entry) {
        if (this.manifest || !dynamic || this.providers[siteId]) return null;
        entry = { domain: idToText(siteId), deps: [] };
      }
      const files = entry.deps.concat(entry.file || entry.domain + '.js');
      const p = (async () => {
        for (const f of files) await this.loadProviderFile(base, f);
      })().catch(e => console.warn('[gtav-host] proveedor', siteId, e && e.message || e))
        .then(() => { p.done = true; this.trace('event', 'provider-loaded', [siteId, !!this.providers[siteId]]); });
      this.providerLoads[siteId] = p;
      return p;
    }
    loadProviderFile(base, file) {
      const url = base + file;
      if (!this.providerFiles[url]) {
        this.providerFiles[url] = fetch(url, { cache: 'no-cache' }).then(r => {
          if (!r.ok) throw new Error(r.status + ' ' + url);
          return r.text();
        }).then(code => {
          const s = document.createElement('script');
          s.textContent = code + '\n//# sourceURL=' + new URL(url, location.href).href;
          document.head.appendChild(s);
        });
      }
      return this.providerFiles[url];
    }
    /** Aviso bajo el visor (p. ej. "cotizaciones inventadas"); '' lo quita. */
    setNote(siteId, text) {
      this.notes[siteId] = text || '';
      if (siteId === this.state.siteId) this.emit('note', { siteId, domain: idToText(siteId), text: this.notes[siteId] });
    }

    /** Vuelve a escribir los campos que se quedaron sin texto (ver loadFallbackStrings). */
    refillMissing() {
      for (const [field, rec] of this.unfilled) {
        const raw = this.text(rec.label);
        if (raw == null) continue;
        this.unfilled.delete(field);
        this.missing.delete(rec.label);
        const path = fieldPath(field);
        if (path) this.set(path, rec.html ? 'htmlText' : 'text', formatGxt(raw, rec.html));
        this.trace('event', 'refill', [rec.label, path]);
      }
    }

    async loadStrings() {
      const urls = [].concat(this.o.stringsUrl || []);
      for (const url of urls) {
        try {
          const r = await fetch(url);
          if (!r.ok) throw new Error(r.status);
          const j = await r.json();
          Object.assign(this.strings, j.strings || j);
        } catch (e) {
          console.warn('[gtav-host] no pude cargar textos', url, e.message);
        }
      }
    }

    /** host_data.json: lo que el script del juego rellena (ver port_web_data.py) */
    async loadData() {
      this.data = {};
      if (!this.o.dataUrl) return;
      try {
        const r = await fetch(this.o.dataUrl);
        if (r.ok) this.data = await r.json();
      } catch (e) { /* sin datos: las webs dinámicas salen sin contenido, como sin script */ }
      this.vehiclePrices = this.data.vehiclePrices || null;
    }

    async loadSites() {
      let list = this.o.sites;
      if (!list && this.o.sitesUrl) {
        try {
          const r = await fetch(this.o.sitesUrl);
          if (r.ok) {
            const j = await r.json();
            const arr = Array.isArray(j) ? j : (j.story || j.sites || []);
            list = arr.map(x => (typeof x === 'string' ? x : x.domain));
            this.siteInfo = {};
            arr.forEach(x => { if (x && x.domain) this.siteInfo[x.domain] = x; });
          }
        } catch (e) { /* sin lista: se intenta cargar cualquier web */ }
      }
      if (list && list.length) this.knownSites = new Set(list.map(d => textToId(d)));
    }

    /** Traduce un label del juego (o null si no existe). */
    text(label) {
      if (label == null || label === '') return '';
      const v = this.lookup(label);
      if (v != null) return v;
      this.missing.add(label);
      return null;
    }
    /** Como text() pero sin apuntar el label en `missing` (DOES_TEXT_LABEL_EXIST). */
    lookup(label) {
      if (label == null || label === '') return '';
      const s = this.strings;
      if (Object.prototype.hasOwnProperty.call(s, label)) return s[label];
      const v = this.byHash(joaat(label));
      if (v == null && Object.prototype.hasOwnProperty.call(LABEL_ALIASES, label)) return this.lookup(LABEL_ALIASES[label]);
      return v;
    }
    /** Texto por hash JOAAT: número (con o sin signo) o cadena hex ('a1b2c3d4', '0xA1B2C3D4'). */
    byHash(hash) {
      let h;
      if (typeof hash === 'number') h = hash;
      else {
        const t = String(hash).trim().replace(/^0x/i, '');
        h = /^[0-9a-f]{1,8}$/i.test(t) ? parseInt(t, 16) : NaN;
      }
      if (!Number.isFinite(h)) return null;
      h = h >>> 0;
      const s = this.strings;
      const hex = h.toString(16).padStart(8, '0');
      const v = s[hex] ?? s[hex.toUpperCase()] ?? s['0x' + hex] ?? s['0x' + hex.toUpperCase()] ?? s[String(h)];
      return v === undefined ? null : v;
    }
    /** Traduce y, si falta, devuelve el label o '' según la configuración. */
    L(label) {
      const v = this.text(label);
      if (v != null) return v;
      return this.o.missingText === 'empty' ? '' : String(label);
    }

    siteSwfUrl(siteId) {
      if (this.o.siteSwf) return this.o.siteSwf(siteId, idToText(siteId));
      return `${this.o.base}/${idToText(siteId)}/${siteId.toLowerCase()}.swf`;
    }
    /**
     * PNG de una textura del juego: img://<txd>/<tex> -> texBase/<txd>/<tex>.png
     * (en minúsculas, como <work>/v/extract/png/<ytd>/<textura>.png).
     */
    texUrl(src) {
      const m = /^img:\/\/([^/]+)\/([^/?#]+?)(?:\.dds|\.png)?$/i.exec(String(src));
      if (!m) return null;
      return this.o.texBase.replace(/\/?$/, '/') + encodeURIComponent(m[1].toLowerCase()) + '/' + encodeURIComponent(m[2].toLowerCase()) + '.png';
    }
    /** URL de nuestra página para un fullURL del juego (/v/<dominio>/index.html?page=X) */
    pageUrl(fullURL) {
      const { siteId, page } = splitFullUrl(fullURL);
      const domain = idToText(siteId);
      if (this.o.pageUrl) return this.o.pageUrl(domain, page);
      const q = page && page !== 'PAGE1' ? `?page=${encodeURIComponent(page)}` : '';
      return `${this.o.base}/${domain}/index.html${q}`;
    }

    // ---- Ruffle -------------------------------------------------------------
    rewriteRules() {
      const origin = location.origin;
      const abs = p => (/^[a-z]+:/i.test(p) ? p : origin + (p.startsWith('/') ? '' : '/') + p);
      const tex = abs(this.o.texBase.replace(/\/?$/, '/'));
      return [
        // Texturas en <img src='img://txd/tex'> y loadMovie
        [/^img:\/\/([^/]+)\/([^/?#]+?)(?:\.dds|\.png)?$/i, tex + '$1/$2.png'],
        // Fuentes importadas (ImportAssets2 "gfxfontlib.swf") desde cualquier carpeta
        [/^.*\/gfxfontlib\.swf$/i, abs(this.o.fontLib)],
      ];
    }

    mountPlayer() {
      const ruffle = global.RufflePlayer && global.RufflePlayer.newest();
      if (!ruffle) throw new Error('Ruffle no está cargado (falta ruffle.js)');
      const player = ruffle.createPlayer();
      player.id = 'gtav-player';
      player.style.width = '100%';
      player.style.height = '100%';
      player.style.display = 'block';
      this.o.container.appendChild(player);
      this.player = player;
      this.bindInput(player);
      const cfg = Object.assign({
        url: this.o.browserSwf,
        allowScriptAccess: true,
        autoplay: 'on',
        unmuteOverlay: 'hidden',
        splashScreen: false,
        preloader: true,
        letterbox: 'on',
        scale: 'showAll',
        forceScale: true,           // el navegador pide noBorder; lo encuadra el shell
        quality: 'high',
        backgroundColor: '#000000',
        contextMenu: 'off',
        warnOnUnsupportedContent: false,
        logLevel: 'error',
        openUrlMode: 'deny',        // nada sale de la colección
        allowNetworking: 'all',
        urlRewriteRules: this.rewriteRules(),
        maxExecutionDuration: 30,
      }, this.o.ruffle);
      if (this.o.ruffle.urlRewriteRules) cfg.urlRewriteRules = this.rewriteRules().concat(this.o.ruffle.urlRewriteRules);
      const api = typeof player.ruffle === 'function' ? player.ruffle() : player;
      api.load(cfg).catch(e => this.emit('error', e));
    }

    // Llamada síncrona a la película (solo fuera de un ExternalInterface.call)
    invoke(path, method, args) {
      if (!this.player) return null;
      try {
        const api = typeof this.player.ruffle === 'function' ? this.player.ruffle() : null;
        const a = toMovie(args || []);
        const r = api && api.callExternalInterface
          ? api.callExternalInterface('HOST_INVOKE', path, method, a)
          : this.player.HOST_INVOKE(path, method, a);
        if (!QUIET.has(method)) this.trace('→movie', `${path}.${method}`, args, r);
        return r;
      } catch (e) {
        console.warn('[gtav-host] invoke falló', path, method, e);
        return null;
      }
    }
    set(path, prop, value) {
      const api = this.player && this.player.ruffle();
      return api ? api.callExternalInterface('HOST_SET', path, prop, toMovie(value)) : false;
    }
    get(path) {
      const api = this.player && this.player.ruffle();
      return api ? api.callExternalInterface('HOST_GET', path) : null;
    }
    /** Como invoke pero diferido: nunca reentra en Ruffle desde un callback AS->JS. */
    later(fn, ms) { setTimeout(() => { try { fn(); } catch (e) { console.error(e); } }, ms || 0); }
    browser(method, ...args) { return this.invoke('browser', method, args); }

    // ---- navegación ---------------------------------------------------------
    /** Ir a una dirección: 'www.bleeter.biz', 'lifeinvader.com/profile', 'WWW_EYEFIND_INFO'... */
    go(address, from) {
      const full = toFullUrl(address);
      if (!full) return;
      if (!this.ready) { this.o.start = full; return; }
      // Mientras carga otra web el navegador del juego ignora GO_TO_WEBPAGE (loadingWebPage):
      // p. ej. "atrás" o una dirección escrita antes de que termine la carga. Se guarda y
      // se pide en cuanto se muestre la que estaba cargando (onPageShown).
      if (this.get('browser.loadingWebPage') === true) {
        const last = this.streams[this.streams.length - 1];
        if (!last || Date.now() - last.t < 30000) {
          this.queuedGo = { from: from || 'user', full };
          this.trace('event', 'go-queued', [full, from || 'user']);
          return;
        }
        // una carga colgada más de 30 s no bloquea la navegación para siempre
        this.trace('event', 'go-unstuck', [full, last.siteId]);
        this.set('browser', 'loadingWebPage', false);
        this.queuedGo = null;
      }
      this.pending = { from: from || 'user', full, t: Date.now() };
      this.browser('GO_TO_WEBPAGE', full);
    }
    /** ¿Quién pidió la página que acaba de mostrarse? (para decidir pushState) */
    takeOrigin(full) {
      const p = this.pending;
      this.pending = null;
      // Sólo cuenta si la página mostrada es de la web pedida: si no, el GO_TO_WEBPAGE se
      // perdió (el navegador lo ignora mientras carga otra) y esto es un clic en la web.
      // El plazo es amplio: la primera carga de una web pesada (lifeinvader) pasa de 15 s
      // con la máquina cargada, y un 'popstate' tomado por 'movie' añadiría una entrada
      // al historial en vez de volver.
      if (!p || Date.now() - p.t > 120000) return 'movie';
      if (splitFullUrl(p.full).siteId !== splitFullUrl(full).siteId) return 'movie';
      return p.from;
    }
    home() { this.go(this.o.home, 'user'); }
    back() { this.historyStep(-1); }
    forward() { this.historyStep(1); }
    /**
     * Atrás (-1) / adelante (+1). Con onHistory (el shell) se mueve el historial de la página,
     * igual que sus botones y Retroceso; sin él, GO_BACK/GO_FORWARD del navegador del juego
     * (su historial interno: sin onHistory el shim no activa shellHistory y no los desvía).
     */
    historyStep(dir) {
      if (!this.ready) return;
      if (this.o.onHistory) { this.o.onHistory(dir < 0 ? -1 : 1); return; }
      this.browser(dir < 0 ? 'GO_BACK' : 'GO_FORWARD');
    }
    /**
     * Estado de atrás/adelante de la barra del juego cuando manda el historial de la página
     * (onHistory): gris y desactivado si no se puede (UPDATE_TOOLBAR_BUTTONS del shim v5).
     */
    setHistoryState(canBack, canForward) {
      this.history = { back: !!canBack, forward: !!canForward };
      if (!this.ready || !this.shellHistory) return;
      this.set('host', 'canBack', this.history.back);
      this.set('host', 'canForward', this.history.forward);
      this.browser('UPDATE_TOOLBAR_BUTTONS');
    }

    onBrowserReady() {
      this.ready = true;
      const b = (m, ...a) => this.browser(m, ...a);
      // Lo que hace appinternet.sc al abrir el navegador (modo historia, PC)
      b('SET_BROWSER_SKIN', this.o.skin);
      b('SET_MULTIPLAYER', false);
      b('SET_WIDESCREEN', true);
      b('IS_JAPANESE', false);
      if (this.o.hideGameCursor) this.set('_level0.CURSOR', '_alpha', 0);
      b('SHOW_CURSOR', true);
      // Atrás/adelante de la barra del juego -> historial de la página (shim v5, §2.12)
      this.shellHistory = !!this.o.onHistory && Number(this.shimVersion) >= 5;
      if (this.shellHistory) {
        this.set('host', 'shellHistory', true);
        const hs = this.history || { back: false, forward: false };
        this.setHistoryState(hs.back, hs.forward);
      }
      this.emit('ready', this);
      const start = this.o.start ? toFullUrl(this.o.start) : this.o.home;
      this.pending = { from: 'initial', full: start, t: Date.now() };
      b('GO_TO_WEBPAGE', start);
    }

    /**
     * Cada vez que el navegador muestra una página (HOST_PAGE_SHOWN, lo avisa el
     * shim desde INITIALISE_WEBSITE): datos de webs dinámicas y aviso al shell.
     */
    onPageShown(full, dynamic, redirect) {
      if (!full || typeof full !== 'string') return;
      const seq = ++this.pageSeq;                          // invalida rellenos pendientes de la anterior
      if (this.runQueuedGo(full)) return;
      if (this.retryStream(full)) return;
      const { siteId, page } = splitFullUrl(full);
      const dyn = dynamic === 1 || dynamic === true;       // BaseWebsite.IS_SITE_DYNAMIC
      const fresh = this.state.siteId !== siteId;           // se entra desde otra web
      this.state.dynamic = dyn;
      this.afterPageShown(full, redirect);
      // 'pageready' = la página ya tiene sus datos (tras el proveedor y UPDATE_TEXT); el
      // shell quita entonces el aviso "Cargando …"
      const ready = () => {
        if (seq !== this.pageSeq) return;
        this.trace('event', 'pageready', [full]);
        this.emit('pageready', { fullURL: full, siteId, page, domain: idToText(siteId) });
        this.moneyNotice(full, page, seq);
      };
      const fill = () => {
        if (seq !== this.pageSeq) return;
        let done;
        try { done = this.fillDynamicSite(full, dyn, fresh); } catch (e) { console.warn('[gtav-host] relleno', full, e); }
        if (done && typeof done.then === 'function') done.then(ready, ready); else ready();
      };
      const wait = this.ensureProvider(siteId, dyn);       // archivo del proveedor, si falta
      if (wait) wait.then(fill); else fill();
    }

    /**
     * Navegación pedida mientras cargaba otra web (ver go): se pide ahora. La página que
     * acaba de mostrarse quedó superada y no se anuncia (ni historial ni barra). Devuelve
     * true si navegó.
     */
    runQueuedGo(full) {
      const q = this.queuedGo;
      if (!q) return false;
      this.queuedGo = null;
      this.pending = { from: q.from, full: q.full, t: Date.now() };
      const norm = f => { const s = splitFullUrl(f); return s.siteId + '_S_' + s.page; };
      if (norm(q.full) === norm(full)) return false;       // era justo la que cargaba
      this.trace('event', 'go-dequeued', [q.full, q.from]);
      this.browser('GO_TO_WEBPAGE', q.full);
      return true;
    }

    /**
     * Red de seguridad para la carrera del pingTimer: si el navegador acaba en la página
     * de error de eyefind porque la web pedida no llegó a cargarse (pingTimer de 3 s de
     * REQUEST_STREAM o onLoadError de MovieClipLoader) y no fue el host quien la dio por
     * inexistente (STREAM_RESPONSE_FAILED), se vuelve a pedir UNA vez. La página de error
     * no se anuncia (ni historial ni barra de direcciones). Devuelve true si reintentó.
     */
    retryStream(full) {
      if (full !== ERROR_PAGE) return false;
      const s = this.streams;
      const err = s[s.length - 1], prev = s[s.length - 2];
      if (!err || err.siteId !== ERROR_SITE || !prev || !prev.ok || prev.ready || prev.retry
          || prev.siteId === ERROR_SITE || Date.now() - prev.t > 60000) return false;
      const target = prev.siteId + (prev.page && prev.page !== 'PAGE1' ? '_S_' + prev.page : '');
      this.retryTarget = prev.siteId;                        // la nueva petición ya no se reintenta
      prev.retry = true;
      this.trace('event', 'stream-retry', [target]);
      this.browser('GO_TO_WEBPAGE', target);
      return true;
    }

    afterPageShown(full, redirect) {
      const { siteId, page } = splitFullUrl(full);
      const prev = this.state.fullURL;
      const prevSite = this.state.siteId;
      this.state.fullURL = full; this.state.siteId = siteId; this.state.page = page;
      if (prevSite !== siteId) this.emit('note', { siteId, domain: idToText(siteId), text: this.notes[siteId] || '' });
      const info = {
        fullURL: full, siteId, page,
        domain: idToText(siteId),
        display: idToText(full),
        url: this.pageUrl(full),
        from: redirect ? 'redirect' : this.takeOrigin(full),
        changed: prev !== full,
        title: this.get('browser.TOOLBAR.titlebarText.text') || '',
      };
      this.trace('event', 'navigate', [info.display, info.from], info.url);
      this.emit('navigate', info);
    }

    /**
     * Aviso "En el juego esto usaría el dinero del personaje" al entrar en una página de
     * compra (MONEY_PAGE). Va DESPUÉS del proveedor de la web y sólo si la compra sigue en
     * pie: no si la página saltó a otra mientras se rellenaba (el proveedor llamó goTo, p. ej.
     * epsilonprogram PURCHASETRANSACTION -> TRANSACTION_D_FAILED "sin existencias", o la web
     * saltó sola durante UPDATE_TEXT) ni si ya se muestra otra página.
     */
    moneyNotice(full, page, seq) {
      if (!MONEY_PAGE.test(page)) return;
      if (seq !== this.pageSeq || this.redirectSeq === seq) {
        this.trace('event', 'notice-skipped', [full]);
        return;
      }
      this.emit('notice', { text: MONEY_NOTICE, page: full });
    }

    // ---- datos de webs dinámicas (lo que rellena appinternet.sc) ------------
    /**
     * Equivale a func_8363 del script: en una web dinámica vacía los slots
     * (SET_DATA_SLOT_EMPTY), deja que el proveedor los rellene y termina con
     * UPDATE_TEXT (sin él la web no pinta ni sus textos fijos).
     */
    fillDynamicSite(full, dyn, fresh) {
      const { siteId, page } = splitFullUrl(full);
      const provider = this.providers[siteId];
      if (!dyn && !provider) return;
      const isObj = !!provider && typeof provider === 'object' && typeof provider.onPage === 'function';
      const clear = isObj && provider.clearSlots !== undefined ? !!provider.clearSlots : dyn;
      if (clear) this.browser('SET_DATA_SLOT_EMPTY');
      if (!provider) { this.updateText(); return; }
      if (!isObj) {
        // Proveedor-función (los internos): devuelve true si hay que repintar
        let refresh = false;
        try { refresh = provider.call(this, this.ctx(siteId, page, fresh)) === true; } catch (e) { console.warn('[gtav-host] proveedor', siteId, e); }
        if (dyn || refresh) this.updateText();
        return;
      }
      const seq = this.pageSeq;
      const api = this.pageApi(siteId, page, fresh);
      const finish = ret => {
        if (seq !== this.pageSeq) return;                   // ya se mostró otra página
        if (!api.updated && (dyn || ret === true)) this.updateText();
      };
      let ret;
      try { ret = provider.onPage(page, api); } catch (e) { console.warn('[gtav-host] proveedor', siteId, page, e); }
      // Proveedor asíncrono: se devuelve la promesa para saber cuándo quedó pintada la página
      if (ret && typeof ret.then === 'function') return ret.then(finish, e => { console.warn('[gtav-host] proveedor', siteId, page, e); finish(); });
      finish(ret);
    }
    /**
     * UPDATE_TEXT. Si durante la llamada la web salta sola a otra página (bolsa:
     * STOCK_PORTFOLIO sin acciones -> STOCK_PORTFOLIO_EMPTY), esa página es una
     * redirección: el shell la pone con replaceState (si no, "atrás" volvería a la
     * página que redirige y el usuario quedaría atrapado).
     */
    updateText(newPage) {
      this.inUpdate = (this.inUpdate || 0) + 1;
      try { return newPage === undefined ? this.browser('UPDATE_TEXT') : this.browser('UPDATE_TEXT', newPage); }
      finally { this.inUpdate--; }
    }
    /** Vuelve a rellenar la página actual (lo que el script hace tras +/- en la bolsa, etc.). */
    refillPage() {
      if (this.state.fullURL) this.fillDynamicSite(this.state.fullURL, !!this.state.dynamic, false);
    }
    ctx(siteId, page, fresh) {
      const self = this;
      return {
        host: self,
        L: l => self.L(l),
        text: l => self.text(l),
        siteId,
        websiteId: self.state.websiteId,
        pageId: self.state.pageId,
        page,
        fresh: !!fresh,
        character: self.o.character,
        slot: (i, ...vals) => self.browser('SET_DATA_SLOT', i, ...vals),
        append: (i, ...vals) => self.browser('APPEND_DATA_SLOT', i, ...vals),
        empty: () => self.browser('SET_DATA_SLOT_EMPTY'),
        call: (m, ...a) => self.browser(m, ...a),
      };
    }

    /**
     * API que recibe un proveedor (registerProvider): lo que appinternet.sc hace con
     * BEGIN_SCALEFORM_MOVIE_METHOD / BEGIN_TEXT_COMMAND_SCALEFORM_STRING. Documentada
     * en docs/gta-v.md, "Host and providers".
     */
    pageApi(siteId, page, fresh) {
      const h = this;
      const fmt = (html) => (label, ...parts) => {
        let raw = h.text(label);
        if (raw == null) raw = h.o.missingText === 'empty' ? '' : String(label);
        return formatGxt(substitute(raw, parts, l => h.L(l)), html);
      };
      const CHAR_NAMES = ['MICHAEL', 'FRANKLIN', 'TREVOR'];
      const state = h.providerState[siteId] || (h.providerState[siteId] = {});
      const seq = h.pageSeq;
      const api = {
        // ¿sigue siendo la página visible? (para proveedores asíncronos)
        isCurrent: () => seq === h.pageSeq,
        host: h, siteId, domain: idToText(siteId), page, pageName: page,
        pageId: h.state.pageId, websiteId: h.state.websiteId, fullURL: h.state.fullURL,
        fresh: !!fresh, dynamic: !!h.state.dynamic,
        selection: h.lastSelection,
        character: h.o.character, characterName: CHAR_NAMES[h.o.character] || 'MICHAEL',
        state, data: h.data,
        updated: false,
        // ---- textos (BEGIN_TEXT_COMMAND_SCALEFORM_STRING + ADD_TEXT_COMPONENT_*) ----
        text: fmt(false),                       // traducido, GXT -> texto plano (campos .text)
        html: fmt(true),                        // traducido, GXT -> HTML (campos htmlText)
        raw: label => h.lookup(label),          // tal cual en el GXT, o null
        has: label => h.lookup(label) != null,  // DOES_TEXT_LABEL_EXIST
        byHash: (hash, html) => { const v = h.byHash(hash); return v == null ? null : formatGxt(v, !!html); },
        format: (str, ...parts) => substitute(String(str), parts, l => h.L(l)),
        need: labels => ([].concat(labels).every(l => h.lookup(l) != null) || h.fallbackLoaded ? Promise.resolve() : h.fallbackReady),
        formatInt: n => Math.floor(Number(n) || 0).toLocaleString('en-US'),
        // ---- película (BEGIN_SCALEFORM_MOVIE_METHOD sobre el navegador) ----
        callMovie: (method, ...args) => h.browser(method, ...args),
        callSite: (method, ...args) => h.invoke('site', method, args),
        setDataSlot: (slot, ...values) => h.browser('SET_DATA_SLOT', slot, ...values),
        appendDataSlot: (slot, ...values) => h.browser('APPEND_DATA_SLOT', slot, ...values),
        setDataSlotEmpty: () => h.browser('SET_DATA_SLOT_EMPTY'),
        updateText: newPage => { api.updated = true; return h.updateText(newPage); },
        addText: n => h.invoke('site', 'ADD_TEXT', [n]),
        proxy: (index, ...args) => h.browser('PROXY_FUNCTION', index, ...args),
        setTickertape: (speed, name) => (name === undefined ? h.browser('SET_TICKERTAPE', speed) : h.browser('SET_TICKERTAPE', speed, name)),
        disableButton: (slot, disabled) => h.browser('DISABLE_BUTTON', slot, disabled !== false),
        setPrices: (...args) => h.browser('SET_PRICES', ...args),
        getSelection: () => h.browser('GET_CURRENT_SELECTION'),
        goTo: target => {
          const t = String(target);
          const full = /\.|^WWW_/i.test(t) ? toFullUrl(t) : (t === 'PAGE1' ? siteId : siteId + '_S_' + t);
          // como func_8687 del script: cuenta como redirección (replaceState en el shell) y la
          // página que redirige no cuenta como compra (moneyNotice)
          h.redirectSeq = seq;
          h.inUpdate = (h.inUpdate || 0) + 1;
          try { return h.browser('GO_TO_WEBPAGE', full); } finally { h.inUpdate--; }
        },
        refresh: () => h.refillPage(),
        invoke: (path, method, args) => h.invoke(path, method, args),
        get: path => h.get(path),
        set: (path, prop, value) => h.set(path, prop, value),
        // ---- página contenedora ----
        note: text => h.setNote(siteId, text),
        log: (...a) => h.trace('provider', siteId, a),
      };
      return api;
    }

    // ---- entrada: ratón, rueda, teclado, táctil -----------------------------
    stagePoint(ev) {
      const r = this.player.getBoundingClientRect();
      return {
        nx: Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)),
        ny: Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height)),
        scale: r.width / STAGE_W,
      };
    }

    bindInput(el) {
      const target = this.o.container;
      let down = null;           // {x, y, id, moved, time}
      const move = ev => {
        if (!this.ready) return;
        const p = this.stagePoint(ev);
        this.lastMouse = p;
        this.mouseDirty = true;
        if (down && ev.pointerId === down.id && ev.pointerType !== 'mouse') {
          // arrastre táctil = desplazar la página 1:1
          const dy = (ev.clientY - down.lastY) / p.scale;
          down.lastY = ev.clientY;
          if (Math.abs(ev.clientY - down.y) > 8) down.moved = true;
          if (down.moved) {
            this.browser('SCROLL_WEBPAGE_PIXELS', -dy);
            down.vel = -dy;
          }
        }
      };
      target.addEventListener('pointermove', move);
      target.addEventListener('pointerdown', ev => {
        if (!this.ready || ev.button > 0) return;
        const p = this.stagePoint(ev);
        this.lastMouse = p;
        this.browser('SET_MOUSE_INPUT', p.nx, p.ny);
        down = { id: ev.pointerId, x: ev.clientX, y: ev.clientY, lastY: ev.clientY, moved: false, vel: 0, type: ev.pointerType };
        if (ev.pointerType === 'mouse') {
          // El navegador del juego selecciona al PULSAR (SET_INPUT_EVENT 1001)
          this.later(() => this.clickAt(p), 0);
        }
      });
      const up = ev => {
        if (!down || ev.pointerId !== down.id) return;
        const d = down; down = null;
        if (!this.ready) return;
        if (d.type === 'mouse') {
          this.browser('SET_INPUT_RELEASE_EVENT', 237);
          return;
        }
        if (!d.moved) {
          // toque = llevar el cursor ahí + clic + soltar
          const p = this.stagePoint(ev);
          this.later(() => { this.clickAt(p); this.browser('SET_INPUT_RELEASE_EVENT', 237); }, 0);
        } else if (Math.abs(d.vel) > 2) {
          this.flingPx = d.vel;       // inercia al soltar
        }
      };
      target.addEventListener('pointerup', up);
      target.addEventListener('pointercancel', up);
      target.addEventListener('wheel', ev => {
        if (!this.ready) return;
        ev.preventDefault();
        let dy = ev.deltaY;
        if (ev.deltaMode === 1) dy *= 40; else if (ev.deltaMode === 2) dy *= 600;
        // appinternet.sc: cada muesca suma ±200 a la velocidad (tope ±1000), *0.9 por frame
        const add = Math.sign(dy) * Math.min(200, Math.max(40, Math.abs(dy) * 2));
        if (Math.sign(this.scrollVel) !== Math.sign(add)) this.scrollVel = 0;
        this.scrollVel = Math.max(-1000, Math.min(1000, this.scrollVel + add));
      }, { passive: false });
      target.addEventListener('contextmenu', ev => ev.preventDefault());
      document.addEventListener('keydown', ev => this.onKey(ev));
      target.style.touchAction = 'none';
    }

    /**
     * Clic en un punto del escenario: coloca el cursor, hace el mismo hitTest que
     * el onEnterFrame del cursor del juego (así no depende de que haya pasado un
     * frame, importante en táctil) y manda SET_INPUT_EVENT(1001).
     */
    clickAt(p) {
      const nx = Math.min(p.nx, 0.987), ny = Math.min(p.ny, 0.962);   // topes de SET_MOUSE_INPUT
      this.browser('SET_MOUSE_INPUT', nx, ny);
      if (!this.get('browser.keyboardFocus')) this.browser('hitTestButtons', nx * STAGE_W, ny * STAGE_H);
      const site = this.state.siteId, page = this.state.page;
      const before = this.browser('GET_CURRENT_SELECTION');
      this.browser('SET_INPUT_EVENT', 1001);
      // appinternet.sc pregunta GET_CURRENT_SELECTION tras cada pulsación y reacciona
      // según la web (paginador de bleeter, empresa elegida en la bolsa...). Aquí:
      // provider.onSelect. La página nueva (si el clic navegó) se rellena después, en
      // una microtarea, así que el proveedor ya sabe qué se eligió.
      const sel = this.browser('GET_CURRENT_SELECTION');
      const picked = typeof sel === 'number' && sel > -1 ? sel : (typeof before === 'number' ? before : -1);
      this.lastSelection = picked;
      const provider = this.providers[site];
      if (!provider || !provider.onSelect || typeof sel !== 'number' || sel < 0) return;
      try {
        if (typeof provider === 'function') {
          if (provider.onSelect.call(this, this.ctx(site, page, false), sel) === true) this.updateText();
        } else {
          const api = this.pageApi(site, page, false);
          const r = provider.onSelect(sel, api);
          if (r === true && !api.updated) this.updateText();
        }
      } catch (e) { console.warn('[gtav-host] onSelect', site, e); }
    }

    onKey(ev) {
      if (!this.ready || ev.ctrlKey || ev.metaKey || ev.altKey) return;
      const t = ev.target;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      // Teclado del juego abierto = keyboardFocus no vacío (lo que mira el propio SET_PC_KEY).
      // No IS_KEYBOARD_ACTIVE: compara currentInterface == BrowserKeyBoard, que da true antes de
      // abrirlo nunca (undefined == undefined) y después para siempre (HIDE_KEYBOARD no limpia
      // currentInterface): Retroceso y las flechas iban a SET_PC_KEY y no hacían nada.
      const focus = this.get('browser.keyboardFocus');
      if (typeof focus === 'string' && focus !== '') {
        let key = null;
        if (ev.key === 'Backspace') key = 'BACKSPACE';
        else if (ev.key === 'Enter') key = 'ENTER';
        else if (ev.key === 'Escape') { this.browser('SET_INPUT_EVENT', 17); ev.preventDefault(); return; }
        else if (ev.key === ' ') key = ' ';
        else if (/^[a-z0-9.\-]$/i.test(ev.key)) key = ev.key.toUpperCase();
        if (key) {
          ev.preventDefault();
          if (key === 'BACKSPACE' || key === 'ENTER') {
            this.browser('SET_PC_KEY', key);
            this.browser('ENTER_TEXT', key, true);
          } else {
            this.browser('SET_PC_KEY', key);
          }
        }
        return;
      }
      // Fuera del teclado: flechas / AvPág como en el juego (±200 de velocidad)
      if (ev.key === 'ArrowDown' || ev.key === 'PageDown') { this.scrollVel = ev.key === 'PageDown' ? 1000 : 200; ev.preventDefault(); }
      else if (ev.key === 'ArrowUp' || ev.key === 'PageUp') { this.scrollVel = ev.key === 'PageUp' ? -1000 : -200; ev.preventDefault(); }
      else if (ev.key === 'Backspace') {
        // El shell usa el historial de la página (history.back) para que Retroceso y
        // su botón "atrás" hagan lo mismo; sin shell, GO_BACK del navegador del juego
        if (this.o.onBackKey) this.o.onBackKey(); else this.back();
        ev.preventDefault();
      }
    }

    // Bucle por frame: ratón (1 llamada por frame), inercia de la rueda, cursor CSS
    _raf() {
      requestAnimationFrame(this._raf);
      if (!this.ready) return;
      if (this.mouseDirty && this.lastMouse) {
        this.mouseDirty = false;
        this.browser('SET_MOUSE_INPUT', this.lastMouse.nx, this.lastMouse.ny);
      }
      if (this.scrollVel !== 0) {
        this.scrollVel *= 0.9;
        if (Math.abs(this.scrollVel) < 5) this.scrollVel = 0;
        this.browser('SET_ANALOG_STICK_INPUT', 0, 0, this.scrollVel, true);
      }
      if (this.flingPx) {
        this.browser('SCROLL_WEBPAGE_PIXELS', this.flingPx);
        this.flingPx *= 0.92;
        if (Math.abs(this.flingPx) < 0.5) this.flingPx = 0;
      }
      this.frame = (this.frame || 0) + 1;
      if (this.o.hideGameCursor && this.frame % 6 === 0) {
        const st = this.get('browser.cursorState');
        const css = st === 'HAND' ? 'pointer' : st === 'TEXT' ? 'text' : st === 'BUSY' ? 'progress' : 'default';
        if (this.o.container.style.cursor !== css) this.o.container.style.cursor = css;
      }
    }
  }
  Host.providers = {};

  // ════════════════════════════════════════════════════════════════════════
  // Funciones que la película llama con ExternalInterface.call(...)
  // Reciben los argumentos de GameInterface.call SIN el nombre del método.
  // Los TextField / MovieClip llegan como "<tf:/ruta>" / "<mc:/ruta>".
  // Para escribir en un argumento se devuelve {ops:[[índice, prop, valor]]},
  // donde índice cuenta desde el nombre del método (0) como en `arguments`.
  // ════════════════════════════════════════════════════════════════════════
  const noop = name => function () { if (H) H.trace('call', name, [...arguments]); };
  const api = {
    // Textos ---------------------------------------------------------------
    SET_TEXT_WITH_TRANSLATION(type, label, field, isHTML) {
      if (!H) return null;
      const raw = H.text(label);
      let value = raw == null ? (H.o.missingText === 'empty' ? '' : String(label)) : formatGxt(raw, !!isHTML);
      // Categorías de eyefind ("MONEY<BR>AND SERVICES"): la web las pide en texto plano a un
      // campo oculto y hace .text.split("<BR>").join(" ") para el "Results for:" de SEARCH
      // (WWW_EYEFIND_INFO.as:371). El juego deja el <BR> literal en .text; aquí también.
      if (raw != null && !isHTML && KEEP_BR_LABELS.test(String(label))) value = formatGxt(String(raw).replace(/<br\s*\/?>/gi, '\u0002'), false).replace(/\u0002/g, '<BR>');
      // Si falta y la tabla completa aún no llegó, se apunta para rellenarlo luego
      if (raw == null && !H.fallbackLoaded) H.unfilled.set(String(field), { label, html: !!isHTML });
      else H.unfilled.delete(String(field));
      H.trace('call', 'SET_TEXT_WITH_TRANSLATION', [type, label, field, isHTML], value);
      return { ops: [[3, isHTML ? 'htmlText' : 'text', value]] };
    },
    // Streaming de películas y texturas ------------------------------------
    REQUEST_GFX_STREAM(type, uid, filename, requester) {
      if (!H) return;
      H.trace('call', 'REQUEST_GFX_STREAM', [type, uid, filename, requester]);
      const siteId = String(filename).toUpperCase();
      const ok = !H.knownSites || H.knownSites.has(siteId);
      // Registro para retryStream (red de seguridad si el navegador acaba en su página de error)
      const rec = { uid, siteId, ok, page: null, ready: false, retry: H.retryTarget === siteId, t: Date.now() };
      H.retryTarget = null;
      H.streams.push(rec);
      if (H.streams.length > 6) H.streams.shift();
      if (ok) H.ensureProvider(siteId, false);            // su proveedor, en paralelo
      // El motor responde después, nunca dentro de la llamada. Microtarea (no
      // setTimeout): así el pingTimer de 3 s del navegador nunca gana la carrera.
      soon(() => {
        rec.page = H.get('browser.pageName');             // página pedida (por si hay que reintentar)
        if (typeof rec.page !== 'string') rec.page = null;
        H.browser(ok ? 'STREAM_RESPONSE' : 'STREAM_RESPONSE_FAILED', uid, siteId);
        // page 'ERROR' en eyefind = la página de error del navegador (SHOW_ERROR_PAGE)
        H.emit('loading', { siteId, domain: idToText(siteId), ok, page: rec.page, error: siteId === ERROR_SITE && rec.page === 'ERROR' });
      });
    },
    GFX_READY(type, clipName) {
      if (!H) return;
      H.trace('call', 'GFX_READY', [type, clipName]);
      const rec = H.streams[H.streams.length - 1];
      if (rec && rec.siteId === String(clipName).toUpperCase()) rec.ready = true;
      // appinternet.sc: HAS_SCALEFORM_CONTAINER_MOVIE_LOADED_INTO_PARENT -> INITIALISE_WEBSITE
      // (el shim avisa después con HOST_PAGE_SHOWN)
      soon(() => H.browser('INITIALISE_WEBSITE'));
    },
    /** Lo llama el shim al final de cada INITIALISE_WEBSITE (carga de web o cambio de página). */
    HOST_PAGE_SHOWN(fullURL, pageName, clipName, pageExists, dynamic) {
      if (!H) return;
      H.trace('call', 'HOST_PAGE_SHOWN', [fullURL, pageName, clipName, pageExists, dynamic]);
      const redirect = !!H.inUpdate;                     // la web saltó sola durante UPDATE_TEXT
      if (redirect) H.redirectSeq = H.pageSeq;           // la página que se rellenaba no se queda (moneyNotice)
      soon(() => H.onPageShown(fullURL, dynamic, redirect));
    },
    REQUEST_REMOVAL: noop('REQUEST_REMOVAL'),
    REQUEST_TXD_AND_ADD_REF(type, requester, txd, uniqueId, addRef) {
      if (!H) return;
      H.trace('call', 'REQUEST_TXD_AND_ADD_REF', [type, requester, txd, uniqueId, addRef]);
      // Las texturas ya están servidas como PNG: se confirma enseguida (en el
      // juego, unos frames después). Las peticiones de un mismo frame van en
      // tanda: primero el shim pasa los TextField de la web a IMGP (para ver
      // el <img src='img://…'> que la web escribe al recibir TXD_HAS_LOADED).
      (H.txdQueue = H.txdQueue || []).push([txd, uniqueId]);
      if (H.txdQueue.length === 1) {
        soon(() => {
          const q = H.txdQueue; H.txdQueue = [];
          H.invoke('host', 'patchSite', []);
          q.forEach(([t, id]) => H.browser('TXD_HAS_LOADED', t, true, id));
        });
      }
    },
    REMOVE_TXD_REF: noop('REMOVE_TXD_REF'),
    // Estado que el script consulta ------------------------------------------
    SET_CURRENT_WEBSITE_ID(type, id) {
      if (!H) return;
      H.state.websiteId = id;
      H.trace('call', 'SET_CURRENT_WEBSITE_ID', [type, id]);
    },
    SET_CURRENT_WEBPAGE_ID(type, id) {
      if (!H) return;
      H.state.pageId = id;
      H.trace('call', 'SET_CURRENT_WEBPAGE_ID', [type, id]);
    },
    SET_GLOBAL_ACTIONSCRIPT_FLAG(type, index, value) {
      if (!H) return;
      H.flags[index] = value;
      H.trace('call', 'SET_GLOBAL_ACTIONSCRIPT_FLAG', [type, index, value]);
      // flag 5 = el navegador pide cerrarse (botón salir): volvemos al índice
      if (index === 5 && value === 1) H.emit('close', {});
    },
    // Configuración de pantalla y colores ------------------------------------
    SET_DISPLAY_CONFIG(type, cfg) {
      if (H) H.trace('call', 'SET_DISPLAY_CONFIG', [type]);
      const v = { screenWidth: 1280, screenHeight: 720, safeTop: 0.05, safeBottom: 0.95, safeLeft: 0.05, safeRight: 0.95,
        isWideScreen: true, isCircleAccept: false, isHiDef: true, isAsian: false, actualWidth: 1280, actualHeight: 720 };
      return { ops: Object.keys(v).map(k => [2, k, v[k]]) };
    },
    GET_HUD_COLOUR(type, colour) {
      const c = HUD_COLOURS[colour] || [255, 255, 255];
      if (H) H.trace('call', 'GET_HUD_COLOUR', [type, colour]);
      return { ops: [[3, 'r', c[0]], [3, 'g', c[1]], [3, 'b', c[2]], [3, 'a', 100]] };
    },
    // Sonido, teclado de consola, depuración: sin efecto en la web -----------
    PLAY_SOUND: noop('PLAY_SOUND'),
    SMARTGLASS_SHOW_KEYBOARD: noop('SMARTGLASS_SHOW_KEYBOARD'),
    SMARTGLASS_HIDE_KEYBOARD: noop('SMARTGLASS_HIDE_KEYBOARD'),
    SMARTGLASS_ENTER_TEXT: noop('SMARTGLASS_ENTER_TEXT'),
    BROWSER_TEXT_ENTERED: noop('BROWSER_TEXT_ENTERED'),
    DEBUG_PRINT_MEMORY_STATS: noop('DEBUG_PRINT_MEMORY_STATS'),
    FORCE_GARBAGE_COLLECTION: noop('FORCE_GARBAGE_COLLECTION'),
    DEBUG_LOG(type, msg) { if (H) H.trace('call', 'DEBUG_LOG', [type, msg]); },
    // Shim ------------------------------------------------------------------
    HOST_SHIM_LOADED(version) {
      encodeEmpty = Number(version) >= 3;
      if (H) { H.shimVersion = version; H.trace('call', 'HOST_SHIM_LOADED', [version]); }
    },
    HOST_BROWSER_READY(version, kind) {
      if (!H) return;
      H.trace('call', 'HOST_BROWSER_READY', [version, kind]);
      soon(() => H.onBrowserReady());
    },
    /** Atrás (-1) / adelante (1) de la barra del juego con shellHistory (shim v5, §2.12). */
    HOST_HISTORY(dir) {
      if (!H) return;
      H.trace('call', 'HOST_HISTORY', [dir]);
      soon(() => H.historyStep(Number(dir)));
    },
    /**
     * loadClip / loadMovie:
     *   "WWW_BLEETER_BIZ"         -> /v/www.bleeter.biz/www_bleeter_biz.swf
     *   "img://txd/tex" (imágenes) -> /v/_tex/txd/tex.png
     */
    HOST_RESOLVE_URL(url) {
      if (!H) return null;
      const s = String(url);
      let out = null;
      if (/^[A-Z0-9_]+$/.test(s)) out = H.siteSwfUrl(s);
      else if (/^img:\/\//i.test(s)) out = H.texUrl(s);
      H.trace('call', 'HOST_RESOLVE_URL', [s], out);
      return out;
    },
    /** El shim vio un htmlText con <img> (tf = ruta del TextField, src = img://txd/tex). */
    HOST_IMG(tf, src, shown) {
      if (H) H.trace('call', 'HOST_IMG', [tf, src, shown]);
    },
    /** La textura terminó de cargar (w/h en px del escenario) o falló (w = -1). */
    HOST_IMG_LOADED(clip, src, w, h, err) {
      if (!H) return;
      H.trace('call', 'HOST_IMG_LOADED', [clip, src, w, h, err]);
      H.emit('image', { clip, src, ok: w >= 0, width: w, height: h, url: H.texUrl(src) });
    },
  };

  // Llamadas que alguna web pudiera hacer y no están en el catálogo: dinero,
  // teléfono, estadísticas... Se registran y no hacen nada.
  const SAFE_NOOPS = ['SET_PLAYER_CASH', 'SPEND_CASH', 'BUY_ITEM', 'PHONE_CALL', 'SET_STAT', 'INCREMENT_STAT',
    'SEND_EMAIL', 'SET_WAYPOINT', 'OPEN_URL', 'TRACK_EVENT'];
  SAFE_NOOPS.forEach(n => { api[n] = function () { if (H) { H.trace('call', n, [...arguments]); H.emit('notice', { text: MONEY_NOTICE, call: n }); } }; });

  // Lo que devuelve cada función viaja a la película: cadenas vacías codificadas (toMovie)
  Object.keys(api).forEach(name => {
    const fn = api[name];
    global[name] = function () { return toMovie(fn.apply(this, arguments)); };
  });

  // ════════════════════════════════════════════════════════════════════════
  // Proveedores de datos para webs dinámicas (equivalen a func_8363 del script)
  // ════════════════════════════════════════════════════════════════════════
  const DAYS = ['BS_PH_SU', 'BS_PH_M', 'BS_PH_TU', 'BS_PH_W', 'BS_PH_TH', 'BS_PH_F', 'BS_PH_SA'];
  // Zonas del mapa (labels GXT de GET_NAME_OF_ZONE) y tiempos de eyefind
  const ZONES = ['DOWNT', 'ROCKF', 'VINE', 'DELPE', 'VESP', 'MIRR', 'DAVIS', 'SANDY', 'PALETO'];
  const WEATHER = [1, 1, 1, 2, 3, 4];     // 1 despejado, 2 nubes, 3 cubierto, 4 lluvia
  const pick = arr => arr[Math.floor(Math.random() * arr.length)];
  const gxtHtml = (c, label) => formatGxt(c.L(label), true);

  /** Primeras entradas de bleeter (grupo más reciente), como func_8488 */
  function bleeterGroups(host) {
    const b = host.data && host.data.bleeter;
    return b && b.groups && b.order && b.order.length ? b : null;
  }

  /**
   * Noticia, tiempo y zona de eyefind: UNA elección por sesión (sessionStorage, y en
   * memoria si no hay), para que la portada, "Read full article" (NEWS) y la búsqueda
   * enseñen lo mismo, como en el juego (allí la noticia es la del último evento de la
   * historia y no cambia entre páginas). Antes se sorteaba en cada página y el artículo
   * completo era otra noticia.
   */
  const EYEFIND_KEY = 'gtav-eyefind-choice';
  function eyefindChoice(host) {
    if (host.eyefindChoice) return host.eyefindChoice;
    const news = (host.data && host.data.news) || [];
    let ch = null;
    try { ch = JSON.parse(global.sessionStorage.getItem(EYEFIND_KEY) || 'null'); } catch (e) { ch = null; }
    const valid = s => s && typeof s === 'object' && WEATHER.includes(s.weather) && ZONES.includes(s.zone)
      && (!news.length || (news[s.ev] && news[s.ev].variants && news[s.ev].variants[s.v]));
    if (!valid(ch)) {
      ch = { weather: pick(WEATHER), zone: pick(ZONES), ev: -1, v: -1 };
      if (news.length) {
        ch.ev = Math.floor(Math.random() * news.length);
        ch.v = Math.floor(Math.random() * news[ch.ev].variants.length);
      }
      try { global.sessionStorage.setItem(EYEFIND_KEY, JSON.stringify(ch)); } catch (e) { /* sin almacenamiento: vale la de memoria */ }
    }
    host.eyefindChoice = ch;
    return ch;
  }

  /**
   * eyefind.info (func_8485): tiempo (slot 0), zona (2), día (3), noticia del día
   * (4 titular, 5 periódico 0-13, 6 texto; func_8489/8490) y los dos últimos
   * bleets (7, 8; func_8488). El juego elige la noticia según el avance de la
   * historia; aquí se elige una al azar de toda la historia, una vez por sesión.
   */
  Host.providers.WWW_EYEFIND_INFO = function (c) {
    const page = String(c.page || 'PAGE1');
    if (page !== 'PAGE1' && page !== 'SEARCH' && page !== 'NEWS') return false;
    const ch = eyefindChoice(c.host);
    c.slot(0, ch.weather);
    c.slot(2, c.L(ch.zone));
    c.slot(3, c.L(DAYS[new Date().getDay()]));
    const news = c.host.data && c.host.data.news;
    if (news && news.length && ch.ev >= 0) {
      const ev = news[ch.ev];
      const [k, paper] = ev.variants[ch.v];
      c.slot(4, gxtHtml(c, ev.hl + k));
      c.slot(5, paper);
      c.slot(6, gxtHtml(c, ev.s + k));
      // Carrera del logo: al entrar en NEWS (o volver a PAGE1) la web ya pintó la página una
      // vez con los datos viejos (INITIALISE_WEBSITE) y creó un "newsImageMC" con ese
      // periódico; el UPDATE_TEXT de ahora crea otro con el mismo nombre y su TXD_HAS_LOADED
      // va al primero (mcScope["newsImageMC"]), que ya tiene textura y lo ignora. Si el
      // periódico del clip viejo no es el de esta noticia, se quita antes de repintar.
      if (page !== 'SEARCH') {
        const mc = 'sitemc.CONTENT.' + page + '.newsImageMC';
        const want = c.host.get('site.newsOrgArray.' + paper);
        const have = c.host.get(mc + '.txd');
        if (typeof c.host.get(mc + '._name') === 'string' && have !== want) {
          c.host.trace('event', 'eyefind-news-logo', [have, want]);
          c.host.invoke(mc, 'removeMovieClip', []);
        }
      }
    }
    const b = bleeterGroups(c.host);
    if (b) {
      const first = b.groups[b.order[0]][0];
      c.slot(7, gxtHtml(c, 'BLE_' + first));
      c.slot(8, gxtHtml(c, 'BLE_' + (first + 1)));
    }
    return false;                                  // UPDATE_TEXT lo pone IS_SITE_DYNAMIC
  };

  /**
   * bleeter.biz (func_8424 -> 8429/8427): cada página muestra un grupo de bleets
   * (labels BLE_<n>, slots 2+) y el paginador (slot 1 = [actual, números…]).
   * Con la historia terminada están todos los grupos, el más reciente primero.
   */
  function bleeterSend(c, page) {
    const b = bleeterGroups(c.host);
    if (!b) return;
    const max = b.order.length;
    page = Math.max(1, Math.min(max, page));
    c.host.bleeterPage = page;
    const [from, to] = b.groups[b.order[page - 1]];
    for (let i = 0; from + i <= to; i++) c.slot(i + 2, gxtHtml(c, 'BLE_' + (from + i)));
    // func_8427: números de página de 10 en 10
    let lo, hi;
    if (page < 10) { lo = 1; hi = 10; } else { lo = Math.floor((page - 1) / 10) * 10 + 1; hi = lo + 10; }
    hi = Math.min(hi, max);
    const nums = [];
    for (let n = lo; n <= hi; n++) nums.push(n);
    c.host.bleeterNums = nums;
    c.slot(1, page, ...nums);
    c.call('DISABLE_BUTTON', 1, page === 1); c.call('DISABLE_BUTTON', 3, page === 1);
    c.call('DISABLE_BUTTON', 2, page === max); c.call('DISABLE_BUTTON', 4, page === max);
  }
  Host.providers.WWW_BLEETER_BIZ = function (c) {
    if (String(c.page || 'PAGE1') !== 'PAGE1') return false;
    // Al entrar desde otra web se empieza por la página 1 (func_8431: iLocal_502 = 1)
    bleeterSend(c, c.fresh ? 1 : (c.host.bleeterPage || 1));
    return false;
  };
  /** Paginador: 1 primera, 2 última, 3 anterior, 4 siguiente, 5… números */
  Host.providers.WWW_BLEETER_BIZ.onSelect = function (c, sel) {
    const b = bleeterGroups(c.host);
    if (!b || String(c.page || 'PAGE1') !== 'PAGE1') return false;
    const cur = c.host.bleeterPage || 1, nums = c.host.bleeterNums || [];
    let next = null;
    if (sel === 1) next = 1;
    else if (sel === 2) next = b.order.length;
    else if (sel === 3) next = cur - 1;
    else if (sel === 4) next = cur + 1;
    else if (sel >= 5 && sel < 5 + nums.length) next = nums[sel - 5];
    if (next == null || next === cur || next < 1 || next > b.order.length) return false;
    bleeterSend(c, next);
    c.call('SCROLL_WEBPAGE_PIXELS', -100000);
    return true;                                   // UPDATE_TEXT
  };

  /**
   * Webs de vehículos: sin SET_PRICES no enseñan ningún vehículo. Los precios del modo
   * historia salen de appinternet.sc (v/scriptdata/ -> host_data.json).
   * Hay dos generaciones de estas webs y cada una tiene SUS ids:
   *  - la actual (update.rpf; clase VehicleWebsite): "vehiclePrices", ids del script actual;
   *  - la de 2013 (web_x64b, ?version=2013; sin VehicleWebsite, tabla propia vehicleData /
   *    carNames): "vehiclePrices2013", precios del script base (x64b) con los ids de cada web
   *    de 2013 y -1 explícito en lo que no se vende (port_vehicle_prices_2013.py). Con la
   *    tabla actual, warstock 2013 enseñaba "Marshall" con foto provisional y el precio del
   *    Dubsta 6x6 (id 29), y elitas 2013 todo corrido un puesto.
   * Un precio texto ("ITEM_FREE") va traducido, como el componente de texto del script.
   */
  function vehicleSite(c) {
    const current = c.host.get('site.className') === 'VehicleWebsite';
    const all = current ? c.host.vehiclePrices : (c.host.data && c.host.data.vehiclePrices2013);
    const table = all && all[c.siteId];
    if (!table) return false;
    if (current && c.host.get('site.pricesSet') === true) return false;   // ya los tiene
    c.host.trace('event', 'vehicle-prices', [c.siteId, current ? 'actual' : '2013', Object.keys(table).length]);
    Object.keys(table).forEach(id => {
      const p = table[id];
      c.call('SET_PRICES', Number(id), typeof p === 'string' ? c.L(p) : p);
    });
    return true;                                                  // repintar
  }
  ['WWW_LEGENDARYMOTORSPORT_NET', 'WWW_SOUTHERNSANANDREASSUPERAUTOS_COM', 'WWW_PANDMCYCLES_COM',
    'WWW_ELITASTRAVEL_COM', 'WWW_DOCKTEASE_COM', 'WWW_WARSTOCK_D_CACHE_D_AND_D_CARRY_COM']
    .forEach(id => { Host.providers[id] = vehicleSite; });

  // ════════════════════════════════════════════════════════════════════════
  // API pública
  // ════════════════════════════════════════════════════════════════════════
  /** 'www.bawsaq.com', 'bawsaq.com', 'lcn-exchange.com', 'WWW_BAWSAQ_COM' -> 'WWW_BAWSAQ_COM' */
  function siteKey(key) {
    const full = toFullUrl(key);
    return full ? splitFullUrl(full).siteId : null;
  }
  /**
   * Registra el proveedor de datos de una web (lo que en el juego hace appinternet.sc
   * para ella). provider = {onPage(pageName, api), onSelect?(selection, api), clearSlots?}
   * o una función (formato antiguo: fn(ctx)). Ver docs/gta-v.md, "Host and providers".
   */
  function registerProvider(domainOrSiteId, provider) {
    const siteId = siteKey(domainOrSiteId);
    if (!siteId) throw new Error('registerProvider: web desconocida ' + domainOrSiteId);
    if (!provider || (typeof provider !== 'function' && typeof provider.onPage !== 'function')) {
      throw new Error('registerProvider: falta onPage(pageName, api) en ' + siteId);
    }
    Host.providers[siteId] = provider;
    if (H) H.trace('event', 'registerProvider', [siteId]);
    return siteId;
  }

  global.GTAVHost = {
    create(opts) {
      if (H) throw new Error('solo un host por página');
      H = new Host(opts);
      H.init().catch(e => { console.error(e); H.emit('error', e); });
      return H;
    },
    get current() { return H; },
    providers: Host.providers,
    registerProvider,
    idToText, textToId, toFullUrl, splitFullUrl, siteKey, joaat, formatGxt, substitute, fieldPath, MONEY_PAGE,
    STAGE_W, STAGE_H, CONTENT_Y, CONTENT_H, MONEY_NOTICE,
  };
  // Nombre corto para los archivos de proveedores (providers/<dominio>.js)
  global.GTAHOST = global.GTAVHost;
})(window);
