from core.shared_storage import (
    create_database,
    save_negotiation,
    update_seller_details,
    get_negotiation,
    get_offer_history
)

from core.negotiation_engine import NegotiationEngine


def test_negotiation():

    create_database()

    negotiation_id = save_negotiation(
        "Test Laptop",
        4000,
        3000
    )

    update_seller_details(
        negotiation_id,
        5000,
        3500
    )

    engine = NegotiationEngine(negotiation_id)

    engine.start()

    print("\n--- SELLER RESPONSE ---")

    result = engine.seller_respond(
        action="offer",
        price=3800
    )

    print(result)

    print("\n--- BUYER RESPONSE ---")

    engine = NegotiationEngine(negotiation_id)

    result = engine.buyer_respond(
        action="accept"
    )

    print(result)

    print("\n--- FINAL RESULT ---")
    print("Status:", get_negotiation(negotiation_id)["status"])
    print("History:", get_offer_history(negotiation_id))


if __name__ == "__main__":
    test_negotiation()