import os
import re
from datetime import datetime

import pandas as pd
import streamlit as st
import psycopg2


# ---------------------------
# Secrets / Passwords
# ---------------------------
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)  # Streamlit Cloud
    except Exception:
        return os.environ.get(name, default)


DATABASE_URL = get_secret("DATABASE_URL", "")
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "Admin@123")
CLIENT_PASSWORD = get_secret("CLIENT_PASSWORD", "1234")


def now_utc_ts():
    # psycopg2 can pass datetime objects; keep timestamp type in DB
    return datetime.utcnow()


# ---------------------------
# DB helpers (Supabase/Postgres)
# ---------------------------
@st.cache_resource
def get_conn():
    if not DATABASE_URL:
        st.error("DATABASE_URL در Secrets تنظیم نشده است.")
        st.stop()
    # keepalives can help stability on some networks
    return psycopg2.connect(
        DATABASE_URL,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )


def get_conn_safe():
    """
    Streamlit Cloud + pooler sometimes drops connections.
    This wrapper pings and recreates the connection if needed.
    """
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("select 1;")
        return conn
    except Exception:
        try:
            get_conn.clear()
        except Exception:
            pass
        conn = get_conn()
        return conn


def ensure_tables_and_policies(conn):
    # Ensure tables exist
    conn.autocommit = True
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

        # RLS + policies (safe-ish: ignore errors if already exists)
        try:
            cur.execute("alter table properties enable row level security;")
        except Exception:
            pass
        try:
            cur.execute("""
            do $$
            begin
              if not exists (select 1 from pg_policies where schemaname='public' and tablename='properties') then
                create policy "Enable all access"
                on properties for all
                using (true) with check (true);
              end if;
            end $$;
            """)
        except Exception:
            pass

        try:
            cur.execute("alter table uploads enable row level security;")
        except Exception:
            pass
        try:
            cur.execute("""
            do $$
            begin
              if not exists (select 1 from pg_policies where schemaname='public' and tablename='uploads') then
                create policy "Enable all access uploads"
                on uploads for all
                using (true) with check (true);
              end if;
            end $$;
            """)
        except Exception:
            pass


# ---------------------------
# Normalizers / Parsers
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
    واحد دیتابیس: میلیون
    مثال: 5 میلیارد = 5000
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

    # owner name/phone (optional)
    for c in cols:
        n = cols_norm[c]
        if "مالک" in n and ("نام" in n or "اسم" in n):
            col_map["owner_name"] = c
            break
    for c in cols:
        n = cols_norm[c]
        if ("تماس" in n and "مالک" in n) or ("شماره" in n and "مالک" in n) or ("موبایل" in n and "مالک" in n):
            col_map["owner_phone"] = c
            break

    # internal notes (optional)
    for c in cols:
        n = cols_norm[c]
        if "یادداشت" in n or "داخلی" in n or "نکته" in n:
            col_map["internal_notes"] = c
            break

    # PRICE: prioritize total price
    for c in cols:
        n = cols_norm[c]
        if ("قیمتکل" in n) or (("قیمت" in n) and ("کل" in n)):
            col_map["price_total"] = c
            break

    # fallback if only one price-like column exists
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
    })

    out = out[out["file_code"].notna() & (out["file_code"] != "")].copy()
    for c in ["region", "address", "property_type", "description", "owner_name", "owner_phone", "internal_notes"]:
        out[c] = out[c].replace({"nan": ""})

    out["updated_at"] = now_utc_ts()
    return out


# ---------------------------
# Cached helpers (speed)
# ---------------------------
@st.cache_data(ttl=60)
def fetch_distinct_cached(colname: str):
    conn = get_conn_safe()
    q = f"select distinct {colname} from properties where {colname} is not null and trim({colname})<>'' order by {colname}"
    df = pd.read_sql_query(q, conn)
    return df[colname].tolist()


# ---------------------------
# Upsert helpers
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
    conn.commit()
    return rows


def upsert_one(conn, row: dict) -> None:
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
    conn.commit()


# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title="سیستم جستجوی املاک", layout="wide")
st.title("سیستم جستجوی املاک (دایمی + سریع‌تر)")

conn = get_conn_safe()
ensure_tables_and_policies(conn)

# --- Login / Role ---
if "role" not in st.session_state:
    st.session_state.role = None

with st.sidebar:
    st.header("ورود")
    role_ui = st.selectbox("نقش", ["مشتری", "مدیر"], index=0)
    pwd = st.text_input("رمز", type="password")
    col_a, col_b = st.columns(2)

    if col_a.button("ورود"):
        if role_ui == "مدیر" and pwd == ADMIN_PASSWORD:
            st.session_state.role = "admin"
            st.success("ورود مدیر موفق بود.")
        elif role_ui == "مشتری" and pwd == CLIENT_PASSWORD:
            st.session_state.role = "client"
            st.success("ورود مشتری موفق بود.")
        else:
            st.error("رمز اشتباه است.")

    if col_b.button("خروج"):
        st.session_state.role = None
        st.info("خارج شدید.")

if st.session_state.role is None:
    st.warning("برای استفاده از برنامه، از نوار کناری وارد شوید.")
    st.stop()

is_admin = (st.session_state.role == "admin")

if is_admin:
    tab_upload, tab_search, tab_add = st.tabs(["آپلود/آپدیت", "جستجو", "ثبت/ویرایش ملک"])
else:
    tab_search, tab_help = st.tabs(["جستجو", "راهنما"])


# ---------------------------
# Upload tab (ADMIN only)
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

                # log uploads
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "insert into uploads(uploaded_at, rows_read, rows_upserted) values (%s,%s,%s)",
                            (now_utc_ts(), int(len(df)), int(n))
                        )
                    conn.commit()
                except Exception:
                    pass

                # clear dropdown cache so new values appear quickly
                try:
                    fetch_distinct_cached.clear()
                except Exception:
                    pass

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
# Add/Edit tab (ADMIN only)
# ---------------------------
if is_admin:
    with tab_add:
        st.subheader("ثبت یا ویرایش ملک (فقط مدیر)")
        st.caption("اگر کد فایل موجود باشد آپدیت می‌شود؛ اگر نباشد ثبت جدید انجام می‌شود.")

        c1, c2, c3 = st.columns(3)

        with c1:
            file_code = st.text_input("کد فایل (اجباری)")
            deal_type = st.selectbox("نوع معامله", ["خرید و فروش", "رهن و اجاره"])
            property_type = st.text_input("نوع ملک", placeholder="مثلاً آپارتمان / دوبلکس / ...")

        with c2:
            region = st.text_input("منطقه", placeholder="مثلاً 1 یا سعادت‌آباد")
            area_m2 = st.number_input("متراژ", min_value=0.0, value=0.0, step=1.0)
            price_million = st.number_input("قیمت کل (میلیون)", min_value=0.0, value=0.0, step=50.0)

        with c3:
            owner_name = st.text_input("نام مالک (فقط مدیر)")
            owner_phone = st.text_input("شماره تماس مالک (فقط مدیر)")

        address = st.text_input("آدرس/لوکیشن")
        description = st.text_area("توضیحات")
        internal_notes = st.text_area("یادداشت داخلی (فقط مدیر)")

        col_save, col_del = st.columns(2)

        if col_save.button("ثبت / آپدیت"):
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

                try:
                    fetch_distinct_cached.clear()
                except Exception:
                    pass

                st.success("ثبت/آپدیت انجام شد (دایمی).")

        if col_del.button("حذف این کد فایل"):
            if not file_code.strip():
                st.error("کد فایل را وارد کنید.")
            else:
                conn = get_conn_safe()
                with conn.cursor() as cur:
                    cur.execute("delete from properties where file_code = %s", (file_code.strip(),))
                conn.commit()

                try:
                    fetch_distinct_cached.clear()
                except Exception:
                    pass

                st.success("حذف شد.")


# ---------------------------
# Search tab (ADMIN + CLIENT)
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

    run = st.button("جستجو")

    if run:
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
            res["قیمت (تومان)"] = res["price_million"].apply(to_toman_from_million)
            res = res.drop(columns=["price_million"])
            st.write(f"تعداد نتایج: {len(res)}")
            st.dataframe(res, use_container_width=True)

            csv = res.to_csv(index=False).encode("utf-8-sig")
            st.download_button("دانلود CSV نتایج", csv, "results.csv", "text/csv")


# ---------------------------
# Help tab (CLIENT only)
# ---------------------------
if not is_admin:
    with tab_help:
        st.subheader("راهنما")
        st.write("شما در حالت مشتری هستید و فقط امکان جستجو و مشاهده فایل‌ها را دارید.")
        st.write("اطلاعات مالک/شماره تماس/یادداشت داخلی فقط برای مدیر نمایش داده می‌شود.")
        st.write("قیمت‌ها بر حسب **میلیون** هستند (مثلاً 5 میلیارد = 5000).")
