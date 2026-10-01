// ============================================================================
// host_pre.as  -  "lado juego" del navegador de GTA V dentro de Ruffle (AS2)
//
// Se inyecta en web_browser.swf, frame 1, JUSTO ANTES de
//     var TIMELINE = new com.rockstargames.gtav.web.WEB_BROWSER(this);
// En ese punto ya corrieron los DoInitAction del frame, asi que todas las
// clases existen en _global.com.rockstargames.*  Las webs (www_*.swf) que el
// navegador carga despues NO redefinen esas clases (cada clase AS2 va envuelta
// en "if(!_global.com...X)"), asi que usan las versiones parchadas de aqui.
//
// Que hace:
//  1. GameInterface.call  -> reenvia a JS (ExternalInterface) convirtiendo los
//     TextField / MovieClip en texto "<tf:ruta>" / "<mc:ruta>" (Ruffle no puede
//     pasar referencias a objetos de escena). Si JS responde {ops:[[i,prop,valor]]}
//     se aplica arguments[i][prop] = valor. Asi el host "rellena" el campo de
//     texto de SET_TEXT_WITH_TRANSLATION (i=3, prop="htmlText"/"text") o los
//     objetos de SET_DISPLAY_CONFIG / GET_HUD_COLOUR, igual que haria el juego.
//  2. ExternalInterface.addCallback: HOST_INVOKE / HOST_SET / HOST_GET para que
//     JS llame metodos del navegador (GO_TO_WEBPAGE, SET_MOUSE_INPUT, ...),
//     de la web cargada o de cualquier clip, como hace el script del juego.
//  3. MovieClipLoader.loadClip / MovieClip.loadMovie pasan la URL por JS
//     (HOST_RESOLVE_URL) para traducir "WWW_LIFEINVADER_COM" a la ruta real.
// ============================================================================

_global.__HOST = new Object();
_global.__HOST.version = 5;
// Referencia a _global para las rutas "_global.*" que llegan desde JS
_global.__HOST.G = _global;
// OJO (compilador JPEXS): los PARAMETROS de una funcion van en registros y una
// funcion anidada no los ve. Nada en este shim depende de closures: los datos
// que necesita una funcion interna se guardan en el objeto (this, callee...).

// ---- 0. Cadenas que llegan de JS --------------------------------------------
// Ruffle convierte en la cadena "null" (4 letras) toda cadena de JS vacia o solo
// de espacios ("", " ", "\n"...): "NULL BMX" en pandmcycles (marca ""), SELL
// oculto en la bolsa (""), etc. host.js manda esas cadenas con el prefijo \u0001
// (y cualquier cadena que ya empiece por \u0001) y aqui se quita. Se aplica a los
// argumentos de HOST_INVOKE / HOST_SET y a lo que devuelve JS en GameInterface.call
// y HOST_RESOLVE_URL.
_global.__HOST.dec = function(v)
{
   var t = typeof v;
   if(t == "string")
   {
      if(v.charCodeAt(0) == 1)
      {
         return v.substring(1);
      }
      return v;
   }
   if(v instanceof Array)
   {
      var out = [];
      var k = 0;
      while(k < v.length)
      {
         out.push(_global.__HOST.dec(v[k]));
         k++;
      }
      return out;
   }
   return v;
};

// ¿Tiene etiquetas HTML? ("<" seguido de letra o "/")
_global.__HOST.hasTags = function(v)
{
   var s = String(v);
   var i = s.indexOf("<");
   var c;
   while(i >= 0 && i < s.length - 1)
   {
      c = s.charAt(i + 1);
      if(c == "/" || (c >= "a" && c <= "z") || (c >= "A" && c <= "Z"))
      {
         return true;
      }
      i = s.indexOf("<",i + 1);
   }
   return false;
};

// htmlText para un campo que NO era html: se quitan TEXTFORMAT, P y FONT (tipo,
// tamano, alineacion del campo del que se copio; p. ej. pandmcycles 2013 guarda el
// htmlText de un nombre de la portada y lo reutiliza en las miniaturas) para que el
// campo conserve su propio formato. Se mantienen B, I, U, BR, A... Cada <P> a partir
// del segundo pasa a <br>.
_global.__HOST.dropFormat = function(v)
{
   var s = String(v);
   var out = "";
   var i = 0;
   var paras = 0;
   var a;
   var b;
   var tag;
   var name;
   var close;
   while(true)
   {
      a = s.indexOf("<",i);
      b = a < 0 ? -1 : s.indexOf(">",a);
      if(a < 0 || b < 0)
      {
         out += s.substring(i);
         break;
      }
      out += s.substring(i,a);
      tag = s.substring(a + 1,b);
      close = tag.charAt(0) == "/";
      name = (!close ? tag : tag.substring(1)).split(" ")[0].split("/")[0].toUpperCase();
      if(name == "P")
      {
         if(!close)
         {
            if(paras > 0)
            {
               out += "<br>";
            }
            paras++;
         }
      }
      else if(name != "TEXTFORMAT" && name != "FONT")
      {
         out += s.substring(a,b + 1);
      }
      i = b + 1;
   }
   return out;
};

// htmlText del campo "diccionario" (localisationTF): sin TEXTFORMAT ni parrafos (cada <P>
// a partir del segundo pasa a <br>) y cada <FONT> solo con FACE y COLOR (sin SIZE,
// LETTERSPACING ni KERNING): el campo al que se copia pone su tamano y su alineacion.
_global.__HOST.localFormat = function(v)
{
   var s = String(v);
   var out = "";
   var i = 0;
   var paras = 0;
   var a;
   var b;
   var tag;
   var name;
   var close;
   var face;
   var color;
   while(true)
   {
      a = s.indexOf("<",i);
      b = a < 0 ? -1 : s.indexOf(">",a);
      if(a < 0 || b < 0)
      {
         out += s.substring(i);
         break;
      }
      out += s.substring(i,a);
      tag = s.substring(a,b + 1);
      close = tag.charAt(1) == "/";
      name = (!close ? tag.substring(1) : tag.substring(2)).split(" ")[0].split("/")[0].split(">")[0].toUpperCase();
      if(name == "P")
      {
         if(!close)
         {
            if(paras > 0)
            {
               out += "<br>";
            }
            paras++;
         }
      }
      else if(name == "FONT")
      {
         if(close)
         {
            out += "</FONT>";
         }
         else
         {
            face = _global.__HOST.attr(tag,"face");
            color = _global.__HOST.attr(tag,"color");
            out += "<FONT" + (face == "" ? "" : " FACE=\"" + face + "\"") + (color == "" ? "" : " COLOR=\"" + color + "\"") + ">";
         }
      }
      else if(name != "TEXTFORMAT")
      {
         out += tag;
      }
      i = b + 1;
   }
   return out;
};

// htmlText con etiquetas para un campo que no era html: se activa html (Scaleform lo
// interpreta igual) y se quitan los formatos ajenos (dropFormat). El campo queda
// marcado (__hostHtml) para que las siguientes asignaciones se traten igual.
_global.__HOST.fixHtml = function(tf, v)
{
   if(tf.__hostHtml || (!tf.html && _global.__HOST.hasTags(v)))
   {
      if(!tf.html)
      {
         tf.html = true;
      }
      tf.__hostHtml = true;
      return _global.__HOST.dropFormat(v);
   }
   return v;
};

// Asigna o[prop] = v como lo haria el juego:
//  * v se decodifica (ver dec);
//  * text/htmlText de un TextField nunca reciben null/undefined (Flash pinta "null");
//  * Scaleform interpreta htmlText aunque el campo tenga html=false; Ruffle pinta
//    las etiquetas tal cual, asi que se activa html antes de asignar.
_global.__HOST.put = function(o, prop, v)
{
   v = _global.__HOST.dec(v);
   if(o instanceof TextField && (prop == "text" || prop == "htmlText"))
   {
      if(v == undefined)
      {
         v = "";
      }
      if(prop == "htmlText")
      {
         v = _global.__HOST.fixHtml(o,v);
      }
      o[prop] = v;
      // textAutoSize="shrink" (Scaleform): p. ej. hushsmush pone la propiedad y luego pide
      // el texto con SET_TEXT_WITH_TRANSLATION (ver shrink, seccion 5)
      if(o.textAutoSize == "shrink")
      {
         _global.__HOST.shrink(o);
      }
      return undefined;
   }
   o[prop] = v;
};

// Describe un argumento para ExternalInterface (los objetos de escena no viajan).
_global.__HOST.describe = function(a)
{
   if(a instanceof TextField)
   {
      return "<tf:" + a._target + ">";
   }
   if(typeof a == "movieclip")
   {
      return "<mc:" + a._target + ">";
   }
   return a;
};

// Solo devolvemos a JS valores simples (evita serializar arboles de clips).
_global.__HOST.plain = function(v)
{
   var t = typeof v;
   if(t == "string" || t == "number" || t == "boolean")
   {
      return v;
   }
   if(v == undefined || v == null)
   {
      return null;
   }
   if(v instanceof Array)
   {
      var out = [];
      var k = 0;
      while(k < v.length)
      {
         out.push(_global.__HOST.plain(v[k]));
         k++;
      }
      return out;
   }
   return _global.__HOST.describe(v) == v ? "<object>" : _global.__HOST.describe(v);
};

// Resuelve una ruta tipo "browser", "site", "sitemc.CONTENT.PAGE1", "_level0.CURSOR"
_global.__HOST.resolve = function(path)
{
   var parts = String(path).split(".");
   var head = parts[0];
   var o;
   var i = 1;
   if(head == "browser")
   {
      o = _level0.TIMELINE;
   }
   else if(head == "site")
   {
      o = _level0.TIMELINE.currentWebsite;
   }
   else if(head == "sitemc")
   {
      o = _level0[_level0.TIMELINE.movieClipName];
   }
   else if(head == "host")
   {
      o = _global.__HOST;
   }
   else if(head == "_global")
   {
      o = _global.__HOST.G;
   }
   else if(head == "_level0" || head == "_root" || head == "")
   {
      o = _level0;
   }
   else
   {
      o = _level0;
      i = 0;
   }
   while(i < parts.length)
   {
      if(o == undefined || o == null)
      {
         return undefined;
      }
      o = o[parts[i]];
      i++;
   }
   return o;
};

// ---- 1. GameInterface.call -------------------------------------------------
com.rockstargames.ui.game.GameInterface.call = function()
{
   var EI = flash.external.ExternalInterface;
   var args = [];
   var i = 0;
   while(i < arguments.length)
   {
      args.push(_global.__HOST.describe(arguments[i]));
      i++;
   }
   var r = EI.call.apply(EI,args);
   if(r != undefined && r != null && r.ops != undefined)
   {
      var ops = r.ops;
      var j = 0;
      while(j < ops.length)
      {
         var op = ops[j];
         var target = arguments[op[0]];
         if(target != undefined && target != null)
         {
            _global.__HOST.put(target,op[1],op[2]);
         }
         j++;
      }
   }
   if(r != undefined && r != null && r.value != undefined)
   {
      return _global.__HOST.dec(r.value);
   }
   return undefined;
};

// ---- 2. Llamadas desde JS ("el juego") hacia la pelicula -------------------
flash.external.ExternalInterface.addCallback("HOST_INVOKE",null,function(path, method, args)
{
   var o = _global.__HOST.resolve(path);
   if(o == undefined || o == null)
   {
      return "<no-target>";
   }
   var f = o[method];
   if(typeof f != "function")
   {
      return "<no-method>";
   }
   if(args == undefined || args == null)
   {
      args = [];
   }
   return _global.__HOST.plain(f.apply(o,_global.__HOST.dec(args)));
});

flash.external.ExternalInterface.addCallback("HOST_SET",null,function(path, prop, value)
{
   var o = _global.__HOST.resolve(path);
   if(o == undefined || o == null)
   {
      return false;
   }
   _global.__HOST.put(o,prop,value);
   return true;
});

flash.external.ExternalInterface.addCallback("HOST_GET",null,function(path)
{
   return _global.__HOST.plain(_global.__HOST.resolve(path));
});

// ---- 3. URLs de carga (webs .swf e imagenes) --------------------------------
_global.__HOST.mapUrl = function(url)
{
   var m = _global.__HOST.dec(flash.external.ExternalInterface.call("HOST_RESOLVE_URL",url));
   if(m == undefined || m == null || m == "" || m == "null")
   {
      return url;
   }
   return m;
};

_global.__HOST.origLoadClip = MovieClipLoader.prototype.loadClip;
MovieClipLoader.prototype.loadClip = function(url, target)
{
   return _global.__HOST.origLoadClip.call(this,_global.__HOST.mapUrl(url),target);
};

_global.__HOST.origLoadMovie = MovieClip.prototype.loadMovie;
MovieClip.prototype.loadMovie = function(url, method)
{
   return _global.__HOST.origLoadMovie.call(this,_global.__HOST.mapUrl(url),method);
};

// ---- 4. <img src='img://txd/textura'> dentro de htmlText --------------------
// Las webs pintan las imagenes que pide el juego (miniaturas de eyefind, fotos
// de vehiculos, casas, avatares de bleeter...) escribiendo en un TextField
//     tf.htmlText = "<img src='img://TXD/TEX' width='160' height='80'/>"
// Ruffle quita la etiqueta <img> sin pedir nada, asi que aqui:
//  * los TextField de la web pasan a heredar de IMGP (hereda de
//    TextField.prototype y redefine htmlText); asi vemos cada asignacion;
//  * cada <img src='img://...'> se quita del texto y se pinta con un clip
//    hermano del TextField (mismo sitio y tamano) que carga el PNG con
//    MovieClipLoader; la URL la traduce JS (HOST_RESOLVE_URL);
//  * las flechas de bolsa (<img src='down_arrow'>, simbolos de biblioteca en
//    medio del texto) se cambian por los caracteres de flecha (U+2193 / U+2191).
// Los TextField se "parchan" al cambiar de fotograma (gotoAndStop/Play), al
// crear clips (attachMovie, duplicateMovieClip, createTextField), al mostrar
// cada pagina y antes de cada tanda de TXD_HAS_LOADED (patchSite desde JS).
_global.__HOST.TFP = TextField.prototype;
_global.__HOST.IMGP = new Object();
_global.__HOST.IMGP.__proto__ = TextField.prototype;
_global.__HOST.IMGP.addProperty("htmlText",function()
{
   var p = this.__proto__;
   this.__proto__ = _global.__HOST.TFP;
   // AS2: "si el campo no es HTML, htmlText se comporta igual que text". Ruffle devuelve
   // <TEXTFORMAT><P><FONT ...> igualmente; pandmcycles 2013 copia asi el htmlText de un
   // campo oculto (localisationTF) a cada nombre y salia "<TEXTFORMAT LEADI...".
   var v = !this.html ? this.text : this.htmlText;
   this.__proto__ = p;
   // localisationTF = campo oculto que las webs usan de "diccionario": piden el texto ahi
   // y copian su htmlText al campo visible (pandmcycles 2013: titulo, cabecera, cuerpo).
   // En el juego el campo visible conserva su alineacion y su tamano (wiki FrontPageold:
   // cuerpo a la izquierda en 13 px) pero sale con la letra y el color del diccionario
   // (el titulo, cuyo campo es cursiva, sale recto). Ruffle exportaria tambien el tamano
   // (20 px) y el centrado y el cuerpo se salia de su caja: se quitan (ver localFormat).
   if(this._name == "localisationTF" && _global.__HOST.hasTags(v))
   {
      v = _global.__HOST.localFormat(v);
   }
   return v;
},function(v)
{
   var p = this.__proto__;
   if(v == undefined)
   {
      v = "";
   }
   var s = _global.__HOST.imgFilter(this,v);
   this.__proto__ = _global.__HOST.TFP;
   // Scaleform interpreta htmlText aunque html sea false (p. ej. pandmcycles 2013
   // copia un htmlText con <TEXTFORMAT ...> a otro campo); Ruffle lo pintaria tal cual
   s = _global.__HOST.fixHtml(this,s);
   this.htmlText = s;
   this.__proto__ = p;
   if(this.textAutoSize == "shrink")
   {
      _global.__HOST.shrink(this);
   }
});

// text: igual que el nativo; solo avisa a shrink (textAutoSize, seccion 5).
_global.__HOST.IMGP.addProperty("text",function()
{
   var p = this.__proto__;
   this.__proto__ = _global.__HOST.TFP;
   var v = this.text;
   this.__proto__ = p;
   return v;
},function(v)
{
   var p = this.__proto__;
   this.__proto__ = _global.__HOST.TFP;
   this.text = v;
   this.__proto__ = p;
   if(this.textAutoSize == "shrink")
   {
      _global.__HOST.shrink(this);
   }
});

// textAutoSize (propiedad de Scaleform: "none", "shrink", "fit"). Ruffle no la conoce; se
// guarda y, con "shrink", se encoge ya el texto que hubiera.
_global.__HOST.IMGP.addProperty("textAutoSize",function()
{
   return this.__hostTas;
},function(v)
{
   this.__hostTas = v;
   if(v == "shrink")
   {
      _global.__HOST.shrink(this);
   }
});

// autoSize = "true" (cadena): Scaleform lo toma como "left"; Ruffle lo ignora y
// el texto queda cortado (p. ej. el enlace EF_WOTM_* de eyefind).
_global.__HOST.IMGP.addProperty("autoSize",function()
{
   var p = this.__proto__;
   this.__proto__ = _global.__HOST.TFP;
   var v = this.autoSize;
   this.__proto__ = p;
   return v;
},function(v)
{
   var p = this.__proto__;
   if(v == "true")
   {
      v = "left";
   }
   else if(v == "false")
   {
      v = "none";
   }
   this.__proto__ = _global.__HOST.TFP;
   this.autoSize = v;
   this.__proto__ = p;
});

// Valor de un atributo de una etiqueta HTML (comillas simples, dobles o nada).
_global.__HOST.attr = function(tag, name)
{
   var k = tag.toLowerCase().indexOf(" " + name + "=");
   if(k < 0)
   {
      return "";
   }
   k += name.length + 2;
   var q = tag.charAt(k);
   var e;
   if(q == "\'" || q == "\"")
   {
      e = tag.indexOf(q,k + 1);
      return tag.substring(k + 1,e < 0 ? tag.length : e);
   }
   e = k;
   while(e < tag.length && tag.charAt(e) != " " && tag.charAt(e) != ">" && tag.charAt(e) != "/")
   {
      e++;
   }
   return tag.substring(k,e);
};

// Quita las <img> del texto; la primera img:// se pinta con imgShow.
_global.__HOST.imgFilter = function(tf, v)
{
   var s = String(v);
   if(v == undefined || v == null || s.indexOf("<img") < 0)
   {
      if(tf.__hostImg != undefined)
      {
         _global.__HOST.imgHide(tf);
      }
      return v;
   }
   var out = "";
   var found = false;
   var i = 0;
   var a;
   var b;
   var tag;
   var src;
   while(true)
   {
      a = s.indexOf("<img",i);
      b = a < 0 ? -1 : s.indexOf(">",a);
      if(a < 0 || b < 0)
      {
         out += s.substring(i);
         break;
      }
      out += s.substring(i,a);
      tag = s.substring(a,b + 1);
      src = _global.__HOST.attr(tag,"src");
      // img://undefined/undefined_b (p. ej. pandmcycles PURCHASE_D_SUCCESS abierta sin haber
      // elegido vehiculo): en el juego no pinta nada; aqui no se pide (era un 404)
      if(src.indexOf("img://") == 0 && (src.indexOf("img://undefined/") == 0 || src.indexOf("/undefined") == src.length - 10))
      {
         src = "";
      }
      if(src.indexOf("img://") == 0)
      {
         if(!found)
         {
            found = true;
            _global.__HOST.imgShow(tf,src,Number(_global.__HOST.attr(tag,"width")),Number(_global.__HOST.attr(tag,"height")),Number(_global.__HOST.attr(tag,"hspace")),Number(_global.__HOST.attr(tag,"vspace")));
         }
      }
      else if(src == "down_arrow")
      {
         // flecha de bolsa (simbolo de la biblioteca): la fuente de las cintas ($Font2)
         // tiene flechas simples, no triangulos
         out += String.fromCharCode(8595);
      }
      else if(src == "up_arrow")
      {
         out += String.fromCharCode(8593);
      }
      i = b + 1;
   }
   if(!found && tf.__hostImg != undefined)
   {
      _global.__HOST.imgHide(tf);
   }
   flash.external.ExternalInterface.call("HOST_IMG",tf._target,src,found);
   return out;
};

// Pinta la textura src (img://txd/tex) donde estaria la <img> del TextField:
// esquina superior izquierda + 2 px de margen interno (+ hspace/vspace), con el
// ancho/alto pedidos (en el juego el PNG se escala a ese tamano).
_global.__HOST.imgShow = function(tf, src, w, h, hs, vs)
{
   var par = tf._parent;
   if(par == undefined)
   {
      return undefined;
   }
   var mc = tf.__hostImg;
   var d;
   if(typeof mc != "movieclip" || mc._parent != par)
   {
      d = par.getNextHighestDepth();
      mc = par.createEmptyMovieClip("__hostImg" + d,d);
      tf.__hostImg = mc;
   }
   if(isNaN(hs))
   {
      hs = 0;
   }
   if(isNaN(vs))
   {
      vs = 0;
   }
   var sx = tf._xscale / 100;
   var sy = tf._yscale / 100;
   mc._x = tf._x + (2 + hs) * sx;
   mc._y = tf._y + (2 + vs) * sy;
   mc._visible = true;
   mc.__w = !(w > 0) ? 0 : w * sx;
   mc.__h = !(h > 0) ? 0 : h * sy;
   if(mc.__src == src && mc.pic.__loaded)
   {
      if(mc.__w > 0)
      {
         mc.pic._width = mc.__w;
      }
      if(mc.__h > 0)
      {
         mc.pic._height = mc.__h;
      }
      return undefined;
   }
   mc.__src = src;
   var pic = mc.createEmptyMovieClip("pic",1);
   // El oyente guarda la textura pedida (sin closures: ver nota arriba)
   var l = new Object();
   l.src = src;
   l.onLoadInit = function(t)
   {
      var m = t._parent;
      if(m.__src != this.src)
      {
         return undefined;
      }
      if(m.__w > 0)
      {
         t._width = m.__w;
      }
      if(m.__h > 0)
      {
         t._height = m.__h;
      }
      t.__loaded = true;
      flash.external.ExternalInterface.call("HOST_IMG_LOADED",t._target,this.src,t._width,t._height);
   };
   l.onLoadError = function(t, err)
   {
      flash.external.ExternalInterface.call("HOST_IMG_LOADED",t._target,this.src,-1,-1,err);
   };
   var mcl = new MovieClipLoader();
   mcl.addListener(l);
   mcl.loadClip(src,pic);
};

_global.__HOST.imgHide = function(tf)
{
   var mc = tf.__hostImg;
   if(typeof mc == "movieclip")
   {
      mc._visible = false;
      mc.__src = undefined;
      mc.pic.removeMovieClip();
   }
};

// ---- 5. textAutoSize = "shrink" -------------------------------------------
// Scaleform encoge el tipo de letra de un campo con textAutoSize="shrink" hasta que el
// texto cabe en la caja (ancho si no parte lineas, alto siempre). Ruffle no conoce la
// propiedad: el titular de hushsmush (HUS_*,
// campo de 450 px, texto de 524) salia cortado bajo la modelo. Aqui se reduce el tamano
// de cada tramo de texto (conservando las proporciones entre tramos) hasta que cabe:
// textWidth <= _width - 4 (sin ajuste de linea) y textHeight <= _height, sin escala.
// Solo sin autoSize (con autoSize la caja crece y Scaleform no encoge). Cada
// asignacion de texto parte del tamano original (el formato nuevo no cambia).
_global.__HOST.overflows = function(tf, aw, ah)
{
   return (!tf.wordWrap && tf.textWidth > aw) || tf.textHeight > ah;
};
_global.__HOST.shrink = function(tf)
{
   if(tf == undefined || tf.__hostShrinking)
   {
      return undefined;
   }
   var p = tf.__proto__;
   if(p == _global.__HOST.IMGP)
   {
      tf.__proto__ = _global.__HOST.TFP;
   }
   var as = String(tf.autoSize);
   var sx = Math.abs(tf._xscale / 100);
   var sy = Math.abs(tf._yscale / 100);
   var n = tf.length;
   var aw;
   var ah;
   var runs;
   var cur;
   var k;
   var sz;
   var it;
   var scale;
   var r;
   var r1;
   var r2;
   var j;
   var f;
   if((as == "none" || as == "false") && sx > 0 && sy > 0 && n > 0 && n < 5000)
   {
      // ancho: caja menos 2 px por lado; alto: la caja entera (Ruffle mide cada linea con
      // su interlineado: una linea de 21 px vive en un campo de 23.4 y en el juego cabe)
      aw = tf._width / sx - 4;
      ah = tf._height / sy;
      if(aw > 0 && ah > 0 && _global.__HOST.overflows(tf,aw,ah))
      {
         tf.__hostShrinking = true;
         runs = [];
         cur = null;
         k = 0;
         while(k < n)
         {
            sz = tf.getTextFormat(k,k + 1).size;
            if(cur == null || cur[2] != sz)
            {
               cur = [k,k + 1,sz];
               runs.push(cur);
            }
            else
            {
               cur[1] = k + 1;
            }
            k++;
         }
         scale = 1;
         it = 0;
         while(it < 40 && _global.__HOST.overflows(tf,aw,ah))
         {
            r1 = 1;
            r2 = 1;
            if(!tf.wordWrap && tf.textWidth > aw)
            {
               r1 = aw / tf.textWidth;
            }
            if(tf.textHeight > ah)
            {
               // con ajuste de linea el alto crece mas o menos con el cuadrado del tamano
               r2 = !tf.wordWrap ? ah / tf.textHeight : Math.sqrt(ah / tf.textHeight);
            }
            r = Math.min(r1,r2);
            if(r > 0.98)
            {
               r = 0.98;
            }
            if(r < 0.5)
            {
               r = 0.5;
            }
            scale *= r;
            j = 0;
            while(j < runs.length)
            {
               if(runs[j][2] > 0)
               {
                  f = new TextFormat();
                  f.size = Math.max(1,Math.floor(runs[j][2] * scale * 10) / 10);
                  tf.setTextFormat(runs[j][0],runs[j][1],f);
               }
               j++;
            }
            it++;
         }
         tf.__hostShrinking = false;
         tf.__hostShrunk = scale;
      }
   }
   tf.__proto__ = p;
};

// ---- 6. Colour.Colourise sobre un TextField -------------------------------
// Colourise(clip, r, g, b, a) hace new flash.geom.Transform(clip).colorTransform =
// ColorTransform(1,1,1,1, r-255, g-255, b-255, 0) y clip._alpha = a. Scaleform lo
// aplica tambien a un TextField; Ruffle no aplica ese colorTransform a un TextField.
// psychicshoutout tine asi el boton del chat (blanco
// en el SWF): #9900FF al 100 % si se puede pulsar y al 30 % si no. Para un TextField se
// emula con textColor (color base del campo + desplazamiento, recortado a 0-255) y _alpha.
_global.__HOST.tintText = function(tf, r, g, b, a)
{
   if(tf.__hostBaseColor == undefined)
   {
      tf.__hostBaseColor = tf.textColor;
   }
   var c = tf.__hostBaseColor;
   var cr = Math.max(0,Math.min(255,((c >> 16) & 255) + r - 255));
   var cg = Math.max(0,Math.min(255,((c >> 8) & 255) + g - 255));
   var cb = Math.max(0,Math.min(255,(c & 255) + b - 255));
   tf.textColor = (cr << 16) | (cg << 8) | cb;
   if(a != undefined)
   {
      tf._alpha = a;
   }
};
_global.__HOST.wrapColour = function()
{
   var C = _global.com.rockstargames.ui.utils.Colour;
   if(C == undefined || C.Colourise == undefined || C.Colourise.__host)
   {
      return undefined;
   }
   var w = function(mc, r, g, b, a)
   {
      if(mc instanceof TextField)
      {
         _global.__HOST.tintText(mc,r,g,b,a);
         return undefined;
      }
      return arguments.callee.__orig(mc,r,g,b,a);
   };
   w.__orig = C.Colourise;
   w.__host = true;
   C.Colourise = w;
};
_global.__HOST.wrapColour();

// ---- 7. Atras / adelante de la barra DEL JUEGO con el historial del shell ----------------
// Los botones de la barra del navegador del juego (WebBrowserBack/Forward.buttonEvent) llaman
// GO_BACK / GO_FORWARD, que usan el historial interno del navegador y navegan con
// GO_TO_WEBPAGE: la pagina que contiene la pelicula lo veia como una navegacion nueva
// (pushState) y "atras" alargaba el historial en vez de volver. Si JS activa shellHistory
// (host.js con la opcion onHistory, lo pone shell.html), GO_BACK / GO_FORWARD avisan a JS
// (HOST_HISTORY(-1 | 1)) y la pagina mueve SU historial, como su boton y Retroceso; el
// estado de los dos botones (gris / blanco) sale de canBack / canForward, que pone JS.
// Se conserva lo demas del original: con el teclado del juego abierto solo lo cierra, la
// lista del historial se cierra y SUPRESS_HISTORY(true) desactiva "atras".
// Sin shellHistory (o con host.back() sin shell) se usa el original (__hostGoBack...).
_global.__HOST.shellHistory = false;
_global.__HOST.canBack = false;
_global.__HOST.canForward = false;
_global.__HOST.WB = com.rockstargames.gtav.web.WEB_BROWSER.prototype;
_global.__HOST.WB.__hostGoBack = _global.__HOST.WB.GO_BACK;
_global.__HOST.WB.__hostGoForward = _global.__HOST.WB.GO_FORWARD;
_global.__HOST.WB.__hostUpdateToolbar = _global.__HOST.WB.UPDATE_TOOLBAR_BUTTONS;
_global.__HOST.WB.GO_BACK = function()
{
   if(_global.__HOST.shellHistory != true || this.keyboardFocus != "")
   {
      return this.__hostGoBack();
   }
   this.REMOVE_LIST();
   if(this.suppressBackButton != true)
   {
      flash.external.ExternalInterface.call("HOST_HISTORY",-1);
   }
};
_global.__HOST.WB.GO_FORWARD = function()
{
   if(_global.__HOST.shellHistory != true || this.keyboardFocus != "")
   {
      return this.__hostGoForward();
   }
   this.REMOVE_LIST();
   flash.external.ExternalInterface.call("HOST_HISTORY",1);
};
// Igual que UPDATE_TOOLBAR_BUTTONS: blanco al 100 % si se puede, gris al 50 % si no.
_global.__HOST.toolbarButton = function(b, on)
{
   if(b == undefined)
   {
      return undefined;
   }
   if(on)
   {
      com.rockstargames.ui.utils.Colour.Colourise(b,255,255,255,100);
   }
   else
   {
      com.rockstargames.ui.utils.Colour.Colourise(b,200,200,200,50);
   }
   b.disabled = !on;
};
_global.__HOST.WB.UPDATE_TOOLBAR_BUTTONS = function()
{
   if(_global.__HOST.shellHistory != true)
   {
      return this.__hostUpdateToolbar();
   }
   _global.__HOST.toolbarButton(this.TOOLBAR.button_back,_global.__HOST.canBack == true);
   _global.__HOST.toolbarButton(this.TOOLBAR.button_forward,_global.__HOST.canForward == true);
};

// Pasa los TextField de un arbol de clips a IMGP (sin salir del arbol).
_global.__HOST.patchTree = function(mc, depth)
{
   if(mc == undefined || depth > 30)
   {
      return undefined;
   }
   var c;
   for(var k in mc)
   {
      c = mc[k];
      if(c instanceof TextField)
      {
         if(c.__proto__ != _global.__HOST.IMGP && c._parent == mc)
         {
            c.__proto__ = _global.__HOST.IMGP;
            if(c.textAutoSize == "shrink")
            {
               _global.__HOST.shrink(c);
            }
         }
      }
      else if(typeof c == "movieclip" && c._parent == mc && k.indexOf("__hostImg") != 0)
      {
         _global.__HOST.patchTree(c,depth + 1);
      }
   }
};
// Pruebas: "ruta=texto" de cada TextField visible de la web (HOST_INVOKE host.texts).
// Los hijos salen de for-in y ademas de getInstanceAtDepth(0..): de varios clips con el MISMO
// nombre de instancia for-in solo da uno (thechildrenofthemountain crea un "tiles" nuevo por
// anagrama sin quitar el anterior: los anagramas 2-11 no salian); los demas se encuentran por
// profundidad (los clips creados por codigo van de 0 en adelante). Cada objeto visitado se
// marca con el numero de pasada (__hostSeen, oculto a for-in) para no repetirlo. La ruta
// (_target) de un repetido es la del primero; lo distingue el nombre de su clip (LETTER_n_i).
_global.__HOST.collectStamp = 0;
_global.__HOST.collectOne = function(mc, c, depth, out, stamp)
{
   if(c == undefined || c._parent != mc || c.__hostSeen == stamp)
   {
      return undefined;
   }
   if(c instanceof TextField)
   {
      c.__hostSeen = stamp;
      ASSetPropFlags(c,"__hostSeen",1);
      if(c._visible)
      {
         out.push(c._target + "=" + c.text);
      }
   }
   else if(typeof c == "movieclip")
   {
      c.__hostSeen = stamp;
      ASSetPropFlags(c,"__hostSeen",1);
      if(c._visible && String(c._name).indexOf("__hostImg") != 0)
      {
         _global.__HOST.collect(c,depth + 1,out,stamp);
      }
   }
};
_global.__HOST.collect = function(mc, depth, out, stamp)
{
   if(mc == undefined || depth > 30)
   {
      return undefined;
   }
   var n;
   var d;
   for(var k in mc)
   {
      _global.__HOST.collectOne(mc,mc[k],depth,out,stamp);
   }
   if(typeof mc == "movieclip")
   {
      n = mc.getNextHighestDepth();
      if(n > 2000)
      {
         n = 2000;
      }
      d = 0;
      while(d < n)
      {
         _global.__HOST.collectOne(mc,mc.getInstanceAtDepth(d),depth,out,stamp);
         d++;
      }
   }
};
_global.__HOST.texts = function()
{
   var out = [];
   _global.__HOST.collectStamp++;
   _global.__HOST.collect(_level0[_level0.TIMELINE.movieClipName],0,out,_global.__HOST.collectStamp);
   return out;
};
_global.__HOST.patchSite = function()
{
   _global.__HOST.wrapColour();
   var site = _level0[_level0.TIMELINE.movieClipName];
   _global.__HOST.patchTree(site,0);
   return typeof site;
};

// Envuelve metodos de MovieClip para parchar lo que se crea.
// modo 1: el propio clip (cambio de fotograma); modo 2: el clip/TextField devuelto.
_global.__HOST.wrapMC = function(name, mode)
{
   var f = function()
   {
      var me = arguments.callee;
      var r = me.__orig.apply(this,arguments);
      if(me.__mode == 1)
      {
         _global.__HOST.patchTree(this,0);
      }
      else if(typeof r == "movieclip")
      {
         _global.__HOST.patchTree(r,0);
      }
      else if(r instanceof TextField)
      {
         r.__proto__ = _global.__HOST.IMGP;
      }
      return r;
   };
   f.__orig = MovieClip.prototype[name];
   f.__mode = mode;
   MovieClip.prototype[name] = f;
   ASSetPropFlags(MovieClip.prototype,name,1);
};
_global.__HOST.wrapMC("gotoAndStop",1);
_global.__HOST.wrapMC("gotoAndPlay",1);
_global.__HOST.wrapMC("attachMovie",2);
_global.__HOST.wrapMC("duplicateMovieClip",2);
_global.__HOST.wrapMC("createTextField",2);

flash.external.ExternalInterface.call("HOST_SHIM_LOADED",_global.__HOST.version);
