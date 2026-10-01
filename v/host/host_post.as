// host_post.as - se inyecta DESPUES de "TIMELINE.INITIALISE(this)" del navegador.
//
// 1. Envuelve WEB_BROWSER.INITIALISE_WEBSITE para avisar a JS cada vez que se
//    muestra una pagina: tanto al cargar otra web (el host la llama tras GFX_READY,
//    como hace appinternet.sc) como al cambiar de pagina dentro de la misma web
//    (GO_TO_WEBPAGE la llama directamente sin pasar por el juego). Antes de
//    avisar, pasa los TextField de la web a IMGP (imagenes <img>, host_pre.as §4).
// 2. Avisa a JS de que _level0.TIMELINE (el navegador) ya existe.
_global.__HOST.b = _level0.TIMELINE;
_global.__HOST.b.__hostInitialiseWebsite = _global.__HOST.b.INITIALISE_WEBSITE;
_global.__HOST.b.INITIALISE_WEBSITE = function()
{
   this.__hostInitialiseWebsite();
   _global.__HOST.patchSite();
   flash.external.ExternalInterface.call("HOST_PAGE_SHOWN",this.fullURL,this.pageName,this.movieClipName,this.doesPageExist,this.currentWebsite.IS_SITE_DYNAMIC);
};
flash.external.ExternalInterface.call("HOST_BROWSER_READY",_global.__HOST.version,typeof _level0.TIMELINE);
