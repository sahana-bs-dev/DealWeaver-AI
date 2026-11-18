from core.negotiation_engine import NegotiationEngine

engine = NegotiationEngine(
    listed_price=5000,
    buyer_budget=4000,
    seller_minimum=3500,
    opening_offer=3000,
    max_rounds=5
)

print("Starting negotiation...")

result = engine.start()
print("Starting result:", result)

for round_number in range(5):
    if engine.status != "active":
        break

    result = engine.next_round()
    print(f"Round {round_number + 1}:", result)

print("Final status:", engine.status)
print("Negotiation history:", engine.history)