import json
import pytest


@pytest.fixture()
def setup(client):
    """建一个分类，含 品牌(select)、类型(multiselect)、价格(number)、日期(date) 四个字段。"""
    category = client.post("/api/categories", json={"name": "欢欢衣服"}).json()
    cid = category["id"]

    brand = client.post(
        f"/api/categories/{cid}/fields", json={"name": "品牌", "type": "select", "sort_order": 1}
    ).json()
    kind = client.post(
        f"/api/categories/{cid}/fields",
        json={"name": "衣服类型", "type": "multiselect", "sort_order": 2},
    ).json()
    price = client.post(
        f"/api/categories/{cid}/fields", json={"name": "购入价格", "type": "number", "sort_order": 3}
    ).json()
    bought = client.post(
        f"/api/categories/{cid}/fields", json={"name": "购入日期", "type": "date", "sort_order": 4}
    ).json()

    def opts(field, labels):
        return [
            client.post(f"/api/fields/{field['id']}/options", json={"label": label}).json()
            for label in labels
        ]

    brands = opts(brand, ["Nike", "Adidas", "Uniqlo"])
    kinds = opts(kind, ["外套", "卫衣"])

    def make(description, values):
        return client.post(
            "/api/logs",
            data={
                "category_id": cid,
                "description": description,
                "field_values": json.dumps(values),
            },
        ).json()

    logs = {
        "nike_coat": make("Nike外套", {
            str(brand["id"]): brands[0]["id"],
            str(kind["id"]): [kinds[0]["id"]],
            str(price["id"]): 899,
            str(bought["id"]): "2026-03-01",
        }),
        "adidas_hoodie": make("Adidas卫衣", {
            str(brand["id"]): brands[1]["id"],
            str(kind["id"]): [kinds[1]["id"]],
            str(price["id"]): 499,
            str(bought["id"]): "2026-01-15",
        }),
        "uniqlo_both": make("Uniqlo两种", {
            str(brand["id"]): brands[2]["id"],
            str(kind["id"]): [kinds[0]["id"], kinds[1]["id"]],
        }),
    }
    return {
        "category": category, "brand": brand, "kind": kind,
        "price": price, "bought": bought,
        "brands": brands, "kinds": kinds, "logs": logs,
    }


def _descriptions(body):
    return [item["description"] for item in body["items"]]


def test_filter_by_single_option(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "fv": [f"{setup['brand']['id']}:{setup['brands'][0]['id']}"]},
    ).json()
    assert _descriptions(body) == ["Nike外套"]
    assert body["total"] == 1


def test_same_field_multiple_options_is_or(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"], "fv": [
            f"{setup['brand']['id']}:{setup['brands'][0]['id']}",
            f"{setup['brand']['id']}:{setup['brands'][1]['id']}",
        ]},
    ).json()
    assert set(_descriptions(body)) == {"Nike外套", "Adidas卫衣"}


def test_different_fields_are_and(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"], "fv": [
            f"{setup['brand']['id']}:{setup['brands'][0]['id']}",
            f"{setup['kind']['id']}:{setup['kinds'][1]['id']}",
        ]},
    ).json()
    assert _descriptions(body) == []


def test_multiselect_filter_matches_any_selected_option(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "fv": [f"{setup['kind']['id']}:{setup['kinds'][0]['id']}"]},
    ).json()
    assert set(_descriptions(body)) == {"Nike外套", "Uniqlo两种"}


def test_sort_by_number_desc_puts_empty_last(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "sort": f"{setup['price']['id']}:desc"},
    ).json()
    assert _descriptions(body) == ["Nike外套", "Adidas卫衣", "Uniqlo两种"]

    # The order above happens to equal plain insertion order (Nike created first,
    # then Adidas, then Uniqlo), so on its own it wouldn't prove real number sorting
    # rather than some unrelated default ordering. Requesting the same field
    # ascending must swap the priced pair while still keeping the empty-valued log
    # last, which only a working build_sort produces.
    asc_body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "sort": f"{setup['price']['id']}:asc"},
    ).json()
    assert _descriptions(asc_body) == ["Adidas卫衣", "Nike外套", "Uniqlo两种"]


def test_sort_by_number_asc_puts_empty_last(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "sort": f"{setup['price']['id']}:asc"},
    ).json()
    assert _descriptions(body) == ["Adidas卫衣", "Nike外套", "Uniqlo两种"]


def test_sort_by_date_asc(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "sort": f"{setup['bought']['id']}:asc"},
    ).json()
    assert _descriptions(body)[:2] == ["Adidas卫衣", "Nike外套"]


def test_sort_by_non_sortable_field_falls_back(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "sort": f"{setup['brand']['id']}:asc"},
    ).json()
    assert _descriptions(body) == ["Uniqlo两种", "Adidas卫衣", "Nike外套"]


def test_garbage_filter_and_sort_params_are_ignored(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "fv": ["abc", "1:", ":2"], "sort": "垃圾"},
    ).json()
    assert body["total"] == 3

    # Prove the garbage entries were actually parsed and discarded, not that fv/sort
    # never reach the query at all: mixing in one VALID fv entry alongside the same
    # garbage must still filter down to the matching logs.
    filtered = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "fv": ["abc", "1:", ":2", f"{setup['kind']['id']}:{setup['kinds'][0]['id']}"],
                "sort": "垃圾"},
    ).json()
    assert filtered["total"] == 2
    assert set(_descriptions(filtered)) == {"Nike外套", "Uniqlo两种"}


def test_filter_total_reflects_filtered_count(client, setup):
    body = client.get(
        "/api/logs",
        params={"category_id": setup["category"]["id"],
                "fv": [f"{setup['kind']['id']}:{setup['kinds'][0]['id']}"]},
    ).json()
    assert body["total"] == 2
