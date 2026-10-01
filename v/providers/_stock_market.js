/*!
 * providers/_stock_market.js — la bolsa del juego: www.bawsaq.com y www.lcn-exchange.com
 *
 * Port de lo que hace appinternet.sc con estas dos webs (func_8363 -> func_8443 y
 * func_8444…func_8471) sobre la tabla de empresas de stock_controller.sc:
 *   func_98   80 empresas: label del nombre (BSS_BSTR_n), label de las siglas y bolsa
 *             (f_8 = 1 BAWSAQ, 0 LCN); descripción en appinternet func_8458.
 *   func_95   titulares de la sección de noticias (<EMP>_P_SR/SF/RF_H), 3 por sección.
 *   func_94   precios de LCN: arranque al azar entre 15 y 290 y 16 pasos de x0.85…1.15
 *   func_29   con historial de 16 valores; cambio = precio - media, % = cambio / media.
 *
 * Lo que NO sale del juego (y lo avisa la página con api.note):
 *   * los precios y el historial: en el juego LCN los genera la partida y BAWSAQ los
 *     tomaba de las estadísticas en línea de Rockstar. LCN se genera con el mismo
 *     método del script (func_94/func_29) y una semilla fija: siempre sale igual.
 *     BAWSAQ usa los precios de las capturas del juego cuando se conocen (10 empresas;
 *     BAWSAQ_SEEN) y, para el resto, uno al azar entre $5 y $1,100 con semilla fija.
 *   * el dinero de cada personaje (Global_61482[personaje]).
 *   * la cartera: está vacía y las compras no se hacen (el host no gasta dinero).
 * Diferencias a propósito (docs/gta-v.md, "Host and providers"): la cinta usa el precio actual (el
 * script manda f_14[f_13], que en BAWSAQ vale 0 y en LCN es el valor más antiguo) y el
 * dinero se pone con SET_BAWSAQ_PLAYER_CASH directo (PROXY_FUNCTION daba "$0" en Ruffle).
 *
 * Lo cargan www.bawsaq.com.js y www.lcn-exchange.com.js (providers/index.json: deps).
 */
(function () {
  'use strict';
  const G = window.GTAHOST;
  if (!G || G.stockMarket) return;

  // ---- tabla de empresas (stock_controller.sc func_98, en su orden) ---------
  // [n del label del nombre, n del label de las siglas, 1 = BAWSAQ / 0 = LCN, BS_CO_<x>DESC]
  // CNT usa el mismo label (BSS_BSTR_16) para nombre y siglas, como en el juego.
  const RAW = [
    [0, 1, 1, 'AMU'], [2, 3, 1, 'BDG'], [4, 5, 0, 'BOL'], [6, 7, 1, 'BFA'], [8, 9, 1, 'BIN'],
    [10, 11, 1, 'BTR'], [12, 13, 1, 'BLE'], [14, 15, 1, 'BRU'], [16, 16, 1, 'CNT'], [17, 18, 1, 'CRE'],
    [19, 20, 1, 'DGP'], [21, 22, 1, 'WAP'], [23, 24, 1, 'FAC'], [25, 26, 0, 'FLC'], [27, 28, 0, 'HJK'],
    [29, 30, 1, 'FRT'], [31, 32, 0, 'AUG'], [33, 34, 0, 'BUL'], [35, 36, 0, 'HAF'], [37, 38, 0, 'SSS'],
    [39, 40, 1, 'LSC'], [41, 42, 1, 'LST'], [43, 44, 1, 'LTD'], [45, 46, 1, 'MAI'], [47, 48, 0, 'MAZ'],
    [49, 50, 1, 'PKW'], [51, 52, 0, 'ARK'], [53, 54, 1, 'PIS'], [55, 56, 1, 'PON'], [57, 58, 0, 'RAI'],
    [59, 60, 1, 'RON'], [61, 62, 1, 'SHT'], [63, 64, 1, 'SPU'], [65, 66, 1, 'TNK'], [67, 68, 1, 'WIW'],
    [69, 70, 1, 'UMA'], [71, 72, 1, 'VAP'], [73, 74, 1, 'VOM'], [75, 76, 1, 'WZL'], [77, 78, 1, 'WIZ'],
    [79, 80, 0, 'DEB'], [81, 82, 1, 'ZIT'], [83, 84, 1, 'SHK'], [85, 86, 1, 'MOL'], [87, 88, 1, 'PMP'],
    [89, 90, 1, 'GOT'], [91, 92, 1, 'EYE'], [93, 94, 0, 'EMU'], [95, 96, 0, 'BEN'], [97, 98, 0, 'GOL'],
    [99, 100, 0, 'BOM'], [101, 102, 0, 'BGR'], [103, 104, 0, 'CLK'], [105, 106, 0, 'BAN'], [107, 108, 0, 'DOP'],
    [109, 110, 0, 'ECL'], [111, 112, 0, 'FUS'], [113, 114, 0, 'GAS'], [115, 116, 0, 'GOP'], [117, 118, 0, 'GRU'],
    [119, 120, 0, 'KRP'], [121, 122, 0, 'LFI'], [123, 124, 0, 'MAX'], [125, 126, 0, 'POP'], [127, 128, 0, 'PRO'],
    [129, 130, 0, 'RWC'], [131, 132, 0, 'RIM'], [133, 134, 0, 'TBO'], [135, 136, 0, 'UPA'], [137, 138, 0, 'VAG'],
    [139, 140, 0, 'UNI'], [141, 142, 1, 'HVY'], [143, 144, 0, 'LOG'], [145, 146, 0, 'MER'], [147, 148, 0, 'RA1'],
    [149, 150, 0, 'RA2'], [151, 152, 1, 'SHR'], [153, 154, 1, 'HAL'], [155, 156, 0, 'MOR'], [157, 158, 0, 'BIL'],
  ];
  const STOCKS = RAW.map(([n, t, ex, d], i) => ({
    i, name: 'BSS_BSTR_' + n, ticker: 'BSS_BSTR_' + t, bawsaq: ex === 1, desc: 'BS_CO_' + d + 'DESC',
  }));

  // ---- noticias (stock_controller.sc func_95/func_96) ---------------------
  // [titular, índice de la empresa]. El cuerpo (<x>_C) no existe en ningún GXT: queda vacío.
  const NEWS = [
    ['ECL_P_SR_H', 55], ['ECL_P_SF_H', 55], ['ECL_P_RF_H', 55], ['BGR_P_SR_H', 51], ['BGR_P_SF_H', 51],
    ['CLK_P_SR_H', 52], ['CLK_P_SF_H', 52], ['CLK_P_RF_H', 52], ['BEN_P_SR_H', 48], ['BEN_P_SF_H', 48],
    ['BEN_P_RF_H', 48], ['FLC_P_SR_H', 13], ['FLC_P_SF_H', 13], ['FLC_P_RF_H', 13], ['PRO_P_SR_H', 64],
    ['PRO_P_SF_H', 64], ['PRO_P_RF_H', 64], ['UNI_P_SR_H', 70], ['UNI_P_SF_H', 70], ['UNI_P_RF_H', 70],
    ['KRP_P_SR_H', 60], ['KRP_P_SF_H', 60], ['KRP_P_RF_H', 60], ['FUS_P_SR_H', 56], ['FUS_P_SF_H', 56],
    ['FUS_P_RF_H', 56], ['GOP_P_SR_H', 58], ['GOP_P_SF_H', 58], ['GOP_P_RF_H', 58], ['BAN_P_SR_H', 53],
    ['BAN_P_SF_H', 53], ['BAN_P_RF_H', 53], ['MAX_P_SR_H', 62], ['MAX_P_SF_H', 62], ['MAX_P_RF_H', 62],
    ['GAS_P_SR_H', 57], ['GAS_P_SF_H', 57], ['GAS_P_RF_H', 57], ['GRU_P_SR_H', 59], ['GRU_P_SF_H', 59],
    ['GRU_P_RF_H', 59], ['PMP_P_SR_H', 44], ['PMP_P_SF_H', 44], ['PMP_P_RF_H', 44],
  ];
  // Titular de la portada que elige func_8466 con la historia terminada: el script
  // recorre sus casos y, con las misiones de Lester hechas, acaba siempre en este
  // (func_92(16): Lifeinvader se recupera tras la muerte de Jay Norris).
  const FRONT_STORY = 'LFI_P_USR_H';
  const SECTIONS = ['BS_NP_GENNEWS', 'BS_NP_CITNEWS', 'BS_NP_MONNEWS', 'BS_NP_TECNEWS'];
  const NEWS_PAGE = { NEWS: 0, NEWS_CITY: 1, NEWS_MONEY: 2, NEWS_TECHNOLOGY: 3 };
  const DAYS = ['BS_PH_SU', 'BS_PH_M', 'BS_PH_TU', 'BS_PH_W', 'BS_PH_TH', 'BS_PH_F', 'BS_PH_SA'];
  const HOURS = ['BS_PH_5', 'BS_PH_4', 'BS_PH_3', 'BS_PH_2', 'BS_PH_1', 'BS_PH_0'];
  const LIST_START = 15;           // Global_76764: los valores del listado empiezan en el slot 15

  // Dinero de cada personaje (Global_61482): inventado; el mismo que el saldo del banco
  // (_player.js, que index.json carga antes; si faltara, estos valores).
  const CASH = (G.playerData && G.playerData.cash) || [1286450, 326480, 587105];   // Michael, Franklin, Trevor

  // ---- precios: mismo método que el script, semilla fija --------------------
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  // BAWSAQ: precios que se ven en las capturas del juego (wiki, Bawsaq.com-GTAV.png y la
  // ficha de Ammu-Nation), por índice de STOCKS. El resto sale al azar entre $5 y $1,100
  // (la misma franja que en esas capturas: de BDG 6.15 a BIN 1079.17).
  const BAWSAQ_SEEN = { 0: 998.22, 1: 6.15, 43: 792.64, 3: 599.61, 4: 1079.17, 6: 999.59, 7: 750, 5: 491.19, 8: 477.98, 9: 432.63 };
  let QUOTES = null;
  function quotes() {
    if (QUOTES) return QUOTES;
    const rnd = mulberry32(20130917);                       // salida del juego: 17-9-2013
    const range = (a, b) => a + (b - a) * rnd();
    const rndB = mulberry32(20131001);                      // GTA Online: 1-10-2013
    const rangeB = (a, b) => a + (b - a) * rndB();
    QUOTES = STOCKS.map(s => {
      // func_94 + func_29: 16 anotaciones en el historial y un paso x0.85…1.15 entre cada una
      let p = range(15, 290);
      const hist = [];
      for (let k = 0; k < 16; k++) {
        hist.push(p);
        let lo = 0.85, hi = 1.15;
        if (p < 5) lo = 1.1; else if (p < 10) lo = 0.95; else if (p > 285) hi = 0.97; else if (p > 270) hi = 1.05;
        p = Math.min(Math.max(Math.abs(p * range(lo, hi)), 3.5), 290);
      }
      const q = { hist, high: Math.max(...hist), low: Math.min(...hist) };
      if (s.bawsaq) {
        // BAWSAQ (func_5/func_8460): precio actual + 5 horas de historial. En el juego
        // venían de Rockstar cada hora (sin el tope de 290 de LCN) y se movían poco: en la
        // ficha de Ammu-Nation de la wiki, 998.11…998.25 en 5 horas. Aquí: el precio de las
        // capturas si se conoce y 5 horas hacia atrás con pasos de x0.985…1.015. Otro
        // generador (rndB) para que los precios de LCN no cambien.
        for (let k = 0; k < 5; k++) range(0, 1);             // la secuencia de LCN, como antes
        const r2 = v => Math.round(v * 100) / 100;
        q.price = BAWSAQ_SEEN[s.i] || r2(Math.exp(rangeB(Math.log(5), Math.log(1100))));
        q.hours = [];
        let h = q.price;
        for (let k = 4; k >= 0; k--) { h = r2(Math.max(h / rangeB(0.985, 1.015), 3.5)); q.hours[k] = h; }
        const avg = q.hours.reduce((a, b) => a + b, 0) / 5;
        q.change = q.price - avg;
        q.high = Math.max(q.price, ...q.hours);
        q.low = Math.min(q.price, ...q.hours);
        q.pct = q.change / avg * 100;
      } else {
        // LCN (func_93/func_29): el último del historial; cambio contra la media de 16
        q.price = hist[15];
        const avg = hist.reduce((a, b) => a + b, 0) / 16;
        q.change = q.price - avg;
        q.pct = q.change / avg * 100;
      }
      return q;
    });
    return QUOTES;
  }
  const quote = i => quotes()[i];

  // Titulares de cada sección (func_95: 3 por sección, sin repetir, al azar -> semilla fija)
  let SECTION_NEWS = null;
  function sectionNews() {
    if (SECTION_NEWS) return SECTION_NEWS;
    const rnd = mulberry32(5000);
    const pool = NEWS.slice();
    for (let k = pool.length - 1; k > 0; k--) { const j = Math.floor(rnd() * (k + 1)); [pool[k], pool[j]] = [pool[j], pool[k]]; }
    SECTION_NEWS = [0, 1, 2, 3].map(c => pool.slice(c * 3, c * 3 + 3).map(n => n[0]));
    return SECTION_NEWS;
  }

  // ---- el proveedor -----------------------------------------------------------
  function makeProvider(bawsaq) {
    const listed = () => STOCKS.filter(s => s.bawsaq === bawsaq && quote(s.i).price > 0);
    const T = (api, label) => api.text(label);
    // func_17 con un label que puede no existir (cuerpos de noticia): vacío, sin apuntarlo
    const T0 = (api, label) => (api.has(label) ? api.text(label) : '');
    const slot = (api, n, ...v) => api.setDataSlot(n, ...v);

    function movers() {
      // func_8468: las 5 de esta bolsa con más |cambio|, de mayor a menor
      return listed().slice().sort((a, b) => Math.abs(quote(b.i).change) - Math.abs(quote(a.i).change)).slice(0, 5);
    }
    function tabs(api) {                                      // func_8471(0)
      ['BS_WB_HOME', 'BS_WB_NEWS', 'BS_WB_MARK', 'BS_WB_MSTOCK'].forEach((l, k) => slot(api, k, T(api, l)));
    }
    function dateline(api, n) { slot(api, n, T(api, 'BS_WB_DATELINE')); }   // func_8470 ("TEMP DATELINE", en un campo oculto)
    function highLabel(api) { return T(api, bawsaq && api.has('BS_WB_HIGHFH') ? 'BS_WB_HIGHFH' : 'BS_WB_HIGH'); }
    function lowLabel(api) { return T(api, bawsaq && api.has('BS_WB_LOWFH') ? 'BS_WB_LOWFH' : 'BS_WB_LOW'); }

    /** func_8461 / func_8460: etiquetas y valores de la gráfica en dos slots */
    function graph(api, s, labelsSlot, valuesSlot) {
      const q = quote(s.i);
      if (s.bawsaq) {
        // últimas 5 horas: cada punto se acerca al precio actual (func_8460) + el actual
        slot(api, labelsSlot, ...HOURS.map(l => T(api, l)), 1.5);
        const pts = q.hours.map((v, k) => (1 - k * 0.2) * v + k * 0.2 * q.price);
        slot(api, valuesSlot, ...pts, q.price);
      } else {
        // última semana: 7 días a partir de "hoy + 2" y los 16 valores del historial
        let d = (new Date().getDay() + 2) % 7;
        const days = [];
        for (let k = 0; k < 7; k++) { days.push(T(api, DAYS[d])); d = (d + 1) % 7; }
        slot(api, labelsSlot, ...days, 2);
        slot(api, valuesSlot, ...q.hist);
      }
    }
    function listHeaders(api, first, portfolio) {             // func_8465
      slot(api, first, T(api, 'BS_WB_NAMEH'));
      slot(api, first + 1, T(api, 'BS_WB_CURPRICH'));
      slot(api, first + 2, T(api, 'BS_WB_VOLU'));
      slot(api, first + 3, T(api, portfolio ? 'BS_WB_RETP' : 'BS_WB_MOVH'));
    }
    function stockOf(api) {
      const st = api.state;
      const all = listed();
      if (st.stock == null || !STOCKS[st.stock] || STOCKS[st.stock].bawsaq !== bawsaq) st.stock = (movers()[0] || all[0]).i;
      return STOCKS[st.stock];
    }
    function cash(api) { return CASH[api.character] || CASH[0]; }

    // ---- una función por página (switch de func_8443) ----
    const PAGES = {
      PAGE1(api) {
        tabs(api); dateline(api, 4);
        slot(api, 5, T(api, 'BS_NP_GENNEWS'));
        const main = sectionNews()[0];
        slot(api, 6, api.has(FRONT_STORY) ? T(api, FRONT_STORY) : T(api, main[0]));
        slot(api, 8, T(api, main[1]));
        slot(api, 10, T(api, main[2]));
        const top = movers();
        top.forEach((s, k) => { const q = quote(s.i); slot(api, 22 + k, T(api, s.ticker), q.price, q.change); });
        if (top[0]) graph(api, top[0], 27, 28);
      },
      LISTINGS(api) {
        tabs(api); dateline(api, 4);
        slot(api, 5, T(api, 'BS_WB_MLIST'));
        slot(api, 6, T(api, 'BS_WB_PERCHA'));
        slot(api, 11, T(api, 'BS_WB_STCKLST'));
        slot(api, 12, T(api, 'BS_WB_LCSTWT'));
        listHeaders(api, 7, false);
        // func_8464: [precio, volumen 55555, cambio, siglas, nombre] + APPEND % (queda en [5])
        listed().forEach((s, k) => {
          const q = quote(s.i);
          slot(api, LIST_START + k, q.price, 55555, q.change, T(api, s.ticker), T(api, s.name));
          api.appendDataSlot(LIST_START + k, q.pct);
        });
      },
      STOCK_PORTFOLIO(api) {
        // func_8463 no añade nada: el personaje no tiene acciones -> la web salta sola a
        // STOCK_PORTFOLIO_EMPTY (POPULATE_TEXT: dataProviderUI.length == 15)
        tabs(api); dateline(api, 4);
        slot(api, 5, T(api, 'BS_WB_MSTOCK'));
        slot(api, 6, T(api, 'BS_WB_BUYPRC'));
        listHeaders(api, 7, true);
        slot(api, 11, T(api, 'BS_TL_PROF'));
        slot(api, 12, T(api, 'BS_TL_SEARCH'));
        slot(api, 13, T(api, 'BS_TL_GOSTRT'));
        slot(api, 14, T(api, 'BS_TL_SELLALL'));
      },
      STOCK_PORTFOLIO_EMPTY(api) {
        tabs(api); dateline(api, 4);
        slot(api, 5, T(api, 'BS_WB_SOR'));                     // func_8448(5)
        slot(api, 6, T(api, 'BS_WB_GOBUY'));
      },
      STOCK_VIEW(api) {                                        // func_8457
        const s = stockOf(api), q = quote(s.i);
        api.state.shares = 0;
        graph(api, s, 37, 38);
        tabs(api);
        slot(api, 4, T(api, 'BS_WB_STCKINF'));
        slot(api, 5, T(api, s.name));
        slot(api, 6, q.price);
        slot(api, 7, T(api, 'BS_WB_VOLU'));
        slot(api, 8, 777777);
        slot(api, 9, q.change);
        slot(api, 10, T(api, s.ticker));
        slot(api, 11, T(api, s.bawsaq ? 'BS_PH_HRS' : 'BS_PH_GR'));
        slot(api, 17, T(api, 'BS_BU_BUY'));
        slot(api, 18, '');                                     // sin acciones: SELL oculto
        slot(api, 19, T(api, s.desc));
        slot(api, 20, T(api, 'BS_PH_F'));
        slot(api, 21, T(api, s.desc));
        slot(api, 22, q.pct);
        slot(api, 23, highLabel(api));
        slot(api, 24, q.high);
        slot(api, 25, lowLabel(api));
        slot(api, 26, q.low);
        slot(api, 27, T(api, 'BS_WB_VAL'));
        slot(api, 28, q.price);
        slot(api, 33, T(api, 'BS_WB_VOLU'));
        slot(api, 34, 88888);
        slot(api, 29, T(api, 'BS_H_LST'));
        slot(api, 30, q.price - q.change);
        slot(api, 31, T(api, 'BS_H_CHNG'));
        slot(api, 32, q.change);
        slot(api, 35, T(api, 'BS_H_OWNED'));
        slot(api, 36, 0);
      },
      STOCK_TRADE_BUY(api) {                                   // func_8455
        tabs(api);
        const s = stockOf(api), q = quote(s.i);
        const max = Math.floor(cash(api) / q.price);
        const n = api.state.shares = Math.max(0, Math.min(api.state.shares || 0, max));
        api.state.trade = 'buy';
        slot(api, 5, T(api, 'BS_BU_BUY'));
        slot(api, 6, T(api, s.ticker));
        slot(api, 7, T(api, s.name));
        slot(api, 8, q.price);
        slot(api, 9, T(api, 'BS_WB_VOLU'));
        slot(api, 10, 99999);
        slot(api, 11, q.change);
        slot(api, 12, n);
        slot(api, 13, T(api, 'BS_TL_SHARES'));
        slot(api, 14, Math.min(n * q.price, cash(api)));
        slot(api, 15, T(api, 'BS_TL_GSUM'));
        slot(api, 16, 0);
        slot(api, 17, T(api, 'BS_TL_SHOWN'));
        slot(api, 18, 0);
        slot(api, 19, T(api, 'BS_TL_IVEST'));
        slot(api, 20, T(api, 'BS_BU_BUY'));
        slot(api, 21, T(api, s.ticker));
        slot(api, 22, T(api, s.ticker));
        slot(api, 23, q.pct);
        slot(api, 24, highLabel(api));
        slot(api, 25, q.high);
        slot(api, 26, lowLabel(api));
        slot(api, 27, q.low);
        slot(api, 28, T(api, 'BS_WB_VAL'));
        slot(api, 29, q.price);
      },
      STOCK_TRADE_SELL(api) {                                  // func_8452 (sin acciones: todo a 0)
        tabs(api);
        const s = stockOf(api), q = quote(s.i);
        api.state.shares = 0;
        api.state.trade = 'sell';
        slot(api, 5, T(api, 'BS_BU_SELL'));
        slot(api, 6, T(api, s.ticker));
        slot(api, 7, T(api, s.name));
        slot(api, 8, q.price);
        slot(api, 9, T(api, 'BS_WB_VOLU'));
        slot(api, 10, 676767);
        slot(api, 11, q.change);
        slot(api, 12, 0);
        slot(api, 13, T(api, 'BS_TL_SHARES'));
        slot(api, 14, 0);
        slot(api, 15, T(api, 'BS_TL_SHOWN'));
        slot(api, 16, 0);
        slot(api, 17, T(api, 'BS_TL_IVEST'));
        slot(api, 18, 0);
        slot(api, 19, T(api, 'BS_TL_PROF'));
        slot(api, 20, T(api, 'BS_BU_SELL'));
        slot(api, 21, T(api, s.ticker));
        slot(api, 22, T(api, s.ticker));
        slot(api, 23, q.pct);
        slot(api, 24, highLabel(api));
        slot(api, 25, q.high);
        slot(api, 26, lowLabel(api));
        slot(api, 27, q.low);
        slot(api, 28, T(api, 'BS_WB_VAL'));
        slot(api, 29, q.price);
        slot(api, 30, T(api, 'BS_TL_SELLALL'));
      },
      STOCK_TRADE_CONFIRM(api) {                               // func_8451
        tabs(api);
        const s = stockOf(api), q = quote(s.i), buy = api.state.trade !== 'sell';
        const n = api.state.shares || 0;
        slot(api, 5, T(api, buy ? 'BS_WB_BS' : 'BS_WB_SS'));
        slot(api, 6, T(api, s.ticker));
        slot(api, 7, T(api, 'BS_TL_SHARES'));
        slot(api, 8, q.price);
        slot(api, 9, T(api, 'BS_WB_VOLU'));
        slot(api, 10, 787878);
        slot(api, 11, q.change);
        slot(api, 13, n);
        slot(api, 14, T(api, 'BS_WB_CONFTR'));
        slot(api, 15, n * q.price);
        slot(api, 16, T(api, 'BS_WB_COST'));
        slot(api, 18, T(api, 'BS_WB_CONF'));
        slot(api, 19, T(api, 'BS_WB_CAN'));
        slot(api, 20, q.pct);
        slot(api, 21, highLabel(api));
        slot(api, 22, q.high);
        slot(api, 23, lowLabel(api));
        slot(api, 24, q.low);
        slot(api, 25, T(api, 'BS_WB_VAL'));
        slot(api, 26, q.price);
      },
      CONFIRMED(api) {                                         // func_8450 (la cartera no cambia)
        tabs(api);
        const s = stockOf(api), q = quote(s.i), buy = api.state.trade !== 'sell';
        const n = api.state.shares || 0;
        slot(api, 4, T(api, 'BS_WB_CONTBU'));
        slot(api, 5, T(api, buy ? 'BS_WB_BS' : 'BS_WB_SS'));
        slot(api, 6, T(api, s.ticker));
        slot(api, 7, T(api, 'BS_TL_SHARES'));
        slot(api, 9, n);
        slot(api, 10, T(api, 'BS_WB_TRCOM'));
        slot(api, 11, n * q.price);
        slot(api, 12, T(api, buy ? 'BS_WB_COST' : 'BS_WB_PROLOS'));
        slot(api, 13, q.price);
        slot(api, 14, q.change);
        slot(api, 15, q.pct);
        slot(api, 16, highLabel(api));
        slot(api, 17, q.high);
        slot(api, 18, lowLabel(api));
        slot(api, 19, q.low);
        slot(api, 20, T(api, 'BS_WB_VOLU'));
        slot(api, 21, 898989);
        slot(api, 22, T(api, 'BS_WB_VAL'));
        slot(api, 23, q.price);
        api.state.shares = 0;
      },
      ERROR(api) {                                             // case 15 (ni Online ni cartera llena)
        tabs(api);
        slot(api, 4, '');
        slot(api, 5, T(api, 'BS_WB_FAI1'));
        slot(api, 6, T(api, 'BS_WB_FAI2'));
      },
      STOCK_PORTFOLIO_SELL_D_ALL(api) {                        // case 16 (sin acciones: 0 de beneficio)
        tabs(api);
        slot(api, 4, ' ');
        slot(api, 5, T(api, 'BS_SL_ALLSHRS'));
        slot(api, 6, api.text('BS_YU_SURE', { label: 'BS_TL_PROF' }, 0));
        slot(api, 7, T(api, 'BS_WB_CONFTRSH'));
        slot(api, 8, T(api, 'BS_WB_CAN'));
      },
    };
    Object.keys(NEWS_PAGE).forEach(name => {
      PAGES[name] = api => {                                   // func_8447(sección)
        const c = NEWS_PAGE[name], items = sectionNews()[c];
        tabs(api);
        SECTIONS.forEach((l, k) => slot(api, 4 + k, T(api, l)));
        slot(api, 8, T(api, SECTIONS[c]));
        items.forEach((hl, k) => {
          slot(api, 9 + 2 * k, T(api, hl));
          slot(api, 10 + 2 * k, T0(api, hl.replace(/_H$/, '_C')));
        });
      };
    });

    /** func_8444: la cinta de cotizaciones (al entrar en la web) */
    function tickertape(api) {
      api.setDataSlotEmpty();
      listed().forEach((s, k) => { const q = quote(s.i); slot(api, k, q.price, q.change, q.pct, T(api, s.ticker)); });
      api.setTickertape(0.5);
      api.setDataSlotEmpty();
    }

    const labelsUsed = ['BS_WB_HOME', FRONT_STORY].concat(NEWS.map(n => n[0]), STOCKS.map(s => s.name), STOCKS.map(s => s.ticker));
    return {
      async onPage(page, api) {
        await api.need(labelsUsed);                            // por si falta alguno en strings.json
        if (!api.isCurrent()) return;
        api.note(bawsaq
          ? 'Precios, gráficas y dinero del personaje inventados (en el juego BAWSAQ los traía de los servidores de Rockstar; los de AMU, BDG, BET, BFA, BIN, BLE, BRU, BTR, CNT y CRE son los de las capturas del juego). Empresas, siglas y titulares son los del juego. Las compras no se hacen.'
          : 'Precios, gráficas y dinero del personaje inventados (en el juego los genera tu partida). Empresas, siglas y titulares son los del juego. Las compras no se hacen.');
        // El script manda PROXY_FUNCTION(0, dinero): WEB_BROWSER y la web lo pasan como
        // [[dinero]] a SET_BAWSAQ_PLAYER_CASH, que Scaleform convierte a número por
        // toString y el AVM1 de Ruffle no (NaN -> "$0"). Mismo resultado, llamada directa.
        api.callSite('SET_BAWSAQ_PLAYER_CASH', cash(api));
        const fill = PAGES[page];
        if (fill) fill(api);
        api.updateText();
        if (api.fresh) tickertape(api);                        // Global_64294: al entrar en la web
        if (page === 'STOCK_TRADE_BUY' || page === 'STOCK_TRADE_SELL') api.disableButton(20, !(api.state.shares > 0));
      },
      /** GET_CURRENT_SELECTION tras cada clic (appinternet.sc: Global_76762) */
      onSelect(sel, api) {
        const st = api.state;
        if ((api.page === 'LISTINGS' || api.page === 'STOCK_PORTFOLIO') && sel >= LIST_START) {
          const s = listed()[sel - LIST_START];
          if (s) st.stock = s.i;
        } else if ((api.page === 'STOCK_TRADE_BUY' || api.page === 'STOCK_TRADE_SELL') && (sel === 21 || sel === 22)) {
          st.shares = Math.max(0, (st.shares || 0) + (sel === 21 ? 1 : -1));
          api.refresh();                                       // Global_76757: se vuelve a pintar la página
        }
        return false;
      },
    };
  }

  // Biblioteca: www.bawsaq.com.js y www.lcn-exchange.com.js registran cada web
  G.stockMarket = { STOCKS, NEWS, quotes, sectionNews, makeProvider, CASH };
})();
