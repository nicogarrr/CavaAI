"""yahoo_symbol: el sufijo sale de la BOLSA del master, no solo de la divisa."""
from types import SimpleNamespace

from app.services.propicks_price_service import yahoo_symbol


def test_exchange_suffix_beats_currency_heuristic():
    # ASML: EUR pero Amsterdam -> .AS, no .MC (F160)
    assert yahoo_symbol(SimpleNamespace(ticker="ASML", exchange="NYSE EURONEXT - EURONEXT AMSTERDAM", currency="EUR")) == "ASML.AS"
    # ALM: Almirall BME -> .MC (F159)
    assert yahoo_symbol(SimpleNamespace(ticker="ALM", exchange="BME", currency="EUR")) == "ALM.MC"
    # Toronto y Suiza
    assert yahoo_symbol(SimpleNamespace(ticker="BHC", exchange="TORONTO STOCK EXCHANGE", currency="CAD")) == "BHC.TO"
    assert yahoo_symbol(SimpleNamespace(ticker="UHR", exchange="SWISS EXCHANGE", currency="CHF")) == "UHR.SW"
    # US (USD en bolsa US, UNKNOWN o vacía): en crudo
    assert yahoo_symbol(SimpleNamespace(ticker="AAPL", exchange="NASDAQ NMS - GLOBAL MARKET", currency="USD")) == "AAPL"
    assert yahoo_symbol(SimpleNamespace(ticker="ACME", exchange="UNKNOWN", currency="USD")) == "ACME"
    # Ya calificado: intacto
    assert yahoo_symbol(SimpleNamespace(ticker="SAN.MC", exchange="BME", currency="EUR")) == "SAN.MC"


def test_xetra_usa_sufijo_de_verificado():
    # F167: SAP XETRA/EUR -> SAP.DE (Yahoo: GER, EUR ~186), nunca el ADS NYSE.
    assert yahoo_symbol(SimpleNamespace(ticker="SAP", exchange="XETRA", currency="EUR")) == "SAP.DE"


def test_yahoo_symbol_none_antes_que_otro_instrumento():
    # F164: TSM en Taiwán - Yahoo pelado devuelve el ADR NYSE en USD.
    assert yahoo_symbol(SimpleNamespace(ticker="TSM", exchange="TAIWAN STOCK EXCHANGE", currency="TWD")) is None
    # F165: NVO en Copenhague - el ADR NYSE en USD no es la línea DKK.
    assert yahoo_symbol(SimpleNamespace(ticker="NVO", exchange="OMX NORDIC EXCHANGE COPENHAGEN", currency="DKK")) is None
    # F166: SHEL LSE/USD - la bolsa declara Londres; la línea US no es ese instrumento.
    assert yahoo_symbol(SimpleNamespace(ticker="SHEL", exchange="LONDON STOCK EXCHANGE", currency="USD")) is None
    # EUR sin bolsa validada: .MC podría ser un homónimo madrileño.
    assert yahoo_symbol(SimpleNamespace(ticker="SAN", exchange="UNKNOWN", currency="EUR")) is None
    assert yahoo_symbol(SimpleNamespace(ticker="MC", exchange="EURONEXT PARIS", currency="EUR")) is None
