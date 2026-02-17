import os
import re
from datetime import datetime

import pandas as pd
import psycopg2
import streamlit as st

# ✅ MUST be the first Streamlit command and only once
st.set_page_config(page_title="مشاور املاک نور", layout="wide")


# ---------------------------
# Config (Railway Variables / Env Vars)
# ---------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")
CLIENT_PASSWORD = os.environ.get("CLIENT_PASSWORD", "1234")


def now_utc_ts() -> datetime:
    return datetime.utcnow()


# ---------------------------
# DB connection (Supabase Postgres via Pooler)
# ---------------------------
@st.cache_resource
def _make_conn():
    if not DATABASE_URL:
        st.error("DATABASE_URL تنظیم نشده. در Railway → Variables مقدار DATABASE_URL را وارد کنید.")
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
        create table if not exists uploads (
          id bigserial primary key,
          uploaded_at timestamp,
          rows_read integer,
          rows_upserted integer
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

        # migration-safe
        try:
            cur.execute("alter table properties add column if not exists bedrooms integer;")
        except Exception:
            pass
        try:
            cur.execute("alter table applicants add column if not exists notes text;")
        except Exception:
            pass


# ---------------------------
# Helpers
# ---------------------------
def normalize_deal_type(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if "رهن" in s or "اجاره" in s:
        return "رهن و اجاره"
    if "فروش" in s or "خرید" in s:
        return "خرید و فروش"
    return s


def normalize_text(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    return "" if s.lower() == "nan" else s


def parse_price_million(v) -> float | None:
    """
    DB unit: million
    Example: 5 میلیارد -> 5000
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)

    s = str(v).strip()
    if not s:
        return None

    s = s.replace(",", "").replace("٬", "").replace(" ", "").replace("\u200c", "")

    m = re.search(r"(\d+(\.\d+)?)میلیارد", s)
    if m:
        return float(m.group(1)) * 1000.0

    m = re.search(r"(\d+(\.\d+)?)میلیون", s)
    if m:
        return float(m.group(1))

    m = re.search(r"(\d+)(تومان)?", s)
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


def parse_bedrooms(v) -> int | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        try:
            iv = int(v)
            return iv if iv >= 0 else None
        except Exception:
            return None
    s = str(v).strip()
    if not s:
        return None
    s = s.replace(" ", "").replace("\u200c", "")
    m = re.search(r"(\d+)", s)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


def has_bedrooms(property_type: str) -> bool:
    pt = normalize_text(property_type).replace("‌", "").replace("\u200c", "").strip()
    if not pt:
        return True

    no_bed_keywords = [
        "زمین", "اداری", "تجاری", "مغازه", "دفتر", "انبار", "سوله", "کارگاه", "باغ", "باغچه"
    ]
    return not any(k in pt for k in no_bed_keywords)


# ---------------------------
# Excel loader (sheet: Database)
# ---------------------------
def load_excel(file) -> pd.DataFrame:
    df = pd.read_excel(file, sheet_name="Database", engine="openpyxl")

    def norm(s):
        return str(s).strip().replace("‌", "").replace("\u200c", "").replace(" ", "")

    cols = list(df.columns)
    cols_norm = {c: norm(c) for c in cols}
    col_map = {}

    def find_col(key, cond):
        for c in cols:
            if cond(cols_norm[c]):
                col_map[key] = c
                return

    # required columns
    find_col("file_code", lambda n: ("کد" in n) and ("فایل" in n or "ملک" in n))
    if "file_code" not in col_map:
        find_col("file_code", lambda n: "کد" in n)

    find_col("deal_type", lambda n: ("نوعمعامله" in n) or ("نوع" in n and "معامله" in n))
    find_col("region", lambda n: "منطقه" in n)
    find_col("address", lambda n: ("آدرس" in n) or ("ادرس" in n))
    find_col("area_m2", lambda n: "متراژ" in n)
    find_col("property_type", lambda n: ("نوعملک" in n) or ("نوع" in n and "ملک" in n))

    # bedrooms (optional)
    find_col("bedrooms", lambda n: ("اتاقخواب" in n) or ("تعداداتاق" in n) or (n == "اتاق") or ("خواب" in n))

    # optional columns
    find_col("description", lambda n: ("توضیحات" in n) or ("شرح" in n))
    find_col("owner_name", lambda n: ("مالک" in n) and (("نام" in n) or ("اسم" in n)))
    find_col("owner_phone", lambda n: (("تماس" in n and "مالک" in n) or ("شماره" in n and "مالک" in n) or ("موبایل" in n and "مالک" in n)))
    find_col("internal_notes", lambda n: ("یادداشت" in n) or ("داخلی" in n) or ("نکته" in n))

    # price total
    find_col("price_total", lambda n: ("قیمتکل" in n) or (("قیمت" in n) and ("کل" in n)))
    if "price_total" not in col_map:
        price_like = [c for c in cols if "قیمت" in cols_norm[c]]
        if len(price_like) == 1:
            col_map["price_total"] = price_like[0]

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
        "bedrooms": df[col_map["bedrooms"]].apply(parse_bedrooms) if "bedrooms" in col_map else None,
        "description": df[col_map["description"]].astype(str).str.strip() if "description" in col_map else "",
        "owner_name": df[col_map["owner_name"]].astype(str).str.strip() if "owner_name" in col_map else "",
        "owner_phone": df[col_map["owner_phone"]].astype(str).str.strip() if "owner_phone" in col_map else "",
        "internal_notes": df[col_map["internal_notes"]].astype(str).str.strip() if "internal_notes" in col_map else "",
        "updated_at": now_utc_ts(),
    })

    out = out[out["file_code"].notna() & (out["file_code"] != "")].copy()
    for c in ["region", "address", "property_type", "description", "owner_name", "owner_phone", "internal_notes"]:
        out[c] = out[c].replace({"nan": ""})
    return out


# ---------------------------
# Cached data
# ---------------------------
@st.cache_data(ttl=180)
def fetch_distinct_cached(colname: str):
    conn = get_conn_safe()
    q = f"select distinct {colname} from properties where {colname} is not null and trim({colname})<>'' order by {colname}"
    df = pd.read_sql_query(q, conn)
    return df[colname].tolist()


@st.cache_data(ttl=120)
def fetch_minmax_cached():
    conn = get_conn_safe()
    q = """
    select
      min(price_million) as min_price,
      max(price_million) as max_price,
      min(area_m2) as min_area,
      max(area_m2) as max_area
    from properties
    """
    df = pd.read_sql_query(q, conn)
    if df.empty:
        return 0.0, 0.0, 0.0, 0.0

    r = df.iloc[0].to_dict()

    def safe(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0.0
        return float(v)

    return safe(r.get("min_price")), safe(r.get("max_price")), safe(r.get("min_area")), safe(r.get("max_area"))


def clear_caches():
    for fn in (fetch_distinct_cached, fetch_minmax_cached):
        try:
            fn.clear()
        except Exception:
            pass


# ---------------------------
# DB Helpers/Writes
# ---------------------------
def property_exists(conn, file_code: str) -> bool:
    if not file_code:
        return False
    with conn.cursor() as cur:
        cur.execute("select 1 from properties where file_code=%s limit 1", (file_code,))
        return cur.fetchone() is not None


def fetch_property_by_code(conn, file_code: str) -> dict | None:
    if not file_code:
        return None
    q = """
    select file_code, deal_type, region, address, area_m2, price_million,
           property_type, bedrooms, description, owner_name, owner_phone, internal_notes
    from properties
    where file_code = %s
    limit 1
    """
    df = pd.read_sql_query(q, conn, params=(file_code,))
    if df.empty:
        return None
    return df.iloc[0].to_dict()


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
                str(r["file_code"]).strip(),
                r["deal_type"],
                r["region"],
                r["address"],
                None if pd.isna(r["area_m2"]) else float(r["area_m2"]),
                None if (r["price_million"] is None or (isinstance(r["price_million"], float) and pd.isna(r["price_million"]))) else float(r["price_million"]),
                r["property_type"],
                None if r.get("bedrooms") is None or (isinstance(r.get("bedrooms"), float) and pd.isna(r.get("bedrooms"))) else int(r.get("bedrooms")),
                r["description"],
                r["owner_name"],
                r["owner_phone"],
                r["internal_notes"],
                now_utc_ts(),
            ))
            rows += 1
    return rows


def insert_upload_log(conn, rows_read: int, rows_upserted: int):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "insert into uploads(uploaded_at, rows_read, rows_upserted) values (%s,%s,%s)",
                (now_utc_ts(), int(rows_read), int(rows_upserted))
            )
    except Exception:
        pass


def upsert_one_property(conn, row: dict):
    with conn.cursor() as cur:
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
            row["file_code"], row["deal_type"], row["region"], row["address"],
            row["area_m2"], row["price_million"], row["property_type"], row["bedrooms"],
            row["description"], row["owner_name"], row["owner_phone"], row["internal_notes"],
            now_utc_ts(),
        ))


def insert_applicant(conn, a: dict):
    with conn.cursor() as cur:
        cur.execute("""
        insert into applicants
          (full_name, phone, deal_type, desired_property_type, region,
           budget_min_million, budget_max_million, bedrooms_min, notes, created_at, updated_at)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            a["full_name"], a["phone"], a["deal_type"], a["desired_property_type"], a["region"],
            a["budget_min_million"], a["budget_max_million"], a["bedrooms_min"], a["notes"],
            now_utc_ts(), now_utc_ts()
        ))


def update_applicant(conn, applicant_id: int, a: dict):
    with conn.cursor() as cur:
        cur.execute("""
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
          updated_at=%s
        where id=%s
        """, (
            a["full_name"], a["phone"], a["deal_type"], a["desired_property_type"], a["region"],
            a["budget_min_million"], a["budget_max_million"], a["bedrooms_min"], a["notes"],
            now_utc_ts(), int(applicant_id)
        ))


# ---------------------------
# UI
# ---------------------------
st.title("مشاور املاک نور")

conn = get_conn_safe()
ensure_tables(conn)

if "role" not in st.session_state:
    st.session_state.role = None

with st.sidebar:
    st.header("ورود")
    role_ui = st.selectbox("نقش", ["مشتری", "مدیر"], index=0, key="login_role")
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
    st.warning("برای استفاده از برنامه، از نوار کناری وارد شوید.")
    st.stop()

is_admin = st.session_state.role == "admin"

# Tabs
if is_admin:
    tab_admin_list, tab_upload, tab_search, tab_add, tab_applicants = st.tabs(
        ["لیست فایل‌ها", "آپلود/آپدیت", "جستجو", "ثبت/ویرایش ملک", "متقاضیان"]
    )
else:
    tab_list, tab_search, tab_help = st.tabs(["فایل‌ها", "جستجو", "راهنما"])


# ---------------------------
# Client: List tab (card style)
# ---------------------------
if not is_admin:
    with tab_list:
        st.subheader("فایل‌های موجود")

        min_p, max_p, min_a, max_a = fetch_minmax_cached()
        if max_p <= 0:
            max_p = 10000
        if max_a <= 0:
            max_a = 500

        f1, f2, f3, f4 = st.columns([1.2, 1.1, 1.1, 1.3])

        with f1:
            quick_q = st.text_input("جستجوی سریع", placeholder="کد فایل / منطقه / نوع ملک ...", key="cl_quick_q")
        with f2:
            deal_filter = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], index=0, key="cl_deal")
        with f3:
            sort_mode = st.selectbox(
                "مرتب‌سازی",
                ["جدیدترین", "ارزان‌ترین", "گران‌ترین", "بیشترین متراژ", "کمترین متراژ"],
                index=0,
                key="cl_sort",
            )
        with f4:
            page_size = st.selectbox("تعداد در هر صفحه", [12, 24, 36, 60], index=1, key="cl_page_size")

        s1, s2 = st.columns(2)
        with s1:
            price_range = st.slider(
                "بازه بودجه (میلیون)",
                min_value=float(max(0.0, min_p)),
                max_value=float(max_p),
                value=(float(max(0.0, min_p)), float(max_p)),
                step=50.0,
                key="cl_price_slider",
            )
        with s2:
            area_range = st.slider(
                "بازه متراژ (متر)",
                min_value=float(max(0.0, min_a)),
                max_value=float(max_a),
                value=(float(max(0.0, min_a)), float(max_a)),
                step=10.0,
                key="cl_area_slider",
            )

        page = st.number_input("صفحه", min_value=1, value=1, step=1, key="cl_page")
        offset = (page - 1) * int(page_size)

        where = ["1=1"]
        params = []

        if quick_q.strip():
            q = f"%{quick_q.strip()}%"
            where.append("(file_code ILIKE %s OR region ILIKE %s OR property_type ILIKE %s)")
            params.extend([q, q, q])

        if deal_filter != "همه":
            where.append("deal_type = %s")
            params.append(deal_filter)

        where.append("(price_million is null OR (price_million >= %s AND price_million <= %s))")
        params.extend([float(price_range[0]), float(price_range[1])])

        where.append("(area_m2 is null OR (area_m2 >= %s AND area_m2 <= %s))")
        params.extend([float(area_range[0]), float(area_range[1])])

        order_by = "updated_at desc nulls last"
        if sort_mode == "ارزان‌ترین":
            order_by = "price_million asc nulls last, updated_at desc nulls last"
        elif sort_mode == "گران‌ترین":
            order_by = "price_million desc nulls last, updated_at desc nulls last"
        elif sort_mode == "بیشترین متراژ":
            order_by = "area_m2 desc nulls last, updated_at desc nulls last"
        elif sort_mode == "کمترین متراژ":
            order_by = "area_m2 asc nulls last, updated_at desc nulls last"

        conn = get_conn_safe()

        count_q = f"select count(*) as cnt from properties where {' and '.join(where)}"
        total_df = pd.read_sql_query(count_q, conn, params=tuple(params))
        total = int(total_df.loc[0, "cnt"]) if not total_df.empty else 0
        total_pages = max(1, (total + int(page_size) - 1) // int(page_size))

        select_cols = """
          file_code, deal_type, region, property_type, area_m2, bedrooms,
          price_million, address, description, updated_at
        """
        data_q = f"""
          select {select_cols}
          from properties
          where {" and ".join(where)}
          order by {order_by}
          limit %s offset %s
        """
        data_params = params + [int(page_size), int(offset)]
        df = pd.read_sql_query(data_q, conn, params=tuple(data_params))

        st.caption(f"تعداد نتایج: {total} | صفحه {page} از {total_pages}")

        if df.empty:
            st.info("نتیجه‌ای پیدا نشد.")
        else:
            cols = st.columns(3)
            for i, row in df.iterrows():
                col = cols[i % 3]

                file_code = normalize_text(row.get("file_code"))
                deal_type = normalize_text(row.get("deal_type"))
                region = normalize_text(row.get("region"))
                ptype = normalize_text(row.get("property_type"))
                area = row.get("area_m2")
                bedrooms = row.get("bedrooms")
                price_m = row.get("price_million")
                address = normalize_text(row.get("address"))
                desc = normalize_text(row.get("description"))
                updated = row.get("updated_at")

                price_toman = toman_str_from_million(price_m)
                price_bil = billion_str_from_million(price_m)

                area_txt = "—"
                try:
                    if area is not None and not (isinstance(area, float) and pd.isna(area)):
                        area_txt = f"{float(area):.0f} متر"
                except Exception:
                    pass

                bed_txt = ""
                try:
                    if has_bedrooms(ptype) and bedrooms is not None and not (isinstance(bedrooms, float) and pd.isna(bedrooms)):
                        bed_txt = f"{int(bedrooms)} خواب"
                except Exception:
                    bed_txt = ""

                with col:
                    st.markdown("---")
                    st.markdown(f"### فایل {file_code}")

                    line1 = " | ".join([x for x in [deal_type, ptype, f"منطقه {region}" if region else ""] if x])
                    if line1:
                        st.caption(line1)

                    l, r = st.columns([1.2, 1])
                    with l:
                        if price_toman:
                            st.markdown(f"**قیمت:** {price_toman}")
                            if price_bil:
                                st.caption(price_bil)
                        else:
                            st.markdown("**قیمت:** نامشخص")

                    with r:
                        meta = area_txt
                        if bed_txt:
                            meta = f"{meta} • {bed_txt}"
                        st.markdown(f"**مشخصات:** {meta}")

                    if desc:
                        preview = desc if len(desc) <= 90 else desc[:90] + "…"
                        st.write(preview)

                    st.caption("کپی کد فایل:")
                    st.code(file_code, language=None)

                    with st.expander("جزئیات", expanded=False):
                        if address:
                            st.write(f"**لوکیشن:** {address}")
                        if desc:
                            st.write(f"**توضیحات:** {desc}")
                        if updated:
                            st.caption(f"آخرین بروزرسانی: {updated}")

            st.markdown("---")
            out = df.copy()
            out["price_toman"] = out["price_million"].apply(toman_str_from_million)
            out["price_billion"] = out["price_million"].apply(billion_str_from_million)
            csv = out.drop(columns=["price_million"]).to_csv(index=False).encode("utf-8-sig")
            st.download_button("دانلود CSV همین صفحه", csv, f"files_page_{page}.csv", "text/csv", key="cl_dl_csv")


# ---------------------------
# Admin: List (table) + load to edit
# ---------------------------
if is_admin:
    with tab_admin_list:
        st.subheader("لیست فایل‌ها (مدیر)")

        conn = get_conn_safe()

        top1, top2, top3, top4 = st.columns([1.3, 1.0, 1.0, 1.0])
        with top1:
            al_q = st.text_input("جستجوی سریع", placeholder="کد فایل / منطقه / نوع ملک ...", key="al_q")
        with top2:
            al_deal = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], index=0, key="al_deal")
        with top3:
            al_sort = st.selectbox("مرتب‌سازی", ["جدیدترین", "ارزان‌ترین", "گران‌ترین"], index=0, key="al_sort")
        with top4:
            al_limit = st.selectbox("تعداد نمایش", [50, 100, 200, 500], index=1, key="al_limit")

        where = ["1=1"]
        params = []

        if al_q.strip():
            q = f"%{al_q.strip()}%"
            where.append("(file_code ILIKE %s OR region ILIKE %s OR property_type ILIKE %s)")
            params.extend([q, q, q])

        if al_deal != "همه":
            where.append("deal_type = %s")
            params.append(al_deal)

        order_by = "updated_at desc nulls last"
        if al_sort == "ارزان‌ترین":
            order_by = "price_million asc nulls last, updated_at desc nulls last"
        elif al_sort == "گران‌ترین":
            order_by = "price_million desc nulls last, updated_at desc nulls last"

        q = f"""
        select
          file_code as "کد فایل",
          deal_type as "نوع معامله",
          property_type as "نوع ملک",
          region as "منطقه",
          area_m2 as "متراژ",
          bedrooms as "خواب",
          price_million as "قیمت (میلیون)",
          owner_name as "مالک",
          owner_phone as "شماره مالک",
          updated_at as "آپدیت"
        from properties
        where {" and ".join(where)}
        order by {order_by}
        limit %s
        """
        df = pd.read_sql_query(q, conn, params=tuple(params + [int(al_limit)]))

        if df.empty:
            st.info("فایلی پیدا نشد.")
        else:
            df["قیمت (تومان)"] = df["قیمت (میلیون)"].apply(toman_str_from_million)
            df["قیمت (میلیارد)"] = df["قیمت (میلیون)"].apply(billion_str_from_million)
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("دانلود CSV لیست", csv, "admin_files.csv", "text/csv", key="al_dl")

            st.divider()
            st.subheader("ویرایش سریع")
            codes = df["کد فایل"].astype(str).tolist()
            sel_code = st.selectbox("انتخاب کد فایل برای ویرایش", codes, key="al_sel_code")

            if st.button("باز کردن در تب ثبت/ویرایش", key="al_open_edit"):
                st.session_state["edit_load_code"] = sel_code
                st.success("انجام شد. برو به تب «ثبت/ویرایش ملک».")


# ---------------------------
# Admin: Upload / Update
# ---------------------------
if is_admin:
    with tab_upload:
        st.subheader("آپلود اکسل و بروزرسانی (فقط مدیر)")
        st.caption("اکسل باید شیت Database داشته باشد. قیمت کل بر حسب میلیون است (مثلاً ۵ میلیارد = ۵۰۰۰).")

        up = st.file_uploader("آپلود Excel", type=["xlsx"], key="adm_upload_excel")
        if up is not None:
            df = load_excel(up)
            st.write("پیش‌نمایش:", df.head(30))

            if st.button("بروزرسانی دیتابیس (Merge/Upsert)", key="adm_do_upsert"):
                conn = get_conn_safe()
                n = upsert_properties(conn, df)
                insert_upload_log(conn, rows_read=len(df), rows_upserted=n)
                clear_caches()
                st.success(f"انجام شد. {n} ردیف درج/آپدیت شد.")

        st.divider()
        st.subheader("آخرین آپلودها")
        try:
            conn = get_conn_safe()
            logs = pd.read_sql_query(
                "select uploaded_at, rows_read, rows_upserted from uploads order by id desc limit 20",
                conn
            )
            st.dataframe(logs, use_container_width=True)
        except Exception:
            st.info("لاگ آپلودها فعلاً در دسترس نیست.")


# ---------------------------
# Admin: Add / Edit (with duplicate code warning)
# ---------------------------
if is_admin:
    with tab_add:
        st.subheader("ثبت یا ویرایش ملک (فقط مدیر)")
        st.caption("اگر کد فایل موجود باشد، امکان آپدیت دارد. برای جلوگیری از اشتباه، اگر کد تکراری باشد باید تیک آپدیت را بزنید.")

        conn = get_conn_safe()

        # If admin clicked "open edit" from list tab, preload form fields
        if "edit_load_code" in st.session_state and st.session_state["edit_load_code"]:
            code_to_load = st.session_state["edit_load_code"]
            row = fetch_property_by_code(conn, code_to_load)
            if row:
                st.session_state["adm_fc"] = normalize_text(row.get("file_code"))
                st.session_state["adm_deal"] = normalize_text(row.get("deal_type")) or "خرید و فروش"
                st.session_state["adm_region"] = normalize_text(row.get("region"))
                st.session_state["adm_address"] = normalize_text(row.get("address"))
                st.session_state["adm_area"] = float(row.get("area_m2") or 0.0)
                st.session_state["adm_price"] = float(row.get("price_million") or 0.0)
                st.session_state["adm_ptype"] = normalize_text(row.get("property_type"))
                st.session_state["adm_bedrooms"] = int(row.get("bedrooms") or 0)
                st.session_state["adm_desc"] = normalize_text(row.get("description"))
                st.session_state["adm_owner"] = normalize_text(row.get("owner_name"))
                st.session_state["adm_phone"] = normalize_text(row.get("owner_phone"))
                st.session_state["adm_notes"] = normalize_text(row.get("internal_notes"))
                st.session_state["adm_confirm_update"] = True  # چون داریم ویرایش می‌کنیم
            st.session_state["edit_load_code"] = ""

        a, b, c = st.columns(3)

        with a:
            file_code = st.text_input("کد فایل (اجباری)", key="adm_fc")
            deal_type = st.selectbox("نوع معامله", ["خرید و فروش", "رهن و اجاره"], key="adm_deal")
            property_type = st.text_input("نوع ملک", placeholder="مثلاً آپارتمان / دوبلکس / ...", key="adm_ptype")

        with b:
            region = st.text_input("منطقه", placeholder="مثلاً 1 یا سعادت‌آباد", key="adm_region")
            area_m2 = st.number_input("متراژ", min_value=0.0, value=0.0, step=1.0, key="adm_area")
            price_million = st.number_input("قیمت کل (میلیون)", min_value=0.0, value=0.0, step=50.0, key="adm_price")

        with c:
            owner_name = st.text_input("نام مالک (فقط مدیر)", key="adm_owner")
            owner_phone = st.text_input("شماره تماس مالک (فقط مدیر)", key="adm_phone")

        bedrooms_val = st.number_input("تعداد اتاق خواب (اگر مربوط است)", min_value=0, value=0, step=1, key="adm_bedrooms")

        address = st.text_input("آدرس/لوکیشن", key="adm_address")
        description = st.text_area("توضیحات", key="adm_desc")
        internal_notes = st.text_area("یادداشت داخلی (فقط مدیر)", key="adm_notes")

        # Duplicate code protection
        exists = False
        if file_code and file_code.strip():
            try:
                exists = property_exists(conn, file_code.strip())
            except Exception:
                exists = False

        if exists:
            st.warning("⚠️ این کد فایل قبلاً وجود دارد. اگر ذخیره کنید، اطلاعات فایل قبلی آپدیت می‌شود.")
            confirm_update = st.checkbox("می‌خواهم همین کد تکراری را آپدیت کنم", key="adm_confirm_update")
        else:
            # keep key stable
            confirm_update = st.checkbox("می‌خواهم همین کد تکراری را آپدیت کنم", value=False, key="adm_confirm_update")

        s1, s2 = st.columns(2)

        if s1.button("ثبت / آپدیت", key="adm_save"):
            fc = (file_code or "").strip()
            if not fc:
                st.error("کد فایل اجباری است.")
            else:
                if exists and not confirm_update:
                    st.error("برای جلوگیری از اشتباه، چون کد تکراری است باید تیک «آپدیت» را بزنید.")
                else:
                    bd = int(bedrooms_val) if has_bedrooms(property_type) else None

                    row = {
                        "file_code": fc,
                        "deal_type": deal_type,
                        "region": (region or "").strip(),
                        "address": (address or "").strip(),
                        "area_m2": float(area_m2) if area_m2 else None,
                        "price_million": float(price_million) if price_million else None,
                        "property_type": (property_type or "").strip(),
                        "bedrooms": bd,
                        "description": (description or "").strip(),
                        "owner_name": (owner_name or "").strip(),
                        "owner_phone": (owner_phone or "").strip(),
                        "internal_notes": (internal_notes or "").strip(),
                    }
                    conn = get_conn_safe()
                    upsert_one_property(conn, row)
                    clear_caches()
                    st.success("ثبت/آپدیت انجام شد (دایمی).")

        if s2.button("حذف این کد فایل", key="adm_del"):
            fc = (file_code or "").strip()
            if not fc:
                st.error("کد فایل را وارد کنید.")
            else:
                conn = get_conn_safe()
                with conn.cursor() as cur:
                    cur.execute("delete from properties where file_code = %s", (fc,))
                clear_caches()
                st.success("حذف شد.")


# ---------------------------
# Admin: Applicants + Matching
# ---------------------------
if is_admin:
    with tab_applicants:
        st.subheader("متقاضیان (فقط مدیر)")

        conn = get_conn_safe()
        apps = pd.read_sql_query(
            "select id, full_name, phone, deal_type, desired_property_type, region, budget_min_million, budget_max_million, bedrooms_min, notes, updated_at "
            "from applicants order by updated_at desc nulls last, id desc",
            conn
        )

        left, right = st.columns([1.1, 1])

        with left:
            st.markdown("### ثبت/ویرایش متقاضی")
            mode = st.radio("حالت", ["ثبت جدید", "ویرایش"], horizontal=True, key="app_mode")

            selected_id = None
            selected_row = None

            if mode == "ویرایش" and not apps.empty:
                label_map = {
                    int(r["id"]): f'#{int(r["id"])} - {normalize_text(r["full_name"])} ({normalize_text(r["phone"])})'
                    for _, r in apps.iterrows()
                }
                selected_id = st.selectbox(
                    "انتخاب متقاضی",
                    list(label_map.keys()),
                    format_func=lambda x: label_map.get(x, str(x)),
                    key="app_select_edit",
                )
                selected_row = apps[apps["id"] == selected_id].iloc[0].to_dict() if selected_id else None

            def prefill(key, default=""):
                if selected_row is None:
                    return default
                v = selected_row.get(key)
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return default
                return v

            full_name = st.text_input("نام و نام خانوادگی", value=str(prefill("full_name", "")), key="app_fullname")
            phone = st.text_input("شماره تماس", value=str(prefill("phone", "")), key="app_phone")
            deal = st.selectbox(
                "نوع معامله",
                ["خرید و فروش", "رهن و اجاره"],
                index=0 if str(prefill("deal_type", "خرید و فروش")) == "خرید و فروش" else 1,
                key="app_deal",
            )

            desired_property_type = st.text_input("نوع ملک موردنظر (اختیاری)", value=str(prefill("desired_property_type", "")), key="app_dptype")
            region = st.text_input("منطقه (اختیاری)", value=str(prefill("region", "")), key="app_region")

            b1, b2 = st.columns(2)
            with b1:
                budget_min = st.number_input(
                    "بودجه از (میلیون)",
                    min_value=0.0,
                    value=float(prefill("budget_min_million", 0.0) or 0.0),
                    step=50.0,
                    key="app_bmin",
                )
            with b2:
                budget_max = st.number_input(
                    "بودجه تا (میلیون) (0 یعنی نامحدود)",
                    min_value=0.0,
                    value=float(prefill("budget_max_million", 0.0) or 0.0),
                    step=50.0,
                    key="app_bmax",
                )

            bedrooms_min = st.number_input("حداقل اتاق خواب (اختیاری)", min_value=0, value=int(prefill("bedrooms_min", 0) or 0), step=1, key="app_bedmin")
            notes = st.text_area("توضیحات", value=str(prefill("notes", "")), key="app_notes")

            if mode == "ثبت جدید":
                if st.button("ثبت متقاضی", key="app_add_btn"):
                    a = {
                        "full_name": full_name.strip(),
                        "phone": phone.strip(),
                        "deal_type": deal,
                        "desired_property_type": desired_property_type.strip(),
                        "region": region.strip(),
                        "budget_min_million": float(budget_min) if budget_min else 0.0,
                        "budget_max_million": float(budget_max) if budget_max else 0.0,
                        "bedrooms_min": int(bedrooms_min) if bedrooms_min else 0,
                        "notes": notes.strip(),
                    }
                    insert_applicant(conn, a)
                    st.success("متقاضی ثبت شد. یک‌بار صفحه را رفرش کنید.")
            else:
                if selected_id is None:
                    st.info("برای ویرایش، یک متقاضی را انتخاب کنید.")
                else:
                    if st.button("ذخیره تغییرات", key="app_save_btn"):
                        a = {
                            "full_name": full_name.strip(),
                            "phone": phone.strip(),
                            "deal_type": deal,
                            "desired_property_type": desired_property_type.strip(),
                            "region": region.strip(),
                            "budget_min_million": float(budget_min) if budget_min else 0.0,
                            "budget_max_million": float(budget_max) if budget_max else 0.0,
                            "bedrooms_min": int(bedrooms_min) if bedrooms_min else 0,
                            "notes": notes.strip(),
                        }
                        update_applicant(conn, int(selected_id), a)
                        st.success("ویرایش انجام شد. یک‌بار صفحه را رفرش کنید.")

        with right:
            st.markdown("### لیست متقاضیان")
            if apps.empty:
                st.info("هنوز متقاضی ثبت نشده است.")
            else:
                show_cols = ["id", "full_name", "phone", "deal_type", "desired_property_type", "region",
                             "budget_min_million", "budget_max_million", "bedrooms_min", "updated_at"]
                st.dataframe(apps[show_cols], use_container_width=True)

            st.divider()
            st.markdown("### مچ خودکار متقاضی با فایل‌ها")

            if apps.empty:
                st.info("ابتدا یک متقاضی ثبت کنید.")
            else:
                label_map2 = {
                    int(r["id"]): f'#{int(r["id"])} - {normalize_text(r["full_name"])} ({normalize_text(r["phone"])})'
                    for _, r in apps.iterrows()
                }
                mid = st.selectbox(
                    "انتخاب متقاضی برای مچ",
                    list(label_map2.keys()),
                    format_func=lambda x: label_map2.get(x, str(x)),
                    key="match_select",
                )
                mr = apps[apps["id"] == mid].iloc[0].to_dict()

                where = ["1=1"]
                params = []

                if normalize_text(mr.get("deal_type")):
                    where.append("deal_type = %s")
                    params.append(normalize_text(mr.get("deal_type")))

                if normalize_text(mr.get("desired_property_type")):
                    where.append("property_type ILIKE %s")
                    params.append(f"%{normalize_text(mr.get('desired_property_type'))}%")

                if normalize_text(mr.get("region")):
                    where.append("region ILIKE %s")
                    params.append(f"%{normalize_text(mr.get('region'))}%")

                bmin = mr.get("budget_min_million")
                bmax = mr.get("budget_max_million")

                if bmin is not None and not (isinstance(bmin, float) and pd.isna(bmin)) and float(bmin) > 0:
                    where.append("price_million >= %s")
                    params.append(float(bmin))

                if bmax is not None and not (isinstance(bmax, float) and pd.isna(bmax)) and float(bmax) > 0:
                    where.append("price_million <= %s")
                    params.append(float(bmax))

                bdm = mr.get("bedrooms_min")
                if bdm is not None and not (isinstance(bdm, float) and pd.isna(bdm)) and int(bdm) > 0:
                    where.append("(bedrooms is not null and bedrooms >= %s)")
                    params.append(int(bdm))

                limit = st.selectbox("حداکثر نتایج", [50, 100, 200, 500], index=1, key="match_limit")

                q = f"""
                  select file_code, deal_type, region, property_type, bedrooms, area_m2, price_million,
                         address, description, updated_at
                  from properties
                  where {" and ".join(where)}
                  order by updated_at desc nulls last
                  limit %s
                """
                params2 = params + [int(limit)]

                conn = get_conn_safe()
                res = pd.read_sql_query(q, conn, params=tuple(params2))

                if res.empty:
                    st.warning("فایل مطابق پیدا نشد.")
                else:
                    res["قیمت (تومان)"] = res["price_million"].apply(toman_str_from_million)
                    res["قیمت (میلیارد)"] = res["price_million"].apply(billion_str_from_million)
                    res = res.drop(columns=["price_million"])
                    st.dataframe(res, use_container_width=True)

                    csv = res.to_csv(index=False).encode("utf-8-sig")
                    st.download_button("دانلود CSV نتایج مچ", csv, f"match_applicant_{mid}.csv", "text/csv", key="match_dl")


# ---------------------------
# Search tab (Admin + Client)
# ---------------------------
with tab_search:
    st.subheader("جستجو")

    deal_opts = ["", "خرید و فروش", "رهن و اجاره"]

    try:
        prop_opts = [""] + fetch_distinct_cached("property_type")
        region_opts = [""] + fetch_distinct_cached("region")
    except Exception:
        prop_opts = [""]
        region_opts = [""]

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        deal = st.selectbox("نوع معامله", deal_opts, index=0, key="sr_deal")
    with c2:
        ptype = st.selectbox("نوع ملک", prop_opts, index=0, key="sr_ptype")
    with c3:
        region = st.selectbox("منطقه", region_opts, index=0, key="sr_region")
    with c4:
        file_code_q = st.text_input("کد فایل (اختیاری)", key="sr_code")
    with c5:
        min_bed = st.number_input("حداقل خواب (اختیاری)", min_value=0, value=0, step=1, key="sr_bed")

    d1, d2, d3, d4 = st.columns(4)
    with d1:
        min_area = st.number_input("متراژ از", min_value=0.0, value=0.0, step=10.0, key="sr_min_area")
    with d2:
        max_area = st.number_input("متراژ تا (0 یعنی محدودیت ندارد)", min_value=0.0, value=0.0, step=10.0, key="sr_max_area")
    with d3:
        min_price = st.number_input("قیمت از (میلیون)", min_value=0.0, value=0.0, step=50.0, key="sr_min_price")
    with d4:
        max_price = st.number_input("قیمت تا (میلیون) (0 یعنی محدودیت ندارد)", min_value=0.0, value=0.0, step=50.0, key="sr_max_price")

    if st.button("جستجو", key="sr_btn"):
        params = []
        where = ["1=1"]

        if file_code_q.strip():
            where.append("file_code ILIKE %s")
            params.append(f"%{file_code_q.strip()}%")

        if deal:
            where.append("deal_type = %s")
            params.append(deal)

        if ptype:
            where.append("property_type = %s")
            params.append(ptype)

        if region:
            where.append("region = %s")
            params.append(region)

        if min_area > 0:
            where.append("area_m2 >= %s")
            params.append(float(min_area))

        if max_area > 0:
            where.append("area_m2 <= %s")
            params.append(float(max_area))

        if min_price > 0:
            where.append("price_million >= %s")
            params.append(float(min_price))

        if max_price > 0:
            where.append("price_million <= %s")
            params.append(float(max_price))

        if min_bed > 0:
            where.append("(bedrooms is not null and bedrooms >= %s)")
            params.append(int(min_bed))

        if is_admin:
            select_cols = """
              file_code, deal_type, region, property_type, bedrooms, area_m2, price_million,
              address, description, owner_name, owner_phone, internal_notes, updated_at
            """
        else:
            select_cols = """
              file_code, deal_type, region, property_type, bedrooms, area_m2, price_million,
              address, description, updated_at
            """

        query = f"""
          select {select_cols}
          from properties
          where {" and ".join(where)}
          order by price_million asc nulls last, updated_at desc nulls last
        """

        conn = get_conn_safe()
        res = pd.read_sql_query(query, conn, params=tuple(params))

        if res.empty:
            st.warning("هیچ نتیجه‌ای پیدا نشد.")
        else:
            res["قیمت (تومان)"] = res["price_million"].apply(toman_str_from_million)
            res["قیمت (میلیارد)"] = res["price_million"].apply(billion_str_from_million)
            res = res.drop(columns=["price_million"])
            st.write(f"تعداد نتایج: {len(res)}")
            st.dataframe(res, use_container_width=True)

            csv = res.to_csv(index=False).encode("utf-8-sig")
            st.download_button("دانلود CSV نتایج", csv, "results.csv", "text/csv", key="sr_dl")


# ---------------------------
# Help tab (Client)
# ---------------------------
if not is_admin:
    with tab_help:
        st.subheader("راهنما")
        st.write("شما در حالت مشتری هستید و فقط امکان مشاهده فایل‌ها و جستجو را دارید.")
        st.write("اطلاعات مالک/شماره تماس/یادداشت داخلی فقط برای مدیر نمایش داده می‌شود.")
        st.write("قیمت‌ها بر حسب **میلیون** هستند (مثلاً 5 میلیارد = 5000).")
        st.write("برای ملک‌هایی مثل زمین/اداری/تجاری، نمایش اتاق خواب انجام نمی‌شود.")
