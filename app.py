import os
import re
from datetime import datetime

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


# =========================
# Noor Theme + Logo
# =========================
NOOR_LOGO_URL = "https://tpjkzusrrkwppbhsmsno.supabase.co/storage/v1/object/public/logos/noor.png"

NOOR_PRIMARY = "#D4AF37"   # gold
NOOR_BG = "#0B0B0B"        # near black
NOOR_CARD = "#111111"
NOOR_TEXT = "#F2F2F2"
NOOR_MUTED = "#B8B8B8"
NOOR_BORDER = "#2A2A2A"
NOOR_SIDEBAR = "#0F0F0F"
NOOR_PILL = "rgba(212,175,55,0.14)"

def apply_noor_theme():
    st.markdown("""
    <style>

    @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;600;700;800;900&display=swap');

    :root{

        --bg:#151821;
        --card:#1E222D;
        --border:#2E3445;

        --gold:#D4AF37;

        --text:#E8EBF2;
        --muted:#AEB4C6;

    }

    /* GLOBAL */

    html, body, .stApp{

        background: var(--bg) !important;

        font-family: Vazirmatn !important;

        direction: rtl;

        color: var(--text);

    }


    /* FIX WHITE HEADER AREA */

    header{

        background: var(--bg) !important;

    }


    .main{

        background: var(--bg) !important;

    }


    section[data-testid="stSidebar"]{

        background: #131620 !important;

    }


    /* INPUT */

    input{

        background: var(--card) !important;

        color: white !important;

    }


    textarea{

        background: var(--card) !important;

        color: white !important;

    }


    /* SELECT BOX */

    [data-baseweb="select"]{

        background: var(--card) !important;

    }


    [data-baseweb="select"] > div{

        background: var(--card) !important;

        color: white !important;

    }


    /* DROPDOWN LIST FIX */

    ul[role="listbox"]{

        background: white !important;

    }


    li[role="option"]{

        color: black !important;

        font-weight: 600;

    }


    li[role="option"]:hover{

        background: #f0f0f0 !important;

        color: black !important;

    }


    /* MULTISELECT TAG */

    [data-baseweb="tag"]{

        background: rgba(212,175,55,0.2) !important;

        color: var(--gold) !important;

        border: 1px solid var(--gold);

    }


    /* BUTTON */

    .stButton button{

        background: linear-gradient(135deg,#D4AF37,#B8962E);

        color:black;

        font-weight:900;

        border-radius:12px;

    }

/* VIP Logo Header */
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

.noor-vip-title{
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
    </style>
    """, unsafe_allow_html=True)


apply_noor_theme()

def show_vip_logo():
    logo = "https://tpjkzusrrkwppbhsmsno.supabase.co/storage/v1/object/public/logos/noor.png"
    st.markdown(
        f"""
        <div class="noor-vip-wrap">
          <div class="noor-vip-card">
            <img src="{logo}" alt="Noor Logo" />
          </div>
          <div class="noor-vip-title">مشاور املاک نور</div>
          <div class="noor-vip-sub">سیستم مدیریت فایل‌ها و متقاضیان</div>
        </div>
        """,
        unsafe_allow_html=True
    )

show_vip_logo()

show_noor_header()


# =========================
# Helpers
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


def parse_price_million(v) -> float | None:
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
        if raw >= 1_000_000:
            return raw / 1_000_000.0
        return raw

    return None


def now_utc():
    return datetime.utcnow()


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

        cur.execute("alter table properties add column if not exists bedrooms integer;")
        cur.execute("alter table properties add column if not exists description text;")
        cur.execute("alter table applicants add column if not exists notes text;")
        cur.execute("alter table applicants add column if not exists bedrooms_min integer;")
        cur.execute("alter table applicants add column if not exists budget_min_million numeric;")
        cur.execute("alter table applicants add column if not exists budget_max_million numeric;")


# =========================
# Cache helpers
# =========================
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
def count_client_results(where_sql: str, params: tuple):
    conn = get_conn_safe()
    q = f"select count(*) as c from properties where {where_sql}"
    df = pd.read_sql_query(q, conn, params=params)
    return int(df.iloc[0]["c"])


@st.cache_data(ttl=180)
def fetch_filter_values(_dsn: str):
    """
    Values for multiselect filters
    """
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


def clear_caches():
    try:
        fetch_minmax_prices.clear()
        count_client_results.clear()
        fetch_filter_values.clear()
    except Exception:
        pass


# =========================
# Auth
# =========================
if "role" not in st.session_state:
    st.session_state.role = None

with st.sidebar:
    st.header("ورود")
    role_ui = st.selectbox("نقش", ["مشتری", "مدیر"], key="login_role_noor")
    pwd = st.text_input("رمز", type="password", key="login_pwd_noor")

    c1, c2 = st.columns(2)
    if c1.button("ورود", key="login_btn_noor"):
        if role_ui == "مدیر" and pwd == ADMIN_PASSWORD:
            st.session_state.role = "admin"
            st.success("ورود مدیر موفق بود.")
        elif role_ui == "مشتری" and pwd == CLIENT_PASSWORD:
            st.session_state.role = "client"
            st.success("ورود مشتری موفق بود.")
        else:
            st.error("رمز اشتباه است.")
    if c2.button("خروج", key="logout_btn_noor"):
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
# Header
# =========================
st.markdown(
    f"""
    <div class="noor-header">
      <img src="{NOOR_LOGO_URL}" width="58" style="border-radius:14px; border:1px solid {NOOR_BORDER}; background:#0f0f0f; padding:6px;" />
      <div>
        <div class="noor-title">مشاور املاک نور</div>
        <div class="noor-subtitle">سیستم فایل‌ها و متقاضیان</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================
# Bedrooms display (fixed)
# =========================
NO_BEDROOM_KEYWORDS = ["زمین", "اداری", "تجاری", "مغازه", "سوله", "انبار", "کارگاه"]


def bedrooms_display(row) -> str:
    ptype = normalize_text(row.get("property_type", ""))
    if any(k in ptype for k in NO_BEDROOM_KEYWORDS):
        return ""

    b = row.get("bedrooms")
    if b is None or (isinstance(b, float) and pd.isna(b)):
        return ""

    # robust conversion (even if text)
    try:
        s = normalize_text(b)
        if not s:
            return ""
        bi = int(float(s))
        return "" if bi <= 0 else str(bi)
    except Exception:
        return ""


# =========================
# Client: Detail page + list (Pagination + Multiselect)
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
        if st.button("بازگشت", key="back_missing_detail"):
            st.session_state.client_selected_file = None
            st.rerun()
        return

    r = df.iloc[0].to_dict()

    if st.button("⬅ بازگشت به لیست فایل‌ها", key="back_to_list_btn"):
        st.session_state.client_selected_file = None
        st.rerun()

    price_m = r.get("price_million")
    price_b = billion_str_from_million(price_m)
    price_t = toman_str_from_million(price_m)

    ptype = normalize_text(r.get("property_type"))
    deal = normalize_text(r.get("deal_type"))
    region = normalize_text(r.get("region"))
    address = normalize_text(r.get("address"))
    desc = normalize_text(r.get("description"))
    area = r.get("area_m2")
    bed = bedrooms_display(r)

    st.markdown("<div class='noor-card'>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="noor-card-top">
          <div>
            <div class="noor-badge">{ptype or "ملک"}</div>
            <div class="noor-code">کد فایل: {code}</div>
          </div>
          <div style="text-align:left">
            <div style="font-size:22px; font-weight:900; color:{NOOR_PRIMARY};">{price_b}</div>
            <div style="font-size:12px; color:{NOOR_MUTED};">{price_t}</div>
          </div>
        </div>
        <div style="color:{NOOR_MUTED}; font-size:13px;">
          <b style="color:{NOOR_TEXT};">{deal}</b>
          {" • " + region if region else ""}
        </div>
        <div class="noor-divider"></div>
        """,
        unsafe_allow_html=True,
    )

    area_str = ""
    try:
        if area is not None and not (isinstance(area, float) and pd.isna(area)):
            area_str = f"{float(area):.0f} متر"
    except Exception:
        area_str = ""

    st.markdown(
        f"""
        <div class="noor-kvgrid">
          <div class="noor-kv"><div class="noor-k">منطقه</div><div class="noor-v">{region or "—"}</div></div>
          <div class="noor-kv"><div class="noor-k">متراژ</div><div class="noor-v">{area_str or "—"}</div></div>
          <div class="noor-kv"><div class="noor-k">خواب</div><div class="noor-v">{(bed + " خواب") if bed else "—"}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if address:
        st.markdown(f"<div class='noor-desc'><b style='color:{NOOR_TEXT}'>آدرس:</b> {address}</div>", unsafe_allow_html=True)

    st.markdown(f"<div class='noor-desc'><b style='color:{NOOR_TEXT}'>توضیحات:</b> {desc or '—'}</div>", unsafe_allow_html=True)
    st.text_input("کپی کد فایل", value=code, key="copy_code_input", help="روی متن کلیک کن و Copy بزن")

    st.markdown("</div>", unsafe_allow_html=True)

    # Similar files
    st.markdown("### فایل‌های مشابه")
    sim_where = ["file_code <> %s"]
    sim_params = [code]

    if region:
        sim_where.append("lower(trim(region)) = lower(trim(%s))")
        sim_params.append(region)
    if ptype:
        sim_where.append("lower(trim(property_type)) = lower(trim(%s))")
        sim_params.append(ptype)

    try:
        if price_m is not None and not (isinstance(price_m, float) and pd.isna(price_m)) and float(price_m) > 0:
            p = float(price_m)
            sim_where.append("price_million is not null and price_million between %s and %s")
            sim_params += [p * 0.85, p * 1.15]
    except Exception:
        pass

    sim = pd.read_sql_query(
        f"""
        select file_code, deal_type, region, property_type, bedrooms, area_m2, price_million, updated_at
        from properties
        where {" and ".join(sim_where)}
        order by updated_at desc nulls last
        limit 8
        """,
        conn,
        params=tuple(sim_params),
    )

    if sim.empty:
        st.info("فایل مشابهی پیدا نشد.")
        return

    for _, sr in sim.iterrows():
        scode = normalize_text(sr.get("file_code"))
        sp = sr.get("price_million")
        st.markdown(
            f"""
            <div class="noor-card">
              <div class="noor-card-top">
                <div>
                  <div class="noor-badge">{normalize_text(sr.get("property_type")) or "ملک"}</div>
                  <div class="noor-code">کد فایل: {scode}</div>
                </div>
                <div style="text-align:left">
                  <div style="font-size:16px; font-weight:900; color:{NOOR_PRIMARY};">{billion_str_from_million(sp)}</div>
                  <div style="font-size:12px; color:{NOOR_MUTED};">{toman_str_from_million(sp)}</div>
                </div>
              </div>
              <div style="color:{NOOR_MUTED}; font-size:13px;">
                <b style="color:{NOOR_TEXT};">{normalize_text(sr.get("deal_type"))}</b>
                {" • " + normalize_text(sr.get("region")) if normalize_text(sr.get("region")) else ""}
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("مشاهده جزئیات", key=f"sim_view_{scode}"):
            st.session_state.client_selected_file = scode
            st.rerun()


def client_files_tab():
    st.subheader("فایل‌ها")

    if "client_selected_file" not in st.session_state:
        st.session_state.client_selected_file = None

    if st.session_state.client_selected_file:
        client_property_detail(st.session_state.client_selected_file)
        return

    mn, mx = fetch_minmax_prices(DATABASE_URL)
    if mx <= 0:
        mx = 10000.0

    regions, ptypes = fetch_filter_values(DATABASE_URL)

    top1, top2, top3, top4 = st.columns([1.4, 1, 1, 0.8])
    with top1:
        q = st.text_input("جستجوی سریع", placeholder="کد فایل / منطقه / نوع ملک / توضیحات ...", key="cl_q_noor")
    with top2:
        deal = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], key="cl_deal_noor")
    with top3:
        sort = st.selectbox("مرتب‌سازی", ["جدیدترین", "ارزان‌ترین", "گران‌ترین"], key="cl_sort_noor")
    with top4:
        page_size = st.selectbox("تعداد در صفحه", [10, 20, 30, 50], index=1, key="cl_pagesize_noor")

    # ✅ Multi-select filters
    f1, f2 = st.columns([1, 1])
    with f1:
        sel_regions = st.multiselect("فیلتر منطقه (چند انتخابی)", options=regions, default=[], key="cl_ms_region_noor")
    with f2:
        sel_ptypes = st.multiselect("فیلتر نوع ملک (چند انتخابی)", options=ptypes, default=[], key="cl_ms_ptype_noor")

    price_rng = st.slider(
        "بازه قیمت (میلیون) — ۵ میلیارد = ۵۰۰۰",
        min_value=float(mn),
        max_value=float(mx),
        value=(float(mn), float(mx)),
        step=50.0,
        key="cl_price_rng_noor"
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

    # multiselect exact match normalized
    if sel_regions:
        where.append("lower(trim(region)) = any(%s)")
        params.append([normalize_text(x).lower() for x in sel_regions])

    if sel_ptypes:
        where.append("lower(trim(property_type)) = any(%s)")
        params.append([normalize_text(x).lower() for x in sel_ptypes])

    where.append("price_million is not null and price_million >= %s and price_million <= %s")
    params += [float(price_rng[0]), float(price_rng[1])]

    where_sql = " and ".join(where)
    params_t = tuple(params)

    total = count_client_results(where_sql, params_t)
    if total <= 0:
        st.info("نتیجه‌ای پیدا نشد.")
        return

    total_pages = max(1, (total + page_size - 1) // page_size)
    pcol1, pcol2, pcol3 = st.columns([1, 1, 2])

    with pcol1:
        page = st.number_input("صفحه", min_value=1, max_value=total_pages, value=1, step=1, key="cl_page_noor")
    with pcol2:
        st.caption(f"نتیجه: {total} فایل")
    with pcol3:
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
        bed = bedrooms_display(r)
        price_m = r.get("price_million")
        desc = normalize_text(r.get("description"))

        price_b = billion_str_from_million(price_m)
        price_t = toman_str_from_million(price_m)

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
                  <div style="font-size:18px; font-weight:900; color:{NOOR_PRIMARY};">{price_b}</div>
                  <div style="font-size:12px; color:{NOOR_MUTED};">{price_t}</div>
                </div>
              </div>

              <div style="color:{NOOR_MUTED}; font-size:13px;">
                <b style="color:{NOOR_TEXT};">{deal_t}</b>
                {" • " + meta_right if meta_right else ""}
              </div>

              <div class="noor-divider"></div>
              <div class="noor-desc">{desc if desc else "—"}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("مشاهده جزئیات", key=f"view_detail_{code}"):
            st.session_state.client_selected_file = code
            st.rerun()


# =========================
# Admin: list + multiselect + remove duplicate bedroom column
# =========================
def admin_files_list_tab():
    st.subheader("لیست فایل‌ها (مدیر)")

    regions, ptypes = fetch_filter_values(DATABASE_URL)

    top1, top2, top3 = st.columns([1.3, 1, 0.8])
    with top1:
        q = st.text_input("جستجوی سریع", placeholder="کد فایل / منطقه / نوع ملک ...", key="al_q_noor")
    with top2:
        deal = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], key="al_deal_noor")
    with top3:
        limit = st.selectbox("تعداد نمایش", [50, 100, 200, 500], index=1, key="al_limit_noor")

    # ✅ Multi-select
    f1, f2 = st.columns([1, 1])
    with f1:
        sel_regions = st.multiselect("فیلتر منطقه (چند انتخابی)", options=regions, default=[], key="al_ms_region_noor")
    with f2:
        sel_ptypes = st.multiselect("فیلتر نوع ملک (چند انتخابی)", options=ptypes, default=[], key="al_ms_ptype_noor")

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

    # ✅ only one bedroom column for display
    df["خواب"] = df.apply(lambda r: bedrooms_display(r.to_dict()), axis=1)

    df["قیمت (میلیارد)"] = df["price_million"].apply(billion_str_from_million)
    df["قیمت (تومان)"] = df["price_million"].apply(toman_str_from_million)

    # remove raw columns that cause duplicate/ugly display
    if "bedrooms" in df.columns:
        df = df.drop(columns=["bedrooms"])
    if "price_million" in df.columns:
        df = df.drop(columns=["price_million"])

    # rename for nicer admin output
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

    # Order columns
    cols = ["کد فایل", "نوع معامله", "نوع ملک", "منطقه", "متراژ", "خواب", "قیمت (میلیارد)", "قیمت (تومان)",
            "مالک", "شماره مالک", "توضیحات", "آپدیت"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)


# =========================
# Admin: add/edit + upload (همان قبلی)
# =========================
def admin_add_edit_property_tab():
    st.subheader("ثبت / ویرایش فایل (مدیر)")

    code_lookup = st.text_input("برای ویرایش/بررسی، کد فایل را وارد کن", key="prop_lookup_code_noor").strip()
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

    with st.form("prop_form_noor"):
        file_code = st.text_input("کد فایل", value=str(code_lookup or ""), key="prop_code_noor")
        deal_type = st.selectbox(
            "نوع معامله",
            ["خرید و فروش", "رهن و اجاره"],
            index=0 if normalize_deal_type(exv("deal_type", "خرید و فروش")) == "خرید و فروش" else 1,
            key="prop_deal_noor"
        )
        property_type = st.text_input("نوع ملک", value=str(exv("property_type", "")), key="prop_ptype_noor")
        region = st.text_input("منطقه", value=str(exv("region", "")), key="prop_region_noor")
        address = st.text_input("آدرس (اختیاری)", value=str(exv("address", "")), key="prop_addr_noor")

        c1, c2, c3 = st.columns(3)
        with c1:
            area_m2 = st.number_input("متراژ", min_value=0.0, value=float(exv("area_m2", 0.0) or 0.0), step=1.0, key="prop_area_noor")
        with c2:
            bedrooms = st.number_input("تعداد خواب (اگر ندارد 0 بزن)", min_value=0, value=int(exv("bedrooms", 0) or 0), step=1, key="prop_bed_noor")
        with c3:
            price_million = st.number_input("قیمت کل (میلیون) — ۵ میلیارد = ۵۰۰۰", min_value=0.0, value=float(exv("price_million", 0.0) or 0.0), step=50.0, key="prop_price_noor")

        description = st.text_area("توضیحات", value=str(exv("description", "")), key="prop_desc_noor")
        owner_name = st.text_input("نام مالک (فقط مدیر)", value=str(exv("owner_name", "")), key="prop_owner_noor")
        owner_phone = st.text_input("شماره مالک (فقط مدیر)", value=str(exv("owner_phone", "")), key="prop_owner_phone_noor")
        internal_notes = st.text_area("یادداشت داخلی (فقط مدیر)", value=str(exv("internal_notes", "")), key="prop_notes_noor")

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

    up = st.file_uploader("آپلود Excel", type=["xlsx"], key="adm_upload_excel_noor")
    if up is None:
        return

    df = load_excel(up)
    st.write("پیش‌نمایش:", df.head(30))

    if st.button("بروزرسانی دیتابیس (Upsert)", key="adm_do_upsert_noor"):
        n = upsert_properties(conn, df)
        with conn.cursor() as cur:
            cur.execute(
                "insert into uploads(uploaded_at, rows_read, rows_upserted) values (%s,%s,%s)",
                (now_utc(), int(len(df)), int(n))
            )
        clear_caches()
        st.success(f"انجام شد. {n} ردیف درج/آپدیت شد.")
        st.rerun()


def applicants_tab():
    st.subheader("متقاضیان (مدیر)")
    st.info("فعلاً تغییری ندادم. اگر خواستی مرحله بعدی: این بخش رو هم کارت‌وار + فیلتر حرفه‌ای می‌کنم.")


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
        st.write("قیمت‌ها بر حسب میلیون هستند. مثال: ۵ میلیارد = ۵۰۰۰")
else:
    t1, t2, t3 = st.tabs(["فایل‌ها", "جستجو", "راهنما"])
    with t1:
        client_files_tab()
    with t2:
        st.info("برای جستجوی دقیق، از فیلترهای تب فایل‌ها استفاده کن.")
    with t3:
        st.write("قیمت‌ها بر حسب میلیون هستند. مثال: ۵ میلیارد = ۵۰۰۰")






