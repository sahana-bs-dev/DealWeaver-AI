import sqlite3
import hashlib
import secrets
import hmac
import uuid
import re

DB_NAME = "dealweaver.db"
GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def generate_negotiation_id():
    return f"DW-{uuid.uuid4().hex[:6].upper()}"


def generate_listing_id():
    return f"LST-{uuid.uuid4().hex[:6].upper()}"


# ============================================================
# GSTIN & MOD-36 CHECKSUM VALIDATOR
# ============================================================

def compute_gstin_checksum(first_14: str) -> str:
    total = 0
    for idx, ch in enumerate(first_14):
        code_point = GST_CHARS.index(ch)
        factor = 2 if idx % 2 != 0 else 1
        product = code_point * factor
        total += (product // 36) + (product % 36)
    remainder = total % 36
    check_val = (36 - remainder) % 36
    return GST_CHARS[check_val]


def validate_gstin(gstin: str) -> tuple[bool, str]:
    gstin = (gstin or "").strip().upper()
    if len(gstin) != 15:
        return False, "GSTIN must be exactly 15 characters."
    if not GSTIN_REGEX.match(gstin):
        return False, "Invalid GSTIN format (expected 2-digit state + 10-char PAN + entity + Z + check digit)."
    expected_check = compute_gstin_checksum(gstin[:14])
    if gstin[14] != expected_check:
        return False, f"Invalid GSTIN checksum (expected '{expected_check}' as 15th character, got '{gstin[14]}')."
    return True, "Valid GSTIN & Checksum verified."


# ============================================================
# ELECTRONIC DEVICE & SECOND-HAND / REUSED DETECTOR
# ============================================================

ELECTRONICS_KEYWORDS = {
    "laptop", "macbook", "phone", "smartphone", "iphone", "samsung", "pixel",
    "tablet", "ipad", "monitor", "tv", "television", "camera", "dslr",
    "headphone", "earbuds", "airpods", "smartwatch", "watch", "gpu", "cpu",
    "pc", "desktop", "printer", "router", "console", "ps5", "xbox", "speaker",
    "charger", "ssd", "hard drive", "electronic", "electronics", "keyboard", "mouse"
}

SECONDHAND_KEYWORDS = {
    "second hand", "second-hand", "2nd hand", "used", "reused", "refurbished",
    "refurb", "pre-owned", "preowned", "open box", "open-box", "repaired",
    "old", "months old", "years old", "scratch", "scratches", "dent",
    "battery health", "without box", "no box", "no warranty", "display piece"
}


def detect_device_and_condition(product: str, specs: str, declared_condition: str = "New") -> dict:
    combined = f"{product} {specs}".lower()

    is_electronic = any(kw in combined for kw in ELECTRONICS_KEYWORDS)
    matched_used_terms = [kw for kw in SECONDHAND_KEYWORDS if kw in combined]

    is_reused = (declared_condition != "Brand New") or len(matched_used_terms) > 0

    if is_reused:
        if declared_condition == "Brand New" and matched_used_terms:
            status_label = "⚠️ Reused / Second-Hand Detected (Mismatch with 'Brand New' claim)"
            mismatch = True
        else:
            status_label = f"♻️ Second-Hand / Reused ({declared_condition})"
            mismatch = False
    else:
        status_label = "🆕 Brand New Electronic Device"
        mismatch = False

    return {
        "is_electronic": is_electronic,
        "is_reused": is_reused,
        "condition_status": status_label,
        "matched_terms": matched_used_terms,
        "condition_mismatch": mismatch,
    }


# ============================================================
# DATABASE SCHEMA & MIGRATIONS
# ============================================================

def create_database():
    conn = get_connection()

    table_info = conn.execute("PRAGMA table_info(negotiations)").fetchall()
    if table_info:
        id_col = next((col for col in table_info if col["name"] == "id"), None)
        if id_col and id_col["type"].upper() == "INTEGER":
            conn.execute("ALTER TABLE negotiations RENAME TO negotiations_old")
            conn.execute("ALTER TABLE negotiation_history RENAME TO negotiation_history_old")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS negotiations (
            id TEXT PRIMARY KEY,
            listing_id TEXT,
            product TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            listed_price REAL,
            buyer_budget REAL NOT NULL,
            seller_minimum REAL,
            opening_offer REAL NOT NULL,
            buyer_username TEXT,
            seller_username TEXT,
            seller_gstin TEXT,
            product_specs TEXT,
            declared_condition TEXT DEFAULT 'Brand New',
            is_reused INTEGER DEFAULT 0,
            condition_mismatch INTEGER DEFAULT 0,
            seller_verified INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            payment_status TEXT DEFAULT 'Pending',
            shipping_address TEXT,
            tracking_number TEXT,
            fulfillment_status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    existing_cols = {col["name"] for col in conn.execute("PRAGMA table_info(negotiations)").fetchall()}
    migrations = {
        "listing_id": "TEXT",
        "quantity": "INTEGER DEFAULT 1",
        "buyer_username": "TEXT",
        "seller_username": "TEXT",
        "seller_gstin": "TEXT",
        "product_specs": "TEXT",
        "declared_condition": "TEXT DEFAULT 'Brand New'",
        "is_reused": "INTEGER DEFAULT 0",
        "condition_mismatch": "INTEGER DEFAULT 0",
        "seller_verified": "INTEGER DEFAULT 0",
        "payment_status": "TEXT DEFAULT 'Pending'",
        "shipping_address": "TEXT",
        "tracking_number": "TEXT",
        "fulfillment_status": "TEXT DEFAULT 'Pending'",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }
    for col_name, col_def in migrations.items():
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE negotiations ADD COLUMN {col_name} {col_def}")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS negotiation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            negotiation_id TEXT NOT NULL,
            speaker TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL,
            reason TEXT,
            round_number INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (negotiation_id)
                REFERENCES negotiations(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS seller_listings (
            listing_id TEXT PRIMARY KEY,
            seller_username TEXT NOT NULL,
            seller_gstin TEXT,
            category TEXT DEFAULT 'Electronics',
            product TEXT NOT NULL,
            product_specs TEXT NOT NULL,
            declared_condition TEXT DEFAULT 'Brand New',
            is_reused INTEGER DEFAULT 0,
            condition_mismatch INTEGER DEFAULT 0,
            detected_keywords TEXT DEFAULT '',
            available_qty INTEGER NOT NULL DEFAULT 1,
            listed_unit_price REAL NOT NULL,
            seller_verified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    existing_listing_cols = {col["name"] for col in conn.execute("PRAGMA table_info(seller_listings)").fetchall()}
    listing_migrations = {
        "seller_gstin": "TEXT",
        "category": "TEXT DEFAULT 'Electronics'",
        "declared_condition": "TEXT DEFAULT 'Brand New'",
        "is_reused": "INTEGER DEFAULT 0",
        "condition_mismatch": "INTEGER DEFAULT 0",
        "detected_keywords": "TEXT DEFAULT ''",
    }
    for col_name, col_def in listing_migrations.items():
        if col_name not in existing_listing_cols:
            conn.execute(f"ALTER TABLE seller_listings ADD COLUMN {col_name} {col_def}")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Buyer', 'Seller')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

# ============================================================
# SELLER CATALOG FUNCTIONS
# ============================================================

def save_seller_listing(
    seller_username,
    product,
    product_specs,
    available_qty,
    listed_unit_price,
    seller_gstin="",
    declared_condition="Brand New",
    category="Electronics"
):
    gst_ok, _ = validate_gstin(seller_gstin)
    detection = detect_device_and_condition(product, product_specs, declared_condition)

    conn = get_connection()
    listing_id = generate_listing_id()

    conn.execute("""
        INSERT INTO seller_listings (
            listing_id, seller_username, seller_gstin, category, product,
            product_specs, declared_condition, is_reused, condition_mismatch,
            detected_keywords, available_qty, listed_unit_price, seller_verified
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        listing_id,
        seller_username,
        (seller_gstin or "").strip().upper(),
        category,
        product.strip(),
        product_specs.strip(),
        declared_condition,
        1 if detection["is_reused"] else 0,
        1 if detection["condition_mismatch"] else 0,
        ", ".join(detection["matched_terms"]),
        int(available_qty),
        float(listed_unit_price),
        1 if gst_ok else 0
    ))

    conn.commit()
    conn.close()
    return listing_id, gst_ok, detection


def get_all_seller_listings():
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM seller_listings
        WHERE available_qty > 0
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_seller_listing(listing_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM seller_listings WHERE listing_id = ?",
        (listing_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================
# NEGOTIATION STORAGE FUNCTIONS
# ============================================================

def save_negotiation(
    product,
    buyer_budget,
    opening_offer,
    quantity=1,
    buyer_username=None,
    listing_id=None,
    seller_username=None,
    seller_gstin="",
    product_specs="",
    declared_condition="Brand New",
    is_reused=False,
    condition_mismatch=False,
    seller_verified=False
):
    conn = get_connection()
    negotiation_id = generate_negotiation_id()

    # Automatically pull seller pricing and details from catalog if listing_id is provided
    listed_price = None
    seller_minimum = None
    if listing_id:
        listing = conn.execute("SELECT * FROM seller_listings WHERE listing_id = ?", (listing_id,)).fetchone()
        if listing:
            seller_username = listing["seller_username"]
            seller_gstin = listing["seller_gstin"]
            product_specs = listing["product_specs"]
            declared_condition = listing["declared_condition"]
            is_reused = listing["is_reused"]
            condition_mismatch = listing["condition_mismatch"]
            seller_verified = listing["seller_verified"]
            listed_price = listing["listed_unit_price"] * int(quantity)
            seller_minimum = listed_price * 0.85  # Automatic price floor baseline

    conn.execute("""
        INSERT INTO negotiations (
            id, listing_id, product, quantity, listed_price, buyer_budget, seller_minimum, opening_offer,
            buyer_username, seller_username, seller_gstin, product_specs,
            declared_condition, is_reused, condition_mismatch, seller_verified
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        negotiation_id,
        listing_id,
        product.strip(),
        int(quantity),
        float(listed_price) if listed_price is not None else None,
        float(buyer_budget),
        float(seller_minimum) if seller_minimum is not None else None,
        float(opening_offer),
        buyer_username,
        seller_username,
        (seller_gstin or "").strip().upper(),
        product_specs,
        declared_condition,
        1 if is_reused else 0,
        1 if condition_mismatch else 0,
        1 if seller_verified else 0
    ))

    conn.commit()
    conn.close()
    return negotiation_id


def update_seller_details(
    negotiation_id,
    listed_price,
    seller_minimum,
    seller_username=None,
    seller_gstin="",
    product_specs=None,
    declared_condition="Brand New"
):
    conn = get_connection()

    current = conn.execute(
        "SELECT * FROM negotiations WHERE id = ?",
        (str(negotiation_id).strip(),)
    ).fetchone()

    if not current:
        conn.close()
        return False

    gst_ok, _ = validate_gstin(seller_gstin)
    final_specs = product_specs if product_specs is not None else (current["product_specs"] or "")
    detection = detect_device_and_condition(current["product"], final_specs, declared_condition)

    cursor = conn.execute("""
        UPDATE negotiations
        SET listed_price = ?,
            seller_minimum = ?,
            seller_username = ?,
            seller_gstin = ?,
            product_specs = ?,
            declared_condition = ?,
            is_reused = ?,
            condition_mismatch = ?,
            seller_verified = ?
        WHERE id = ?
    """, (
        float(listed_price),
        float(seller_minimum),
        seller_username if seller_username is not None else current["seller_username"],
        (seller_gstin or "").strip().upper(),
        final_specs,
        declared_condition,
        1 if detection["is_reused"] else 0,
        1 if detection["condition_mismatch"] else 0,
        1 if gst_ok else 0,
        str(negotiation_id).strip()
    ))

    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_negotiation(negotiation_id):
    if not negotiation_id:
        return None
    conn = get_connection()
    result = conn.execute(
        "SELECT * FROM negotiations WHERE id = ?",
        (str(negotiation_id).strip(),)
    ).fetchone()
    conn.close()
    return dict(result) if result else None


def get_all_negotiations():
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, product, quantity, buyer_budget, listed_price, opening_offer,
               buyer_username, seller_username, is_reused, seller_verified, status, created_at
        FROM negotiations
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_offer(negotiation_id, speaker, action, price, reason, round_number):
    conn = get_connection()
    conn.execute("""
        INSERT INTO negotiation_history
        (negotiation_id, speaker, action, price, reason, round_number)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        str(negotiation_id).strip(),
        speaker,
        action,
        price,
        reason,
        round_number
    ))
    conn.commit()
    conn.close()


def get_offer_history(negotiation_id):
    conn = get_connection()
    results = conn.execute("""
        SELECT speaker, action, price, reason, round_number, created_at
        FROM negotiation_history
        WHERE negotiation_id = ?
        ORDER BY id ASC
    """, (str(negotiation_id).strip(),)).fetchall()
    conn.close()
    return [dict(row) for row in results]


def update_negotiation_status(negotiation_id, status):
    conn = get_connection()
    conn.execute("""
        UPDATE negotiations
        SET status = ?
        WHERE id = ?
    """, (status, str(negotiation_id).strip()))
    conn.commit()
    conn.close()


def get_product_history_for_user(username: str, role: str):
    """Retrieves all past and active product negotiations for a specific Buyer or Seller."""
    conn = get_connection()
    if role == "Buyer":
        rows = conn.execute("""
            SELECT n.*, 
                   (SELECT COUNT(*) FROM negotiation_history h WHERE h.negotiation_id = n.id) as total_turns
            FROM negotiations n
            WHERE n.buyer_username = ?
            ORDER BY n.created_at DESC
        """, (username,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT n.*, 
                   (SELECT COUNT(*) FROM negotiation_history h WHERE h.negotiation_id = n.id) as total_turns
            FROM negotiations n
            WHERE n.seller_username = ?
            ORDER BY n.created_at DESC
        """, (username,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ============================================================
# USER AUTHENTICATION FUNCTIONS
# ============================================================

def register_user(username, password, role):
    username = username.strip().lower()

    if len(username) < 3:
        return False, "Username must contain at least 3 characters."

    if len(password) < 8:
        return False, "Password must contain at least 8 characters."

    if role not in ["Buyer", "Seller"]:
        return False, "Invalid user role."

    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        310000
    ).hex()

    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO users
            (username, password_hash, salt, role)
            VALUES (?, ?, ?, ?)
        """, (username, password_hash, salt, role))
        conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "Username already exists. Choose another."
    finally:
        conn.close()


def authenticate_user(username, password):
    username = username.strip().lower()

    conn = get_connection()
    user = conn.execute("""
        SELECT * FROM users
        WHERE username = ?
    """, (username,)).fetchone()
    conn.close()

    if not user:
        return None

    entered_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        user["salt"].encode("utf-8"),
        310000
    ).hex()

    if hmac.compare_digest(entered_hash, user["password_hash"]):
        return {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"]
        }

    return None