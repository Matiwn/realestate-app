import os
import re
from datetime import datetime
from supabase import create_client
import uuid
import pandas as pd
import psycopg2
import streamlit as st


# =========================
# Streamlit config (MUST be first st.*)
# =========================
st.set_page_config(page_title="مشاور املاک نور", layout="wide")


# =========================
# ENV
# =========================
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")
CLIENT_PASSWORD = os.environ.get("CLIENT_PASSWORD", "1234")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)
NOOR_LOGO_URL = "https://tpjkzusrrkwppbhsmsno.supabase.co/storage/v1/object/public/logos/noor.png"


# =========================
# VIP Theme
# =========================
def apply_noor_theme():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;600;700;800;900&display=swap');

        :root{
          --bg:#1B1F27;         /* dark gray */
          --surface:#171A20;
          --card:#1B1F27;
          --border:#2B3140;

          --gold:#D4AF37;
          --gold2:#B9922B;

          --text:#E7EAF2;
          --muted:#B8BED0;
          --muted2:#8D94AA;

          --shadow: 0 10px 30px rgba(0,0,0,0.35);
          --shadow2: 0 12px 34px rgba(0,0,0,0.45);
        }

        /* Global */
        html, body, [class*="css"], .stApp{
          direction: rtl !important;
          text-align: right !important;
          font-family: "Vazirmatn", system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif !important;
          color: var(--text) !important;
          background: var(--bg) !important;
          font-size: 17px !important;
        }
        .stApp{ background: var(--bg) !important; }

        /* Fix white header area */
        header{ background: var(--bg) !important; }
        .main{ background: var(--bg) !important; }

        /* Container padding */
        .block-container{
          padding-top: 1.0rem !important;
          padding-bottom: 2.2rem !important;
        }

        /* Sidebar */
        section[data-testid="stSidebar"]{
          background: linear-gradient(180deg, #141721 0%, #10131a 100%) !important;
          border-right:1px solid var(--border);
        }
        section[data-testid="stSidebar"] *{
          color: var(--text) !important;
          font-size: 15px !important;
        }

        /* Labels */
        label{
          color: var(--gold2) !important;   /* طلایی تیره */
          font-weight: 900 !important;
          font-size: 15px !important;
        }
        .stCaption, .stCaption *{
          color: var(--muted2) !important;
          font-size: 13px !important;
        }

        /* Tabs */
        button[data-baseweb="tab"]{
          color: var(--muted) !important;
          border-radius: 999px !important;
          background: transparent !important;
          border: 1px solid transparent !important;
          font-weight: 900 !important;
          padding: 10px 14px !important;
        }
        button[data-baseweb="tab"][aria-selected="true"]{
          color: #111 !important;
          background: linear-gradient(135deg, rgba(212,175,55,0.95), rgba(185,146,43,0.95)) !important;
          border: 1px solid rgba(212,175,55,0.35) !important;
          box-shadow: 0 8px 20px rgba(212,175,55,0.18) !important;
        }

        /* Buttons */
        .stButton>button{
          background: linear-gradient(135deg, var(--gold), var(--gold2)) !important;
          color: #111 !important;
          border: 0 !important;
          border-radius: 16px !important;
          font-weight: 950 !important;
          padding: 0.85rem 1.1rem !important;
          font-size: 16px !important;
          box-shadow: 0 12px 28px rgba(212,175,55,0.14) !important;
          transition: transform .12s ease, box-shadow .12s ease, opacity .12s ease;
        }
        .stButton>button:hover{
          transform: translateY(-1px);
          box-shadow: 0 16px 34px rgba(212,175,55,0.20) !important;
          opacity: 0.98;
        }

        /* Inputs */
        .stTextInput input, .stNumberInput input, .stTextArea textarea{
          background: rgba(27,31,39,0.92) !important;
          color: #FFFFFF !important;
          border: 1px solid rgba(43,49,64,0.95) !important;
          border-radius: 16px !important;
          padding: 12px 14px !important;
          font-size: 16px !important;
          box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
        }
        .stTextInput input::placeholder, .stTextArea textarea::placeholder{
          color: var(--muted2) !important;
          opacity: 1 !important;
        }

        /* Select (control dark) */
        [data-baseweb="select"] > div{
          background: rgba(27,31,39,0.92) !important;
          border: 1px solid rgba(43,49,64,0.95) !important;
          border-radius: 16px !important;
          box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
        }
        [data-baseweb="select"] span, [data-baseweb="select"] input{
          color: #FFFFFF !important;
          font-size: 16px !important;
          caret-color: var(--gold) !important;
        }

        /* Dropdown list WHITE + black text (your request) */
        ul[role="listbox"]{
          background: #FFFFFF !important;
          border: 1px solid rgba(43,49,64,0.35) !important;
          border-radius: 16px !important;
          overflow: hidden !important;
          box-shadow: var(--shadow2) !important;
        }
        li[role="option"]{
          color: #111111 !important;
          font-size: 16px !important;
          font-weight: 800 !important;
        }
        li[role="option"]:hover{
          background: #F2F2F2 !important;
          color: #111111 !important;
        }

        /* Multiselect tags */
        [data-baseweb="tag"]{
          background: rgba(212,175,55,0.16) !important;
          border: 1px solid rgba(212,175,55,0.40) !important;
          color: var(--gold2) !important;
          font-weight: 950 !important;
          border-radius: 999px !important;
        }

        /* Dataframe */
        .stDataFrame{
          background: rgba(27,31,39,0.75) !important;
          border: 1px solid rgba(43,49,64,0.95) !important;
          border-radius: 18px !important;
          padding: 8px !important;
          box-shadow: var(--shadow) !important;
        }

        /* Card (for client list) */
        .noor-card{
          background: linear-gradient(180deg, rgba(27,31,39,0.92), rgba(20,24,36,0.92));
          border: 1px solid rgba(43,49,64,0.95);
          border-radius: 22px;
          padding: 16px;
          margin-bottom: 14px;
          box-shadow: var(--shadow);
          backdrop-filter: blur(8px);
        }
        .noor-card-top{
          display:flex;
          justify-content: space-between;
          align-items: baseline;
          gap: 10px;
          margin-bottom: 10px;
        }
        .noor-badge{
          display:inline-block;
          padding: 6px 12px;
          border-radius: 999px;
          background: rgba(212,175,55,0.14);
          border: 1px solid rgba(212,175,55,0.40);
          color: var(--gold2) !important;
          font-weight: 950;
          font-size: 13px;
          white-space: nowrap;
        }
        .noor-code{
          color: var(--muted2) !important;
          font-weight: 800;
          font-size: 13px;
          margin-top: 4px;
        }
        .noor-divider{
          height: 1px;
          background: rgba(43,49,64,0.9);
          margin: 12px 0;
        }
        .noor-desc{
          color: var(--text) !important;
          opacity: .92;
          font-size: 15px;
          line-height: 1.95;
        }

        /* VIP Title */
        .noor-vip-section{ margin-top: 18px; margin-bottom: 10px; }
        .noor-vip-title{
          font-size: 28px;
          font-weight: 950;
          background: linear-gradient(90deg,#D4AF37,#FFE07A,#B8962E);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          text-shadow: 0 0 12px rgba(212,175,55,0.12);
        }
        .noor-vip-line{
          width: 64px;
          height: 4px;
          margin-top: 7px;
          border-radius: 10px;
          background: linear-gradient(90deg,#D4AF37,#FFE07A);
          box-shadow: 0 0 12px rgba(212,175,55,0.35);
        }

        /* VIP Logo */
        .noor-vip-wrap{
          display:flex;
          flex-direction:column;
          align-items:center;
          justify-content:center;
          margin: 10px 0 18px 0;
        }
        .noor-vip-card{
          width: 210px;
          height: 210px;
          border-radius: 34px;
          padding: 18px;
          background: linear-gradient(180deg, rgba(32,37,50,0.75), rgba(20,24,33,0.85));
          border: 1px solid rgba(212,175,55,0.30);
          box-shadow:
            0 0 0 1px rgba(255,255,255,0.04) inset,
            0 18px 45px rgba(0,0,0,0.55),
            0 0 35px rgba(212,175,55,0.22);
          backdrop-filter: blur(10px);
          display:flex;
          align-items:center;
          justify-content:center;
        }
        .noor-vip-card img{
          width: 160px;
          height: 160px;
          border-radius: 26px;
          object-fit: cover;
          box-shadow: 0 10px 30px rgba(0,0,0,0.55);
        }
        .noor-vip-header-title{
          margin-top: 12px;
          font-size: 34px;
          font-weight: 950;
          line-height: 1.2;
          background: linear-gradient(90deg, #D4AF37, #FFE07A, #B9922B);
          -webkit-background-clip:text;
          -webkit-text-fill-color:transparent;
        }
        .noor-vip-sub{
          margin-top: 6px;
          color: rgba(231,234,242,0.75);
          font-size: 15px;
          font-weight: 700;
        }

        @media (max-width: 640px){
          .block-container{ padding-left: 0.9rem !important; padding-right: 0.9rem !important; }
          .noor-vip-card{ width: 190px; height: 190px; }
          .noor-vip-card img{ width: 145px; height: 145px; }
          .noor-vip-header-title{ font-size: 28px; }
        }
/* ===== FIX SLIDER (RTL overflow) ===== */

/* make slider block full width + prevent overflow */
div[data-testid="stSlider"]{
  direction: ltr !important;           /* important: slider must be LTR */
  text-align: left !important;
  width: 100% !important;
}

div[data-testid="stSlider"] > div{
  width: 100% !important;
  overflow: visible !important;        /* allow handles show correctly */
}

/* give a little horizontal padding so handles don't go خارج کادر */
div[data-testid="stSlider"] .stSlider{
  padding-left: 10px !important;
  padding-right: 10px !important;
}

/* slider labels stay readable in RTL page */
div[data-testid="stSlider"] label{
  direction: rtl !important;
  text-align: right !important;
}
        </style>
        """,
        unsafe_allow_html=True
    )


apply_noor_theme()


def show_vip_logo():
    st.markdown(
        f"""
        <div class="noor-vip-wrap">
          <div class="noor-vip-card">
            <img src="{NOOR_LOGO_URL}" alt="Noor Logo" />
          </div>
          <div class="noor-vip-header-title">مشاور املاک نور</div>
          <div class="noor-vip-sub">سیستم مدیریت فایل‌ها و متقاضیان</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def vip_title(text: str):
    st.markdown(
        f"""
        <div class="noor-vip-section">
          <div class="noor-vip-title">{text}</div>
          <div class="noor-vip-line"></div>
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================
# Helpers
# =========================
def normalize_text(x) -> str:
    if x is None:
        return ""
    return str(x).replace("\u200c", "").replace("‌", "").strip()


def normalize_deal_type(x) -> str:
    s = normalize_text(x)
    if not s:
        return ""
    if "رهن" in s or "اجاره" in s:
        return "رهن و اجاره"
    if "خرید" in s or "فروش" in s:
        return "خرید و فروش"
    return s


def now_utc():
    return datetime.utcnow()


def parse_price_million(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)

    s = normalize_text(v).replace(",", "").replace("٬", "").replace(" ", "")
    if not s:
        return None

    m = re.search(r"(\d+(\.\d+)?)میلیارد", s)
    if m:
        return float(m.group(1)) * 1000.0

    m = re.search(r"(\d+(\.\d+)?)میلیون", s)
    if m:
        return float(m.group(1))

    m = re.search(r"(\d+(\.\d+)?)", s)
    if m:
        raw = float(m.group(1))
        if raw >= 1_000_000:
            return raw / 1_000_000.0
        return raw

    return None


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


NO_BEDROOM_KEYWORDS = ["زمین", "اداری", "تجاری", "مغازه", "سوله", "انبار", "کارگاه"]


def bedrooms_display(row: dict) -> str:
    ptype = normalize_text(row.get("property_type", ""))
    if any(k in ptype for k in NO_BEDROOM_KEYWORDS):
        return ""
    b = row.get("bedrooms")
    if b is None or (isinstance(b, float) and pd.isna(b)):
        return ""
    try:
        bi = int(float(str(b)))
        return "" if bi <= 0 else str(bi)
    except Exception:
        return ""


# =========================
# DB
# =========================
@st.cache_resource
def _make_conn():
    if not DATABASE_URL:
        st.error("DATABASE_URL تنظیم نشده است.")
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
        cur.execute("""
        create table if not exists uploads (
          id bigserial primary key,
          uploaded_at timestamp,
          rows_read integer,
          rows_upserted integer
        );
        """)
        # ensure columns
        cur.execute("alter table properties add column if not exists bedrooms integer;")
        cur.execute("alter table properties add column if not exists description text;")
        cur.execute("alter table applicants add column if not exists notes text;")
        cur.execute("alter table applicants add column if not exists bedrooms_min integer;")
        cur.execute("alter table applicants add column if not exists budget_min_million numeric;")
        cur.execute("alter table applicants add column if not exists budget_max_million numeric;")


@st.cache_data(ttl=180)
def fetch_filter_values(_dsn: str):
    conn = get_conn_safe()
    r1 = pd.read_sql_query(
        "select distinct trim(region) as v from properties where region is not null and trim(region) <> '' order by v",
        conn
    )
    r2 = pd.read_sql_query(
        "select distinct trim(property_type) as v from properties where property_type is not null and trim(property_type) <> '' order by v",
        conn
    )
    regions = [normalize_text(x) for x in r1["v"].tolist() if normalize_text(x)]
    ptypes = [normalize_text(x) for x in r2["v"].tolist() if normalize_text(x)]
    return regions, ptypes


@st.cache_data(ttl=180)
def fetch_minmax_prices(_dsn: str):
    conn = get_conn_safe()
    df = pd.read_sql_query("select min(price_million) as mn, max(price_million) as mx from properties", conn)
    mn = df.loc[0, "mn"]
    mx = df.loc[0, "mx"]
    mn = 0.0 if mn is None or (isinstance(mn, float) and pd.isna(mn)) else float(mn)
    mx = 0.0 if mx is None or (isinstance(mx, float) and pd.isna(mx)) else float(mx)
    return mn, mx


@st.cache_data(ttl=60)
def count_properties(where_sql: str, params: tuple):
    conn = get_conn_safe()
    q = f"select count(*) as c from properties where {where_sql}"
    df = pd.read_sql_query(q, conn, params=params)
    return int(df.iloc[0]["c"])


def clear_caches():
    try:
        fetch_filter_values.clear()
        fetch_minmax_prices.clear()
        count_properties.clear()
    except Exception:
        pass


# =========================
# Auth
# =========================
if "role" not in st.session_state:
    st.session_state.role = None

with st.sidebar:
    st.header("ورود")
    role_ui = st.selectbox("نقش", ["مشتری", "مدیر"], key="login_role")
    pwd = st.text_input("رمز", type="password", key="login_pwd")

    c1, c2 = st.columns(2)
    if c1.button("ورود", key="login_btn"):
        if role_ui == "مدیر" and pwd == ADMIN_PASSWORD:
            st.session_state.role = "admin"
            st.success("ورود مدیر موفق بود.")
        elif role_ui == "مشتری" and pwd == CLIENT_PASSWORD:
            st.session_state.role = "client"
            st.success("ورود مشتری موفق بود.")
        else:
            st.error("رمز اشتباه است.")
    if c2.button("خروج", key="logout_btn"):
        st.session_state.role = None
        st.info("خارج شدید.")

if st.session_state.role is None:
    show_vip_logo()
    st.warning("برای استفاده از برنامه، از نوار کناری وارد شوید.")
    st.stop()

is_admin = st.session_state.role == "admin"


# =========================
# Init DB
# =========================
conn = get_conn_safe()
ensure_tables(conn)

show_vip_logo()


# =========================
# Excel upload helpers
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

    find_col("price_total", lambda n: ("قیمتکل" in n) or (("قیمت" in n) and ("کل" in n)))
    if "price_total" not in col_map:
        price_like = [c for c in cols if "قیمت" in cols_norm[c]]
        if len(price_like) == 1:
            col_map["price_total"] = price_like[0]

    find_col("owner_name", lambda n: ("مالک" in n) and (("نام" in n) or ("اسم" in n)))
    find_col("owner_phone", lambda n: (("تماس" in n and "مالک" in n) or ("شماره" in n and "مالک" in n) or ("موبایل" in n and "مالک" in n)))
    find_col("internal_notes", lambda n: ("یادداشت" in n) or ("داخلی" in n) or ("نکته" in n))

    required = ["file_code", "deal_type", "region", "property_type", "area_m2", "price_total"]
    missing = [k for k in required if k not in col_map]
    if missing:
        st.error("ستون‌های لازم پیدا نشد: " + "، ".join(missing))
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
                normalize_text(r["file_code"]),
                normalize_deal_type(r["deal_type"]),
                normalize_text(r["region"]),
                normalize_text(r["address"]),
                None if pd.isna(r["area_m2"]) else float(r["area_m2"]),
                None if r["price_million"] is None or (isinstance(r["price_million"], float) and pd.isna(r["price_million"])) else float(r["price_million"]),
                normalize_text(r["property_type"]),
                None if r.get("bedrooms") is None or (isinstance(r.get("bedrooms"), float) and pd.isna(r.get("bedrooms"))) else int(float(r.get("bedrooms"))),
                normalize_text(r.get("description", "")),
                normalize_text(r.get("owner_name", "")),
                normalize_text(r.get("owner_phone", "")),
                normalize_text(r.get("internal_notes", "")),
            ))
            rows += 1
    return rows


# =========================
# Client UI
# =========================
def client_property_detail(code: str):
    code = normalize_text(code)
    df = pd.read_sql_query(
        """
        select file_code, deal_type, region, property_type, bedrooms, area_m2, price_million,
               address, description, updated_at
        from properties
        where file_code=%s
        """,
        conn,
        params=(code,),
    )
    if df.empty:
        st.error("این فایل پیدا نشد.")
        if st.button("بازگشت", key="cl_back_missing"):
            st.session_state.client_selected_file = None
            st.rerun()
        return

    r = df.iloc[0].to_dict()

    if st.button("⬅ بازگشت به لیست فایل‌ها", key="cl_back_to_list"):
        st.session_state.client_selected_file = None
        st.rerun()

    price_m = r.get("price_million")
    ptype = normalize_text(r.get("property_type"))
    deal = normalize_text(r.get("deal_type"))
    region = normalize_text(r.get("region"))
    address = normalize_text(r.get("address"))
    desc = normalize_text(r.get("description"))
    area = r.get("area_m2")
    bed = bedrooms_display(r)

    area_str = ""
    try:
        if area is not None and not (isinstance(area, float) and pd.isna(area)):
            area_str = f"{float(area):.0f} متر"
    except Exception:
        area_str = ""

    st.markdown("<div class='noor-card'>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="noor-card-top">
          <div>
            <div class="noor-badge">{ptype or "ملک"}</div>
            <div class="noor-code">کد فایل: {code}</div>
          </div>
          <div style="text-align:left">
            <div style="font-size:22px; font-weight:950; color:var(--gold);">{billion_str_from_million(price_m)}</div>
            <div style="font-size:12px; color:var(--muted2);">{toman_str_from_million(price_m)}</div>
          </div>
        </div>

        <div style="color:var(--muted); font-size:14px;">
          <b style="color:var(--text);">{deal}</b>
          {" • " + region if region else ""}
        </div>

        <div class="noor-divider"></div>

        <div style="display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:10px;">
          <div style="border:1px solid rgba(43,49,64,0.95); border-radius:16px; padding:10px 12px; background:rgba(255,255,255,0.03);">
            <div style="color:var(--muted2); font-size:12px;">منطقه</div>
            <div style="font-weight:950; font-size:15px;">{region or "—"}</div>
          </div>
          <div style="border:1px solid rgba(43,49,64,0.95); border-radius:16px; padding:10px 12px; background:rgba(255,255,255,0.03);">
            <div style="color:var(--muted2); font-size:12px;">متراژ</div>
            <div style="font-weight:950; font-size:15px;">{area_str or "—"}</div>
          </div>
          <div style="border:1px solid rgba(43,49,64,0.95); border-radius:16px; padding:10px 12px; background:rgba(255,255,255,0.03);">
            <div style="color:var(--muted2); font-size:12px;">خواب</div>
            <div style="font-weight:950; font-size:15px;">{(bed + " خواب") if bed else "—"}</div>
          </div>
        </div>

        <div class="noor-desc" style="margin-top:12px;"><b style="color:var(--gold2);">آدرس:</b> {address or "—"}</div>
        <div class="noor-desc"><b style="color:var(--gold2);">توضیحات:</b> {desc or "—"}</div>
        """,
        unsafe_allow_html=True
    )

    st.text_input("کپی کد فایل", value=code, key="cl_copy_code", help="روی متن کلیک کن و Copy بزن")

    st.markdown("</div>", unsafe_allow_html=True)


def client_files_tab():
    vip_title("فایل‌ها")

    if "client_selected_file" not in st.session_state:
        st.session_state.client_selected_file = None

    if st.session_state.client_selected_file:
        client_property_detail(st.session_state.client_selected_file)
        return

    mn, mx = fetch_minmax_prices(DATABASE_URL)
    if mx <= 0:
        mx = 10000.0

    regions, ptypes = fetch_filter_values(DATABASE_URL)

    vip_title("جستجوی سریع")

    c1, c2, c3, c4 = st.columns([1.4, 1, 1, 0.8])
    with c1:
        q = st.text_input("عبارت جستجو", placeholder="مثلاً: کد فایل، منطقه، نوع ملک، توضیحات…", key="cl_q")
    with c2:
        deal = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], key="cl_deal")
    with c3:
        sort = st.selectbox("مرتب‌سازی", ["جدیدترین", "ارزان‌ترین", "گران‌ترین"], key="cl_sort")
    with c4:
        page_size = st.selectbox("تعداد در صفحه", [10, 20, 30, 50], index=1, key="cl_pagesize")

    r1, r2 = st.columns([1, 1])
    with r1:
        sel_regions = st.multiselect("فیلتر منطقه (چند انتخابی)", options=regions, default=[], key="cl_ms_region")
    with r2:
        sel_ptypes = st.multiselect("فیلتر نوع ملک (چند انتخابی)", options=ptypes, default=[], key="cl_ms_ptype")

    price_rng = st.slider(
        "بازه قیمت (میلیون) — ۵ میلیارد = ۵۰۰۰",
        min_value=float(mn),
        max_value=float(mx),
        value=(float(mn), float(mx)),
        step=50.0,
        key="cl_price_rng"
    )

    where = ["1=1"]
    params = []

    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(file_code ILIKE %s OR region ILIKE %s OR property_type ILIKE %s OR description ILIKE %s)")
        params += [like, like, like, like]

    if deal != "همه":
        where.append("lower(trim(deal_type)) = lower(trim(%s))")
        params.append(deal)

    if sel_regions:
        where.append("lower(trim(region)) = any(%s)")
        params.append([normalize_text(x).lower() for x in sel_regions])

    if sel_ptypes:
        where.append("lower(trim(property_type)) = any(%s)")
        params.append([normalize_text(x).lower() for x in sel_ptypes])

    where.append("price_million is not null and price_million between %s and %s")
    params += [float(price_rng[0]), float(price_rng[1])]

    where_sql = " and ".join(where)
    params_t = tuple(params)

    total = count_properties(where_sql, params_t)
    if total <= 0:
        st.info("نتیجه‌ای پیدا نشد.")
        return

    total_pages = max(1, (total + page_size - 1) // page_size)

    pc1, pc2, pc3 = st.columns([1, 1, 2])
    with pc1:
        page = st.number_input("صفحه", min_value=1, max_value=total_pages, value=1, step=1, key="cl_page")
    with pc2:
        st.caption(f"نتیجه: {total} فایل")
    with pc3:
        st.caption(f"صفحه {page} از {total_pages}")

    offset = (page - 1) * page_size

    order = "updated_at desc nulls last"
    if sort == "ارزان‌ترین":
        order = "price_million asc nulls last"
    elif sort == "گران‌ترین":
        order = "price_million desc nulls last"

    df = pd.read_sql_query(
        f"""
        select file_code, deal_type, region, property_type, bedrooms, area_m2, price_million, description, updated_at
        from properties
        where {where_sql}
        order by {order}
        limit %s offset %s
        """,
        conn,
        params=tuple(params + [int(page_size), int(offset)])
    )

    for _, r in df.iterrows():
        code = normalize_text(r.get("file_code"))
        deal_t = normalize_text(r.get("deal_type"))
        region = normalize_text(r.get("region"))
        ptype = normalize_text(r.get("property_type"))
        area = r.get("area_m2")
        bed = bedrooms_display(r.to_dict())
        price_m = r.get("price_million")
        desc = normalize_text(r.get("description"))

        area_str = ""
        try:
            if area is not None and not (isinstance(area, float) and pd.isna(area)):
                area_str = f"{float(area):.0f} متر"
        except Exception:
            area_str = ""

        bed_str = f"{bed} خواب" if bed else ""
        meta_right = " • ".join([x for x in [region, area_str, bed_str] if x])

        st.markdown(
            f"""
            <div class="noor-card">
              <div class="noor-card-top">
                <div>
                  <div class="noor-badge">{ptype or "ملک"}</div>
                  <div class="noor-code">کد فایل: {code}</div>
                </div>
                <div style="text-align:left">
                  <div style="font-size:18px; font-weight:950; color:var(--gold);">{billion_str_from_million(price_m)}</div>
                  <div style="font-size:12px; color:var(--muted2);">{toman_str_from_million(price_m)}</div>
                </div>
              </div>

              <div style="color:var(--muted); font-size:14px;">
                <b style="color:var(--text);">{deal_t}</b>
                {" • " + meta_right if meta_right else ""}
              </div>

              <div class="noor-divider"></div>
              <div class="noor-desc">{desc if desc else "—"}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("مشاهده جزئیات", key=f"cl_view_{code}"):
            st.session_state.client_selected_file = code
            st.rerun()


# =========================
# Admin UI
# =========================
def admin_files_list_tab():
    vip_title("لیست فایل‌ها (مدیر)")

    regions, ptypes = fetch_filter_values(DATABASE_URL)

    c1, c2, c3 = st.columns([1.3, 1, 0.8])
    with c1:
        q = st.text_input("جستجوی سریع", placeholder="کد فایل / منطقه / نوع ملک ...", key="ad_q")
    with c2:
        deal = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], key="ad_deal")
    with c3:
        limit = st.selectbox("تعداد نمایش", [50, 100, 200, 500], index=1, key="ad_limit")

    r1, r2 = st.columns([1, 1])
    with r1:
        sel_regions = st.multiselect("فیلتر منطقه (چند انتخابی)", options=regions, default=[], key="ad_ms_region")
    with r2:
        sel_ptypes = st.multiselect("فیلتر نوع ملک (چند انتخابی)", options=ptypes, default=[], key="ad_ms_ptype")

    where = ["1=1"]
    params = []

    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(file_code ILIKE %s OR region ILIKE %s OR property_type ILIKE %s)")
        params += [like, like, like]

    if deal != "همه":
        where.append("lower(trim(deal_type)) = lower(trim(%s))")
        params.append(deal)

    if sel_regions:
        where.append("lower(trim(region)) = any(%s)")
        params.append([normalize_text(x).lower() for x in sel_regions])

    if sel_ptypes:
        where.append("lower(trim(property_type)) = any(%s)")
        params.append([normalize_text(x).lower() for x in sel_ptypes])

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
    df["خواب"] = df.apply(lambda r: bedrooms_display(r.to_dict()), axis=1)
    df["قیمت (میلیارد)"] = df["price_million"].apply(billion_str_from_million)
    df["قیمت (تومان)"] = df["price_million"].apply(toman_str_from_million)

    # remove raw to avoid duplicates
    for c in ["bedrooms", "price_million"]:
        if c in df.columns:
            df = df.drop(columns=[c])

    show = df.rename(columns={
        "file_code": "کد فایل",
        "deal_type": "نوع معامله",
        "property_type": "نوع ملک",
        "region": "منطقه",
        "area_m2": "متراژ",
        "owner_name": "مالک",
        "owner_phone": "شماره مالک",
        "description": "توضیحات",
        "updated_at": "آپدیت",
    })

    cols = ["کد فایل", "نوع معامله", "نوع ملک", "منطقه", "متراژ", "خواب", "قیمت (میلیارد)", "قیمت (تومان)",
            "مالک", "شماره مالک", "توضیحات", "آپدیت"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)


def admin_add_edit_property_tab():
    vip_title("ثبت / ویرایش فایل (مدیر)")

    code_lookup = st.text_input("برای ویرایش/بررسی، کد فایل را وارد کن", key="prop_lookup").strip()
    existing = None
    if code_lookup:
        ex = pd.read_sql_query("select * from properties where file_code=%s", conn, params=(code_lookup,))
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

    with st.form("prop_form"):
        file_code = st.text_input("کد فایل", value=str(code_lookup or ""), key="prop_code")
        deal_type = st.selectbox(
            "نوع معامله",
            ["خرید و فروش", "رهن و اجاره"],
            index=0 if normalize_deal_type(exv("deal_type", "خرید و فروش")) == "خرید و فروش" else 1,
            key="prop_deal"
        )
        property_type = st.text_input("نوع ملک", value=str(exv("property_type", "")), key="prop_ptype")
        region = st.text_input("منطقه", value=str(exv("region", "")), key="prop_region")
        address = st.text_input("آدرس (اختیاری)", value=str(exv("address", "")), key="prop_addr")

        c1, c2, c3 = st.columns(3)
        with c1:
            area_m2 = st.number_input("متراژ", min_value=0.0, value=float(exv("area_m2", 0.0) or 0.0), step=1.0, key="prop_area")
        with c2:
            bedrooms = st.number_input("تعداد خواب (اگر ندارد 0 بزن)", min_value=0, value=int(exv("bedrooms", 0) or 0), step=1, key="prop_bed")
        with c3:
            price_million = st.number_input("قیمت کل (میلیون) — ۵ میلیارد = ۵۰۰۰", min_value=0.0, value=float(exv("price_million", 0.0) or 0.0), step=50.0, key="prop_price")

        description = st.text_area("توضیحات", value=str(exv("description", "")), key="prop_desc")
        owner_name = st.text_input("نام مالک (فقط مدیر)", value=str(exv("owner_name", "")), key="prop_owner")
        owner_phone = st.text_input("شماره مالک (فقط مدیر)", value=str(exv("owner_phone", "")), key="prop_owner_phone")
        internal_notes = st.text_area("یادداشت داخلی (فقط مدیر)", value=str(exv("internal_notes", "")), key="prop_notes")

        colA, colB, _ = st.columns([1, 1, 2])
        save_btn = colA.form_submit_button("ذخیره (Upsert)")
        del_btn = colB.form_submit_button("حذف فایل")

    if save_btn:
        if not file_code.strip():
            st.error("کد فایل الزامی است.")
            return

        ex2 = pd.read_sql_query("select file_code from properties where file_code=%s", conn, params=(file_code.strip(),))
        if not ex2.empty:
            st.warning("اخطار: این کد فایل تکراری است و با ذخیره، اطلاعات **جایگزین/آپدیت** می‌شود.")

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
                normalize_text(file_code),
                normalize_deal_type(deal_type),
                normalize_text(region),
                normalize_text(address),
                float(area_m2) if area_m2 else None,
                float(price_million) if price_million else None,
                normalize_text(property_type),
                int(bedrooms) if bedrooms else 0,
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


def admin_upload_tab():
    vip_title("آپلود / بروزرسانی اکسل (مدیر)")
    st.caption("قیمت‌ها بر حسب میلیون است: ۵ میلیارد = ۵۰۰۰")

    up = st.file_uploader("آپلود Excel", type=["xlsx"], key="adm_upload_excel")
    if up is None:
        return

    df = load_excel(up)
    st.write("پیش‌نمایش:", df.head(30))

    if st.button("بروزرسانی دیتابیس (Upsert)", key="adm_do_upsert"):
        n = upsert_properties(conn, df)
        with conn.cursor() as cur:
            cur.execute(
                "insert into uploads(uploaded_at, rows_read, rows_upserted) values (%s,%s,%s)",
                (now_utc(), int(len(df)), int(n))
            )
        clear_caches()
        st.success(f"انجام شد. {n} ردیف درج/آپدیت شد.")
        st.rerun()


# =========================
# Applicants (Admin)
# =========================
def applicants_match_query(app_row: dict) -> pd.DataFrame:
    where = ["1=1"]
    params = []

    deal = normalize_text(app_row.get("deal_type"))
    if deal:
        where.append("lower(trim(deal_type)) = lower(trim(%s))")
        params.append(deal)

    region = normalize_text(app_row.get("region"))
    if region:
        where.append("lower(trim(region)) = lower(trim(%s))")
        params.append(region)

    ptype = normalize_text(app_row.get("desired_property_type"))
    if ptype:
        where.append("lower(trim(property_type)) = lower(trim(%s))")
        params.append(ptype)

    bmin = app_row.get("budget_min_million")
    bmax = app_row.get("budget_max_million")
    if bmin is not None and not (isinstance(bmin, float) and pd.isna(bmin)):
        where.append("price_million is not null and price_million >= %s")
        params.append(float(bmin))
    if bmax is not None and not (isinstance(bmax, float) and pd.isna(bmax)):
        where.append("price_million is not null and price_million <= %s")
        params.append(float(bmax))

    bedmin = app_row.get("bedrooms_min")
    if bedmin is not None and not (isinstance(bedmin, float) and pd.isna(bedmin)):
        # only apply bedroom filter for properties that have bedrooms
        where.append("(bedrooms is null OR bedrooms >= %s)")
        params.append(int(bedmin))

    q = f"""
    select file_code, deal_type, region, property_type, bedrooms, area_m2, price_million, description, updated_at
    from properties
    where {" and ".join(where)}
    order by updated_at desc nulls last
    limit 80
    """
    return pd.read_sql_query(q, conn, params=tuple(params))


def applicants_tab():
    vip_title("متقاضیان (مدیر)")
    st.caption("ثبت متقاضی + لیست + مچ کردن با فایل‌ها بر اساس بودجه/نوع معامله/منطقه/نوع ملک")

    with st.expander("➕ ثبت متقاضی جدید", expanded=False):
        with st.form("app_form"):
            full_name = st.text_input("نام و نام خانوادگی", key="app_name")
            phone = st.text_input("شماره تماس", key="app_phone")
            deal_type = st.selectbox("نوع معامله", ["خرید و فروش", "رهن و اجاره"], key="app_deal")
            desired_property_type = st.text_input("نوع ملک مدنظر (اختیاری)", key="app_ptype")
            region = st.text_input("منطقه مدنظر (اختیاری)", key="app_region")

            c1, c2, c3 = st.columns(3)
            with c1:
                budget_min = st.number_input("حداقل بودجه (میلیون)", min_value=0.0, value=0.0, step=50.0, key="app_bmin")
            with c2:
                budget_max = st.number_input("حداکثر بودجه (میلیون)", min_value=0.0, value=5000.0, step=50.0, key="app_bmax")
            with c3:
                bedrooms_min = st.number_input("حداقل خواب (اختیاری)", min_value=0, value=0, step=1, key="app_bedmin")

            notes = st.text_area("توضیحات/نیازها", key="app_notes")

            save_app = st.form_submit_button("ثبت متقاضی")

        if save_app:
            with conn.cursor() as cur:
                cur.execute("""
                insert into applicants(full_name, phone, deal_type, desired_property_type, region,
                                       budget_min_million, budget_max_million, bedrooms_min,
                                       notes, created_at, updated_at)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), now())
                """, (
                    normalize_text(full_name),
                    normalize_text(phone),
                    normalize_deal_type(deal_type),
                    normalize_text(desired_property_type),
                    normalize_text(region),
                    float(budget_min) if budget_min else 0.0,
                    float(budget_max) if budget_max else None,
                    int(bedrooms_min) if bedrooms_min else 0,
                    normalize_text(notes),
                ))
            st.success("متقاضی ثبت شد.")
            st.rerun()

    apps = pd.read_sql_query(
        "select id, full_name, phone, deal_type, desired_property_type, region, budget_min_million, budget_max_million, bedrooms_min, notes, created_at "
        "from applicants order by created_at desc limit 200",
        conn
    )

    if apps.empty:
        st.info("هنوز متقاضی ثبت نشده است.")
        return

    st.dataframe(
        apps.rename(columns={
            "id": "ID",
            "full_name": "نام",
            "phone": "شماره",
            "deal_type": "نوع معامله",
            "desired_property_type": "نوع ملک",
            "region": "منطقه",
            "budget_min_million": "حداقل بودجه (میلیون)",
            "budget_max_million": "حداکثر بودجه (میلیون)",
            "bedrooms_min": "حداقل خواب",
            "notes": "توضیحات",
            "created_at": "تاریخ ثبت",
        }),
        use_container_width=True
    )
# ---------- Delete Applicant (VIP Modal) ----------

    st.divider()
    vip_title("حذف متقاضی")

    delete_id = st.selectbox(
        "انتخاب متقاضی برای حذف",
        apps["id"].tolist(),
        format_func=lambda x: f"{int(x)} - {apps.loc[apps['id']==x, 'full_name'].iloc[0]}",
        key="delete_applicant_select"
    )


    if st.button("حذف متقاضی", key="delete_applicant_btn"):

        @st.dialog("تایید حذف")
        def confirm_delete():

            st.warning("این عملیات غیرقابل بازگشت است")

            name = apps.loc[apps["id"]==delete_id,"full_name"].iloc[0]

            st.write(f"آیا از حذف «{name}» مطمئن هستید؟")

            col1,col2 = st.columns(2)

            if col1.button("بله حذف شود", key="confirm_delete_yes"):

                with conn.cursor() as cur:

                    cur.execute(
                        "delete from applicants where id=%s",
                        (int(delete_id),)
                    )

                st.success("متقاضی حذف شد")

                st.rerun()


            if col2.button("انصراف", key="confirm_delete_no"):

                st.rerun()


        confirm_delete()
    st.divider()
    vip_title("مچ کردن متقاضی با فایل‌ها")

    sel_id = st.selectbox(
        "انتخاب متقاضی برای مچ",
        options=apps["id"].tolist(),
        format_func=lambda x: f"{int(x)} - {apps.loc[apps['id']==x, 'full_name'].iloc[0]}",
        key="app_sel_id"
    )

    app_row = apps[apps["id"] == sel_id].iloc[0].to_dict()
    matches = applicants_match_query(app_row)

    if matches.empty:
        st.warning("فایل مطابق پیدا نشد.")
        return

    matches = matches.copy()
    matches["خواب"] = matches.apply(lambda r: bedrooms_display(r.to_dict()), axis=1)
    matches["قیمت (میلیارد)"] = matches["price_million"].apply(billion_str_from_million)
    matches["قیمت (تومان)"] = matches["price_million"].apply(toman_str_from_million)
    for c in ["price_million", "bedrooms"]:
        if c in matches.columns:
            matches = matches.drop(columns=[c])

    matches = matches.rename(columns={
        "file_code": "کد فایل",
        "deal_type": "نوع معامله",
        "region": "منطقه",
        "property_type": "نوع ملک",
        "area_m2": "متراژ",
        "description": "توضیحات",
        "updated_at": "آپدیت",
    })

    cols = ["کد فایل", "نوع معامله", "نوع ملک", "منطقه", "متراژ", "خواب", "قیمت (میلیارد)", "قیمت (تومان)", "توضیحات", "آپدیت"]
    cols = [c for c in cols if c in matches.columns]
    st.dataframe(matches[cols], use_container_width=True)


# =========================
# Main Tabs
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
        vip_title("راهنما")
        st.write("قیمت‌ها بر حسب **میلیون** هستند. مثال: **۵ میلیارد = ۵۰۰۰**")
else:
    t1, t2 = st.tabs(["فایل‌ها", "راهنما"])
    with t1:
        client_files_tab()
    with t2:
        vip_title("راهنما")
        st.write("قیمت‌ها بر حسب **میلیون** هستند. مثال: **۵ میلیارد = ۵۰۰۰**")


