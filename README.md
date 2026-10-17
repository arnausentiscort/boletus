# Carpe Boletum

App per saber quan anar a buscar ceps (*Boletus aereus*, *B. aestivalis*) i ous de reig (*Amanita caesarea*) a cada lloc, a partir de la pluja i la temperatura.

- S'instal·la al mòbil des del navegador (Compartir → Afegir a la pantalla d'inici).
- Cada cop que s'obre baixa la pluja dels últims dies i la previsió (Open-Meteo).
- Funciona sense cobertura amb les últimes dades guardades.
- Els llocs van xifrats (`data/llocs.enc.json`); només s'obren amb l'enllaç que porta la clau.

## Dades
- Relleu: Terrain Tiles (Terrarium, AWS). Cobertes del sòl i geologia: ICGC.
- Mapa de fons: ICGC (ortofoto i topogràfic gris), en directe.
- Pluja: Open-Meteo (ERA5 fins al 2021, models d'alta resolució des del 2022).

## Eines
- `tools/build_obsol.py`: refà la capa d'obaga/solana.
- `tools/encrypt_llocs.mjs <clau>`: xifra `tools/llocs.json` (no es puja) a `data/llocs.enc.json`.
