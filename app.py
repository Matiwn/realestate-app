import os
import re
from datetime import datetime

import pandas as pd
import psycopg2
import streamlit as st


# =========================
# Streamlit config (ONLY ONCE)
# =========================
st.set_page_config(page_title="سیستم املاک", layout="wide")


# =========================
# ENV
# =========================
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")
CLIENT_PASSWORD = os.environ.get("CLIENT_PASSWORD", "1234")


# =========================
# Helpers: money formatting
# =========================
def toman_str_from_million(x) -> str:
    """DB unit: million. 5000 => 5,000,000,000 تومان"""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    try:
        toman = int(round(float(x) * 1_000_000))
        return f"{toman:,} تومان"
    except Exception:
        return ""


def billion_str_from_million(x) -> str:
    """DB unit: million. 5000 => 5.00 میلیارد"""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    try:
        b = float(x) / 1000.0
        if b >= 1:
            return f"{b:.2f} میلیارد"
        return f"{float(x):.0f} میلیون"
    except Exception:
        return ""


def normalize_deal_type(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if "رهن" in s or "اجاره" in s:
        return "رهن و اجاره"
    if "خرید" in s or "فروش" in s:
        return "خرید و فروش"
    return s


def parse_price_million(v) -> float | None:
    """
    Parse user/excel price into 'million' unit.
    Examples:
      5 میلیارد => 5000
      5000 => 5000
      200 میلیون => 200
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

    m = re.search(r"(\d+)", s)
    if m:
        raw = float(m.group(1))
        # if user typed toman big number, convert to million
        if raw >= 1_000_000:
            return raw / 1_000_000.0
        return raw

    return None


def now_utc():
    return datetime.utcnow()


# =========================
# DB connection (stable + reconnect)
# =========================
@st.cache_resource
def _make_conn():
    if not DATABASE_URL:
        st.error("DATABASE_URL تنظیم نشده. در سرویس/سرور مقدار DATABASE_URL را قرار بده.")
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

        # safety migrations
        cur.execute("alter table properties add column if not exists bedrooms integer;")
        cur.execute("alter table properties add column if not exists description text;")
        cur.execute("alter table applicants add column if not exists notes text;")
        cur.execute("alter table applicants add column if not exists bedrooms_min integer;")
        cur.execute("alter table applicants add column if not exists budget_min_million numeric;")
        cur.execute("alter table applicants add column if not exists budget_max_million numeric;")


# =========================
# Cached lookups for filters
# =========================
@st.cache_data(ttl=180)
def fetch_distinct(conn_dsn: str, col: str):
    conn = get_conn_safe()
    df = pd.read_sql_query(
        f"select distinct {col} from properties where {col} is not null and trim({col})<>'' order by {col}",
        conn
    )
    return df[col].tolist()


@st.cache_data(ttl=120)
def fetch_minmax(conn_dsn: str):
    conn = get_conn_safe()
    df = pd.read_sql_query(
        "select min(price_million) as min_price, max(price_million) as max_price from properties",
        conn
    )
    if df.empty:
        return 0.0, 0.0
    mn = df.loc[0, "min_price"]
    mx = df.loc[0, "max_price"]
    mn = 0.0 if mn is None or (isinstance(mn, float) and pd.isna(mn)) else float(mn)
    mx = 0.0 if mx is None or (isinstance(mx, float) and pd.isna(mx)) else float(mx)
    return mn, mx


def clear_caches():
    try:
        fetch_distinct.clear()
        fetch_minmax.clear()
    except Exception:
        pass


# =========================
# Authentication (simple)
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
    st.warning("برای استفاده از برنامه، از نوار کناری وارد شوید.")
    st.stop()

is_admin = st.session_state.role == "admin"

# =========================
# Init DB
# =========================
conn = get_conn_safe()
ensure_tables(conn)

st.title("سیستم املاک")


# =========================
# Tabs
# =========================
if is_admin:
    tab_list_admin, tab_upload, tab_search, tab_add_edit, tab_applicants = st.tabs(
        ["لیست فایل‌ها (مدیر)", "آپلود/آپدیت", "جستجو", "ثبت/ویرایش ملک", "متقاضیان"]
    )
else:
    tab_list, tab_search, tab_help = st.tabs(["فایل‌ها", "جستجو", "راهنما"])


# =========================
# Client List
# =========================
def render_client_list():
    st.subheader("فایل‌های موجود")

    min_p, max_p = fetch_minmax(DATABASE_URL)
    if max_p <= 0:
        max_p = 10000.0

    q = st.text_input("جستجوی سریع", placeholder="کد فایل / منطقه / نوع ملک ...", key="cl_q")
    deal = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], key="cl_deal")
    price_rng = st.slider(
        "بازه بودجه (میلیون)",
        min_value=float(min_p),
        max_value=float(max_p),
        value=(float(min_p), float(max_p)),
        step=50.0,
        key="cl_price_rng",
    )

    where = ["1=1"]
    params = []

    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(file_code ILIKE %s OR region ILIKE %s OR property_type ILIKE %s)")
        params += [like, like, like]

    if deal != "همه":
        where.append("deal_type = %s")
        params.append(deal)

    # price filter: include rows with NULL price (optional) => but for list, we keep only ranged or null
    where.append("(price_million is null OR (price_million >= %s AND price_million <= %s))")
    params += [float(price_rng[0]), float(price_rng[1])]

    conn = get_conn_safe()
    df = pd.read_sql_query(
        f"""
        select file_code, deal_type, region, property_type, area_m2, bedrooms,
               price_million, description, updated_at
        from properties
        where {" and ".join(where)}
        order by updated_at desc nulls last
        limit 200
        """,
        conn,
        params=tuple(params)
    )

    if df.empty:
        st.info("نتیجه‌ای پیدا نشد.")
        return

    df["قیمت (میلیارد)"] = df["price_million"].apply(billion_str_from_million)
    df["قیمت (تومان)"] = df["price_million"].apply(toman_str_from_million)

    show = df.drop(columns=["price_million"])
    st.dataframe(show, use_container_width=True)


# =========================
# Admin List
# =========================
def render_admin_list():
    st.subheader("لیست فایل‌ها (مدیر)")

    q = st.text_input("جستجوی سریع", placeholder="کد فایل / منطقه / نوع ملک ...", key="al_q")
    deal = st.selectbox("نوع معامله", ["همه", "خرید و فروش", "رهن و اجاره"], key="al_deal")
    limit = st.selectbox("تعداد نمایش", [50, 100, 200, 500], index=1, key="al_limit")

    where = ["1=1"]
    params = []

    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(file_code ILIKE %s OR region ILIKE %s OR property_type ILIKE %s)")
        params += [like, like, like]

    if deal != "همه":
        where.append("deal_type = %s")
        params.append(deal)

    conn = get_conn_safe()
    df = pd.read_sql_query(
        f"""
        select file_code, deal_type, property_type, region, area_m2, bedrooms,
               price_million, owner_name, owner_phone, updated_at
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

    df["قیمت (میلیارد)"] = df["price_million"].apply(billion_str_from_million)
    df["قیمت (تومان)"] = df["price_million"].apply(toman_str_from_million)
    st.dataframe(df.drop(columns=["price_million"]), use_container_width=True)


# =========================
# Upload Excel (Admin)
# =========================
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
    find_col("owner_name", lambda n: ("مالک" in n) and (("نام" in n) or ("اسم" in n)))
    find_col("owner_phone", lambda n: (("تماس" in n and "مالک" in n) or ("شماره" in n and "مالک" in n) or ("موبایل" in n and "مالک" in n)))
    find_col("internal_notes", lambda n: ("یادداشت" in n) or ("داخلی" in n) or ("نکته" in n))

    # price total
    find_col("price_total", lambda n: ("قیمتکل" in n) or (("قیمت" in n) and ("کل" in n)))
    if "price_total" not in col_map:
        price_like = [c for c in cols if "قیمت" in cols_norm[c]]
        if len(price_like) == 1:
            col_map["price_total"] = price_like[0]

    required = ["file_code", "deal_type", "region", "property_type", "area_m2", "price_total"]
    missing = [k for k in required if k not in col_map]
    if missing:
        st.error("ستون‌های لازم پیدا نشد: " + "، ".join(missing))
        st.info("نام ستون‌های شیت Database:\n- " + "\n- ".join([str(c) for c in cols]))
        st.stop()

    out = pd.DataFrame({
        "file_code": df[col_map["file_code"]].astype(str).str.strip(),
        "deal_type": df[col_map["deal_type"]].apply(normalize_deal_type),
        "region": df[col_map["region"]].astype(str).str.strip(),
        "address": df[col_map["address"]].astype(str).str.strip() if "address" in col_map else "",
        "area_m2": pd.to_numeric(df[col_map["area_m2"]], errors="coerce"),
        "price_million": df[col_map["price_total"]].apply(parse_price_million),
        "property_type": df[col_map["property_type"]].astype(str).str.strip(),
        "bedrooms": pd.to_numeric(df[col_map["bedrooms"]], errors="coerce") if "bedrooms" in col_map else None,
        "description": df[col_map["description"]].astype(str).str.strip() if "description" in col_map else "",
        "owner_name": df[col_map["owner_name"]].astype(str).str.strip() if "owner_name" in col_map else "",
        "owner_phone": df[col_map["owner_phone"]].astype(str).str.strip() if "owner_phone" in col_map else "",
        "internal_notes": df[col_map["internal_notes"]].astype(str).str.strip() if "internal_notes" in col_map else "",
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
                str(r["file_code"]).strip(),
                r["deal_type"],
                r["region"],
                r["address"],
                None if pd.isna(r["area_m2"]) else float(r["area_m2"]),
                None if (r["price_million"] is None or (isinstance(r["price_million"], float) and pd.isna(r["price_million"]))) else float(r["price_million"]),
                r["property_type"],
                None if r.get("bedrooms") is None or (isinstance(r.get("bedrooms"), float) and pd.isna(r.get("bedrooms"))) else int(float(r.get("bedrooms"))),
                r["description"],
                r["owner_name"],
                r["owner_phone"],
                r["internal_notes"],
                now_utc(),
            ))
            rows += 1
    return rows


# =========================
# Applicants (FIXED: display + matching)
# =========================
def applicants_tab(conn):
    st.subheader("متقاضیان (فقط مدیر)")

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

    # ---------- form (add/edit)
    with left:
        st.markdown("### ثبت / ویرایش متقاضی")

        mode = st.radio(
            "حالت",
            ["ثبت جدید", "ویرایش"],
            horizontal=True,
            key="app_mode_radio_unique",
        )

        selected_id = None
        selected_row = None

        if mode == "ویرایش":
            if apps.empty:
                st.info("متقاضی‌ای وجود ندارد.")
            else:
                label_map = {
                    int(r["id"]): f'#{int(r["id"])} - {str(r.get("full_name") or "").strip()} ({str(r.get("phone") or "").strip()})'
                    for _, r in apps.iterrows()
                }
                selected_id = st.selectbox(
                    "انتخاب متقاضی",
                    list(label_map.keys()),
                    format_func=lambda x: label_map.get(x, str(x)),
                    key="app_selectbox_edit_unique",
                )
                selected_row = apps[apps["id"] == selected_id].iloc[0].to_dict()

        def val(key, default=""):
            if not selected_row:
                return default
            v = selected_row.get(key)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return default
            return v

        full_name = st.text_input("نام و نام خانوادگی", value=str(val("full_name", "")), key="app_fullname_unique")
        phone = st.text_input("شماره تماس", value=str(val("phone", "")), key="app_phone_unique")

        deal_type = st.selectbox(
            "نوع معامله",
            ["خرید و فروش", "رهن و اجاره"],
            index=0 if str(val("deal_type", "خرید و فروش")) == "خرید و فروش" else 1,
            key="app_deal_unique"
        )

        desired_property_type = st.text_input("نوع ملک موردنظر (اختیاری)", value=str(val("desired_property_type", "")), key="app_dptype_unique")
        region = st.text_input("منطقه (اختیاری)", value=str(val("region", "")), key="app_region_unique")

        b1, b2 = st.columns(2)
        with b1:
            budget_min = st.number_input(
                "بودجه از (میلیون)",
                min_value=0.0,
                value=float(val("budget_min_million", 0.0) or 0.0),
                step=50.0,
                key="app_budget_min_unique"
            )
        with b2:
            budget_max = st.number_input(
                "بودجه تا (میلیون) (0 یعنی نامحدود)",
                min_value=0.0,
                value=float(val("budget_max_million", 0.0) or 0.0),
                step=50.0,
                key="app_budget_max_unique"
            )

        bedrooms_min = st.number_input(
            "حداقل خواب (اختیاری)",
            min_value=0,
            value=int(val("bedrooms_min", 0) or 0),
            step=1,
            key="app_bedmin_unique"
        )

        notes = st.text_area("توضیحات", value=str(val("notes", "")), key="app_notes_unique")

        if mode == "ثبت جدید":
            if st.button("ثبت متقاضی", key="app_add_btn_unique"):
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
                                full_name.strip(),
                                phone.strip(),
                                deal_type,
                                desired_property_type.strip(),
                                region.strip(),
                                float(budget_min) if budget_min else 0.0,
                                float(budget_max) if budget_max else 0.0,
                                int(bedrooms_min) if bedrooms_min else 0,
                                notes.strip(),
                            )
                        )
                    st.success("متقاضی ثبت شد.")
                    st.rerun()

        else:
            if selected_id is not None and st.button("ذخیره تغییرات", key="app_save_btn_unique"):
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
                            full_name.strip(),
                            phone.strip(),
                            deal_type,
                            desired_property_type.strip(),
                            region.strip(),
                            float(budget_min) if budget_min else 0.0,
                            float(budget_max) if budget_max else 0.0,
                            int(bedrooms_min) if bedrooms_min else 0,
                            notes.strip(),
                            int(selected_id),
                        )
                    )
                st.success("ویرایش ذخیره شد.")
                st.rerun()

    # ---------- list + match
    with right:
        st.markdown("### لیست متقاضیان (نمایش درست میلیارد/تومان)")

        if apps.empty:
            st.info("هنوز متقاضی ثبت نشده است.")
        else:
            view = apps.copy()
            # ✅ show budgets nicely
            view["بودجه از (میلیارد)"] = view["budget_min_million"].apply(billion_str_from_million)
            view["بودجه تا (میلیارد)"] = view["budget_max_million"].apply(billion_str_from_million)
            view["بودجه از (تومان)"] = view["budget_min_million"].apply(toman_str_from_million)
            view["بودجه تا (تومان)"] = view["budget_max_million"].apply(toman_str_from_million)

            show_cols = [
                "id", "full_name", "phone", "deal_type", "desired_property_type", "region",
                "budget_min_million", "budget_max_million",
                "بودجه از (میلیارد)", "بودجه تا (میلیارد)",
                "bedrooms_min", "updated_at"
            ]
            st.dataframe(view[show_cols], use_container_width=True)

        st.divider()
        st.markdown("### مچ خودکار متقاضی با فایل‌ها (FIXED)")

        if apps.empty:
            st.info("ابتدا متقاضی ثبت کنید.")
        else:
            label_map2 = {
                int(r["id"]): f'#{int(r["id"])} - {str(r.get("full_name") or "").strip()} ({str(r.get("phone") or "").strip()})'
                for _, r in apps.iterrows()
            }
            mid = st.selectbox(
                "انتخاب متقاضی برای مچ",
                list(label_map2.keys()),
                format_func=lambda x: label_map2.get(x, str(x)),
                key="match_select_unique",
            )
            mr = apps[apps["id"] == mid].iloc[0].to_dict()

            where = ["1=1"]
            params = []

            # deal type (strict)
            dt = (mr.get("deal_type") or "").strip()
            if dt:
                where.append("deal_type = %s")
                params.append(dt)

            # desired property type (contains)
            dpt = (mr.get("desired_property_type") or "").strip()
            if dpt:
                where.append("property_type ILIKE %s")
                params.append(f"%{dpt}%")

            # region (contains)
            reg = (mr.get("region") or "").strip()
            if reg:
                where.append("region ILIKE %s")
                params.append(f"%{reg}%")

            # budgets (0 => unlimited)
            bmin = mr.get("budget_min_million")
            bmax = mr.get("budget_max_million")
            try:
                bmin_f = float(bmin) if bmin is not None and not pd.isna(bmin) else 0.0
            except Exception:
                bmin_f = 0.0
            try:
                bmax_f = float(bmax) if bmax is not None and not pd.isna(bmax) else 0.0
            except Exception:
                bmax_f = 0.0

            # IMPORTANT: price_million can be NULL in some files.
            # For matching budgets, we only match rows that have price_million not null.
            if bmin_f > 0 or bmax_f > 0:
                where.append("price_million is not null")

            if bmin_f > 0:
                where.append("price_million >= %s")
                params.append(bmin_f)

            if bmax_f > 0:
                where.append("price_million <= %s")
                params.append(bmax_f)

            # bedrooms
            bdm = mr.get("bedrooms_min")
            try:
                bdm_i = int(bdm) if bdm is not None and not pd.isna(bdm) else 0
            except Exception:
                bdm_i = 0
            if bdm_i > 0:
                where.append("(bedrooms is not null and bedrooms >= %s)")
                params.append(bdm_i)

            limit = st.selectbox("حداکثر نتایج", [50, 100, 200, 500], index=1, key="match_limit_unique")

            q = f"""
              select file_code, deal_type, region, property_type, bedrooms, area_m2, price_million,
                     address, description, updated_at
              from properties
              where {" and ".join(where)}
              order by updated_at desc nulls last
              limit %s
            """
            params2 = params + [int(limit)]
            res = pd.read_sql_query(q, conn, params=tuple(params2))

            if res.empty:
                st.warning("فایل مطابق پیدا نشد. (با بودجه/نوع/منطقه کمتر محدود کن)")
            else:
                res["قیمت (میلیارد)"] = res["price_million"].apply(billion_str_from_million)
                res["قیمت (تومان)"] = res["price_million"].apply(toman_str_from_million)
                st.dataframe(res.drop(columns=["price_million"]), use_container_width=True)


# =========================
# Render tabs
# =========================
if is_admin:
    with tab_list_admin:
        render_admin_list()

    with tab_upload:
        st.subheader("آپلود اکسل و بروزرسانی (فقط مدیر)")
        st.caption("اکسل باید شیت Database داشته باشد. قیمت کل بر حسب میلیون است (۵ میلیارد = ۵۰۰۰).")

        up = st.file_uploader("آپلود Excel", type=["xlsx"], key="adm_upload_excel")
        if up is not None:
            df = load_excel(up)
            st.write("پیش‌نمایش:", df.head(30))
            if st.button("بروزرسانی دیتابیس (Upsert)", key="adm_do_upsert"):
                conn = get_conn_safe()
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
        try:
            conn = get_conn_safe()
            logs = pd.read_sql_query(
                "select uploaded_at, rows_read, rows_upserted from uploads order by id desc limit 20",
                conn
            )
            st.dataframe(logs, use_container_width=True)
        except Exception:
            st.info("لاگ آپلودها فعلاً در دسترس نیست.")

    with tab_search:
        st.subheader("جستجو")
        conn = get_conn_safe()

        try:
            prop_opts = [""] + fetch_distinct(DATABASE_URL, "property_type")
            region_opts = [""] + fetch_distinct(DATABASE_URL, "region")
        except Exception:
            prop_opts = [""]
            region_opts = [""]

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            deal = st.selectbox("نوع معامله", ["", "خرید و فروش", "رهن و اجاره"], key="sr_deal")
        with c2:
            ptype = st.selectbox("نوع ملک", prop_opts, key="sr_ptype")
        with c3:
            region = st.selectbox("منطقه", region_opts, key="sr_region")
        with c4:
            file_code_q = st.text_input("کد فایل (اختیاری)", key="sr_code")

        d1, d2, d3, d4 = st.columns(4)
        with d1:
            min_price = st.number_input("قیمت از (میلیون)", min_value=0.0, value=0.0, step=50.0, key="sr_min_price")
        with d2:
            max_price = st.number_input("قیمت تا (میلیون) (0 یعنی محدودیت ندارد)", min_value=0.0, value=0.0, step=50.0, key="sr_max_price")
        with d3:
            min_area = st.number_input("متراژ از", min_value=0.0, value=0.0, step=10.0, key="sr_min_area")
        with d4:
            max_area = st.number_input("متراژ تا (0 یعنی محدودیت ندارد)", min_value=0.0, value=0.0, step=10.0, key="sr_max_area")

        if st.button("جستجو", key="sr_btn"):
            where = ["1=1"]
            params = []

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

            if min_price > 0:
                where.append("price_million >= %s")
                params.append(float(min_price))
            if max_price > 0:
                where.append("price_million <= %s")
                params.append(float(max_price))

            if min_area > 0:
                where.append("area_m2 >= %s")
                params.append(float(min_area))
            if max_area > 0:
                where.append("area_m2 <= %s")
                params.append(float(max_area))

            q = f"""
              select file_code, deal_type, region, property_type, bedrooms, area_m2, price_million,
                     address, description, updated_at
              from properties
              where {" and ".join(where)}
              order by updated_at desc nulls last
              limit 500
            """
            res = pd.read_sql_query(q, conn, params=tuple(params))
            if res.empty:
                st.warning("هیچ نتیجه‌ای پیدا نشد.")
            else:
                res["قیمت (میلیارد)"] = res["price_million"].apply(billion_str_from_million)
                res["قیمت (تومان)"] = res["price_million"].apply(toman_str_from_million)
                st.dataframe(res.drop(columns=["price_million"]), use_container_width=True)

    with tab_add_edit:
        st.subheader("ثبت/ویرایش ملک (فقط مدیر)")
        st.info("این بخش قبلاً داشتید؛ اگر نیاز داری همینجا هم کامل‌ترش کنم، بگو (الان تمرکز روی متقاضیان و پایداری بود).")

    with tab_applicants:
        applicants_tab(get_conn_safe())

else:
    with tab_list:
        render_client_list()

    with tab_search:
        st.subheader("جستجو")
        st.write("برای جستجوی دقیق‌تر، از بخش فایل‌ها استفاده کن (نسخه مشتری ساده‌تره).")

    with tab_help:
        st.subheader("راهنما")
        st.write("قیمت‌ها بر حسب میلیون هستند. مثال: ۵ میلیارد = ۵۰۰۰")
