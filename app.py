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
    """
    Pooler/Network might drop idle connections.
    This function pings and recreates if needed.
    """
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
        conn = _make_conn()
        return conn


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

    # optional columns
    find_col("description", lambda n: ("توضیحات" in n) or ("شرح" in n))
    find_col("owner_name", lambda n: ("مالک" in n) and (("نام" in n) or ("اسم" in n)))
    find_col(
        "owner_phone",
        lambda n: (("تماس" in n and "مالک" in n) or ("شماره" in n and "مالک" in n) or ("موبایل" in n and "مالک" in n))
    )
    find_col("internal_notes", lambda n: ("یادداشت" in n) or ("داخلی" in n) or ("نکته" in n))

    # price total (prefer "قیمت کل")
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
# Cached dropdown data (speed)
# ---------------------------
@st.cache_data(ttl=180)
def fetch_distinct_cached(colname: str):
    conn = get_conn_safe()
    q = f"select distinct {colname} from properties where {colname} is not null and trim({colname})<>'' order by {colname}"
    df = pd.read_sql_query(q, conn)
    return df[colname].tolist()


def clear_caches():
    try:
        fetch_distinct_cached.clear()
    except Exception:
        pass


# ---------------------------
# DB Writes
# ---------------------------
def upsert_properties(conn, df: pd.DataFrame) -> int:
    rows = 0
    with conn.cursor() as cur:
        for _, r in df.iterrows():
            cur.execute("""
            insert into properties
              (file_code, deal_type, region, address, area_m2, price_million, property_type, description,
               owner_name, owner_phone, internal_notes, updated_at)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (file_code) do update set
              deal_type=excluded.deal_type,
              region=excluded.region,
              address=excluded.address,
              area_m2=excluded.area_m2,
              price_million=excluded.price_million,
              property_type=excluded.property_type,
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


def upsert_one(conn, row: dict):
    with conn.cursor() as cur:
        cur.execute("""
        insert into properties
          (file_code, deal_type, region, address, area_m2, price_million, property_type, description,
           owner_name, owner_phone, internal_notes, updated_at)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (file_code) do update set
          deal_type=excluded.deal_type,
          region=excluded.region,
          address=excluded.address,
          area_m2=excluded.area_m2,
          price_million=excluded.price_million,
          property_type=excluded.property_type,
          description=excluded.description,
          owner_name=excluded.owner_name,
          owner_phone=excluded.owner_phone,
          internal_notes=excluded.internal_notes,
          updated_at=excluded.updated_at
        """, (
            row["file_code"],
            row["deal_type"],
            row["region"],
            row["address"],
            row["area_m2"],
            row["price_million"],
            row["property_type"],
            row["description"],
            row["owner_name"],
            row["owner_phone"],
            row["internal_notes"],
            now_utc_ts(),
        ))


# ---------------------------
# App UI
# ---------------------------
st.title("مشاور املاک نور")

conn = get_conn_safe()
ensure_tables(conn)

# Session state for role
if "role" not in st.session_state:
    st.session_state.role = None

with st.sidebar:
    st.header("ورود")
    role_ui = st.selectbox("نقش", ["مشتری", "مدیر"], index=0)
    pwd = st.text_input("رمز", type="password")
    c1, c2 = st.columns(2)

    if c1.button("ورود"):
        if role_ui == "مدیر" and pwd == ADMIN_PASSWORD:
            st.session_state.role = "admin"
            st.success("ورود مدیر موفق بود.")
        elif role_ui == "مشتری" and pwd == CLIENT_PASSWORD:
            st.session_state.role = "client"
            st.success("ورود مشتری موفق بود.")
        else:
            st.error("رمز اشتباه است.")

    if c2.button("خروج"):
        st.session_state.role = None
        st.info("خارج شدید.")

if st.session_state.role is None:
    st.warning("برای استفاده از برنامه، از نوار کناری وارد شوید.")
    st.stop()

is_admin = st.session_state.role == "admin"

# Tabs
if is_admin:
    tab_upload, tab_search, tab_add = st.tabs(["آپلود/آپدیت", "جستجو", "ثبت/ویرایش ملک"])
else:
    tab_list, tab_search, tab_help = st.tabs(["فایل‌ها", "جستجو", "راهنما"])


# ---------------------------
# Client: List tab (first tab) - Card style
# ---------------------------
if not is_admin:
    with tab_list:
        st.subheader("فایل‌های موجود")

        # --- Filters / Sorting ---
        f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.2, 1.4])

        with f1:
            quick_q = st.text_input("جستجوی سریع", placeholder="کد فایل / منطقه / نوع ملک ...")

        with f2:
            deal_filter = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], index=0)

        with f3:
            sort_mode = st.selectbox(
                "مرتب‌سازی",
                ["جدیدترین", "ارزان‌ترین", "گران‌ترین", "بیشترین متراژ", "کمترین متراژ"],
                index=0
            )

        with f4:
            page_size = st.selectbox("تعداد در هر صفحه", [12, 24, 36, 60], index=1)

        page = st.number_input("صفحه", min_value=1, value=1, step=1)
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
          file_code, deal_type, region, property_type, area_m2,
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
            def safe_txt(x):
                if x is None:
                    return ""
                s = str(x)
                return "" if s.lower() == "nan" else s

            cols = st.columns(3)
            for i, row in df.iterrows():
                col = cols[i % 3]

                file_code = safe_txt(row.get("file_code"))
                deal_type = safe_txt(row.get("deal_type"))
                region = safe_txt(row.get("region"))
                ptype = safe_txt(row.get("property_type"))
                area = row.get("area_m2")
                price_m = row.get("price_million")
                address = safe_txt(row.get("address"))
                desc = safe_txt(row.get("description"))
                updated = row.get("updated_at")

                price_toman = toman_str_from_million(price_m)

                area_txt = ""
                try:
                    if area is not None and not (isinstance(area, float) and pd.isna(area)):
                        area_txt = f"{float(area):.0f} متر"
                except Exception:
                    area_txt = safe_txt(area)

                with col:
                    st.markdown("---")
                    st.markdown(f"### فایل {file_code}")

                    line1 = " | ".join([x for x in [deal_type, ptype, f"منطقه {region}" if region else ""] if x])
                    if line1:
                        st.caption(line1)

                    left, right = st.columns([1.2, 1])
                    with left:
                        st.markdown(f"**قیمت:** {price_toman if price_toman else 'نامشخص'}")
                    with right:
                        st.markdown(f"**متراژ:** {area_txt if area_txt else '—'}")

                    if desc:
                        preview = desc if len(desc) <= 90 else desc[:90] + "…"
                        st.write(preview)

                    with st.expander("جزئیات"):
                        if address:
                            st.write(f"**لوکیشن:** {address}")
                        if desc:
                            st.write(f"**توضیحات:** {desc}")
                        if updated:
                            st.caption(f"آخرین بروزرسانی: {updated}")

            st.markdown("---")
            out = df.copy()
            out["price_toman"] = out["price_million"].apply(toman_str_from_million)
            csv = out.drop(columns=["price_million"]).to_csv(index=False).encode("utf-8-sig")
            st.download_button("دانلود CSV همین صفحه", csv, f"files_page_{page}.csv", "text/csv")


# ---------------------------
# Admin: Upload / Update tab
# ---------------------------
if is_admin:
    with tab_upload:
        st.subheader("آپلود اکسل و بروزرسانی (فقط مدیر)")
        st.caption("اکسل باید شیت Database داشته باشد. قیمت کل بر حسب میلیون است (مثلاً ۵ میلیارد = ۵۰۰۰).")

        up = st.file_uploader("آپلود Excel", type=["xlsx"])
        if up is not None:
            df = load_excel(up)
            st.write("پیش‌نمایش:", df.head(30))

            if st.button("بروزرسانی دیتابیس (Merge/Upsert)"):
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
# Admin: Add / Edit tab
# ---------------------------
if is_admin:
    with tab_add:
        st.subheader("ثبت یا ویرایش ملک (فقط مدیر)")
        st.caption("اگر کد فایل موجود باشد آپدیت می‌شود؛ اگر نباشد ثبت جدید انجام می‌شود.")

        a, b, c = st.columns(3)
        with a:
            file_code = st.text_input("کد فایل (اجباری)")
            deal_type = st.selectbox("نوع معامله", ["خرید و فروش", "رهن و اجاره"])
            property_type = st.text_input("نوع ملک", placeholder="مثلاً آپارتمان / دوبلکس / ...")

        with b:
            region = st.text_input("منطقه", placeholder="مثلاً 1 یا سعادت‌آباد")
            area_m2 = st.number_input("متراژ", min_value=0.0, value=0.0, step=1.0)
            price_million = st.number_input("قیمت کل (میلیون)", min_value=0.0, value=0.0, step=50.0)

        with c:
            owner_name = st.text_input("نام مالک (فقط مدیر)")
            owner_phone = st.text_input("شماره تماس مالک (فقط مدیر)")

        address = st.text_input("آدرس/لوکیشن")
        description = st.text_area("توضیحات")
        internal_notes = st.text_area("یادداشت داخلی (فقط مدیر)")

        s1, s2 = st.columns(2)

        if s1.button("ثبت / آپدیت"):
            if not file_code.strip():
                st.error("کد فایل اجباری است.")
            else:
                row = {
                    "file_code": file_code.strip(),
                    "deal_type": deal_type,
                    "region": region.strip(),
                    "address": address.strip(),
                    "area_m2": float(area_m2) if area_m2 else None,
                    "price_million": float(price_million) if price_million else None,
                    "property_type": property_type.strip(),
                    "description": description.strip(),
                    "owner_name": owner_name.strip(),
                    "owner_phone": owner_phone.strip(),
                    "internal_notes": internal_notes.strip(),
                }
                conn = get_conn_safe()
                upsert_one(conn, row)
                clear_caches()
                st.success("ثبت/آپدیت انجام شد (دایمی).")

        if s2.button("حذف این کد فایل"):
            if not file_code.strip():
                st.error("کد فایل را وارد کنید.")
            else:
                conn = get_conn_safe()
                with conn.cursor() as cur:
                    cur.execute("delete from properties where file_code = %s", (file_code.strip(),))
                clear_caches()
                st.success("حذف شد.")


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

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        deal = st.selectbox("نوع معامله", deal_opts, index=0)
        ptype = st.selectbox("نوع ملک", prop_opts, index=0)

    with c2:
        region = st.selectbox("منطقه", region_opts, index=0)
        file_code_q = st.text_input("کد فایل (اختیاری)")

    with c3:
        min_area = st.number_input("متراژ از", min_value=0.0, value=0.0, step=10.0)
        max_area = st.number_input("متراژ تا (0 یعنی محدودیت ندارد)", min_value=0.0, value=0.0, step=10.0)

    with c4:
        min_price = st.number_input("قیمت از (میلیون)", min_value=0.0, value=0.0, step=50.0)
        max_price = st.number_input("قیمت تا (میلیون) (0 یعنی محدودیت ندارد)", min_value=0.0, value=0.0, step=50.0)

    if st.button("جستجو"):
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

        if is_admin:
            select_cols = """
              file_code, deal_type, region, property_type, area_m2, price_million,
              address, description, owner_name, owner_phone, internal_notes, updated_at
            """
        else:
            select_cols = """
              file_code, deal_type, region, property_type, area_m2, price_million,
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
            res = res.drop(columns=["price_million"])

            st.write(f"تعداد نتایج: {len(res)}")
            st.dataframe(res, use_container_width=True)

            csv = res.to_csv(index=False).encode("utf-8-sig")
            st.download_button("دانلود CSV نتایج", csv, "results.csv", "text/csv")


# ---------------------------
# Help tab (Client)
# ---------------------------
if not is_admin:
    with tab_help:
        st.subheader("راهنما")
        st.write("شما در حالت مشتری هستید و فقط امکان مشاهده فایل‌ها و جستجو را دارید.")
        st.write("اطلاعات مالک/شماره تماس/یادداشت داخلی فقط برای مدیر نمایش داده می‌شود.")
        st.write("قیمت‌ها بر حسب **میلیون** هستند (مثلاً 5 میلیارد = 5000).")
```

