"""Sanctions feed: list parsers, snapshot diff, the collector (offline fakes), vessel linking, publish rows."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from algent_backend.sanctions import collect as collect_mod
from algent_backend.sanctions import diff as diffmod
from algent_backend.sanctions import publish as pub
from algent_backend.sanctions import store, vessels
from algent_backend.sanctions.contracts import Entry
from algent_backend.sanctions.sources import eu, ofac, uk

OFAC_XML = """<?xml version="1.0"?>
<sdnList xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML">
  <sdnEntry><uid>36</uid><lastName>AEROCARIBBEAN AIRLINES</lastName><sdnType>Entity</sdnType>
    <programList><program>CUBA</program></programList>
    <addressList><address><uid>25</uid><city>Havana</city><country>Cuba</country></address></addressList></sdnEntry>
  <sdnEntry><uid>4238</uid><lastName>MAR AZUL</lastName><sdnType>Vessel</sdnType>
    <programList><program>IRAN</program></programList>
    <idList><id><uid>1</uid><idType>Vessel Registration Identification</idType><idNumber>IMO 7406784</idNumber></id></idList>
    <vesselInfo><vesselFlag>Panama</vesselFlag><vesselOwner>Samir de Navegacion S.A.</vesselOwner></vesselInfo></sdnEntry>
  <sdnEntry><uid>2674</uid><firstName>Abu</firstName><lastName>ABBAS</lastName><sdnType>Individual</sdnType>
    <programList><program>SDGT</program></programList>
    <nationalityList><nationality><uid>9</uid><country>Egypt</country></nationality></nationalityList></sdnEntry>
</sdnList>"""

UK_XML = """<?xml version="1.0" encoding="utf-8"?>
<Designations>
  <Designation><DateDesignated>12/10/2026</DateDesignated><UniqueID>RUS1</UniqueID>
    <Names><Name><Name1>IVAN</Name1><Name6>PETROV</Name6><NameType>Primary Name</NameType></Name>
           <Name><Name6>I. Petrov</Name6><NameType>Alias</NameType></Name></Names>
    <RegimeName>The Russia (Sanctions) (EU Exit) Regulations 2019</RegimeName>
    <IndividualEntityShip>Individual</IndividualEntityShip>
    <Addresses><Address><AddressCountry>Russia</AddressCountry></Address></Addresses></Designation>
  <Designation><DateDesignated>03/10/2017</DateDesignated><UniqueID>DPR0075</UniqueID>
    <Names><Name><Name6>Petrel 8</Name6><NameType>Primary name</NameType></Name></Names>
    <RegimeName>The Democratic People's Republic of Korea (Sanctions) (EU Exit) Regulations 2019</RegimeName>
    <IndividualEntityShip>Ship</IndividualEntityShip>
    <ShipDetails><Ship><IMONumbers><IMONumber>IMO9562233</IMONumber></IMONumbers>
      <CurrentBelievedFlagOfShips><CurrentBelievedFlagOfShip>Comoros</CurrentBelievedFlagOfShip></CurrentBelievedFlagOfShips></Ship></ShipDetails></Designation>
</Designations>"""

EU_XML = """<?xml version="1.0" encoding="UTF-8"?>
<export xmlns="http://eu.europa.ec/fpi/fsd/export">
  <sanctionEntity designationDate="2026-10-08" logicalId="185569">
    <regulation publicationDate="2026-10-08" programme="UKR"><publicationUrl>https://eur-lex.europa.eu/x</publicationUrl></regulation>
    <subjectType code="enterprise"/>
    <nameAlias wholeName="ARMORGRUPP LLC"/><address countryIso2Code="RU"/>
  </sanctionEntity>
  <sanctionEntity logicalId="55"><regulation publicationDate="2016-03-05" programme="PRK"/>
    <subjectType code="enterprise"/><nameAlias wholeName="Some Ship"/>
    <identification number="5342883" identificationTypeCode="imo" countryIso2Code="00"/></sanctionEntity>
</export>"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "list.xml"
    p.write_text(text, encoding="utf-8")
    return p


def test_ofac_parse(tmp_path):
    got = ofac.parse(_write(tmp_path, OFAC_XML))
    assert set(got) == {"36", "4238", "2674"}
    assert got["36"].type == "entity" and got["36"].countries == ["CU"]
    ship = got["4238"]
    assert (ship.type, ship.imo, ship.flag, ship.owner) == ("vessel", "7406784", "PA", "Samir de Navegacion S.A.")
    assert got["2674"].name == "Abu ABBAS" and got["2674"].type == "person" and got["2674"].countries == ["EG"]


def test_uk_parse(tmp_path):
    got = uk.parse(_write(tmp_path, UK_XML))
    p = got["RUS1"]
    assert p.name == "IVAN PETROV" and p.designated_on == "2026-10-12" and p.countries == ["RU"] and p.programmes == ["Russia"]
    s = got["DPR0075"]
    assert (s.type, s.imo, s.flag) == ("vessel", "9562233", "KM")


def test_eu_parse(tmp_path):
    got = eu.parse(_write(tmp_path, EU_XML))
    assert got["185569"].designated_on == "2026-10-08" and got["185569"].countries == ["RU"] and got["185569"].programmes == ["UKR"]
    assert got["55"].type == "vessel" and got["55"].imo == "5342883"


def _e(ref, name="X", **kw):
    return Entry(ref=ref, name=name, **kw)


def test_diff_baseline_only_recent_listed_dates():
    day = date(2026, 10, 16)
    new = {"a": _e("a", designated_on="2026-10-12"), "b": _e("b", designated_on="2017-01-01"), "c": _e("c")}
    ev = diffmod.diff("uk", None, new, day)
    assert [e.ref for e in ev] == ["a"] and ev[0].baseline and ev[0].date == "2026-10-12"
    assert diffmod.diff("ofac", None, {"c": _e("c")}, day) == []


def test_diff_added_removed_and_dating():
    day = date(2026, 10, 16)
    old = {"a": _e("a"), "b": _e("b")}
    new = {"a": _e("a"), "c": _e("c", designated_on="2026-10-14"), "d": _e("d", designated_on="2020-01-01")}
    ev = {(e.action, e.ref): e for e in diffmod.diff("eu", old, new, day)}
    assert set(ev) == {("designated", "c"), ("designated", "d"), ("delisted", "b")}
    assert ev[("designated", "c")].date == "2026-10-14"
    assert ev[("designated", "d")].date == "2026-10-16"          # a back-dated entry is dated the day we saw it
    assert ev[("delisted", "b")].date == "2026-10-16"


def test_diff_refuses_truncated_snapshot():
    old = {str(i): _e(str(i)) for i in range(10)}
    with pytest.raises(ValueError):
        diffmod.diff("ofac", old, {"1": _e("1")}, date(2026, 10, 16))


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_SANCTIONS_STORE", str(tmp_path / "sx"))
    monkeypatch.setenv("ALGENT_GEOLEDGER_STORE", str(tmp_path / "geo"))
    return tmp_path


def test_collect_baseline_then_diff_then_vessel_link(stores):
    snaps = [{"1": _e("1"), "2": _e("2", "Old Co")}, {"1": _e("1"), "3": _e("3", "SHIP ONE", type="vessel", imo="9562233", flag="KM", programmes=["IRAN"])}]
    state = {"i": 0}

    def fetch(_dir):
        return snaps[state["i"]]

    first = collect_mod.collect(["ofac"], today=date(2026, 10, 15), fetchers={"ofac": fetch})
    assert first["sources"][0]["baseline"] and first["sources"][0]["events"] == 0
    state["i"] = 1
    second = collect_mod.collect(["ofac"], today=date(2026, 10, 16), fetchers={"ofac": fetch})
    assert second["sources"][0]["events"] == 2
    kinds = sorted((e.action, e.name) for e in store.events())
    assert kinds == [("delisted", "Old Co"), ("designated", "SHIP ONE")]
    assert second["vessels"]["assets"] == 1 and second["vessels"]["events"] == 1
    # re-running the same day adds nothing
    again = collect_mod.collect(["ofac"], today=date(2026, 10, 16), fetchers={"ofac": fetch})
    assert again["sources"][0]["new"] == 0 and store.load_status()["ofac"]["last_ok"]
    from algent_backend.geoledger.store import Ledger

    led = Ledger()
    ship = next(a for a in led.live() if a.type == "vessel")
    assert ship.attrs["imo"] == "9562233" and led.status(ship.id).status == "designated"
    assert vessels.asset_id(next(e for e in store.events() if e.type == "vessel")) == ship.id


def test_collect_isolates_a_failing_source(stores):
    def boom(_dir):
        raise RuntimeError("down")

    rep = collect_mod.collect(["ofac", "uk"], today=date(2026, 10, 16), fetchers={"ofac": boom, "uk": lambda _d: {"1": _e("1")}})
    assert [r["status"] for r in rep["sources"]] == ["error", "ok"]
    assert "down" in store.load_status()["ofac"]["last_error"]


def test_publish_sends_only_new_rows(stores):
    collect_mod.collect(["uk"], today=date(2026, 10, 16), fetchers={"uk": lambda _d: {"1": _e("1", designated_on="2026-10-14")}}, link_vessels=False)
    sent: list = []

    class Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def executemany(self, sql, rows): sent.extend(rows)

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return Cur()
        def commit(self): pass

    res = pub.publish(connect=lambda: Conn())
    assert res["db"] and res["events"] == 1 and len(sent) == 1 and sent[0][1] == "uk"
    assert pub.publish(connect=lambda: Conn())["events"] == 0
