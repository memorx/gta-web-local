/*!
 * providers/_bank.js — los tres bancos del modo historia: www.maze-bank.com (Michael),
 * www.fleeca.com (Franklin) y www.thebankofliberty.com (Trevor).
 *
 * Port de appinternet.sc: func_8363 (webs 21/22/23) -> func_8364 -> func_8365, que sólo
 * rellena la página 2 (TRANSACTIONS) y luego pone UPDATE_TEXT:
 *   slot 0  saldo (Global_61482[cuenta])
 *   slot 1  titular (ACCNA_MIKE / ACCNA_FRANKLIN / ACCNA_TREVOR)
 *   slot 2  W_BA_ATL "Account Transactions"
 *   slot 3  [saldo, W_BA_BAL "Balance"]
 *   slot 4… un movimiento por slot, el más reciente primero (hasta 11, Global_114135.
 *           f_20568.f_233[cuenta]): [1 abono / 0 cargo, importe, concepto]; el concepto
 *           es func_8366(origen), un label ACCNA_* o de tienda (S_H_*, S_CL_*, S_G_*…).
 * La portada (PAGE1) la hace la web sola con browser.player: cada banco sólo reconoce a
 * su cliente (BANKS_baseclass.POPULATE_TEXT) y a los demás les dice "Username Unrecognized".
 *
 * Lo que NO sale del juego (y lo dice api.note): el saldo (el mismo dinero de BAWSAQ/LCN,
 * _player.js) y los movimientos, que en el juego son los de tu partida. Los conceptos son
 * los del juego y algunos importes también, sacados de los scripts:
 *   * Epsilon: donativos de $500 y $5,000 (origen 29) y la túnica, $25,000 (origen 30)
 *     — appinternet.sc func_8515, func_54(0, 0, 29/30, importe).
 *   * The Reality Mill, $500 (origen 94) y International Money Transfer, $10,000
 *     (origen 93) — appinternet.sc, func_54(personaje, 0, 94, 500) y func_7605.
 *   * Vehículos: precios de modo historia de la web (host_data.json vehiclePrices):
 *     Legendary Motorsport 440,000 y 95,000, Pedal and Metal 2,500, Elitas 500,000.
 * El resto de importes son inventados.
 */
(function () {
  'use strict';
  const G = window.GTAHOST;
  if (!G || G.bank) return;

  // func_8366: origen del movimiento -> label (sólo los que se usan aquí)
  const SOURCE = {
    2: 'ACCNA_BROKERA', 24: 'ACCNA_DRFR', 25: 'ACCNA_STRP', 26: 'ACCNA_HUNT', 28: 'ACCNA_RACES',
    29: 'ACCNA_EPS_ST', 30: 'ACCNA_EPS_RB', 40: 'ACCNA_GOL_CLU', 42: 'S_H_02', 50: 'S_CL_03',
    59: 'S_CH_01', 68: 'S_T_06', 69: 'S_G_01', 70: 'S_G_02', 80: 'S_MO_01', 85: 'ACCNA_CARSITE',
    87: 'ACCNA_PLANESITE', 89: 'ACCNA_BIKESITE', 93: 'ACCNA_CONSIT', 94: 'ACCNA_TRMSITE',
    99: 'ACCNA_TOWING', 100: 'ACCNA_TAXI_LOT', 101: 'ACCNA_ARMS', 106: 'ACCNA_MCINEMA',
    109: 'ACCNA_SMOKE', 122: 'ACCNA_PD_SS', 128: 'ACCNA_H_SS',
  };
  const CR = 1, DB = 0;
  // Movimientos de cada personaje, el más reciente primero: [abono/cargo, origen, importe]
  const LOG = [
    [ // Michael — Maze Bank
      [CR, 2, 48210],        // Stock Brokerage: vendió sus acciones (la cartera de BAWSAQ/LCN está vacía)
      [DB, 24, 1600],        // Dr. Friedlander Clinical Services
      [DB, 59, 4720],        // Ponsonbys
      [DB, 40, 100],         // Los Santos Golf Club
      [DB, 85, 440000],      // Legendary Motorsport (Pegassi Infernus, precio de la web)
      [CR, 106, 2340],       // Tivoli Cinema
      [DB, 30, 25000],       // Epsilon Group retail: la túnica (func_8515)
      [DB, 29, 5000],        // Epsilon Group voluntary donation (func_8515)
      [DB, 29, 500],         // Epsilon Group voluntary donation (func_8515)
      [DB, 94, 500],         // The Reality Mill Subscription (func_54(0, 0, 94, 500))
      [DB, 80, 6150],        // Los Santos Customs
    ],
    [ // Franklin — Fleeca
      [CR, 109, 1800],       // Smoke on the Water
      [DB, 89, 2500],        // Pedal and Metal Sales (precio de la web)
      [DB, 42, 160],         // Herr Kutz Barber
      [DB, 50, 395],         // Binco Clothing
      [CR, 100, 2850],       // Downtown Cab Co.
      [DB, 69, 7450],        // Ammu-Nation
      [DB, 99, 150000],      // Towing Impound
      [DB, 85, 95000],       // Legendary Motorsport (precio de la web)
      [DB, 93, 10000],       // International Money Transfer (func_7605)
      [DB, 94, 500],         // The Reality Mill Subscription (func_54(1, 0, 94, 500))
      [DB, 80, 9300],        // Los Santos Customs
    ],
    [ // Trevor — Bank of Liberty
      [CR, 101, 9000],       // McKenzie Field Hangar
      [DB, 70, 12300],       // Ammu-Nation
      [DB, 25, 1100],        // Vanilla Unicorn
      [DB, 87, 500000],      // Elitas Travel Solutions (precio de la web)
      [DB, 128, 1500],       // Sandy Shores Hospital
      [CR, 28, 1000],        // Off-Road Races
      [DB, 122, 500],        // Sandy Shores PD Bail
      [DB, 68, 250],         // Ink Inc Tattoos
      [DB, 93, 10000],       // International Money Transfer (func_7605)
      [DB, 94, 500],         // The Reality Mill Subscription (func_54(2, 0, 94, 500))
      [CR, 26, 400],         // Hunting Pay
    ],
  ];
  const CASH = (G.playerData && G.playerData.cash) || [1286450, 326480, 587105];
  const NAME = (G.playerData && G.playerData.accountName) || ['ACCNA_MIKE', 'ACCNA_FRANKLIN', 'ACCNA_TREVOR'];
  // Cliente de cada banco (BANKS_baseclass: Maze = player 0, Fleeca = 2, Liberty = 3)
  const CLIENT = { WWW_MAZE_D_BANK_COM: 0, WWW_FLEECA_COM: 1, WWW_THEBANKOFLIBERTY_COM: 2 };
  const CHAR = ['michael', 'franklin', 'trevor'];
  const LABELS = ['W_BA_ATL', 'W_BA_BAL'].concat(NAME, Object.keys(SOURCE).map(k => SOURCE[k]));

  function makeProvider(domain) {
    const owner = CLIENT[G.siteKey(domain)];
    return {
      async onPage(page, api) {
        if (api.character !== owner) {
          // Otro personaje: la web dice "Username Unrecognized" en la portada y no enseña
          // el botón de movimientos. A TRANSACTIONS sólo se llega con la dirección: a la portada.
          api.note('Este banco es el de ' + ['Michael', 'Franklin', 'Trevor'][owner] + ': con otro personaje no reconoce la cuenta, como en el juego (?personaje=' + CHAR[owner] + ').');
          if (page === 'TRANSACTIONS') api.goTo('PAGE1');
          return;
        }
        api.note('Saldo y movimientos inventados (en el juego son los de tu partida). Los conceptos son los del juego y algunos importes también (Epsilon, The Reality Mill, vehículos de las webs). El saldo es el mismo dinero que en BAWSAQ y LCN.');
        if (page !== 'TRANSACTIONS') return;                  // func_8364: sólo el caso 2
        await api.need(LABELS);
        if (!api.isCurrent()) return;
        const c = api.character;
        api.setDataSlot(0, CASH[c]);
        api.setDataSlot(1, api.text(NAME[c]));
        api.setDataSlot(2, api.text('W_BA_ATL'));
        api.setDataSlot(3, CASH[c], api.text('W_BA_BAL'));
        LOG[c].slice(0, 11).forEach(([type, src, amount], k) => {
          api.setDataSlot(4 + k, type, amount, api.text(SOURCE[src]));
        });
      },
    };
  }

  G.bank = { SOURCE, LOG, CLIENT, makeProvider };
})();
