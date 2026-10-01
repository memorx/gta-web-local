/*!
 * providers/www.lcn-exchange.com.js — LCN, la bolsa del modo historia (siteId 7).
 * La lógica (port de appinternet.sc func_8443…8471) está en _stock_market.js, que
 * comparte con www.bawsaq.com; index.json la carga antes que este archivo.
 */
GTAHOST.registerProvider('www.lcn-exchange.com', GTAHOST.stockMarket.makeProvider(false));
