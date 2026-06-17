import io
import json
from pathlib import Path

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

from review_generator import generate_reviews_for_sku, ALL_COLUMNS

BASE_DIR = Path(__file__).parent
POSITIVE_FILE = BASE_DIR / "리뷰작업_긍정리뷰.xlsx"
NEGATIVE_FILE = BASE_DIR / "리뷰작업_부정리뷰.xlsx"
PRODUCTS_FILE = BASE_DIR / "products.json"

# 직접 추가한 상품(custom_products)의 영구 저장소.
# Streamlit Cloud의 로컬 파일은 재배포 시 초기화되므로, 여기서 새로 추가한
# 상품이 사라지지 않도록 Google Sheets에 저장한다.
PRODUCTS_SHEET_ID = "1E8Jkkd7Ol8Yeh2o4aLTNdfhoFCKyz-1ufhW4KF7yaBo"
PRODUCTS_SHEET_GID = 117185975
SHEET_KEYWORD_COLS = 6  # 소구키워드1~6


@st.cache_data
def load_excel(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    data = df.iloc[3:].reset_index(drop=True)
    data = data[data["product_id"].notna()].copy()
    data["product_id"] = data["product_id"].astype(str).str.strip().str.replace(r"^[^\d]+", "", regex=True)
    # 숫자로만 이뤄진 유효한 product_id만 유지 (한글·특수문자 행 제거)
    data = data[data["product_id"].str.match(r"^\d+$")]
    return data.reset_index(drop=True)


@st.cache_resource
def get_products_sheet():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(PRODUCTS_SHEET_ID)
    return next(w for w in spreadsheet.worksheets() if w.id == PRODUCTS_SHEET_GID)


def load_custom_products_from_sheet() -> list:
    rows = get_products_sheet().get_all_values()[1:]  # 1행은 헤더
    products = []
    for row in rows:
        if len(row) < 2 or not row[0].strip():
            continue
        keywords = [v.strip() for v in row[2:2 + SHEET_KEYWORD_COLS] if v.strip()]
        products.append({
            "product_id": row[0].strip(),
            "product_title": row[1].strip(),
            "appeal_points": ", ".join(keywords),
        })
    return products


def _find_sheet_row(pid: str):
    ids = get_products_sheet().col_values(1)
    for i, v in enumerate(ids[1:], start=2):  # 2행부터 (1행은 헤더)
        if v.strip() == pid:
            return i
    return None


def append_product_to_sheet(pid: str, title: str, appeal: str):
    get_products_sheet().append_row([pid, title, appeal], value_input_option="RAW")


def update_appeal_points_in_sheet(pid: str, appeal: str):
    row = _find_sheet_row(pid)
    if row:
        get_products_sheet().update(
            range_name=f"C{row}:H{row}",
            values=[[appeal, "", "", "", "", ""]],
            value_input_option="RAW",
        )


def delete_product_from_sheet(pid: str):
    row = _find_sheet_row(pid)
    if row:
        get_products_sheet().delete_rows(row)


def load_products() -> dict:
    if PRODUCTS_FILE.exists():
        with open(PRODUCTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"appeal_points": {}, "custom_products": [], "hidden_skus": []}
        for path in [POSITIVE_FILE, NEGATIVE_FILE]:
            if path.exists():
                df = load_excel(path)
                for _, row in df.drop_duplicates("product_id").iterrows():
                    pid = str(row["product_id"])
                    if pid not in data["appeal_points"]:
                        data["appeal_points"][pid] = ""
        save_products(data)
    data["custom_products"] = load_custom_products_from_sheet()
    return data


def save_products(data: dict):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_product_title(pid: str, excel_dfs: list, products_data: dict) -> str:
    for cp in products_data["custom_products"]:
        if cp["product_id"] == pid:
            return cp["product_title"]
    for df in excel_dfs:
        rows = df[df["product_id"] == pid]
        if not rows.empty:
            title = rows.iloc[0].get("product_title", "")
            if pd.notna(title) and title:
                return str(title)
    return pid


def get_appeal_points(pid: str, products_data: dict) -> str:
    for cp in products_data["custom_products"]:
        if cp["product_id"] == pid:
            return cp.get("appeal_points", "")
    return products_data["appeal_points"].get(pid, "")


# ── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="리뷰 메이커", page_icon="✍️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;1,300&family=Jost:wght@200;300;400;500&display=swap');

:root {
    --bg:        #eceae6;
    --surface:   #ffffff;
    --ink:       #1a1918;
    --ink-soft:  #7a7873;
    --ink-muted: #b8b5b0;
    --rule:      #dedad4;
    --hover-bg:  #f5f4f1;
}

/* ── GLOBAL ── */
*, *::before, *::after { box-sizing: border-box; }
html, body, .stApp { background: var(--bg) !important; font-family: 'Jost', sans-serif; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
[data-testid="stHeader"] { background: transparent !important; border-bottom: none !important; }

/* ── CONTENT CARD ── */
.main .block-container {
    background: var(--surface) !important;
    max-width: 880px !important;
    margin: 2.5rem auto 4rem !important;
    padding: 4rem 5rem 5rem !important;
    border: 1px solid var(--rule);
    box-shadow: 0 2px 40px rgba(0,0,0,0.04);
}

/* ── TITLE ── */
h1 {
    font-family: 'Cormorant Garamond', serif !important;
    font-weight: 300 !important;
    font-size: 3rem !important;
    letter-spacing: -0.02em !important;
    color: var(--ink) !important;
    margin-bottom: 0.25rem !important;
    line-height: 1.05 !important;
}

/* ── SECTION HEADERS (st.header → h2) ── */
h2 {
    font-family: 'Jost', sans-serif !important;
    font-weight: 400 !important;
    font-size: 0.62rem !important;
    letter-spacing: 0.22em !important;
    text-transform: uppercase !important;
    color: var(--ink-soft) !important;
    margin-top: 3.5rem !important;
    margin-bottom: 1.6rem !important;
    padding-bottom: 0.9rem !important;
    border-bottom: 1px solid var(--rule) !important;
}

/* ── SUBHEADER (st.subheader → h3) ── */
h3 {
    font-family: 'Jost', sans-serif !important;
    font-weight: 400 !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    color: var(--ink) !important;
    margin-bottom: 1rem !important;
}

/* ── CAPTION ── */
[data-testid="stCaptionContainer"] p, .stCaption p {
    font-family: 'Jost', sans-serif !important;
    font-weight: 300 !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.04em !important;
    color: var(--ink-soft) !important;
    margin-top: 0.1rem !important;
}

/* ── LABELS ── */
label, p[data-testid="stWidgetLabel"] > span,
.stRadio > label, .stMultiSelect > label,
.stSelectSlider > label, .stNumberInput > label,
.stTextInput > label, .stTextArea > label {
    font-family: 'Jost', sans-serif !important;
    font-weight: 400 !important;
    font-size: 0.62rem !important;
    letter-spacing: 0.18em !important;
    text-transform: uppercase !important;
    color: var(--ink-soft) !important;
}

/* ── RADIO — segmented control style ── */
.stRadio > div[role="radiogroup"] {
    flex-direction: row !important;
    gap: 0 !important;
    flex-wrap: nowrap !important;
}
.stRadio > div[role="radiogroup"] > label {
    border: 1px solid var(--rule) !important;
    margin-right: -1px !important;
    padding: 0.55rem 1.4rem !important;
    cursor: pointer !important;
    background: transparent !important;
    transition: background 0.18s, color 0.18s !important;
    text-transform: uppercase !important;
    font-size: 0.65rem !important;
    letter-spacing: 0.14em !important;
    color: var(--ink-soft) !important;
    border-radius: 0 !important;
    font-weight: 400 !important;
}
.stRadio > div[role="radiogroup"] > label:hover { background: var(--hover-bg) !important; color: var(--ink) !important; }
/* 선택된 항목 — 검정 채움 */
.stRadio > div[role="radiogroup"] > label:has(input:checked) {
    background: var(--ink) !important;
    color: #ffffff !important;
    border-color: var(--ink) !important;
}
.stRadio > div[role="radiogroup"] > label:has(input:checked) p,
.stRadio > div[role="radiogroup"] > label:has(input:checked) span,
.stRadio > div[role="radiogroup"] > label:has(input:checked) div {
    color: #ffffff !important;
}
/* hide radio circles */
.stRadio input[type="radio"] { display: none !important; }
.stRadio [data-baseweb="radio"] > div:first-child { display: none !important; }

/* ── MULTISELECT ── */
[data-testid="stMultiSelect"] [data-baseweb="select"] > div:first-child {
    border: none !important;
    border-bottom: 1px solid var(--rule) !important;
    border-radius: 0 !important;
    background: transparent !important;
    padding: 0.35rem 0 !important;
    font-family: 'Jost', sans-serif !important;
    font-weight: 300 !important;
    font-size: 0.82rem !important;
    color: var(--ink) !important;
    box-shadow: none !important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] {
    background: var(--ink) !important;
    border-radius: 0 !important;
    font-family: 'Jost', sans-serif !important;
    font-size: 0.65rem !important;
    letter-spacing: 0.06em !important;
}

/* ── TEXT INPUTS & TEXTAREA ── */
.stTextInput input, .stTextArea textarea, .stNumberInput input {
    font-family: 'Jost', sans-serif !important;
    font-weight: 300 !important;
    font-size: 0.85rem !important;
    color: var(--ink) !important;
    background: #ffffff !important;
    background-color: #ffffff !important;
    border: none !important;
    border-bottom: 1px solid var(--rule) !important;
    border-radius: 0 !important;
    padding: 0.45rem 0.1rem !important;
    box-shadow: none !important;
    transition: border-color 0.2s !important;
}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: var(--ink) !important;
    border-bottom-color: var(--ink) !important;
    box-shadow: none !important;
    outline: none !important;
}
/* 숫자 입력 wrapper 배경도 흰색 고정 */
.stNumberInput [data-baseweb="input"],
.stNumberInput > div > div {
    background: #ffffff !important;
    background-color: #ffffff !important;
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder {
    color: var(--ink-muted) !important;
    font-weight: 300 !important;
    font-size: 0.8rem !important;
}

/* ── SELECT SLIDER ── */
[data-testid="stSelectSlider"] [data-testid="stTickBar"] span {
    font-family: 'Jost', sans-serif !important;
    font-size: 0.62rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: var(--ink-soft) !important;
}
[data-testid="stSelectSlider"] [role="slider"] {
    background: var(--ink) !important;
    border: 2px solid var(--ink) !important;
}
[data-testid="stSelectSlider"] [data-testid="stSlider"] > div > div > div > div {
    background: var(--ink) !important;
}

/* ── BUTTONS (secondary/default) ── */
.stButton > button, [data-testid="baseButton-secondary"] {
    font-family: 'Jost', sans-serif !important;
    font-weight: 400 !important;
    font-size: 0.62rem !important;
    letter-spacing: 0.18em !important;
    text-transform: uppercase !important;
    border-radius: 0 !important;
    background: transparent !important;
    border: 1px solid var(--ink) !important;
    color: var(--ink) !important;
    padding: 0.65rem 1.8rem !important;
    transition: background 0.22s, color 0.22s !important;
    min-height: 0 !important;
}
.stButton > button:hover { background: var(--ink) !important; color: #fff !important; }

/* primary button */
[data-testid="baseButton-primary"], .stButton > button[kind="primary"] {
    background: var(--ink) !important;
    background-color: var(--ink) !important;
    color: #ffffff !important;
    border: 1px solid var(--ink) !important;
}
[data-testid="baseButton-primary"] p,
[data-testid="baseButton-primary"] span,
.stButton > button[kind="primary"] p,
.stButton > button[kind="primary"] span { color: #ffffff !important; }
[data-testid="baseButton-primary"]:hover, .stButton > button[kind="primary"]:hover {
    background: transparent !important;
    background-color: transparent !important;
    color: var(--ink) !important;
}
[data-testid="baseButton-primary"]:hover p,
[data-testid="baseButton-primary"]:hover span,
.stButton > button[kind="primary"]:hover p,
.stButton > button[kind="primary"]:hover span { color: var(--ink) !important; }

/* ── DOWNLOAD BUTTONS ── */
.stDownloadButton > button {
    font-family: 'Jost', sans-serif !important;
    font-weight: 400 !important;
    font-size: 0.62rem !important;
    letter-spacing: 0.18em !important;
    text-transform: uppercase !important;
    border-radius: 0 !important;
    background: transparent !important;
    border: 1px solid var(--rule) !important;
    color: var(--ink-soft) !important;
    padding: 0.65rem 1.5rem !important;
    width: 100% !important;
    transition: border-color 0.2s, color 0.2s !important;
}
.stDownloadButton > button:hover { border-color: var(--ink) !important; color: var(--ink) !important; }

/* ── EXPANDER ── */
[data-testid="stExpander"] {
    border: 1px solid var(--rule) !important;
    border-radius: 0 !important;
    margin-bottom: 0.6rem !important;
    background: transparent !important;
}
[data-testid="stExpander"] summary {
    font-family: 'Jost', sans-serif !important;
    font-weight: 400 !important;
    font-size: 0.65rem !important;
    letter-spacing: 0.16em !important;
    text-transform: uppercase !important;
    color: var(--ink-soft) !important;
    padding: 0.9rem 1.2rem !important;
    transition: color 0.18s !important;
}
[data-testid="stExpander"] summary:hover { color: var(--ink) !important; }
[data-testid="stExpander"] summary svg { color: var(--ink-muted) !important; }

/* ── PROGRESS BAR ── */
[data-testid="stProgress"] > div {
    background: var(--rule) !important;
    height: 1px !important;
    border-radius: 0 !important;
}
[data-testid="stProgress"] > div > div {
    background: var(--ink) !important;
    height: 1px !important;
    border-radius: 0 !important;
}

/* ── TABS ── */
[data-testid="stTabs"] [role="tablist"] {
    background: transparent !important;
    border-bottom: 1px solid var(--rule) !important;
    gap: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
    font-family: 'Jost', sans-serif !important;
    font-weight: 400 !important;
    font-size: 0.62rem !important;
    letter-spacing: 0.16em !important;
    text-transform: uppercase !important;
    color: var(--ink-soft) !important;
    border-radius: 0 !important;
    padding: 0.75rem 1.4rem !important;
    background: transparent !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.18s !important;
}
[data-testid="stTabs"] [role="tab"]:hover { color: var(--ink) !important; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: var(--ink) !important;
    border-bottom: 2px solid var(--ink) !important;
    font-weight: 500 !important;
}

/* ── ALERTS ── */
[data-testid="stAlert"],
div[data-testid="stAlert"],
[data-testid="stNotification"],
.stAlert, [role="alert"] {
    border-radius: 0 !important;
    border: none !important;
    border-left: 2px solid var(--ink-muted) !important;
    background: var(--hover-bg) !important;
    background-color: var(--hover-bg) !important;
    font-family: 'Jost', sans-serif !important;
    font-weight: 300 !important;
    font-size: 0.78rem !important;
    color: var(--ink) !important;
    padding: 0.8rem 1.2rem !important;
}
[data-testid="stAlert"] p,
[data-testid="stAlert"] span,
[data-testid="stAlert"] svg { color: var(--ink) !important; fill: var(--ink-muted) !important; }

/* ── DATAFRAME ── */
[data-testid="stDataFrame"] { border: 1px solid var(--rule) !important; border-radius: 0 !important; }
[data-testid="stDataFrame"] table { font-family: 'Jost', sans-serif !important; font-size: 0.78rem !important; }
[data-testid="stDataFrame"] th {
    font-size: 0.6rem !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: var(--ink-soft) !important;
    font-weight: 400 !important;
    background: var(--hover-bg) !important;
    border-bottom: 1px solid var(--rule) !important;
}

/* ── DIVIDER ── */
hr { border: none !important; border-top: 1px solid var(--rule) !important; margin: 2rem 0 !important; }

/* ── MISC ── */
p { font-family: 'Jost', sans-serif !important; font-weight: 300 !important; font-size: 0.85rem !important; color: var(--ink) !important; line-height: 1.6 !important; }
strong, b { font-weight: 500 !important; }
code { font-size: 0.78rem !important; background: var(--hover-bg) !important; padding: 0.15rem 0.4rem !important; border-radius: 2px !important; color: var(--ink) !important; }
[data-testid="column"] { padding: 0 0.4rem !important; }
.element-container { margin-bottom: 0.6rem !important; }

/* number input spinner buttons */
.stNumberInput [data-testid="stNumberInputStepUp"],
.stNumberInput [data-testid="stNumberInputStepDown"] {
    border-radius: 0 !important;
    border: 1px solid var(--rule) !important;
    color: var(--ink-soft) !important;
}
</style>
""", unsafe_allow_html=True)

st.title("리뷰 메이커")
st.caption("기존 리뷰를 학습해 새로운 일본어 리뷰를 자동 생성합니다.")

# ── 소스 데이터 관리 ──────────────────────────────────────────────────────────
with st.expander("📂 소스 데이터 관리 (엑셀 파일 업로드/교체)", expanded=False):
    st.markdown("긍정/부정 리뷰 소스 파일을 교체하려면 아래에 업로드하세요. 업로드하면 기존 파일이 덮어써집니다.")

    col_pos, col_neg = st.columns(2)

    with col_pos:
        st.markdown("**긍정 리뷰 파일**")
        if POSITIVE_FILE.exists():
            try:
                pos_preview = load_excel(POSITIVE_FILE)
                st.success(f"현재 파일: {len(pos_preview)}개 리뷰 등록됨")
            except Exception:
                st.warning("현재 파일 읽기 오류")
        else:
            st.warning("파일 없음")

        uploaded_pos = st.file_uploader(
            "새 긍정 리뷰 파일 업로드 (.xlsx)",
            type=["xlsx"],
            key="upload_pos",
        )
        if uploaded_pos is not None:
            with open(POSITIVE_FILE, "wb") as f:
                f.write(uploaded_pos.getbuffer())
            st.cache_data.clear()
            st.success("긍정 리뷰 파일이 교체됐습니다.")
            st.rerun()

    with col_neg:
        st.markdown("**부정 리뷰 파일**")
        if NEGATIVE_FILE.exists():
            try:
                neg_preview = load_excel(NEGATIVE_FILE)
                st.success(f"현재 파일: {len(neg_preview)}개 리뷰 등록됨")
            except Exception:
                st.warning("현재 파일 읽기 오류")
        else:
            st.warning("파일 없음")

        uploaded_neg = st.file_uploader(
            "새 부정 리뷰 파일 업로드 (.xlsx)",
            type=["xlsx"],
            key="upload_neg",
        )
        if uploaded_neg is not None:
            with open(NEGATIVE_FILE, "wb") as f:
                f.write(uploaded_neg.getbuffer())
            st.cache_data.clear()
            st.success("부정 리뷰 파일이 교체됐습니다.")
            st.rerun()

# ── 파일 로드 ─────────────────────────────────────────────────────────────────
files_ok = True
for label, path in [("긍정 리뷰 파일", POSITIVE_FILE), ("부정 리뷰 파일", NEGATIVE_FILE)]:
    if not path.exists():
        st.error(f"{label}을 찾을 수 없습니다: `{path}`")
        files_ok = False

if not files_ok:
    st.stop()

pos_df = load_excel(POSITIVE_FILE)
neg_df = load_excel(NEGATIVE_FILE)
excel_dfs = [pos_df, neg_df]

if "products_data" not in st.session_state:
    st.session_state.products_data = load_products()

products_data = st.session_state.products_data

# ── 상품 관리 섹션 ────────────────────────────────────────────────────────────
with st.expander("🗂️ 상품 관리 (추가·삭제·소구 포인트 편집)", expanded=False):

    st.subheader("등록된 상품 목록")

    excel_skus = sorted(set(
        list(pos_df["product_id"].unique()) + list(neg_df["product_id"].unique())
    ))
    all_display = []
    for pid in excel_skus:
        if pid not in products_data["hidden_skus"]:
            all_display.append({"pid": pid, "source": "excel"})
    for cp in products_data["custom_products"]:
        all_display.append({"pid": cp["product_id"], "source": "custom"})

    if not all_display:
        st.info("등록된 상품이 없습니다.")
    else:
        header = st.columns([1.5, 2.5, 4, 1])
        header[0].markdown("**상품 ID**")
        header[1].markdown("**상품명**")
        header[2].markdown("**소구 포인트**")
        header[3].markdown("**삭제**")

        for item in all_display:
            pid = item["pid"]
            source = item["source"]
            title = get_product_title(pid, excel_dfs, products_data)
            appeal = get_appeal_points(pid, products_data)

            col_id, col_title, col_ap, col_del = st.columns([1.5, 2.5, 4, 1])
            with col_id:
                st.markdown(f"`{pid}`")
            with col_title:
                st.markdown(title[:30] if title else "—")
            with col_ap:
                new_ap = st.text_input(
                    "소구 포인트",
                    value=appeal,
                    key=f"ap_{pid}",
                    label_visibility="collapsed",
                    placeholder="예: 保湿力が高い、毛穴ケア効果、低刺激処方...",
                )
                if new_ap != appeal:
                    if source == "excel":
                        products_data["appeal_points"][pid] = new_ap
                        save_products(products_data)
                    else:
                        update_appeal_points_in_sheet(pid, new_ap)
                        for cp in products_data["custom_products"]:
                            if cp["product_id"] == pid:
                                cp["appeal_points"] = new_ap
                    st.session_state.products_data = products_data
            with col_del:
                if st.button("🗑️", key=f"del_{pid}", help="삭제"):
                    if source == "excel":
                        if pid not in products_data["hidden_skus"]:
                            products_data["hidden_skus"].append(pid)
                        save_products(products_data)
                    else:
                        delete_product_from_sheet(pid)
                        products_data["custom_products"] = [
                            cp for cp in products_data["custom_products"]
                            if cp["product_id"] != pid
                        ]
                    st.session_state.products_data = products_data
                    st.rerun()

    st.divider()

    st.subheader("새 상품 추가")
    c1, c2 = st.columns(2)
    with c1:
        new_pid = st.text_input("상품 ID (product_id)", placeholder="예: 12345")
    with c2:
        new_title = st.text_input("상품명", placeholder="예: XXX 미용액")
    new_ap = st.text_area(
        "소구 포인트",
        placeholder="예: セラミド配合で保湿力抜群、敏感肌でも使える低刺激処方、毛穴ケアに特化...",
        height=80,
    )
    if st.button("＋ 상품 추가", type="primary"):
        if not new_pid or not new_title:
            st.warning("상품 ID와 상품명은 필수입니다.")
        else:
            existing_ids = [cp["product_id"] for cp in products_data["custom_products"]] + excel_skus
            if new_pid in existing_ids:
                st.warning("이미 등록된 상품 ID입니다.")
            else:
                append_product_to_sheet(new_pid, new_title, new_ap)
                products_data["custom_products"].append({
                    "product_id": new_pid,
                    "product_title": new_title,
                    "appeal_points": new_ap,
                })
                st.session_state.products_data = products_data
                st.success(f"「{new_title}」을 추가했습니다.")
                st.rerun()

# 표시할 상품 목록 구성
visible_skus = []
for pid in excel_skus:
    if pid not in products_data["hidden_skus"]:
        visible_skus.append(pid)
for cp in products_data["custom_products"]:
    visible_skus.append(cp["product_id"])

# ── 1단계: 리뷰 타입 선택 ──────────────────────────────────────────────────────
st.header("1단계 · 리뷰 타입 선택")

review_type = st.radio(
    "생성할 리뷰 타입을 선택하세요",
    options=["긍정", "부정", "긍정 + 부정 모두"],
    horizontal=True,
)

# ── 2단계: 상품 선택 ────────────────────────────────────────────────────────────
st.header("2단계 · 상품 선택")

if not visible_skus:
    st.warning("등록된 상품이 없습니다. 상품 관리에서 추가해주세요.")
    st.stop()

sku_options = {pid: f"{pid}  |  {get_product_title(pid, excel_dfs, products_data)}" for pid in visible_skus}
selected_skus = st.multiselect(
    "리뷰를 생성할 상품 선택",
    options=list(sku_options.keys()),
    format_func=lambda x: sku_options[x],
    default=visible_skus[:1],
    help="여러 상품을 동시에 선택할 수 있습니다.",
)

# ── 3단계: 생성 수량 ────────────────────────────────────────────────────────────
st.header("3단계 · 생성 수량")

if review_type == "긍정 + 부정 모두":
    c1, c2 = st.columns(2)
    with c1:
        num_positive = st.number_input("긍정 리뷰 수 (상품당)", min_value=1, max_value=50, value=5, step=1)
    with c2:
        num_negative = st.number_input("부정 리뷰 수 (상품당)", min_value=1, max_value=50, value=5, step=1)
    num_reviews = None
else:
    num_reviews = st.number_input("생성할 리뷰 수 (상품당)", min_value=1, max_value=50, value=5, step=1)

with st.expander("고급 옵션"):
    diversity_level = st.select_slider(
        "리뷰 다양성",
        options=["낮음", "보통", "높음"],
        value="보통",
        help="높을수록 기존 리뷰와 다른 표현이 사용됩니다.",
    )

# ── 4단계: 생성 및 다운로드 ────────────────────────────────────────────────────
st.header("4단계 · 생성 및 다운로드")

if not selected_skus:
    st.warning("상품을 한 개 이상 선택해주세요.")
    st.stop()

if review_type == "긍정 + 부정 모두":
    total = len(selected_skus) * (num_positive + num_negative)
    st.info(f"총 {total}개 리뷰 생성 예정 — 긍정 {num_positive}개 + 부정 {num_negative}개 × 상품 {len(selected_skus)}개")
else:
    total = len(selected_skus) * num_reviews
    st.info(f"총 {total}개 {review_type} 리뷰 생성 예정 — {num_reviews}개 × 상품 {len(selected_skus)}개")

if st.button("리뷰 생성 시작 ▶", type="primary"):
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        st.error("API 키가 설정되지 않았습니다. `.streamlit/secrets.toml`에 `ANTHROPIC_API_KEY`를 입력해주세요.")
        st.stop()

    all_generated = []
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    tasks = []
    if review_type == "긍정 + 부정 모두":
        for sku in selected_skus:
            tasks.append((sku, "긍정", num_positive))
            tasks.append((sku, "부정", num_negative))
    elif review_type == "긍정":
        for sku in selected_skus:
            tasks.append((sku, "긍정", num_reviews))
    else:
        for sku in selected_skus:
            tasks.append((sku, "부정", num_reviews))

    for i, (sku, r_type, count) in enumerate(tasks):
        status_text.markdown(f"**생성 중...** `{sku}` — {r_type} {count}개 ({i + 1}/{len(tasks)})")

        if r_type == "긍정":
            sku_df = pos_df[pos_df["product_id"] == sku].reset_index(drop=True)
            if sku_df.empty:
                sku_df = neg_df[neg_df["product_id"] == sku].reset_index(drop=True)
        else:
            sku_df = neg_df[neg_df["product_id"] == sku].reset_index(drop=True)
            if sku_df.empty:
                sku_df = pos_df[pos_df["product_id"] == sku].reset_index(drop=True)

        selling_points = get_appeal_points(sku, products_data)

        try:
            generated = generate_reviews_for_sku(
                existing_df=sku_df,
                num_reviews=count,
                review_type=r_type,
                diversity_level=diversity_level,
                api_key=api_key,
                selling_points=selling_points,
                product_id=sku,
            )
            all_generated.extend(generated)
        except Exception as e:
            st.warning(f"`{sku}` {r_type} 생성 중 오류 (건너뜀): {e}")

        progress_bar.progress((i + 1) / len(tasks))

    status_text.markdown("**완료!**")

    if not all_generated:
        st.error("생성된 리뷰가 없습니다.")
        st.stop()

    result_df = pd.DataFrame(all_generated)
    for c in ALL_COLUMNS:
        if c not in result_df.columns:
            result_df[c] = ""
    result_df = result_df[ALL_COLUMNS]

    # ── 결과 미리보기 ──────────────────────────────────────────────────────────
    st.subheader(f"생성 결과 — 총 {len(result_df)}개")

    if review_type == "긍정 + 부정 모두":
        tab_pos, tab_neg, tab_all = st.tabs(["긍정 리뷰", "부정 리뷰", "전체"])
        with tab_pos:
            pos_result = result_df[result_df["review_score"].astype(str).isin(["4", "5", "4.0", "5.0"])]
            st.dataframe(pos_result.reset_index(drop=True), use_container_width=True, hide_index=True)
        with tab_neg:
            neg_result = result_df[result_df["review_score"].astype(str).isin(["1", "2", "1.0", "2.0"])]
            st.dataframe(neg_result.reset_index(drop=True), use_container_width=True, hide_index=True)
        with tab_all:
            st.dataframe(result_df.reset_index(drop=True), use_container_width=True, hide_index=True)
    else:
        st.dataframe(result_df.reset_index(drop=True), use_container_width=True, hide_index=True)

    # ── 다운로드 ───────────────────────────────────────────────────────────────
    st.subheader("다운로드")
    dl1, dl2 = st.columns(2)

    csv_buf = io.StringIO()
    result_df.to_csv(csv_buf, index=False, encoding="utf-8-sig")
    with dl1:
        st.download_button(
            "CSV 다운로드",
            data=csv_buf.getvalue().encode("utf-8-sig"),
            file_name="generated_reviews.csv",
            mime="text/csv",
            use_container_width=True,
        )

    excel_buf = io.BytesIO()
    result_df.to_excel(excel_buf, index=False, engine="openpyxl")
    with dl2:
        st.download_button(
            "Excel 다운로드",
            data=excel_buf.getvalue(),
            file_name="generated_reviews.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
