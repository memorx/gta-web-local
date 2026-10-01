/*!
 * providers/www.thechildrenofthemountain.com.js — Children of the Mountain (siteId 20 en
 * appinternet.sc), el "proceso C.o.M" de Brother Adrian que sigue Franklin.
 *
 * La web no es dinámica (IS_SITE_DYNAMIC = 0) y se pinta sola: su constructor pone
 * browser.DebugTextContent = true y así INITIALISE_WEBSITE ya llama a UPDATE_TEXT. Lo único
 * que le da el script es su avance, Global_76920, en el slot 0 (POPULATE_TEXT lo lee en
 * completedStatus en cada página). Estados: 0 nada · 1 recibió el correo con la contraseña
 * de la etapa 2 · 2 pagó la etapa 2 · 3 pagó la etapa 3 · 4 vio el seminario y recibió la
 * contraseña de la etapa 4 · 5 pagó la etapa 4 · 6 proceso completo.
 *
 * Port de lo que hace appinternet.sc con esta web:
 *   * func_8473 (tras INITIALISE_WEBSITE de una web recién cargada): SET_DATA_SLOT(0,
 *     Global_76920) + UPDATE_TEXT.
 *   * Primera página al entrar desde otra web: PAGE1 con estado < 1 -> correo (func_212
 *     -921778680 = EMSTR_657/658: la contraseña de la etapa 2), slot 0 = 1,
 *     UPDATE_TEXT, estado 1. La web sólo acepta esa contraseña con browser.player == 2
 *     (Franklin) y completedStatus == 1; si no, COM_INCORRECT.
 *   * Cambio de página dentro de la web:
 *       - PAGE1 con estado 3 (al acabar el seminario, STAGE3WEBINARDONE vuelve a PAGE1) ->
 *         correo -606278748 (EMSTR_659/660: la contraseña de la etapa 4), slot 0
 *         = 4, UPDATE_TEXT, estado 4. Con 4 la portada pide la contraseña de la etapa 4.
 *       - CERTIFICATE con estado 5 -> correo -414580094 (EMSTR_661/662), estado 6 (y
 *         func_132 le da a Franklin la camiseta de C.o.M).
 *   * Clic (Global_76762 = selección 0, el botón Submit) en STAGE2_D_JOIN ($199, estado < 2
 *     -> 2), STAGE2_D_COMPLETE ($4999, < 3 -> 3) y STAGE4 ($9999, < 5 -> 5): si el personaje
 *     tiene el dinero (func_8596) se le cobra (func_8594), SET_DATA_SLOT(0, estado nuevo);
 *     si no, "Click_Fail" y func_8687 -> PAYMENTERROR. La web ya salta sola a la etapa
 *     siguiente a los 1,5 s (setInterval de goToAnchor); PAYMENTERROR la para
 *     (POPULATE_TEXT hace clearInterval).
 *
 * Estado por defecto: 0, como una partida que nunca abrió la web, y se abre como Franklin
 * (build_v_sites.py CHARACTER): al entrar llega el primer correo y se puede recorrer todo
 * (contraseña 2 -> $199 -> anagramas -> $4999 -> seminario -> contraseña 4 -> $9999 -> test ->
 * certificado). Los correos del juego salen bajo el visor (api.note). El avance se guarda
 * en la sesión de la pestaña (sessionStorage 'gtav-com-status': recargar no lo pierde, una
 * pestaña nueva empieza de 0); el dinero es el de _player.js y no se descuenta (como los
 * donativos de Epsilon): si no llega, PAYMENTERROR.
 *
 * Ruffle: el slot 0 se deja como número y no como el array que guarda SET_DATA_SLOT (ver
 * putSlot); si no, la web rechaza las contraseñas.
 *
 * Diferencias a propósito:
 *   * Si se entra desde fuera directamente en otra página que PAGE1 (?page=STAGE3, o "atrás"
 *     desde otra web), sólo se pone el slot 0, sin el UPDATE_TEXT de func_8473: STAGE2 y
 *     STAGE3 añaden sus anagramas/diapositivas a arrays compartidos en cada POPULATE_TEXT y
 *     con dos saldrían repetidos (el juego lo haría; allí no se puede entrar así salvo con
 *     "atrás"). completedStatus sólo se usa en PAGE1, que ya lo lee al mostrarse.
 *   * Si así (entrando por ?page=FAQ) se llega luego a PAGE1 sin salir de la web, el primer
 *     correo llega igual; en el juego haría falta salir y volver a entrar.
 *   * En CERTIFICATE (estado 5 -> 6) el slot 0 también pasa a 6: el script no lo toca y HOME
 *     seguiría enseñando la etapa 4 hasta volver a entrar en la web.
 */
(function () {
  'use strict';
  const G = window.GTAHOST;
  if (!G) return;

  const FRANKLIN = 1;                       // api.character (skin 2 = browser.player 2)
  // página -> [precio, estado tras pagar, página a la que salta la web] (bloque "case 20"
  // del bucle de clics; el salto lo hace la web: gotoStage2/gotoStage3/gotoStage4)
  const PAYMENT = {
    STAGE2_D_JOIN: [199, 2, 'STAGE2'],
    STAGE2_D_COMPLETE: [4999, 3, 'STAGE3'],
    STAGE4: [9999, 5, 'STAGE4_D_1'],
  };
  // estado al que lleva cada correo -> [asunto, cuerpo] (remitente EMSTR_652, Brother Adrian)
  const EMAIL = {
    1: ['EMSTR_657', 'EMSTR_658'],
    4: ['EMSTR_659', 'EMSTR_660'],
    6: ['EMSTR_661', 'EMSTR_662'],
  };
  const FROM = 'EMSTR_652';
  const LABELS = [FROM].concat(...Object.values(EMAIL));
  const money = n => '$' + Math.floor(n).toLocaleString('en-US');

  // Avance (Global_76920) guardado en la sesión de la pestaña: recargar o entrar por
  // ?page=STAGE3 no lo pierde; una pestaña nueva empieza de 0 (como eyefind en host.js)
  const KEY = 'gtav-com-status';
  function status(api) {
    if (typeof api.state.status !== 'number') {
      let v = 0;
      try { v = Math.floor(Number(window.sessionStorage.getItem(KEY))) || 0; } catch (e) { v = 0; }
      api.state.status = v >= 0 && v <= 6 ? v : 0;
    }
    return api.state.status;
  }
  function save(api, s) {
    api.state.status = s;
    try { window.sessionStorage.setItem(KEY, String(s)); } catch (e) { /* sin almacenamiento: vale el de memoria */ }
  }
  /**
   * SET_DATA_SLOT(0, s), como el script. El navegador guarda el slot como array
   * (dataProviderUI[0] = arguments.slice(1) = [s]) y la web compara completedStatus == 1 /
   * == 4 al enviar la contraseña. Scaleform pasa el array a primitivo por toString ("1" == 1,
   * si no, el juego mismo no aceptaría la contraseña); el AVM1 de Ruffle solo usa valueOf, que
   * devuelve el array, y [1] == 1 da false (contraseña correcta -> INCORRECT). Por eso el slot se deja
   * luego con el número: setPage1Content (String(status.valueOf())) funciona igual.
   */
  const putSlot = (api, s) => { api.setDataSlot(0, s); api.set('site.dataProviderUI', '0', s); };
  const setStatus = (api, s) => { save(api, s); putSlot(api, s); };

  /** Texto de un label de correo, en una línea (sin ~códigos~ ni <u>) */
  function line(api, label) {
    return api.text(label).replace(/<[^>]*>/g, '').replace(/\s*\n+\s*/g, ' ').replace(/\s{2,}/g, ' ').trim();
  }
  /** Enseña bajo el visor el correo que en el juego llegaría al teléfono de Franklin */
  async function email(api, s) {
    await api.need(LABELS);
    if (!api.isCurrent()) return;
    const [subject, body] = EMAIL[s];
    api.note('Correo de ' + line(api, FROM) + ' a Franklin — «' + line(api, subject) + '» ' + line(api, body));
  }
  /**
   * Aviso bajo el visor: en la portada, el correo con la contraseña que toca (estados 1 y 4);
   * en el certificado, el último correo; tras un pago, el aviso del cobro en la página a la
   * que salta la web; con otro personaje, que el proceso es de Franklin.
   */
  function pageNote(api, page, s) {
    if (api.character !== FRANKLIN) {
      api.note('En el juego el proceso C.o.M es de Franklin: con otro personaje la web contesta INCORRECT a '
        + 'cualquier contraseña. Ábrela con ?personaje=franklin.');
      return;
    }
    const keep = api.state.keepNoteFor === page;
    api.state.keepNoteFor = null;
    if (page === 'PAGE1' && (s === 1 || s === 4)) email(api, s);
    else if (page === 'CERTIFICATE' && s === 6) email(api, 6);
    else if (!keep) api.note('');
  }

  GTAHOST.registerProvider('www.thechildrenofthemountain.com', {
    clearSlots: false,                      // la web no es dinámica: el slot 0 se conserva
    onPage(page, api) {
      let s = status(api);
      if (api.fresh) {
        // func_8473 + primera página de la web (rama "else" del cambio de web)
        if (page === 'PAGE1' && s < 1 && api.character === FRANKLIN) save(api, s = 1);
        putSlot(api, s);
        if (page === 'PAGE1') api.updateText();
      } else if (page === 'PAGE1' && s < 1 && api.character === FRANKLIN) {
        // (diferencia) se entró por otra página (?page=FAQ) y se llega a la portada sin salir
        // de la web: el juego no manda el correo hasta volver a entrar; aquí sí, para que la
        // contraseña no quede fuera de alcance
        setStatus(api, s = 1);
        api.updateText();
      } else if (page === 'PAGE1' && s === 3) {
        // cambio de página dentro de la web (rama "case 20" con iLocal_618 == iLocal_619)
        setStatus(api, s = 4);
        api.updateText();
      } else if (page === 'CERTIFICATE' && s === 5) {
        // (el script no toca el slot aquí: la portada seguiría en 5 hasta volver a entrar;
        // se pone ya para que HOME enseñe "Process Complete")
        setStatus(api, s = 6);
      }
      pageNote(api, page, s);
    },
    onSelect(sel, api) {
      if (sel !== 0) return;
      const pay = PAYMENT[api.page];
      if (!pay) return;
      const [price, next, goes] = pay;
      const s = status(api);
      if (s >= next) return;                  // ya pagado (Global_76920 < n)
      const pd = G.playerData;
      const cash = pd && pd.cash ? Number(pd.cash[api.character]) : Infinity;
      if (cash >= price) {
        setStatus(api, next);
        api.state.keepNoteFor = goes;         // la web salta sola ahí a los 1,5 s
        api.note('En el juego aquí se le cobran ' + money(price) + ' a ' + api.characterName.charAt(0)
          + api.characterName.slice(1).toLowerCase() + ' (tiene ' + money(cash) + '); en esta copia no se descuentan.');
      } else {
        api.note('');
        api.goTo('PAYMENTERROR');             // func_8687, tras el sonido "Click_Fail"
      }
    },
  });
})();
