import random
import pandas as pd
import streamlit as st

from core.negotiation_engine import NegotiationEngine
from core.shared_storage import get_connection,get_negotiation,get_all_negotiations,get_offer_history
from core.shared_storage import (
    create_database,
    save_negotiation,
    get_negotiation,
    get_all_negotiations,
    update_seller_details,
    save_offer,
    get_offer_history,
    update_negotiation_status,
    save_seller_listing,
    get_all_seller_listings,
    validate_gstin,
    compute_gstin_checksum,
    detect_device_and_condition,
    register_user,
    authenticate_user
)


# ============================================================
# HELPER: GENERATE TEST GSTIN & RISK ANALYSIS
# ============================================================

def generate_test_gstin(state_code: str = "29") -> str:
    letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
    digits = "".join(random.choices("0123456789", k=4))
    last_letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    base_14 = f"{state_code}{letters}{digits}{last_letter}1Z"
    return base_14 + compute_gstin_checksum(base_14)


def analyze_seller_product_risk(item: dict) -> dict:
    """Evaluates GSTIN checksum, second-hand/reused detection, specs, and pricing."""
    risk_score = 0
    flags = []

    gstin = (item.get("seller_gstin") or "").strip().upper()
    gst_ok, gst_msg = validate_gstin(gstin)
    if not gst_ok:
        risk_score += 30
        flags.append(f"Unverified Seller GSTIN: {gst_msg}")

    specs = (item.get("product_specs") or "").strip()
    if len(specs) < 20:
        risk_score += 20
        flags.append("Incomplete product specifications / warranty details (< 20 chars).")

    # Second-hand / reused electronics detection
    declared_cond = item.get("declared_condition") or "Brand New"
    detection = detect_device_and_condition(item.get("product", ""), specs, declared_cond)

    if detection["condition_mismatch"]:
        risk_score += 40
        flags.append(
            f"Condition Mismatch Alert: Seller selected 'Brand New', but description contains "
            f"reused/second-hand indicators ({', '.join(detection['matched_terms'])})."
        )
    elif detection["is_reused"]:
        risk_score += 20
        terms_note = f" ({', '.join(detection['matched_terms'])})" if detection["matched_terms"] else ""
        flags.append(f"Second-Hand / Reused Device Detected{terms_note} — inspect battery health & warranty.")

    listed_price = item.get("listed_price") or item.get("listed_unit_price") or 0
    buyer_budget = item.get("buyer_budget") or 0
    if buyer_budget > 0 and listed_price > 0 and listed_price < (0.5 * buyer_budget):
        risk_score += 25
        flags.append("Price is >50% below budget — verify device authenticity.")

    if risk_score < 30:
        level, icon = "LOW RISK", "🟢"
    elif risk_score < 60:
        level, icon = "MEDIUM RISK", "🟡"
    else:
        level, icon = "HIGH RISK", "🔴"

    return {
        "score": min(risk_score, 100),
        "level": level,
        "icon": icon,
        "flags": flags,
        "gst_ok": gst_ok,
        "detection": detection,
    }


def render_risk_panel(item: dict):
    risk = analyze_seller_product_risk(item)
    st.subheader(f"{risk['icon']} Trust & Risk Analysis: {risk['level']} ({risk['score']}/100)")
    st.progress(risk["score"] / 100.0)
    st.write(f"**Device Condition Status:** {risk['detection']['condition_status']}")
    if risk["gst_ok"]:
        st.write(f"**Seller GSTIN:** `{item.get('seller_gstin')}` ✅ (Checksum Verified)")

    if risk["flags"]:
        for flag in risk["flags"]:
            st.warning(f"⚠️ {flag}")
    else:
        st.success("✅ Verified GSTIN checksum, Brand New device confirmed, and complete specs.")


# ============================================================
# PAGE CONFIGURATION & SESSION INITIALIZATION
# ============================================================

st.set_page_config(
    page_title="DEALWEAVER AI",
    page_icon="🤝",
    layout="wide"
)

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = "Login"

if "active_negotiation_id" not in st.session_state:
    shared_id = st.query_params.get("neg_id")
    st.session_state.active_negotiation_id = shared_id if shared_id else None

create_database()

st.title("🤝 DEALWEAVER AI")
st.subheader("Smart Buyer-Seller Negotiation Portal")
st.markdown("---")


# ============================================================
# LOGIN AND REGISTRATION (AUTO-NAVIGATE & CLEAR CREDENTIALS)
# ============================================================

if st.session_state.auth_user is None:

    st.markdown("## Welcome to DEALWEAVER AI")
    st.write("Login to your account or create a new account.")

    col_login, col_reg, _ = st.columns([1, 1, 3])
    with col_login:
        if st.button(
            "🔐 Login",
            type="primary" if st.session_state.auth_mode == "Login" else "secondary",
            use_container_width=True
        ):
            st.session_state.auth_mode = "Login"
            st.rerun()

    with col_reg:
        if st.button(
            "✨ Create Account",
            type="primary" if st.session_state.auth_mode == "Register" else "secondary",
            use_container_width=True
        ):
            st.session_state.auth_mode = "Register"
            st.rerun()

    st.markdown("---")

    if st.session_state.auth_mode == "Login":
        if st.session_state.pop("account_created_flag", False):
            st.success("✅ Account created! Please log in with your credentials.")

        st.subheader("Welcome Back!")
        with st.form("login_form", clear_on_submit=True):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", use_container_width=True):
                user = authenticate_user(username, password)
                if user:
                    st.session_state.auth_user = user
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    else:
        st.subheader("Create Your Account")
        with st.form("register_form", clear_on_submit=True):
            new_username = st.text_input("Choose Username")
            new_password = st.text_input("Create Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            account_role = st.selectbox("Register As", ["Buyer", "Seller"])

            if st.form_submit_button("Create Account", use_container_width=True):
                if new_password != confirm_password:
                    st.error("Passwords do not match.")
                else:
                    success, message = register_user(new_username, new_password, account_role)
                    if success:
                        st.session_state.auth_mode = "Login"
                        st.session_state.account_created_flag = True
                        st.rerun()
                    else:
                        st.error(message)

    st.stop()


# ============================================================
# AUTHENTICATED USER DASHBOARD & SIDEBAR
# ============================================================

logged_in_user = st.session_state.auth_user
user_role = logged_in_user["role"]

st.sidebar.title("🤝 DEALWEAVER AI")
st.sidebar.success(f"Logged in as: {logged_in_user['username']}")
st.sidebar.write(f"Account Type: {user_role}")
st.sidebar.markdown("---")

if user_role == "Buyer":
    st.sidebar.title("🛍️ Buyer Dashboard")
    pages = [
        "Electronics Marketplace",
        "Negotiation Setup",
        "Live Negotiation",
        "Product History",
        "AI Analysis",
        "Gen AI Suggestions",
        "Final Deal Report"
    ]
else:
    st.sidebar.title("🏪 Seller Dashboard")
    pages = [
        "Electronics Marketplace",
        "Seller Setup",
        "Live Negotiation",
        "Product History",
        "AI Analysis",
        "Gen AI Suggestions",
        "Final Deal Report"
    ]

page = st.sidebar.radio("Select a page", pages)

st.sidebar.markdown("---")
if st.sidebar.button("Logout", use_container_width=True):
    st.session_state.auth_user = None
    st.session_state.active_negotiation_id = None
    st.session_state.auth_mode = "Login"
    st.rerun()


# ============================================================
# NEW PAGE: ELECTRONIC DEVICES FOR SALE DASHBOARD
# ============================================================

if page == "Electronics Marketplace":

    st.header("💻 Electronic Devices Available for Sale")
    st.write("Live dashboard of all electronic devices listed by Sellers, including automated **Second-Hand / Reused Detection** and **GSTIN Trust Status**.")

    listings = get_all_seller_listings()
    electronic_listings = [
        item for item in listings
        if item.get("category") == "Electronics"
        or detect_device_and_condition(item["product"], item["product_specs"])["is_electronic"]
    ]

    if not electronic_listings:
        st.info("No electronic devices are currently listed for sale. Sellers can list devices under **Seller Setup**.")
    else:
        # Summary KPI Metrics
        total_models = len(electronic_listings)
        total_units = sum(int(i["available_qty"]) for i in electronic_listings)
        new_count = sum(1 for i in electronic_listings if not i.get("is_reused"))
        used_count = sum(1 for i in electronic_listings if i.get("is_reused"))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Electronic Listings", total_models)
        m2.metric("Total Units in Stock", total_units)
        m3.metric("🆕 Brand New Devices", new_count)
        m4.metric("♻️ Second-Hand / Reused", used_count)

        st.markdown("---")

        # Condition Filter
        condition_filter = st.radio(
            "Filter Devices by Condition",
            ["All Electronics", "Brand New Only", "Second-Hand / Reused Only"],
            horizontal=True
        )

        filtered_items = []
        for item in electronic_listings:
            if condition_filter == "Brand New Only" and item.get("is_reused"):
                continue
            if condition_filter == "Second-Hand / Reused Only" and not item.get("is_reused"):
                continue
            filtered_items.append(item)

        # Structured Dashboard Table
        table_rows = []
        for item in filtered_items:
            risk = analyze_seller_product_risk(item)
            cond_badge = (
                "⚠️ Mismatch (Reused Detected)" if item.get("condition_mismatch")
                else ("♻️ Second-Hand / Reused" if item.get("is_reused") else "🆕 Brand New")
            )
            table_rows.append({
                "Listing ID": item["listing_id"],
                "Electronic Device": item["product"],
                "Detected Condition": cond_badge,
                "Seller": item["seller_username"],
                "GSTIN Status": "✅ Verified" if item.get("seller_verified") else "❌ Unverified",
                "Stock (Units)": item["available_qty"],
                "Price / Unit (₹)": f"₹{item['listed_unit_price']:,.2f}",
                "Trust & Risk": f"{risk['icon']} {risk['level']} ({risk['score']}/100)",
            })

        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

        # Detailed Device Cards
        st.subheader("🔍 Detailed Device Inspection")
        for item in filtered_items:
            with st.expander(
                f"{item['product']} — ₹{item['listed_unit_price']:,.2f}/unit "
                f"({item['available_qty']} in stock) | Seller: {item['seller_username']}"
            ):
                c1, c2 = st.columns([1.3, 1])
                with c1:
                    st.write(f"**Listing ID:** `{item['listing_id']}`")
                    st.write(f"**Declared Condition:** {item.get('declared_condition', 'Brand New')}")
                    if item.get("detected_keywords"):
                        st.warning(f"🔍 **Second-Hand Keywords Detected in Specs:** `{item['detected_keywords']}`")
                    st.write(f"**Specifications & Warranty:** {item['product_specs']}")
                with c2:
                    render_risk_panel(item)


# ============================================================
# PAGE 1A: BUYER NEGOTIATION SETUP
# ============================================================

elif page == "Negotiation Setup":

    st.header("⚙️ Buyer Negotiation Setup")

    # --- BUYER'S PAST & ACTIVE NEGOTIATIONS SECTION (Resume any old or yesterday's request) ---
    st.subheader("📜 Your Past & Active Negotiation Requests")
    st.caption("Access all your previous or yesterday's negotiation rooms to continue chatting or complete orders.")

    all_negs = get_all_negotiations()
    logged_in_buyer = logged_in_user.get("username")
    buyer_history = [
        n for n in all_negs 
        if n.get("buyer_username") == logged_in_buyer
    ]

    if buyer_history:
        for n in buyer_history:
            col_h1, col_h2 = st.columns([4, 1])
            with col_h1:
                status_label = n.get("status", "pending").upper()
                badge = "✅ Completed" if status_label == "COMPLETED" else f"⏳ {status_label}"
                
                st.write(
                    f"• **ID: `{n['id']}`** [{badge}] — Product: **{n['product']}** | "
                    f"Qty: **{n.get('quantity', 1)}** | Opening Offer: ₹{n['opening_offer']:,.2f} | "
                    f"Created: {n.get('created_at', 'N/A')}"
                )
            with col_h2:
                if st.button("Resume Room", key=f"resume_neg_{n['id']}"):
                    st.session_state.active_negotiation_id = n['id']
                    st.query_params["neg_id"] = n['id']
                    st.rerun()
    else:
        st.info("You haven't initiated any negotiation requests yet.")

    st.markdown("---")
    st.subheader("📦 Select From Seller's Published Products")
    listings = get_all_seller_listings()

    if listings:
        listing_options = {
            f"{item['product']} — Seller: {item['seller_username']} | "
            f"{'♻️ Used/Reused' if item.get('is_reused') else '🆕 New'} | "
            f"₹{item['listed_unit_price']:,.2f}/unit | Stock: {item['available_qty']} ({item['listing_id']})": item
            for item in listings
        }

        selected_label = st.selectbox("Choose Seller Product Listing", options=list(listing_options.keys()))
        selected_listing = listing_options[selected_label]

        col_prod, col_trust = st.columns([1.2, 1])
        with col_prod:
            st.info(
                f"**Product:** {selected_listing['product']}\n\n"
                f"**Seller:** {selected_listing['seller_username']}\n\n"
                f"**Available Stock:** {selected_listing['available_qty']} units\n\n"
                f"**Seller Listed Price:** ₹{selected_listing['listed_unit_price']:,.2f} / unit\n\n"
                f"**Specifications & Condition:** {selected_listing['product_specs']}"
            )
        with col_trust:
            render_risk_panel(selected_listing)

        st.markdown("---")
        st.subheader("🛒 Set Purchase Quantity & Offer")

        with st.form("catalog_negotiation_form"):
            buy_qty = st.number_input(
                "How Many Products Do You Want to Buy? (Quantity)",
                min_value=1,
                max_value=int(selected_listing["available_qty"]),
                value=1,
                step=1
            )

            unit_budget = st.number_input(
                "Your Maximum Budget Per Unit (₹)",
                min_value=1.0,
                value=float(selected_listing["listed_unit_price"])
            )

            unit_opening_offer = st.number_input(
                "Your Opening Offer Per Unit (₹)",
                min_value=1.0,
                value=round(float(selected_listing["listed_unit_price"]) * 0.85, 2)
            )

            total_budget = unit_budget * buy_qty
            total_opening = unit_opening_offer * buy_qty
            total_listed = float(selected_listing["listed_unit_price"]) * buy_qty

            st.caption(
                f"**Order Totals for {buy_qty} unit(s):** "
                f"Seller Listed Total: ₹{total_listed:,.2f} | "
                f"Your Max Budget: ₹{total_budget:,.2f} | "
                f"Your Opening Offer: ₹{total_opening:,.2f}"
            )

            if st.form_submit_button("Create Negotiation Room"):
                if unit_opening_offer > unit_budget:
                    st.error("Opening offer cannot exceed your budget.")
                else:
                    neg_id = save_negotiation(
                        product=selected_listing["product"],
                        buyer_budget=total_budget,
                        opening_offer=total_opening,
                        quantity=buy_qty,
                        buyer_username=logged_in_user["username"],
                        listing_id=selected_listing["listing_id"],
                        seller_username=selected_listing["seller_username"],
                        seller_gstin=selected_listing.get("seller_gstin", ""),
                        product_specs=selected_listing["product_specs"],
                        declared_condition=selected_listing.get("declared_condition", "Brand New"),
                        is_reused=bool(selected_listing.get("is_reused")),
                        condition_mismatch=bool(selected_listing.get("condition_mismatch")),
                        seller_verified=bool(selected_listing.get("seller_verified"))
                    )
                    st.session_state.active_negotiation_id = neg_id
                    st.query_params["neg_id"] = neg_id

                    st.success(f"Negotiation Created! ID: **{neg_id}**")
                    st.write(f"Negotiation ID: `{neg_id}` | Direct Link: `?neg_id={neg_id}`")

    else:
        st.warning("No Seller listings found.")


# ============================================================
# PAGE 1B: SELLER SETUP PAGE
# ============================================================

elif page == "Seller Setup":

    st.header("🏪 Seller Dashboard - Product Catalog & Negotiation Setup")

    if "demo_gstin" not in st.session_state:
        st.session_state.demo_gstin = "29ABCDE1234F1Z5"

    tab_catalog, tab_join = st.tabs([
        "1️⃣ Publish Electronic / Product Listing",
        "2️⃣ Respond to Buyer Negotiation ID"
    ])

    with tab_catalog:
        st.subheader("List Product for Sale")
        with st.form("seller_publish_form", clear_on_submit=True):
            sel_category = st.selectbox("Category", ["Electronics", "General / Other"])
            sel_product = st.text_input("Product Name")
            sel_declared_cond = st.selectbox("Declared Device Condition", ["Brand New", "Second-Hand / Used", "Refurbished", "Open Box"])
            sel_specs = st.text_area("Product Specs, Warranty & Proof of Authenticity")
            sel_qty = st.number_input("Available Quantity in Stock", min_value=1, value=5, step=1)
            sel_unit_price = st.number_input("Listed Price Per Unit (₹)", min_value=1.0, value=25000.0)
            sel_gstin = st.text_input("Seller 15-Character GSTIN", value=st.session_state.demo_gstin)

            if st.form_submit_button("Publish Product"):
                if not sel_product.strip():
                    st.error("Please enter a product name.")
                else:
                    gst_ok, gst_msg = validate_gstin(sel_gstin)
                    if not gst_ok:
                        st.error(f"GSTIN Validation Failed: {gst_msg}")
                    else:
                        lst_id, _, detection = save_seller_listing(
                            seller_username=logged_in_user["username"],
                            product=sel_product,
                            product_specs=sel_specs,
                            available_qty=sel_qty,
                            listed_unit_price=sel_unit_price,
                            seller_gstin=sel_gstin,
                            declared_condition=sel_declared_cond,
                            category=sel_category
                        )
                        st.success(f"Product published! Listing ID: **{lst_id}**")

    with tab_join:
        st.subheader("Active Buyer Requests")

        all_negs = get_all_negotiations()
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        pending_negs = [
            n for n in all_negs 
            if n.get("created_at", "").startswith(today_str) or n.get("status", "pending") == "pending"
        ]
        
        if pending_negs:
            st.caption("Active & Today's Buyer Requests:")
            for n in pending_negs:
                col_r1, col_r2 = st.columns([4, 1])
                with col_r1:
                    status_badge = "✅ Completed" if n.get("status") == "completed" else "⏳ Pending"
                    st.write(
                        f"• **{n['id']}** [{status_badge}] — Product: **{n['product']}** | "
                        f"Qty: **{n['quantity']}** | Buyer: `{n['buyer_username'] or 'Buyer'}` | "
                        f"Offer: ₹{n['opening_offer']:,.2f}"
                    )
                with col_r2:
                    if n.get("status") != "completed":
                        if st.button("Load", key=f"quick_load_{n['id']}"):
                            st.session_state.active_negotiation_id = n['id']
                            st.query_params["neg_id"] = n['id']
                            st.session_state.seller_request_loaded = True
                            
                            if n.get("listing_id"):
                                from core.shared_storage import get_seller_listing
                                listing = get_seller_listing(n["listing_id"])
                                if listing:
                                    st.session_state.prefill_listed_price = listing["listed_unit_price"] * n["quantity"]
                                    st.session_state.prefill_specs = listing["product_specs"]
                                    st.session_state.prefill_cond = listing.get("declared_condition", "Brand New")
                                    st.session_state.prefill_gstin = listing.get("seller_gstin", "")
                            st.rerun()

        st.markdown("---")
        default_neg = st.query_params.get("neg_id", st.session_state.active_negotiation_id or "")
        negotiation_id = st.text_input("Or enter Negotiation ID manually:", value=str(default_neg)).strip().upper()

        if st.button("Load Buyer Request"):
            data = get_negotiation(negotiation_id)
            if data:
                st.session_state.active_negotiation_id = negotiation_id
                st.query_params["neg_id"] = negotiation_id
                st.session_state.seller_request_loaded = True

        if st.session_state.get("seller_request_loaded", False) and st.session_state.active_negotiation_id:
            data = get_negotiation(st.session_state.active_negotiation_id)
            if data:
                st.success(f"Loaded Negotiation **{data['id']}**")
                qty = data.get("quantity") or 1
                
                default_listed = st.session_state.pop("prefill_listed_price", float(data["buyer_budget"]))
                default_specs = st.session_state.pop("prefill_specs", data.get("product_specs") or "")
                default_cond = st.session_state.pop("prefill_cond", "Brand New")
                default_gstin = st.session_state.pop("prefill_gstin", data.get("seller_gstin") or st.session_state.demo_gstin)

                listed_price = st.number_input(f"Total Listed Price for {qty} unit(s) (₹)", min_value=1.0, value=float(default_listed))
                seller_minimum = st.number_input(f"Total Minimum Acceptable Price (₹)", min_value=1.0, value=round(float(default_listed) * 0.85, 2))
                declared_cond = st.selectbox("Device Condition", ["Brand New", "Second-Hand / Used", "Refurbished", "Open Box"])
                product_specs = st.text_area("Product Specs", value=default_specs)
                seller_gstin = st.text_input("Seller GSTIN", value=default_gstin)

                if st.button("Save & Open Live Negotiation Room"):
                    from core.shared_storage import update_seller_details
                    update_seller_details(
                        negotiation_id=data["id"],
                        listed_price=listed_price,
                        seller_minimum=seller_minimum,
                        seller_gstin=seller_gstin,
                        declared_condition=declared_cond,
                        product_specs=product_specs
                    )
                    st.success("Terms saved! Switch to **Live Negotiation** on the sidebar.")


# ============================================================
# PAGE 2: LIVE NEGOTIATION
# ============================================================

elif page == "Live Negotiation":

    st.header("🤝 Live Negotiation")

    active_id = st.session_state.get("active_negotiation_id")

    if not active_id:
        st.warning("Please enter or select the Negotiation ID.")
        entered_id = st.text_input("Negotiation ID", value=str(st.query_params.get("neg_id", ""))).strip().upper()

        if st.button("Load Negotiation"):
            data = get_negotiation(entered_id)
            if data:
                st.session_state.active_negotiation_id = entered_id
                st.query_params["neg_id"] = entered_id
                st.rerun()
            else:
                st.error("Negotiation ID not found.")

    else:
        @st.fragment(run_every="2s")
        def auto_refresh_negotiation_room(neg_id: str):
            data = get_negotiation(neg_id)

            if not data:
                st.error("Negotiation not found.")
                return

            if data["listed_price"] is None or data["seller_minimum"] is None:
                st.info(f"🔗 **Negotiation ID:** `{neg_id}`")
                st.warning("Waiting for the seller to submit their selling details...")
                return

            st.info(f"🔗 **Negotiation ID:** `{neg_id}`")

            col_details, col_risk = st.columns([1.2, 1])
            with col_details:
                qty = data.get("quantity") or 1
                st.subheader(f"Product: {data['product']} (Qty: {qty})")
                st.write(f"**Buyer Budget:** ₹{data['buyer_budget']:,.2f}")
                st.write(f"**Seller Listed Price:** ₹{data['listed_price']:,.2f}")
                if user_role == "Seller":
                    st.write(f"**Seller Minimum:** ₹{data['seller_minimum']:,.2f}")

            with col_risk:
                render_risk_panel(data)

            engine = NegotiationEngine(neg_id)
            st.markdown("---")
            st.subheader("Negotiation History")
            history = get_offer_history(neg_id)

            if history:
                for item in history:
                    price_text = f"₹{item['price']:,.2f}" if item["price"] is not None else "No price"
                    st.write(f"**{item['speaker']}** — {item['action']} — {price_text}")
                    if item["reason"]:
                        st.caption(item["reason"])
            else:
                st.info("Negotiation has not started yet.")

            st.markdown("---")

            if engine.status == "pending":
                if st.button("Start Negotiation"):
                    engine.start()
                    st.rerun()

            elif engine.status in ["accepted", "no_deal"]:
                if engine.status == "accepted":
                    if data.get("status") != "completed":
                        conn = get_connection()
                        conn.execute("UPDATE negotiations SET status = 'completed' WHERE id = ?", (neg_id,))
                        conn.commit()
                        conn.close()
                    st.success("Negotiation completed successfully!")
                else:
                    st.warning("Negotiation ended without a deal.")

            else:
                st.info(f"Current turn: **{engine.current_speaker}**")

                if user_role == engine.current_speaker:
                    st.subheader(f"{user_role} Action")

                    col_act1, col_act2, col_act3 = st.columns(3)
                    
                    with col_act1:
                        if st.button("✅ Accept Offer", type="primary", key=f"{user_role}_accept_btn"):
                            try:
                                # Force direct database completion and log the acceptance
                                conn = get_connection()
                                conn.execute("UPDATE negotiations SET status = 'completed' WHERE id = ?", (neg_id,))
                                conn.commit()
                                conn.close()
                                
                                # Log acceptance to offer history
                                from core.shared_storage import log_offer_history
                                log_offer_history(neg_id, speaker=user_role, action="accept", price=None, reason="Deal accepted by user.")
                            except Exception as e:
                                st.error(f"Error accepting deal: {e}")
                            st.rerun()

                    with col_act2:
                        if st.button("❌ Reject", key=f"{user_role}_reject_btn"):
                            try:
                                if user_role == "Buyer":
                                    engine.buyer_respond("reject")
                                else:
                                    engine.seller_respond("reject")
                            except Exception:
                                conn = get_connection()
                                conn.execute("UPDATE negotiations SET status = 'no_deal' WHERE id = ?", (neg_id,))
                                conn.commit()
                                conn.close()
                            st.rerun()

                    with col_act3:
                        if st.button("🚫 Withdraw", key=f"{user_role}_withdraw_btn"):
                            try:
                                if user_role == "Buyer":
                                    engine.buyer_respond("withdraw")
                                else:
                                    engine.seller_respond("withdraw")
                            except Exception:
                                conn = get_connection()
                                conn.execute("UPDATE negotiations SET status = 'no_deal' WHERE id = ?", (neg_id,))
                                conn.commit()
                                conn.close()
                            st.rerun()

                    st.markdown("---")
                    counter_price = st.number_input("Enter counteroffer amount (₹)", min_value=1.0, step=100.0, key=f"{user_role}_counter_price_input")

                    if st.button("Submit Counteroffer", key=f"{user_role}_submit_counter"):
                        if user_role == "Buyer":
                            engine.buyer_respond("offer", counter_price)
                        else:
                            engine.seller_respond("offer", counter_price)
                        st.rerun()

            # --- POST-COMPLETION PAYMENT & FULFILLMENT WORKFLOW ---
            if data.get("status") == "completed":
                st.markdown("---")
                st.success("🎉 Deal Successfully Completed! Proceed with payment and fulfillment below.")
                
                current_payment_status = data.get("payment_status", "Pending")

                # 1. PAYMENT SECTION (Buyer)
                if user_role == "Buyer":
                    st.subheader("💳 Secure Payment & Checkout")
                    if current_payment_status != "Paid":
                        final_price = data.get("opening_offer", 0)
                        if history:
                            for h in reversed(history):
                                if h["price"] is not None:
                                    final_price = h["price"]
                                    break
                        st.info(f"Final Agreed Price to Pay: **₹{final_price:,.2f}**")
                        
                        pay_method = st.selectbox("Select Payment Method", ["UPI / QR", "Credit/Debit Card", "Net Banking", "Escrow Wallet"])
                        if pay_method == "UPI / QR":
                            st.info("📱 Scan QR Code or enter UPI ID (mock@upi) to complete payment.")

                        if st.button("Pay Securely Now", key="buyer_pay_btn"):
                            conn = get_connection()
                            conn.execute("UPDATE negotiations SET payment_status = 'Paid' WHERE id = ?", (neg_id,))
                            conn.commit()
                            conn.close()
                            st.success(f"Payment successful via {pay_method}! Funds secured in escrow.")
                            st.rerun()
                    else:
                        st.success("✅ Payment Completed & Secured in Escrow.")

                # 2. BUYER ADDRESS SECTION
                if user_role == "Buyer":
                    if current_payment_status == "Paid":
                        st.subheader("📦 Provide Delivery Address")
                        with st.form("buyer_address_form"):
                            shipping_addr = st.text_area("Enter your complete delivery address / handover instructions:", value=data.get("shipping_address") or "")
                            if st.form_submit_button("Submit Address to Seller"):
                                conn = get_connection()
                                conn.execute("UPDATE negotiations SET shipping_address = ? WHERE id = ?", (shipping_addr, neg_id))
                                conn.commit()
                                conn.close()
                                st.success("Shipping address submitted successfully!")
                                st.rerun()
                    else:
                        st.warning("🔒 Complete payment above to unlock the delivery address form.")

                # 3. SELLER FULFILLMENT SECTION
                elif user_role == "Seller":
                    st.subheader("🚚 Order Fulfillment & Shipping History")
                    if current_payment_status == "Paid":
                        st.success("💰 Payment Verified & Secured in Escrow!")
                        buyer_addr = data.get("shipping_address")
                        
                        if buyer_addr:
                            st.info(f"**Buyer's Delivery Address:**\n{buyer_addr}")
                            with st.form("seller_fulfillment_form"):
                                tracking_info = st.text_input("Enter Courier Tracking Number / Dispatch Details:", value=data.get("tracking_number") or "")
                                if st.form_submit_button("Confirm Dispatch & Complete Order"):
                                    conn = get_connection()
                                    conn.execute("UPDATE negotiations SET tracking_number = ?, fulfillment_status = 'Dispatched' WHERE id = ?", (tracking_info, neg_id))
                                    conn.commit()
                                    conn.close()
                                    st.success("Fulfillment updated! Order marked as Dispatched.")
                                    st.rerun()
                        else:
                            st.warning("⏳ Waiting for the buyer to submit their delivery address.")
                    else:
                        st.warning("⏳ Waiting for the buyer to complete secure payment.")

        auto_refresh_negotiation_room(active_id)
# ============================================================
# PAGE 3: AI ANALYSIS
# ============================================================

elif page == "AI Analysis":

    st.header("🧠 AI Negotiation & Risk Analysis")

    active_id = st.session_state.get("active_negotiation_id")
    if active_id:
        data = get_negotiation(active_id)
        if data and data.get("listed_price") is not None:
            render_risk_panel(data)
            st.markdown("---")

    st.subheader("Message Intent Prediction")
    st.write("Enter a buyer or seller negotiation message.")

    message = st.text_area(
        "Negotiation Message",
        placeholder="Example: I can offer 3500 for this laptop"
    )

    if st.button("Analyze Message"):
        if not message.strip():
            st.warning("Please enter a message first.")
        else:
            try:
                from models.intent_predictor import predict_intent

                with st.spinner("Analyzing message..."):
                    intent, confidence = predict_intent(message)

                st.success("Intent prediction completed!")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Predicted Intent", intent)
                with col2:
                    st.metric("Confidence", f"{confidence}%")

            except Exception as e:
                st.error(f"Prediction error: {e}")


# ============================================================
# PAGE 4: GEN AI SUGGESTIONS
# ============================================================

elif page == "Gen AI Suggestions":

    st.header("✨ Gen AI Negotiation Suggestions")
    st.write("Real-time strategic advice powered by your active negotiation metrics and market gap analysis.")

    active_id = st.session_state.get("active_negotiation_id")

    if not active_id:
        st.warning("Please load or select an active Negotiation ID first (from Live Negotiation or Setup).")
        
        # Quick input to load a negotiation for suggestions
        load_id_input = st.text_input("Enter Negotiation ID for Suggestions (e.g., DW-8F3A9C)").strip().upper()
        if st.button("Load Negotiation for AI Analysis"):
            if get_negotiation(load_id_input):
                st.session_state.active_negotiation_id = load_id_input
                st.rerun()
            else:
                st.error("Negotiation ID not found.")
    else:
        data = get_negotiation(active_id)
        history = get_offer_history(active_id)

        if not data:
            st.error("Active negotiation details could not be loaded.")
        else:
            qty = data.get("quantity") or 1
            product_name = data["product"]
            buyer_budget = data["buyer_budget"]
            listed_price = data["listed_price"]
            seller_min = data["seller_minimum"]

            # Display deal context metrics
            col_c1, col_c2, col_c3 = st.columns(3)
            col_c1.metric("Product & Qty", f"{product_name} ({qty}x)")
            if listed_price:
                col_c2.metric("Seller Listed Total", f"₹{listed_price:,.2f}")
            col_c3.metric("Your Role", user_role)

            st.markdown("---")

            if not listed_price or not seller_min:
                st.info("⏳ Waiting for the seller to submit their selling terms. Once submitted, Gen AI will generate tailored negotiation tactics.")
            else:
                st.subheader(f"🎯 Strategic Recommendations for {user_role}")

                # Calculate smart dynamic price suggestions based on gap
                total_gap = listed_price - data["opening_offer"]
                midpoint = (listed_price + data["opening_offer"]) / 2

                if user_role == "Buyer":
                    suggested_counter = round(midpoint * 0.95, -2)
                    max_stretch = round(buyer_budget * 0.95, -2)

                    st.markdown(f"""
                    * **Recommended Next Counteroffer:** `₹{suggested_counter:,.2f}` (Targeting the mid-market value gap).
                    * **Max Concession Limit:** Try not to exceed `₹{max_stretch:,.2f}` to keep a safe safety margin under your max budget (`₹{buyer_budget:,.2f}`).
                    """)

                    st.markdown("### 💬 Suggested Script / Phrasing")
                    st.info(f'"I am very interested in this {product_name}, but considering market rates and buying {qty} unit(s), would you consider meeting in the middle at **₹{suggested_counter:,.2f}**?"')

                    st.markdown("### 💡 AI Tactics & Framing")
                    st.write("""
                    1. **Anchor on Quantity:** Emphasize that you are purchasing multiple units to justify a volume discount.
                    2. **Highlight Alternatives:** Gently remind the seller if similar electronics are available with verified warranties.
                    """)

                else:  # Seller Role
                    suggested_counter = round(midpoint * 1.05, -2)
                    min_floor = round(seller_min * 1.02, -2)

                    st.markdown(f"""
                    * **Recommended Next Counteroffer:** `₹{suggested_counter:,.2f}` (Defending your product valuation while showing flexibility).
                    * **Absolute Price Floor:** Do not drop below `₹{min_floor:,.2f}` to protect your margins above your minimum acceptable price (`₹{seller_min:,.2f}`).
                    """)

                    st.markdown("### 💬 Suggested Script / Phrasing")
                    st.info(f'"Given the premium condition and specifications of this electronic device, I can offer a special discounted total of **₹{suggested_counter:,.2f}** if we finalize today."')

                    st.markdown("### 💡 AI Tactics & Framing")
                    st.write("""
                    1. **Bundle Value:** Emphasize product specs, testing quality, or verified GSTIN credentials to justify holding your price.
                    2. **Time Scarcity:** Note that other buyers are looking at electronic inventory in high demand.
                    """)

                st.markdown("---")
                st.subheader("📊 Conversation Intent Insights")
                if history:
                    last_action = history[-1]["action"]
                    last_speaker = history[-1]["speaker"]
                    st.write(f"The last move was made by **{last_speaker}** (`{last_action}`).")
                    if last_action == "counter":
                        st.success("💡 **Tip:** The negotiation is progressing through active concessions. Keep your counter-steps proportional.")
                    elif last_action == "reject":
                        st.warning("⚠️ **Tip:** An offer was rejected. Slow down price movement and pivot toward highlighting product value or warranty perks.")
                else:
                    st.write("The negotiation has not exchanged formal counteroffers yet. Use your opening statement to set a strong anchor.")

# ============================================================
# PAGE 5: FINAL DEAL REPORT
# ============================================================

elif page == "Final Deal Report":

    st.header("📊 Final Deal Report")

    active_id = st.session_state.get("active_negotiation_id")

    if not active_id:
        st.warning("Please enter your Negotiation ID.")
        entered_id = st.text_input(
            "Negotiation ID (e.g., DW-8F3A9C)",
            key="report_negotiation_id"
        ).strip().upper()

        if st.button("Load Report"):
            data = get_negotiation(entered_id)
            if data:
                st.session_state.active_negotiation_id = entered_id
                st.rerun()
            else:
                st.error("Negotiation ID not found.")

    else:
        data = get_negotiation(active_id)
        history = get_offer_history(active_id)

        if not data:
            st.error("Negotiation not found.")
        else:
            qty = data.get("quantity") or 1
            st.subheader(f"Product: {data['product']} (Qty: {qty})")
            st.write(f"Negotiation ID: `{active_id}`")
            st.write(f"**Status:** {data['status'].upper()}")

            if data["status"] == "accepted":
                accepted_offer = next(
                    (
                        item
                        for item in reversed(history)
                        if item["action"] == "accept" and item["price"] is not None
                    ),
                    None
                )

                if accepted_offer:
                    final_price = accepted_offer["price"]
                    st.success("🎉 Deal successfully completed!")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Final Agreed Total", f"₹{final_price:,.2f}")
                    with col2:
                        st.metric("Agreed Price / Unit", f"₹{final_price / qty:,.2f}")
                    with col3:
                        savings = data["listed_price"] - final_price
                        st.metric("Buyer Savings", f"₹{savings:,.2f}")

                    st.write("Quantity Purchased:", f"{qty} unit(s)")
                    st.write("Buyer Budget: ₹", f"{data['buyer_budget']:,.2f}")
                    st.write("Seller Minimum: ₹", f"{data['seller_minimum']:,.2f}")
                    st.write(
                        "Buyer Budget Check:",
                        "Passed" if final_price <= data["buyer_budget"] else "Failed"
                    )
                    st.write(
                        "Seller Minimum Check:",
                        "Passed" if final_price >= data["seller_minimum"] else "Failed"
                    )

            elif data["status"] == "no_deal":
                st.warning("No agreement was reached.")
            else:
                st.info("Negotiation is still in progress.")

            st.markdown("---")
            st.subheader("Complete Negotiation History")

            if history:
                for item in history:
                    price_text = f"₹{item['price']:,.2f}" if item["price"] is not None else "No price"
                    st.write(f"**{item['speaker']}** | {item['action']} | {price_text}")
                    if item["reason"]:
                        st.caption(item["reason"])
            else:
                st.info("No negotiation history available yet.")
# ============================================================
# PRODUCT HISTORY VIEWS FOR BUYERS & SELLERS
# ============================================================

def render_product_history_dashboard(username: str, role: str):
    st.subheader(f"📜 Product Negotiation History ({role} View)")
    st.write("Track all active, completed, and closed product negotiations associated with your account.")

    from core.shared_storage import get_product_history_for_user, get_offer_history
    history_records = get_product_history_for_user(username, role)

    if not history_records:
        st.info("No product negotiation history found yet. Start or join a negotiation to see records here.")
        return

    for rec in history_records:
        status_color = "🟢" if rec["status"] == "accepted" else ("🔴" if rec["status"] == "no_deal" else "🟡")
        with st.expander(
            f"{status_color} [{rec['id']}] Product: {rec['product']} | "
            f"Qty: {rec['quantity']} | Status: {rec['status'].upper()} | "
            f"Date: {rec['created_at']}"
        ):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Buyer Budget:** ₹{rec['buyer_budget']:,.2f}")
            
            # Fixed string formatting for listed price
            listed_price_text = f"₹{rec['listed_price']:,.2f}" if rec.get('listed_price') else 'Pending'
            c2.write(f"**Seller Listed Price:** {listed_price_text}")
            c3.write(f"**Total Turns Exchanged:** {rec['total_turns']}")

            if rec.get("product_specs"):
                st.caption(f"**Specifications & Condition:** {rec['product_specs']}")

            # Load message/offer timeline for this specific product room
            timeline = get_offer_history(rec["id"])
            if timeline:
                st.markdown("**Transaction Timeline:**")
                for entry in timeline:
                    p_text = f"₹{entry['price']:,.2f}" if entry['price'] is not None else "-"
                    st.text(f"• [{entry['created_at']}] {entry['speaker']} -> {entry['action'].upper()} ({p_text}) {entry['reason'] or ''}")
            
            if st.button(f"Open Negotiation Room {rec['id']}", key=f"hist_open_{rec['id']}"):
                st.session_state.active_negotiation_id = rec['id']
                st.query_params["neg_id"] = rec['id']
                st.success(f"Loaded negotiation {rec['id']}. Switch to **Live Negotiation** on the sidebar.")


# ============================================================
# PAGE ROUTER: PRODUCT HISTORY
# ============================================================

            elif page == "Product History":
             render_product_history_dashboard(logged_in_user["username"], user_role)