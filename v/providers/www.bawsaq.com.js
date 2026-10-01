/*!
 * providers/www.bawsaq.com.js — BAWSAQ, la bolsa "en línea" del juego (siteId 4).
 * La lógica (port de appinternet.sc func_8443…8471) está en _stock_market.js, que
 * comparte con www.lcn-exchange.com; index.json la carga antes que este archivo.
 */
GTAHOST.registerProvider('www.bawsaq.com', GTAHOST.stockMarket.makeProvider(true));
