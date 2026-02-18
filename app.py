import os
import psycopg2
import pandas as pd
import streamlit as st


# ---------------------------
# PAGE CONFIG
# ---------------------------

st.set_page_config(layout="wide")


# ---------------------------
# DATABASE CONNECTION
# ---------------------------

DATABASE_URL = os.environ.get("DATABASE_URL")

@st.cache_resource
def get_conn():
    return psycopg2.connect(DATABASE_URL)

conn = get_conn()


# ---------------------------
# GET TENANT FROM DOMAIN
# ---------------------------

def get_current_tenant():

    host = st.headers.get("Host", "")

    if not host:
        return None

    subdomain = host.split(".")[0].lower()

    query = """
    select *
    from tenants
    where subdomain = %s
    and is_active = true
    limit 1
    """

    df = pd.read_sql(query, conn, params=[subdomain])

    if df.empty:
        return None

    return df.iloc[0]


tenant = get_current_tenant()


# ---------------------------
# IF TENANT NOT FOUND
# ---------------------------

if tenant is None:

    st.error("دامنه معتبر نیست")

    st.stop()


tenant_id = tenant["id"]


# ---------------------------
# APPLY WHITE LABEL
# ---------------------------

primary = tenant["primary_color"] or "#000000"
secondary = tenant["secondary_color"] or "#FFFFFF"

st.markdown(f"""
<style>

.main {{
background-color: {secondary};
}}

.stButton>button {{
background-color: {primary};
color: white;
border-radius: 8px;
}}

</style>
""", unsafe_allow_html=True)


# ---------------------------
# HEADER
# ---------------------------

col1, col2 = st.columns([1,4])

with col1:
    st.image(tenant["logo_url"], width=140)

with col2:
    st.title(tenant["site_title"])



# ---------------------------
# LOAD PROPERTIES
# ---------------------------

query = """
select *
from properties
where tenant_id = %s
order by id desc
"""

df = pd.read_sql(query, conn, params=[tenant_id])


# ---------------------------
# SHOW FILES
# ---------------------------

st.subheader("لیست فایل‌ها")

st.dataframe(df, use_container_width=True)


# ---------------------------
# ADD NEW FILE
# ---------------------------

st.subheader("ثبت فایل جدید")

with st.form("add_form"):

    code = st.text_input("کد فایل")
    price = st.number_input("قیمت")
    area = st.number_input("متراژ")

    submit = st.form_submit_button("ثبت")


    if submit:

        insert = """
        insert into properties
        (code, price, area, tenant_id)
        values (%s,%s,%s,%s)
        """

        cursor = conn.cursor()

        cursor.execute(insert, (code, price, area, tenant_id))

        conn.commit()

        st.success("ثبت شد")

        st.rerun()
