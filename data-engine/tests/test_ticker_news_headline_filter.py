import pytest

from app.services.ticker_news_lane import is_data_page_headline

DATA_PAGES = [
    "SPCX Precio de acciones, noticias, cotización e historial de SPCX Oct 2026 136.000 call (SPCX261030C00136000)",
    "ASTS Perfil y datos de criptomonedas de AST SpaceMobile tokenized stock (xStock) USD (ASTSX-USD)",
    "SPCX PSPCX3X a EUR: valor de precio de Arcus SPCX (3x Long) hoy en Euro",
    "Arcus SPCX (3x Long) (PSPCX3X) información de precios, capitalización de mercado, gráficos",
    "Previsión de ASTS: precio objetivo 2027, TV",
    "ASTS Oct 2026 72.000 call",
]
NEWS = [
    "Telecom stocks tumble on SpaceX spectrum acquisition news",
    "SpaceX Buys Wireless Spectrum For Starlink; Verizon, AT&T, T-Mobile Tumble",
    "B.Riley rebaja la calificación de AST Spacemobile por preocupaciones de precios",
    "Las acciones de AST SpaceMobile caen por doble noticia negativa",
    "AST SpaceMobile lanza BlueBird y fija precio de la oferta en 72 dólares",
    "SpaceX Plans $40 Billion Financing Deal Led by Apollo to Buy Nvidia AI Chips",
]


@pytest.mark.parametrize("title", DATA_PAGES)
def test_data_pages_are_filtered(title):
    assert is_data_page_headline(title)


@pytest.mark.parametrize("title", NEWS)
def test_real_news_is_kept(title):
    assert not is_data_page_headline(title)


def test_none_and_empty():
    assert not is_data_page_headline(None)
    assert not is_data_page_headline("")
