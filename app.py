import os
import re
from datetime import datetime

import pandas as pd
import psycopg2
import streamlit as st


# =========================
# Streamlit config (MUST be first st.*)
# =========================
st.set_page_config(page_title="سیستم املاک", layout="wide")


# =========================
# ENV
# =========================
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")
CLIENT_PASSWORD = os.environ.get("CLIENT_PASSWORD", "1234")


# =========================
# Money helpers (DB unit = million)
# 5 میلیارد => 5000
# =========================
def toman_str_from_million(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    try:
        toman = int(round(float(x) * 1_000_000))
        return f"{toman:,} تومان"
    except Exception:
        return ""


def billion_str_from_million(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    try:
        b = float(x) / 1000.0
        if b >= 1:
            return f"{b:.2f} میلیارد"
        return f"{float(x):.0f} میلیون"
    except Exception:
        return ""


def normalize_text(x) -> str:
    if x is None:
        return ""
    return (
        str(x)
        .replace("\u200c", "")
        .replace("‌", "")
        .strip()
    )


def normalize_deal_type(x) -> str:
    s = normalize_text(x)
    if not s:
        return ""
    if "رهن" in s or "اجاره" in s:
        return "رهن و اجاره"
    if "خرید" in s or "فروش" in s:
        return "خرید و فروش"
    return s


def parse_price_million(v) -> float | None:
    """
    Parse user/excel price into 'million'.
    Examples:
      "5 میلیارد" => 5000
      5000 => 5000
      "200 میلیون" => 200
      "5,000" => 5000 (assumed million)
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)

    s = normalize_text(v)
    if not s:
        return None
    s = s.replace(",", "").replace("٬", "").replace(" ", "")

    m = re.search(r"(\d+(\.\d+)?)میلیارد", s)
    if m:
        return float(m.group(1)) * 1000.0

    m = re.search(r"(\d+(\.\d+)?)میلیون", s)
    if m:
        return float(m.group(1))

    m = re.search(r"(\d+(\.\d+)?)", s)
    if m:
        raw = float(m.group(1))
        # if someone pasted toman big number:
        if raw >= 1_000_000:
            return raw / 1_000_000.0
        return raw

    return None


def now_utc():
    return datetime.utcnow()


# =========================
# DB (stable connect + keepalive)
# =========================
@st.cache_resource
def _make_conn():
    if not DATABASE_URL:
        st.error("DATABASE_URL تنظیم نشده است. در Variables سرویس مقدار DATABASE_URL را قرار بده.")
        st.stop()

    conn = psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )
    conn.autocommit = True
    return conn


def get_conn_safe():
    try:
        conn = _make_conn()
        with conn.cursor() as cur:
            cur.execute("select 1;")
        return conn
    except Exception:
        try:
            _make_conn.clear()
        except Exception:
            pass
        return _make_conn()


def ensure_tables(conn):
    with conn.cursor() as cur:
        # properties
        cur.execute("""
        create table if not exists properties (
          file_code text primary key,
          deal_type text,
          region text,
          address text,
          area_m2 numeric,
          price_million numeric,
          property_type text,
          bedrooms integer,
          description text,
          owner_name text,
          owner_phone text,
          internal_notes text,
          updated_at timestamp
        );
        """)

        # applicants
        cur.execute("""
        create table if not exists applicants (
          id bigserial primary key,
          full_name text,
          phone text,
          deal_type text,
          desired_property_type text,
          region text,
          budget_min_million numeric,
          budget_max_million numeric,
          bedrooms_min integer,
          notes text,
          created_at timestamp,
          updated_at timestamp
        );
        """)

        # uploads log
        cur.execute("""
        create table if not exists uploads (
          id bigserial primary key,
          uploaded_at timestamp,
          rows_read integer,
          rows_upserted integer
        );
        """)

        # migrations (safe)
        cur.execute("alter table properties add column if not exists bedrooms integer;")
        cur.execute("alter table properties add column if not exists description text;")
        cur.execute("alter table applicants add column if not exists notes text;")
        cur.execute("alter table applicants add column if not exists bedrooms_min integer;")
        cur.execute("alter table applicants add column if not exists budget_min_million numeric;")
        cur.execute("alter table applicants add column if not exists budget_max_million numeric;")


# =========================
# Cache helpers (reduce load)
# =========================
@st.cache_data(ttl=180)
def fetch_minmax_prices(_dsn: str):
    conn = get_conn_safe()
    df = pd.read_sql_query(
        "select min(price_million) as mn, max(price_million) as mx from properties",
        conn
    )
    mn = df.loc[0, "mn"]
    mx = df.loc[0, "mx"]
    mn = 0.0 if mn is None or (isinstance(mn, float) and pd.isna(mn)) else float(mn)
    mx = 0.0 if mx is None or (isinstance(mx, float) and pd.isna(mx)) else float(mx)
    return mn, mx


def clear_caches():
    try:
        fetch_minmax_prices.clear()
    except Exception:
        pass


# =========================
# Auth
# =========================
if "role" not in st.session_state:
    st.session_state.role = None

with st.sidebar:
    st.header("ورود")
    role_ui = st.selectbox("نقش", ["مشتری", "مدیر"], key="login_role_v1")
    pwd = st.text_input("رمز", type="password", key="login_pwd_v1")

    c1, c2 = st.columns(2)
    if c1.button("ورود", key="login_btn_v1"):
        if role_ui == "مدیر" and pwd == ADMIN_PASSWORD:
            st.session_state.role = "admin"
            st.success("ورود مدیر موفق بود.")
        elif role_ui == "مشتری" and pwd == CLIENT_PASSWORD:
            st.session_state.role = "client"
            st.success("ورود مشتری موفق بود.")
        else:
            st.error("رمز اشتباه است.")

    if c2.button("خروج", key="logout_btn_v1"):
        st.session_state.role = None
        st.info("خارج شدید.")

if st.session_state.role is None:
    st.warning("برای استفاده از برنامه، از نوار کناری وارد شوید.")
    st.stop()

is_admin = st.session_state.role == "admin"


# =========================
# Init DB
# =========================
conn = get_conn_safe()
ensure_tables(conn)


# =========================
# UI title
# =========================
st.title("سیستم املاک")


# =========================
# Core: list views
# =========================
NO_BEDROOM_KEYWORDS = ["زمین", "اداری", "تجاری", "مغازه", "سوله", "انبار", "کارگاه"]


def bedrooms_display(row) -> str:
    ptype = normalize_text(row.get("property_type", ""))
    if any(k in ptype for k in NO_BEDROOM_KEYWORDS):
        return ""
    b = row.get("bedrooms")
    if b is None or (isinstance(b, float) and pd.isna(b)):
        return ""
    try:
        bi = int(float(b))
        return "" if bi <= 0 else str(bi)
    except Exception:
        return ""


def client_files_tab():
    st.subheader("فایل‌ها")

    mn, mx = fetch_minmax_prices(DATABASE_URL)
    if mx <= 0:
        mx = 10000.0  # fallback

    q = st.text_input("جستجوی سریع", placeholder="کد فایل / منطقه / نوع ملک ...", key="cl_q_v1")
    deal = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], key="cl_deal_v1")
    price_rng = st.slider(
        "بازه قیمت (میلیون) — ۵ میلیارد = ۵۰۰۰",
        min_value=float(mn),
        max_value=float(mx),
        value=(float(mn), float(mx)),
        step=50.0,
        key="cl_price_rng_v1"
    )

    where = ["1=1"]
    params = []

    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(file_code ILIKE %s OR region ILIKE %s OR property_type ILIKE %s)")
        params += [like, like, like]

    if deal != "همه":
        where.append("lower(trim(deal_type)) = lower(trim(%s))")
        params.append(deal)

    # keep rows that have price within range (ignore NULL in client list for clarity)
    where.append("price_million is not null and price_million >= %s and price_million <= %s")
    params += [float(price_rng[0]), float(price_rng[1])]

    df = pd.read_sql_query(
        f"""
        select file_code, deal_type, region, property_type, bedrooms, area_m2, price_million, description, updated_at
        from properties
        where {" and ".join(where)}
        order by updated_at desc nulls last
        limit 300
        """,
        conn,
        params=tuple(params)
    )

    if df.empty:
        st.info("نتیجه‌ای پیدا نشد.")
        return

    df = df.copy()
    df["خواب"] = df.apply(bedrooms_display, axis=1)
    df["قیمت (میلیارد)"] = df["price_million"].apply(billion_str_from_million)
    df["قیمت (تومان)"] = df["price_million"].apply(toman_str_from_million)

    show = df[[
        "file_code", "deal_type", "region", "property_type", "خواب", "area_m2",
        "قیمت (میلیارد)", "قیمت (تومان)", "description", "updated_at"
    ]].rename(columns={
        "file_code": "کد فایل",
        "deal_type": "نوع معامله",
        "region": "منطقه",
        "property_type": "نوع ملک",
        "area_m2": "متراژ",
        "description": "توضیحات",
        "updated_at": "آپدیت"
    })

    st.dataframe(show, use_container_width=True)


def admin_files_list_tab():
    st.subheader("لیست فایل‌ها (مدیر)")

    q = st.text_input("جستجوی سریع", placeholder="کد فایل / منطقه / نوع ملک ...", key="al_q_v1")
    deal = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], key="al_deal_v1")
    limit = st.selectbox("تعداد نمایش", [50, 100, 200, 500], index=1, key="al_limit_v1")

    where = ["1=1"]
    params = []

    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(file_code ILIKE %s OR region ILIKE %s OR property_type ILIKE %s)")
        params += [like, like, like]

    if deal != "همه":
        where.append("lower(trim(deal_type)) = lower(trim(%s))")
        params.append(deal)

    df = pd.read_sql_query(
        f"""
        select file_code, deal_type, property_type, region, area_m2, bedrooms,
               price_million, owner_name, owner_phone, description, updated_at
        from properties
        where {" and ".join(where)}
        order by updated_at desc nulls last
        limit %s
        """,
        conn,
        params=tuple(params + [int(limit)])
    )

    if df.empty:
        st.info("فایلی پیدا نشد.")
        return

    df = df.copy()
    df["قیمت (میلیارد)"] = df["price_million"].apply(billion_str_from_million)
    df["قیمت (تومان)"] = df["price_million"].apply(toman_str_from_million)
    df["خواب"] = df.apply(bedrooms_display, axis=1)

    show = df[[
        "file_code", "deal_type", "region", "property_type", "خواب",
        "area_m2", "قیمت (میلیارد)", "قیمت (تومان)",
        "owner_name", "owner_phone", "description", "updated_at"
    ]].rename(columns={
        "file_code": "کد فایل",
        "deal_type": "نوع معامله",
        "region": "منطقه",
        "property_type": "نوع ملک",
        "area_m2": "متراژ",
        "owner_name": "مالک",
        "owner_phone": "شماره مالک",
        "description": "توضیحات",
        "updated_at": "آپدیت"
    })

    st.dataframe(show, use_container_width=True)


# =========================
# Admin: Add/Edit Property (with duplicate code warning)
# =========================
def admin_add_edit_property_tab():
    st.subheader("ثبت / ویرایش فایل (مدیر)")

    # quick check existing
    code_lookup = st.text_input("برای ویرایش/بررسی، کد فایل را وارد کن", key="prop_lookup_code_v1").strip()
    existing = None
    if code_lookup:
        ex = pd.read_sql_query(
            "select * from properties where file_code=%s",
            conn,
            params=(code_lookup,)
        )
        if not ex.empty:
            existing = ex.iloc[0].to_dict()
            st.info("این کد فایل وجود دارد. اگر ذخیره کنی، اطلاعات **آپدیت** می‌شود.")
        else:
            st.success("این کد فایل جدید است.")

    def exv(k, default=""):
        if not existing:
            return default
        v = existing.get(k)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return v

    with st.form("prop_form_v1"):
        file_code = st.text_input("کد فایل", value=str(code_lookup or ""), key="prop_code_v1")
        deal_type = st.selectbox(
            "نوع معامله",
            ["خرید و فروش", "رهن و اجاره"],
            index=0 if normalize_deal_type(exv("deal_type", "خرید و فروش")) == "خرید و فروش" else 1,
            key="prop_deal_v1"
        )
        property_type = st.text_input("نوع ملک", value=str(exv("property_type", "")), key="prop_ptype_v1")
        region = st.text_input("منطقه", value=str(exv("region", "")), key="prop_region_v1")
        address = st.text_input("آدرس (اختیاری)", value=str(exv("address", "")), key="prop_addr_v1")

        c1, c2, c3 = st.columns(3)
        with c1:
            area_m2 = st.number_input(
                "متراژ",
                min_value=0.0,
                value=float(exv("area_m2", 0.0) or 0.0),
                step=1.0,
                key="prop_area_v1"
            )
        with c2:
            bedrooms = st.number_input(
                "تعداد خواب (اگر ندارد 0 بزن)",
                min_value=0,
                value=int(exv("bedrooms", 0) or 0),
                step=1,
                key="prop_bed_v1"
            )
        with c3:
            price_million = st.number_input(
                "قیمت کل (میلیون) — ۵ میلیارد = ۵۰۰۰",
                min_value=0.0,
                value=float(exv("price_million", 0.0) or 0.0),
                step=50.0,
                key="prop_price_v1"
            )

        description = st.text_area("توضیحات", value=str(exv("description", "")), key="prop_desc_v1")
        owner_name = st.text_input("نام مالک (فقط مدیر)", value=str(exv("owner_name", "")), key="prop_owner_v1")
        owner_phone = st.text_input("شماره مالک (فقط مدیر)", value=str(exv("owner_phone", "")), key="prop_owner_phone_v1")
        internal_notes = st.text_area("یادداشت داخلی (فقط مدیر)", value=str(exv("internal_notes", "")), key="prop_notes_v1")

        colA, colB, colC = st.columns([1, 1, 2])
        save_btn = colA.form_submit_button("ذخیره (Upsert)")
        del_btn = colB.form_submit_button("حذف فایل")

    if save_btn:
        if not file_code.strip():
            st.error("کد فایل الزامی است.")
            return

        # ✅ Duplicate warning (again, at save time)
        ex2 = pd.read_sql_query(
            "select file_code from properties where file_code=%s",
            conn,
            params=(file_code.strip(),)
        )
        if not ex2.empty:
            st.warning("اخطار: این کد فایل تکراری است و با ذخیره، اطلاعات **جایگزین/آپدیت** می‌شود.")

        deal_norm = normalize_deal_type(deal_type)

        with conn.cursor() as cur:
            cur.execute("""
            insert into properties
              (file_code, deal_type, region, address, area_m2, price_million, property_type, bedrooms,
               description, owner_name, owner_phone, internal_notes, updated_at)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            on conflict (file_code) do update set
              deal_type=excluded.deal_type,
              region=excluded.region,
              address=excluded.address,
              area_m2=excluded.area_m2,
              price_million=excluded.price_million,
              property_type=excluded.property_type,
              bedrooms=excluded.bedrooms,
              description=excluded.description,
              owner_name=excluded.owner_name,
              owner_phone=excluded.owner_phone,
              internal_notes=excluded.internal_notes,
              updated_at=excluded.updated_at
            """, (
                file_code.strip(),
                deal_norm,
                normalize_text(region),
                normalize_text(address),
                float(area_m2) if area_m2 else None,
                float(price_million) if price_million else None,
                normalize_text(property_type),
                int(bedrooms) if bedrooms else None,
                normalize_text(description),
                normalize_text(owner_name),
                normalize_text(owner_phone),
                normalize_text(internal_notes),
            ))

        clear_caches()
        st.success("فایل ذخیره شد.")
        st.rerun()

    if del_btn:
        if not file_code.strip():
            st.error("برای حذف، کد فایل را وارد کن.")
            return
        with conn.cursor() as cur:
            cur.execute("delete from properties where file_code=%s", (file_code.strip(),))
        clear_caches()
        st.success("فایل حذف شد.")
        st.rerun()


# =========================
# Admin: Upload Excel (Database sheet)
# =========================
def load_excel(file) -> pd.DataFrame:
    df = pd.read_excel(file, sheet_name="Database", engine="openpyxl")

    def norm_col(s):
        return normalize_text(s).replace(" ", "")

    cols = list(df.columns)
    cols_norm = {c: norm_col(c) for c in cols}
    col_map = {}

    def find_col(key, predicate):
        for c in cols:
            if predicate(cols_norm[c]):
                col_map[key] = c
                return

    find_col("file_code", lambda n: ("کد" in n) and ("فایل" in n or "ملک" in n))
    if "file_code" not in col_map:
        find_col("file_code", lambda n: "کد" in n)

    find_col("deal_type", lambda n: ("نوعمعامله" in n) or ("نوع" in n and "معامله" in n))
    find_col("region", lambda n: "منطقه" in n)
    find_col("address", lambda n: ("آدرس" in n) or ("ادرس" in n))
    find_col("area_m2", lambda n: "متراژ" in n)
    find_col("property_type", lambda n: ("نوعملک" in n) or ("نوع" in n and "ملک" in n))
    find_col("bedrooms", lambda n: ("اتاقخواب" in n) or ("خواب" in n))
    find_col("description", lambda n: ("توضیحات" in n) or ("شرح" in n))

    # price total
    find_col("price_total", lambda n: ("قیمتکل" in n) or (("قیمت" in n) and ("کل" in n)))
    if "price_total" not in col_map:
        # fallback: if only one price column exists, take it
        price_like = [c for c in cols if "قیمت" in cols_norm[c]]
        if len(price_like) == 1:
            col_map["price_total"] = price_like[0]

    # optional owner fields
    find_col("owner_name", lambda n: ("مالک" in n) and (("نام" in n) or ("اسم" in n)))
    find_col("owner_phone", lambda n: (("تماس" in n and "مالک" in n) or ("شماره" in n and "مالک" in n) or ("موبایل" in n and "مالک" in n)))
    find_col("internal_notes", lambda n: ("یادداشت" in n) or ("داخلی" in n) or ("نکته" in n))

    required = ["file_code", "deal_type", "region", "property_type", "area_m2", "price_total"]
    missing = [k for k in required if k not in col_map]
    if missing:
        st.error("ستون‌های لازم پیدا نشد: " + "، ".join(missing))
        st.info("نام ستون‌های شیت Database:\n- " + "\n- ".join([str(c) for c in cols]))
        st.stop()

    out = pd.DataFrame({
        "file_code": df[col_map["file_code"]].astype(str).str.strip(),
        "deal_type": df[col_map["deal_type"]].apply(normalize_deal_type),
        "region": df[col_map["region"]].astype(str).map(normalize_text),
        "address": df[col_map["address"]].astype(str).map(normalize_text) if "address" in col_map else "",
        "area_m2": pd.to_numeric(df[col_map["area_m2"]], errors="coerce"),
        "price_million": df[col_map["price_total"]].apply(parse_price_million),
        "property_type": df[col_map["property_type"]].astype(str).map(normalize_text),
        "bedrooms": pd.to_numeric(df[col_map["bedrooms"]], errors="coerce") if "bedrooms" in col_map else None,
        "description": df[col_map["description"]].astype(str).map(normalize_text) if "description" in col_map else "",
        "owner_name": df[col_map["owner_name"]].astype(str).map(normalize_text) if "owner_name" in col_map else "",
        "owner_phone": df[col_map["owner_phone"]].astype(str).map(normalize_text) if "owner_phone" in col_map else "",
        "internal_notes": df[col_map["internal_notes"]].astype(str).map(normalize_text) if "internal_notes" in col_map else "",
        "updated_at": now_utc(),
    })

    out = out[out["file_code"].notna() & (out["file_code"] != "")].copy()
    return out


def upsert_properties(conn, df: pd.DataFrame) -> int:
    rows = 0
    with conn.cursor() as cur:
        for _, r in df.iterrows():
            cur.execute("""
            insert into properties
              (file_code, deal_type, region, address, area_m2, price_million, property_type, bedrooms,
               description, owner_name, owner_phone, internal_notes, updated_at)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (file_code) do update set
              deal_type=excluded.deal_type,
              region=excluded.region,
              address=excluded.address,
              area_m2=excluded.area_m2,
              price_million=excluded.price_million,
              property_type=excluded.property_type,
              bedrooms=excluded.bedrooms,
              description=excluded.description,
              owner_name=excluded.owner_name,
              owner_phone=excluded.owner_phone,
              internal_notes=excluded.internal_notes,
              updated_at=excluded.updated_at
            """, (
                normalize_text(r["file_code"]),
                normalize_deal_type(r["deal_type"]),
                normalize_text(r["region"]),
                normalize_text(r["address"]),
                None if pd.isna(r["area_m2"]) else float(r["area_m2"]),
                None if (r["price_million"] is None or (isinstance(r["price_million"], float) and pd.isna(r["price_million"]))) else float(r["price_million"]),
                normalize_text(r["property_type"]),
                None if r.get("bedrooms") is None or (isinstance(r.get("bedrooms"), float) and pd.isna(r.get("bedrooms"))) else int(float(r.get("bedrooms"))),
                normalize_text(r.get("description", "")),
                normalize_text(r.get("owner_name", "")),
                normalize_text(r.get("owner_phone", "")),
                normalize_text(r.get("internal_notes", "")),
                now_utc(),
            ))
            rows += 1
    return rows


def admin_upload_tab():
    st.subheader("آپلود اکسل و بروزرسانی (مدیر)")
    st.caption("قیمت کل بر حسب میلیون است: ۵ میلیارد = ۵۰۰۰")

    up = st.file_uploader("آپلود Excel", type=["xlsx"], key="adm_upload_excel_v1")
    if up is not None:
        df = load_excel(up)
        st.write("پیش‌نمایش:", df.head(30))
        if st.button("بروزرسانی دیتابیس (Upsert)", key="adm_do_upsert_v1"):
            n = upsert_properties(conn, df)
            with conn.cursor() as cur:
                cur.execute(
                    "insert into uploads(uploaded_at, rows_read, rows_upserted) values (%s,%s,%s)",
                    (now_utc(), int(len(df)), int(n))
                )
            clear_caches()
            st.success(f"انجام شد. {n} ردیف درج/آپدیت شد.")
            st.rerun()

    st.divider()
    st.subheader("آخرین آپلودها")
    logs = pd.read_sql_query(
        "select uploaded_at, rows_read, rows_upserted from uploads order by id desc limit 20",
        conn
    )
    st.dataframe(logs, use_container_width=True)


# =========================
# Applicants (FULL + MATCH FIXED)
# =========================
def applicants_tab():
    st.subheader("متقاضیان (مدیر)")

    apps = pd.read_sql_query(
        """
        select id, full_name, phone, deal_type, desired_property_type, region,
               budget_min_million, budget_max_million, bedrooms_min, notes, updated_at
        from applicants
        order by updated_at desc nulls last, id desc
        """,
        conn
    )

    left, right = st.columns([1.05, 1])

    # --- Left: add/edit/delete
    with left:
        st.markdown("### ثبت / ویرایش متقاضی")

        mode = st.radio("حالت", ["ثبت جدید", "ویرایش"], horizontal=True, key="app_mode_v3")

        selected_id = None
        selected_row = None

        if mode == "ویرایش":
            if apps.empty:
                st.info("متقاضی‌ای وجود ندارد.")
            else:
                label_map = {
                    int(r["id"]): f'#{int(r["id"])} - {normalize_text(r.get("full_name"))} ({normalize_text(r.get("phone"))})'
                    for _, r in apps.iterrows()
                }
                selected_id = st.selectbox(
                    "انتخاب متقاضی",
                    list(label_map.keys()),
                    format_func=lambda x: label_map.get(x, str(x)),
                    key="app_pick_v3",
                )
                selected_row = apps[apps["id"] == selected_id].iloc[0].to_dict()

        def val(key, default=""):
            if not selected_row:
                return default
            v = selected_row.get(key)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return default
            return v

        full_name = st.text_input("نام و نام خانوادگی", value=str(val("full_name", "")), key="app_fullname_v3")
        phone = st.text_input("شماره تماس", value=str(val("phone", "")), key="app_phone_v3")

        deal_type = st.selectbox(
            "نوع معامله",
            ["خرید و فروش", "رهن و اجاره"],
            index=0 if normalize_deal_type(val("deal_type", "خرید و فروش")) == "خرید و فروش" else 1,
            key="app_deal_v3",
        )
        desired_property_type = st.text_input("نوع ملک موردنظر (اختیاری)", value=str(val("desired_property_type", "")), key="app_ptype_v3")
        region = st.text_input("منطقه (اختیاری)", value=str(val("region", "")), key="app_region_v3")

        b1, b2 = st.columns(2)
        with b1:
            budget_min = st.number_input(
                "بودجه از (میلیون)",
                min_value=0.0,
                value=float(val("budget_min_million", 0.0) or 0.0),
                step=50.0,
                key="app_bmin_v3"
            )
        with b2:
            budget_max = st.number_input(
                "بودجه تا (میلیون) (0 یعنی نامحدود)",
                min_value=0.0,
                value=float(val("budget_max_million", 0.0) or 0.0),
                step=50.0,
                key="app_bmax_v3"
            )

        bedrooms_min = st.number_input(
            "حداقل خواب (اختیاری)",
            min_value=0,
            value=int(val("bedrooms_min", 0) or 0),
            step=1,
            key="app_bedmin_v3"
        )
        notes = st.text_area("توضیحات", value=str(val("notes", "")), key="app_notes_v3")

        cA, cB, cC = st.columns([1, 1, 2])

        if mode == "ثبت جدید":
            if cA.button("ثبت متقاضی", key="app_add_btn_v3"):
                if not full_name.strip():
                    st.error("نام متقاضی را وارد کنید.")
                else:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            insert into applicants
                              (full_name, phone, deal_type, desired_property_type, region,
                               budget_min_million, budget_max_million, bedrooms_min, notes, created_at, updated_at)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), now())
                            """,
                            (
                                normalize_text(full_name),
                                normalize_text(phone),
                                normalize_deal_type(deal_type),
                                normalize_text(desired_property_type),
                                normalize_text(region),
                                float(budget_min) if budget_min else 0.0,
                                float(budget_max) if budget_max else 0.0,
                                int(bedrooms_min) if bedrooms_min else 0,
                                normalize_text(notes),
                            )
                        )
                    st.success("متقاضی ثبت شد.")
                    st.rerun()
        else:
            if selected_id is not None and cA.button("ذخیره تغییرات", key="app_save_btn_v3"):
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        update applicants set
                          full_name=%s,
                          phone=%s,
                          deal_type=%s,
                          desired_property_type=%s,
                          region=%s,
                          budget_min_million=%s,
                          budget_max_million=%s,
                          bedrooms_min=%s,
                          notes=%s,
                          updated_at=now()
                        where id=%s
                        """,
                        (
                            normalize_text(full_name),
                            normalize_text(phone),
                            normalize_deal_type(deal_type),
                            normalize_text(desired_property_type),
                            normalize_text(region),
                            float(budget_min) if budget_min else 0.0,
                            float(budget_max) if budget_max else 0.0,
                            int(bedrooms_min) if bedrooms_min else 0,
                            normalize_text(notes),
                            int(selected_id),
                        )
                    )
                st.success("ویرایش ذخیره شد.")
                st.rerun()

            if selected_id is not None and cB.button("حذف متقاضی", key="app_del_btn_v3"):
                with conn.cursor() as cur:
                    cur.execute("delete from applicants where id=%s", (int(selected_id),))
                st.success("حذف شد.")
                st.rerun()

    # --- Right: list + match
    with right:
        st.markdown("### لیست متقاضیان (نمایش درست میلیارد/تومان)")

        if apps.empty:
            st.info("هنوز متقاضی ثبت نشده است.")
        else:
            view = apps.copy()
            view["بودجه از (میلیارد)"] = view["budget_min_million"].apply(billion_str_from_million)
            view["بودجه تا (میلیارد)"] = view["budget_max_million"].apply(billion_str_from_million)
            view["بودجه از (تومان)"] = view["budget_min_million"].apply(toman_str_from_million)
            view["بودجه تا (تومان)"] = view["budget_max_million"].apply(toman_str_from_million)

            show_cols = [
                "id", "full_name", "phone", "deal_type", "desired_property_type", "region",
                "budget_min_million", "budget_max_million", "بودجه از (میلیارد)", "بودجه تا (میلیارد)",
                "bedrooms_min", "updated_at"
            ]
            st.dataframe(view[show_cols], use_container_width=True)

        st.divider()
        st.markdown("### مچ متقاضی با فایل‌ها (FIXED)")

        if apps.empty:
            return

        label_map2 = {
            int(r["id"]): f'#{int(r["id"])} - {normalize_text(r.get("full_name"))} ({normalize_text(r.get("phone"))})'
            for _, r in apps.iterrows()
        }
        mid = st.selectbox(
            "انتخاب متقاضی برای مچ",
            list(label_map2.keys()),
            format_func=lambda x: label_map2.get(x, str(x)),
            key="match_pick_v3"
        )
        mr = apps[apps["id"] == mid].iloc[0].to_dict()

        debug = st.checkbox("دیباگ مچ (نمایش علت صفر شدن)", value=False, key="match_debug_v3")

        where = ["1=1"]
        params = []

        # deal type (normalized + trim/lower)
        dt = normalize_deal_type(mr.get("deal_type"))
        if dt:
            where.append("lower(trim(deal_type)) = lower(trim(%s))")
            params.append(dt)

        # property type (contains)
        dpt = normalize_text(mr.get("desired_property_type"))
        if dpt:
            where.append("trim(property_type) ILIKE %s")
            params.append(f"%{dpt}%")

        # region (contains)
        reg = normalize_text(mr.get("region"))
        if reg:
            where.append("trim(region) ILIKE %s")
            params.append(f"%{reg}%")

        # budgets (million), 0 => unlimited
        def _f(x):
            try:
                return float(x) if x is not None and not pd.isna(x) else 0.0
            except Exception:
                return 0.0

        bmin = _f(mr.get("budget_min_million"))
        bmax = _f(mr.get("budget_max_million"))

        # Only apply price filters if user actually set budget
        if bmin > 0:
            where.append("price_million is not null and price_million >= %s")
            params.append(bmin)
        if bmax > 0:
            where.append("price_million is not null and price_million <= %s")
            params.append(bmax)

        # bedrooms (only if requested)
        bdm = int(_f(mr.get("bedrooms_min")))
        if bdm > 0:
            where.append("(bedrooms is not null and bedrooms >= %s)")
            params.append(bdm)

        limit = st.selectbox("حداکثر نتایج", [50, 100, 200, 500], index=1, key="match_limit_v3")

        q = f"""
            select file_code, deal_type, region, property_type, bedrooms, area_m2, price_million,
                   description, updated_at
            from properties
            where {" and ".join(where)}
            order by updated_at desc nulls last
            limit %s
        """

        if debug:
            st.code(q)
            st.write("params:", params)

        res = pd.read_sql_query(q, conn, params=tuple(params + [int(limit)]))

        if res.empty:
            st.warning("فایل مطابق پیدا نشد. (اگر دیباگ روشنه، کوئری/پارامترها رو ببین)")
            return

        res = res.copy()
        res["خواب"] = res.apply(bedrooms_display, axis=1)
        res["قیمت (میلیارد)"] = res["price_million"].apply(billion_str_from_million)
        res["قیمت (تومان)"] = res["price_million"].apply(toman_str_from_million)

        show = res.drop(columns=["price_million"]).rename(columns={
            "file_code": "کد فایل",
            "deal_type": "نوع معامله",
            "region": "منطقه",
            "property_type": "نوع ملک",
            "area_m2": "متراژ",
            "description": "توضیحات",
            "updated_at": "آپدیت"
        })

        st.dataframe(show, use_container_width=True)


# =========================
# Tabs
# =========================
if is_admin:
    t1, t2, t3, t4, t5 = st.tabs(["لیست فایل‌ها", "آپلود/آپدیت", "ثبت/ویرایش فایل", "متقاضیان", "راهنما"])

    with t1:
        admin_files_list_tab()

    with t2:
        admin_upload_tab()

    with t3:
        admin_add_edit_property_tab()

    with t4:
        applicants_tab()

    with t5:
        st.write("قیمت‌ها بر حسب میلیون ذخیره می‌شوند. مثال: ۵ میلیارد = ۵۰۰۰")

else:
    t1, t2, t3 = st.tabs(["فایل‌ها", "جستجو", "راهنما"])

    with t1:
        client_files_tab()

    with t2:
        st.subheader("جستجو (سریع)")
        st.info("برای جستجوی دقیق، از تب فایل‌ها استفاده کن. (فیلترهای کامل آنجاست.)")

    with t3:
        st.write("قیمت‌ها بر حسب میلیون هستند. مثال: ۵ میلیارد = ۵۰۰۰")
