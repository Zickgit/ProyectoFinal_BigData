"""
Genera el informe final en PDF (informe/Informe_ProyectoFinal_BigData.pdf).

Requiere haber ejecutado el ETL y tener las capturas en informe/capturas/.
    python informe/generar_informe.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import modelo as M  # noqa: E402

REPO_URL = "https://github.com/Zickgit/ProyectoFinal_BigData"
PAGES_URL = "https://zickgit.github.io/ProyectoFinal_BigData/"
CAPTURAS = Path(__file__).parent / "capturas"
SALIDA = Path(__file__).parent / "Informe_ProyectoFinal_BigData.pdf"
AZUL = colors.HexColor("#14284b")

st = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=st["Heading1"], textColor=AZUL, fontSize=16, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=st["Heading2"], textColor=AZUL, fontSize=12.5, spaceBefore=8, spaceAfter=4)
P = ParagraphStyle("P", parent=st["BodyText"], fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=6)
LI = ParagraphStyle("LI", parent=P, leftIndent=14, bulletIndent=4, spaceAfter=2)
PIE = ParagraphStyle("PIE", parent=P, fontSize=8.5, textColor=colors.HexColor("#52514e"), alignment=TA_CENTER)
CODE = ParagraphStyle("CODE", fontName="Courier", fontSize=6.6, leading=8.1, backColor=colors.HexColor("#f5f6f8"),
                      borderPadding=4, leftIndent=2)
CEN = ParagraphStyle("CEN", parent=P, alignment=TA_CENTER)


def f(v, d=0):
    return f"{v:,.{d}f}"


def bullets(items):
    return [Paragraph(t, LI, bulletText="•") for t in items]


def tabla(filas, anchos, cab=True):
    t = Table(filas, colWidths=anchos, repeatRows=1 if cab else 0)
    estilo = [("FONT", (0, 0), (-1, -1), "Helvetica", 9),
              ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9c7c1")),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fb")])]
    if cab:
        estilo += [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                   ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9)]
    t.setStyle(TableStyle(estilo))
    return t


def captura(nombre, pie, ancho=17 * cm):
    ruta = CAPTURAS / nombre
    if not ruta.exists():
        return [Paragraph(f"[Falta captura: {nombre}]", P)]
    from PIL import Image as PILImage
    w, h = PILImage.open(ruta).size
    return [KeepTogether([Image(str(ruta), width=ancho, height=ancho * h / w), Paragraph(pie, PIE)]),
            Spacer(1, 8)]


def codigo(ruta: Path, titulo: str):
    texto = ruta.read_text(encoding="utf-8")
    return [Paragraph(titulo, H2), Preformatted(texto, CODE)]


def pie_pagina(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#52514e"))
    canvas.drawString(2 * cm, 1.2 * cm, "UNACH · Ingeniería en Desarrollo y Tecnologías de Software · Big Data")
    canvas.drawRightString(letter[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


def main():
    datos = M.cargar_datos()
    z = datos["infocana_zafra"]
    serie = M.serie_anual(datos, "azucar_producida_total")
    comp = serie[serie["completa"]].reset_index(drop=True)
    curso = serie[~serie["completa"]]
    r = M.ajustar_pronosticar(comp, 3, 0.20)
    p1 = r.pronostico.iloc[0]
    xy = M.regresion_xy(datos["infocana_ingenio_zafra"], "cana_molida_neta")
    ult = serie.iloc[-1]
    uc = comp.iloc[-1]
    imax, imin = comp["y"].idxmax(), comp["y"].idxmin()
    tasa = ((comp["y"].iloc[-1] / comp["y"].iloc[0]) ** (1 / (len(comp) - 1)) - 1) * 100
    n_sem = len(datos["infocana_semanal"])
    n_ing = datos["infocana_semanal"]["ingenio"].nunique()
    primera, ultima = z["zafra"].iloc[0], z["zafra"].iloc[-1]

    h = []
    # ---- Portada -------------------------------------------------------------
    h += [Spacer(1, 1.2 * cm),
          Paragraph("UNIVERSIDAD AUTÓNOMA DE CHIAPAS", ParagraphStyle("u", parent=CEN, fontSize=15, leading=20,
                                                                    textColor=AZUL, fontName="Helvetica-Bold")),
          Paragraph("Escuela de Tecnologías Digitales Aplicadas, Campus IV", CEN),
          Paragraph("Ingeniería en Desarrollo y Tecnologías de Software", CEN),
          Spacer(1, 1.6 * cm),
          Paragraph("Unidad de Competencia: Big Data", ParagraphStyle("b", parent=CEN, fontSize=12)),
          Paragraph("Proyecto Final · Evaluación Final: Dashboard aplicando algoritmo de Series de Tiempo",
                    ParagraphStyle("b2", parent=CEN, fontSize=11)),
          Spacer(1, 1.2 * cm),
          Paragraph("“Análisis predictivo de la producción de azúcar en México mediante regresión lineal y "
                    "procesamiento ETL con datos abiertos de Infocaña”",
                    ParagraphStyle("t", parent=CEN, fontSize=17, leading=24, fontName="Helvetica-Bold",
                                   textColor=AZUL)),
          Spacer(1, 1.6 * cm),
          Paragraph("<b>Integrantes del equipo:</b>", CEN),
          Paragraph("[Nombre del estudiante 1] — Matrícula: [__________]", CEN),
          Paragraph("[Nombre del estudiante 2] — Matrícula: [__________]", CEN),
          Spacer(1, 0.8 * cm),
          Paragraph("<b>Docente:</b> Dr. Christian Mauricio Castillo Estrada", CEN),
          Paragraph("<b>Periodo:</b> Agosto – Diciembre 2026", CEN),
          Paragraph(f"<b>Fecha de entrega:</b> 23 de noviembre de 2026", CEN),
          Spacer(1, 1.2 * cm),
          Paragraph(f"<b>Repositorio:</b> <link href='{REPO_URL}' color='blue'>{REPO_URL}</link>", CEN),
          Paragraph(f"<b>Dashboard (GitHub Pages):</b> <link href='{PAGES_URL}' color='blue'>{PAGES_URL}</link>", CEN),
          PageBreak()]

    # ---- Introducción ----------------------------------------------------------
    h += [Paragraph("1. Introducción", H1),
          Paragraph("La agroindustria de la caña de azúcar es una de las actividades más relevantes del campo "
                    "mexicano. El Comité Nacional para el Desarrollo Sustentable de la Caña de Azúcar (CONADESUCA) "
                    "publica, a través del sistema <b>Infocaña</b> y del portal de datos abiertos datos.gob.mx, el "
                    "avance semanal de la producción de cada ingenio: caña molida, superficie cosechada, azúcar "
                    "producida por tipo, eficiencias y rendimientos.", P),
          Paragraph("El propósito de este proyecto es aplicar técnicas de Big Data para integrar esos datos "
                    f"históricos ({primera} a {ultima}) mediante un pipeline <b>ETL</b> (extracción, transformación "
                    "y carga), construir un modelo de aprendizaje supervisado de <b>regresión lineal</b> "
                    "(scikit-learn) para pronosticar la <b>producción total de azúcar</b> como serie de tiempo, y "
                    "presentar los resultados en un <b>Dashboard</b> interactivo desarrollado con <b>Shiny for "
                    "Python</b>, exportado con <b>ShinyLive</b> y desplegado en <b>GitHub Pages</b>.", P),
          Paragraph("Objetivos específicos", H2)]
    h += bullets([
        "Descargar e integrar los CSV de Infocaña de varias zafras en un solo conjunto de datos.",
        "Limpiar, normalizar y transformar los datos; generar variables derivadas y agregados por zafra.",
        "Ajustar un modelo Y = β0 + β1·X con Y = azúcar producida total y X = periodo (zafra), "
        "dividiendo los datos en 80 % entrenamiento y 20 % prueba, y evaluar su desempeño.",
        "Construir un dashboard con controles de entrada, DataTable y gráficas para apoyar la toma de decisiones.",
        "Responder los cuestionamientos del caso de estudio con base en el pronóstico.",
    ])

    # ---- Metodología -----------------------------------------------------------
    h += [Paragraph("2. Metodología", H1), Paragraph("2.1 Pipeline ETL (etl/etl_infocana.py)", H2)]
    h += bullets([
        "<b>Extract:</b> descarga de un CSV por zafra desde datos.gob.mx (CONADESUCA). Los archivos se guardan "
        "en <i>data/raw</i> y se reutilizan como caché. Se integraron "
        f"{len(z)} zafras ({primera} a {ultima}) en un único DataFrame.",
        "<b>Transform:</b> normalización de nombres de columnas (minúsculas, sin acentos y homologación entre "
        "esquemas: p. ej. <i>semana → no_s_zafra</i>, <i>azucar_total → azucar_producida_total</i>); "
        "homologación de nombres de ingenios; conversión de tipos numéricos; eliminación de registros con "
        "nulos en campos clave, duplicados y valores negativos.",
        "<b>Variables derivadas:</b> rendimiento en fábrica calculado (azúcar / caña neta × 100), rendimiento en "
        "campo (caña bruta / superficie), azúcar por hectárea, y rendimiento promedio por ingenio.",
        "<b>Agregación por zafra:</b> como los datos son acumulados semanales, se toma la última semana "
        "reportada por cada ingenio (cierre) y se suma a nivel nacional. Se marca como <i>en curso</i> la "
        "zafra cuyo número de semanas es menor al 85 % de la mediana histórica.",
        f"<b>Load:</b> almacenamiento en DataFrames de pandas, archivos CSV y base de datos SQLite "
        f"(<i>data/processed/infocana.db</i>) con 5 tablas. Resultado: {f(n_sem)} registros semanales limpios "
        f"de {n_ing} ingenios.",
    ])
    filas = [["Zafra", "Ingenios", "Semanas", "Estado", "Azúcar total (t)", "Caña neta (t)", "Rend. fábrica %"]]
    for _, row in z.iterrows():
        filas.append([row.zafra, int(row.num_ingenios), int(row.semanas),
                      "Completa" if str(row.completa).lower() in ("true", "1") else "En curso",
                      f(row.azucar_producida_total), f(row.cana_molida_neta), f(row.rend_fabrica_nacional, 2)])
    h += [Spacer(1, 4), Paragraph("Tabla 1. Agregado nacional por zafra obtenido por el ETL.", PIE),
          tabla(filas, [2.3 * cm, 1.7 * cm, 1.7 * cm, 1.9 * cm, 3.1 * cm, 3.1 * cm, 2.6 * cm])]

    h += [Paragraph("2.2 Modelo de regresión lineal para series de tiempo (app/modelo.py)", H2),
          Paragraph("Se utilizó <b>LinearRegression</b> de scikit-learn con el modelo <b>Y = β0 + β1·X</b>, donde "
                    "Y es la variable seleccionada (por defecto <i>azucar_producida_total</i>) y X es el periodo de "
                    "tiempo (año de inicio de la zafra en la serie anual, o semana de zafra en la serie semanal).", P)]
    h += bullets([
        "<b>División 80/20 cronológica:</b> al tratarse de una serie temporal no se barajan los datos: el 80 % "
        "de los periodos más antiguos se usa para entrenar y el 20 % más reciente para probar.",
        "<b>Métricas de evaluación:</b> R² (entrenamiento y prueba), MAE, RMSE y MAPE sobre el conjunto de prueba.",
        "<b>Calibración:</b> desde el dashboard se ajusta el porcentaje de prueba, la zafra inicial de "
        "entrenamiento y si se excluye la zafra en curso (incompleta). Evaluado el modelo, se recalibra con todos "
        "los periodos para generar el pronóstico con su intervalo de predicción al 95 %.",
        "<b>Regresión X–Y:</b> adicionalmente se ajusta Y = azúcar producida total vs. X = caña molida neta "
        "(cierre por ingenio y zafra) con división aleatoria 80/20 (random_state = 42).",
    ])

    h += [Paragraph("2.3 Dashboard (Shiny for Python + ShinyLive + GitHub Pages)", H2)]
    h += bullets([
        "<b>Panel de configuración:</b> variable, ingenio (o nacional), frecuencia (anual / semanal), zafra, "
        "horizonte de pronóstico, % de prueba, zafra inicial y botón <i>Generar pronóstico</i>.",
        "<b>Indicadores:</b> horizonte, último valor real, pronóstico final y R² de prueba.",
        "<b>Plot:</b> serie histórica, recta de regresión, predicción sobre el conjunto de prueba, pronóstico e "
        "intervalo de predicción; métricas del modelo y tabla de valores pronosticados.",
        "<b>DataTable:</b> las 5 tablas del ETL con filtros por columna.",
        "<b>Pestañas adicionales:</b> regresión X–Y, indicadores por ingenio e interpretación automática.",
        "<b>Despliegue:</b> <i>shinylive export app docs</i> genera un sitio estático (Python corre en el "
        "navegador con Pyodide/WebAssembly) que GitHub Pages publica desde la carpeta <i>/docs</i>.",
    ])

    # ---- Código y URL ------------------------------------------------------------
    h += [PageBreak(), Paragraph("3. Código del proyecto y URL del repositorio", H1),
          tabla([["Recurso", "URL"],
                 ["Repositorio GitHub", Paragraph(f"<link href='{REPO_URL}' color='blue'>{REPO_URL}</link>", P)],
                 ["Dashboard (GitHub Pages)", Paragraph(f"<link href='{PAGES_URL}' color='blue'>{PAGES_URL}</link>", P)]],
                [4.5 * cm, 12 * cm]),
          Spacer(1, 6),
          Paragraph("Estructura del repositorio:", P),
          Preformatted(
              "ProyectoFinal_BigData/\n"
              "├── etl/etl_infocana.py        # Pipeline ETL (Extract, Transform, Load)\n"
              "├── data/raw/                  # CSV originales de datos.gob.mx por zafra\n"
              "├── data/processed/            # CSV limpios + infocana.db (SQLite)\n"
              "├── app/app.py                 # Dashboard Shiny for Python\n"
              "├── app/modelo.py              # Regresión lineal (scikit-learn)\n"
              "├── app/data/                  # Datos que consume el dashboard\n"
              "├── docs/                      # Exportación ShinyLive (GitHub Pages)\n"
              "└── informe/                   # Este informe y sus capturas", CODE),
          Spacer(1, 6),
          Paragraph("Ejecución local:", P),
          Preformatted("pip install -r requirements.txt\n"
                       "python etl/etl_infocana.py          # ETL\n"
                       "python app/modelo.py                # resultados del modelo en consola\n"
                       "shiny run app/app.py                # dashboard en http://127.0.0.1:8000\n"
                       "shinylive export app docs           # sitio estático para GitHub Pages", CODE),
          Spacer(1, 6),
          Paragraph("El código fuente completo del ETL y del modelo se incluye en el Anexo A; el código del "
                    "dashboard (app/app.py) se encuentra en el repositorio.", P)]

    # ---- Resultados ---------------------------------------------------------------
    h += [PageBreak(), Paragraph("4. Resultados (capturas del funcionamiento)", H1)]
    h += captura("01_pronostico_anual.png", "Figura 1. Pronóstico anual de la producción nacional de azúcar "
                 "(regresión lineal, 80 % entrenamiento / 20 % prueba).")
    h += captura("02_pronostico_horizonte3.png", "Figura 2. Pronóstico con horizonte de 3 zafras e intervalo de "
                 "predicción al 95 %.")
    h += captura("03_semanal.png", "Figura 3. Serie semanal: acumulado de la zafra en curso y pronóstico de las "
                 "siguientes semanas.")
    h += captura("04_datatable.png", "Figura 4. Componente DataTable con los datos procesados por el ETL.")
    h += captura("05_regresion_xy.png", "Figura 5. Regresión lineal simple: azúcar producida total vs. caña "
                 "molida neta.")
    h += captura("06_ingenios.png", "Figura 6. Indicadores por ingenio y producción nacional por zafra.")
    h += captura("07_interpretacion.png", "Figura 7. Pestaña de interpretación para la toma de decisiones.")

    h += [Paragraph("Métricas del modelo anual (nacional)", H2),
          tabla([["Concepto", "Valor"],
                 ["Zafras completas usadas", f"{len(comp)} ({comp.etiqueta.iloc[0]} a {comp.etiqueta.iloc[-1]})"],
                 ["Entrenamiento / prueba", f"{r.n_train} / {r.n_test} zafras (80 % / 20 %, cronológico)"],
                 ["Ecuación (recalibrada)", r.ecuacion],
                 ["R² entrenamiento", f(r.r2_train, 3)],
                 ["R² prueba", f(r.r2_test, 3) if r.r2_test == r.r2_test else "n/d (1 punto de prueba)"],
                 ["MAE prueba (t)", f(r.mae)], ["RMSE prueba (t)", f(r.rmse)], ["MAPE prueba", f"{f(r.mape, 2)} %"]],
                [6 * cm, 10.5 * cm]),
          Spacer(1, 6),
          Paragraph("Regresión azúcar producida total vs. caña molida neta", H2),
          Paragraph(f"Ŷ = {f(xy.b0, 2)} + {xy.b1:.5f}·X. Con {len(xy.datos)} observaciones (ingenio-zafra), "
                    f"el modelo obtuvo R² = {xy.r2_train:.4f} en entrenamiento y R² = {xy.r2_test:.4f} en prueba "
                    f"(MAE = {f(xy.mae)} t). La pendiente indica que por cada tonelada de caña neta molida se "
                    f"obtienen en promedio {xy.b1 * 1000:.1f} kg de azúcar, lo que confirma que la caña molida es "
                    "el principal determinante del volumen producido.", P)]

    # ---- Interpretación ------------------------------------------------------------
    h += [PageBreak(), Paragraph("5. Interpretación de resultados y cuestionamientos del caso de estudio", H1),
          Paragraph("Pregunta 1. ¿Cuál es el último valor real de los datos históricos?", H2),
          Paragraph(f"El último registro real disponible corresponde a la zafra <b>{ult.etiqueta}</b>, semana "
                    f"{int(ult.semanas)}, con un acumulado nacional de <b>{f(ult.y)} t</b> de azúcar. Como esta "
                    "zafra sigue en curso, el valor es parcial y no se usa para calibrar el modelo anual.", P),
          Paragraph(f"El último valor real de una zafra completa es <b>{f(uc.y)} t</b> de azúcar en la zafra "
                    f"<b>{uc.etiqueta}</b>; este es el valor que el dashboard muestra como “Último valor real” en "
                    "la serie anual.", P),
          Paragraph("Pregunta 2. ¿Cómo ha cambiado la producción total de azúcar a lo largo de las zafras y "
                    "cuánto podría producirse en la próxima zafra si la tendencia continúa?", H2),
          Paragraph(f"Entre {comp.etiqueta.iloc[0]} y {comp.etiqueta.iloc[-1]} la producción nacional pasó de "
                    f"{f(comp.y.iloc[0])} t a {f(comp.y.iloc[-1])} t, una tasa media anual de {tasa:+.2f} %. El "
                    f"máximo se registró en {comp.etiqueta[imax]} ({f(comp.y[imax])} t) y el mínimo en "
                    f"{comp.etiqueta[imin]} ({f(comp.y[imin])} t).", P),
          Paragraph(f"La regresión lineal estima una pendiente β1 = {f(r.b1)} t por zafra, es decir, una "
                    f"tendencia <b>{'creciente' if r.b1 > 0 else 'decreciente'}</b>. En el conjunto de prueba el "
                    f"error medio fue de {f(r.mae)} t (MAPE {f(r.mape, 2)} %).", P),
          Paragraph(f"<b>Si la tendencia continúa, la próxima zafra ({M.etiqueta_zafra(p1.x)}) produciría "
                    f"aproximadamente {f(p1.y)} t de azúcar</b>, con un intervalo de predicción al 95 % de "
                    f"{f(max(p1.li, 0))} a {f(p1.ls)} t.", P)]
    pron = [["Zafra", "Pronóstico (t)", "Límite inferior 95 %", "Límite superior 95 %"]]
    for _, q in r.pronostico.iterrows():
        pron.append([M.etiqueta_zafra(q.x), f(q.y), f(max(q.li, 0)), f(q.ls)])
    h += [tabla(pron, [3.5 * cm, 4 * cm, 4.5 * cm, 4.5 * cm]), Spacer(1, 6)]
    if len(curso):
        c = curso.iloc[0]
        h += [Paragraph(f"Al corte de la semana {int(c.semanas)}, la zafra {c.etiqueta} acumula {f(c.y)} t, "
                        f"equivalente al {c.y / p1.y * 100:.1f} % del valor pronosticado para la zafra completa. "
                        "El dashboard permite seguir este avance en la vista semanal.", P)]
    h += [Paragraph("Toma de decisiones", H2)]
    h += bullets([
        "El pronóstico anticipa la oferta nacional de azúcar, útil para planear inventarios, exportaciones "
        "y la logística de molienda y transporte.",
        "La amplitud del intervalo de predicción muestra que la producción es sensible a factores externos "
        "(clima, sequías, plagas, superficie cosechada), por lo que el pronóstico lineal es una referencia de "
        "tendencia y no un valor exacto.",
        "La relación casi lineal entre caña molida neta y azúcar producida indica que las acciones que "
        "incrementan la caña disponible y el rendimiento en fábrica impactan directamente la producción.",
        "Se recomienda recalibrar el modelo cada semana con los datos nuevos de Infocaña y comparar "
        "periodos de calibración distintos desde el dashboard.",
    ])
    h += [Paragraph("6. Conclusiones", H1),
          Paragraph("Se construyó un flujo completo de analítica de datos: un pipeline ETL que integra y depura "
                    "los datos abiertos de Infocaña de varias zafras, un modelo de regresión lineal evaluado con una "
                    "división cronológica 80/20 y un dashboard interactivo en Shiny for Python desplegado como sitio "
                    "estático en GitHub Pages. El dashboard permite al usuario elegir la variable, el ingenio, la "
                    "frecuencia y el horizonte, calibrar el modelo y consultar los datos, lo que lo convierte en una "
                    "herramienta de apoyo para la toma de decisiones en el sector agroindustrial.", P),
          Paragraph("Como limitación, la regresión lineal sólo captura la tendencia de largo plazo; con pocas "
                    "zafras y alta variabilidad interanual el intervalo de predicción es amplio. Como trabajo "
                    "futuro se pueden incorporar modelos con estacionalidad (ARIMA/SARIMA) o regresión múltiple con "
                    "variables climáticas y de superficie.", P),
          Paragraph("Fuente de datos", H2),
          Paragraph("CONADESUCA. <i>Avance de la producción de caña y azúcar (Infocaña)</i>. Datos abiertos, "
                    "https://www.datos.gob.mx/dataset/avance_produccion_cana_azucar_infocana (licencia CC-BY 4.0).", P)]

    # ---- Anexo --------------------------------------------------------------------
    h += [PageBreak(), Paragraph("Anexo A. Código fuente", H1)]
    h += codigo(ROOT / "etl" / "etl_infocana.py", "A.1 etl/etl_infocana.py — Pipeline ETL")
    h += [PageBreak()] + codigo(ROOT / "app" / "modelo.py", "A.2 app/modelo.py — Modelo de regresión lineal")

    doc = SimpleDocTemplate(str(SALIDA), pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title="Proyecto Final Big Data - Infocaña", author="Equipo Big Data UNACH")
    doc.build(h, onFirstPage=lambda c, d: None, onLaterPages=pie_pagina)
    print(f"Informe generado: {SALIDA}")


if __name__ == "__main__":
    main()
