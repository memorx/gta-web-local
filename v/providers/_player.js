/*!
 * providers/_player.js — datos del personaje que comparten varias webs.
 *
 * En el juego el dinero de cada personaje es Global_61482[personaje]: lo enseñan igual
 * BAWSAQ y LCN ("My Cash", appinternet.sc func_8443 -> PROXY_FUNCTION 0) y su banco
 * (saldo, func_8365). Aquí es inventado pero el mismo en todas las webs, como en el juego.
 * Lo cargan como dependencia (providers/index.json: "deps") _stock_market.js y _bank.js.
 */
(function () {
  'use strict';
  const G = window.GTAHOST;
  if (!G || G.playerData) return;
  G.playerData = {
    // Michael, Franklin, Trevor (0/1/2 = api.character)
    cash: [1286450, 326480, 587105],
    // func_8365: label del titular de la cuenta
    accountName: ['ACCNA_MIKE', 'ACCNA_FRANKLIN', 'ACCNA_TREVOR'],
  };
})();
