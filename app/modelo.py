"""
Modelo de series de tiempo con regresión lineal (scikit-learn).

    Y = β0 + β1·X

* Serie anual   : X = periodo (zafra, año de inicio), Y = variable agregada
                  a nivel nacional o por ingenio (cierre de cada zafra).
* Serie semanal : X = semana de zafra, Y = acumulado de la zafra elegida.

División del conjunto de datos: 80 % entrenamiento / 20 % prueba. Al ser una
serie de tiempo la división es cronológica (sin barajar): los periodos más
recientes forman el conjunto de prueba. Una vez evaluado, el modelo se
recalibra con todos los datos para generar el pronóstico.

También incluye la regresión lineal simple Y = azúcar producida total,
X = caña molida neta (ejemplo del documento del proyecto).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

DATA_DIR = Path(__file__).parent / "data"

VARIABLES = {
    "azucar_producida_total": "Azúcar producida total (t)",
    "cana_molida_neta": "Caña molida neta (t)",
    "cana_molida_bruta": "Caña molida bruta (t)",
    "superficie_cosechada": "Superficie cosechada (ha)",
    "azucar_producida_estandar": "Azúcar estándar (t)",
    "azucar_producida_refinada": "Azúcar refinada (t)",
}

# Cuantiles t de Student (95 %, dos colas) para intervalos de predicción.
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 30: 2.042}


def t95(gl: int) -> float:
    if gl <= 0:
        return float("nan")
    claves = [k for k in sorted(_T95) if k <= gl]
    return _T95[claves[-1]] if gl <= 30 else 1.96


def cargar_datos(data_dir: Path = DATA_DIR) -> dict[str, pd.DataFrame]:
    nombres = ["infocana_semanal", "infocana_ingenio_zafra", "infocana_nacional_semanal",
               "infocana_zafra", "infocana_rend_ingenio"]
    return {n: pd.read_csv(data_dir / f"{n}.csv") for n in nombres}


# --------------------------------------------------------------------------
# Construcción de series
# --------------------------------------------------------------------------
def serie_anual(datos: dict, variable: str, ingenio: str | None = None) -> pd.DataFrame:
    """Serie por zafra. Columnas: etiqueta, x (año inicio), y, completa."""
    zafras = datos["infocana_zafra"][["zafra", "anio_inicio", "completa", "semanas"]]
    if ingenio:
        iz = datos["infocana_ingenio_zafra"]
        base = iz[iz["ingenio"] == ingenio][["zafra", variable]]
    else:
        base = datos["infocana_zafra"][["zafra", variable]]
    s = zafras.merge(base, on="zafra", how="inner")
    s = s.rename(columns={"zafra": "etiqueta", "anio_inicio": "x", variable: "y"})
    s["completa"] = s["completa"].astype(str).str.lower().isin(["true", "1"])
    return s.sort_values("x").reset_index(drop=True)


def serie_semanal(datos: dict, variable: str, zafra: str, ingenio: str | None = None) -> pd.DataFrame:
    """Acumulado semanal de la zafra. Columnas: etiqueta, x (semana), y."""
    if ingenio:
        d = datos["infocana_semanal"]
        d = d[(d["ingenio"] == ingenio) & (d["zafra"] == zafra)]
    else:
        d = datos["infocana_nacional_semanal"]
        d = d[d["zafra"] == zafra]
    s = d[["no_s_zafra", variable]].rename(columns={"no_s_zafra": "x", variable: "y"})
    s = s.sort_values("x").reset_index(drop=True)
    s["etiqueta"] = "S" + s["x"].astype(int).astype(str)
    s["completa"] = True
    return s


# --------------------------------------------------------------------------
# Ajuste, evaluación y pronóstico
# --------------------------------------------------------------------------
@dataclass
class Resultado:
    serie: pd.DataFrame
    n_train: int
    n_test: int
    b0: float
    b1: float
    b0_eval: float
    b1_eval: float
    r2_train: float
    r2_test: float
    mae: float
    rmse: float
    mape: float
    pronostico: pd.DataFrame = field(default_factory=pd.DataFrame)
    ajuste: np.ndarray = field(default_factory=lambda: np.array([]))
    pred_test: np.ndarray = field(default_factory=lambda: np.array([]))

    @property
    def ecuacion(self) -> str:
        signo = "+" if self.b1 >= 0 else "−"
        return f"Ŷ = {self.b0:,.2f} {signo} {abs(self.b1):,.2f}·X"


def dividir_cronologico(n: int, prop_test: float = 0.20) -> tuple[int, int]:
    """Devuelve (n_train, n_test) respetando el orden temporal."""
    if n < 3:
        return n, 0
    n_test = max(1, int(round(n * prop_test)))
    n_test = min(n_test, n - 2)  # al menos 2 puntos para entrenar
    return n - n_test, n_test


def ajustar_pronosticar(serie: pd.DataFrame, horizonte: int, prop_test: float = 0.20,
                        paso: float = 1.0) -> Resultado:
    s = serie.reset_index(drop=True)
    X = s[["x"]].to_numpy(dtype=float)
    y = s["y"].to_numpy(dtype=float)
    n = len(s)
    n_train, n_test = dividir_cronologico(n, prop_test)

    # 1) Evaluación: entrenar con el 80 % más antiguo, probar con el 20 % reciente
    m_eval = LinearRegression().fit(X[:n_train], y[:n_train])
    r2_train = r2_score(y[:n_train], m_eval.predict(X[:n_train])) if n_train > 2 else float("nan")
    if n_test:
        pred_test = m_eval.predict(X[n_train:])
        yt = y[n_train:]
        mae = mean_absolute_error(yt, pred_test)
        rmse = math.sqrt(mean_squared_error(yt, pred_test))
        mape = float(np.mean(np.abs((yt - pred_test) / np.where(yt == 0, np.nan, yt)))) * 100
        r2_test = r2_score(yt, pred_test) if n_test > 1 else float("nan")
    else:
        pred_test = np.array([])
        mae = rmse = mape = r2_test = float("nan")

    # 2) Recalibración con todos los datos y pronóstico
    m = LinearRegression().fit(X, y)
    ajuste = m.predict(X)
    x_fut = s["x"].iloc[-1] + paso * np.arange(1, horizonte + 1)
    y_fut = m.predict(x_fut.reshape(-1, 1))

    # Intervalo de predicción al 95 %
    gl = n - 2
    if gl > 0:
        s_res = math.sqrt(np.sum((y - ajuste) ** 2) / gl)
        xm = X[:, 0].mean()
        sxx = np.sum((X[:, 0] - xm) ** 2)
        margen = t95(gl) * s_res * np.sqrt(1 + 1 / n + (x_fut - xm) ** 2 / sxx)
    else:
        margen = np.full(horizonte, np.nan)
    pron = pd.DataFrame({"x": x_fut, "y": y_fut, "li": y_fut - margen, "ls": y_fut + margen})

    return Resultado(
        serie=s, n_train=n_train, n_test=n_test,
        b0=float(m.intercept_), b1=float(m.coef_[0]),
        b0_eval=float(m_eval.intercept_), b1_eval=float(m_eval.coef_[0]),
        r2_train=float(r2_train), r2_test=float(r2_test),
        mae=float(mae), rmse=float(rmse), mape=float(mape),
        pronostico=pron, ajuste=ajuste, pred_test=pred_test,
    )


def etiqueta_zafra(anio_inicio: float) -> str:
    a = int(round(anio_inicio))
    return f"{a}-{a + 1}"


# --------------------------------------------------------------------------
# Regresión lineal simple Y = β0 + β1·X (X = caña molida neta)
# --------------------------------------------------------------------------
@dataclass
class ResultadoXY:
    datos: pd.DataFrame
    es_test: np.ndarray
    b0: float
    b1: float
    r2_train: float
    r2_test: float
    mae: float
    rmse: float


def regresion_xy(ingenio_zafra: pd.DataFrame, xvar: str, yvar: str = "azucar_producida_total",
                 prop_test: float = 0.20, semilla: int = 42) -> ResultadoXY:
    d = ingenio_zafra[(ingenio_zafra[xvar] > 0) & (ingenio_zafra[yvar] > 0)].reset_index(drop=True)
    idx = np.arange(len(d))
    tr, te = train_test_split(idx, test_size=prop_test, random_state=semilla)
    X, y = d[[xvar]].to_numpy(float), d[yvar].to_numpy(float)
    m = LinearRegression().fit(X[tr], y[tr])
    pte = m.predict(X[te])
    es_test = np.zeros(len(d), dtype=bool)
    es_test[te] = True
    return ResultadoXY(
        datos=d, es_test=es_test, b0=float(m.intercept_), b1=float(m.coef_[0]),
        r2_train=float(r2_score(y[tr], m.predict(X[tr]))), r2_test=float(r2_score(y[te], pte)),
        mae=float(mean_absolute_error(y[te], pte)), rmse=float(math.sqrt(mean_squared_error(y[te], pte))),
    )


if __name__ == "__main__":
    datos = cargar_datos()
    serie = serie_anual(datos, "azucar_producida_total")
    completas = serie[serie["completa"]]
    print("Serie anual (zafras completas):")
    print(completas[["etiqueta", "y"]].to_string(index=False))
    if len(completas) >= 3:
        r = ajustar_pronosticar(completas, horizonte=1)
        print(f"\nTrain={r.n_train} Test={r.n_test} | {r.ecuacion}")
        print(f"R² train={r.r2_train:.3f} R² test={r.r2_test:.3f} MAE={r.mae:,.0f} RMSE={r.rmse:,.0f} MAPE={r.mape:.2f}%")
        p = r.pronostico.iloc[0]
        print(f"Pronóstico {etiqueta_zafra(p.x)}: {p.y:,.0f} t  (IC95 %: {p.li:,.0f} – {p.ls:,.0f})")
    xy = regresion_xy(datos["infocana_ingenio_zafra"], "cana_molida_neta")
    print(f"\nRegresión azúcar ~ caña neta: β0={xy.b0:,.2f} β1={xy.b1:.5f} R² test={xy.r2_test:.3f}")
