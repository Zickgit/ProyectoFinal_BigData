"""
Pipeline ETL - Infocaña (CONADESUCA)
=====================================

Proyecto final Big Data: "Análisis predictivo de la producción de azúcar en
México mediante regresión lineal y procesamiento ETL con datos abiertos de
Infocaña".

Fuente: https://www.datos.gob.mx/dataset/avance_produccion_cana_azucar_infocana

Etapas
------
1. Extract   : descarga los CSV de cada zafra (2014-2015 ... 2025-2026) desde
               datos.gob.mx. Si un archivo ya existe en data/raw se reutiliza
               (caché local), de modo que el pipeline también funciona sin red.
2. Transform : normaliza nombres de columnas, convierte tipos, elimina nulos y
               duplicados, genera variables derivadas y agrega por zafra.
3. Load      : guarda los resultados en DataFrames de pandas, archivos CSV y
               una base de datos SQLite (data/processed/infocana.db). Copia los
               CSV que necesita el dashboard a app/data/.

Uso
---
    python etl/etl_infocana.py            # usa caché y descarga lo que falte
    python etl/etl_infocana.py --offline  # sólo archivos locales de data/raw
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
import unicodedata
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
APP_DATA_DIR = ROOT / "app" / "data"
DB_PATH = PROCESSED_DIR / "infocana.db"

BASE_URL = (
    "https://repodatos.atdt.gob.mx/api_update/conadesuca/"
    "avance_produccion_cana_azucar_infocana/"
)

# Recursos publicados en datos.gob.mx (un CSV por zafra).
FUENTES: dict[str, str] = {
    "2014-2015": "infocana_14_15_resumen_ok.csv",
    "2015-2016": "infocana_15_16_resumen_ok.csv",
    "2016-2017": "infocana_16_17_resumen_ok.csv",
    "2017-2018": "infocana_17_18_resumen_ok.csv",
    "2018-2019": "infocana_18_19_resumen_ok.csv",
    "2019-2020": "infocana_19_20_resumen_ok.csv",
    "2020-2021": "infocana_20_21_resumen_ok.csv",
    "2021-2022": "infocana_21_22_resumen_ok.csv",
    "2022-2023": "infocana_22_23_resumen_ok.csv",
    "2023-2024": "infocana_23_24_resumen_ok.csv",
    "2024-2025": "Infocana_24_25_resumen_ok.csv",
    "2025-2026": "Infocana_25_26_resumen.csv",
}

# Columnas numéricas del esquema estándar de Infocaña.
COLUMNAS_NUMERICAS = [
    "no_s_zafra",
    "cana_molida_bruta",
    "cana_molida_neta",
    "superficie_cosechada",
    "azucar_producida_total",
    "azucar_producida_refinada",
    "azucar_producida_estandar",
    "azucar_producida_blanca_especial",
    "azucar_producida_mascabado",
    "toneladas_azucar_con_pol_menor_99_2",
    "karbe_ton_cana_bruta_teorico",
    "karbe_ton_cana_neta_teorico",
    "eficiencia_en_fabrica",
    "rendimiento_campo",
    "rendimiento_fabrica",
    "rendimiento_agroindustrial",
]

# Variables acumuladas (se suman entre ingenios al agregar a nivel nacional).
VARIABLES_ACUMULADAS = [
    "cana_molida_bruta",
    "cana_molida_neta",
    "superficie_cosechada",
    "azucar_producida_total",
    "azucar_producida_refinada",
    "azucar_producida_estandar",
    "azucar_producida_blanca_especial",
    "azucar_producida_mascabado",
    "toneladas_azucar_con_pol_menor_99_2",
]

# Sinónimos observados entre zafras -> nombre estándar.
SINONIMOS = {
    "ingenio_azucarero": "ingenio",
    "nombre_ingenio": "ingenio",
    "no_semana_zafra": "no_s_zafra",
    "num_semana_zafra": "no_s_zafra",
    "semana_zafra": "no_s_zafra",
    "no_s_de_zafra": "no_s_zafra",
    "karbe_ton_cania_bruta_teorico": "karbe_ton_cana_bruta_teorico",
    "karbe_ton_cania_neta_teorico": "karbe_ton_cana_neta_teorico",
    "cania_molida_bruta": "cana_molida_bruta",
    "cania_molida_neta": "cana_molida_neta",
    "toneladas_azucar_con_pol_menor_99_20": "toneladas_azucar_con_pol_menor_99_2",
    "eficiencia_fabrica": "eficiencia_en_fabrica",
    # Esquema de las zafras 2014-2015 a 2024-2025
    "semana": "no_s_zafra",
    "azucar_total": "azucar_producida_total",
    "azucar_refinada": "azucar_producida_refinada",
    "azucar_estandar": "azucar_producida_estandar",
    "azucar_blanca_especial": "azucar_producida_blanca_especial",
    "azucar_mascabado": "azucar_producida_mascabado",
    "azucar_pol_menor_99_2": "toneladas_azucar_con_pol_menor_99_2",
    "karbe_cana_bruta": "karbe_ton_cana_bruta_teorico",
    "karbe_cana_neta": "karbe_ton_cana_neta_teorico",
}


# --------------------------------------------------------------------------
# EXTRACT
# --------------------------------------------------------------------------
def descargar(zafra: str, archivo: str, offline: bool) -> Path | None:
    """Devuelve la ruta local del CSV de la zafra; lo descarga si hace falta."""
    destino = RAW_DIR / archivo
    if destino.exists() and destino.stat().st_size > 0 and not _es_html(destino):
        print(f"  [cache]     {zafra}: {archivo}")
        return destino
    if offline:
        print(f"  [faltante]  {zafra}: {archivo} (modo offline)")
        return None
    try:
        import requests

        resp = requests.get(
            BASE_URL + archivo,
            timeout=120,
            headers={"User-Agent": "ETL-Infocana/1.0 (proyecto academico)"},
        )
        resp.raise_for_status()
        if resp.content.lstrip()[:1] == b"<":
            raise ValueError("el servidor devolvió HTML en lugar de CSV")
        destino.write_bytes(resp.content)
        print(f"  [descarga]  {zafra}: {archivo} ({len(resp.content):,} bytes)")
        return destino
    except Exception as exc:  # noqa: BLE001
        print(f"  [error]     {zafra}: {archivo} -> {exc}")
        return None


def _es_html(ruta: Path) -> bool:
    with open(ruta, "rb") as fh:
        return fh.read(64).lstrip()[:1] == b"<"


def leer_csv(ruta: Path) -> pd.DataFrame:
    """Lee un CSV probando varias codificaciones y detectando el separador."""
    bruto = ruta.read_bytes()
    for codificacion in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            texto = bruto.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    primera = texto.splitlines()[0]
    sep = ";" if primera.count(";") > primera.count(",") else ","
    return pd.read_csv(StringIO(texto), sep=sep, dtype=str)


def extract(offline: bool = False) -> pd.DataFrame:
    print("EXTRACT")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    marcos = []
    for zafra, archivo in FUENTES.items():
        ruta = descargar(zafra, archivo, offline)
        if ruta is None:
            continue
        df = leer_csv(ruta)
        df["archivo_origen"] = archivo
        df["zafra_archivo"] = zafra
        marcos.append(df)
    # Cualquier otro CSV colocado manualmente en data/raw también se integra.
    conocidos = set(FUENTES.values())
    for ruta in sorted(RAW_DIR.glob("*.csv")):
        if ruta.name not in conocidos and not _es_html(ruta):
            print(f"  [extra]     {ruta.name}")
            df = leer_csv(ruta)
            df["archivo_origen"] = ruta.name
            df["zafra_archivo"] = _zafra_desde_nombre(ruta.name)
            marcos.append(df)
    if not marcos:
        sys.exit("No hay archivos CSV disponibles en data/raw.")
    print(f"  Archivos integrados: {len(marcos)}")
    return marcos


def _zafra_desde_nombre(nombre: str) -> str | None:
    m = re.search(r"(\d{2})_(\d{2})", nombre)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return f"20{a:02d}-20{b:02d}"


# --------------------------------------------------------------------------
# TRANSFORM
# --------------------------------------------------------------------------
def normalizar_columna(nombre: str) -> str:
    """'Caña Molida Bruta ' -> 'cana_molida_bruta'."""
    s = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s.strip().lower()).strip("_")
    return SINONIMOS.get(s, s)


def normalizar_zafra(valor: str | float, respaldo: str | None) -> str | None:
    if isinstance(valor, str):
        m = re.search(r"(\d{2,4})\s*[-/]\s*(\d{2,4})", valor)
        if m:
            a, b = m.group(1), m.group(2)
            a = int(a) + 2000 if len(a) == 2 else int(a)
            b = int(b) + 2000 if len(b) == 2 else int(b)
            return f"{a}-{b}"
    return respaldo


def limpiar_texto(valor):
    if not isinstance(valor, str):
        return valor
    return re.sub(r"\s+", " ", valor).strip()


# Ingenios que cambiaron de nombre entre zafras -> clave del nombre vigente.
ALIAS_INGENIOS = {
    "azsuremex - tenosique": "azsuremex",
    "cuatotolapam": "ciasa (cuatotolapam)",
    "el potrero": "central el potrero",
    "jose ma. martinez (tala)": "tala",
    "jose ma. morelos": "jose maria morelos",
    # Nota: en 2015-2016 "la providencia" (sem. 9-13) y "la providencia, central"
    # (sem. 14-34) son dos series acumuladas independientes (el acumulado se
    # reinicia), por eso "la providencia" NO se fusiona: se suman ambas.
    "la providencia, central": "central la providencia",
    "pablo machado (la margarita)": "la margarita",
    "pujiltic (cia. la fe)": "cia. la fe (pujiltic)",
    "san cristobal zcmx": "san cristobal",
    "san miguelito": "central san miguelito",
    "tamazula-saenz": "tamazula",
    "presidente benito juarez-santos": "presidente benito juarez",
}


def clave_ingenio(nombre: str) -> str:
    """'Lázaro Cárdenas - Siembra' y 'lazaro cardenas' -> 'lazaro cardenas'."""
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\s*-\s*siembra$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return ALIAS_INGENIOS.get(s, s)


def nombres_canonicos(ingenios: pd.Series) -> dict[str, str]:
    """Nombre a mostrar por ingenio: se prefiere la grafía con acentos (archivo
    más reciente); si sólo existe en minúsculas se usa el nombre más reciente
    que coincide con la clave, en formato de título."""
    acentuados: dict[str, str] = {}
    minusculas: dict[str, str] = {}
    for nombre in ingenios.dropna().unique():  # orden cronológico de las zafras
        k = clave_ingenio(nombre)
        limpio = re.sub(r"\s*-\s*[Ss]iembra$", "", nombre).strip()
        if nombre != nombre.lower():
            acentuados[k] = limpio
        elif clave_ingenio(limpio) == k and re.sub(r"\s+", " ", limpio.lower()) == k:
            minusculas[k] = limpio
        else:
            minusculas.setdefault(k, k)
    canon = {}
    for k in set(acentuados) | set(minusculas):
        if k in acentuados:
            canon[k] = acentuados[k]
        else:
            t = minusculas[k].title()
            for a, b in ((" De ", " de "), (" Del ", " del "), ("Cia.", "Cía.")):
                t = t.replace(a, b)
            canon[k] = t
    return canon


def transform(marcos: list[pd.DataFrame]) -> dict[str, pd.DataFrame]:
    print("TRANSFORM")
    normalizados = []
    for df in marcos:
        df = df.rename(columns=normalizar_columna)
        df = df.loc[:, ~df.columns.duplicated()]
        normalizados.append(df)
    datos = pd.concat(normalizados, ignore_index=True, sort=False)
    n0 = len(datos)
    print(f"  Registros integrados: {n0:,}")

    # Tipos de datos ------------------------------------------------------
    datos["ingenio"] = datos["ingenio"].map(limpiar_texto)
    canon = nombres_canonicos(datos["ingenio"])
    datos["ingenio"] = datos["ingenio"].map(lambda n: canon.get(clave_ingenio(n), n) if isinstance(n, str) else n)
    if "zafra" not in datos:
        datos["zafra"] = None
    datos["zafra"] = [
        normalizar_zafra(z, r) for z, r in zip(datos["zafra"], datos["zafra_archivo"])
    ]
    for col in COLUMNAS_NUMERICAS:
        if col not in datos:
            datos[col] = pd.NA
        datos[col] = pd.to_numeric(
            datos[col].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )

    # Limpieza ---------------------------------------------------------------
    clave = ["ingenio", "zafra", "no_s_zafra", "azucar_producida_total"]
    datos = datos.dropna(subset=clave)
    datos = datos[datos["ingenio"].str.len() > 0]
    # Volúmenes acumulados: un nulo significa "sin reporte" -> 0. Los indicadores
    # (eficiencias, rendimientos) se dejan nulos cuando la zafra no los publica.
    datos[VARIABLES_ACUMULADAS] = datos[VARIABLES_ACUMULADAS].fillna(0)
    # Valores negativos no tienen sentido físico
    datos = datos[(datos[VARIABLES_ACUMULADAS] >= 0).all(axis=1)]
    dup = datos.duplicated(subset=["ingenio", "zafra", "no_s_zafra"], keep="last")
    if dup.any():
        print(f"  Duplicados (ingenio, zafra, semana) eliminados: {int(dup.sum())}")
    datos = datos[~dup]
    datos["no_s_zafra"] = datos["no_s_zafra"].astype(int)
    print(f"  Registros eliminados por nulos/duplicados/negativos: {n0 - len(datos):,}")

    # Variables derivadas ---------------------------------------------------
    datos["anio_inicio"] = datos["zafra"].str[:4].astype(int)
    datos["rend_fabrica_calc"] = _ratio(datos["azucar_producida_total"], datos["cana_molida_neta"]) * 100
    datos["rend_campo_calc"] = _ratio(datos["cana_molida_bruta"], datos["superficie_cosechada"])
    datos["azucar_por_ha"] = _ratio(datos["azucar_producida_total"], datos["superficie_cosechada"])
    columnas = (
        ["ingenio", "zafra", "anio_inicio", "no_s_zafra"]
        + [c for c in COLUMNAS_NUMERICAS if c != "no_s_zafra"]
        + ["rend_fabrica_calc", "rend_campo_calc", "azucar_por_ha", "archivo_origen"]
    )
    semanal = datos[columnas].sort_values(["anio_inicio", "ingenio", "no_s_zafra"]).reset_index(drop=True)

    # Cierre por ingenio y zafra (los datos son acumulados -> última semana)
    ingenio_zafra = (
        semanal.sort_values("no_s_zafra")
        .groupby(["zafra", "ingenio"], as_index=False)
        .last()
        .rename(columns={"no_s_zafra": "ultima_semana"})
        .drop(columns=["archivo_origen"])
        .sort_values(["anio_inicio", "ingenio"])
        .reset_index(drop=True)
    )

    # Serie nacional semanal (acumulado nacional por semana de zafra) --------
    nacional_semanal = _nacional_semanal(semanal)

    # Agregación por año/zafra ------------------------------------------------
    agg = {c: "sum" for c in VARIABLES_ACUMULADAS}
    por_zafra = ingenio_zafra.groupby(["zafra", "anio_inicio"], as_index=False).agg(agg)
    extra = ingenio_zafra.groupby("zafra").agg(
        num_ingenios=("ingenio", "nunique"),
        semanas=("ultima_semana", "max"),
        rend_fabrica_prom_ingenios=("rend_fabrica_calc", "mean"),
    )
    por_zafra = por_zafra.merge(extra, on="zafra")
    por_zafra["rend_fabrica_nacional"] = _ratio(por_zafra["azucar_producida_total"], por_zafra["cana_molida_neta"]) * 100
    por_zafra["rend_campo_nacional"] = _ratio(por_zafra["cana_molida_bruta"], por_zafra["superficie_cosechada"])
    por_zafra["azucar_por_ha"] = _ratio(por_zafra["azucar_producida_total"], por_zafra["superficie_cosechada"])
    por_zafra = por_zafra.sort_values("anio_inicio").reset_index(drop=True)
    por_zafra["periodo"] = range(1, len(por_zafra) + 1)
    por_zafra["completa"] = _marcar_completas(por_zafra)
    por_zafra["var_pct_azucar"] = por_zafra["azucar_producida_total"].pct_change() * 100

    # Rendimiento promedio por ingenio (todas las zafras) ---------------------
    rend_ingenio = (
        ingenio_zafra.groupby("ingenio", as_index=False)
        .agg(
            zafras=("zafra", "nunique"),
            azucar_promedio=("azucar_producida_total", "mean"),
            cana_neta_promedio=("cana_molida_neta", "mean"),
            rend_fabrica_promedio=("rend_fabrica_calc", "mean"),
            rend_campo_promedio=("rend_campo_calc", "mean"),
            azucar_por_ha_promedio=("azucar_por_ha", "mean"),
        )
        .sort_values("azucar_promedio", ascending=False)
        .reset_index(drop=True)
    )

    print(f"  Registros limpios (semanal): {len(semanal):,}")
    print(f"  Ingenios: {semanal['ingenio'].nunique()} | Zafras: {semanal['zafra'].nunique()}")
    return {
        "infocana_semanal": semanal,
        "infocana_ingenio_zafra": ingenio_zafra,
        "infocana_nacional_semanal": nacional_semanal,
        "infocana_zafra": por_zafra,
        "infocana_rend_ingenio": rend_ingenio,
    }


def _ratio(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a / b.where(b > 0)).fillna(0).round(4)


def _marcar_completas(por_zafra: pd.DataFrame) -> pd.Series:
    """Las zafras históricas están cerradas. Sólo la más reciente puede estar en
    curso: se considera incompleta si su número de semanas es menor al 85 % de la
    mediana de semanas de las zafras anteriores."""
    completas = pd.Series(True, index=por_zafra.index)
    if len(por_zafra) > 1:
        ultima = por_zafra.index[-1]
        referencia = por_zafra["semanas"].iloc[:-1].median()
        completas[ultima] = bool(por_zafra.loc[ultima, "semanas"] >= 0.85 * referencia)
    else:
        completas.iloc[0] = bool(por_zafra["semanas"].iloc[0] >= 30)
    return completas


def _nacional_semanal(semanal: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for zafra, grupo in semanal.groupby("zafra"):
        semanas = range(1, int(grupo["no_s_zafra"].max()) + 1)
        tabla = {}
        for var in VARIABLES_ACUMULADAS:
            piv = grupo.pivot_table(index="no_s_zafra", columns="ingenio", values=var, aggfunc="last")
            # Acumulados: se arrastra el último valor reportado; antes del
            # arranque del ingenio el acumulado es 0.
            piv = piv.reindex(semanas).ffill().fillna(0)
            tabla[var] = piv.sum(axis=1)
        reporte = grupo.groupby("no_s_zafra")["ingenio"].nunique().reindex(semanas).fillna(0)
        df = pd.DataFrame(tabla)
        df["ingenios_reportando"] = reporte.astype(int)
        df["zafra"] = zafra
        df["anio_inicio"] = int(zafra[:4])
        df.index.name = "no_s_zafra"
        df = df[df["ingenios_reportando"].cumsum() > 0]  # desde la 1a semana con reportes
        filas.append(df.reset_index())
    out = pd.concat(filas, ignore_index=True)
    out = out[["zafra", "anio_inicio", "no_s_zafra", "ingenios_reportando"] + VARIABLES_ACUMULADAS]
    return out.sort_values(["anio_inicio", "no_s_zafra"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# LOAD
# --------------------------------------------------------------------------
def load(tablas: dict[str, pd.DataFrame]) -> None:
    print("LOAD")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        for nombre, df in tablas.items():
            df.to_sql(nombre, con, if_exists="replace", index=False)
            ruta = PROCESSED_DIR / f"{nombre}.csv"
            df.to_csv(ruta, index=False)
            shutil.copy(ruta, APP_DATA_DIR / ruta.name)
            print(f"  {nombre:<28} {len(df):>6,} filas -> {ruta.relative_to(ROOT)}")
    print(f"  SQLite: {DB_PATH.relative_to(ROOT)}")


def main() -> dict[str, pd.DataFrame]:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="no descargar; usar sólo data/raw")
    args = parser.parse_args()
    tablas = transform(extract(offline=args.offline))
    load(tablas)
    resumen = tablas["infocana_zafra"][["zafra", "num_ingenios", "semanas", "completa", "azucar_producida_total"]]
    print("\nProducción nacional de azúcar por zafra (t):")
    print(resumen.to_string(index=False))
    return tablas


if __name__ == "__main__":
    main()
