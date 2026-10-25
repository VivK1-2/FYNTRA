from app.providers.sec.provider import SECProvider


def _fact(val, start, end, fy=2023, fp="FY", form="10-K", filed="2023-11-03"):
    d = {"val": val, "end": end, "fy": fy, "fp": fp, "form": form, "filed": filed, "accn": "0000320193-23-000106"}
    if start:
        d["start"] = start
    return d


def test_picks_current_year_not_prior_comparative():
    # A FY2023 10-K also contains FY2022 and FY2021 values tagged fy=2023
    facts = {"us-gaap": {"Revenues": {"units": {"USD": [
        _fact(365, "2020-09-27", "2021-09-25"),
        _fact(394, "2021-09-26", "2022-09-24"),
        _fact(383, "2022-09-25", "2023-09-30"),
    ]}}}}
    r = SECProvider()._extract_fact(facts, ["Revenues"], 2023)
    assert r["value"] == 383 and r["source"]["xbrl_tag"] == "us-gaap:Revenues"


def test_flow_items_reject_quarterly_durations():
    facts = {"us-gaap": {"Revenues": {"units": {"USD": [_fact(90, "2023-07-02", "2023-09-30")]}}}}
    assert SECProvider()._extract_fact(facts, ["Revenues"], 2023) is None


def test_balance_sheet_instant_has_no_start():
    facts = {"us-gaap": {"Assets": {"units": {"USD": [
        _fact(352, None, "2022-09-24"), _fact(353, None, "2023-09-30")]}}}}
    r = SECProvider()._extract_fact(facts, ["Assets"], 2023, flow=False)
    assert r["value"] == 353


def test_ignores_non_annual_forms_and_falls_through_tags():
    facts = {"us-gaap": {
        "Revenues": {"units": {"USD": [_fact(1, "2022-09-25", "2023-09-30", form="10-Q")]}},
        "SalesRevenueNet": {"units": {"USD": [_fact(383, "2022-09-25", "2023-09-30")]}},
    }}
    r = SECProvider()._extract_fact(facts, ["Revenues", "SalesRevenueNet"], 2023)
    assert r["value"] == 383 and r["metric"] == "SalesRevenueNet"
