"""
Dashboard - Pronóstico de Series de Tiempo · Producción de azúcar en México
Shiny for Python + ShinyLive (despliegue estático en GitHub Pages).
Datos: Infocaña (CONADESUCA) vía datos.gob.mx, procesados con etl/etl_infocana.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["figure.dpi"] = 96
matplotlib.rcParams["font.family"] = "DejaVu Sans"
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter
from shiny import App, reactive, render, ui

import modelo as M

DATOS = M.cargar_datos()
ZAFRAS = DATOS["infocana_zafra"]["zafra"].tolist()
INGENIOS = sorted(DATOS["infocana_semanal"]["ingenio"].unique().tolist())
ULTIMA_ZAFRA = ZAFRAS[-1]

# Paleta validada (skill dataviz): serie 1 azul, 2 naranja, 3 aqua
AZUL, NARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
TINTA, TINTA2, GRIS, REJILLA, FONDO = "#0b0b0b", "#52514e", "#9a9893", "#e6e4df", "#fcfcfb"

TABLAS = {
    "infocana_semanal": "Registros semanales por ingenio (limpios)",
    "infocana_zafra": "Agregado nacional por zafra",
    "infocana_ingenio_zafra": "Cierre por ingenio y zafra",
    "infocana_nacional_semanal": "Acumulado nacional por semana",
    "infocana_rend_ingenio": "Rendimiento promedio por ingenio",
}


def icono(path: str) -> ui.Tag:
    return ui.HTML(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="40" height="40" '
        f'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round">{path}</svg>'
    )


ICONO_CAL = icono('<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4M16 2v4M3 10h18"/>')
ICONO_DB = icono('<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>')
ICONO_TEND = icono('<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>')
ICONO_DIANA = icono('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>')

CSS = f"""
.navbar, .bslib-page-title {{ background:#14284b !important; color:#fff !important; }}
.bslib-page-title {{ padding:.7rem 1.2rem; font-weight:600; letter-spacing:.2px; }}
.bslib-sidebar-layout > .sidebar {{ background:#f3f6fb; }}
.value-box-title {{ font-size:.85rem; }}
.value-box-value {{ font-size:1.6rem !important; }}
.estado-modelo {{ background:#eaf6ee; border-radius:.5rem; padding:.7rem .8rem; font-size:.9rem; }}
.estado-modelo b {{ color:{AZUL}; }}
.metrica td {{ padding:.15rem .5rem; }}
.metrica td:first-child {{ color:{TINTA2}; }}
.respuesta {{ font-size:1rem; line-height:1.55; }}
.respuesta h5 {{ margin-top:1rem; color:#14284b; }}
.nota {{ color:{TINTA2}; font-size:.85rem; }}
"""

# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
sidebar = ui.sidebar(
    ui.h5("⚙ Configuración del pronóstico"),
    ui.input_select("variable", "Variable (Y)", M.VARIABLES, selected="azucar_producida_total"),
    ui.input_select("ingenio", "Ingenio", {"": "Nacional (todos los ingenios)", **{i: i for i in INGENIOS}}),
    ui.input_select("frecuencia", "Frecuencia", {"anual": "Anual (por zafra)", "semanal": "Semanal (acumulado de una zafra)"}),
    ui.panel_conditional(
        "input.frecuencia === 'semanal'",
        ui.input_select("zafra_sem", "Zafra", ZAFRAS, selected=ULTIMA_ZAFRA),
    ),
    ui.input_radio_buttons("horizonte", "Horizonte de pronóstico", {"1": "1", "2": "2", "3": "3", "5": "5"},
                           selected="1", inline=True),
    ui.output_text("unidad_horizonte", inline=False),
    ui.hr(),
    ui.h6("Calibración del modelo"),
    ui.input_slider("prop_test", "Conjunto de prueba (%)", min=10, max=40, value=20, step=5, post="%"),
    ui.panel_conditional(
        "input.frecuencia === 'anual'",
        ui.input_slider("anio_desde", "Entrenar desde la zafra (año inicio)",
                        min=int(DATOS["infocana_zafra"]["anio_inicio"].min()),
                        max=int(DATOS["infocana_zafra"]["anio_inicio"].max()),
                        value=int(DATOS["infocana_zafra"]["anio_inicio"].min()), step=1, sep=""),
        ui.input_checkbox("excluir_curso", "Excluir zafra en curso (incompleta)", True),
    ),
    ui.input_action_button("generar", "▶ Generar pronóstico", class_="btn-primary w-100"),
    ui.output_ui("estado_modelo"),
    width=320,
)

tab_pronostico = ui.nav_panel(
    "Pronóstico",
    ui.layout_columns(
        ui.value_box("Horizonte", ui.output_text("vb_horizonte"), showcase=ICONO_CAL, theme="bg-gradient-blue-indigo"),
        ui.value_box("Último valor real", ui.output_text("vb_ultimo"), ui.output_text("vb_ultimo_sub"),
                     showcase=ICONO_DB, theme="primary"),
        ui.value_box("Pronóstico final", ui.output_text("vb_pronostico"), ui.output_text("vb_pron_sub"),
                     showcase=ICONO_TEND, theme="success"),
        ui.value_box("R² (prueba)", ui.output_text("vb_r2"), ui.output_text("vb_r2_sub"),
                     showcase=ICONO_DIANA, theme="light"),
        fill=False,
    ),
    ui.card(
        ui.card_header("📈 Serie histórica, ajuste y pronóstico (Regresión lineal)"),
        ui.output_plot("grafica_serie", height="440px"),
        full_screen=True,
    ),
    ui.layout_columns(
        ui.card(ui.card_header("Métricas del modelo (80/20 cronológico)"), ui.output_ui("metricas")),
        ui.card(ui.card_header("Valores pronosticados"), ui.output_data_frame("tabla_pronostico")),
        col_widths=[5, 7],
    ),
)

tab_datos = ui.nav_panel(
    "Datos (DataTable)",
    ui.card(
        ui.card_header(
            ui.layout_columns(
                ui.input_select("tabla", None, TABLAS, width="100%"),
                ui.output_text("conteo_tabla"),
                col_widths=[6, 6],
            )
        ),
        ui.output_data_frame("tabla_datos"),
        full_screen=True,
    ),
)

tab_xy = ui.nav_panel(
    "Regresión X–Y",
    ui.layout_columns(
        ui.card(
            ui.card_header("Y = β0 + β1·X   (Y: azúcar producida total)"),
            ui.input_select("xvar", "Variable independiente (X)", {
                "cana_molida_neta": "Caña molida neta (t)",
                "cana_molida_bruta": "Caña molida bruta (t)",
                "superficie_cosechada": "Superficie cosechada (ha)",
            }),
            ui.output_ui("metricas_xy"),
            ui.p("Cada punto es el cierre de un ingenio en una zafra. División aleatoria 80 % "
                 "entrenamiento / 20 % prueba (random_state=42).", class_="nota"),
        ),
        ui.card(ui.output_plot("grafica_xy", height="460px"), full_screen=True),
        col_widths=[4, 8],
    ),
)

tab_ingenios = ui.nav_panel(
    "Indicadores por ingenio",
    ui.layout_columns(
        ui.card(ui.card_header("Top 15 ingenios · producción promedio de azúcar por zafra"),
                ui.output_plot("grafica_ingenios", height="460px"), full_screen=True),
        ui.card(ui.card_header("Producción nacional por zafra"),
                ui.output_plot("grafica_barras_zafra", height="460px"), full_screen=True),
        col_widths=[6, 6],
    ),
)

tab_interp = ui.nav_panel(
    "Interpretación",
    ui.card(ui.card_header("Interpretación del dashboard para la toma de decisiones"),
            ui.output_ui("interpretacion")),
)

app_ui = ui.page_sidebar(
    sidebar,
    ui.navset_card_underline(tab_pronostico, tab_datos, tab_xy, tab_ingenios, tab_interp),
    ui.tags.style(CSS),
    title="📊 Dashboard - Pronóstico de Series de Tiempo · Producción de azúcar en México (Infocaña)",
    fillable=False,
)


# --------------------------------------------------------------------------
# Utilidades de formato
# --------------------------------------------------------------------------
def fmt(v: float, dec: int = 0) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:,.{dec}f}"


def fmt_corto(v: float, _pos=None) -> str:
    a = abs(v)
    if a >= 1e6:
        return f"{v / 1e6:.1f} M"
    if a >= 1e3:
        return f"{v / 1e3:.0f} k"
    return f"{v:.0f}"


def estilo_ejes(ax):
    ax.set_facecolor(FONDO)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRIS)
    ax.tick_params(colors=TINTA2, labelsize=9)
    ax.grid(True, color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(FuncFormatter(fmt_corto))


# --------------------------------------------------------------------------
# Servidor
# --------------------------------------------------------------------------
def server(input, output, session):

    @reactive.calc
    @reactive.event(input.generar, ignore_none=False)
    def calculo():
        variable = input.variable()
        ingenio = input.ingenio() or None
        h = int(input.horizonte())
        prop = input.prop_test() / 100
        if input.frecuencia() == "anual":
            serie = M.serie_anual(DATOS, variable, ingenio)
            en_curso = serie[~serie["completa"]]
            modelo_s = serie[serie["x"] >= input.anio_desde()]
            if input.excluir_curso():
                modelo_s = modelo_s[modelo_s["completa"]]
            else:
                en_curso = en_curso.iloc[0:0]
        else:
            serie = M.serie_semanal(DATOS, variable, input.zafra_sem(), ingenio)
            en_curso = serie.iloc[0:0]
            modelo_s = serie
        if len(modelo_s) < 3:
            return {"error": "Se requieren al menos 3 periodos para ajustar el modelo. "
                             "Amplíe el rango de calibración o elija otro ingenio/zafra."}
        res = M.ajustar_pronosticar(modelo_s, h, prop)
        return {"res": res, "en_curso": en_curso, "frecuencia": input.frecuencia(),
                "variable": variable, "ingenio": ingenio or "Nacional", "h": h}

    def etiqueta_x(x: float, frecuencia: str) -> str:
        return M.etiqueta_zafra(x) if frecuencia == "anual" else f"Semana {int(round(x))}"

    @render.text
    def unidad_horizonte():
        return "zafras (años) hacia adelante" if input.frecuencia() == "anual" else "semanas hacia adelante"

    # ---- Value boxes -----------------------------------------------------
    @render.text
    def vb_horizonte():
        c = calculo()
        if "error" in c:
            return "—"
        return f"{c['h']} {'zafra' if c['frecuencia'] == 'anual' else 'semana'}{'s' if c['h'] > 1 else ''}"

    @render.text
    def vb_ultimo():
        c = calculo()
        return "—" if "error" in c else fmt(c["res"].serie["y"].iloc[-1])

    @render.text
    def vb_ultimo_sub():
        c = calculo()
        if "error" in c:
            return ""
        return etiqueta_x(c["res"].serie["x"].iloc[-1], c["frecuencia"])

    @render.text
    def vb_pronostico():
        c = calculo()
        return "—" if "error" in c else fmt(c["res"].pronostico["y"].iloc[-1])

    @render.text
    def vb_pron_sub():
        c = calculo()
        if "error" in c:
            return ""
        p = c["res"].pronostico.iloc[-1]
        ultimo = c["res"].serie["y"].iloc[-1]
        cambio = (p.y / ultimo - 1) * 100 if ultimo else float("nan")
        return f"{etiqueta_x(p.x, c['frecuencia'])} · {cambio:+.1f} % vs. último"

    @render.text
    def vb_r2():
        c = calculo()
        return "—" if "error" in c else fmt(c["res"].r2_test, 3)

    @render.text
    def vb_r2_sub():
        c = calculo()
        return "" if "error" in c else f"MAPE prueba: {fmt(c['res'].mape, 2)} %"

    @render.ui
    def estado_modelo():
        c = calculo()
        if "error" in c:
            return ui.div(ui.p("⚠ " + c["error"]), class_="estado-modelo")
        r = c["res"]
        return ui.div(
            ui.div("📶 Modelo: ", ui.tags.b("Regresión Lineal (sklearn)")),
            ui.div("✅ Pronóstico generado"),
            ui.div(ui.tags.code(r.ecuacion), style="margin-top:.4rem;font-size:.8rem"),
            class_="estado-modelo mt-3",
        )

    # ---- Gráfica principal ----------------------------------------------
    @render.plot(alt="Serie histórica, ajuste de regresión lineal y pronóstico")
    def grafica_serie():
        c = calculo()
        fig, ax = plt.subplots(figsize=(11, 4.4))
        fig.patch.set_facecolor("white")
        estilo_ejes(ax)
        if "error" in c:
            ax.text(0.5, 0.5, c["error"], ha="center", va="center", transform=ax.transAxes, color=TINTA2)
            return fig
        r, frec = c["res"], c["frecuencia"]
        s, p = r.serie, r.pronostico
        # Datos históricos
        ax.plot(s["x"], s["y"], "-o", color=AZUL, lw=2, ms=6, label="Datos históricos", zorder=3)
        # Recta de regresión (todos los datos)
        xx = np.concatenate([s["x"].to_numpy(float), p["x"].to_numpy(float)])
        ax.plot(xx, r.b0 + r.b1 * xx, "--", color=GRIS, lw=1.2, label="Recta de regresión", zorder=2)
        # Conjunto de prueba (predicción del modelo de evaluación)
        if r.n_test:
            xt = s["x"].iloc[r.n_train:]
            ax.plot(xt, r.pred_test, "s", color=NARANJA, ms=8, mfc="white", mew=2,
                    label=f"Predicción en prueba ({r.n_test} periodos)", zorder=4)
            ax.axvspan(xt.iloc[0] - 0.5 * _paso(s), xt.iloc[-1] + 0.5 * _paso(s), color=NARANJA, alpha=0.06, lw=0)
        # Zafra en curso (parcial, fuera del modelo)
        ec = c["en_curso"]
        if len(ec):
            ax.plot(ec["x"], ec["y"], "o", color=GRIS, ms=8, mfc="white", mew=2,
                    label="Zafra en curso (parcial, excluida)", zorder=3)
        # Pronóstico
        x_last, y_last = s["x"].iloc[-1], s["y"].iloc[-1]
        ax.fill_between(p["x"], p["li"], p["ls"], color=AQUA, alpha=0.15, lw=0, label="Intervalo de predicción 95 %")
        ax.plot([x_last, *p["x"]], [y_last, *p["y"]], "-o", color=AQUA, lw=2, ms=6, label="Pronóstico", zorder=3)
        ax.axvline(x_last, color=GRIS, ls=":", lw=1.2)
        ax.annotate(f"Último dato: {fmt_corto(y_last)}", (x_last, y_last), xytext=(-12, 22),
                    textcoords="offset points", ha="right", fontsize=9, color=TINTA,
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=AZUL, lw=1),
                    arrowprops=dict(arrowstyle="-", color=AZUL, lw=1))
        pf = p.iloc[-1]
        ax.annotate(f"Pronóstico: {fmt_corto(pf.y)}", (pf.x, pf.y), xytext=(10, 0),
                    textcoords="offset points", ha="left", va="center", fontsize=9, color=TINTA,
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=AQUA, lw=1))
        ax.set_xlim(right=float(pf.x) + 1.6 * _paso(s))
        # Ejes
        ticks = list(s["x"]) + list(ec["x"]) + list(p["x"])
        ticks = sorted(set(float(t) for t in ticks))
        ax.set_xticks(ticks)
        if frec == "anual":
            ax.set_xticklabels([M.etiqueta_zafra(t) for t in ticks], rotation=35, ha="right")
            ax.set_xlabel("Zafra", color=TINTA2)
        else:
            ax.set_xticklabels([f"S{int(t)}" for t in ticks])
            ax.set_xlabel("Semana de zafra", color=TINTA2)
        ax.set_ylabel(M.VARIABLES[c["variable"]], color=TINTA2)
        ax.set_title(f"{M.VARIABLES[c['variable']]} · {c['ingenio']}", loc="left", fontsize=11, color=TINTA)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.30), ncol=3, frameon=False, fontsize=9,
                  labelcolor=TINTA2)
        fig.tight_layout()
        return fig

    def _paso(s):
        return float(np.median(np.diff(s["x"]))) if len(s) > 1 else 1.0

    @render.ui
    def metricas():
        c = calculo()
        if "error" in c:
            return ui.p(c["error"])
        r = c["res"]
        filas = [
            ("Periodos entrenamiento / prueba", f"{r.n_train} / {r.n_test}"),
            ("β0 (intercepto)", fmt(r.b0, 2)),
            ("β1 (pendiente por periodo)", fmt(r.b1, 2)),
            ("R² entrenamiento", fmt(r.r2_train, 3)),
            ("R² prueba", fmt(r.r2_test, 3)),
            ("MAE prueba", fmt(r.mae)),
            ("RMSE prueba", fmt(r.rmse)),
            ("MAPE prueba", f"{fmt(r.mape, 2)} %"),
        ]
        return ui.div(
            ui.tags.table(*[ui.tags.tr(ui.tags.td(a), ui.tags.td(ui.tags.b(b))) for a, b in filas], class_="metrica"),
            ui.p(f"Modelo recalibrado con todos los periodos: {r.ecuacion}", class_="nota mt-2"),
        )

    @render.data_frame
    def tabla_pronostico():
        c = calculo()
        if "error" in c:
            return pd.DataFrame()
        p = c["res"].pronostico
        return render.DataGrid(pd.DataFrame({
            "Periodo": [etiqueta_x(x, c["frecuencia"]) for x in p["x"]],
            "Pronóstico": p["y"].round(0).map(lambda v: f"{v:,.0f}"),
            "Límite inferior 95 %": p["li"].round(0).map(lambda v: f"{v:,.0f}"),
            "Límite superior 95 %": p["ls"].round(0).map(lambda v: f"{v:,.0f}"),
        }), width="100%")

    # ---- DataTable --------------------------------------------------------
    @render.text
    def conteo_tabla():
        df = DATOS[input.tabla()]
        return f"{len(df):,} registros · {df.shape[1]} columnas"

    @render.data_frame
    def tabla_datos():
        df = DATOS[input.tabla()].copy()
        num = df.select_dtypes("number").columns
        df[num] = df[num].round(3)
        return render.DataGrid(df, filters=True, height="560px", width="100%")

    # ---- Regresión X-Y ------------------------------------------------------
    @reactive.calc
    def calculo_xy():
        return M.regresion_xy(DATOS["infocana_ingenio_zafra"], input.xvar())

    @render.ui
    def metricas_xy():
        r = calculo_xy()
        filas = [("Observaciones", f"{len(r.datos)} (prueba: {int(r.es_test.sum())})"),
                 ("β0", fmt(r.b0, 2)), ("β1", fmt(r.b1, 5)),
                 ("R² entrenamiento", fmt(r.r2_train, 4)), ("R² prueba", fmt(r.r2_test, 4)),
                 ("MAE prueba", fmt(r.mae)), ("RMSE prueba", fmt(r.rmse))]
        return ui.tags.table(*[ui.tags.tr(ui.tags.td(a), ui.tags.td(ui.tags.b(b))) for a, b in filas],
                             class_="metrica")

    @render.plot(alt="Dispersión azúcar producida vs variable X con recta de regresión")
    def grafica_xy():
        r = calculo_xy()
        x, y = r.datos[input.xvar()], r.datos["azucar_producida_total"]
        fig, ax = plt.subplots(figsize=(8, 4.6))
        estilo_ejes(ax)
        ax.xaxis.set_major_formatter(FuncFormatter(fmt_corto))
        ax.scatter(x[~r.es_test], y[~r.es_test], s=34, color=AZUL, alpha=0.75, edgecolor="white", lw=0.8,
                   label="Entrenamiento (80 %)")
        ax.scatter(x[r.es_test], y[r.es_test], s=40, color=NARANJA, alpha=0.9, edgecolor="white", lw=0.8,
                   label="Prueba (20 %)")
        xx = np.linspace(0, x.max() * 1.03, 50)
        ax.plot(xx, r.b0 + r.b1 * xx, color=TINTA, lw=1.5, label=f"Ŷ = {r.b0:,.0f} + {r.b1:.4f}·X")
        etiquetas = {"cana_molida_neta": "Caña molida neta (t)", "cana_molida_bruta": "Caña molida bruta (t)",
                     "superficie_cosechada": "Superficie cosechada (ha)"}
        ax.set_xlabel(etiquetas[input.xvar()], color=TINTA2)
        ax.set_ylabel("Azúcar producida total (t)", color=TINTA2)
        ax.legend(frameon=False, fontsize=9, labelcolor=TINTA2)
        fig.tight_layout()
        return fig

    # ---- Indicadores ----------------------------------------------------
    @render.plot(alt="Top 15 ingenios por producción promedio de azúcar")
    def grafica_ingenios():
        d = DATOS["infocana_rend_ingenio"].nlargest(15, "azucar_promedio").iloc[::-1]
        fig, ax = plt.subplots(figsize=(7, 4.6))
        estilo_ejes(ax)
        ax.grid(axis="y", visible=False)
        ax.xaxis.set_major_formatter(FuncFormatter(fmt_corto))
        pos = np.arange(len(d))
        ax.barh(pos, d["azucar_promedio"].to_numpy(float), color=AZUL, height=0.7)
        ax.set_yticks(pos, [str(n) for n in d["ingenio"]])
        for yv, (v, rf) in enumerate(zip(d["azucar_promedio"], d["rend_fabrica_promedio"])):
            ax.text(v, yv, f"  {fmt_corto(v)} t · rend. {rf:.1f} %", va="center", fontsize=8, color=TINTA2)
        ax.set_xlim(0, d["azucar_promedio"].max() * 1.35)
        ax.tick_params(axis="y", labelsize=8)
        ax.set_xlabel("Azúcar promedio por zafra (t)", color=TINTA2)
        fig.tight_layout()
        return fig

    @render.plot(alt="Producción nacional de azúcar por zafra")
    def grafica_barras_zafra():
        d = DATOS["infocana_zafra"]
        fig, ax = plt.subplots(figsize=(7, 4.6))
        estilo_ejes(ax)
        ax.grid(axis="x", visible=False)
        completa = d["completa"].astype(str).str.lower().isin(["true", "1"])
        colores = [AZUL if cp else "#c9c7c1" for cp in completa]
        pos = np.arange(len(d))
        ax.bar(pos, d["azucar_producida_total"].to_numpy(float), color=colores, width=0.7)
        ax.set_xticks(pos, [str(zf) for zf in d["zafra"]])
        for i, (v, cp) in enumerate(zip(d["azucar_producida_total"], completa)):
            ax.text(i, v, fmt_corto(v) + ("" if cp else "\n(en curso)"), ha="center", va="bottom",
                    fontsize=8, color=TINTA2)
        ax.set_ylim(0, d["azucar_producida_total"].max() * 1.15)
        plt.setp(ax.get_xticklabels(), rotation=40, ha="right")
        ax.set_title("Azúcar producida total (t) · gris = zafra en curso", loc="left", fontsize=10, color=TINTA2)
        fig.tight_layout()
        return fig

    # ---- Interpretación ---------------------------------------------------
    @render.ui
    def interpretacion():
        serie = M.serie_anual(DATOS, "azucar_producida_total")
        comp = serie[serie["completa"]].reset_index(drop=True)
        curso = serie[~serie["completa"]]
        ult = serie.iloc[-1]
        bloques = [
            ui.h5("1. ¿Cuál es el último valor real de los datos históricos?"),
            ui.p(f"El último registro real corresponde a la zafra {ult.etiqueta} (semana {int(ult.semanas)}), "
                 f"con un acumulado nacional de {fmt(ult.y)} t de azúcar."
                 + (" Esta zafra sigue en curso, por lo que es un valor parcial." if not ult.completa else "")),
        ]
        if len(comp):
            uc = comp.iloc[-1]
            bloques.append(ui.p(f"La última zafra completa es {uc.etiqueta}, con {fmt(uc.y)} t "
                                "de azúcar producidas a nivel nacional; es el último valor real con el que "
                                "se calibra el modelo anual."))
        bloques.append(ui.h5("2. ¿Cómo ha cambiado la producción y cuánto podría producirse en la próxima zafra?"))
        if len(comp) >= 3:
            r = M.ajustar_pronosticar(comp, 1, 0.20)
            p = r.pronostico.iloc[0]
            imax, imin = comp["y"].idxmax(), comp["y"].idxmin()
            tasa = ((comp["y"].iloc[-1] / comp["y"].iloc[0]) ** (1 / (len(comp) - 1)) - 1) * 100
            tendencia = "creciente" if r.b1 > 0 else "decreciente"
            bloques += [
                ui.p(f"Entre {comp.etiqueta.iloc[0]} y {comp.etiqueta.iloc[-1]} la producción pasó de "
                     f"{fmt(comp.y.iloc[0])} t a {fmt(comp.y.iloc[-1])} t (tasa media anual {tasa:+.2f} %). "
                     f"El máximo se registró en {comp.etiqueta[imax]} ({fmt(comp.y[imax])} t) y el mínimo en "
                     f"{comp.etiqueta[imin]} ({fmt(comp.y[imin])} t)."),
                ui.p(f"La regresión lineal (X = periodo/zafra) estima una tendencia {tendencia} de "
                     f"{fmt(r.b1)} t por zafra ({r.ecuacion}). En el 20 % de prueba obtuvo "
                     f"MAE = {fmt(r.mae)} t y MAPE = {fmt(r.mape, 2)} %."),
                ui.p(ui.tags.b(f"Si la tendencia continúa, la próxima zafra ({M.etiqueta_zafra(p.x)}) "
                               f"produciría alrededor de {fmt(p.y)} t de azúcar "
                               f"(intervalo de predicción 95 %: {fmt(max(p.li, 0))} – {fmt(p.ls)} t).")),
            ]
            if len(curso):
                bloques.append(ui.p(f"Nota: la zafra {curso.etiqueta.iloc[0]} lleva {fmt(curso.y.iloc[0])} t "
                                    f"al corte de la semana {int(curso.semanas.iloc[0])}, "
                                    f"{curso.y.iloc[0] / p.y * 100:.1f} % del valor pronosticado para una zafra "
                                    "completa.", class_="nota"))
        else:
            bloques.append(ui.p("Se requieren al menos 3 zafras completas para estimar la tendencia anual."))
        bloques.append(ui.p("Implicaciones para la toma de decisiones: el pronóstico permite anticipar la "
                            "oferta nacional de azúcar para planear inventarios, exportaciones y la logística "
                            "de molienda. Como la producción depende del clima y de la superficie cosechada, "
                            "el pronóstico lineal debe leerse junto con su intervalo de predicción y "
                            "recalibrarse cada semana con los nuevos datos de Infocaña.", class_="nota"))
        return ui.div(*bloques, class_="respuesta")


app = App(app_ui, server)
