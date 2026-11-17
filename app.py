import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go

# =====================================================================
# 페이지 기본 설정
# =====================================================================
st.set_page_config(
    page_title="국토부 실거래가 & 네이버 호가 통합 대시보드",
    page_icon="🏢",
    layout="wide",
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
# 전국 법정동 코드 데이터 로드 (GitHub 공개 표준 법정동 TSV 캐싱)
# =====================================================================
@st.cache_data(ttl=86400 * 7, show_spinner=False)
def load_all_dong_map():
    """전국 법정동 코드표에서 시군구 5자리 코드별 읍/면/동 목록 매핑"""
    urls = [
        "https://raw.githubusercontent.com/cosmosfarm/korea-administrative-district/master/법정동코드%20전체자료.txt",
        "https://raw.githubusercontent.com/kostat-data/korea-bjd-code/main/bjd_code.txt",
    ]
    dong_by_code5 = {}
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw_bytes = resp.read()
            try:
                text = raw_bytes.decode("cp949")
            except UnicodeDecodeError:
                text = raw_bytes.decode("utf-8", errors="ignore")

            for line in text.splitlines()[1:]:
                parts = line.strip().split("\t")
                if len(parts) < 3:
                    continue
                bjd_code, full_name, status = parts[0].strip(), parts[1].strip(), parts[2].strip()
                if status != "존재" or len(bjd_code) != 10:
                    continue
                # 시군구(끝 5자리 00000) 제외, 리(끝 2자리 != 00) 제외 -> 읍/면/동만 추출
                if bjd_code.endswith("00000") or not bjd_code.endswith("00"):
                    continue
                code5 = bjd_code[:5]
                dong_name = full_name.split(" ")[-1]
                dong_by_code5.setdefault(code5, set()).add(dong_name)

            if dong_by_code5:
                return {k: sorted(list(v)) for k, v in dong_by_code5.items()}
        except Exception:
            continue
    return {}


# =====================================================================
# 국토교통부 아파트 매매 / 전월세 실거래가 API 병렬 고속 수집
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
    """단일 연월(YYYYMM)의 매매 + 전월세 데이터를 동시에 조회"""
    sale_endpoints = [
        "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
        "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    ]
    rent_ep = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

    month_sales, month_rents = [], []
    err_msg = ""

    # 1) 매매 조회
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

    # 2) 전월세 조회 (순수 전세만 추출)
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


@st.cache_data(ttl=3600, show_spinner=False)
def collect_molit_transactions(lawd_cd_5, service_key, months=24):
    """최대 120개월까지 병렬 스레드로 빠르게 조회"""
    if not service_key or not lawd_cd_5:
        return [], [], "인증키 또는 지역코드가 없습니다."

    ym_list = get_recent_ym_list(months)
    sale_records, rent_records = [], []
    first_err = ""

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
st.caption("최대 120개월(10년) 국토부 실거래가 추세와 PC에서 수집한 네이버 매물 CSV를 실시간으로 비교·분석합니다.")

dong_map = load_all_dong_map()

with st.sidebar:
    st.header("📍 1. 분석 지역 선택")

    # 1) 시/도 선택
    sido_names = list(REGION_DATA.keys())
    default_sido_idx = sido_names.index("경기도")
    sel_sido_name = st.selectbox("1) 시/도 선택", sido_names, index=default_sido_idx)

    # 2) 시/군/구 선택
    sgg_dict = REGION_DATA[sel_sido_name]
    sgg_names = list(sgg_dict.keys())
    default_sgg_idx = sgg_names.index("이천시") if "이천시" in sgg_names else 0
    sel_sgg_name = st.selectbox("2) 시/군/구 선택", sgg_names, index=default_sgg_idx)
    lawd_cd_5 = sgg_dict[sel_sgg_name]

    # 3) 읍/면/동 선택 (미선택 시 기본 '선택 안함' -> 시/군/구 전체)
    dong_candidates = dong_map.get(lawd_cd_5, [])
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
        help="최대 120개월(10년)까지 조회 가능합니다. 기간이 길면 5~10초 정도 소요됩니다.",
    )

    st.divider()
    st.header("📂 3. 네이버 매물 CSV 연동 (선택)")
    uploaded_csv = st.file_uploader(
        "PC 수집기 결과 CSV 파일 업로드",
        type=["csv"],
        help="PC에서 수집한 *_all_listings.csv 파일을 올리면 현재 호가와 실거래가 괴리율을 자동 비교합니다.",
    )

    run_btn = st.button("🚀 실거래가 조회 및 분석 실행", type="primary", use_container_width=True)

# 업로드된 CSV 파싱
naver_df = None
if uploaded_csv is not None:
    try:
        naver_df = pd.read_csv(uploaded_csv)
        if "가격" in naver_df.columns:
            naver_df["price_num"] = naver_df["가격"].apply(parse_price_to_manwon)
        st.sidebar.success(f"✅ 매물 CSV 로드 완료 ({len(naver_df)}건)")
    except Exception as e:
        st.sidebar.error(f"CSV 읽기 오류: {e}")

# 데이터 조회 실행
if run_btn:
    region_label = (
        f"{sel_sido_name} {sel_sgg_name}"
        if sel_dong_sidebar == "선택 안함"
        else f"{sel_sido_name} {sel_sgg_name} {sel_dong_sidebar}"
    )
    with st.spinner(f"🏛️ {region_label} 최근 {months}개월({months/12:.1f}년) 국토부 실거래가 조회 중..."):
        sales, rents, err_msg = collect_molit_transactions(lawd_cd_5, api_key, months)
        st.session_state["molit_result"] = {
            "region": region_label,
            "selected_dong": sel_dong_sidebar,
            "months": months,
            "sales": sales,
            "rents": rents,
            "err": err_msg,
        }

# 결과 표시
if "molit_result" in st.session_state:
    res = st.session_state["molit_result"]
    all_sales = res["sales"]
    all_rents = res["rents"]
    chosen_dong = res["selected_dong"]

    if not all_sales:
        st.warning(f"조회된 매매 실거래 데이터가 없습니다. {res['err']}")
    else:
        # 사이드바에서 동을 선택한 경우 해당 동으로 즉시 필터링
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
            # 단지 목록 생성 (거래건수 많은 순)
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

            apt
