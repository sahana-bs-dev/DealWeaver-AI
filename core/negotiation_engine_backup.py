from agents.buyer_agent import BuyerAgent
from agents.seller_agent import SellerAgent


class NegotiationEngine:

    def __init__(
        self,
        listed_price,
        buyer_budget,
        seller_minimum,
        opening_offer,
        max_rounds=5
    ):
        if buyer_budget < seller_minimum:
            raise ValueError("No feasible price overlap exists.")

        self.buyer = BuyerAgent(
            max_budget=buyer_budget,
            opening_offer=opening_offer,
            max_rounds=max_rounds
        )

        self.seller = SellerAgent(
            listed_price=listed_price,
            min_price=seller_minimum,
            max_rounds=max_rounds
        )

        self.history = []
        self.status = "active"

    def _update_status(self, result):
        if result["action"] == "accept":
            self.status = "accepted"
        elif result["action"] == "no_deal":
            self.status = "no_deal"

    def start(self):
        seller_result = self.seller.make_opening_offer()
        buyer_result = self.buyer.make_opening_offer()

        self.history.append({
            "speaker": "Seller",
            "decision": seller_result
        })

        self.history.append({
            "speaker": "Buyer",
            "decision": buyer_result
        })

        # Seller evaluates the buyer's opening offer.
        result = self.seller.receive_offer(buyer_result["price"])

        self.history.append({
            "speaker": "Seller",
            "decision": result
        })

        self._update_status(result)

        return result

    def next_round(self):
        if self.status != "active":
            return {
                "action": "no_deal",
                "price": None,
                "reason": "Negotiation has ended.",
                "round": None
            }

        buyer_result = self.buyer.receive_offer(
            self.seller.current_offer
        )

        self.history.append({
            "speaker": "Buyer",
            "decision": buyer_result
        })

        self._update_status(buyer_result)

        if self.status != "active":
            return buyer_result

        # Seller responds to the buyer's counteroffer.
        # If the buyer rejects, seller reconsiders the
        # buyer's most recent offer and reduces the price.
        seller_offer = (
            buyer_result["price"]
            if buyer_result["action"] == "counter"
            else self.buyer.current_offer
        )

        seller_result = self.seller.receive_offer(seller_offer)

        self.history.append({
            "speaker": "Seller",
            "decision": seller_result
        })

        self._update_status(seller_result)

        return seller_result