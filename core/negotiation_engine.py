from agents.buyer_agent import BuyerAgent
from agents.seller_agent import SellerAgent

from core.shared_storage import (
    get_negotiation,
    save_offer,
    get_offer_history,
    update_negotiation_status
)


class NegotiationEngine:

    def __init__(self, negotiation_id):

        data = get_negotiation(negotiation_id)

        if not data:
            raise ValueError("Negotiation not found.")

        if data["listed_price"] is None or data["seller_minimum"] is None:
            raise ValueError("Seller details are incomplete.")

        if data["buyer_budget"] < data["seller_minimum"]:
            raise ValueError("No feasible price overlap exists.")

        self.negotiation_id = negotiation_id

        self.buyer = BuyerAgent(
            max_budget=data["buyer_budget"],
            opening_offer=data["opening_offer"]
        )

        self.seller = SellerAgent(
            listed_price=data["listed_price"],
            min_price=data["seller_minimum"]
        )

        self.buyer_budget = data["buyer_budget"]
        self.seller_minimum = data["seller_minimum"]
        self.listed_price = data["listed_price"]

        self.history = get_offer_history(negotiation_id)
        self.status = data["status"]

        self.current_offer = None
        self.current_speaker = "Buyer"

        if self.history:

            last = self.history[-1]

            if last["speaker"] == "Buyer":
                self.current_speaker = "Seller"
            else:
                self.current_speaker = "Buyer"

            # Restore agent state after Streamlit reruns
            self.buyer.started = True
            self.seller.started = True

            self.buyer.current_round = sum(
                1 for item in self.history
                if item["speaker"] == "Buyer"
            )

            self.seller.current_round = sum(
                1 for item in self.history
                if item["speaker"] == "Seller"
            )

            # Restore the latest valid offer
            priced_history = [
                item for item in self.history
                if item["price"] is not None
            ]

            if priced_history:
                self.current_offer = float(
                    priced_history[-1]["price"]
                )

            buyer_offers = [
                item["price"]
                for item in self.history
                if item["speaker"] == "Buyer"
                and item["price"] is not None
            ]

            seller_offers = [
                item["price"]
                for item in self.history
                if item["speaker"] == "Seller"
                and item["price"] is not None
            ]

            if buyer_offers:
                self.buyer.current_offer = float(
                    buyer_offers[-1]
                )

            if seller_offers:
                self.seller.current_offer = float(
                    seller_offers[-1]
                )

    def _record(self, speaker, action, price, reason):

        history = self.get_history()
        round_number = len(history) // 2 + 1

        save_offer(
            self.negotiation_id,
            speaker,
            action,
            price,
            reason,
            round_number
        )

        self.history = get_offer_history(self.negotiation_id)

        if price is not None:
            self.current_offer = price

        if action == "accept":
            self.status = "accepted"
        elif action == "no_deal":
            self.status = "no_deal"

        update_negotiation_status(
            self.negotiation_id,
            self.status
        )

    def get_history(self):
        return get_offer_history(self.negotiation_id)

    def start(self):

        if self.status != "pending":
            raise RuntimeError("Negotiation cannot be started.")

        if self.history:
            raise RuntimeError("Negotiation has already started.")

        self.status = "active"

        update_negotiation_status(
            self.negotiation_id,
            "active"
        )

        seller_decision = self.seller.make_opening_offer()

        self._record(
            "Seller",
            seller_decision["action"],
            seller_decision["price"],
            seller_decision["reason"]
        )

        buyer_decision = self.buyer.make_opening_offer()

        self._record(
            "Buyer",
            buyer_decision["action"],
            buyer_decision["price"],
            buyer_decision["reason"]
        )

        self.current_speaker = "Seller"

        return {
            "action": "counter",
            "price": self.current_offer,
            "reason": "Opening offer submitted.",
            "round": (len(self.history) + 1) // 2
        }

    def buyer_respond(self, action, price=None):

        if self.status != "active":
            raise RuntimeError("Negotiation is not active.")

        if self.current_speaker != "Buyer":
            raise RuntimeError("It is currently the seller's turn.")

        if action == "withdraw":

            decision = self.buyer.withdraw()

            self._record(
                "Buyer",
                "no_deal",
                None,
                decision["reason"]
            )

        elif action == "reject":

            decision = self.buyer.reject_offer(
                "Buyer rejected the seller's offer."
            )

            if decision["action"] == "reject":
                self._record(
                    "Buyer",
                    "reject",
                    None,
                    decision["reason"]
                )
            elif decision["action"] == "no_deal":
                self._record(
                    "Buyer",
                    "no_deal",
                    None,
                    decision["reason"]
                )

        elif action == "accept":

            if self.current_offer is None:
                raise ValueError("There is no offer to accept.")

            if self.current_offer > self.buyer_budget:
                raise ValueError("Offer exceeds the buyer's budget.")

            decision = self.buyer.receive_offer(self.current_offer)

            if decision["action"] == "accept":
                self._record(
                    "Buyer",
                    "accept",
                    decision["price"],
                    decision["reason"]
                )
            elif decision["action"] == "counter":
                self._record(
                    "Buyer",
                    "counter",
                    decision["price"],
                    decision["reason"]
                )
            elif decision["action"] == "reject":
                self._record(
                    "Buyer",
                    "reject",
                    None,
                    decision["reason"]
                )
            elif decision["action"] == "no_deal":
                self._record(
                    "Buyer",
                    "no_deal",
                    None,
                    decision["reason"]
                )

        elif action == "offer":

            if price is None or price <= 0:
                raise ValueError("Enter a valid offer.")

            if price > self.buyer_budget:
                raise ValueError("Offer cannot exceed buyer's budget.")

            self.buyer.current_offer = float(price)
            self.buyer.current_round += 1

            self._record(
                "Buyer",
                "counter",
                float(price),
                "Buyer submitted a counteroffer."
            )

        else:
            raise ValueError("Invalid buyer action.")

        if self.status == "active":
            self.current_speaker = "Seller"

        return {
            "action": action,
            "price": self.current_offer,
            "reason": "Buyer action recorded.",
            "round": (len(self.history) + 1) // 2
        }

    def seller_respond(self, action, price=None):

        if self.status != "active":
            raise RuntimeError("Negotiation is not active.")

        if self.current_speaker != "Seller":
            raise RuntimeError("It is currently the buyer's turn.")

        if action == "withdraw":

            decision = self.seller.withdraw()

            self._record(
                "Seller",
                "no_deal",
                None,
                decision["reason"]
            )

        elif action == "reject":

            decision = self.seller.reject_offer(
                "Seller rejected the buyer's offer."
            )

            if decision["action"] == "reject":
                self._record(
                    "Seller",
                    "reject",
                    None,
                    decision["reason"]
                )
            elif decision["action"] == "no_deal":
                self._record(
                    "Seller",
                    "no_deal",
                    None,
                    decision["reason"]
                )

        elif action == "accept":

            if self.current_offer is None:
                raise ValueError("There is no offer to accept.")

            if self.current_offer < self.seller_minimum:
                raise ValueError("Cannot accept below seller's minimum.")

            decision = self.seller.receive_offer(self.current_offer)

            if decision["action"] == "accept":
                self._record(
                    "Seller",
                    "accept",
                    decision["price"],
                    decision["reason"]
                )
            elif decision["action"] == "counter":
                self._record(
                    "Seller",
                    "counter",
                    decision["price"],
                    decision["reason"]
                )
            elif decision["action"] == "reject":
                self._record(
                    "Seller",
                    "reject",
                    None,
                    decision["reason"]
                )
            elif decision["action"] == "no_deal":
                self._record(
                    "Seller",
                    "no_deal",
                    None,
                    decision["reason"]
                )

        elif action == "offer":

            if price is None or price <= 0:
                raise ValueError("Enter a valid counteroffer.")

            if price < self.seller_minimum:
                raise ValueError("Counteroffer cannot be below seller's minimum.")

            if price > self.listed_price:
                raise ValueError("Counteroffer cannot exceed listed price.")

            if price > self.buyer_budget:
                raise ValueError("Counteroffer exceeds buyer's budget.")

            self.seller.current_offer = float(price)
            self.seller.current_round += 1

            self._record(
                "Seller",
                "counter",
                float(price),
                "Seller submitted a counteroffer."
            )

        else:
            raise ValueError("Invalid seller action.")

        if self.status == "active":
            self.current_speaker = "Buyer"

        return {
            "action": action,
            "price": self.current_offer,
            "reason": "Seller action recorded.",
            "round": (len(self.history) + 1) // 2
        }