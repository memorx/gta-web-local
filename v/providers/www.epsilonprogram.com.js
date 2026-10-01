/*!
 * providers/www.epsilonprogram.com.js — el Programa Épsilon (siteId 5).
 *
 * Port de lo que hace appinternet.sc con esta web (func_8363 caso 5 -> func_8440, más
 * func_24/func_8515/func_8528 del bucle principal), con el hilo de Épsilon terminado:
 *   * PAGE1: tras UPDATE_TEXT, DISABLE_BUTTON(4, false) si ya se donaron los $5,000
 *     (func_7609(88), paso 5 de Épsilon): se activa el botón "Welcome" que la web deja
 *     apagado (WWW_EPSILONPROGRAM_COM.POPULATE_TEXT: DISABLE_BUTTON(4, true)).
 *   * PRESENTATION (14): la presentación de Cris Formage. En el juego el script pone
 *     Global_78300 = 1 y, cada vez que termina una frase grabada (EPSW_VOICE1…5, del
 *     diálogo EPSWAUD), pasa a la siguiente diapositiva con PROXY_FUNCTION(0, n) y al
 *     final PROXY_FUNCTION(6, 6) (texto EPS_PRESENTATION). Aquí no hay audio: cada
 *     diapositiva dura lo que tardan en leerse sus subtítulos, que salen bajo el visor
 *     (son los del juego, EPSW_VOICE<n>_<k>).
 *   * Comprar la túnica (STORE -> PURCHASETRANSACTION): con el hilo terminado el script
 *     de la túnica (epsrobes) ya no corre y func_8515 -> func_8528(1) manda a
 *     TRANSACTION_D_FAILED con EPSI_NO_STOCK ("Sadly we have no robes in stock…").
 *   * TRANSACTION_D_FAILED (22): slot 0 = el mensaje (func_8440).
 * Los donativos (MAKEDONATION) salen bien sin más: Michael tiene dinero de sobra.
 * Sólo Michael: con otro personaje la web misma enseña ERROR (EPSI_NO_MP_VISIT).
 */
(function () {
  'use strict';
  const G = window.GTAHOST;
  if (!G) return;
  // Subtitles of each line of Cris: labels EPSW_VOICE<n>_<k> of the EPSWAUD dialogue block
  // (epswaud.gxt2, not in strings.json / strings_all.json, which only carry global.gxt2).
  // The build exports their text from your own game files (v/gxt2json.py) to
  // www.epsilonprogram.com.json next to this file; no game text ships with the code.
  const VOICE = {
    1: ['EPSW_VOICE1_1', 'EPSW_VOICE1_3', 'EPSW_VOICE1_5', 'EPSW_VOICE1_7'],
    2: ['EPSW_VOICE2_1', 'EPSW_VOICE2_3', 'EPSW_VOICE2_5', 'EPSW_VOICE2_7', 'EPSW_VOICE2_8'],
    3: ['EPSW_VOICE3_1', 'EPSW_VOICE3_3', 'EPSW_VOICE3_5', 'EPSW_VOICE3_7', 'EPSW_VOICE3_9'],
    4: ['EPSW_VOICE4_1', 'EPSW_VOICE4_3', 'EPSW_VOICE4_5'],
    5: ['EPSW_VOICE5_1', 'EPSW_VOICE5_3', 'EPSW_VOICE5_5', 'EPSW_VOICE5_7', 'EPSW_VOICE5_9',
      'EPSW_VOICE5_10', 'EPSW_VOICE5_12', 'EPSW_VOICE5_13'],
  };
  let SUBTITLES = null;
  function subtitles(api) {
    if (!SUBTITLES) {
      const host = api.host;
      const base = host && host.providersBase ? host.providersBase() : null;
      SUBTITLES = !base ? Promise.resolve({}) :
        fetch(base + 'www.epsilonprogram.com.json', { cache: 'no-cache' })
          .then(r => (r.ok ? r.json() : {}))
          .catch(() => ({}));
    }
    return SUBTITLES;
  }
  const LINE_MS = 3800;           // una línea de subtítulo
  const LABELS = ['EPSI_NO_STOCK'];
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  async function presentation(api) {
    // func_24 + bucle principal: diapositivas 1…5, cada una con su frase; luego la 6
    const text = await subtitles(api);
    for (let n = 1; n <= 5; n++) {
      if (!api.isCurrent()) return;
      api.callSite('PROXY_FUNCTION', 0, n);
      for (const label of VOICE[n]) {
        if (!api.isCurrent()) return;
        const line = G.formatGxt(text[label] || '', false).trim();
        if (line) api.note('Cris Formage: «' + line + '»');
        await sleep(LINE_MS);
      }
    }
    if (!api.isCurrent()) return;
    api.callSite('PROXY_FUNCTION', 6, 6);
    api.note('');
  }

  GTAHOST.registerProvider('www.epsilonprogram.com', {
    async onPage(page, api) {
      if (api.character !== 0) return;                      // la web enseña ERROR sola
      api.note('');
      switch (page) {
        case 'PAGE1':
          api.updateText();
          api.disableButton(4, false);                        // func_8440 caso 1 (flag 88)
          return;
        case 'PURCHASETRANSACTION':
          api.goTo('TRANSACTION_D_FAILED');                   // func_8515 -> func_8528(1)
          return;
        case 'TRANSACTION_D_FAILED':
          await api.need(LABELS);
          if (!api.isCurrent()) return;
          api.setDataSlot(0, api.text('EPSI_NO_STOCK'));      // func_8440 caso 22, Global_78301 = 1
          return;
        case 'PRESENTATION':
          api.updateText();
          presentation(api);                                  // sin await: sigue sola
          return;
      }
    },
  });
})();
