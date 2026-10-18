# Boletus

App per saber quan anar a buscar ceps (*Boletus aereus*, *B. aestivalis*) i ous de reig (*Amanita caesarea*) a cada lloc, a partir de la pluja i la temperatura.

- S'instal·la al mòbil des del navegador (Compartir → Afegir a la pantalla d'inici).
- Cada cop que s'obre baixa la pluja dels últims dies i la previsió (Open-Meteo).
- Funciona sense cobertura amb les últimes dades guardades.
- Els llocs i les sortides inicials són a `data/llocs.json`.

## Dades
- Relleu: Terrain Tiles (Terrarium, AWS). Cobertes del sòl i geologia: ICGC.
- Mapa de fons: ICGC (ortofoto i topogràfic gris), en directe.
- Pluja: Open-Meteo (ERA5 fins al 2021, models d'alta resolució des del 2022).

## Buscar boscos
A uns 50 km de Torredembarra: bosc, matollar o avellaners sobre roca àcida, entre 200 i 800 m (`data/region.json`, `data/region.png`, fet amb `tools/build_region.py`).

## Avisos
Cada matí GitHub Actions executa `tools/avisos.py` i envia avisos a ntfy (tema `boletus-ceps-x7q2`) quan ha plogut prou i el dia abans del millor dia.

## Eines
- `tools/build_obsol.py`: refà la capa d'obaga/solana.
