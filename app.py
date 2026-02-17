import os
import re
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st


# ---------------------------
# Config (Local + Render)
# ---------------------------
DATA_DIR = os.environ.get("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "realestate.db")


# ---------------------------
# DB helpers
# ---------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def ensure_tables(conn: sqlite3.Connection):
    # Base table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS properties (
        file_code TEXT PRIMARY KEY,
        deal_type TEXT,
        region TEXT,
        address TEXT,
        area_m2 REAL,
        price_million REAL,
        property_type TEXT,
        description TEXT,
        updated_at TEXT
    );
    """)

    # Upload logs
    conn.execute("""
    CREATE TABLE IF NOT EXISTS uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uploaded_at TEXT,
        rows_read INTEGER,
        rows_upserted INTEGER
    );
    """)
    conn.commit()


# ---------------------------
# Normalizers / Parsers
# ---------------------------
def normalize_deal_type(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    # Only 2 categories you want:
    if "رهن" in s or "اجاره" in s:
        return "رهن و اجاره"
    if "فروش" in s or "خرید" in s:
        return "خرید و فروش"
    return s


def parse_price_million(v) -> float | None:
    """
    Your convention:
      - numbers are in MILLION
      - 5 billion => 5000
    Also supports strings like "5 میلیارد" or "5000 میلیون" or "5,000,000,000 تومان".
    Returns: price in MILLION.
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None

    # numeric => assume million directly
    if isinstance(v, (int, float)):
        return float(v)

    s = str(v).strip()
    if not s:
        return None

    s = s.replace(",", "").replace("٬", "").replace(" ", "").replace("\u200c", "")

    # "X میلیارد"
    m = re.search(r"(\d+(\.\d+)?)میلیارد", s)
    if m:
        return float(m.group(1)) * 1000.0

    # "X میلیون"
    m = re.search(r"(\d+(\.\d+)?)میلیون", s)
    if m:
        return float(m.group(1))

    # ".... تومان" or plain digits
    m = re.search(r"(\d+)(تومان)?", s)
    if m:
        raw = float(m.group(1))
        # if looks like full toman
        if raw >= 1_000_000:
            return raw / 1_000_000.0
        # otherwise assume million
        return raw

    return None


def to_toman_from_million(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    try:
        toman = int(round(float(x) * 1_000_000))
        return f"{toman:,} تومان"
    except Exception:
        return ""


# ---------------------------
# Excel loader (Robust)
# ---------------------------
def load_excel(file) -> pd.DataFrame:
    df = pd.read_excel(file, sheet_name="Database", engine="openpyxl")

    def norm(s):
        return str(s).strip().replace("‌", "").replace("\u200c", "").replace(" ", "")

    cols = list(df.columns)
    cols_norm = {c: norm(c) for c in cols}

    col_map = {}

    # file_code
    for c in cols:
        n = cols_norm[c]
        if ("کد" in n) and ("فایل" in n or "ملک" in n):
            col_map["file_code"] = c
            break
    if "file_code" not in col_map:
        for c in cols:
            if "کد" in cols_norm[c]:
                col_map["file_code"] = c
                break

    # deal_type
    for c in cols:
        n = cols_norm[c]
        if "نوعمعامله" in n or ("نوع" in n and "معامله" in n):
            col_map["deal_type"] = c
            break

    # region
    for c in cols:
        if "منطقه" in cols_norm[c]:
            col_map["region"] = c
            break

    # address
    for c in cols:
        n = cols_norm[c]
        if "آدرس" in n or "ادرس" in n:
            col_map["address"] = c
            break

    # area_m2
    for c in cols:
        if "متراژ" in cols_norm[c]:
            col_map["area_m2"] = c
            break

    # property_type
    for c in cols:
        n = cols_norm[c]
        if "نوعملک" in n or ("نوع" in n and "ملک" in n):
            col_map["property_type"] = c
            break

    # description (optional)
    for c in cols:
        n = cols_norm[c]
        if "توضیحات" in n or "شرح" in n:
            col_map["description"] = c
            break

    # PRICE: prioritize total price (not per m2)
    # price_total
    for c in cols:
        n = cols_norm[c]
        if ("قیمتکل" in n) or (("قیمت" in n) and ("کل" in n)):
            col_map["price_total"] = c
            break

    # price per m2 (optional, we don't use it as main price)
    for c in cols:
        n = cols_norm[c]
        if ("قیمتهرمتر" in n) or (("قیمت" in n) and ("هرمتر" in n or "متر" in n)):
            col_map["price_per_m2"] = c
            break

    # fallback: if only one price-like column exists
    if "price_total" not in col_map:
        price_like = [c for c in cols if "قیمت" in cols_norm[c]]
        if len(price_like) == 1:
            col_map["price_total"] = price_like[0]

    # required columns
    required = ["file_code", "deal_type", "region", "address", "area_m2", "property_type", "price_total"]
    missing = [k for k in required if k not in col_map]
    if missing:
        st.error("ستون‌های لازم پیدا نشد: " + "، ".join(missing))
        st.info("نام ستون‌های شیت Database:\n- " + "\n- ".join([str(c) for c in cols]))
        st.stop()

    out = pd.DataFrame({
        "file_code": df[col_map["file_code"]].astype(str).str.strip(),
        "deal_type": df[col_map["deal_type"]].apply(normalize_deal_type),
        "region": df[col_map["region"]].astype(str).str.strip(),
        "address": df[col_map["address"]].astype(str).str.strip(),
        "area_m2": pd.to_numeric(df[col_map["area_m2"]], errors="coerce"),
        "price_million": df[col_map["price_total"]].apply(parse_price_million),
        "property_type": df[col_map["property_type"]].astype(str).str.strip(),
        "description": df[col_map["description"]].astype(str).str.strip() if "description" in col_map else "",
    })

    # clean
    out = out[out["file_code"].notna() & (out["file_code"] != "")].copy()
    out["region"] = out["region"].replace({"nan": ""})
    out["address"] = out["address"].replace({"nan": ""})
    out["property_type"] = out["property_type"].replace({"nan": ""})
    out["description"] = out["description"].replace({"nan": ""})
    out["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")

    return out


# ---------------------------
# Upsert
# ---------------------------
def upsert_properties(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    cur = conn.cursor()
    rows = 0

    for _, r in df.iterrows():
        cur.execute("""
        INSERT INTO properties
          (file_code, deal_type, region, address, area_m2, price_million, property_type, description, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_code) DO UPDATE SET
          deal_type=excluded.deal_type,
          region=excluded.region,
          address=excluded.address,
          area_m2=excluded.area_m2,
          price_million=excluded.price_million,
          property_type=excluded.property_type,
          description=excluded.description,
          updated_at=excluded.updated_at
        """, (
            str(r["file_code"]).strip(),
            r["deal_type"],
            r["region"],
            r["address"],
            None if pd.isna(r["area_m2"]) else float(r["area_m2"]),
            None if (r["price_million"] is None or (isinstance(r["price_million"], float) and pd.isna(r["price_million"]))) else float(r["price_million"]),
            r["property_type"],
            r["description"],
            r["updated_at"],
        ))
        rows += 1

    conn.commit()
    return rows


# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title="سیستم جستجوی املاک", layout="wide")
st.title("سیستم جستجوی املاک (آپدیت روزانه + سرچ حرفه‌ای)")

conn = get_conn()
ensure_tables(conn)

tab1, tab2 = st.tabs(["آپلود/آپدیت روزانه", "جستجو و خروجی"])

# Upload tab
with tab1:
    st.subheader("آپلود فایل اکسل و بروزرسانی دیتابیس")
    st.caption("فایل اکسل باید شیت Database داشته باشد.")
    up = st.file_uploader("آپلود Excel", type=["xlsx"])

    if up is not None:
        df = load_excel(up)
        st.write("پیش‌نمایش داده‌ها:", df.head(30))

        if st.button("بروزرسانی دیتابیس (Merge/Upsert)"):
            n = upsert_properties(conn, df)
            conn.execute(
                "INSERT INTO uploads(uploaded_at, rows_read, rows_upserted) VALUES(?,?,?)",
                (datetime.utcnow().isoformat(timespec="seconds"), len(df), n)
            )
            conn.commit()
            st.success(f"انجام شد. {n} ردیف درج/آپدیت شد.")

    st.divider()
    st.subheader("آخرین آپلودها")
    logs = pd.read_sql_query(
        "SELECT uploaded_at, rows_read, rows_upserted FROM uploads ORDER BY id DESC LIMIT 20",
        conn
    )
    st.dataframe(logs, use_container_width=True)

# Search tab (Professional)
with tab2:
    st.subheader("جستجو و فیلتر حرفه‌ای")

    # Options from DB
    deal_opts = ["", "خرید و فروش", "رهن و اجاره"]
    prop_opts = [""] + [r[0] for r in conn.execute(
        "SELECT DISTINCT property_type FROM properties WHERE property_type IS NOT NULL AND TRIM(property_type)<>'' ORDER BY property_type"
    ).fetchall()]
    region_opts = [""] + [r[0] for r in conn.execute(
        "SELECT DISTINCT region FROM properties WHERE region IS NOT NULL AND TRIM(region)<>'' ORDER BY region"
    ).fetchall()]

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        deal = st.selectbox("نوع معامله", deal_opts, index=0)
        ptype = st.selectbox("نوع ملک", prop_opts, index=0)

    with c2:
        region = st.selectbox("منطقه", region_opts, index=0)
        file_code = st.text_input("کد فایل (اختیاری)")

    with c3:
        min_area = st.number_input("متراژ از", min_value=0.0, value=0.0, step=10.0)
        max_area = st.number_input("متراژ تا (0 یعنی محدودیت ندارد)", min_value=0.0, value=0.0, step=10.0)

    with c4:
        min_price = st.number_input("قیمت از (میلیون)", min_value=0.0, value=0.0, step=50.0)
        max_price = st.number_input("قیمت تا (میلیون) (0 یعنی محدودیت ندارد)", min_value=0.0, value=0.0, step=50.0)

    run = st.button("جستجو")

    if run:
        query = """
            SELECT
              file_code, deal_type, region, property_type, area_m2, price_million, address, description, updated_at
            FROM properties
            WHERE 1=1
        """
        params = []

        if file_code.strip():
            query += " AND file_code LIKE ?"
            params.append(f"%{file_code.strip()}%")

        if deal:
            query += " AND deal_type = ?"
            params.append(deal)

        if ptype:
            query += " AND property_type = ?"
            params.append(ptype)

        if region:
            query += " AND region = ?"
            params.append(region)

        if min_area > 0:
            query += " AND area_m2 >= ?"
            params.append(float(min_area))

        if max_area > 0:
            query += " AND area_m2 <= ?"
            params.append(float(max_area))

        if min_price > 0:
            query += " AND price_million >= ?"
            params.append(float(min_price))

        if max_price > 0:
            query += " AND price_million <= ?"
            params.append(float(max_price))

        query += " ORDER BY price_million ASC, updated_at DESC"

        res = pd.read_sql_query(query, conn, params=params)

        if res.empty:
            st.warning("هیچ نتیجه‌ای پیدا نشد.")
        else:
            res["قیمت (تومان)"] = res["price_million"].apply(to_toman_from_million)
            res = res.drop(columns=["price_million"])
            st.write(f"تعداد نتایج: {len(res)}")
            st.dataframe(res, use_container_width=True)

            csv = res.to_csv(index=False).encode("utf-8-sig")
            st.download_button("دانلود CSV نتایج", csv, "results.csv", "text/csv")