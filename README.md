# Análisis predictivo de la producción de azúcar en México (Infocaña)

Proyecto final · Big Data · Ingeniería en Desarrollo y Tecnologías de Software (UNACH)

**Dashboard en línea:** https://zickgit.github.io/ProyectoFinal_BigData/

Regresión lineal (scikit-learn) aplicada como modelo de series de tiempo para pronosticar la
producción total de azúcar, con datos abiertos de Infocaña (CONADESUCA) procesados mediante un
pipeline ETL y visualizados en un dashboard de **Shiny for Python** desplegado con **ShinyLive**
en **GitHub Pages**.

## Estructura

```
etl/etl_infocana.py      Pipeline ETL (Extract, Transform, Load)
data/raw/                CSV originales por zafra (datos.gob.mx)
data/processed/          CSV limpios y base SQLite infocana.db
app/app.py               Dashboard Shiny for Python
app/modelo.py            Modelo de regresión lineal (Y = β0 + β1·X)
app/data/                Datos que consume el dashboard
docs/                    Sitio estático exportado con ShinyLive (GitHub Pages)
informe/                 Informe final en PDF, capturas y script generador
```

## Uso

```bash
pip install -r requirements.txt
python etl/etl_infocana.py        # ETL: descarga/integra, limpia, agrega y carga
python app/modelo.py              # métricas y pronóstico en consola
shiny run app/app.py              # dashboard local
shinylive export app docs         # regenerar el sitio de GitHub Pages
```

## Modelo

* **Y:** `azucar_producida_total` (seleccionable en el dashboard) · **X:** periodo (zafra o semana).
* División **80 % entrenamiento / 20 % prueba** en orden cronológico; métricas R², MAE, RMSE y MAPE.
* Recalibración con todos los periodos y pronóstico con intervalo de predicción al 95 %.
* Regresión complementaria: azúcar producida total vs. caña molida neta.

## Publicación en GitHub Pages

*Settings → Pages → Build and deployment → Deploy from a branch* → rama del proyecto, carpeta `/docs`.

Fuente: CONADESUCA, [Avance de la producción de caña y azúcar (Infocaña)](https://www.datos.gob.mx/dataset/avance_produccion_cana_azucar_infocana), CC-BY 4.0.
