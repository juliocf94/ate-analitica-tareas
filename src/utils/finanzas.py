"""Flujo de caja simulado y ROI de ATE a 12 y 24 meses (Hito II).

Todos los supuestos están en :data:`SUPUESTOS` para que el jurado pueda
cambiarlos y volver a correr el cálculo::

    python -m src.utils.finanzas
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Supuestos:
    """Supuestos del modelo de negocio (USD, precios sin IVA).

    Attributes:
        precio_alumno_mes: Licencia por estudiante y mes lectivo.
        alumnos_por_centro: Matrícula promedio de un centro privado cliente.
        meses_lectivos: Meses del calendario (1 = enero) en que se factura; febrero a noviembre.
        centros_por_mes: Centros activos al cierre de cada mes, del 1 al 24 (los 3 primeros son piloto gratuito).
        inversion_inicial: Desarrollo (horas del equipo valoradas), revisión legal del aviso de privacidad y dominio.
        costos_nube: Costo mensual de infraestructura por tramo (desde el mes indicado).
        soporte_mensual: Desarrollador de medio tiempo para soporte, desde el mes 4.
        fijos_mensuales: Contabilidad y mercadeo, desde el mes 4.
        isr: Impuesto sobre la renta sobre la utilidad anual positiva (se paga en los meses 12 y 24).
        comision_ventas: Fracción del ingreso para quien consigue y acompaña a los centros.
        pasarela_pago: Comisión del procesador de pagos.
        tasa_descuento_anual: Para el valor actual neto (VAN).
    """

    precio_alumno_mes: float = 0.50
    alumnos_por_centro: int = 400
    meses_lectivos: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
    centros_por_mes: tuple[int, ...] = (2, 2, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20,
                                        21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32)
    inversion_inicial: dict = field(default_factory=lambda: {
        "desarrollo (3 personas x 160 h x 10 USD/h)": 4800.0,
        "revisión legal del aviso de privacidad (Decreto 144)": 300.0,
        "teléfonos de prueba (gama baja y Huawei)": 250.0,
        "dominio (primer año)": 15.0,
    })
    costos_nube: tuple[tuple[int, dict], ...] = (
        (1, {"MongoDB Atlas Flex": 30.0, "Render Starter (API)": 7.0, "Vercel Pro": 20.0, "AWS S3": 2.0}),
        (7, {"MongoDB Atlas M10": 57.0, "Render Starter (API)": 7.0, "Vercel Pro": 20.0, "AWS S3": 3.0}),
        (13, {"MongoDB Atlas M10": 57.0, "Render Standard (API)": 25.0, "Vercel Pro": 20.0, "AWS S3": 5.0}),
    )
    soporte_mensual: float = 500.0
    fijos_mensuales: dict = field(default_factory=lambda: {"contabilidad": 100.0, "mercadeo": 150.0})
    isr: float = 0.30
    comision_ventas: float = 0.10
    pasarela_pago: float = 0.035
    tasa_descuento_anual: float = 0.12
    mes_inicio: int = 1          # enero de 2027


SUPUESTOS = Supuestos()


def _nube(mes: int, s: Supuestos) -> float:
    vigente = [costos for desde, costos in s.costos_nube if desde <= mes][-1]
    return sum(vigente.values())


def flujo_de_caja(s: Supuestos = SUPUESTOS, meses: int = 24, factor_adopcion: float = 1.0) -> pd.DataFrame:
    """Flujo de caja mensual con el mes 0 como inversión inicial.

    Args:
        s: Supuestos del modelo.
        meses: Horizonte en meses.
        factor_adopcion: Multiplica los centros de cada mes (escenarios pesimista y optimista).

    Returns:
        Tabla con ingresos, costos, flujo neto y acumulado por mes.
    """
    filas = [{"mes": 0, "mes_calendario": None, "centros": 0, "ingresos": 0.0, "nube": 0.0, "soporte": 0.0,
              "comisiones": 0.0, "fijos": 0.0, "isr": 0.0, "inversion": sum(s.inversion_inicial.values())}]
    for m in range(1, meses + 1):
        calendario = (s.mes_inicio + m - 2) % 12 + 1
        centros = round(s.centros_por_mes[m - 1] * factor_adopcion)
        piloto = m <= 3
        factura = calendario in s.meses_lectivos and not piloto
        ingresos = centros * s.alumnos_por_centro * s.precio_alumno_mes if factura else 0.0
        filas.append({"mes": m, "mes_calendario": calendario, "centros": centros, "ingresos": ingresos,
                      "nube": _nube(m, s), "soporte": s.soporte_mensual if m >= 4 else 0.0,
                      "comisiones": ingresos * (s.comision_ventas + s.pasarela_pago),
                      "fijos": sum(s.fijos_mensuales.values()) if m >= 4 else 0.0, "isr": 0.0, "inversion": 0.0})
    df = pd.DataFrame(filas)
    operativos = ["nube", "soporte", "comisiones", "fijos"]
    for cierre in (12, 24):
        anio = df[(df["mes"] > cierre - 12) & (df["mes"] <= cierre)]
        utilidad = anio["ingresos"].sum() - anio[operativos].sum().sum()
        df.loc[df["mes"] == cierre, "isr"] = max(utilidad, 0) * s.isr
    df["egresos"] = df[operativos + ["isr", "inversion"]].sum(axis=1)
    df["flujo_neto"] = df["ingresos"] - df["egresos"]
    df["acumulado"] = df["flujo_neto"].cumsum()
    return df.round(2)


def indicadores(df: pd.DataFrame, s: Supuestos = SUPUESTOS) -> dict:
    """ROI, VAN y mes de recuperación a 12 y 24 meses.

    El ROI se calcula como (beneficio neto acumulado del período) / inversión,
    donde el beneficio neto ya descuenta la inversión inicial.
    """
    inversion = sum(s.inversion_inicial.values())
    tasa_mes = (1 + s.tasa_descuento_anual) ** (1 / 12) - 1
    resultado = {}
    for h in (12, 24):
        tramo = df[df["mes"] <= h]
        van = sum(f / (1 + tasa_mes) ** m for m, f in zip(tramo["mes"], tramo["flujo_neto"]))
        # Recuperación: primer mes a partir del cual el acumulado ya no vuelve a ser negativo.
        negativos = tramo[tramo["acumulado"] < 0]["mes"]
        positivo = tramo[tramo["mes"] > (negativos.max() if len(negativos) else -1)]
        resultado[f"{h}_meses"] = {
            "ingresos": round(tramo["ingresos"].sum(), 2),
            "egresos": round(tramo["egresos"].sum(), 2),
            "beneficio_neto": round(tramo["flujo_neto"].sum(), 2),
            "roi": round(tramo["flujo_neto"].sum() / inversion, 3),
            "van": round(van, 2),
            "mes_recuperacion": int(positivo["mes"].iloc[0]) if len(positivo) else None,
        }
    return resultado


def escenarios(s: Supuestos = SUPUESTOS) -> pd.DataFrame:
    """ROI y recuperación con adopción al 50 % (pesimista), 100 % (base) y 125 % (optimista)."""
    filas = []
    for nombre, factor in (("pesimista", 0.5), ("base", 1.0), ("optimista", 1.25)):
        ind = indicadores(flujo_de_caja(s, factor_adopcion=factor), s)
        for h, v in ind.items():
            filas.append({"escenario": nombre, "horizonte": h, **v})
    return pd.DataFrame(filas)


def graficar(df: pd.DataFrame, ruta: Path) -> Path:
    """Barras de flujo neto mensual y línea del acumulado."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig, eje = plt.subplots(figsize=(10, 4))
    colores = ["#9a3412" if v < 0 else "#1f5fae" for v in df["flujo_neto"]]
    eje.bar(df["mes"], df["flujo_neto"], color=colores, label="Flujo neto mensual")
    eje.plot(df["mes"], df["acumulado"], color="#111", marker="o", ms=3, label="Acumulado")
    eje.axhline(0, color="#666", lw=0.8)
    eje.set(xlabel="Mes (0 = inversión; 1 = enero 2027)", ylabel="USD",
            title="Flujo de caja simulado de ATE a 24 meses")
    eje.grid(alpha=0.3)
    eje.legend()
    fig.tight_layout()
    fig.savefig(ruta, dpi=130)
    plt.close(fig)
    return ruta


def main() -> None:
    """Calcula el flujo, imprime los indicadores y guarda tabla y figura en reports/."""
    import json

    df = flujo_de_caja()
    ind = indicadores(df)
    (RAIZ / "reports").mkdir(exist_ok=True)
    df.to_csv(RAIZ / "reports" / "flujo_caja_24m.csv", index=False)
    (RAIZ / "reports" / "indicadores_financieros.json").write_text(
        json.dumps({"supuestos": asdict(SUPUESTOS), "indicadores": ind}, indent=2, ensure_ascii=False,
                   default=str), encoding="utf-8")
    graficar(df, RAIZ / "reports" / "figures" / "flujo_caja_24m.png")
    esc = escenarios()
    esc.to_csv(RAIZ / "reports" / "escenarios_financieros.csv", index=False)
    print(df.to_string(index=False))
    print(json.dumps(ind, indent=2, ensure_ascii=False))
    print(esc.to_string(index=False))


if __name__ == "__main__":
    main()
