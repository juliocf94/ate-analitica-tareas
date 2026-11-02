"""Pruebas del flujo de caja y los indicadores financieros (Hito II)."""
from src.utils.finanzas import SUPUESTOS, escenarios, flujo_de_caja, indicadores


def test_piloto_y_vacaciones_no_facturan():
    df = flujo_de_caja().set_index("mes")
    assert df.loc[0, "inversion"] == sum(SUPUESTOS.inversion_inicial.values())
    # Meses 1 a 3: piloto gratuito; diciembre y enero: vacaciones escolares.
    assert (df.loc[1:3, "ingresos"] == 0).all()
    assert (df[df["mes_calendario"].isin([1, 12])]["ingresos"] == 0).all()
    assert df["acumulado"].iloc[-1] == round(df["flujo_neto"].sum(), 2)


def test_mas_adopcion_da_mejor_roi():
    esc = escenarios().query("horizonte == '24_meses'").set_index("escenario")
    assert esc.loc["pesimista", "roi"] < esc.loc["base", "roi"] < esc.loc["optimista", "roi"]
    base = indicadores(flujo_de_caja())
    assert base["24_meses"]["roi"] == esc.loc["base", "roi"]
