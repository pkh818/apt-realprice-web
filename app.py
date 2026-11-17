import os
import re
import time
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from difflib import SequenceMatcher

import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

# =====================================================================
# 페이지 기본 설정
# =====================================================================
st.set_page_config(
    page_title="부동산 매물 & 국토부 실거래가 통합 대시보드",
    page_icon="🏢",
    layout="wide",
)

# Streamlit Secrets에서 API 키 로드 (없으면 기본값 사용)
DEFAULT_API_KEY = st.secrets.get(
    "MOLIT_API_KEY",
    "31a08f319d25f742296a53f8cf22e82830a5aae5efd82cd666d17b62e2f9e64b",
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://new.land.naver.com/",
}


# =====================================================================
# 1. 네이버 부동산 지역 및 단지 조회 (API 우선 + Headless 크롬 백업)
# =====================================================================
@st.cache_resource
def get_headless_driver():
    """클라우드 리눅스(Chromium)용 Headless 드라이버 초기화"""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    else:
        service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.get("https://new.land.naver.com/")
    time.sleep(1.5)
    return driver


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_regions(cortar_no="0000000000"):
    """시/도, 시/군/구, 읍/면/동 목록 조회"""
    url = f"https://new.land.naver.com/api/regions/list?cortarNo={cortar_no}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            return res.json().get("regionList", [])
    except Exception:
        pass

    # 차단 시 Headless 브라우저로 우회 조회
    driver = get_headless_driver()
    driver.get(url)
    time.sleep(0.6)
    raw = driver.find_element(By.TAG_NAME, "pre").text
    return json.loads(raw).get("regionList", [])


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_complexes_in_dong(dong_code):
    """특정 법정동의 아파트 단지 목록 조회"""
    url = f"https://new.land.naver.com/api/regions/complexes?cortarNo={dong_code}&realEstateType=APT&order="
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            return res.json().get("complexList", [])
    except Exception:
        pass

    driver = get_headless_driver()
    driver.get(url)
    time.sleep(0.6)
    raw = driver.find_element(By.TAG_NAME, "body").text
    return json.loads(raw).get("complexList", [])


def fetch_naver_articles_for_complex(complex_no, dong_name, complex_name, households, built_year):
    """특정 단지의 현재 네이버 부동산 매물(매매/전세/월세) 호가 수집"""
    url = (
        f"https://new.land.naver.com/api/articles/complex/{complex_no}"
        f"?realEstateType=APT&tradeType=&tag=%3A%3A%3A%3A%3A%3A%3A%3A&rentPriceMin=0&rentPriceMax=900000000"
        f"&priceMin=0&priceMax=900000000&areaMin=0&areaMax=900000000&oldBuildYears&recentlyBuildYears"
        f"&minHouseHoldCount&maxHouseHoldCount&showArticle=false&sameAddressGroup=true&minMaintenanceCost"
        f"&maxMaintenanceCost&priceType=RETAIL&directions=&page=1&complexNo={complex_no}&buildingNos=&areaNos=&type=list&order=rank"
    )
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            articles = res.json().get("articleList", [])
    except Exception:
        pass

    if not articles:
        try:
            driver = get_headless_driver()
            driver.get(url)
            time.sleep(0.6)
            raw = driver.find_element(By.TAG_NAME, "pre").text
            articles = json.loads(raw).get("articleList", [])
        except Exception:
            articles = []

    parsed = []
    for art in articles:
        trade_type = art.get("tradeTypeName", "")
        raw_price = art.get("dealOrWarrantPrc", "")
        rent_prc = art.get("rentPrc", "")
        if trade_type == "월세" and rent_prc:
            price_formatted = f"{raw_price}/{rent_prc}"
        else:
            price_formatted = raw_price

        price_num = parse_price_to_manwon(raw_price)
        if price_num <= 0:
            continue

        area1 = art.get("area1", 0)  # 공급면적
        area2 = art.get("area2", 0)  # 전용면적
        area_name = art.get("areaName", "")
        pyrom = int(round(float(area1) * 0.3025)) if area1 else 0
        area_spec = f"{area1}/{area2}㎡({area_name})" if area1 and area2 else ""

        floor_info = art.get("floorInfo", "")
        floor_cat = "중"
        if floor_info:
            top_p = floor_info.split("/")[0]
            if top_p == "저" or (top_p.isdigit() and int(top_p) <= 3):
                floor_cat = "저"
            elif top_p in ["고", "탑"]:
                floor_cat = "고"

        parsed.append({
            "dong": dong_name,
            "name": complex_name,
            "code": str(complex_no),
            "trade_type": trade_type,
            "area_spec": area_spec,
            "exclu_m2": float(area2) if area2 else 0.0,
            "pyrom": pyrom,
            "households": households,
            "built_year": built_year,
            "floor": floor_cat,
            "floor_raw": floor_info,
            "direction": art.get("direction", "-"),
            "features": art.get("articleFeatureDesc", "-"),
            "price": price_num,
            "price_formatted": price_formatted,
            "realtor": art.get("realtorName", "-"),
        })
    return parsed


# =====================================================================
# 2. 국토교통부 아파트 매매 / 전월세 실거래가 API 수집 및 매칭 (기존 로직 유지)
# =====================================================================
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


@st.cache_data(ttl=3600, show_spinner=False)
def collect_molit_transactions(lawd_cd_5, service_key, months=24):
    if not service_key or not lawd_cd_5:
        return [], []

    ym_list = get_recent_ym_list(months)
    sale_endpoints = [
        "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
        "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    ]
    rent_ep = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"

    sale_records, rent_records = [], []
    active_sale_ep = sale_endpoints[0]

    for ym in ym_list:
        for ep in [active_sale_ep] + [e for e in sale_endpoints if e != active_sale_ep]:
            try:
                xml_str = fetch_molit_xml(ep, service_key, lawd_cd_5, ym)
                root = ET.fromstring(xml_str)
                res_code = get_xml_text(root, [".//resultCode"])
                if res_code and res_code not in ["00", "000"]:
                    continue
                active_sale_ep = ep
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

                    sale_records.append({
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
            except Exception:
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

                    rent_records.append({
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

    return sale_records, rent_records


def normalize_apt_name(name):
    s = re.sub(r"\([^)]*\)", "", name)
    s = re.sub(r"제(\d+)", r"\1", s)
    s = s.replace("아파트", "").replace("도시", "")
    return re.sub(r"[^가-힣a-zA-Z0-9]", "", s).lower()


def calc_name_similarity(c_norm, m_norm):
    if not c_norm or not m_norm:
        return 0.0
    if c_norm == m_norm:
        return 1.0
    if c_norm in m_norm or m_norm in c_norm:
        ratio = min(len(c_norm), len(m_norm)) / max(len(c_norm), len(m_norm))
        return 0.82 + (ratio * 0.15)
    c_nums = re.findall(r"\d+", c_norm)
    m_nums = re.findall(r"\d+", m_norm)
    if c_nums and m_nums and c_nums != m_nums:
        return 0.0
    common_chars = sum(1 for ch in set(c_norm) if ch in m_norm)
    char_overlap = common_chars / max(len(set(c_norm)), len(set(m_norm)))
    seq_ratio = SequenceMatcher(None, c_norm, m_norm).ratio()
    return max(seq_ratio, char_overlap * 0.9)


def match_molit_to_complexes(master_complexes, sale_records, rent_records):
    molit_groups = {}
    for r in sale_records:
        key = (r["dong"].strip(), r["apt_name"].strip())
        molit_groups.setdefault(key, {"sales": [], "rents": []})["sales"].append(r)
    for r in rent_records:
        key = (r["dong"].strip(), r["apt_name"].strip())
        molit_groups.setdefault(key, {"sales": [], "rents": []})["rents"].append(r)

    matched_map = {}
    for c in master_complexes:
        c_dong = c["dong"].strip()
        c_name = c["name"].strip()
        c_key = c["code"] if c["code"] else c_name
        c_norm = normalize_apt_name(c_name)

        dong_candidates = [
            (m_dong, m_apt, grp)
            for (m_dong, m_apt), grp in molit_groups.items()
            if m_dong == c_dong or c_dong.endswith(m_dong) or m_dong.endswith(c_dong)
        ]

        best_grp, best_score = None, 0.0
        for _, m_apt, grp in dong_candidates:
            score = calc_name_similarity(c_norm, normalize_apt_name(m_apt))
            if score > best_score:
                best_score, best_grp = score, grp

        if best_score < 0.58:
            for (_, m_apt), grp in molit_groups.items():
                score = calc_name_similarity(c_norm, normalize_apt_name(m_apt))
                if score >= 0.78 and score > best_score:
                    best_score, best_grp = score, grp

        if best_grp and best_score >= 0.58:
            matched_map[c_key] = {
                "sales": sorted(best_grp["sales"], key=lambda x: x["date"]),
                "rents": sorted(best_grp["rents"], key=lambda x: x["date"]),
            }
        else:
            matched_map[c_key] = {"sales": [], "rents": []}
    return matched_map


# =====================================================================
# 3. Streamlit 웹 UI 렌더링
# =====================================================================
st.title("🏢 네이버 부동산 매물 & 국토부 실거래가 통합 대시보드")
st.caption("웹에서 지역을 선택하면 단지별 호가 매물과 국토교통부 실거래가 추세·전세가율·괴리율을 실시간으로 비교합니다.")

# --- 사이드바: 지역 및 API 설정 ---
with st.sidebar:
    st.header("📍 1. 지역 및 조회 설정")

    sido_list = fetch_regions("0000000000")
    sido_names = [r["cortarName"] for r in sido_list]
    default_sido_idx = sido_names.index("경기도") if "경기도" in sido_names else 0
    sel_sido_name = st.selectbox("시/도 선택", sido_names, index=default_sido_idx)
    sel_sido = next(r for r in sido_list if r["cortarName"] == sel_sido_name)

    sigungu_list = fetch_regions(sel_sido["cortarNo"])
    sigungu_names = [r["cortarName"] for r in sigungu_list]
    default_sgg_idx = sigungu_names.index("이천시") if "이천시" in sigungu_names else 0
    sel_sgg_name = st.selectbox("시/군/구 선택", sigungu_names, index=default_sgg_idx)
    sel_sgg = next(r for r in sigungu_list if r["cortarName"] == sel_sgg_name)

    dong_list = fetch_regions(sel_sgg["cortarNo"])
    dong_names = ["전체 (시/군/구 전체)"] + [r["cortarName"] for r in dong_list]
    sel_dong_name = st.selectbox("읍/면/동 선택", dong_names)

    st.divider()
    st.header("🏛️ 2. 국토부 API 설정")
    api_key = st.text_input("공공데이터포털 인증키", value=DEFAULT_API_KEY, type="password")
    months = st.slider("실거래가 조회 기간(개월)", min_value=6, max_value=48, value=24, step=6)
    fetch_naver_opt = st.checkbox("네이버 현재 매물 호가도 함께 수집", value=True)

    run_btn = st.button("🚀 데이터 조회 및 분석 시작", type="primary", use_container_width=True)

# --- 조회 실행 ---
if run_btn:
    lawd_cd_5 = str(sel_sgg["cortarNo"])[:5]
    if sel_dong_name.startswith("전체"):
        region_title = f"{sel_sido_name} {sel_sgg_name} 전체"
        target_dongs = dong_list
    else:
        selected_dong = next(r for r in dong_list if r["cortarName"] == sel_dong_name)
        region_title = f"{sel_sido_name} {sel_sgg_name} {sel_dong_name}"
        target_dongs = [selected_dong]

    progress_bar = st.progress(0, text="아파트 단지 목록을 불러오는 중...")

    master_complexes = []
    for idx, d in enumerate(target_dongs, start=1):
        d_code = d.get("cortarNo")
        d_name = d.get("areaName") or d.get("cortarName") or ""
        comps = fetch_complexes_in_dong(d_code)
        for c in comps:
            master_complexes.append({
                "dong": d_name,
                "name": c.get("complexName", ""),
                "code": str(c.get("complexNo", "")),
                "households": int(c.get("totalHouseholdCount", 0) or 0),
                "built_year": int(str(c.get("useApproveYmd", "0"))[:4] or 0),
            })
        progress_bar.progress(int(idx / max(len(target_dongs), 1) * 30), text=f"[{idx}/{len(target_dongs)}] {d_name} 단지 목록 수집 중...")

    # 중복 단지 제거
    seen_codes = set()
    unique_complexes = []
    for c in master_complexes:
        if c["code"] not in seen_codes:
            seen_codes.add(c["code"])
            unique_complexes.append(c)

    progress_bar.progress(45, text=f"국토교통부 실거래가({months}개월) 조회 중...")
    sale_records, rent_records = collect_molit_transactions(lawd_cd_5, api_key, months)
    molit_matched_map = match_molit_to_complexes(unique_complexes, sale_records, rent_records)

    all_listings = []
    if fetch_naver_opt and unique_complexes:
        for idx, c in enumerate(unique_complexes, start=1):
            pct = 45 + int((idx / len(unique_complexes)) * 55)
            progress_bar.progress(min(pct, 99), text=f"네이버 호가 매물 수집 중 ({idx}/{len(unique_complexes)}): {c['name']}")
            items = fetch_naver_articles_for_complex(
                c["code"], c["dong"], c["name"], c["households"], c["built_year"]
            )
            all_listings.extend(items)
            time.sleep(0.15)

    progress_bar.progress(100, text="✅ 모든 데이터 수집 및 매칭 완료!")
    time.sleep(0.4)
    progress_bar.empty()

    st.session_state["result"] = {
        "region_title": region_title,
        "complexes": unique_complexes,
        "listings": all_listings,
        "molit_map": molit_matched_map,
    }

# --- 결과 대시보드 출력 ---
if "result" in st.session_state:
    res = st.session_state["result"]
    region_title = res["region_title"]
    complexes = res["complexes"]
    listings = res["listings"]
    molit_map = res["molit_map"]

    st.subheader(f"📊 {region_title} 분석 결과 (총 {len(complexes)}개 단지 / 매물 {len(listings)}건)")

    # 1) 단지 선택 및 실거래가 심층 분석 섹션
    complex_options = [
        f"[{c['dong']}] {c['name']} (실거래 {len(molit_map.get(c['code'], {}).get('sales', []))}건)"
        for c in complexes
    ]
    if complex_options:
        sel_idx = st.selectbox("🔍 심층 분석할 아파트 단지를 선택하세요:", range(len(complex_options)), format_func=lambda i: complex_options[i])
        target_comp = complexes[sel_idx]
        c_key = target_comp["code"]
        m_entry = molit_map.get(c_key, {"sales": [], "rents": []})
        sales = m_entry["sales"]
        rents = m_entry["rents"]

        # 전용면적 탭 필터
        area_set = sorted(list({round(s["area"]) for s in sales if s["area"] > 0}))
        area_choices = ["전체 평형"] + [f"전용 {a}㎡ (약 {round(a * 0.3025 * 1.32)}평형)" for a in area_set]
        sel_area_label = st.radio("전용면적 선택", area_choices, horizontal=True)

        if sel_area_label != "전체 평형":
            target_area = int(re.search(r"전용 (\d+)㎡", sel_area_label).group(1))
            sales_f = [s for s in sales if round(s["area"]) == target_area]
            rents_f = [r for r in rents if round(r["area"]) == target_area]
            naver_sales = [
                n for n in listings
                if n["code"] == c_key and n["trade_type"] == "매매" and abs(round(n["exclu_m2"]) - target_area) <= 2
            ]
        else:
            sales_f = sales
            rents_f = rents
            naver_sales = [n for n in listings if n["code"] == c_key and n["trade_type"] == "매매"]

        if sales_f:
            recent_3 = sales_f[-3:]
            recent_avg = round(sum(s["price"] for s in recent_3) / len(recent_3))
            latest = sales_f[-1]
            peak = max(sales_f, key=lambda x: x["price"])
            recovery_rate = (recent_avg / peak["price"]) * 100

            # KPI 카드 4개
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("최근 실거래가 (직전 3건 평균)", fmt_price(recent_avg), f"최근: {latest['date']} ({fmt_price(latest['price'])})")

            if naver_sales:
                naver_min = min(n["price"] for n in naver_sales)
                naver_avg = round(sum(n["price"] for n in naver_sales) / len(naver_sales))
                diff = naver_min - recent_avg
                diff_pct = (diff / recent_avg) * 100
                k2.metric("네이버 최저 호가 vs 실거래", f"{diff_pct:+.1f}%", f"최저호가 {fmt_price(naver_min)}")
            else:
                naver_min, naver_avg = 0, 0
                k2.metric("네이버 최저 호가", "매물 없음", "동일 평형 매물 없음")

            k3.metric("전고점 대비 회복률", f"{recovery_rate:.1f}%", f"최고가: {fmt_price(peak['price'])} ({peak['date']})")

            if rents_f:
                rent_avg = round(sum(r["deposit"] for r in rents_f[-5:]) / len(rents_f[-5:]))
                j_ratio = (rent_avg / recent_avg) * 100
                k4.metric("전세가율 (매매-전세 갭)", f"{j_ratio:.1f}%", f"전세평균 {fmt_price(rent_avg)} (갭 {fmt_price(recent_avg - rent_avg)})")
            else:
                k4.metric("전세가율", "데이터 부족", "최근 순수 전세 거래 없음")

            # Plotly 실거래 추세 차트
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=[f"{s['date']} ({s['floor']}층)" for s in sales_f],
                y=[round(s["price"] / 10000, 2) for s in sales_f],
                mode="lines+markers",
                name="국토부 실거래가 (억)",
                line=dict(color="#1c7ed6", width=2.5),
                marker=dict(size=8),
            ))
            if naver_min > 0:
                fig.add_hline(y=round(naver_min / 10000, 2), line_dash="dash", line_color="red", annotation_text=f"네이버 최저호가 ({fmt_price(naver_min)})")
            if naver_avg > 0 and naver_avg != naver_min:
                fig.add_hline(y=round(naver_avg / 10000, 2), line_dash="dot", line_color="green", annotation_text=f"네이버 평균호가 ({fmt_price(naver_avg)})")

            fig.update_layout(
                title=f"📈 {target_comp['name']} 실거래가 추세 및 현재 호가 비교 (단위: 억 원)",
                yaxis_title="금액 (억 원)",
                height=380,
                margin=dict(l=20, r=20, t=50, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

            # 실거래 상세 이력 표
            with st.expander("📋 국토교통부 실거래 상세 이력 보기 (최신순)", expanded=False):
                df_sales = pd.DataFrame(sales_f[::-1])[["date", "area", "floor", "price"]]
                df_sales["실거래가"] = df_sales["price"].apply(fmt_price)
                df_sales.columns = ["계약일", "전용면적(㎡)", "층", "원단위(만원)", "실거래가"]
                st.dataframe(df_sales[["계약일", "전용면적(㎡)", "층", "실거래가"]], use_container_width=True, hide_index=True)
        else:
            st.info("선택한 단지(또는 평형)의 국토교통부 매매 실거래 내역이 없습니다.")

    st.divider()

    # 2) 전체 수집 매물 필터 및 CSV 다운로드
    st.subheader("📋 수집된 전체 매물 호가 리스트")
    if listings:
        df_list = pd.DataFrame(listings)
        f1, f2, f3 = st.columns(3)
        sel_trade = f1.selectbox("거래구분 필터", ["전체", "매매", "전세", "월세"])
        kw_search = f2.text_input("단지명 / 법정동 / 특징 검색", "")
        max_eok = f3.number_input("최대 가격 (억 원, 0은 전체)", min_value=0.0, value=0.0, step=0.5)

        if sel_trade != "전체":
            df_list = df_list[df_list["trade_type"] == sel_trade]
        if kw_search:
            df_list = df_list[
                df_list["name"].str.contains(kw_search, case=False, na=False)
                | df_list["dong"].str.contains(kw_search, case=False, na=False)
                | df_list["features"].str.contains(kw_search, case=False, na=False)
            ]
        if max_eok > 0:
            df_list = df_list[df_list["price"] <= max_eok * 10000]

        display_cols = ["dong", "name", "trade_type", "area_spec", "pyrom", "floor_raw", "direction", "price_formatted", "features", "realtor"]
        df_show = df_list[display_cols].copy()
        df_show.columns = ["법정동", "아파트명", "거래", "면적", "평형", "층수", "향", "가격", "매물특징", "중개업소"]

        st.dataframe(df_show, use_container_width=True, hide_index=True)

        csv_bytes = df_show.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="📥 필터링된 매물 엑셀(CSV) 다운로드",
            data=csv_bytes,
            file_name=f"{region_title.replace(' ', '_')}_listings.csv",
            mime="text/csv",
        )
    else:
        st.warning("수집된 네이버 호가 매물이 없습니다. (네이버 일시 차단 시 국토부 실거래가 탭을 이용해 주세요.)")
