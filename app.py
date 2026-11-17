import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# =====================================================================
# 페이지 기본 설정
# =====================================================================
st.set_page_config(
    page_title="국토부 실거래가 & 네이버 매물 통합 대시보드",
    page_icon="🏢",
    layout="wide",
)

# 모바일(스마트폰)에서 selectbox 터치 시 가상 키보드(천지인 자판) 원천 차단 CSS
st.markdown(
    """
    <style>
    /* selectbox 내부의 텍스트 검색용 input 태그 자체를 숨겨 모바일 키보드 호출 차단 */
    div[data-baseweb="select"] input {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

DEFAULT_API_KEY = st.secrets.get(
    "MOLIT_API_KEY",
    "31a08f319d25f742296a53f8cf22e82830a5aae5efd82cd666d17b62e2f9e64b",
)

# =====================================================================
# 전국 시/도 및 시/군/구 법정동 5자리 코드 내장 데이터
# =====================================================================
REGION_DATA = {
    "서울특별시": {
        "강남구": "11680", "강동구": "11740", "강북구": "11305", "강서구": "11500",
        "관악구": "11620", "광진구": "11215", "구로구": "11530", "금천구": "11545",
        "노원구": "11350", "도봉구": "11320", "동대문구": "11230", "동작구": "11590",
        "마포구": "11440", "서대문구": "11410", "서초구": "11650", "성동구": "11200",
        "성북구": "11290", "송파구": "11710", "양천구": "11470", "영등포구": "11560",
        "용산구": "11170", "은평구": "11380", "종로구": "11110", "중구": "11140", "중랑구": "11260",
    },
    "경기도": {
        "가평군": "41820", "고양시 덕양구": "41281", "고양시 일산동구": "41285", "고양시 일산서구": "41287",
        "과천시": "41290", "광명시": "41210", "광주시": "41610", "구리시": "41310",
        "군포시": "41410", "김포시": "41570", "남양주시": "41360", "동두천시": "41250",
        "부천시 소사구": "41194", "부천시 오정구": "41196", "부천시 원미구": "41192",
        "성남시 분당구": "41135", "성남시 수정구": "41131", "성남시 중원구": "41133",
        "수원시 권선구": "41113", "수원시 영통구": "41117", "수원시 장안구": "41111", "수원시 팔달구": "41115",
        "시흥시": "41390", "안산시 단원구": "41273", "안산시 상록구": "41271", "안성시": "41550",
        "안양시 동안구": "41173", "안양시 만안구": "41171", "양주시": "41630", "양평군": "41830",
        "여주시": "41670", "연천군": "41800", "오산시": "41370",
        "용인시 기흥구": "41463", "용인시 수지구": "41465", "용인시 처인구": "41461",
        "의왕시": "41430", "의정부시": "41150", "이천시": "41500", "파주시": "41480",
        "평택시": "41220", "포천시": "41650", "하남시": "41450", "화성시": "41590",
    },
    "인천광역시": {
        "강화군": "28710", "계양구": "28245", "남동구": "28200", "동구": "28140",
        "미추홀구": "28177", "부평구": "28237", "서구": "28260", "연수구": "28185",
        "옹진군": "28720", "중구": "28110",
    },
    "부산광역시": {
        "강서구": "26440", "금정구": "26410", "기장군": "26710", "남구": "26290",
        "동구": "26170", "동래구": "26260", "부산진구": "26230", "북구": "26320",
        "사상구": "26530", "사하구": "26380", "서구": "26140", "수영구": "26500",
        "연제구": "26470", "영도구": "26200", "중구": "26110", "해운대구": "26350",
    },
    "대구광역시": {
        "군위군": "27720", "남구": "27200", "달서구": "27290", "달성군": "27710",
        "동구": "27140", "북구": "27230", "서구": "27170", "수성구": "27260", "중구": "27110",
    },
    "광주광역시": {
        "광산구": "29200", "남구": "29155", "동구": "29110", "북구": "29170", "서구": "29140",
    },
    "대전광역시": {
        "대덕구": "30230", "동구": "30110", "서구": "30170", "유성구": "30200", "중구": "30140",
    },
    "울산광역시": {
        "남구": "31140", "동구": "31170", "북구": "31200", "울주군": "31710", "중구": "31110",
    },
    "세종특별자치시": {
        "세종특별자치시": "36110",
    },
    "강원특별자치도": {
        "강릉시": "51150", "고성군": "51820", "동해시": "51170", "삼척시": "51230",
        "속초시": "51210", "양구군": "51800", "양양군": "51830", "영월군": "51750",
        "원주시": "51130", "인제군": "51810", "정선군": "51770", "철원군": "51780",
        "춘천시": "51110", "태백시": "51190", "평창군": "51760", "홍천군": "51720",
        "화천군": "51790", "횡성군": "51730",
    },
    "충청북도": {
        "괴산군": "43760", "단양군": "43800", "보은군": "43720", "영동군": "43740",
        "옥천군": "43730", "음성군": "43770", "제천시": "43150", "증평군": "43745",
        "진천군": "43750", "청주시 상당구": "43111", "청주시 서원구": "43112",
        "청주시 청원구": "43114", "청주시 흥덕구": "43113", "충주시": "43130",
    },
    "충청남도": {
        "계룡시": "44250", "공주시": "44150", "금산군": "44710", "논산시": "44230",
        "당진시": "44270", "보령시": "44180", "부여군": "44760", "서산시": "44210",
        "서천군": "44770", "아산시": "44200", "예산군": "44810",
        "천안시 동남구": "44131", "천안시 서북구": "44133", "청양군": "44790",
        "태안군": "44825", "홍성군": "44800",
    },
    "전북특별자치도": {
        "고창군": "52790", "군산시": "52130", "김제시": "52210", "남원시": "52190",
        "무주군": "52730", "부안군": "52800", "순창군": "52770", "완주군": "52710",
        "익산시": "52140", "임실군": "52750", "장수군": "52740",
        "전주시 덕진구": "52113", "전주시 완산구": "52111", "정읍시": "52180", "진안군": "52720",
    },
    "전라남도": {
        "강진군": "46810", "고흥군": "46770", "곡성군": "46720", "광양시": "46230",
        "구례군": "46730", "나주시": "46170", "담양군": "46710", "목포시": "46110",
        "무안군": "46840", "보성군": "46780", "순천시": "46150", "신안군": "46910",
        "여수시": "46130", "영광군": "46870", "영암군": "46830", "완도군": "46890",
        "장성군": "46880", "장흥군": "46800", "진도군": "46900", "함평군": "46860",
        "해남군": "46820", "화순군": "46790",
    },
    "경상북도": {
        "경산시": "47290", "경주시": "47130", "고령군": "47830", "구미시": "47190",
        "김천시": "47150", "문경시": "47280", "봉화군": "47920", "상주시": "47250",
        "성주군": "47840", "안동시": "47170", "영덕군": "47770", "영양군": "47760",
        "영주시": "47210", "영천시": "47230", "예천군": "47900", "울릉군": "47940",
        "울진군": "47930", "의성군": "47730", "청도군": "47820", "청송군": "47750",
        "칠곡군": "47850", "포항시 남구": "47111", "포항시 북구": "47113",
    },
    "경상남도": {
        "거제시": "48310", "거창군": "48880", "고성군": "48820", "김해시": "48250",
        "남해군": "48840", "밀양시": "48270", "사천시": "48240", "산청군": "48860",
        "양산시": "48330", "의령군": "48720", "진주시": "48170", "창녕군": "48740",
        "창원시 마산합포구": "48125", "창원시 마산회원구": "48127", "창원시 성산구": "48123",
        "창원시 의창구": "48121", "창원시 진해구": "48129", "통영시": "48220",
        "하동군": "48850", "함안군": "48730", "함양군": "48870", "합천군": "48890",
    },
    "제주특별자치도": {
        "서귀포시": "50130", "제주시": "50110",
    },
}


# =====================================================================
# 시/군/구 코드(5자리)로 읍/면/동 목록 조회
# =====================================================================
@st.cache_data(ttl=86400, show_spinner=False)
def get_dongs_by_sigungu(sido_name, sgg_name, code5):
    try:
        url = f"https://grpc-proxy-server-mkvo6j4wsq-du.a.run.app/v1/regcodes?regcode_pattern={code5}*00&is_ignore_zero=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
            dongs = set()
            for item in data.get("regcodes", []):
                c = item.get("code", "")
                if len(c) == 10 and not c.endswith("00000") and c.endswith("00"):
                    parts = item.get("name", "").split()
                    if parts:
                        dongs.add(parts[-1])
            if dongs:
                return sorted(list(dongs))
    except Exception:
        pass

    try:
        now = datetime.now()
        y, m = now.year, now.month
        dongs = set()
        for _ in range(3):
            ym = f"{y}{m:02d}"
            encoded_key = DEFAULT_API_KEY if "%" in DEFAULT_API_KEY else urllib.parse.quote(DEFAULT_API_KEY, safe="")
            url = (
                f"https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
                f"?serviceKey={encoded_key}&LAWD_CD={code5}&DEAL_YMD={ym}&pageNo=1&numOfRows=999"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                root = ET.fromstring(resp.read().decode("utf-8", errors="ignore"))
                for item in root.findall(".//item"):
                    el = item.find("umdNm")
                    if el is None:
                        el = item.find("법정동")
                    if el is not None and el.text:
                        dongs.add(el.text.strip())
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        if dongs:
            return sorted(list(dongs))
    except Exception:
        pass

    return []


# =====================================================================
# 유틸리티 및 국토부 실거래가 API 병렬 수집 (진행바 지원)
# =====================================================================
def fmt_price(val):
    if not val or val <= 0:
        return "-"
    eok = int(val // 10000)
    man = int(round(val % 10000))
    if eok > 0 and man > 0:
        return f"{eok}억 {man:,}"
    if eok > 0:
        return f"{eok}억"
    return f"{man:,}만"


def parse_price_to_manwon(price_text):
    try:
        main_part = str(price_text).split("/")[0].replace(",", "").replace(" ", "")
        if "억" in main_part:
            parts = main_part.split("억")
            eok = int(parts[0]) * 10000
            man = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            return eok + man
        return int(main_part)
    except Exception:
        return 0


def parse_pyrom_num(py_str):
    try:
        m = re.search(r"(\d+)", str(py_str))
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def parse_floor_category(floor_raw):
    s = str(floor_raw).strip()
    if not s or s == "nan":
        return "중"
    top_part = s.split("/")[0]
    m_tot = re.search(r"/(\d+)층", s)
    total_part = int(m_tot.group(1)) if m_tot else 99

    if top_part == "저" or (top_part.isdigit() and int(top_part) <= 3):
        return "저"
    if top_part in ["고", "탑"] or (top_part.isdigit() and int(top_part) >= total_part - 1):
        return "고"
    return "중"


def get_recent_ym_list(months=24):
    now = datetime.now()
    y, m = now.year, now.month
    ym_list = []
    for _ in range(months):
        ym_list.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return ym_list


def fetch_molit_xml(endpoint_url, service_key, lawd_cd, deal_ymd):
    encoded_key = service_key if "%" in service_key else urllib.parse.quote(service_key, safe="")
    url = f"{endpoint_url}?serviceKey={encoded_key}&LAWD_CD={lawd_cd}&DEAL_YMD={deal_ymd}&pageNo=1&numOfRows=9999"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def get_xml_text(item_elem, tag_names):
    for tag in tag_names:
        el = item_elem.find(tag)
        if el is not None and el.text:
            return el.text.strip()
    return ""


def fetch_single_month_data(lawd_cd_5, service_key, ym):
    sale_endpoints = [
        "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
        "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    ]
    rent_ep = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

    month_sales, month_rents = [], []
    err_msg = ""

    for ep in sale_endpoints:
        try:
            xml_str = fetch_molit_xml(ep, service_key, lawd_cd_5, ym)
            root = ET.fromstring(xml_str)
            res_code = get_xml_text(root, [".//resultCode"])
            if res_code and res_code not in ["00", "000"]:
                err_msg = f"API 응답 코드({res_code}): {get_xml_text(root, ['.//resultMsg'])}"
                continue
            for item in root.findall(".//item"):
                if get_xml_text(item, ["cdealType", "해제여부"]) == "O":
                    continue
                dong_nm = get_xml_text(item, ["umdNm", "법정동"])
                apt_nm = get_xml_text(item, ["aptNm", "아파트"])
                price_str = get_xml_text(item, ["dealAmount", "거래금액"]).replace(",", "")
                if not price_str or not apt_nm:
                    continue
                area_str = get_xml_text(item, ["excluUseAr", "전용면적"])
                floor_str = get_xml_text(item, ["floor", "층"])
                y_str = get_xml_text(item, ["dealYear", "년"])
                m_int = int(get_xml_text(item, ["dealMonth", "월"]) or 1)
                d_int = int(get_xml_text(item, ["dealDay", "일"]) or 1)
                b_yr = get_xml_text(item, ["buildYear", "건축년도"])

                month_sales.append({
                    "dong": dong_nm,
                    "apt_name": apt_nm,
                    "price": int(price_str),
                    "area": round(float(area_str), 2) if area_str else 0.0,
                    "floor": int(floor_str) if floor_str.lstrip("-").isdigit() else 0,
                    "date": f"{y_str}-{m_int:02d}-{d_int:02d}",
                    "ym": f"{y_str}-{m_int:02d}",
                    "build_year": int(b_yr) if b_yr.isdigit() else 0,
                })
            break
        except Exception as e:
            err_msg = str(e)
            continue

    try:
        xml_str = fetch_molit_xml(rent_ep, service_key, lawd_cd_5, ym)
        root = ET.fromstring(xml_str)
        res_code = get_xml_text(root, [".//resultCode"])
        if not res_code or res_code in ["00", "000"]:
            for item in root.findall(".//item"):
                dong_nm = get_xml_text(item, ["umdNm", "법정동"])
                apt_nm = get_xml_text(item, ["aptNm", "아파트"])
                dep_str = get_xml_text(item, ["deposit", "보증금액"]).replace(",", "")
                mon_str = get_xml_text(item, ["monthlyRent", "월세금액"]).replace(",", "")
                if not dep_str or not apt_nm or (mon_str.isdigit() and int(mon_str) > 0):
                    continue
                area_str = get_xml_text(item, ["excluUseAr", "전용면적"])
                floor_str = get_xml_text(item, ["floor", "층"])
                y_str = get_xml_text(item, ["dealYear", "년"])
                m_int = int(get_xml_text(item, ["dealMonth", "월"]) or 1)
                d_int = int(get_xml_text(item, ["dealDay", "일"]) or 1)
                b_yr = get_xml_text(item, ["buildYear", "건축년도"])

                month_rents.append({
                    "dong": dong_nm,
                    "apt_name": apt_nm,
                    "deposit": int(dep_str),
                    "area": round(float(area_str), 2) if area_str else 0.0,
                    "floor": int(floor_str) if floor_str.lstrip("-").isdigit() else 0,
                    "date": f"{y_str}-{m_int:02d}-{d_int:02d}",
                    "ym": f"{y_str}-{m_int:02d}",
                    "build_year": int(b_yr) if b_yr.isdigit() else 0,
                })
    except Exception:
        pass

    return month_sales, month_rents, err_msg


def collect_molit_with_progress(lawd_cd_5, service_key, months=24):
    """진행바 및 남은 예상 시간(초)을 실시간 표시하며 병렬 수집"""
    if not service_key or not lawd_cd_5:
        return [], [], "인증키 또는 지역코드가 없습니다."

    ym_list = get_recent_ym_list(months)
    total_tasks = len(ym_list)
    sale_records, rent_records = [], []
    first_err = ""

    progress_bar = st.progress(0, text=f"⏳ 국토교통부 실거래가 조회 준비 중... (총 {total_tasks}개월 분량)")
    start_time = time.time()
    completed = 0

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_single_month_data, lawd_cd_5, service_key, ym): ym
            for ym in ym_list
        }
        for future in as_completed(futures):
            m_sales, m_rents, err = future.result()
            sale_records.extend(m_sales)
            rent_records.extend(m_rents)
            if err and not first_err:
                first_err = err

            completed += 1
            elapsed = time.time() - start_time
            avg_per_item = elapsed / completed
            remaining_sec = max(0.0, avg_per_item * (total_tasks - completed))
            pct = int((completed / total_tasks) * 100)

            progress_bar.progress(
                pct,
                text=(
                    f"🏛️ 실거래가 수집 중: {completed}/{total_tasks}개월 ({pct}%) | "
                    f"경과: {elapsed:.1f}초 · 예상 남은 시간: 약 {remaining_sec:.1f}초"
                ),
            )

    progress_bar.progress(100, text=f"✅ 조회 완료! (총 {total_tasks}개월 데이터 수집 소요 시간: {time.time() - start_time:.1f}초)")
    time.sleep(0.6)
    progress_bar.empty()

    return sale_records, rent_records, first_err


def normalize_apt_name(name):
    s = re.sub(r"\([^)]*\)", "", str(name))
    s = re.sub(r"제(\d+)", r"\1", s)
    s = s.replace("아파트", "").replace("도시", "")
    return re.sub(r"[^가-힣a-zA-Z0-9]", "", s).lower()


# =====================================================================
# Streamlit 웹 UI 렌더링
# =====================================================================
st.title("🏢 국토교통부 실거래가 & 네이버 호가 통합 대시보드")
st.caption("국토부 매매·전세 실거래가 추세 분석과 PC에서 수집한 네이버 부동산 매물 CSV 상세 필터링을 한 화면에서 제공합니다.")

with st.sidebar:
    st.header("📍 1. 국토부 실거래 조회 지역")

    sido_names = list(REGION_DATA.keys())
    default_sido_idx = sido_names.index("경기도")
    sel_sido_name = st.selectbox("1) 시/도 선택", sido_names, index=default_sido_idx)

    sgg_dict = REGION_DATA[sel_sido_name]
    sgg_names = list(sgg_dict.keys())
    default_sgg_idx = sgg_names.index("이천시") if "이천시" in sgg_names else 0
    sel_sgg_name = st.selectbox("2) 시/군/구 선택", sgg_names, index=default_sgg_idx)
    lawd_cd_5 = sgg_dict[sel_sgg_name]

    dong_candidates = get_dongs_by_sigungu(sel_sido_name, sel_sgg_name, lawd_cd_5)
    dong_options = ["선택 안함"] + dong_candidates
    sel_dong_sidebar = st.selectbox("3) 읍/면/동 선택", dong_options, index=0)

    st.divider()
    st.header("🏛️ 2. 국토부 API 설정")
    api_key = st.text_input("공공데이터포털 인증키", value=DEFAULT_API_KEY, type="password")
    months = st.slider(
        "실거래가 조회 기간 (개월)",
        min_value=6,
        max_value=120,
        value=24,
        step=6,
        help="최대 120개월(10년)까지 조회 가능합니다.",
    )

    run_btn = st.button("🚀 국토부 실거래가 조회 실행", type="primary", use_container_width=True)

    st.divider()
    st.header("📂 3. 네이버 매물 CSV 업로드")
    uploaded_csv = st.file_uploader(
        "PC 수집기 결과 CSV 파일 선택",
        type=["csv"],
        help="PC 수집기에서 생성된 *_all_listings.csv 파일을 업로드하면 아래 [네이버 매물 분석] 탭과 [실거래 괴리율]에 자동 연동됩니다.",
    )

# 업로드된 CSV 전처리 및 세션 저장
if uploaded_csv is not None:
    try:
        raw_df = pd.read_csv(uploaded_csv)
        if "가격" in raw_df.columns:
            raw_df["price_num"] = raw_df["가격"].apply(parse_price_to_manwon)
        else:
            raw_df["price_num"] = 0

        if "환산평형" in raw_df.columns:
            raw_df["pyrom_num"] = raw_df["환산평형"].apply(parse_pyrom_num)
        else:
            raw_df["pyrom_num"] = 0

        if "층수" in raw_df.columns:
            raw_df["floor_cat"] = raw_df["층수"].apply(parse_floor_category)
        else:
            raw_df["floor_cat"] = "중"

        for col, default_val in [
            ("법정동", "-"), ("아파트명", "-"), ("단지코드", ""), ("거래구분", "-"),
            ("공급/전용면적", "-"), ("세대수", 0), ("준공년도", 0),
            ("층수", "-"), ("향", "-"), ("매물특징", "-"), ("가격", "-"),
            ("중개업소(부동산)", "-"), ("네이버부동산URL", ""),
        ]:
            if col not in raw_df.columns:
                raw_df[col] = default_val

        raw_df["세대수"] = pd.to_numeric(raw_df["세대수"], errors="coerce").fillna(0).astype(int)
        raw_df["준공년도"] = pd.to_numeric(raw_df["준공년도"], errors="coerce").fillna(0).astype(int)

        st.session_state["naver_df"] = raw_df
        st.sidebar.success(f"✅ 네이버 매물 CSV 로드 완료 ({len(raw_df):,}건)")
    except Exception as e:
        st.sidebar.error(f"CSV 파일 읽기 오류: {e}")

naver_df = st.session_state.get("naver_df", None)

# 국토부 실거래가 조회 실행 (메인 영역에 진행바 표시)
if run_btn:
    region_label = (
        f"{sel_sido_name} {sel_sgg_name}"
        if sel_dong_sidebar == "선택 안함"
        else f"{sel_sido_name} {sel_sgg_name} {sel_dong_sidebar}"
    )
    sales, rents, err_msg = collect_molit_with_progress(lawd_cd_5, api_key, months)
    st.session_state["molit_result"] = {
        "region": region_label,
        "selected_dong": sel_dong_sidebar,
        "months": months,
        "sales": sales,
        "rents": rents,
        "err": err_msg,
    }

# =====================================================================
# 메인 화면 탭 구성
# =====================================================================
tab_naver, tab_molit = st.tabs([
    f"📋 네이버 부동산 매물 분석 ({len(naver_df):,}건)" if naver_df is not None else "📋 네이버 부동산 매물 분석 (CSV 업로드)",
    "📈 국토부 실거래가 & 괴리율 심층 분석",
])

# ---------------------------------------------------------------------
# TAB 1: 업로드된 네이버 부동산 매물 CSV 상세 분석 및 필터링
# ---------------------------------------------------------------------
with tab_naver:
    if naver_df is None:
        st.info(
            "👈 왼쪽 사이드바 **[3. 네이버 매물 CSV 업로드]**에서 PC 수집기로 만든 `*_all_listings.csv` 파일을 올려주세요.\n\n"
            "업로드 즉시 단지별 매물 수 요약, 거래구분/평형/향/준공년도/특징/가격대별 다중 필터링 및 국토부 실거래가 비교가 활성화됩니다."
        )
    else:
        st.subheader("📊 수집된 네이버 부동산 매물 요약")

        total_cnt = len(naver_df)
        sale_df = naver_df[naver_df["거래구분"] == "매매"]
        jeonse_df = naver_df[naver_df["거래구분"] == "전세"]
        wolse_df = naver_df[naver_df["거래구분"] == "월세"]
        unique_apts = naver_df["아파트명"].nunique()

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("전체 수집 매물", f"{total_cnt:,}건", f"총 {unique_apts}개 단지")
        m2.metric("매매 매물", f"{len(sale_df):,}건", f"평균 {fmt_price(sale_df['price_num'].mean())}" if not sale_df.empty else "-")
        m3.metric("전세 매물", f"{len(jeonse_df):,}건", f"평균 {fmt_price(jeonse_df['price_num'].mean())}" if not jeonse_df.empty else "-")
        m4.metric("월세 매물", f"{len(wolse_df):,}건")
        m5.metric("매매 최저가", fmt_price(sale_df["price_num"].min()) if not sale_df.empty else "-")

        with st.expander("🏢 단지별 매물 건수 및 최저·평균 호가 요약표 보기", expanded=False):
            summary_rows = []
            for (d_nm, a_nm), grp in naver_df.groupby(["법정동", "아파트명"]):
                s_grp = grp[grp["거래구분"] == "매매"]
                j_grp = grp[grp["거래구분"] == "전세"]
                summary_rows.append({
                    "법정동": d_nm,
                    "아파트명": a_nm,
                    "세대수": int(grp["세대수"].max()),
                    "준공년도": int(grp["준공년도"].max()),
                    "전체매물": len(grp),
                    "매매건수": len(s_grp),
                    "매매최저가": fmt_price(s_grp["price_num"].min()) if not s_grp.empty else "-",
                    "매매평균가": fmt_price(s_grp["price_num"].mean()) if not s_grp.empty else "-",
                    "전세건수": len(j_grp),
                    "전세최저가": fmt_price(j_grp["price_num"].min()) if not j_grp.empty else "-",
                })
            df_apt_sum = pd.DataFrame(summary_rows).sort_values(by=["전체매물", "매매건수"], ascending=False)
            st.dataframe(df_apt_sum, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("🔍 상세 매물 조건 검색 및 필터링")

        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            f_trade = st.selectbox("거래구분", ["전체", "매매", "전세", "월세"])
        with fc2:
            dong_list_csv = ["전체 법정동"] + sorted(list(naver_df["법정동"].dropna().unique()))
            f_dong = st.selectbox("법정동 선택", dong_list_csv)
        with fc3:
            f_apt_kw = st.text_input("아파트명 검색", placeholder="예: 롯데캐슬, 자이...")
        with fc4:
            f_dir = st.selectbox("향 (방향)", ["전체 방향", "남향 계열 (남/남동/남서)", "남향", "남동향", "남서향", "동향", "서향"])

        fc5, fc6, fc7, fc8 = st.columns(4)
        with fc5:
            f_feat_kw = st.text_input("매물 특징 검색", placeholder="예: 올수리, 조망, 급매, 역세권...")
        with fc6:
            f_py_range = st.slider("평형 범위 (평)", min_value=0, max_value=100, value=(0, 100))
        with fc7:
            f_price_range = st.slider("가격 범위 (억 원)", min_value=0.0, max_value=50.0, value=(0.0, 50.0), step=0.5)
        with fc8:
            f_floor_opt = st.selectbox("층수 필터", ["모두 포함", "저·고층 제외 (중층만)", "저층만", "고층만"])

        fc9, fc10, fc11, fc12 = st.columns(4)
        with fc9:
            f_min_year = st.number_input("최소 준공년도", min_value=0, max_value=2030, value=0, step=1)
        with fc10:
            f_min_ho = st.number_input("최소 세대수", min_value=0, max_value=10000, value=0, step=100)
        with fc11:
            f_sort = st.selectbox("정렬 기준", ["아파트명순", "가격 낮은순 ↑", "가격 높은순 ↓", "평형 넓은순 ↓", "준공 최신순 ↓"])
        with fc12:
            st.write("")
            st.write("")
            only_has_url = st.checkbox("네이버 링크 있는 매물만", value=False)

        fdf = naver_df.copy()
        if f_trade != "전체":
            fdf = fdf[fdf["거래구분"] == f_trade]
        if f_dong != "전체 법정동":
            fdf = fdf[fdf["법정동"] == f_dong]
        if f_apt_kw.strip():
            fdf = fdf[fdf["아파트명"].str.contains(f_apt_kw.strip(), case=False, na=False)]
        if f_dir == "남향 계열 (남/남동/남서)":
            fdf = fdf[fdf["향"].isin(["남향", "남동향", "남서향"])]
        elif f_dir != "전체 방향":
            fdf = fdf[fdf["향"] == f_dir]
        if f_feat_kw.strip():
            fdf = fdf[fdf["매물특징"].str.contains(f_feat_kw.strip(), case=False, na=False)]

        if f_py_range != (0, 100):
            fdf = fdf[(fdf["pyrom_num"] == 0) | ((fdf["pyrom_num"] >= f_py_range[0]) & (fdf["pyrom_num"] <= f_py_range[1]))]
        if f_price_range != (0.0, 50.0):
            min_man = f_price_range[0] * 10000
            max_man = f_price_range[1] * 10000
            fdf = fdf[(fdf["price_num"] >= min_man) & (fdf["price_num"] <= max_man)]

        if f_floor_opt == "저·고층 제외 (중층만)":
            fdf = fdf[fdf["floor_cat"] == "중"]
        elif f_floor_opt == "저층만":
            fdf = fdf[fdf["floor_cat"] == "저"]
        elif f_floor_opt == "고층만":
            fdf = fdf[fdf["floor_cat"] == "고"]

        if f_min_year > 0:
            fdf = fdf[(fdf["준공년도"] == 0) | (fdf["준공년도"] >= f_min_year)]
        if f_min_ho > 0:
            fdf = fdf[(fdf["세대수"] == 0) | (fdf["세대수"] >= f_min_ho)]
        if only_has_url:
            fdf = fdf[fdf["네이버부동산URL"].astype(str).str.startswith("http")]

        if f_sort == "가격 낮은순 ↑":
            fdf = fdf.sort_values(by="price_num", ascending=True)
        elif f_sort == "가격 높은순 ↓":
            fdf = fdf.sort_values(by="price_num", ascending=False)
        elif f_sort == "평형 넓은순 ↓":
            fdf = fdf.sort_values(by="pyrom_num", ascending=False)
        elif f_sort == "준공 최신순 ↓":
            fdf = fdf.sort_values(by="준공년도", ascending=False)
        else:
            fdf = fdf.sort_values(by=["아파트명", "price_num"], ascending=[True, True])

        st.markdown(f"**✅ 필터링 결과: 전체 {len(naver_df):,}건 중 `{len(fdf):,}건` 일치**")

        display_cols = [
            "법정동", "아파트명", "거래구분", "공급/전용면적", "환산평형",
            "세대수", "준공년도", "층수", "향", "가격", "매물특징", "중개업소(부동산)", "네이버부동산URL"
        ]
        st.dataframe(
            fdf[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "네이버부동산URL": st.column_config.LinkColumn("단지 링크", display_text="네이버 열기 ↗"),
                "세대수": st.column_config.NumberColumn("세대수", format="%d세대"),
                "준공년도": st.column_config.NumberColumn("준공", format="%d년"),
            },
        )

        csv_filtered = fdf[display_cols].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="📥 필터링된 네이버 매물 CSV 다운로드",
            data=csv_filtered,
            file_name="filtered_naver_listings.csv",
            mime="text/csv",
        )

# ---------------------------------------------------------------------
# TAB 2: 국토교통부 실거래가 & 네이버 호가 괴리율 심층 분석
# ---------------------------------------------------------------------
with tab_molit:
    if "molit_result" not in st.session_state:
        st.info("👈 왼쪽 사이드바에서 **[1. 분석 지역]**과 **[2. 조회 기간]**을 선택한 후 **[🚀 국토부 실거래가 조회 실행]** 버튼을 눌러주세요.")
    else:
        res = st.session_state["molit_result"]
        all_sales = res["sales"]
        all_rents = res["rents"]
        chosen_dong = res["selected_dong"]

        if not all_sales:
            st.warning(f"조회된 매매 실거래 데이터가 없습니다. {res['err']}")
        else:
            if chosen_dong != "선택 안함":
                sales = [s for s in all_sales if chosen_dong in s["dong"] or s["dong"] in chosen_dong]
                rents = [r for r in all_rents if chosen_dong in r["dong"] or r["dong"] in chosen_dong]
            else:
                sales = all_sales
                rents = all_rents

            st.subheader(f"📊 {res['region']} 최근 {res['months']}개월 실거래가 심층 분석")

            if not sales:
                st.info(f"'{chosen_dong}' 지역에 최근 {res['months']}개월간 등록된 아파트 매매 실거래가 없습니다.")
            else:
                apt_counts = {}
                for s in sales:
                    key = (s["dong"], s["apt_name"])
                    apt_counts[key] = apt_counts.get(key, 0) + 1

                sorted_apts = sorted(apt_counts.items(), key=lambda x: (-x[1], x[0][0], x[0][1]))
                apt_labels = [f"[{k[0]}] {k[1]} (매매 {cnt}건)" for k, cnt in sorted_apts]

                sel_apt_idx = st.selectbox(
                    "🏢 분석할 아파트 단지 선택:",
                    range(len(apt_labels)),
                    format_func=lambda i: apt_labels[i],
                )

                target_dong, target_apt = sorted_apts[sel_apt_idx][0]

                apt_sales = sorted([s for s in sales if s["dong"] == target_dong and s["apt_name"] == target_apt], key=lambda x: x["date"])
                apt_rents = sorted([r for r in rents if r["dong"] == target_dong and r["apt_name"] == target_apt], key=lambda x: x["date"])

                areas = sorted(list({round(s["area"]) for s in apt_sales if s["area"] > 0}))
                area_opts = ["전체 평형"] + [f"전용 {a}㎡ (약 {round(a * 0.3025 * 1.32)}평형)" for a in areas]
                sel_area_txt = st.radio("📐 전용면적 선택", area_opts, horizontal=True)

                if sel_area_txt != "전체 평형":
                    t_area = int(re.search(r"전용 (\d+)㎡", sel_area_txt).group(1))
                    apt_sales = [s for s in apt_sales if round(s["area"]) == t_area]
                    apt_rents = [r for r in apt_rents if round(r["area"]) == t_area]

                if apt_sales:
                    recent_3 = apt_sales[-3:]
                    recent_avg = round(sum(s["price"] for s in recent_3) / len(recent_3))
                    latest = apt_sales[-1]
                    peak = max(apt_sales, key=lambda x: x["price"])
                    rec_rate = (recent_avg / peak["price"]) * 100

                    naver_min, naver_avg, naver_cnt = 0, 0, 0
                    if naver_df is not None and "아파트명" in naver_df.columns:
                        t_norm = normalize_apt_name(target_apt)
                        matched_n = naver_df[
                            (naver_df["거래구분"] == "매매")
                            & (naver_df["아파트명"].apply(lambda x: t_norm in normalize_apt_name(x) or normalize_apt_name(x) in t_norm))
                        ]
                        if not matched_n.empty:
                            naver_cnt = len(matched_n)
                            naver_min = int(matched_n["price_num"].min())
                            naver_avg = int(matched_n["price_num"].mean())

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("최근 실거래가 (직전 3건 평균)", fmt_price(recent_avg), f"최근: {latest['date']} / {fmt_price(latest['price'])} ({latest['floor']}층)")

                    if naver_min > 0:
                        diff = naver_min - recent_avg
                        diff_pct = (diff / recent_avg) * 100
                        c2.metric(f"네이버 최저 호가 ({naver_cnt}건 중)", f"{diff_pct:+.1f}%", f"최저 {fmt_price(naver_min)} / 평균 {fmt_price(naver_avg)}")
                    else:
                        c2.metric("네이버 호가 비교", "매물 없음/미연동", "CSV 업로드 시 자동 비교")

                    c3.metric("조회기간 최고가(전고점) 대비 회복률", f"{rec_rate:.1f}%", f"최고가: {fmt_price(peak['price'])} ({peak['date']})")

                    if apt_rents:
                        rent_avg = round(sum(r["deposit"] for r in apt_rents[-5:]) / len(apt_rents[-5:]))
                        j_ratio = (rent_avg / recent_avg) * 100
                        c4.metric("전세가율 (매매-전세 갭)", f"{j_ratio:.1f}%", f"전세평균 {fmt_price(rent_avg)} (갭 {fmt_price(recent_avg - rent_avg)})")
                    else:
                        c4.metric("전세가율", "전세 거래 부족", "최근 순수 전세 실거래 없음")

                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=[f"{s['date']} ({s['floor']}층)" for s in apt_sales],
                        y=[round(s["price"] / 10000, 2) for s in apt_sales],
                        mode="lines+markers",
                        name="국토부 실거래가 (억)",
                        line=dict(color="#1c7ed6", width=2.5),
                        marker=dict(size=7),
                    ))
                    if naver_min > 0:
                        fig.add_hline(y=round(naver_min / 10000, 2), line_dash="dash", line_color="red", annotation_text=f"네이버 최저호가 ({fmt_price(naver_min)})")
                    if naver_avg > 0 and naver_avg != naver_min:
                        fig.add_hline(y=round(naver_avg / 10000, 2), line_dash="dot", line_color="green", annotation_text=f"네이버 평균호가 ({fmt_price(naver_avg)})")

                    fig.update_layout(
                        title=f"📈 [{target_dong}] {target_apt} 실거래 추세 차트 ({res['months']}개월, 단위: 억 원)",
                        yaxis_title="거래금액 (억 원)",
                        height=400,
                        margin=dict(l=20, r=20, t=50, b=20),
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    df_detail = pd.DataFrame(apt_sales[::-1])[["date", "area", "floor", "price"]]
                    df_detail["실거래가"] = df_detail["price"].apply(fmt_price)
                    df_show = df_detail[["date", "area", "floor", "실거래가"]]
                    df_show.columns = ["계약일", "전용면적(㎡)", "층수", "실거래가"]
                    st.dataframe(df_show, use_container_width=True, hide_index=True)

                    csv_data = df_show.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                    st.download_button(
                        "📥 이 단지 실거래가 엑셀(CSV) 다운로드",
                        data=csv_data,
                        file_name=f"{target_dong}_{target_apt}_{res['months']}개월_실거래가.csv",
                        mime="text/csv",
                    )
