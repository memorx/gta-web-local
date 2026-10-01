# GTA Web Local

*[Read in English](README.md)*

Navega en tu propia computadora las páginas web que salen dentro de los juegos de Grand
Theft Auto, tal como se ven en el juego:

- **GTA IV**, **The Lost and Damned** y **The Ballad of Gay Tony**: todo el internet de
  Liberty City (eyefind.info, love-meet.net, la base de datos de la LCPD, Weazel News, el
  correo del juego...). Son unas 726 páginas convertidas desde los archivos del propio
  juego. Las partes que el juego llena con scripts (noticias, perfiles de citas,
  expedientes policiacos, anuncios) también salen llenas.
- **GTA V** (modo historia): los 81 sitios del navegador del juego (eyefind, bleeter,
  Lifeinvader, los bancos, BAWSAQ y LCN, Legendary Motorsport, Elitás Travel, el Epsilon
  Program, The Children of the Mountain...). Cada uno es la película Flash del propio
  juego, convertida para [Ruffle](https://ruffle.rs) y corriendo dentro del navegador
  original del juego.
- **GTA III**, **Vice City** y **San Andreas**: esos juegos no tienen internet adentro,
  así que se reconstruyen los 29 sitios que Rockstar publicó para ellos en su momento
  (Liberty Tree, Love Media, Kent Paul, Degenatron, Exsorbeo, el Epsilon Program...) a
  partir de la Wayback Machine del Internet Archive.

Todo lo sirve un pequeño servidor local, con una portada de los cinco juegos en
`http://127.0.0.1:8044/`.

## Este repositorio no trae archivos del juego

Aquí solo hay **código**: ninguna página, imagen, fuente, texto ni dato de los juegos, y
nada bajado del Internet Archive. Todo se genera en tu computadora:

- GTA IV y GTA V se convierten desde **tu propia copia instalada** del juego.
- Los sitios de GTA III, Vice City y San Andreas los baja tu computadora de la Wayback
  Machine. Cada archivo está amarrado a una captura y a una suma de verificación
  (`classic/lock/`), así que a todos les sale exactamente lo mismo.

Las construcciones son reproducibles: con los mismos archivos del juego sale
exactamente la misma salida, byte por byte.

## Cómo empezar

Necesitas **Python 3.11+** y **Git**. Para GTA V también **Java 8+** y Pillow
(`pip install -r requirements.txt`). Go, el SDK de .NET, Ruffle y las demás herramientas
se bajan solas, en versiones fijas, la primera vez que hacen falta.

```sh
git clone --recurse-submodules https://github.com/memorx/gta-web-local
cd gta-web-local
copy config.example.toml config.toml   # en Linux/macOS: cp
# edita config.toml: pon en gta4 / gta5 las carpetas de tus juegos (deja una vacía para saltarla)

python build.py iv          # GTA IV + episodios          (~3 minutos la primera vez)
python build.py v           # sitios de GTA V              (~8 minutos la primera vez)
python build.py classic     # III / VC / SA desde la Wayback Machine (~2 horas la primera vez)
python build.py             # o todo junto

python serve.py             # y abre http://127.0.0.1:8044/
```

Las carpetas de los juegos solo se leen; nunca se escribe en ellas.

## Documentación (en inglés)

- [docs/iv-and-classics.md](docs/iv-and-classics.md): GTA IV y los sitios clásicos.
- [docs/gta-v.md](docs/gta-v.md): GTA V, sus etapas, cómo reciben sus datos los sitios
  dinámicos y las limitaciones conocidas.
- [third_party/README.md](third_party/README.md): el convertidor de páginas de GTA IV.

Probado en Windows 11 con GTA IV Complete Edition (Steam) y GTA V Enhanced. GTA V Legacy
y Linux están implementados pero todavía no se han probado.

## Créditos

- [zeozeozeo/gtaweb](https://github.com/zeozeozeo/gtaweb): el convertidor original de
  `.whm` de GTA IV en el que se basa el fork de este proyecto.
- [Ruffle](https://ruffle.rs): el emulador de Flash que reproduce los sitios de GTA V y
  los sitios Flash antiguos.
- [rage-cli](https://github.com/VIRUXE/rage-cli), [CodeWalker](https://github.com/dexyfex/CodeWalker)
  y [JPEXS Free Flash Decompiler](https://github.com/jindrapetrik/jpexs-decompiler):
  leen los archivos, texturas y películas Flash de GTA V.
- El [Internet Archive](https://archive.org): sin la Wayback Machine, los sitios de GTA
  III, Vice City y San Andreas ya no existirían. Trátalo con cuidado: la construcción
  baja un archivo a la vez a propósito.
- La comunidad de la [GTA Wiki](https://gta.fandom.com), cuyas capturas de los juegos
  sirvieron para comprobar que cada sitio de GTA V se viera bien.

## Licencia y aviso legal

El código de este repositorio está bajo la [licencia MIT](LICENSE). Las herramientas que
baja la construcción conservan sus propias licencias.

Grand Theft Auto y todo su contenido (los sitios, sus textos, imágenes y fuentes) son
propiedad de Rockstar Games y Take-Two Interactive. Este es un proyecto de fans, sin
fines de lucro y sin relación con ellos. Necesitas tu propia copia legal de los juegos;
no compartas lo que genera la construcción.
