import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import json
import glob
import os
import re
import textwrap

try:
    import numpy_financial as npf
except ImportError:
    npf = None

st.set_page_config(
    page_title="STORM-Viewer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── THEME & CSS (Precision Architect) ─────────────────────────────────────────
st.markdown("""
<style>
    :root {
        --primary: #0c1c3e;
        --secondary: #00d4ff;
        --accent: #ff4b4b;
        --bg-color: #f8f9fa;
        --card-bg: #ffffff;
        --text-main: #2d3748;
        --text-light: #718096;
    }
    .stApp { background-color: var(--bg-color); color: var(--text-main); font-family: 'Inter', sans-serif; }
    h1, h2, h3 { color: var(--primary); font-weight: 800; letter-spacing: -0.5px; }
    .stMetric {
        background: var(--card-bg); border-left: 5px solid var(--secondary);
        padding: 15px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .stMetric [data-testid="stMetricLabel"] { color: var(--text-light); font-weight: 700; text-transform: uppercase; font-size: 0.8rem; }
    .stMetric [data-testid="stMetricValue"] { color: var(--primary); font-weight: 900; font-size: 1.8rem; }
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; border-bottom: 2px solid #e2e8f0; }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px; font-weight: 600; color: var(--text-light); border: none; transition: all 0.3s ease;
    }
    .stTabs [aria-selected="true"] { color: var(--primary); border-bottom: 3px solid var(--secondary); background: transparent; }
    div[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
    .logo-container { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #e2e8f0; }
    .logo-container img { max-height: 45px; object-fit: contain; }
</style>
""", unsafe_allow_html=True)

# ─── AUTHENTICATION ────────────────────────────────────────────────────────────
AUTH_FILE = "users.json"
def load_users():
    default_users = {"admin": "Coromoto_22"}
    if not os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "w") as f:
            json.dump(default_users, f)
        return default_users
    try:
        with open(AUTH_FILE, "r") as f:
            return json.load(f)
    except Exception:
        # If file is corrupted, return default admin to prevent crash
        return default_users


def save_users(users_dict):
    with open(AUTH_FILE, "w") as f:
        json.dump(users_dict, f)

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = None

if not st.session_state['authenticated']:
    st.markdown("<h2 style='text-align: center; color: var(--primary); margin-top: 50px;'>STORM-Viewer Pro</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Executive Decision Dashboard</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        with st.form("login_form"):
            st.markdown("#### Login")
            user = st.text_input("Username")
            pwd = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Access Application", use_container_width=True)
            
            if submitted:
                users = load_users()
                # Case-insensitive check
                user_match = next((k for k in users if k.lower() == user.lower()), None)
                if user_match and users[user_match] == pwd:
                    st.session_state['authenticated'] = True
                    st.session_state['username'] = user_match
                    st.rerun()
                else:
                    st.error("Invalid username or password")
    st.stop()

# ─── DATA LOADING ────────────────────────────────────────────────────────────
def _get_scenarios_cache_key():
    """Returns a string of file paths + modification timestamps to use as cache key."""
    scenarios_dir = "scenarios"
    if not os.path.exists(scenarios_dir):
        return ""
    files = sorted(glob.glob(os.path.join(scenarios_dir, "*.json")))
    return "|".join(f"{f}:{os.path.getmtime(f):.0f}" for f in files)

    # Moved down to authenticated block
    return []

# @st.cache_data
# def load_scenarios(cache_key: str):
#    ... (logic kept in function below)

# if not scenarios:
#    st.error(f"⚠️ No scenarios found. Please ensure JSON files are placed in the `./scenarios` directory.")
#    st.stop()

def ind_mean(sc, key):
    arr = sc['indicators'].get(key, [0.0])
    return float(np.mean(arr))

def _safe_mirr_annual(cf_monthly, finance_rate, reinvest_rate):
    """
    Calcula la TIRM mensual y la convierte a TIRM Anual Efectiva.
    Equivalente a la función TIRM() de Excel / npf.mirr().
    """
    try:
        cf = np.asarray(cf_monthly, dtype=float)
        has_neg = np.any(cf < 0)
        has_pos = np.any(cf > 0)
        if not (has_neg and has_pos):
            return None
        if npf is not None:
            r_monthly = npf.mirr(cf, finance_rate, reinvest_rate)
        else:
            n = len(cf) - 1
            pos = cf > 0
            neg = cf < 0
            pv_neg = np.sum(cf[neg] / ((1 + finance_rate) ** np.arange(len(cf))[neg]))
            fv_pos = np.sum(cf[pos] * ((1 + reinvest_rate) ** (n - np.arange(len(cf))[pos])))
            if pv_neg >= 0 or fv_pos <= 0:
                return None
            r_monthly = (-fv_pos / pv_neg) ** (1 / n) - 1
        if r_monthly is None or not np.isfinite(r_monthly) or r_monthly <= -1.0:
            return None
        return float(((1 + r_monthly) ** 12 - 1) * 100.0)
    except Exception:
        return None

def _simulate_investor_cf(cf_post_tax_mm, capital_inicial):
    """
    Simula el flujo de caja del inversionista y el balance del fondo del proyecto.
    El contratista aporta un capital_inicial en el mes 0 (outflow -capital_inicial).
    Mes a mes, los egresos y tributos se cubren del balance del fondo.
    Si el balance cae por debajo de 0, el inversionista inyecta el déficit.
    Si el balance supera el capital_inicial, se distribuye el excedente.
    Al finalizar el proyecto, el balance remanente se liquida al inversionista.
    """
    is_1d = False
    arr = np.asarray(cf_post_tax_mm, dtype=float)
    if arr.ndim == 1:
        is_1d = True
        arr = arr[np.newaxis, :]
    n_iters, n_periods = arr.shape
    B = np.full(n_iters, capital_inicial, dtype=float)
    cf_investor = np.zeros((n_iters, n_periods + 1))
    cf_investor[:, 0] = -capital_inicial
    cash_pool = np.zeros((n_iters, n_periods))
    
    for t in range(n_periods):
        cf_t = arr[:, t]
        b_potential = B + cf_t
        injections = np.where(b_potential < 0, -b_potential, 0.0)
        distributions = np.where(b_potential > capital_inicial, b_potential - capital_inicial, 0.0)
        cf_investor[:, t + 1] = distributions - injections
        B = b_potential + injections - distributions
        cash_pool[:, t] = B
        
    cf_investor[:, -1] += B
    if is_1d:
        return cf_investor[0], cash_pool[0]
    return cf_investor, cash_pool

def _get_autofin_cases(sc):
    """
    Extrae o computa los 3 casos de capital inicial para el análisis de caja autofinanciable.
    """
    if 'autofin_cases' in sc and sc['autofin_cases']:
        return sc['autofin_cases'], sc['params'].get('capital_inicial_casos', [])
        
    p = sc['params']
    cf = sc.get('cash_flows', {})
    dates = sc.get('dates', [])
    n_periods = len(dates)
    if n_periods == 0 or 'cf_post_tax' not in cf:
        return {}, []
        
    cap_cases = p.get('capital_inicial_casos', [])
    if not cap_cases:
        cap_base = float(p.get('capital_inicial', 40.0))
        cap_cases = [max(0.0, cap_base - 10.0), cap_base, cap_base + 10.0]
    cap_cases = [float(x) for x in cap_cases]
    
    cf_post = np.array(cf['cf_post_tax'], dtype=float)
    discount_rate = float(p.get('discount_rate', 15.0)) / 100.0
    monthly_r = (1 + discount_rate) ** (1 / 12) - 1
    finance_rate_m = monthly_r
    reinvest_rate_m = monthly_r
    
    cases_dict = {}
    for idx, cap in enumerate(cap_cases):
        case_name = f"caso_{idx+1}"
        cf_inv, pool = _simulate_investor_cf(cf_post, cap)
        
        if cf_inv.ndim == 1:
            cum_inv = np.cumsum(cf_inv)
            mco = float(np.abs(min(0.0, np.min(cum_inv))))
            min_pool = int(np.argmin(pool))
            pos_idx = np.where(cum_inv[1:] >= 0)[0]
            payback = float(pos_idx[0] + 1) if len(pos_idx) > 0 else float(n_periods)
            tirm_val = _safe_mirr_annual(cf_inv, finance_rate_m, reinvest_rate_m)
            pos_sum = np.sum(cf_inv[cf_inv > 0])
            neg_sum = np.sum(-cf_inv[cf_inv < 0])
            moic = float(pos_sum / neg_sum) if neg_sum > 0 else 0.0
            disc = (1 + monthly_r) ** np.arange(n_periods + 1)
            npv_val = float(np.sum(cf_inv / disc))
            
            cases_dict[case_name] = {
                'capital': cap,
                'cf_investor_post_tax': cf_inv[np.newaxis, :],
                'cum_cf_investor_post_tax': cum_inv[np.newaxis, :],
                'cash_pool_autofin': pool[np.newaxis, :],
                'mco_autofin': [mco],
                'min_pool_months': [min_pool],
                'payback_months_autofin': [payback],
                'tirm_investor': tirm_val,
                'moic_investor': [moic],
                'npv_investor': [npv_val]
            }
        else:
            cum_inv = np.cumsum(cf_inv, axis=1)
            mco = np.abs(np.minimum(cum_inv, 0).min(axis=1))
            min_pool = np.argmin(pool, axis=1)
            payback = np.full(cf_inv.shape[0], n_periods, dtype=float)
            for i in range(cf_inv.shape[0]):
                pos_idx = np.where(cum_inv[i, 1:] >= 0)[0]
                if len(pos_idx) > 0:
                    payback[i] = pos_idx[0] + 1
            mean_cf = np.mean(cf_inv, axis=0)
            tirm_val = _safe_mirr_annual(mean_cf, finance_rate_m, reinvest_rate_m)
            pos_sum = np.sum(np.where(cf_inv > 0, cf_inv, 0), axis=1)
            neg_sum = np.sum(np.where(cf_inv < 0, -cf_inv, 0), axis=1)
            moic = np.where(neg_sum > 0, pos_sum / neg_sum, 0.0)
            disc = ((1 + monthly_r) ** np.arange(n_periods + 1))[np.newaxis, :]
            npv_val = np.sum(cf_inv / disc, axis=1)
            
            cases_dict[case_name] = {
                'capital': cap,
                'cf_investor_post_tax': cf_inv,
                'cum_cf_investor_post_tax': cum_inv,
                'cash_pool_autofin': pool,
                'mco_autofin': mco,
                'min_pool_months': min_pool,
                'payback_months_autofin': payback,
                'tirm_investor': tirm_val,
                'moic_investor': moic,
                'npv_investor': npv_val
            }
    return cases_dict, cap_cases

def _ensure_sens_pre_tax(df_s, sc):
    """
    Asegura que el dataframe de sensibilidad cuente con la columna 'VPN HPOC Pre (MMUSD)'.
    Si no está pre-calculada en el archivo, se computa analíticamente con alta precisión.
    """
    if 'VPN HPOC Pre (MMUSD)' in df_s.columns and df_s['VPN HPOC Pre (MMUSD)'].notnull().all():
        return df_s
    p = sc['params']
    cf = sc.get('cash_flows', {})
    dates = sc.get('dates', [])
    dr = float(p.get('discount_rate', 15.0)) / 100.0
    mr = (1 + dr) ** (1 / 12) - 1
    dm = (1 + mr) ** np.arange(len(dates))
    
    base_price = float(p.get('oil_price', 60.0))
    int_tax_rate = float(p.get('integrated_tax_rate', p.get('int_tax_rate', 9.0))) / 100.0
    
    costs_pv = float(np.sum((np.array(cf.get('capex', [0])) + np.array(cf.get('opex', [0])) + np.array(cf.get('abex', [0]))) / dm))
    gi_base_pv = float(np.sum(np.array(cf.get('gross_income', [0])) / dm))
    
    pre_vals = []
    r_cols = [c for c in df_s.columns if 'Regal' in c or 'Royalty' in c]
    r_col = r_cols[0] if r_cols else None
    
    for _, row in df_s.iterrows():
        if 'VPN HPOC Pre (MMUSD)' in row and pd.notnull(row['VPN HPOC Pre (MMUSD)']):
            pre_vals.append(float(row['VPN HPOC Pre (MMUSD)']))
        else:
            price = float(row['Precio Aceite']) if 'Precio Aceite' in row else float(row.get('Oil Price', base_price))
            r_rate = float(row[r_col]) / 100.0 if r_col else 0.3
            scaled_gi_pv = gi_base_pv * (price / base_price) if base_price > 0 else gi_base_pv
            v_roy = r_rate * scaled_gi_pv
            v_iih = int_tax_rate * scaled_gi_pv
            pre_vals.append(scaled_gi_pv - v_roy - v_iih - costs_pv)
    df_s['VPN HPOC Pre (MMUSD)'] = pre_vals
    return df_s


def find_logo(pattern):
    for ext in ["png", "jpg", "jpeg", "PNG", "JPG"]:
        exact = f"assets/{pattern}.{ext}"
        if os.path.exists(exact):
            return exact
    for ext in ["png", "jpg", "jpeg", "PNG", "JPG"]:
        matches = glob.glob(f"assets/{pattern}*.{ext}")
        if matches:
            return matches[0]
    return None

# ─── SIDEBAR LAYOUT ────────────────────────────────────────────────────────────
c1, c2 = st.sidebar.columns(2)
with c1:
    logo1 = find_logo("mi_logo") or find_logo("mi") or find_logo("company") or find_logo("logo_empresa")
    if logo1:
        st.image(logo1)
    else:
        st.markdown("### Client")

with c2:
    logo2 = find_logo("logo_app") or find_logo("storm") or find_logo("app")
    if logo2:
        st.image(logo2)
    else:
        st.markdown("### STORM")

st.sidebar.markdown("<hr style='border:none; border-top:1px solid #e2e8f0; margin:10px 0;'>", unsafe_allow_html=True)

# ── Navigation: Analysis Premises ──
st.sidebar.markdown("<h3 style='color: #718096; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px;'>PROJECT</h3>", unsafe_allow_html=True)

# ─── DATA LOADING (INSIDE AUTHENTICATED BLOCK) ──────────────────────────────
def _compress_scenario_data(data):
    """Compress 2D Monte Carlo matrices to 1D vectors and scalar totals to optimize RAM usage."""
    cf = data.get('cash_flows', {})
    cf_opt = {}
    for k, v in cf.items():
        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], list):
            arr = np.array(v, dtype=np.float64)
            cf_opt[k] = np.round(arr.mean(axis=0), 4).tolist()
            cf_opt[k + '_nom_total'] = float(np.round(arr.sum(axis=1).mean(), 4))
        else:
            cf_opt[k] = v
    data['cash_flows'] = cf_opt

    prod = data.get('production', {})
    prod_opt = {}
    for k in ['Qo', 'NP', 'Qg', 'GP']:
        if k in prod and isinstance(prod[k], list) and len(prod[k]) > 0 and isinstance(prod[k][0], list):
            arr = np.array(prod[k], dtype=np.float64)
            p10, p50, p90 = np.percentile(arr, [10, 50, 90], axis=0)
            prod_opt[k + '_p10'] = np.round(p10, 4).tolist()
            prod_opt[k + '_p50'] = np.round(p50, 4).tolist()
            prod_opt[k + '_p90'] = np.round(p90, 4).tolist()
    for k, v in prod.items():
        if k not in ['Qo', 'NP', 'Qg', 'GP']:
            prod_opt[k] = v
    data['production'] = prod_opt

    return data

@st.cache_data
def load_scenarios(cache_key: str):
    """Load all scenario JSON files and compress 2D matrices to fit within Streamlit Cloud memory limits."""
    scenarios_dir = "scenarios"
    if not os.path.exists(scenarios_dir):
        return [], []
    
    files = sorted(glob.glob(os.path.join(scenarios_dir, "*.json")))
    PALETTE = ["#FF4B4B", "#00D4FF", "#0C1C3E", "#28A745", "#E91E63", "#9C27B0"]
    loaded = []
    errors = []
    
    for idx, filepath in enumerate(files):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data = _compress_scenario_data(data)
                data['_color'] = PALETTE[idx % len(PALETTE)]
                data['_filename'] = os.path.basename(filepath)
                loaded.append(data)
        except Exception as e:
            errors.append(f"Error loading {os.path.basename(filepath)}: {e}")
            
    loaded.sort(key=lambda x: x['_filename'])
    return loaded, errors

scenarios, load_errors = load_scenarios(_get_scenarios_cache_key())

for err in load_errors:
    st.sidebar.error(err)

if not scenarios:
    st.error(f"⚠️ No scenarios found. Please ensure JSON files are placed in the `./scenarios` directory.")
    st.info("Required structure:\n- `scenarios/Case_Base.json`\n- `scenarios/Sc._1.json`\n- `scenarios/Sc._2.json`\n- `scenarios/Sc._3.json`")
    st.stop()

scenario_names = [s['params'].get('esc_name', s['_filename']) for s in scenarios]
NAV_PREMISES = "📋 Analysis Premises"

# Init navigation and scenario session state
if 'nav_page' not in st.session_state:
    st.session_state['nav_page'] = NAV_PREMISES
if '_sel_scenario' not in st.session_state:
    st.session_state['_sel_scenario'] = None

# Analysis Premises button
if st.sidebar.button(NAV_PREMISES, use_container_width=True,
                     type="primary" if st.session_state['nav_page'] == NAV_PREMISES else "secondary"):
    st.session_state['nav_page'] = NAV_PREMISES
    st.session_state['_sel_scenario'] = None
    st.rerun()

st.sidebar.markdown("<hr style='border:none; border-top:1px solid #e2e8f0; margin:10px 0;'>", unsafe_allow_html=True)
st.sidebar.markdown("<h3 style='color: #718096; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;'>SCENARIO</h3>", unsafe_allow_html=True)

# on_change callback: called ONLY when user clicks a different scenario
def _on_scenario_change():
    if st.session_state.get('_sel_scenario'):
        st.session_state['nav_page'] = st.session_state['_sel_scenario']

# Scenario radio — backed by session state key, index=None when on Analysis Premises
sel_esc_name = st.sidebar.radio(
    "Select Scenario", scenario_names,
    index=None,
    key='_sel_scenario',
    on_change=_on_scenario_change,
    label_visibility="collapsed"
)

# Reference scenario for styling/colors
if sel_esc_name:
    sel_sc = next((s for s in scenarios if s['params'].get('esc_name', s['_filename']) == sel_esc_name), scenarios[0])
else:
    sel_sc = scenarios[0]

sel_color = sel_sc.get('_color', '#00d4ff')

if st.session_state['nav_page'] != NAV_PREMISES and sel_esc_name:
    # Scenario Image
    search_names = [
        sel_esc_name, 
        sel_esc_name.replace("Sc.", "Scenario").strip(),
        sel_esc_name.replace("Sce.", "Scenario").strip()
    ]
    if sel_esc_name == "Case Base":
        search_names.append("Base Case")

    scen_img = None
    for name in search_names:
        scen_img = find_logo(name)
        if scen_img:
            break

    if scen_img:
        st.sidebar.image(scen_img)
    else:
        st.sidebar.warning(f"⚠️ Image not found. Save it as: `assets/{sel_esc_name}.png`")
    scen_desc = sel_sc['params'].get('esc_desc', f'Approved development plan considering all activities for {sel_esc_name}.')
    st.sidebar.info(f"**{sel_esc_name}:** {scen_desc}")

st.sidebar.markdown("<hr style='border:none; border-top:1px solid #e2e8f0; margin:10px 0;'>", unsafe_allow_html=True)
username_display = st.session_state['username'].capitalize() if st.session_state['username'] else 'User'
st.sidebar.markdown(f"👤 **{username_display}**")

if st.session_state['username'] == 'admin':
    with st.sidebar.expander("⚙️ Manage Users"):
        with st.form("new_user_form"):
            new_u = st.text_input("New Username")
            new_p = st.text_input("New Password", type="password")
            if st.form_submit_button("Create User"):
                users = load_users()
                if new_u.lower() in [u.lower() for u in users]:
                    st.error("User already exists.")
                else:
                    users[new_u] = new_p
                    save_users(users)
                    st.success(f"User '{new_u}' created!")

if st.sidebar.button("🔒 Logout", use_container_width=True):
    st.session_state['authenticated'] = False
    st.session_state['username'] = None
    st.rerun()

# ── Refresh / Clear Cache at bottom ──
st.sidebar.markdown("<hr style='border:none; border-top:1px solid #e2e8f0; margin:10px 0;'>", unsafe_allow_html=True)
if st.sidebar.button("🔄 Refresh / Clear Cache", use_container_width=True):
    st.cache_data.clear()
    st.rerun()


# ─── PAGE: ANALYSIS PREMISES ─────────────────────────────────────────────────
if st.session_state.get('nav_page') == NAV_PREMISES:
    # Use Case Base (or first scenario) as the reference for premises
    ref_sc = next((s for s in scenarios if 'Case' in s['params'].get('esc_name', '')), scenarios[0])
    p = ref_sc['params']
    dates_list = ref_sc.get('dates', [])
    date_start = dates_list[0][:10]  if dates_list else '—'
    date_end   = dates_list[-1][:10] if dates_list else '—'

    def safe_fmt(val, is_currency=False, precision=1):
        try:
            v = float(val)
            if np.isnan(v):
                return "—"
            if is_currency:
                return f"${v:.{precision}f}"
            return f"{v:.{precision}f}"
        except (ValueError, TypeError):
            return "—"

    proj_name      = p.get('proj_name', '—')
    oil_price      = safe_fmt(p.get('oil_price'), True, 2)
    gas_price      = safe_fmt(p.get('gas_price'), True, 2)
    discount_rate  = safe_fmt(p.get('discount_rate'), False, 1)
    royalty_rate   = safe_fmt(p.get('royalty_rate', p.get('royalties')), False, 1)
    int_tax_rate   = safe_fmt(p.get('integrated_tax_rate', p.get('int_tax_rate')), False, 2)
    islr_rate      = safe_fmt(p.get('islr_rate'), False, 1)
    rec_capex      = safe_fmt(p.get('recovery_capex_rate'), False, 1)
    rec_opex       = safe_fmt(p.get('recovery_opex_rate'), False, 1)
    
    avail_type     = p.get('availability_type', 'constant')
    
    def get_avail(key):
        val = p.get(key)
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
            
    avail_val = get_avail('availability_val') or 1.0
    avail_min = get_avail('availability_min') or 1.0
    avail_mode = get_avail('availability_mode') or 1.0
    avail_max = get_avail('availability_max') or 1.0

    if avail_type == 'constant':
        avail_str = f"{avail_val*100:.1f}% (Constant)"
    else:
        avail_str = f"BetaPERT — Min: {avail_min*100:.1f}% / Mode: {avail_mode*100:.1f}% / Max: {avail_max*100:.1f}%"

    st.markdown("""
    <style>
    .prem-section-title {
        font-size: 0.72rem; font-weight: 800; text-transform: uppercase;
        letter-spacing: 1.5px; color: #718096; margin-bottom: 10px;
    }
    .prem-card {
        background: white;
        border-left: 5px solid #00d4ff;
        padding: 18px 20px;
        border-radius: 10px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        margin-bottom: 16px;
    }
    .prem-card-accent {
        border-left-color: #0c1c3e;
    }
    .prem-field-label {
        font-size: 0.72rem; font-weight: 700; color: #a0aec0;
        text-transform: uppercase; letter-spacing: 0.8px;
        margin-bottom: 2px;
    }
    .prem-field-value {
        font-size: 1.05rem; font-weight: 800; color: #0c1c3e;
        line-height: 1.3;
    }
    .prem-subgroup {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 14px 16px;
        margin-top: 10px;
    }
    .prem-subgroup-title {
        font-size: 0.68rem; font-weight: 800; color: #0c1c3e;
        text-transform: uppercase; letter-spacing: 1.2px;
        border-bottom: 2px solid #00d4ff;
        padding-bottom: 6px;
        margin-bottom: 10px;
    }
    .prem-grid { display: flex; gap: 24px; flex-wrap: wrap; }
    .prem-grid-item { flex: 1; min-width: 120px; }
    </style>
    """, unsafe_allow_html=True)

    # ── Header ──
    st.markdown(f"""
    <div style="margin-bottom: 4px;">
        <h1 style="color: #0c1c3e; font-size: 2rem; font-weight: 900; margin-bottom: 4px;">
            {proj_name} — Analysis Premises
        </h1>
        <p style="color: #718096; font-size: 0.95rem;">
            Economic and fiscal parameters used as inputs for all evaluated scenarios.
        </p>
    </div>
    <hr style="border: none; border-top: 2px solid #e2e8f0; margin: 12px 0 24px 0;">
    """, unsafe_allow_html=True)

    col_main, col_img = st.columns([3, 1])

    with col_main:
        # ── Card 1: Field Name ──
        st.markdown(f"""
        <div class="prem-card">
            <div class="prem-field-label">Field Name / Project</div>
            <div class="prem-field-value" style="font-size: 1.5rem;">{proj_name}</div>
        </div>
        """, unsafe_allow_html=True)

        # ── Card 2: Project Horizon ──
        st.markdown(f"""
        <div class="prem-card">
            <div class="prem-section-title">Project Horizon</div>
            <div class="prem-grid">
                <div class="prem-grid-item">
                    <div class="prem-field-label">Analysis Start Date</div>
                    <div class="prem-field-value">{date_start}</div>
                </div>
                <div class="prem-grid-item">
                    <div class="prem-field-label">Analysis End Date</div>
                    <div class="prem-field-value">{date_end}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Card 3: Economic Parameters — split into sub-blocks for reliable rendering ──
        # Header card open
        st.markdown('<div class="prem-card prem-card-accent"><div class="prem-section-title">Economic Parameters</div>', unsafe_allow_html=True)

        # Sub-block: Prices
        st.markdown('<div class="prem-subgroup"><div class="prem-subgroup-title">Prices</div></div>', unsafe_allow_html=True)
        ec1, ec2, ec3 = st.columns(3)
        with ec1:
            st.markdown(f'<div class="prem-field-label">Oil Price</div><div class="prem-field-value">{oil_price} <span style="font-size:0.75rem;font-weight:500;color:#718096;">USD/bbl</span></div>', unsafe_allow_html=True)
        with ec2:
            st.markdown(f'<div class="prem-field-label">Gas Price</div><div class="prem-field-value">{gas_price} <span style="font-size:0.75rem;font-weight:500;color:#718096;">USD/mcf</span></div>', unsafe_allow_html=True)
        with ec3:
            st.markdown(f'<div class="prem-field-label">Discount Rate</div><div class="prem-field-value">{discount_rate}<span style="font-size:0.75rem;font-weight:500;color:#718096;"> %</span></div>', unsafe_allow_html=True)

        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

        # Sub-block: Taxes & Royalties
        st.markdown('<div class="prem-subgroup"><div class="prem-subgroup-title">Taxes &amp; Royalties</div></div>', unsafe_allow_html=True)
        et1, et2, et3 = st.columns(3)
        with et1:
            st.markdown(f'<div class="prem-field-label">Royalties</div><div class="prem-field-value">{royalty_rate}<span style="font-size:0.75rem;font-weight:500;color:#718096;"> %</span></div>', unsafe_allow_html=True)
        with et2:
            st.markdown(f'<div class="prem-field-label">Integrated Tax</div><div class="prem-field-value">{int_tax_rate}<span style="font-size:0.75rem;font-weight:500;color:#718096;"> %</span></div>', unsafe_allow_html=True)
        with et3:
            st.markdown(f'<div class="prem-field-label">Income Tax (ISLR)</div><div class="prem-field-value">{islr_rate}<span style="font-size:0.75rem;font-weight:500;color:#718096;"> %</span></div>', unsafe_allow_html=True)

        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

        # Sub-block: Cost Recovery
        st.markdown('<div class="prem-subgroup"><div class="prem-subgroup-title">Cost Recovery</div></div>', unsafe_allow_html=True)
        er1, er2, er3 = st.columns(3)
        with er1:
            st.markdown(f'<div class="prem-field-label">CAPEX Recovery</div><div class="prem-field-value">{rec_capex}<span style="font-size:0.75rem;font-weight:500;color:#718096;"> %</span></div>', unsafe_allow_html=True)
        with er2:
            st.markdown(f'<div class="prem-field-label">OPEX Recovery</div><div class="prem-field-value">{rec_opex}<span style="font-size:0.75rem;font-weight:500;color:#718096;"> %</span></div>', unsafe_allow_html=True)

        # Close outer card div
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

        # ── Card 4: System Availability ──
        st.markdown(f'<div class="prem-card"><div class="prem-section-title">System Availability</div><div class="prem-field-value">{avail_str}</div></div>', unsafe_allow_html=True)

    with col_img:
        proj_img = find_logo("Project")
        if proj_img:
            st.markdown(
                "<div style='padding-top: 0px;'></div>",
                unsafe_allow_html=True
            )
            st.image(proj_img, caption="Project Reference")
        else:
            st.info("Place `assets/Project.png` as project reference image.")

    st.stop()

# Ensure scenario variables are defined past premises page
if not sel_esc_name:
    sel_esc_name = scenario_names[0]
    sel_sc = next((s for s in scenarios if s['params'].get('esc_name', s['_filename']) == sel_esc_name), scenarios[0])
    sel_color = sel_sc['_color']

if st.session_state.get('nav_page') != sel_esc_name and st.session_state.get('nav_page') != NAV_PREMISES:
    st.session_state['nav_page'] = sel_esc_name


# ─── PLOTTING HELPERS ────────────────────────────────────────────────────────
def hist_plot(data_array, title, color, nom_val=None, nbins=28):
    d_clean = np.array(data_array, dtype=float)
    d_clean = d_clean[~np.isnan(d_clean) & ~np.isinf(d_clean)]
    if len(d_clean) == 0: return go.Figure()
    
    p10, p50, p90 = np.percentile(d_clean, [10, 50, 90])
    mean_val = np.mean(d_clean)

    counts, edges = np.histogram(d_clean, bins=nbins)
    centers = (edges[:-1] + edges[1:]) / 2
    widths  = (edges[1:] - edges[:-1]) * 0.92

    max_dist = max(np.abs(centers - p50).max(), 1e-9)
    opacities = 0.22 + 0.78 * (1.0 - np.abs(centers - p50) / max_dist)

    fig = go.Figure()
    for i in range(len(counts)):
        fig.add_trace(go.Bar(
            x=[centers[i]], y=[counts[i]], width=[widths[i]],
            marker=dict(color=color, opacity=float(opacities[i]), line=dict(color='white', width=1)),
            showlegend=False,
            hovertemplate=f"{edges[i]:.1f} – {edges[i+1]:.1f} MM USD<br>Frequency: {counts[i]}<extra></extra>"
        ))

    for val, lbl in [(p90, 'P90'), (p50, 'P50'), (p10, 'P10')]:
        fig.add_vline(x=val, line=dict(color='#222222', dash='dash', width=1.4),
                      annotation=dict(text=f"<b>| {lbl}</b>:{val:.1f}", font=dict(size=9, color='#222222'), yref='paper', y=1.02, showarrow=False))

    left_text  = f"<b>Mean (NPV):</b> {mean_val:.2f}"
    if nom_val is not None: left_text += f"<br><span style='color:#888'>Nominal Mean:</span> {nom_val:.2f}"
    right_text = f"P90: {p90:.2f}&nbsp;&nbsp;&nbsp;&nbsp;P10: {p10:.2f}"
    for txt, ax, anchor in [(left_text, 0, 'left'), (right_text, 1, 'right')]:
        fig.add_annotation(x=ax, y=-0.22, xref='paper', yref='paper', text=txt, showarrow=False, font=dict(size=9, color='#555555'), align=anchor, xanchor=anchor)

    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color='#1a1a2e'), x=0, xanchor='left', y=0.97),
        xaxis=dict(title=dict(text='MM USD', font=dict(size=11, color='#555')), showgrid=False, zeroline=False, showline=True, linecolor='#d0d0d0', linewidth=1),
        yaxis=dict(title=dict(text='Frequency', font=dict(size=11, color='#555')), showgrid=True, gridcolor='#f0f0f0', gridwidth=1, zeroline=False),
        bargap=0.0, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=55, b=80, l=55, r=25), showlegend=False, hovermode='x'
    )
    return fig

def get_cf_monthly(cf_dict, key):
    """Retrieve 1D monthly mean array for cash flow key."""
    val = cf_dict.get(key, [])
    if not len(val):
        return np.array([])
    arr = np.array(val, dtype=float)
    if arr.ndim == 2:
        return np.mean(arr, axis=0)
    return arr

def get_p10_p50_p90(prod_dict, key):
    """Retrieve P10, P50, P90 vectors for production forecast plots."""
    if key + '_p10' in prod_dict:
        return (
            np.array(prod_dict[key + '_p10']),
            np.array(prod_dict[key + '_p50']),
            np.array(prod_dict[key + '_p90'])
        )
    raw = prod_dict.get(key, [])
    if len(raw) > 0 and isinstance(raw[0], list):
        return np.percentile(raw, [10, 50, 90], axis=0)
    arr = np.array(raw) if len(raw) > 0 else np.zeros(1)
    return arr, arr, arr

def reserves_bar(res_dict, title, color_1p, color_2p, color_3p, y_label):
    order = ['1P', '2P', '3P']
    labels = [k for k in order if k in res_dict]
    values = [float(res_dict[k]) for k in labels]
    colors = [color_1p, color_2p, color_3p]
    fig = go.Figure()
    for i, (lbl, val) in enumerate(zip(labels, values)):
        fig.add_trace(go.Bar(
            x=[lbl], y=[val], name=lbl,
            marker_color=colors[i % len(colors)],
            text=[f"{val:.1f}"], textposition='outside',
            width=0.45
        ))
    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(family='Inter, sans-serif', size=17, color='#1a1c1e'),
            x=0, y=0.98, xanchor='left'
        ),
        yaxis_title=y_label,
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=50, b=40, l=45, r=20),
        yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.06)', rangemode='tozero'),
        xaxis=dict(tickfont=dict(family='Inter, sans-serif', size=12)),
        font=dict(family='Inter, sans-serif')
    )
    return fig

def plot_dual(dates, rate_data, cum_data, res_dict, title, y1_lbl, y2_lbl, color):
    if isinstance(rate_data, tuple):
        r10, r50, r90 = rate_data
    else:
        rate_arr = np.asarray(rate_data)
        if rate_arr.ndim == 1:
            r10 = r50 = r90 = rate_arr
        else:
            r10, r50, r90 = np.percentile(rate_arr, [10, 50, 90], axis=0)
        
    if isinstance(cum_data, tuple):
        c10, c50, c90 = cum_data
    else:
        cum_arr = np.asarray(cum_data)
        if cum_arr.ndim == 1:
            c10 = c50 = c90 = cum_arr
        else:
            c10, c50, c90 = np.percentile(cum_arr, [10, 50, 90], axis=0)
        
    fig = go.Figure()
    
    # 1. Reserves reference lines (3P, 2P, 1P)
    dash_colors = {'1P': '#1a1a2e', '2P': '#4a4e69', '3P': '#7a7a8c'}
    for nm in ['3P', '2P', '1P']:
        if nm in res_dict:
            val = float(res_dict[nm])
            fig.add_trace(go.Scatter(
                x=dates, y=[val]*len(dates), name=nm, yaxis='y2',
                line=dict(color=dash_colors.get(nm, '#4a4e69'), width=1.5, dash='dashdot')
            ))
            
    # 2. Cumulative curves
    fig.add_trace(go.Scatter(x=dates, y=c90, name='Cum P90', yaxis='y2', line=dict(color=color, width=1, dash='dot'), opacity=0.6))
    fig.add_trace(go.Scatter(x=dates, y=c50, name='Cum P50', yaxis='y2', line=dict(color=color, width=2.5, dash='dot')))
    fig.add_trace(go.Scatter(x=dates, y=c10, name='Cum P10', yaxis='y2', line=dict(color=color, width=1, dash='dot'), opacity=0.6))

    # 3. Production Rate curves & band
    fig.add_trace(go.Scatter(x=dates, y=r50, name='Q P50', line=dict(color=color, width=2.5)))
    fig.add_trace(go.Scatter(x=dates, y=r90, name='Q P90', line=dict(color=color, width=1), opacity=0.35))
    fig.add_trace(go.Scatter(x=dates, y=r10, name='Q P10', line=dict(color=color, width=1),
                             fill='tonexty', fillcolor='rgba(0,128,0,0.15)' if 'green' in color else 'rgba(214,39,40,0.15)', opacity=0.35))

    layout_dict = dict(
        xaxis_title='Fecha',
        yaxis=dict(title=y1_lbl, showgrid=True, gridcolor='rgba(0,0,0,0.05)', rangemode='tozero'),
        yaxis2=dict(title=y2_lbl, overlaying='y', side='right', showgrid=False, rangemode='tozero'),
        legend=dict(orientation='h', yanchor='top', y=-0.2, xanchor='center', x=0.5, font=dict(family='Inter, sans-serif', size=10)),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=40 if not title else 80, l=50, r=50, b=100),
        hovermode='x unified',
        font=dict(family='Inter, sans-serif')
    )
    if title:
        layout_dict['title'] = dict(text=f"<b>{title}</b>", font=dict(size=18, color=color), y=0.98, x=0, xanchor='left')
    fig.update_layout(**layout_dict)
    return fig


# ─── MAIN DASHBOARD ──────────────────────────────────────────────────────────
st.title("Executive Financial Dashboard")
st.markdown("Comparative analysis of pre-calculated economic scenarios.")
st.markdown("---")

# ─── SECTION 1: DETAIL CARD ──────────────────────────────────────────────────
m_cols = st.columns(6)
metrics = [
    ("NPV Post-Tax", f"{ind_mean(sel_sc, 'npv_hpoc_post'):.1f} MMUSD"),
    ("IRR Post-Tax", f"{float(sel_sc['indicators'].get('irr_post_annual', 0.0)):.2f}%"),
    ("MOIC", f"{ind_mean(sel_sc, 'moic'):.2f}x"),
    ("Gov. Take", f"{ind_mean(sel_sc, 'npv_gov_take'):.1f}%"),
    ("Peak Inv. (MCE)", f"{ind_mean(sel_sc, 'mce_mm'):.1f} MMUSD"),
    ("Payout Time", f"{ind_mean(sel_sc, 'payout_years'):.1f} Yrs"),
]
for col, (label, val) in zip(m_cols, metrics):
    col.metric(label, val)

p_sel = sel_sc['params']
ind_sel = sel_sc['indicators']
if p_sel.get('aplica_autofin', False):
    st.markdown("##### 📦 Métricas del Inversionista (Caja Autofinanciable - Caso 2 Base)")
    card_cols_inv = st.columns(6)
    tirm_inv_val = ind_sel.get('tirm_investor')
    tirm_inv_str = f"{float(tirm_inv_val):.2f}%" if (tirm_inv_val is not None and np.isfinite(tirm_inv_val)) else "N/A"
    payback_inv_val = ind_mean(sel_sc, 'payback_months_autofin')
    payback_inv_str = f"Mes {int(round(payback_inv_val))}" if payback_inv_val < len(sel_sc.get('dates', [])) else "N/A"
    metrics_inv = [
        ("Capital Inicial (C₀)", f"{float(p_sel.get('capital_inicial', 40.0)):.1f} MMUSD"),
        ("Exposición / MCO",     f"{ind_mean(sel_sc, 'mco_autofin'):.2f} MMUSD"),
        ("TIRM Inversionista",   tirm_inv_str),
        ("MOIC Inversionista",   f"{ind_mean(sel_sc, 'moic_investor'):.2f}x"),
        ("VPN Inversionista",    f"{ind_mean(sel_sc, 'npv_investor'):.2f} MMUSD"),
        ("Mes Autofinanc.",      payback_inv_str),
    ]
    for col, (label, val) in zip(card_cols_inv, metrics_inv):
        col.metric(label, val)

# ─── SECTION 2: TABS ─────────────────────────────────────────────────────────
st.markdown(f"### 🔍 Detailed Inspection: {sel_esc_name}")
t_bubble, t_det1, t_det2, t_det3, t_det4, t_det5, t_sens, t_gt, t_sens_fiscal, t_autofin = st.tabs([
    "📊 KPI Comparativo",
    "🏗️ Cascada Fiscal",
    "🛢️ Pronósticos",
    "💸 Egresos",
    "📈 Distribuciones NPV",
    "💼 Flujo de Caja",
    "📊 Indicadores & Sensibilidad",
    "⚖️ Equilibrio Fiscal / GT",
    "🔬 Análisis de Sensibilidad Fiscal",
    "📦 Caja Autofinanciable & Exposición"
])


# Helpers for aggregations
dates = sel_sc.get('dates', [])
cf = sel_sc.get('cash_flows', {})
ind_det = sel_sc.get('indicators', {})

def nom_total(sc, key):
    cf_map = sc.get('cash_flows', {})
    if key + '_nom_total' in cf_map:
        return float(cf_map[key + '_nom_total'])
    val = cf_map.get(key, [[0.0]])
    arr = np.array(val, dtype=float)
    if arr.ndim == 2:
        return float(np.mean(np.sum(arr, axis=1)))
    elif arr.ndim == 1:
        return float(np.sum(arr))
    return float(val)

def safe_agg(arr):
    return {'Mean': np.mean(arr), 'Std Dev': np.std(arr),
            'Min': np.min(arr), 'P10': np.percentile(arr,10),
            'P50': np.percentile(arr,50), 'P90': np.percentile(arr,90),
            'Max': np.max(arr)}

with t_bubble:
    st.subheader("KPI Comparative Analysis (Bubble Chart)")
    c1, c2 = st.columns(2)
    y_axis_opt = c1.selectbox("Y-Axis Indicator (KPI)", 
        ["NPV Contractor Post-Tax (MMUSD)", "NPV Contractor Pre-Tax (MMUSD)", "IRR Post-Tax (%)", "MOIC (Multiple)"])
    bubble_size_opt = c2.selectbox("Bubble Size", 
        ["Np P50 (MMbbls)", "Np P10 (MMbbls)", "Np P90 (MMbbls)"])

    y_key_map = {
        "NPV Contractor Post-Tax (MMUSD)": ("npv_hpoc_post", False),
        "NPV Contractor Pre-Tax (MMUSD)":  ("npv_hpoc_pre",  False),
        "IRR Post-Tax (%)":                ("irr_post_annual", True),
        "MOIC (Multiple)":                 ("moic", False),
    }
    size_key_map = {"Np P50 (MMbbls)": "np_p50", "Np P10 (MMbbls)": "np_p10", "Np P90 (MMbbls)": "np_p90"}

    bubble_fig = go.Figure()
    for sc in scenarios:
        p = sc['params']
        y_key, is_scalar = y_key_map[y_axis_opt]
        y_val = float(sc['indicators'].get(y_key, 0.0)) if is_scalar else ind_mean(sc, y_key)
        np_val = sc.get('production', {}).get(size_key_map[bubble_size_opt], 1.0)

        n_interventions = (
            p.get('n_terminaciones', 0) + 
            p.get('n_rma', 0) + 
            p.get('n_cambio_zona', 0) + 
            p.get('n_limpieza', 0) + 
            p.get('n_reactivacion', 0)
        )
        bubble_fig.add_trace(go.Scatter(
            x=[n_interventions], y=[y_val], mode='markers+text',
            name=p.get('esc_name', sc['_filename']),
            marker=dict(size=max(np_val * 3, 18), color=sc['_color'], opacity=0.82, line=dict(color='white', width=2)),
            text=[p.get('esc_name', sc['_filename'])], textposition='top center',
            customdata=[[p.get('esc_name', sc['_filename']), p.get('esc_desc', ''), np_val, ind_mean(sc, 'npv_gov_take')]],
            hovertemplate="<b>%{customdata[0]}</b><br>Interventions: %{x}<br>"+y_axis_opt+": %{y:.2f}<br>Np: %{customdata[2]:.2f} MMbbls<br>Gov. Take: %{customdata[3]:.1f}%<extra></extra>"
        ))
    bubble_fig.update_layout(xaxis_title="Number of Interventions", yaxis_title=y_axis_opt, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(248,249,250,0.8)')
    st.plotly_chart(bubble_fig, use_container_width=True)

    if len(scenarios) > 1:
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("📊 Tabla Comparativa de Escenarios")
        rows = []
        for sc in scenarios:
            rows.append({
                "Escenario": sc['params'].get('esc_name', sc['_filename']),
                "VPN Post-Tax (MMUSD)": round(ind_mean(sc, 'npv_hpoc_post'), 2),
                "TIR / TIRM (%)": round(float(sc['indicators'].get('irr_post_annual', 0.0)), 2),
                "MOIC (x)": round(ind_mean(sc, 'moic'), 2),
                "Pico Inv. MCE (MMUSD)": round(ind_mean(sc, 'mce_mm'), 2),
                "Gov. Take (%)": round(ind_mean(sc, 'npv_gov_take'), 2),
            })
        st.dataframe(pd.DataFrame(rows).set_index("Escenario"), use_container_width=True)

with t_det1:
    st.subheader("Fiscal Waterfall per Barrel (USD/boe)")
    prod_sel = sel_sc.get('production', {})
    boe_total = prod_sel.get('np_p50', 1.0) * 1e6
    
    comp = {
        "Gross Revenue": nom_total(sel_sc, 'gross_income'),
        "(-) Royalties": -nom_total(sel_sc, 'royalty'),
        "(-) Integrated Tax": -nom_total(sel_sc, 'int_tax'),
        "(-) CAPEX": -nom_total(sel_sc, 'capex'),
        "(-) OPEX": -nom_total(sel_sc, 'opex'),
        "(-) ABEX": -nom_total(sel_sc, 'abex'),
        "(-) Income Tax (ISLR)": -nom_total(sel_sc, 'islr'),
        "Net Cash Flow": nom_total(sel_sc, 'cf_post_tax')
    }
    y_vals = []
    text_vals = []
    for k, v in comp.items():
        v_boe = v * 1e6 / boe_total if boe_total > 0 else 0
        y_vals.append(v_boe)
        text_vals.append(f"${v_boe:,.2f}")
    
    measure_types = ["relative"] * len(comp)
    measure_types[0] = "absolute"
    measure_types[-1] = "total"

    wf_fig = go.Figure(go.Waterfall(
        name="2026 Fiscal Frame", orientation="v",
        measure=measure_types, x=list(comp.keys()), textposition="outside",
        text=text_vals, y=y_vals,
        connector={"line":{"color":"rgb(63, 63, 63)"}},
        decreasing={"marker":{"color":"#ef553b"}},
        increasing={"marker":{"color":"#00cc96"}},
        totals={"marker":{"color":"#636efa"}}
    ))
    wf_fig.update_layout(title="Contractor Profit Margin Breakdown (USD/boe)", 
                         waterfallgap=0.3, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(248,249,250,0.8)')
    st.plotly_chart(wf_fig, use_container_width=True)

with t_det2:
    st.subheader("Pronósticos de Producción")
    r1, r2 = st.columns(2)
    prod_sel = sel_sc.get('production', {})
    res_oil = sel_sc.get('reserves_oil', {'1P': 0.0, '2P': 0.0, '3P': 0.0})
    res_gas = sel_sc.get('reserves_gas', {'1P': 0.0, '2P': 0.0, '3P': 0.0})

    with r1:
        st.plotly_chart(plot_dual(
            dates, get_p10_p50_p90(prod_sel, 'Qo'), get_p10_p50_p90(prod_sel, 'NP'),
            res_oil, "", "Gasto (bpd)", "Np (MMbls)", "green"
        ), use_container_width=True)
        st.plotly_chart(reserves_bar(
            res_oil, "Reservas de Aceite (MMb)",
            '#1a1a2e', '#1f77b4', '#74b9ff', "MMb"
        ), use_container_width=True)

    with r2:
        st.plotly_chart(plot_dual(
            dates, get_p10_p50_p90(prod_sel, 'Qg'), get_p10_p50_p90(prod_sel, 'GP'),
            res_gas, "", "Gasto (Mpcd)", "Gp (MMMpc)", "#d62728"
        ), use_container_width=True)
        st.plotly_chart(reserves_bar(
            res_gas, "Reservas de Gas (MMMpc)",
            '#1a1a2e', '#d62728', '#ff7f7f', "MMMpc"
        ), use_container_width=True)

with t_det3:
    st.subheader("Expected Monthly Expenditures")
    capex_m = get_cf_monthly(cf, 'capex')
    opex_m  = get_cf_monthly(cf, 'opex')
    abex_m  = get_cf_monthly(cf, 'abex')
    
    c_cap, c_op, c_ab = st.columns(3)
    card_tpl = """
    <div style="background: white; border-left: 5px solid #00d4ff; padding: 12px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 15px;">
        <div style="color: #6c757d; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px;">{label}</div>
        <div style="display: flex; flex-direction: column;">
            <div style="color: #0c1c3e; font-size: 1.6rem; font-weight: 800; line-height: 1.2;">{vp} <span style="font-size: 0.8rem; font-weight: 400; color: #00d4ff;">MMUSD (NPV)</span></div>
            <div style="color: #a0aec0; font-size: 1.0rem; font-weight: 600; margin-top: 4px;">{nominal} <span style="font-size: 0.7rem; font-weight: 400;">Nominal</span></div>
        </div>
    </div>
    """
    with c_cap: st.markdown(card_tpl.format(label="TOTAL CAPEX", vp=f"{np.mean(ind_det.get('npv_capex', [0])):.2f}", nominal=f"{np.sum(capex_m):.2f}"), unsafe_allow_html=True)
    with c_op:  st.markdown(card_tpl.format(label="TOTAL OPEX",  vp=f"{np.mean(ind_det.get('npv_opex', [0])):.2f}",  nominal=f"{np.sum(opex_m):.2f}"),  unsafe_allow_html=True)
    with c_ab:  st.markdown(card_tpl.format(label="TOTAL ABEX",  vp=f"{np.mean(ind_det.get('npv_abex', [0])):.2f}",  nominal=f"{np.sum(abex_m):.2f}"),  unsafe_allow_html=True)
    
    if len(capex_m) > 0:
        c_exp1, c_exp2 = st.columns([2, 1])
        
        with c_exp1:
            cum_c = np.cumsum(np.array(capex_m) + np.array(opex_m) + np.array(abex_m))
            fig_exp = go.Figure()
            fig_exp.add_trace(go.Bar(x=dates, y=capex_m, name='CAPEX', marker_color='#1f77b4'))
            fig_exp.add_trace(go.Bar(x=dates, y=opex_m,  name='OPEX',  marker_color='#ff7f0e'))
            fig_exp.add_trace(go.Bar(x=dates, y=abex_m,  name='ABEX',  marker_color='#2ca02c'))
            fig_exp.add_trace(go.Scatter(x=dates, y=cum_c, name='Cumulative Cost', yaxis='y2', line=dict(color='black', width=3)))
            fig_exp.update_layout(barmode='stack', title="Expected Investments and Expenditures (Monte Carlo Mean)",
                                  xaxis_title="Date", yaxis_title="Monthly Disbursement (MMUSD)",
                                  yaxis2=dict(title="Cumulative Cost (MMUSD)", overlaying='y', side='right'),
                                  legend=dict(orientation='h', yanchor='top', y=-0.2, xanchor='center', x=0.5),
                                  paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(b=100), hovermode='x unified')
            st.plotly_chart(fig_exp, use_container_width=True)

        with c_exp2:
            p = sel_sc.get('params', {})
            act_names = ["Reactivation", "Cleansing and Stimulation", "Change of Zone", "Workover", "Drilling Completion"]
            act_vals = [
                p.get('n_reactivacion', 0),
                p.get('n_limpieza', 0),
                p.get('n_cambio_zona', 0),
                p.get('n_rma', 0),
                p.get('n_terminaciones', 0)
            ]
            total_act = sum(act_vals)
            
            fig_act = go.Figure(go.Bar(
                x=act_names,
                y=act_vals,
                text=act_vals,
                textposition='outside',
                marker_color='#1f77b4'
            ))
            fig_act.update_layout(
                title=dict(text=f"<b>Activity Quantity</b><br><span style='font-size: 14px; font-weight: normal; color: #000;'>Total: {total_act}</span>", font=dict(size=18, color='#0c1c3e'), x=0),
                xaxis=dict(tickangle=-45),
                yaxis_title="# Interventions",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(248,249,250,0.8)',
                margin=dict(b=100, t=80)
            )
            st.plotly_chart(fig_act, use_container_width=True)

        # ─── DISTRIBUCIÓN DE EGRESOS POR RENGLÓN (MEDIA MONTE CARLO) ────────
        st.markdown("<hr style='margin: 30px 0 20px 0; border: none; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)
        col_pie_title, col_pie_toggle = st.columns([1.8, 1])
        with col_pie_title:
            st.markdown(
                "<div style='display:flex; align-items:center; gap:8px;'>"
                "<span style='font-size:1.4rem;'>📊</span>"
                "<h3 style='margin:0; color:#012743; font-family:Inter,sans-serif; font-weight:700; font-size:1.35rem;'>Distribución de Egresos por Renglón (Media Monte Carlo)</h3>"
                "</div>",
                unsafe_allow_html=True
            )
        with col_pie_toggle:
            pie_mode = st.segmented_control(
                "Visualización de Pastel Egresos",
                options=["Porcentajes (%)", "Monto (MMUSD)"],
                default="Porcentajes (%)",
                label_visibility="collapsed",
                key=f"pie_mode_egresos_{sel_esc_name}"
            ) or "Porcentajes (%)"

        egresos_det = sel_sc.get('egresos_detallados')

        def get_subcategory_sum_from_json(egresos, cat, pattern):
            if not egresos or cat not in egresos:
                return 0.0
            pattern_re = re.compile(pattern, re.IGNORECASE)
            total = 0.0
            for row_idx, vals in egresos[cat].items():
                if pattern_re.search(str(row_idx)):
                    total += sum(float(v) for v in vals)
            return total

        capex_infra = get_subcategory_sum_from_json(egresos_det, 'capex', r'Infra.*Media')
        capex_pozo  = get_subcategory_sum_from_json(egresos_det, 'capex', r'Pozo.*Desarrollo.*Media')
        capex_rma   = get_subcategory_sum_from_json(egresos_det, 'capex', r'RMA.*Media')
        capex_expl  = get_subcategory_sum_from_json(egresos_det, 'capex', r'Explora.*Media')

        opex_fijo   = get_subcategory_sum_from_json(egresos_det, 'opex', r'Fijo.*Media')
        opex_rme    = get_subcategory_sum_from_json(egresos_det, 'opex', r'RME.*Media')
        opex_var    = get_subcategory_sum_from_json(egresos_det, 'opex', r'Variable.*Media')
        opex_mano   = get_subcategory_sum_from_json(egresos_det, 'opex', r'Mano.*Obra.*Media')
        opex_adm    = get_subcategory_sum_from_json(egresos_det, 'opex', r'Administra.*Media')
        opex_otro   = get_subcategory_sum_from_json(egresos_det, 'opex', r'Otros.*Egresos.*Media')

        abex_infra  = get_subcategory_sum_from_json(egresos_det, 'abex', r'Abandono.*Infra.*Media')
        abex_pozos  = get_subcategory_sum_from_json(egresos_det, 'abex', r'Abandono.*Pozos.*Media')

        def render_pie_chart(labels, values, title, color_sequence):
            filtered_labels = []
            filtered_values = []
            for l, v in zip(labels, values):
                if v > 1e-4:
                    filtered_labels.append(l)
                    filtered_values.append(v)
            
            if not filtered_values:
                st.markdown(f"""
                <div style="background-color: #f8fafc; border-left: 4px solid #cbd5e1; padding: 20px; border-radius: 12px; height: 260px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.02); margin-top: 10px;">
                    <div style="font-size: 2rem; margin-bottom: 5px;">🚫</div>
                    <h6 style="color: #64748b; margin: 0; font-family: 'Inter', sans-serif; font-weight: 700;">{title}</h6>
                    <p style="color: #94a3b8; font-size: 0.8rem; margin-top: 6px;">No aplica para este proyecto / Datos no disponibles</p>
                </div>
                """, unsafe_allow_html=True)
                return

            if pie_mode == "Porcentajes (%)":
                text_info = 'percent+label'
                text_list = None
            else:
                text_info = 'text+label'
                text_list = [f"{v:.2f} MMUSD" for v in filtered_values]

            fig = go.Figure(data=[go.Pie(
                labels=filtered_labels,
                values=filtered_values,
                hole=0.45,
                marker=dict(colors=color_sequence),
                text=text_list,
                textinfo=text_info,
                insidetextorientation='horizontal',
                hovertemplate="<b>%{label}</b><br>Monto: %{value:.2f} MMUSD<br>Porcentaje: %{percent}<extra></extra>"
            )])
            fig.update_layout(
                title=dict(
                    text=f"<b>{title}</b>",
                    font=dict(family='Inter, sans-serif', size=15, color='#1a1c1e'),
                    x=0.5,
                    xanchor='center'
                ),
                showlegend=False,
                margin=dict(t=50, b=10, l=10, r=10),
                height=280,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
            )
            st.plotly_chart(fig, use_container_width=True)

        c_pie1, c_pie2, c_pie3 = st.columns(3)
        with c_pie1:
            render_pie_chart(
                ["Infraestructura", "Perforación", "RMA", "Exploración"],
                [capex_infra, capex_pozo, capex_rma, capex_expl],
                "CAPEX",
                ['#1f77b4', '#3ca0e6', '#74b9ff', '#adcde7']
            )
        with c_pie2:
            render_pie_chart(
                ["Fijo", "RME", "Variable", "Mano de Obra", "Administración", "Otros Egresos"],
                [opex_fijo, opex_rme, opex_var, opex_mano, opex_adm, opex_otro],
                "OPEX",
                ['#ff7f0e', '#ffa854', '#ffd1a4', '#d62728', '#f88379', '#fab1a0']
            )
        with c_pie3:
            render_pie_chart(
                ["Infraestructura", "Pozos"],
                [abex_infra, abex_pozos],
                "ABEX",
                ['#2ca02c', '#55efc4']
            )

        # ─── ANÁLISIS DETALLADO DE INTERVENCIONES (DRILEX) ───────────────
        df_drilex_list = sel_sc.get('params', {}).get('df_drilex', [])
        if df_drilex_list:
            st.markdown("<hr style='margin: 30px 0 20px 0; border: none; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)
            st.markdown(
                "<div style='display:flex; align-items:center; gap:8px; margin-bottom:15px;'>"
                "<span style='font-size:1.4rem;'>🛢️</span>"
                "<h3 style='margin:0; color:#012743; font-family:Inter,sans-serif; font-weight:700; font-size:1.35rem;'>Análisis Detallado de Intervenciones (DRILEX)</h3>"
                "</div>",
                unsafe_allow_html=True
            )
            
            df_drilex_df = pd.DataFrame(df_drilex_list)
            if not df_drilex_df.empty and 'Fecha' in df_drilex_df.columns:
                df_drilex_df['Fecha_dt'] = pd.to_datetime(df_drilex_df['Fecha'], dayfirst=True, errors='coerce')
                
                sc_dates_dt = pd.to_datetime(dates)
                if len(sc_dates_dt) > 0:
                    start_dt = sc_dates_dt[0]
                    end_dt = sc_dates_dt[-1]
                    df_filtered = df_drilex_df[(df_drilex_df['Fecha_dt'] >= start_dt) & (df_drilex_df['Fecha_dt'] <= end_dt)].copy()
                    
                    if not df_filtered.empty:
                        # 1. Occurrence bar chart
                        df_filtered['Mes'] = df_filtered['Fecha_dt'].dt.strftime('%Y-%m')
                        if 'Cantidad de Pozos' in df_filtered.columns:
                            df_filtered['Cantidad de Pozos'] = pd.to_numeric(df_filtered['Cantidad de Pozos'], errors='coerce').fillna(1)
                            df_occ_raw = df_filtered.groupby(['Mes', 'Tipo de Actividad'])['Cantidad de Pozos'].sum().reset_index(name='Ocurrencias')
                        else:
                            df_occ_raw = df_filtered.groupby(['Mes', 'Tipo de Actividad']).size().reset_index(name='Ocurrencias')
                        
                        min_act_dt = df_filtered['Fecha_dt'].min()
                        max_act_dt = df_filtered['Fecha_dt'].max()
                        start_year = min_act_dt.year
                        end_year = max_act_dt.year
                        all_months = pd.date_range(start=f"{start_year}-01-01", end=f"{end_year}-12-01", freq='MS')
                        
                        all_types = ['Perforación', 'RMA', 'RME']
                        months_str = all_months.strftime('%Y-%m')
                        mux = pd.MultiIndex.from_product([months_str, all_types], names=['Mes', 'Tipo de Actividad'])
                        df_template = pd.DataFrame(index=mux).reset_index()
                        
                        df_occ = pd.merge(df_template, df_occ_raw, on=['Mes', 'Tipo de Actividad'], how='left').fillna(0)
                        df_occ['Ocurrencias'] = pd.to_numeric(df_occ['Ocurrencias'], errors='coerce').fillna(0).astype(int)
                        df_occ = df_occ.sort_values('Mes')
                        df_occ['Fecha_Grafica'] = pd.to_datetime(df_occ['Mes'] + '-01')
                        
                        fig_occ = px.bar(
                            df_occ,
                            x='Fecha_Grafica',
                            y='Ocurrencias',
                            color='Tipo de Actividad',
                            barmode='stack',
                            color_discrete_map={
                                'Perforación': '#3ca0e6',
                                'RMA': '#74b9ff',
                                'RME': '#ffa854'
                            },
                            category_orders={'Tipo de Actividad': ['Perforación', 'RMA', 'RME']}
                        )
                        fig_occ.update_layout(
                            title=dict(
                                text="<b>Ocurrencia Mensual de Intervenciones</b>",
                                font=dict(family='Inter, sans-serif', size=16, color='#1a1c1e'),
                                x=0.5,
                                xanchor='center'
                            ),
                            xaxis_title="Mes (Año-Mes)",
                            yaxis_title="Cantidad de Intervenciones",
                            legend_title="Actividad",
                            font=dict(family='Inter, sans-serif', size=12),
                            height=380,
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            hovermode='x unified',
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                        )
                        fig_occ.update_xaxes(type='date', tickformat='%Y-%m', hoverformat='%Y-%m')
                        
                        # 2. Cost calculations from JSON
                        discount_rate_drilex = float(sel_sc.get('params', {}).get('discount_rate', 15.0))
                        
                        def get_subcategory_metrics_from_json(egresos, cat, pattern, dates_list, discount_rate_ann):
                            if not egresos or cat not in egresos:
                                return 0.0, 0.0
                            pattern_re = re.compile(pattern, re.IGNORECASE)
                            monthly_flow = None
                            for row_idx, vals in egresos[cat].items():
                                if pattern_re.search(str(row_idx)):
                                    arr_vals = np.array([float(v) for v in vals])
                                    if monthly_flow is None:
                                        monthly_flow = arr_vals
                                    else:
                                        monthly_flow += arr_vals
                            
                            if monthly_flow is None:
                                return 0.0, 0.0
                            nominal_sum = float(np.sum(monthly_flow))
                            
                            dr = discount_rate_ann / 100.0
                            monthly_r = (1 + dr) ** (1 / 12) - 1
                            months = np.arange(len(dates_list))
                            discount_factors = (1 + monthly_r) ** months
                            
                            if len(monthly_flow) > len(discount_factors):
                                monthly_flow = monthly_flow[:len(discount_factors)]
                            elif len(monthly_flow) < len(discount_factors):
                                discount_factors = discount_factors[:len(monthly_flow)]
                                
                            vp_sum = float(np.sum(monthly_flow / discount_factors))
                            return nominal_sum, vp_sum
                        
                        nom_perf, vp_perf = get_subcategory_metrics_from_json(egresos_det, 'capex', r'Pozo.*Desarrollo.*Media', dates, discount_rate_drilex)
                        nom_rma, vp_rma   = get_subcategory_metrics_from_json(egresos_det, 'capex', r'RMA.*Media', dates, discount_rate_drilex)
                        nom_rme, vp_rme   = get_subcategory_metrics_from_json(egresos_det, 'opex', r'RME.*Media', dates, discount_rate_drilex)
                        
                        # Layout side by side
                        col_dr1, col_dr2 = st.columns([1.5, 1])
                        with col_dr1:
                            st.plotly_chart(fig_occ, use_container_width=True)
                        with col_dr2:
                            drilex_cost_mode = st.segmented_control(
                                "Tipo de Costo DRILEX",
                                options=["Nominal", "Valor Presente (VP)"],
                                default="Valor Presente (VP)",
                                key=f"drilex_cost_mode_{sel_esc_name}"
                            ) or "Valor Presente (VP)"
                            
                            labels_drilex = ["Perforación", "RMA", "RME"]
                            if drilex_cost_mode == "Valor Presente (VP)":
                                values_drilex = [vp_perf, vp_rma, vp_rme]
                                unit = "MMUSD (VP)"
                            else:
                                values_drilex = [nom_perf, nom_rma, nom_rme]
                                unit = "MMUSD"
                            
                            total_drilex = sum(values_drilex)
                            colors_drilex = ['#3ca0e6', '#74b9ff', '#ffa854']
                            
                            filtered_labels = []
                            filtered_values = []
                            for l, v in zip(labels_drilex, values_drilex):
                                if v > 1e-4:
                                    filtered_labels.append(l)
                                    filtered_values.append(v)
                                    
                            if filtered_values:
                                _total_c = sum(filtered_values)
                                _slice_text_c = [
                                    f"<b>{l}</b><br>{v:.2f} {unit}" if v / _total_c >= 0.05 else ""
                                    for l, v in zip(filtered_labels, filtered_values)
                                ]
                                _slice_pull_c = [0.07 if v / _total_c < 0.05 else 0 for v in filtered_values]

                                fig_cost = go.Figure(data=[go.Pie(
                                    labels=filtered_labels,
                                    values=filtered_values,
                                    hole=0.5,
                                    marker=dict(colors=[colors_drilex[labels_drilex.index(l)] for l in filtered_labels]),
                                    text=_slice_text_c,
                                    textinfo='text',
                                    textposition='inside',
                                    insidetextorientation='horizontal',
                                    pull=_slice_pull_c,
                                    hovertemplate="<b>%{label}</b><br>Costo: %{value:.2f} " + unit + "<br>Porcentaje: %{percent:.1%}<extra></extra>"
                                )])
                                fig_cost.update_layout(
                                    title=dict(
                                        text=f"<b>Distribución de Costos DRILEX ({drilex_cost_mode})</b>",
                                        font=dict(family='Inter, sans-serif', size=15, color='#1a1c1e'),
                                        x=0.5, xanchor='center', y=0.98, yanchor='top'
                                    ),
                                    annotations=[dict(
                                        text=f"Total<br><b>{total_drilex:.2f}</b><br>{unit}",
                                        x=0.5, y=0.5, font_size=11, showarrow=False, align="center"
                                    )],
                                    showlegend=True,
                                    legend=dict(
                                        orientation="h", yanchor="bottom", y=-0.15,
                                        xanchor="center", x=0.5,
                                        font=dict(size=11), itemsizing='constant'
                                    ),
                                    margin=dict(t=50, b=70, l=20, r=20),
                                    height=380,
                                    paper_bgcolor='rgba(0,0,0,0)',
                                    plot_bgcolor='rgba(0,0,0,0)',
                                )
                                st.plotly_chart(fig_cost, use_container_width=True)
                            else:
                                st.markdown(f"""
                                <div style="background-color: #f8fafc; border-left: 4px solid #cbd5e1; padding: 20px; border-radius: 12px; height: 360px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.02); margin-top: 10px;">
                                    <div style="font-size: 2.5rem; margin-bottom: 10px;">🚫</div>
                                    <h5 style="color: #64748b; margin: 0; font-family: 'Inter', sans-serif; font-weight: 700;">Distribución de Costos DRILEX</h5>
                                    <p style="color: #94a3b8; font-size: 0.9rem; margin-top: 8px;">No hay costos asociados en este horizonte</p>
                                </div>
                                """, unsafe_allow_html=True)
                    else:
                        st.info("No hay intervenciones registradas en el horizonte de este escenario.")

with t_det4:
    st.subheader("Net Present Value Distributions (MMUSD)")
    nom_pre   = nom_total(sel_sc, 'cf_pre_tax')
    nom_post  = nom_total(sel_sc, 'cf_post_tax')
    nom_state = nom_total(sel_sc, 'state_income')
    nom_roy   = nom_total(sel_sc, 'royalty')

    dc1, dc2 = st.columns(2)
    with dc1:
        st.plotly_chart(hist_plot(ind_det.get('npv_hpoc_pre', []),  "NPV Pre-Tax Contractor", '#1f77b4', nom_val=nom_pre),   use_container_width=True)
        st.plotly_chart(hist_plot(ind_det.get('npv_state', []),     "NPV Total State Take",   '#7B2FBE', nom_val=nom_state), use_container_width=True)
    with dc2:
        st.plotly_chart(hist_plot(ind_det.get('npv_hpoc_post', []), "NPV Post-Tax Contractor", '#17becf', nom_val=nom_post),  use_container_width=True)
        st.plotly_chart(hist_plot(ind_det.get('npv_royalty', []),   "NPV Royalties",           '#2ca02c', nom_val=nom_roy),   use_container_width=True)

with t_det5:
    st.subheader("Expected Cash Flow Analysis")
    inc_m  = get_cf_monthly(cf, 'gross_income')
    if len(inc_m) > 0:
        capex_m = get_cf_monthly(cf, 'capex')
        opex_m  = get_cf_monthly(cf, 'opex')
        abex_m  = get_cf_monthly(cf, 'abex')
        cost_m = capex_m + opex_m + abex_m
        roy_m  = get_cf_monthly(cf, 'royalty')
        int_m  = get_cf_monthly(cf, 'int_tax')
        islr_m = get_cf_monthly(cf, 'islr')
        net_m  = get_cf_monthly(cf, 'cf_post_tax')

        fig_cf = go.Figure()
        fig_cf.add_trace(go.Bar(x=dates, y=inc_m,   name='Gross Revenue',       marker_color='#17becf'))
        fig_cf.add_trace(go.Bar(x=dates, y=-cost_m, name='Costs (CAPEX+OPEX+ABEX)', marker_color='#d62728'))
        
        # Desglose de impuestos en tonos de gris
        fig_cf.add_trace(go.Bar(x=dates, y=-roy_m,  name='Royalties',          marker_color='#a6a6a6'))
        fig_cf.add_trace(go.Bar(x=dates, y=-int_m,  name='Integrated Tax',     marker_color='#7f7f7f'))
        fig_cf.add_trace(go.Bar(x=dates, y=-islr_m, name='Income Tax (ISLR)',  marker_color='#4d4d4d'))
        fig_cf.add_trace(go.Scatter(x=dates, y=net_m, name='Net Cash Flow',  line=dict(color='black', width=2)))
        fig_cf.update_layout(barmode='relative', title="Expected Cash Flow (Monte Carlo Mean)",
                             xaxis_title="Date", yaxis_title="MM USD",
                             legend=dict(orientation='h', yanchor='top', y=-0.2, xanchor='center', x=0.5),
                             paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(b=100), hovermode='x unified')
        st.plotly_chart(fig_cf, use_container_width=True)

# ─── TAB 7: INDICADORES & SENSIBILIDAD ───────────────────────────────────────
with t_sens:
    _oil_p  = sel_sc.get('params', {}).get('oil_price', '—')
    _gas_p  = sel_sc.get('params', {}).get('gas_price', '—')
    st.markdown(
        f"<div style='display:flex; justify-content:space-between; align-items:baseline; margin-bottom:20px; border-bottom:3px solid #012743; padding-bottom:12px;'>"
        f"<h2 style='margin:0; color:#012743; font-family:Inter,sans-serif; font-size:1.85rem; font-weight:700;'>Resumen de Indicadores Económicos</h2>"
        f"<div style='color:#4a5568; font-size:0.95rem; font-family:Inter,sans-serif; background:#f8fafc; padding:5px 15px; border-radius:20px; border:1px solid #e2e8f0;'>"
        f"<b>Precio Aceite:</b> <span style='color:#012743; font-weight:700;'>${float(_oil_p):.2f} USD/bl</span> | "
        f"<b>Precio Gas:</b> <span style='color:#012743; font-weight:700;'>${float(_gas_p):.2f} USD/mcf</span>"
        f"</div></div>",
        unsafe_allow_html=True
    )
    
    ind_dict = sel_sc.get('indicators', {})
    
    def _agg_list(arr):
        a = np.asarray(arr, dtype=float)
        if a.size == 0: return [0.0]*7
        return [np.mean(a), np.std(a), np.min(a), np.percentile(a,10), 
                np.percentile(a,50), np.percentile(a,90), np.max(a)]

    summary_rows = [
        ("VP de los Ingresos", "VP Ingresos por Aceite (MMUSD)", _agg_list(ind_dict.get('npv_oil_income', [0]))),
        ("VP de los Ingresos", "VP Ingresos por Gas (MMUSD)", _agg_list(ind_dict.get('npv_gas_income', [0]))),
        ("Indicadores de Valor Presente (VP)", "VP Regalías (MMUSD)", _agg_list(ind_dict.get('npv_royalty', [0]))),
        ("Indicadores de Valor Presente (VP)", "VP Impuesto Integrado (MMUSD)", _agg_list(ind_dict.get('npv_int_tax', [0]))),
        ("Indicadores de Valor Presente (VP)", "VP Impuesto sobre la Renta (ISLR) (MMUSD)", _agg_list(ind_dict.get('npv_islr', [0]))),
        ("Indicadores de Valor Presente (VP)", "VP Participación Total del Estado (MMUSD)", _agg_list(ind_dict.get('npv_state', [0]))),
        ("VPN HPOC (Rentabilidad Operativa)", "VPN Contratista Pre-Impuesto (MMUSD)", _agg_list(ind_dict.get('npv_hpoc_pre', [0]))),
        ("VPN HPOC (Rentabilidad Operativa)", "VPN Contratista Post-Impuesto (MMUSD)", _agg_list(ind_dict.get('npv_hpoc_post', [0]))),
        ("Eficiencia Operativa y Recuperación", "Pico de Inversión (MCE) (MMUSD)", _agg_list(ind_dict.get('mce_mm', [0]))),
        ("Eficiencia Operativa y Recuperación", "Tiempo de Recuperación (Años)", _agg_list(ind_dict.get('payout_years', [0]))),
        ("Eficiencia Operativa y Recuperación", "MOIC (Múltiplo de Inversión)", _agg_list(ind_dict.get('moic', [0]))),
        ("Eficiencia Operativa y Recuperación", "Punto de Equilibrio (USD/bbl)", _agg_list(ind_dict.get('breakeven_price', [0]))),
        ("Eficiencia Operativa y Recuperación", "Máximo Requerimiento de Financiamiento (MMUSD)", _agg_list(ind_dict.get('max_financing_mm', [0]))),
        ("Medida de Competitividad Internacional", "Government Take (%)", _agg_list(ind_dict.get('npv_gov_take', [0])))
    ]

    cat_counts = {}
    for r in summary_rows:
        cat_counts[r[0]] = cat_counts.get(r[0], 0) + 1

    table_html = """
    <style>
        .premium-table { width: 100%; border-collapse: collapse; margin-bottom: 25px; font-family: 'Inter', sans-serif; font-size: 0.88rem; background-color: white; border: 1px solid #e2e8f0; }
        .premium-table th { background-color: #012743; color: white; text-align: center; padding: 12px 10px; font-weight: 600; border: 1px solid #1d3d5a; text-transform: uppercase; letter-spacing: 0.5px; }
        .premium-table td { padding: 10px; border: 1px solid #e2e8f0; text-align: center; color: #2d3748; }
        .premium-table .group-header { background-color: #ffffff; font-weight: 700; color: #012743; text-align: left; padding-left: 15px; width: 22%; border-right: 2px solid #cbd5e0; vertical-align: middle; }
        .premium-table .indicator-name { text-align: left; padding-left: 15px; width: 28%; font-weight: 500; color: #4a5568; }
        .premium-table tr:nth-child(even) { background-color: #f8fafc; }
        .premium-table tr:hover { background-color: #f1f5f9; }
        .premium-table .val-cell { font-family: 'Courier New', monospace; font-weight: 600; text-align: right; }
    </style>
    <table class="premium-table">
        <thead>
            <tr>
                <th>Clasificación</th><th>Indicador</th><th>Media</th><th>Desv. Est.</th>
                <th>Mín</th><th>P10</th><th>P50</th><th>P90</th><th>Máx</th>
            </tr>
        </thead>
        <tbody>
    """
    curr_cat = None
    for cat, ind_name, vals in summary_rows:
        table_html += "<tr>"
        if cat != curr_cat:
            table_html += f'<td class="group-header" rowspan="{cat_counts[cat]}">{cat}</td>'
            curr_cat = cat
        table_html += f'<td class="indicator-name">{ind_name}</td>'
        for v in vals:
            table_html += f'<td class="val-cell">{v:,.2f}</td>'
        table_html += "</tr>"
    table_html += "</tbody></table>"
    st.markdown(table_html, unsafe_allow_html=True)

    # ─── TIRM Cards ───
    st.markdown("<br>", unsafe_allow_html=True)
    c_irr1, c_irr2 = st.columns(2)
    tirm_pre_val = ind_dict.get('irr_pre_annual')
    tirm_post_val = ind_dict.get('irr_post_annual')
    disc_r = float(sel_sc['params'].get('discount_rate', 15.0))

    def _fmt_tirm(val):
        try:
            if val is None or not np.isfinite(float(val)): return "N/A"
            return f"{float(val):.2f}%"
        except Exception:
            return "N/A"

    def _irr_color(val):
        if val is None: return "#a0aec0"
        try:
            v = float(val)
            if v >= disc_r: return "#16a34a"
            if v >= 0: return "#d97706"
            return "#dc2626"
        except Exception:
            return "#a0aec0"

    card_irr_tpl = """
    <div style="background: white; border-left: 5px solid #00d4ff; padding: 22px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); height: 100%;">
        <div style="color: #6c757d; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 1px;">{label}</div>
        <div style="color: {color}; font-size: 2.8rem; font-weight: 800; line-height: 1;">{value}</div>
        <div style="color: #a0aec0; font-size: 0.72rem; margin-top: 8px; font-style: italic;">TIRM — Tasa Interna de Retorno Modificada (anual efectiva)</div>
    </div>
    """
    with c_irr1:
        st.markdown(card_irr_tpl.format(label="TIRM PRE-TAX (% ANUAL)", value=_fmt_tirm(tirm_pre_val), color=_irr_color(tirm_pre_val)), unsafe_allow_html=True)
    with c_irr2:
        st.markdown(card_irr_tpl.format(label="TIRM POST-TAX (% ANUAL)", value=_fmt_tirm(tirm_post_val), color=_irr_color(tirm_post_val)), unsafe_allow_html=True)

    st.caption(
        f"💡 **TIRM (Tasa Interna de Retorno Modificada):** Equivalente a `TIRM()` de Excel. "
        f"Flujos negativos financiados y flujos positivos reinvertidos a la tasa de descuento del proyecto ({disc_r:.1f}% anual)."
    )

    # ─── SENSITIVITY MATRIX (AS IN USER IMAGE) ───
    st.markdown("---")
    st.subheader("Análisis de Sensibilidad: Regalías vs Precio Aceite")
    
    sens_raw = sel_sc.get('sensibilidad', [])
    prices_found = sorted(list({float(d.get('Precio Aceite', d.get('Oil Price', 0))) for d in sens_raw if 'Precio Aceite' in d or 'Oil Price' in d}))
    p_defaults = [50.0, 60.0, 70.0, 80.0]
    if len(prices_found) >= 4:
        p_defaults = prices_found[:4]

    cs1, cs2, cs3, cs4 = st.columns(4)
    with cs1: p1 = st.number_input("Precio 1 (USD/bl)", value=float(p_defaults[0]), step=5.0, key=f"s_p1_{sel_esc_name}")
    with cs2: p2 = st.number_input("Precio 2 (USD/bl)", value=float(p_defaults[1]), step=5.0, key=f"s_p2_{sel_esc_name}")
    with cs3: p3 = st.number_input("Precio 3 (USD/bl)", value=float(p_defaults[2]), step=5.0, key=f"s_p3_{sel_esc_name}")
    with cs4: p4 = st.number_input("Precio 4 (USD/bl)", value=float(p_defaults[3]), step=5.0, key=f"s_p4_{sel_esc_name}")

    st.button("Ejecutar Sensibilidad", type="primary", key=f"btn_exec_sens_{sel_esc_name}")

    if sens_raw:
        df_sens_tab5 = pd.DataFrame(sens_raw)
        
        def _norm_s_col(c):
            if 'Precio' in c or 'Oil' in c: return 'Precio Aceite'
            if 'Regal' in c or 'Royalty' in c: return 'Regalía (%)'
            if 'VPN HPOC Post' in c: return 'VPN HPOC Post (MMUSD)'
            if 'VPN HPOC Pre' in c: return 'VPN HPOC Pre (MMUSD)'
            if 'Gov Take' in c: return 'Gov Take (%)'
            if 'MCE' in c or 'Peak' in c: return 'MCE (MMUSD)'
            if 'Payout' in c: return 'Payout (Years)'
            if 'Max Financ' in c: return 'Max Financ. (MMUSD)'
            if 'Break-even' in c or 'Punto' in c: return 'Break-even (USD/bbl)'
            if 'TIRM' in c or 'IRR' in c: return 'TIRM Post-Tax (%)'
            return c

        df_sens_tab5.columns = [_norm_s_col(c) for c in df_sens_tab5.columns]
        df_sens_tab5 = _ensure_sens_pre_tax(df_sens_tab5, sel_sc)

        expected_sens_cols = [
            'VPN HPOC Pre (MMUSD)', 'VPN HPOC Post (MMUSD)', 'Max Financ. (MMUSD)',
            'Gov Take (%)', 'TIRM Post-Tax (%)', 'Break-even (USD/bbl)',
            'Payout (Years)', 'MCE (MMUSD)'
        ]
        for col in expected_sens_cols:
            if col not in df_sens_tab5.columns:
                df_sens_tab5[col] = np.nan

        target_prices = [p1, p2, p3, p4]
        df_sens_tab5['Precio_Match'] = df_sens_tab5['Precio Aceite'].apply(lambda x: min(target_prices, key=lambda t: abs(t - x)))
        
        def _mk_pivot(col):
            piv = df_sens_tab5.pivot_table(index='Regalía (%)', columns='Precio_Match', values=col, aggfunc='mean')
            piv = piv.sort_index(ascending=True)
            return piv

        pivot_pre  = _mk_pivot('VPN HPOC Pre (MMUSD)')
        pivot_post = _mk_pivot('VPN HPOC Post (MMUSD)')
        pivot_mf   = _mk_pivot('Max Financ. (MMUSD)')
        pivot_gt   = _mk_pivot('Gov Take (%)')
        pivot_tirm = _mk_pivot('TIRM Post-Tax (%)')
        pivot_be   = _mk_pivot('Break-even (USD/bbl)')

        # Fila 1 de Matrices de Calor
        r1_c1, r1_c2, r1_c3 = st.columns(3)
        with r1_c1:
            st.markdown("#### VPN HPOC Pre-Tax (MMUSD)")
            st.dataframe(pivot_pre.style.background_gradient(cmap='Blues').format("{:.1f}"), use_container_width=True)
        with r1_c2:
            st.markdown("#### VPN HPOC Post-Tax (MMUSD)")
            st.dataframe(pivot_post.style.background_gradient(cmap='Blues').format("{:.1f}"), use_container_width=True)
        with r1_c3:
            st.markdown("#### Máx. Req. Financiamiento (MMUSD)")
            st.dataframe(pivot_mf.style.background_gradient(cmap='Oranges').format("{:.1f}"), use_container_width=True)

        # Fila 2 de Matrices de Calor
        r2_c1, r2_c2, r2_c3 = st.columns(3)
        with r2_c1:
            st.markdown("#### Government Take (%)")
            st.dataframe(pivot_gt.style.background_gradient(cmap='Reds').format("{:.2f}%"), use_container_width=True)
        with r2_c2:
            st.markdown("#### TIRM Post-Tax (% anual)")
            if pivot_tirm.notnull().any().any():
                st.dataframe(pivot_tirm.style.background_gradient(cmap='Greens').format("{:.2f}%"), use_container_width=True)
            else:
                st.dataframe(pivot_post.style.background_gradient(cmap='Greens').format("{:.1f}"), use_container_width=True)
        with r2_c3:
            st.markdown("#### Punto de Equilibrio (USD/bbl)")
            st.dataframe(pivot_be.style.background_gradient(cmap='YlOrRd_r').format("{:.2f}"), use_container_width=True)

        # ─── Corner Solutions 1: Indicators by Oil Price ───
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="border-bottom: 3px solid #012743; padding-bottom: 10px; margin-bottom: 20px;">
            <h2 style="margin: 0; color: #012743; font-family: 'Inter', sans-serif; font-size: 1.6rem; font-weight: 700;">Corner Solutions 1: Indicators by Oil Price</h2>
            <p style="color: #64748b; font-size: 0.95rem; margin-top: 5px;">Select an oil price to view all key indicators across each evaluated Royalty rate (%)</p>
        </div>
        """, unsafe_allow_html=True)

        cs1_prices = sorted(df_sens_tab5['Precio Aceite'].unique())
        sel_cs1_p = st.selectbox("🛢️ Select Oil Price (USD/bbl)", options=cs1_prices, format_func=lambda x: f"${x:.1f} / bbl", key=f"cs1_p_{sel_esc_name}")
        df_cs1_sub = df_sens_tab5[df_sens_tab5['Precio Aceite'] == sel_cs1_p].sort_values('Regalía (%)')
        roy_cols_cs1 = sorted(df_cs1_sub['Regalía (%)'].unique())

        def _get_cs1_row(col_name):
            return [df_cs1_sub[df_cs1_sub['Regalía (%)'] == r][col_name].values[0] if len(df_cs1_sub[df_cs1_sub['Regalía (%)'] == r]) > 0 else np.nan for r in roy_cols_cs1]

        corner_rows = [
            ("NPV HPOC (High Performance Operation Consortia Profitability)", "NPV Contractor Post-Tax (MMUSD)", _get_cs1_row('VPN HPOC Post (MMUSD)')),
            ("Operational Efficiency and Capital Recovery", "Max Financing Req. (MMUSD)", _get_cs1_row('Max Financ. (MMUSD)')),
            ("Operational Efficiency and Capital Recovery", "Peak Investment (MCE) (MMUSD)", _get_cs1_row('MCE (MMUSD)')),
            ("Operational Efficiency and Capital Recovery", "Break-even (USD/bbl)", _get_cs1_row('Break-even (USD/bbl)')),
            ("Operational Efficiency and Capital Recovery", "Payout Time (Years)", _get_cs1_row('Payout (Years)')),
            ("International Competitiveness Measure", "Government Take (%)", _get_cs1_row('Gov Take (%)'))
        ]

        corner_counts = {}
        for r in corner_rows:
            corner_counts[r[0]] = corner_counts.get(r[0], 0) + 1

        corner_html = f"""
        <table class="premium-table">
            <thead>
                <tr>
                    <th>Classification</th><th>Indicator</th>
                    {" ".join([f"<th>{r:.0f}%</th>" for r in roy_cols_cs1])}
                </tr>
            </thead>
            <tbody>
        """
        c_curr_cat = None
        for cat, ind_lbl, vals in corner_rows:
            corner_html += "<tr>"
            if cat != c_curr_cat:
                corner_html += f'<td class="group-header" rowspan="{corner_counts[cat]}">{cat}</td>'
                c_curr_cat = cat
            corner_html += f'<td class="indicator-name">{ind_lbl}</td>'
            for v in vals:
                fmt_v = f"{v:,.2f}" if pd.notnull(v) else "—"
                corner_html += f'<td class="val-cell">{fmt_v}</td>'
            corner_html += "</tr>"
        corner_html += "</tbody></table>"
        st.markdown(corner_html, unsafe_allow_html=True)
    else:
        st.warning("⚠️ No se encontraron datos de sensibilidad precalculados en este escenario.")


# ─── TAB 8: EQUILIBRIO FISCAL / GT ──────────────────────────────────────────
with t_gt:
    st.header("⚖️ Sensibilidad de Equilibrio Fiscal (Government Take)")
    st.markdown("""
    Esta herramienta busca las combinaciones de **Regalía**, **Impuesto Integrado** e **ISLR** que cumplen con un objetivo de **Government Take (GT)**.
    Los resultados se ordenan de mayor a menor rentabilidad para el contratista (**VPN Post-Tax**).
    """)
    
    col_gt1, col_gt2 = st.columns([1, 2])
    with col_gt1:
        target_gt = st.number_input("Objetivo Government Take (%)", min_value=1.0, max_value=99.0, value=float(sel_sc['params'].get('target_gt', 50.0)), step=1.0, key=f"tgt_{sel_esc_name}")
        tolerance = st.slider("Tolerancia (+/- %)", 0.1, 5.0, 1.0, step=0.1, key=f"tol_{sel_esc_name}")
        precision = st.radio("Precisión de búsqueda", ["Fina (1%)", "Media (2%)", "Gruesa (5%)"], index=0, horizontal=True, key=f"prec_{sel_esc_name}")
    
    with col_gt2:
        st.info(f"Se buscarán combinaciones que resulten en un GT entre **{(target_gt - tolerance):.1f}%** y **{(target_gt + tolerance):.1f}%**.")
        st.caption("Esta herramienta evalúa miles de combinaciones fiscales instantáneamente a partir de los ingresos y egresos del proyecto.")

    st.markdown("### ⚙️ Rangos de Sensibilidad Fiscal")
    st.caption("Define los límites de búsqueda para cada parámetro. Se muestran los límites legales para referencia.")
    cr1, cr2, cr3 = st.columns(3)
    with cr1:
        range_royalty = st.slider("Regalía (%)", 0, 30, (20, 30), step=1, key=f"r_roy_{sel_esc_name}")
        st.caption("Mín: 0% | Máx: 30% (Ley 2026)")
    with cr2:
        range_int_tax = st.slider("Impuesto Integrado (%)", 0, 15, (5, 15), step=1, key=f"r_int_{sel_esc_name}")
        st.caption("Mín: 0% | Máx: 15% (Ley 2026)")
    with cr3:
        range_islr = st.slider("ISLR (%)", 0, 50, (0, 50), step=1, key=f"r_islr_{sel_esc_name}")
        st.caption("Mín: 0% | Máx: 50% (Ley 2026)")

    st.markdown("---")
    exec_gt_search = st.button("🔍 Buscar Combinaciones Óptimas", type="primary", key=f"btn_gt_{sel_esc_name}")

    gt_store_key = f"gt_df_{sel_esc_name}"
    
    # Initialize from scenario optimizacion_fiscal if available
    if gt_store_key not in st.session_state and sel_sc.get('optimizacion_fiscal'):
        df_init_gt = pd.DataFrame(sel_sc['optimizacion_fiscal'])
        def _norm_gt_col(c):
            if 'Regal' in c or 'Royalty' in c: return 'Regalía (%)'
            if 'Integrado' in c: return 'Imp. Integrado (%)'
            if 'ISLR' in c or 'Income' in c: return 'ISLR (%)'
            if 'Pre' in c: return 'VPN HPOC Pre-Tax (MMUSD)'
            if 'Post' in c: return 'VPN HPOC Post-Tax (MMUSD)'
            if 'Gov' in c or 'Take' in c: return 'Government Take (%)'
            return c
        df_init_gt.columns = [_norm_gt_col(c) for c in df_init_gt.columns]
        st.session_state[gt_store_key] = df_init_gt

    if exec_gt_search:
        with st.spinner("Realizando búsqueda ultra-rápida..."):
            dr = float(sel_sc['params'].get('discount_rate', 15.0)) / 100.0
            mr = (1 + dr) ** (1 / 12) - 1
            n_per = len(sel_sc.get('dates', []))
            dm = (1 + mr) ** np.arange(n_per)
            
            cf_b = sel_sc.get('cash_flows', {})
            gi_pv = float(np.sum(np.array(cf_b.get('gross_income', [0])) / dm))
            costs_pv = float(np.sum((np.array(cf_b.get('capex', [0])) + np.array(cf_b.get('opex', [0])) + np.array(cf_b.get('abex', [0]))) / dm))
            total_rent = gi_pv - costs_pv

            if total_rent <= 0:
                st.error("El proyecto no genera renta económica positiva en estas condiciones. No es posible calcular el Government Take.")
            else:
                step = 1 if "Fina" in precision else (2 if "Media" in precision else 5)
                r_range = np.arange(range_royalty[0], range_royalty[1] + 1, step)
                i_range = np.arange(range_int_tax[0], range_int_tax[1] + 1, step)
                s_range = np.arange(range_islr[0], range_islr[1] + 1, step)
                
                rows_gt = []
                for r_val in r_range:
                    for i_val in i_range:
                        for s_val in s_range:
                            v_roy = (r_val / 100.0) * gi_pv
                            v_iih = (i_val / 100.0) * gi_pv
                            taxable = gi_pv - v_roy - v_iih - costs_pv
                            v_islr = (s_val / 100.0) * max(0.0, taxable)
                            v_hpoc_pre = taxable
                            v_hpoc_post = taxable - v_islr
                            gt_c = ((v_roy + v_iih + v_islr) / total_rent) * 100.0
                            if abs(gt_c - target_gt) <= tolerance:
                                rows_gt.append({
                                    "Regalía (%)": r_val,
                                    "Imp. Integrado (%)": i_val,
                                    "ISLR (%)": s_val,
                                    "VPN HPOC Pre-Tax (MMUSD)": v_hpoc_pre,
                                    "VPN HPOC Post-Tax (MMUSD)": v_hpoc_post,
                                    "Government Take (%)": gt_c
                                })
                if rows_gt:
                    st.session_state[gt_store_key] = pd.DataFrame(rows_gt).sort_values("VPN HPOC Post-Tax (MMUSD)", ascending=False)
                else:
                    st.session_state[gt_store_key] = None
                    st.warning("No se encontraron combinaciones en el rango especificado. Intenta aumentar la tolerancia o ajustar el objetivo.")

    if gt_store_key in st.session_state and st.session_state[gt_store_key] is not None:
        df_gt_res = st.session_state[gt_store_key].copy()
        total_found = len(df_gt_res)
        
        st.markdown("---")
        st.subheader("📊 Dashboard de Optimización HPOC: VPN vs. Government Take")

        tol_viz_key = f"m_tol_{sel_esc_name}"
        if tol_viz_key not in st.session_state:
            st.session_state[tol_viz_key] = 1.0
        m_tol = st.session_state[tol_viz_key]

        cat_cumple = f"Cumple Meta ({target_gt-0.5:.1f} - {target_gt+0.5:.1f}%)"
        cat_prox = f"Proximidad Crítica ({target_gt-m_tol:.1f} - {target_gt-0.5:.1f}% y {target_gt+0.5:.1f} - {target_gt+m_tol:.1f}%)"

        def _get_gt_cat(gt_val):
            diff = abs(gt_val - target_gt)
            if diff <= 0.5: return cat_cumple
            elif diff <= m_tol: return cat_prox
            else: return "Resto"

        df_gt_res['Categoria'] = df_gt_res['Government Take (%)'].apply(_get_gt_cat)
        df_viz = df_gt_res[df_gt_res['Categoria'] != "Resto"].copy()
        
        num_meta = len(df_viz[df_viz['Categoria'] == cat_cumple])
        max_vpn_cumple = df_viz[df_viz['Categoria'] == cat_cumple]['VPN HPOC Post-Tax (MMUSD)'].max() if num_meta > 0 else 0
        best_vpn_overall = df_gt_res['VPN HPOC Post-Tax (MMUSD)'].max() if len(df_gt_res) > 0 else 0

        db_c1, db_c2, db_c3 = st.columns([1, 2, 1.1])
        with db_c1:
            st.markdown("<span style='font-size:11px; font-weight:bold; color:#94a3b8;'>ESCENARIOS EN META</span>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='margin-top:-6px; color:#0c1c3e;'>{num_meta} <span style='font-size:16px; font-weight:normal; color:#94a3b8;'>de {total_found}</span></h2>", unsafe_allow_html=True)
            st.progress(num_meta / total_found if total_found > 0 else 0.0)
            
            st.slider("Margen de Tolerancia Visual (%)", min_value=1.0, max_value=10.0, step=0.5, key=tol_viz_key, help="Ajusta el rango para considerar escenarios en 'Proximidad Crítica'")
            st.caption(f"Nota: {num_meta} escenarios cumplen la meta.")

            st.markdown("<span style='font-size:11px; font-weight:bold; color:#94a3b8;'>MÁXIMO VPN (CUMPLE)</span>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='margin-top:-6px; color:#059669;'>${max_vpn_cumple:,.2f}M</h2>", unsafe_allow_html=True)
            st.caption("Valor óptimo bajo restricción de GT")

            st.markdown("<span style='font-size:11px; font-weight:bold; color:#94a3b8;'>MEJOR VPN ABSOLUTO</span>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='margin-top:-6px; color:#2563eb;'>${best_vpn_overall:,.2f}M</h2>", unsafe_allow_html=True)
            st.caption("Independiente de la meta")

        with db_c2:
            if len(df_viz) > 0:
                fig_gt = px.scatter(
                    df_viz, 
                    x="Government Take (%)", 
                    y="VPN HPOC Post-Tax (MMUSD)",
                    color="Categoria",
                    color_discrete_map={cat_cumple: "#10b981", cat_prox: "#64748b"},
                    hover_data=["Regalía (%)", "Imp. Integrado (%)", "ISLR (%)"],
                    title="Análisis de Proximidad a la Meta"
                )
                fig_gt.add_vline(x=target_gt, line_dash="dash", line_color="#ef4444", annotation_text=f"META {target_gt}%")
                fig_gt.update_traces(marker=dict(size=14, opacity=0.9, line=dict(width=1, color='white')))
                fig_gt.update_layout(
                    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="left", x=0, title=""),
                    margin=dict(b=80),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(248,249,250,0.8)'
                )
                st.plotly_chart(fig_gt, use_container_width=True)
            else:
                st.info("No hay escenarios en el rango visual. Amplía la tolerancia en la búsqueda.")

        with db_c3:
            st.markdown("**Top Resultados (Visualizados)**")
            with st.container(height=450):
                if len(df_viz) == 0:
                    st.caption("No hay escenarios para mostrar.")
                else:
                    sorted_viz = df_viz.sort_values("VPN HPOC Post-Tax (MMUSD)", ascending=False)
                    for i, (_, row) in enumerate(sorted_viz.iterrows()):
                        bg_c = "#ecfdf5" if row['Categoria'] == cat_cumple else "#f8fafc"
                        bd_c = "#a7f3d0" if row['Categoria'] == cat_cumple else "#e2e8f0"
                        st.markdown(f"""
                        <div style='background-color: {bg_c}; border: 1px solid {bd_c}; border-radius: 12px; padding: 12px; margin-bottom: 10px;'>
                            <div style='display: flex; justify-content: space-between; margin-bottom: 4px;'>
                                <span style='font-size: 0.75rem; font-weight: bold; color: #64748b;'>RANK {i+1}</span>
                                <span style='font-size: 0.75rem; font-weight: bold; background-color: #e2e8f0; padding: 2px 8px; border-radius: 10px;'>GT: {row['Government Take (%)']:.2f}%</span>
                            </div>
                            <div style='font-size: 1.35rem; font-weight: 900; color: #1e293b; margin: 3px 0;'>
                                ${row['VPN HPOC Post-Tax (MMUSD)']:.2f} <span style='font-size: 0.7rem; font-weight: normal; color: #94a3b8;'>MMUSD</span>
                            </div>
                            <div style='display: flex; gap: 5px; margin-top: 6px;'>
                                <span style='font-size: 0.7rem; background-color: rgba(255,255,255,0.8); border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px;'>R: {row['Regalía (%)']:.0f}%</span>
                                <span style='font-size: 0.7rem; background-color: rgba(255,255,255,0.8); border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px;'>Ii: {row['Imp. Integrado (%)']:.0f}%</span>
                                <span style='font-size: 0.7rem; background-color: rgba(255,255,255,0.8); border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px;'>I: {row['ISLR (%)']:.0f}%</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

        with st.expander("📂 Ver Tabla de Datos Completa", expanded=False):
            st.dataframe(
                df_gt_res.drop(columns=['Categoria'], errors='ignore').head(100).style.format({
                    "Regalía (%)": "{:.0f}%",
                    "Imp. Integrado (%)": "{:.0f}%",
                    "ISLR (%)": "{:.0f}%",
                    "VPN HPOC Pre-Tax (MMUSD)": "{:.2f}",
                    "VPN HPOC Post-Tax (MMUSD)": "{:.2f}",
                    "Government Take (%)": "{:.2f}%"
                }).background_gradient(subset=["VPN HPOC Post-Tax (MMUSD)"], cmap="Greens"),
                use_container_width=True
            )
    else:
        st.info("💡 Haz clic en 'Buscar Combinaciones Óptimas' para evaluar combinaciones fiscales bajo la meta de Government Take.")


# ─── TAB 9: ANÁLISIS DE SENSIBILIDAD FISCAL (MULTIDIMENSIONAL) ───────────────
with t_sens_fiscal:
    sens_data_t9 = sel_sc.get('sensibilidad', [])
    if not sens_data_t9:
        st.info("💡 No se encontraron datos de sensibilidad en este escenario.")
    else:
        df_t9 = pd.DataFrame(sens_data_t9)
        def _norm_t9_col(c):
            if 'Precio' in c or 'Oil' in c: return 'Precio Aceite'
            if 'Regal' in c or 'Royalty' in c: return 'Regalía (%)'
            if 'VPN HPOC Post' in c: return 'VPN HPOC Post (MMUSD)'
            if 'VPN HPOC Pre' in c: return 'VPN HPOC Pre (MMUSD)'
            if 'Gov Take' in c: return 'Gov Take (%)'
            if 'MCE' in c or 'Peak' in c: return 'MCE (MMUSD)'
            if 'Payout' in c: return 'Payout (Years)'
            if 'Max Financ' in c: return 'Max Financ. (MMUSD)'
            if 'Break-even' in c or 'Punto' in c: return 'Break-even (USD/bbl)'
            if 'TIRM' in c or 'IRR' in c: return 'TIRM Post-Tax (%)'
            return c
        df_t9.columns = [_norm_t9_col(c) for c in df_t9.columns]
        df_t9 = _ensure_sens_pre_tax(df_t9, sel_sc)
        if 'Comp Take (%)' not in df_t9.columns:
            df_t9['Comp Take (%)'] = 100.0 - df_t9['Gov Take (%)']

        st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; border-bottom: 3px solid #0c1c3e; padding-bottom: 10px;">
            <div>
                <h1 style="margin:0; font-family: 'Inter', sans-serif; color: #0c1c3e; font-size: 1.8rem; font-weight:800;">ANÁLISIS DE SENSIBILIDAD FISCAL</h1>
                <p style="color: #64748b; margin-top: 4px; font-size: 0.95rem;">Evaluación Multidimensional: Precio vs. Regalías — Powered by STORM-Viewer</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        ind_map_t9 = {
            "VPN": "VPN HPOC Post (MMUSD)",
            "TIR": "TIRM Post-Tax (%)" if 'TIRM Post-Tax (%)' in df_t9.columns else "VPN HPOC Post (MMUSD)",
            "GOV. TAKE": "Gov Take (%)",
            "COMP. TAKE": "Comp Take (%)",
            "PAYBACK": "Payout (Years)",
            "MARGEN UN.": "Break-even (USD/bbl)"
        }
        avail_inds = {k: v for k, v in ind_map_t9.items() if v in df_t9.columns and df_t9[v].notnull().any()}
        
        hdr_c1, hdr_c2 = st.columns([1, 1.2])
        with hdr_c2:
            active_ind_t9 = st.segmented_control(
                "Seleccionar Indicador", 
                options=list(avail_inds.keys()), 
                default=list(avail_inds.keys())[0], 
                label_visibility="collapsed",
                key=f"t9_ind_ctrl_{sel_esc_name}"
            ) or list(avail_inds.keys())[0]
        active_col_t9 = avail_inds[active_ind_t9]

        col_side, col_curve, col_radar = st.columns([1, 2.2, 1.2])
        prices_t9 = sorted(df_t9['Precio Aceite'].unique())
        royalties_t9 = sorted(df_t9['Regalía (%)'].unique())

        with col_side:
            st.markdown("#### ⚙️ PARÁMETROS DE ENTRADA")
            mode_t9 = st.radio("Modo de Sensibilidad", ["Fijar Precio / Variar Regalía", "Fijar Regalía / Variar Precio"], key=f"t9_mode_{sel_esc_name}")
            
            if mode_t9 == "Fijar Precio / Variar Regalía":
                fixed_p = st.selectbox("Precio Crudo (USD/bl)", options=prices_t9, format_func=lambda x: f"${x:.1f}", key=f"t9_p_{sel_esc_name}")
                df_plot_t9 = df_t9[df_t9['Precio Aceite'] == fixed_p].sort_values('Regalía (%)')
                x_axis_t9 = 'Regalía (%)'
                x_lbl_t9 = "Regalía (%)"
                sel_pt_val = st.select_slider("Seleccionar Punto (%)", options=sorted(df_plot_t9[x_axis_t9].unique()), value=sorted(df_plot_t9[x_axis_t9].unique())[0], key=f"t9_pt_{sel_esc_name}")
            else:
                fixed_r = st.selectbox("Regalía (%)", options=royalties_t9, format_func=lambda x: f"{x:.0f}%", key=f"t9_r_{sel_esc_name}")
                df_plot_t9 = df_t9[df_t9['Regalía (%)'] == fixed_r].sort_values('Precio Aceite')
                x_axis_t9 = 'Precio Aceite'
                x_lbl_t9 = "Precio Aceite (USD/bbl)"
                sel_pt_val = st.select_slider("Seleccionar Punto (USD)", options=sorted(df_plot_t9[x_axis_t9].unique()), value=sorted(df_plot_t9[x_axis_t9].unique())[0], key=f"t9_pt_{sel_esc_name}")

            pt_data = df_plot_t9[df_plot_t9[x_axis_t9] == sel_pt_val].iloc[0]
            _vpn_card = f"${pt_data['VPN HPOC Post (MMUSD)']:,.1f}M"
            _tir_card = f"{pt_data['TIRM Post-Tax (%)']:.1f}%" if 'TIRM Post-Tax (%)' in pt_data and pd.notnull(pt_data['TIRM Post-Tax (%)']) else "N/A"
            _gt_card  = f"{pt_data['Gov Take (%)']:.1f}%"
            _pb_card  = f"{pt_data['Payout (Years)']:.2f} Años" if 'Payout (Years)' in pt_data and pd.notnull(pt_data['Payout (Years)']) else "—"

            st.markdown(f"""
            <div style="background-color:#0c1c3e; color:white; padding:22px; border-radius:18px; box-shadow:0 8px 24px rgba(0,0,0,0.15); font-family:Inter,sans-serif; margin-top:15px;">
                <p style="font-size:0.75rem; font-weight:700; color:#a0aec0; text-transform:uppercase; margin:0 0 4px 0; letter-spacing:1px;">INDICADORES CLAVE</p>
                <p style="font-size:2rem; font-weight:900; margin:0 0 14px 0;">{_vpn_card}</p>
                <table style="width:100%; border-collapse:collapse;">
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.12);">
                        <td style="padding:8px 0; color:#94a3b8; font-size:0.85rem;">VPN Post-Tax</td>
                        <td style="padding:8px 0; text-align:right; font-weight:700; font-size:0.95rem;">{_vpn_card}</td>
                    </tr>
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.12);">
                        <td style="padding:8px 0; color:#94a3b8; font-size:0.85rem;">TIR</td>
                        <td style="padding:8px 0; text-align:right; font-weight:700; color:#4ade80;">{_tir_card}</td>
                    </tr>
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.12);">
                        <td style="padding:8px 0; color:#94a3b8; font-size:0.85rem;">Gov. Take</td>
                        <td style="padding:8px 0; text-align:right; font-weight:700; color:#fbbf24;">{_gt_card}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0; color:#94a3b8; font-size:0.85rem;">Payback</td>
                        <td style="padding:8px 0; text-align:right; font-weight:700;">{_pb_card}</td>
                    </tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

        with col_curve:
            fig_curve = go.Figure()
            fig_curve.add_trace(go.Scatter(
                x=df_plot_t9[x_axis_t9],
                y=df_plot_t9[active_col_t9],
                mode='lines+markers',
                line=dict(color='#6366f1', width=4),
                marker=dict(size=10, color='white', line=dict(color='#6366f1', width=3)),
                fill='tozeroy',
                fillcolor='rgba(99,102,241,0.06)',
                hovertemplate=f"<b>{x_lbl_t9}:</b> %{{x}}<br><b>{active_ind_t9}:</b> %{{y:.2f}}<extra></extra>"
            ))
            fig_curve.add_trace(go.Scatter(
                x=[sel_pt_val], y=[pt_data[active_col_t9]],
                mode='markers',
                marker=dict(size=16, color='#6366f1', line=dict(color='white', width=3)),
                showlegend=False,
                hovertemplate=f"<b>Punto Seleccionado</b><br>{x_lbl_t9}: {sel_pt_val}<br>{active_ind_t9}: {pt_data[active_col_t9]:.2f}<extra></extra>"
            ))
            fig_curve.update_layout(
                title=dict(text=f"Curva: {active_ind_t9}", font=dict(size=15, color='#0c1c3e'), x=0),
                xaxis_title=x_lbl_t9, yaxis_title=active_ind_t9,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=50, b=50, l=50, r=20), height=460,
                xaxis=dict(showgrid=True, gridcolor='#f1f5f9', zeroline=False),
                yaxis=dict(showgrid=True, gridcolor='#f1f5f9', zeroline=False),
                font=dict(family='Inter, sans-serif')
            )
            st.plotly_chart(fig_curve, use_container_width=True)

        with col_radar:
            st.markdown("#### BALANCE DEL PROYECTO")
            v_vpn_r = float(pt_data['VPN HPOC Post (MMUSD)'])
            v_tir_r = float(pt_data.get('TIRM Post-Tax (%)', 15.0)) if pd.notnull(pt_data.get('TIRM Post-Tax (%)')) else 15.0
            v_gt_r  = float(pt_data['Gov Take (%)'])
            v_ct_r  = 100.0 - v_gt_r
            v_pb_r  = float(pt_data.get('Payout (Years)', 7.5)) if pd.notnull(pt_data.get('Payout (Years)')) else 7.5
            v_mg_r  = float(pt_data.get('Break-even (USD/bbl)', 50.0)) if pd.notnull(pt_data.get('Break-even (USD/bbl)')) else 50.0

            r_vals = [
                min(1.0, max(0.0, v_vpn_r / 500.0)),
                min(1.0, max(0.0, v_tir_r / 100.0)),
                v_gt_r / 100.0,
                v_ct_r / 100.0,
                max(0.05, 1.0 - (v_pb_r / 15.0)),
                max(0.05, 1.0 - (v_mg_r / 100.0))
            ]

            fig_radar_t9 = go.Figure()
            fig_radar_t9.add_trace(go.Scatterpolar(
                r=r_vals,
                theta=["VPN", "TIR", "Gov Take", "Comp Take", "Payback", "Break-even"],
                fill='toself',
                fillcolor='rgba(99,102,241,0.25)',
                line=dict(color='#6366f1', width=2),
                marker=dict(size=6, color='#6366f1')
            ))
            fig_radar_t9.update_layout(
                polar=dict(radialaxis=dict(visible=False, range=[0, 1]), angularaxis=dict(tickfont=dict(size=10, color='#64748b'))),
                showlegend=False, paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=25, b=25, l=25, r=25), height=310,
                font=dict(family='Inter, sans-serif', size=10, color='#64748b')
            )
            st.plotly_chart(fig_radar_t9, use_container_width=True)

            obs_p = pt_data.get('Precio Aceite', 60.0)
            obs_r = pt_data.get('Regalía (%)', 30.0)
            st.markdown(f"""
            <div style="background:#f8fafc; border-radius:12px; padding:14px; border-left:4px solid #6366f1; margin-top:8px;">
                <div style="font-size:0.72rem; font-weight:700; color:#64748b; margin-bottom:4px;">ℹ️ NOTA</div>
                <div style="font-size:0.85rem; color:#1e293b;">A <b>${obs_p:.1f}/bl</b>, el balance fiscal óptimo se encuentra con una regalía de <b>{obs_r:.0f}%</b>.</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        c_rent_t9, c_heat_t9 = st.columns([1, 1])

        with c_rent_t9:
            st.markdown("#### 💰 DISTRIBUCIÓN DE RENTA")
            st.caption("Participación relativa de la renta económica total generada")
            v_gt_bar = float(pt_data['Gov Take (%)'])
            v_ct_bar = 100.0 - v_gt_bar
            fig_rent_t9 = go.Figure()
            fig_rent_t9.add_trace(go.Bar(y=["Distribución"], x=[v_gt_bar], name="Estado", orientation='h', marker=dict(color='#f59e0b')))
            fig_rent_t9.add_trace(go.Bar(y=["Distribución"], x=[v_ct_bar], name="Contratista", orientation='h', marker=dict(color='#6366f1')))
            fig_rent_t9.update_layout(
                barmode='stack',
                xaxis=dict(showticklabels=False, range=[0, 100]),
                yaxis=dict(showticklabels=False), showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=40, b=20, l=20, r=20), height=180
            )
            fig_rent_t9.add_annotation(x=v_gt_bar/2, y=0, text=f"Estado<br>{v_gt_bar:.1f}%", showarrow=False, font=dict(color="white", size=13, weight="bold"))
            fig_rent_t9.add_annotation(x=v_gt_bar+v_ct_bar/2, y=0, text=f"Contratista<br>{v_ct_bar:.1f}%", showarrow=False, font=dict(color="white", size=13, weight="bold"))
            st.plotly_chart(fig_rent_t9, use_container_width=True)

        with c_heat_t9:
            st.markdown("#### 🌡️ MAPA DE INTENSIDAD VPN")
            st.caption("Evaluación global de sensibilidad — Regalía vs. Precio")
            try:
                pivot_heat_t9 = df_t9.pivot(index='Regalía (%)', columns='Precio Aceite', values='VPN HPOC Post (MMUSD)')
                fig_heat_t9 = px.imshow(
                    pivot_heat_t9,
                    labels=dict(x="Precio Aceite (USD/bbl)", y="Regalía (%)", color="VPN (MMUSD)"),
                    color_continuous_scale='Blues', aspect='auto'
                )
                fig_heat_t9.update_layout(margin=dict(t=10, b=40, l=10, r=10), height=200, coloraxis_colorbar=dict(thickness=12, len=0.8))
                st.plotly_chart(fig_heat_t9, use_container_width=True)
            except Exception:
                st.info("El mapa de calor requiere una matriz completa de precio × regalía.")


# ─── TAB 10: CAJA AUTOFINANCIABLE & EXPOSICIÓN ───────────────────────────────
with t_autofin:
    st.header("📦 Modelo de Caja Autofinanciable y Métricas de Exposición (MCO / TIRM)")
    st.markdown(
        "Este análisis evalúa el desempeño financiero del proyecto asumiendo que el "
        "Contratista dispone de un **Capital Inicial** ($C_0$) para cubrir los egresos planificados y "
        "asegurar las operaciones, de modo que el proyecto posteriormente se **autofinancia** "
        "a partir de los ingresos generados por la venta de los hidrocarburos."
    )

    autofin_cases, cap_cases = _get_autofin_cases(sel_sc)

    if not autofin_cases:
        st.info("💡 Este escenario no contiene datos de flujo de caja post-impuesto suficientes para simular la caja autofinanciable.")
    else:
        case_options = [
            f"Caso 1: {cap_cases[0]:.1f} MMUSD",
            f"Caso 2 (Base): {cap_cases[1]:.1f} MMUSD",
            f"Caso 3: {cap_cases[2]:.1f} MMUSD"
        ]
        
        selected_case_lbl = st.segmented_control(
            "Seleccionar Caso de Inversión Inicial:",
            options=case_options,
            default=case_options[1],
            key=f"sel_cap_case_{sel_esc_name}"
        ) or case_options[1]
        
        case_idx = case_options.index(selected_case_lbl)
        case_key = f"caso_{case_idx + 1}"
        case_data = autofin_cases[case_key]
        cap_selected = float(case_data['capital'])

        mco_val = float(np.mean(case_data['mco_autofin']))
        min_pool_val = float(np.mean(case_data['min_pool_months']))
        payback_val = float(np.mean(case_data['payback_months_autofin']))
        tirm_inv = case_data['tirm_investor']
        moic_inv = float(np.mean(case_data['moic_investor']))
        npv_inv = float(np.mean(case_data['npv_investor']))

        st.markdown(f"### 📊 Indicadores Clave del Inversionista — Caso Evaluado: {cap_selected:.1f} MMUSD")
        
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        card_autofin_tpl = """
        <div style="background: white; padding: 22px; border-radius: 12px; box-shadow: 0 4px 18px rgba(0,0,0,0.06); border-top: 4px solid {color}; text-align: center; height: 100%;">
            <div style="color: #718096; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;">{title}</div>
            <div style="color: #2d3748; font-size: 1.8rem; font-weight: 800; margin-bottom: 4px;">{value}</div>
            <div style="color: #a0aec0; font-size: 0.72rem; font-style: italic;">{subtitle}</div>
        </div>
        """
        with col_k1:
            st.markdown(card_autofin_tpl.format(title="Capital Inicial (C₀)", value=f"{cap_selected:.1f} MMUSD", subtitle="Capital aportado al inicio", color="#4a5568"), unsafe_allow_html=True)
        with col_k2:
            st.markdown(card_autofin_tpl.format(title="Exposición Máxima (MCO)", value=f"{mco_val:.2f} MMUSD", subtitle="Financiamiento total requerido", color="#dc2626"), unsafe_allow_html=True)
        with col_k3:
            st.markdown(card_autofin_tpl.format(title="Mes de Mínima Caja", value=f"Mes {int(round(min_pool_val)) + 1}", subtitle="Punto más bajo del balance", color="#d97706"), unsafe_allow_html=True)
        with col_k4:
            pb_str = f"Mes {int(round(payback_val))}" if payback_val < len(dates) else "N/A"
            st.markdown(card_autofin_tpl.format(title="Mes Autofinanciamiento", value=pb_str, subtitle="Recuperación total de inversión", color="#16a34a"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col_k5, col_k6, col_k7 = st.columns(3)
        with col_k5:
            tirm_str_inv = f"{tirm_inv:.2f}%" if tirm_inv is not None and np.isfinite(tirm_inv) else "N/A"
            st.markdown(card_autofin_tpl.format(title="TIRM del Inversionista", value=tirm_str_inv, subtitle="Tasa Interna Retorno Modificada", color="#00d4ff"), unsafe_allow_html=True)
        with col_k6:
            st.markdown(card_autofin_tpl.format(title="MOIC Inversionista", value=f"{moic_inv:.2f}x", subtitle="Múltiplo de capital retornado", color="#9C27B0"), unsafe_allow_html=True)
        with col_k7:
            st.markdown(card_autofin_tpl.format(title="VPN Inversionista", value=f"{npv_inv:.2f} MMUSD", subtitle=f"Valor Presente Neto (a {sel_sc['params'].get('discount_rate', 15.0):.1f}%)", color="#4CAF50"), unsafe_allow_html=True)

        st.markdown("---")
        # ─── CURVAS J COMPARATIVAS ───
        st.subheader(f"📈 Curvas en J y Balance de Caja ({selected_case_lbl})")
        st.markdown(
            "La siguiente gráfica muestra el **Balance de Caja** acumulado en el fondo del proyecto "
            "(recursos líquidos disponibles que inician en $C_0$) y el **Flujo de Caja Acumulado del Inversionista** "
            "(entradas y salidas netas del socio inversor)."
        )

        pool_arr = np.array(case_data['cash_pool_autofin'])
        inv_cum_arr = np.array(case_data['cum_cf_investor_post_tax'])
        
        if pool_arr.ndim == 2 and pool_arr.shape[0] > 1:
            pool_p10, pool_p50, pool_p90 = np.percentile(pool_arr, [10, 50, 90], axis=0)
            inv_p10, inv_p50, inv_p90 = np.percentile(inv_cum_arr, [10, 50, 90], axis=0)
        else:
            pool_p50 = pool_arr[0] if pool_arr.ndim == 2 else pool_arr
            pool_p10 = pool_p50 * 0.9
            pool_p90 = pool_p50 * 1.1
            inv_p50 = inv_cum_arr[0] if inv_cum_arr.ndim == 2 else inv_cum_arr
            inv_p10 = inv_p50 * 0.9
            inv_p90 = inv_p50 * 1.1

        start_d = pd.Timestamp(dates[0]) if dates else pd.Timestamp('2026-01-01')
        m0_d = start_d - pd.DateOffset(months=1)
        dates_with_m0 = [m0_d] + list(dates)

        fig_j = go.Figure()
        # Project Cash Pool (Y1)
        fig_j.add_trace(go.Scatter(x=dates, y=pool_p50, name="Balance de Caja (P50)", line=dict(color="#d97706", width=3), legendgroup="pool"))
        fig_j.add_trace(go.Scatter(x=dates, y=pool_p10, name="Balance P10", line=dict(color="#d97706", width=1), opacity=0.2, legendgroup="pool", showlegend=False))
        fig_j.add_trace(go.Scatter(x=dates, y=pool_p90, name="Balance P90", line=dict(color="#d97706", width=1), fill='tonexty', fillcolor='rgba(217, 119, 6, 0.1)', opacity=0.2, legendgroup="pool", showlegend=False))

        # Investor Cumulative Flow (Y2)
        fig_j.add_trace(go.Scatter(x=dates_with_m0, y=inv_p50, name="Flujo Acumulado Inversionista (P50)", line=dict(color="#2196F3", width=3, dash='dash'), yaxis="y2", legendgroup="inv"))
        fig_j.add_trace(go.Scatter(x=dates_with_m0, y=inv_p10, line=dict(color="#2196F3", width=1, dash='dash'), opacity=0.2, yaxis="y2", legendgroup="inv", showlegend=False))
        fig_j.add_trace(go.Scatter(x=dates_with_m0, y=inv_p90, line=dict(color="#2196F3", width=1, dash='dash'), fill='tonexty', fillcolor='rgba(33, 150, 243, 0.08)', opacity=0.2, yaxis="y2", legendgroup="inv", showlegend=False))

        fig_j.add_hline(y=0.0, line_dash="dot", line_color="rgba(0,0,0,0.3)", yref="y2")
        fig_j.add_hline(y=cap_selected, line_dash="dashdot", line_color="rgba(217, 119, 6, 0.5)", yref="y", annotation_text=f"Capital Inicial: {cap_selected:.1f} MMUSD", annotation_position="top left")

        fig_j.update_layout(
            title=dict(text=f"Curva en J y Pool de Caja del Proyecto ({selected_case_lbl})", font=dict(family='Inter, sans-serif', size=16, color="#2d3748")),
            xaxis=dict(title="Fecha", showgrid=True, gridcolor='rgba(0,0,0,0.05)'),
            yaxis=dict(title="Balance del Fondo de Caja (MMUSD)", showgrid=True, gridcolor='rgba(0,0,0,0.05)'),
            yaxis2=dict(title="Flujo Acumulado Inversionista (MMUSD)", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(t=50, b=90, l=50, r=50), height=460, hovermode="x unified"
        )
        st.plotly_chart(fig_j, use_container_width=True)

        st.markdown("---")
        # ─── COMPARATIVE TABLE ───
        st.subheader("⚖️ Comparación de Escenarios: Modelo Estándar vs. Casos de Inversión")
        st.markdown(
            "La siguiente tabla compara las métricas clave de rentabilidad y exposición "
            "bajo el modelo estándar del Contratista (sin capital inicial retenido) y los "
            "tres casos evaluados de **Capital Inicial (MMUSD)**."
        )

        c1_d = autofin_cases['caso_1']
        c2_d = autofin_cases['caso_2']
        c3_d = autofin_cases['caso_3']

        std_mco = ind_mean(sel_sc, 'max_financing_mm')
        std_payout = ind_mean(sel_sc, 'payout_years') * 12.0
        std_tirm_val = sel_sc['indicators'].get('irr_post_annual')
        std_tirm_str = f"{float(std_tirm_val):.2f}%" if std_tirm_val is not None and np.isfinite(float(std_tirm_val)) else "N/A"
        std_moic = ind_mean(sel_sc, 'moic')
        std_npv = ind_mean(sel_sc, 'npv_hpoc_post')

        c1_tirm = f"{c1_d['tirm_investor']:.2f}%" if c1_d['tirm_investor'] is not None and np.isfinite(c1_d['tirm_investor']) else "N/A"
        c2_tirm = f"{c2_d['tirm_investor']:.2f}%" if c2_d['tirm_investor'] is not None and np.isfinite(c2_d['tirm_investor']) else "N/A"
        c3_tirm = f"{c3_d['tirm_investor']:.2f}%" if c3_d['tirm_investor'] is not None and np.isfinite(c3_d['tirm_investor']) else "N/A"

        c1_pay = f"Mes {int(round(np.mean(c1_d['payback_months_autofin'])))}" if np.mean(c1_d['payback_months_autofin']) < len(dates) else "N/A"
        c2_pay = f"Mes {int(round(np.mean(c2_d['payback_months_autofin'])))}" if np.mean(c2_d['payback_months_autofin']) < len(dates) else "N/A"
        c3_pay = f"Mes {int(round(np.mean(c3_d['payback_months_autofin'])))}" if np.mean(c3_d['payback_months_autofin']) < len(dates) else "N/A"
        std_pay = f"Mes {int(round(std_payout))}" if std_payout < len(dates) else "N/A"

        comp_matrix_rows = [
            {
                "Métrica": "Capital Inicial Aportado (C₀)",
                "Modelo Estándar (Sin Buffer)": "0.0 MMUSD",
                "Caso 1": f"{float(cap_cases[0]):.1f} MMUSD",
                "Caso 2 (Base)": f"{float(cap_cases[1]):.1f} MMUSD",
                "Caso 3": f"{float(cap_cases[2]):.1f} MMUSD",
            },
            {
                "Métrica": "Máxima Exposición de Caja (MCO)",
                "Modelo Estándar (Sin Buffer)": f"{std_mco:.2f} MMUSD",
                "Caso 1": f"{np.mean(c1_d['mco_autofin']):.2f} MMUSD",
                "Caso 2 (Base)": f"{np.mean(c2_d['mco_autofin']):.2f} MMUSD",
                "Caso 3": f"{np.mean(c3_d['mco_autofin']):.2f} MMUSD",
            },
            {
                "Métrica": "Mes de Mínima Caja",
                "Modelo Estándar (Sin Buffer)": "Mes 1",
                "Caso 1": f"Mes {int(round(np.mean(c1_d['min_pool_months']))) + 1}",
                "Caso 2 (Base)": f"Mes {int(round(np.mean(c2_d['min_pool_months']))) + 1}",
                "Caso 3": f"Mes {int(round(np.mean(c3_d['min_pool_months']))) + 1}",
            },
            {
                "Métrica": "Mes de Autofinanciamiento / Retorno",
                "Modelo Estándar (Sin Buffer)": std_pay,
                "Caso 1": c1_pay,
                "Caso 2 (Base)": c2_pay,
                "Caso 3": c3_pay,
            },
            {
                "Métrica": "Tasa Interna de Retorno (TIRM)",
                "Modelo Estándar (Sin Buffer)": std_tirm_str,
                "Caso 1": c1_tirm,
                "Caso 2 (Base)": c2_tirm,
                "Caso 3": c3_tirm,
            },
            {
                "Métrica": "Múltiplo de Capital (MOIC)",
                "Modelo Estándar (Sin Buffer)": f"{std_moic:.2f}x",
                "Caso 1": f"{np.mean(c1_d['moic_investor']):.2f}x",
                "Caso 2 (Base)": f"{np.mean(c2_d['moic_investor']):.2f}x",
                "Caso 3": f"{np.mean(c3_d['moic_investor']):.2f}x",
            },
            {
                "Métrica": "Valor Presente Neto (VPN MMUSD)",
                "Modelo Estándar (Sin Buffer)": f"${std_npv:,.2f}M",
                "Caso 1": f"${np.mean(c1_d['npv_investor']):,.2f}M",
                "Caso 2 (Base)": f"${np.mean(c2_d['npv_investor']):,.2f}M",
                "Caso 3": f"${np.mean(c3_d['npv_investor']):,.2f}M",
            },
        ]
        st.dataframe(pd.DataFrame(comp_matrix_rows).set_index("Métrica"), use_container_width=True)








