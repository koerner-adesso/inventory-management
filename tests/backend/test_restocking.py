"""
Tests for restocking API endpoints.
"""
from datetime import date, timedelta

import pytest


def recommendations(client, budget, strategy="urgency"):
    """Helper: fetch recommendations for a budget and strategy."""
    response = client.get(f"/api/restocking/recommendations?budget={budget}&strategy={strategy}")
    assert response.status_code == 200
    return response.json()


def max_budget(client):
    """Helper: cost of covering every shortfall."""
    return recommendations(client, 0)["max_budget"]


class TestRestockRecommendations:
    """Test suite for GET /api/restocking/recommendations."""

    def test_zero_budget_recommends_nothing(self, client):
        """Test that a zero budget recommends no items."""
        data = recommendations(client, 0)
        assert data["recommended"] == []
        assert data["total_cost"] == 0
        assert data["budget_remaining"] == 0
        assert len(data["skipped"]) > 0

    def test_large_budget_recommends_all_shortfalls(self, client):
        """Test that a budget above max_budget covers every shortfall."""
        data = recommendations(client, max_budget(client) + 1)
        assert data["skipped"] == []
        assert len(data["recommended"]) > 0
        assert abs(data["total_cost"] - data["max_budget"]) < 0.01

    def test_decreasing_item_not_recommended(self, client):
        """Test that an item with stock above forecast has no shortfall and is not listed."""
        data = recommendations(client, max_budget(client) + 1)
        listed = {item["sku"] for item in data["recommended"] + data["skipped"]}
        # MTR-304 has 40 on hand against a forecast of 35
        assert "MTR-304" not in listed

    def test_total_never_exceeds_budget(self, client):
        """Test that the recommended total stays within the budget for several budgets."""
        for budget in [500, 2500, 8000, 15000, 30000]:
            data = recommendations(client, budget)
            assert data["total_cost"] <= budget
            assert abs(data["total_cost"] + data["budget_remaining"] - budget) < 0.01

    def test_total_matches_recommended_items(self, client):
        """Test that total_cost equals the sum of the recommended line totals."""
        data = recommendations(client, 10000)
        line_sum = sum(item["total_cost"] for item in data["recommended"])
        assert abs(data["total_cost"] - line_sum) < 0.01

    def test_item_cost_calculation(self, client):
        """Test that each item's total is shortfall times unit cost."""
        data = recommendations(client, max_budget(client) + 1)
        for item in data["recommended"]:
            assert item["shortfall"] > 0
            assert abs(item["total_cost"] - item["shortfall"] * item["unit_cost"]) < 0.01

    def test_recommendation_structure(self, client):
        """Test that recommended items expose all fields the client needs."""
        data = recommendations(client, max_budget(client) + 1)
        item = data["recommended"][0]
        for field in ["sku", "name", "category", "supplier_name", "trend", "forecasted_demand",
                      "quantity_on_hand", "quantity_on_order", "shortfall", "unit_cost",
                      "total_cost", "lead_time_days"]:
            assert field in item

    def test_urgency_orders_by_shortfall(self, client):
        """Test that the urgency strategy ranks the largest shortfall first."""
        data = recommendations(client, max_budget(client) + 1, "urgency")
        shortfalls = [item["shortfall"] for item in data["recommended"]]
        assert shortfalls == sorted(shortfalls, reverse=True)

    def test_value_orders_by_shortfall_per_dollar(self, client):
        """Test that the value strategy ranks the best shortfall-per-dollar first."""
        data = recommendations(client, max_budget(client) + 1, "value")
        ratios = [item["shortfall"] / item["unit_cost"] for item in data["recommended"]]
        assert ratios == sorted(ratios, reverse=True)

    def test_strategies_rank_differently(self, client):
        """Test that the two strategies produce different orderings."""
        budget = max_budget(client) + 1
        urgency = [i["sku"] for i in recommendations(client, budget, "urgency")["recommended"]]
        value = [i["sku"] for i in recommendations(client, budget, "value")["recommended"]]
        assert sorted(urgency) == sorted(value)
        assert urgency != value

    def test_item_that_does_not_fit_is_skipped_not_split(self, client):
        """Test that quantities stay fixed: an unaffordable item is skipped whole."""
        data = recommendations(client, 3000)
        for item in data["recommended"]:
            assert item["quantity_on_order"] == 0
        skipped_costs = [item["total_cost"] for item in data["skipped"]]
        assert all(cost > 0 for cost in skipped_costs)
        # Everything skipped either did not fit when considered or came after the budget ran low
        assert data["total_cost"] <= 3000

    def test_invalid_strategy_rejected(self, client):
        """Test that an unknown strategy returns a validation error."""
        response = client.get("/api/restocking/recommendations?budget=100&strategy=cheapest")
        assert response.status_code == 422

    def test_negative_budget_rejected(self, client):
        """Test that a negative budget returns a validation error."""
        response = client.get("/api/restocking/recommendations?budget=-5")
        assert response.status_code == 422


class TestRestockOrders:
    """Test suite for POST and GET /api/restocking/orders."""

    def first_item(self, client):
        """Helper: a recommended item to order against."""
        return recommendations(client, max_budget(client) + 1)["recommended"][0]

    def test_create_order(self, client):
        """Test placing a valid order."""
        item = self.first_item(client)
        response = client.post(
            "/api/restocking/orders",
            json={"items": [{"sku": item["sku"], "quantity": item["shortfall"]}]},
        )
        assert response.status_code == 201

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        assert len(order["items"]) == 1
        assert abs(order["total_cost"] - item["total_cost"]) < 0.01

    def test_lead_time_and_expected_delivery(self, client):
        """Test that lead time is the slowest item's and drives the delivery date."""
        items = recommendations(client, max_budget(client) + 1)["recommended"]
        lines = [{"sku": i["sku"], "quantity": i["shortfall"]} for i in items]
        order = client.post("/api/restocking/orders", json={"items": lines}).json()

        assert order["lead_time_days"] == max(i["lead_time_days"] for i in items)
        expected = date.today() + timedelta(days=order["lead_time_days"])
        assert order["expected_delivery"] == expected.isoformat()

    def test_pricing_is_computed_server_side(self, client):
        """Test that client-supplied prices are ignored."""
        item = self.first_item(client)
        response = client.post(
            "/api/restocking/orders",
            json={"items": [{"sku": item["sku"], "quantity": 1, "unit_cost": 0.01, "total_cost": 0.01}]},
        )
        assert response.status_code == 201
        assert abs(response.json()["total_cost"] - item["unit_cost"]) < 0.01

    def test_empty_order_rejected(self, client):
        """Test that an order with no items is rejected."""
        response = client.post("/api/restocking/orders", json={"items": []})
        assert response.status_code == 400
        assert "at least one" in response.json()["detail"].lower()

    def test_unknown_sku_rejected(self, client):
        """Test that an unknown SKU is rejected."""
        response = client.post("/api/restocking/orders", json={"items": [{"sku": "NOPE-000", "quantity": 1}]})
        assert response.status_code == 400
        assert "does not need restocking" in response.json()["detail"]

    def test_sku_without_shortfall_rejected(self, client):
        """Test that a SKU with enough stock cannot be ordered."""
        response = client.post("/api/restocking/orders", json={"items": [{"sku": "MTR-304", "quantity": 1}]})
        assert response.status_code == 400

    def test_quantity_over_shortfall_rejected(self, client):
        """Test that ordering more than the shortfall is rejected."""
        item = self.first_item(client)
        response = client.post(
            "/api/restocking/orders",
            json={"items": [{"sku": item["sku"], "quantity": item["shortfall"] + 1}]},
        )
        assert response.status_code == 400
        assert "exceeds shortfall" in response.json()["detail"]

    def test_duplicate_sku_lines_rejected(self, client):
        """Test that splitting one SKU across lines cannot bypass the shortfall check."""
        item = self.first_item(client)
        lines = [{"sku": item["sku"], "quantity": item["shortfall"]}] * 2
        response = client.post("/api/restocking/orders", json={"items": lines})
        assert response.status_code == 400

    def test_non_positive_quantity_rejected(self, client):
        """Test that zero or negative quantities fail validation."""
        item = self.first_item(client)
        for quantity in [0, -3]:
            response = client.post(
                "/api/restocking/orders", json={"items": [{"sku": item["sku"], "quantity": quantity}]}
            )
            assert response.status_code == 422

    def test_ordered_quantity_counts_as_incoming(self, client):
        """Test that a placed order removes the item from recommendations, preventing double-ordering."""
        item = self.first_item(client)
        client.post(
            "/api/restocking/orders",
            json={"items": [{"sku": item["sku"], "quantity": item["shortfall"]}]},
        )
        after = recommendations(client, max_budget(client) + 1)
        assert item["sku"] not in {i["sku"] for i in after["recommended"] + after["skipped"]}

        # A second order for the same SKU has nothing left to cover
        response = client.post(
            "/api/restocking/orders", json={"items": [{"sku": item["sku"], "quantity": 1}]}
        )
        assert response.status_code == 400

    def test_partial_order_leaves_remainder(self, client):
        """Test that a partial order reduces the shortfall and shows quantity on order."""
        item = self.first_item(client)
        client.post("/api/restocking/orders", json={"items": [{"sku": item["sku"], "quantity": 10}]})

        after = recommendations(client, max_budget(client) + 1)
        updated = next(i for i in after["recommended"] + after["skipped"] if i["sku"] == item["sku"])
        assert updated["quantity_on_order"] == 10
        assert updated["shortfall"] == item["shortfall"] - 10

    def test_list_orders_newest_first(self, client):
        """Test that submitted orders are listed newest first."""
        items = recommendations(client, max_budget(client) + 1)["recommended"][:2]
        for item in items:
            client.post("/api/restocking/orders", json={"items": [{"sku": item["sku"], "quantity": 1}]})

        response = client.get("/api/restocking/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] > data[1]["id"]
        assert data[0]["items"][0]["sku"] == items[1]["sku"]

    def test_list_orders_empty_by_default(self, client):
        """Test that no orders are listed before any are placed."""
        response = client.get("/api/restocking/orders")
        assert response.status_code == 200
        assert response.json() == []
