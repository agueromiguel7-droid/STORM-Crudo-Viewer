import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import json
import glob
import os
import textwrap

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
@st.cache_data
def load_scenarios(cache_key: str):
    """Load all scenario JSON files. cache_key changes when files are modified on disk."""
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
    st.session_state['_sel_scenario'] = scenario_names[0]

# Analysis Premises button
if st.sidebar.button(NAV_PREMISES, use_container_width=True,
                     type="primary" if st.session_state['nav_page'] == NAV_PREMISES else "secondary"):
    st.session_state['nav_page'] = NAV_PREMISES
    st.rerun()

st.sidebar.markdown("<hr style='border:none; border-top:1px solid #e2e8f0; margin:10px 0;'>", unsafe_allow_html=True)
st.sidebar.markdown("<h3 style='color: #718096; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;'>SCENARIO</h3>", unsafe_allow_html=True)

# on_change callback: called ONLY when user clicks a different scenario
def _on_scenario_change():
    st.session_state['nav_page'] = st.session_state['_sel_scenario']

# Scenario radio — backed by session state key, on_change fires only on real user interaction
# Note: do NOT pass index= when using key=, as session_state is the single source of truth
sel_esc_name = st.sidebar.radio(
    "Select Scenario", scenario_names,
    key='_sel_scenario',
    on_change=_on_scenario_change,
    label_visibility="collapsed"
)

sel_sc = next(s for s in scenarios if s['params'].get('esc_name', s['_filename']) == sel_esc_name)
sel_color = sel_sc['_color']

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

if st.session_state['nav_page'] != NAV_PREMISES:
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

# When a scenario is selected via radio, sync nav_page
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

def plot_dual(dates, rate_data, cum_data, res_dict, title, y1_lbl, y2_lbl, color):
    r10, r50, r90 = np.percentile(rate_data, [10, 50, 90], axis=0)
    c10, c50, c90 = np.percentile(cum_data,  [10, 50, 90], axis=0)
        
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=r10, name='Rate P10', line=dict(color=color, width=1), opacity=0.35))
    fig.add_trace(go.Scatter(x=dates, y=r90, name='Rate P90', line=dict(color=color, width=1), fill='tonexty', fillcolor=f'rgba(0,128,0,0.15)' if 'green' in color else 'rgba(214,39,40,0.15)', opacity=0.35))
    fig.add_trace(go.Scatter(x=dates, y=r50, name='Rate P50', line=dict(color=color, width=3)))
    
    fig.add_trace(go.Scatter(x=dates, y=c10, name='Cum P10', yaxis='y2', line=dict(color=color, width=1, dash='dot'), opacity=0.5))
    fig.add_trace(go.Scatter(x=dates, y=c50, name='Cum P50', yaxis='y2', line=dict(color=color, width=2, dash='dot')))
    fig.add_trace(go.Scatter(x=dates, y=c90, name='Cum P90', yaxis='y2', line=dict(color=color, width=1, dash='dot'), opacity=0.5))
    
    dash_colors = ['#1a1a2e', '#4a4e69', '#9a8c98']
    for i, (nm, val) in enumerate(res_dict.items()):
        fig.add_trace(go.Scatter(x=dates, y=[val]*len(dates), name=f"Res {nm}", yaxis='y2', line=dict(color=dash_colors[i], width=1.5, dash='dashdot')))
    fig.update_layout(title=dict(text=title, font=dict(size=20, color=color), y=0.98, x=0, xanchor='left'),
        xaxis_title='Date', yaxis=dict(title=y1_lbl, showgrid=True, gridcolor='rgba(0,0,0,0.05)'),
        yaxis2=dict(title=y2_lbl, overlaying='y', side='right', showgrid=False),
        legend=dict(orientation='h', yanchor='top', y=-0.2, xanchor='center', x=0.5, font=dict(size=10)),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=100, l=50, r=50, b=100), hovermode='x unified')
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

# ─── SECTION 2: TABS ─────────────────────────────────────────────────────────
st.markdown(f"### 🔍 Detailed Inspection: {sel_esc_name}")
t_bubble, t_det1, t_det2, t_det3, t_det4, t_det5, t_det6a, t_det6b, t_det7 = st.tabs([
    "📊 KPI Analysis", "🏗️ Fiscal Waterfall", "🛢️ Forecasts", "💸 Expenditures", 
    "📈 NPV Distributions", "💼 Cash Flow", "🎯 Corner Solutions 1", "🎯 Corner Solutions 2",
    "⚖️ Fiscal Optimization"
])

# Helpers for aggregations
dates = sel_sc.get('dates', [])
cf = sel_sc.get('cash_flows', {})
ind_det = sel_sc.get('indicators', {})

def nom_total(sc, key):
    arr = sc['cash_flows'].get(key, [[0.0]])
    return float(np.mean(np.sum(arr, axis=1)))

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
    st.subheader("Production Forecasts")
    r1, r2 = st.columns(2)
    prod_sel = sel_sc.get('production', {})
    with r1:
        st.plotly_chart(plot_dual(
            dates, np.array(prod_sel.get('Qo', [])), np.array(prod_sel.get('NP', [])),
            sel_sc.get('reserves_oil', {}), "Oil Production Forecast", "Rate (bpd)", "Cumulative (MMbbls)", "green"
        ), use_container_width=True)
    with r2:
        st.plotly_chart(plot_dual(
            dates, np.array(prod_sel.get('Qg', [])), np.array(prod_sel.get('GP', [])),
            sel_sc.get('reserves_gas', {}), "Gas Production Forecast", "Rate (Mcfd)", "Cumulative (Bcf)", "#d62728"
        ), use_container_width=True)

with t_det3:
    st.subheader("Expected Monthly Expenditures")
    capex_m = np.mean(cf.get('capex', []), axis=0) if len(cf.get('capex', [])) else []
    opex_m  = np.mean(cf.get('opex', []), axis=0) if len(cf.get('opex', [])) else []
    abex_m  = np.mean(cf.get('abex', []), axis=0) if len(cf.get('abex', [])) else []
    
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

with t_det4:
    st.subheader("Net Present Value Distributions (MMUSD)")
    nom_pre   = float(np.mean(np.sum(cf.get('cf_pre_tax', [[0]]),   axis=1)))
    nom_post  = float(np.mean(np.sum(cf.get('cf_post_tax', [[0]]),  axis=1)))
    nom_state = float(np.mean(np.sum(cf.get('state_income', [[0]]), axis=1)))
    nom_roy   = float(np.mean(np.sum(cf.get('royalty', [[0]]),      axis=1)))

    dc1, dc2 = st.columns(2)
    with dc1:
        st.plotly_chart(hist_plot(ind_det.get('npv_hpoc_pre', []),  "NPV Pre-Tax Contractor", '#1f77b4', nom_val=nom_pre),   use_container_width=True)
        st.plotly_chart(hist_plot(ind_det.get('npv_state', []),     "NPV Total State Take",   '#7B2FBE', nom_val=nom_state), use_container_width=True)
    with dc2:
        st.plotly_chart(hist_plot(ind_det.get('npv_hpoc_post', []), "NPV Post-Tax Contractor", '#17becf', nom_val=nom_post),  use_container_width=True)
        st.plotly_chart(hist_plot(ind_det.get('npv_royalty', []),   "NPV Royalties",           '#2ca02c', nom_val=nom_roy),   use_container_width=True)

with t_det5:
    st.subheader("Expected Cash Flow Analysis")
    inc_m  = np.mean(cf.get('gross_income', []), axis=0) if len(cf.get('gross_income', [])) else []
    if len(inc_m) > 0:
        cost_m = np.mean(np.array(cf['capex']) + np.array(cf['opex']) + np.array(cf['abex']), axis=0)
        roy_m  = np.mean(cf.get('royalty', []), axis=0)
        int_m  = np.mean(cf.get('int_tax', []), axis=0)
        islr_m = np.mean(cf.get('islr', []), axis=0)
        net_m  = np.mean(cf.get('cf_post_tax', []), axis=0)

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

with t_det6a:
    _oil_p  = sel_sc.get('params', {}).get('oil_price', '—')
    _gas_p  = sel_sc.get('params', {}).get('gas_price', '—')
    st.markdown(
        f"<div style='display:flex; align-items:baseline; gap:24px; flex-wrap:wrap; margin-bottom:8px;'>"
        f"<span style='font-size:1.35rem; font-weight:800; color:#0c1c3e;'>Economic Indicators Summary</span>"
        f"<span style='font-size:0.88rem; color:#64748b; font-weight:600;'>"
        f"Oil Price: <span style='color:#0c1c3e;'>${_oil_p:.2f} USD/bl</span>"
        f"&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"Gas Price: <span style='color:#0c1c3e;'>${_gas_p:.2f} USD/mcf</span>"
        f"</span></div>",
        unsafe_allow_html=True
    )
    df_sum = pd.DataFrame({
        "PV Royalties (MMUSD)":         safe_agg(ind_det.get('npv_royalty', [0])),
        "PV Integrated Tax (MMUSD)":    safe_agg(ind_det.get('npv_int_tax', [0])),
        "PV Income Tax (ISLR) (MMUSD)": safe_agg(ind_det.get('npv_islr', [0])),
        "PV Total State Take (MMUSD)":  safe_agg(ind_det.get('npv_state', [0])),
        "NPV Contractor Pre-Tax (MMUSD)": safe_agg(ind_det.get('npv_hpoc_pre', [0])),
        "NPV Contractor Post-Tax (MMUSD)":safe_agg(ind_det.get('npv_hpoc_post', [0])),
        "Peak Investment (MCE) (MMUSD)": safe_agg(ind_det.get('mce_mm', [0])),
        "Payout Time (Years)":           safe_agg(ind_det.get('payout_years', [0])),
        "MOIC (Multiple)":               safe_agg(ind_det.get('moic', [0])),
        "Break-even (USD/bbl)":          safe_agg(ind_det.get('breakeven_price', [0])),
        "Maximum Contractor Financing Requirement (MMUSD)": safe_agg(ind_det.get('max_financing_mm', [0])),
        "Government Take (%)":           safe_agg(ind_det.get('npv_gov_take', [0])),
    }).T
    
    # Estructura de grupos e indicadores para el HTML
    groups = [
        ("Present Value (PV) Indicators", [
            "PV Royalties (MMUSD)", "PV Integrated Tax (MMUSD)", 
            "PV Income Tax (ISLR) (MMUSD)", "PV Total State Take (MMUSD)"
        ]),
        ("NPV HPOC (High Performance Operation Consortia Profitability)", [
            "NPV Contractor Pre-Tax (MMUSD)", "NPV Contractor Post-Tax (MMUSD)"
        ]),
        ("Operational Efficiency and Capital Recovery", [
            "Peak Investment (MCE) (MMUSD)", "Payout Time (Years)", 
            "MOIC (Multiple)", "Break-even (USD/bbl)", 
            "Maximum Contractor Financing Requirement (MMUSD)"
        ]),
        ("International Competitiveness Measure", [
            "Government Take (%)"
        ])
    ]
    
    # Generación de tabla HTML con celdas combinadas (rowspan)
    html_table = """
    <style>
        .custom-table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 13px;
            color: #334155;
            background-color: white;
            border-radius: 4px;
        }
        .custom-table th {
            background-color: #f8fafc;
            color: #475569;
            font-weight: 600;
            padding: 10px;
            border: 1px solid #e2e8f0;
            text-align: center;
        }
        .custom-table td {
            padding: 8px 12px;
            border: 1px solid #e2e8f0;
        }
        .group-header {
            background-color: #ffffff;
            font-weight: bold;
            color: #1e293b;
            vertical-align: middle;
            text-align: left;
            width: 240px;
        }
        .indicator-name {
            background-color: #fcfcfc;
        }
        .val-cell {
            text-align: right;
            font-family: 'Courier New', Courier, monospace;
        }
        .custom-table tr:hover {
            background-color: #f1f5f9;
        }
    </style>
    <table class="custom-table">
        <thead>
            <tr>
                <th>Classification</th>
                <th>Indicator</th>
                <th>Mean</th>
                <th>Std Dev</th>
                <th>Min</th>
                <th>P10</th>
                <th>P50</th>
                <th>P90</th>
                <th>Max</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for cat_name, ind_list in groups:
        for i, ind_name in enumerate(ind_list):
            html_table += "<tr>"
            if i == 0:
                html_table += f'<td class="group-header" rowspan="{len(ind_list)}">{cat_name}</td>'
            
            # Obtener valores de la fila
            if ind_name in df_sum.index:
                vals = df_sum.loc[ind_name]
                html_table += f'<td class="indicator-name">{ind_name}</td>'
                for val in vals:
                    html_table += f'<td class="val-cell">{val:,.2f}</td>'
            html_table += "</tr>"
            
    html_table += "</tbody></table>"
    st.markdown(html_table, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    c_irr1, c_irr2 = st.columns(2)
    with c_irr1: st.metric("IRR Pre-Tax (% Annual)",  f"{ind_det.get('irr_pre_annual', 0.0):.2f}%")
    with c_irr2: st.metric("IRR Post-Tax (% Annual)", f"{ind_det.get('irr_post_annual', 0.0):.2f}%")

    # ── CORNER SOLUTIONS 1: Price-filtered unified table ──────────────────────
    st.markdown("---")
    st.subheader("Corner Solutions 1: Indicators by Oil Price")
    st.markdown("Select an oil price to view all key indicators across each evaluated Royalty rate (%)")
    
    sens_data_cs1 = sel_sc.get('sensibilidad', [])
    if sens_data_cs1:
        df_cs1 = pd.DataFrame(sens_data_cs1)
        
        def rename_col_cs1(col):
            if 'Precio' in col or 'Oil' in col: return 'Oil Price'
            if 'Regal' in col or 'Royalty' in col: return 'Royalty (%)'
            if 'VPN HPOC Post' in col: return 'NPV Contractor Post-Tax (MMUSD)'
            if 'Gov Take' in col: return 'Government Take (%)'
            if 'MCE' in col or 'Peak' in col: return 'Peak Inv. (MCE) (MMUSD)'
            if 'Payout' in col: return 'Payout Time (Years)'
            if 'Max Financ' in col: return 'Max Financing Req. (MMUSD)'
            if 'Break-even' in col or 'Punto' in col: return 'Break-even (USD/bbl)'
            return col
        
        df_cs1.columns = [rename_col_cs1(c) for c in df_cs1.columns]
        
        available_prices = sorted(df_cs1['Oil Price'].unique())
        selected_price = st.selectbox(
            "🛢️ Select Oil Price (USD/bbl)",
            options=available_prices,
            format_func=lambda x: f"${x:.1f} / bbl",
            key="cs1_price_selector"
        )
        
        df_filtered = df_cs1[df_cs1['Oil Price'] == selected_price].copy()
        royalty_cols = sorted(df_filtered['Royalty (%)'].unique())
        
        # Indicators and their classifications
        cs1_groups = [
            ("NPV HPOC (High Performance\nOperation Consortia Profitability)", [
                ("NPV Contractor Post-Tax (MMUSD)", "NPV Contractor Post-Tax (MMUSD)")
            ]),
            ("Operational Efficiency and\nCapital Recovery", [
                ("Max Financing Req. (MMUSD)",   "Max Financing Req. (MMUSD)"),
                ("Peak Investment (MCE) (MMUSD)", "Peak Inv. (MCE) (MMUSD)"),
                ("Break-even (USD/bbl)",           "Break-even (USD/bbl)"),
                ("Payout Time (Years)",             "Payout Time (Years)"),
            ]),
            ("International Competitiveness\nMeasure", [
                ("Government Take (%)", "Government Take (%)")
            ]),
        ]
        
        # Build lookup: indicator_col -> {royalty: value}
        lookup = {}
        for _, row in df_filtered.iterrows():
            r = row['Royalty (%)']
            for ind_label, ind_col in [(t[0], t[1]) for grp, inds in cs1_groups for t in inds]:
                if ind_col not in lookup:
                    lookup[ind_col] = {}
                if ind_col in row:
                    lookup[ind_col][r] = row[ind_col]
        
        # Color maps per indicator (for gradient)
        cmap_cfg = {
            "NPV Contractor Post-Tax (MMUSD)": ("Blues", False),
            "Max Financing Req. (MMUSD)":      ("Oranges", False),
            "Peak Inv. (MCE) (MMUSD)":         ("YlOrRd_r", False),
            "Break-even (USD/bbl)":             ("YlOrRd", False),
            "Payout Time (Years)":              ("YlGn_r", False),
            "Government Take (%)": ("Reds", False),
        }
        
        # Royalty columns header
        r_col_headers = "".join([f"<th style='text-align:center; min-width:75px;'>{r:.0f}%</th>" for r in royalty_cols])
        
        cs1_html = textwrap.dedent(f"""
            <style>
                .cs1-table {{ width:100%; border-collapse:collapse; font-family:'Segoe UI',sans-serif; font-size:12.5px; color:#334155; }}
                .cs1-table th {{ background:#f8fafc; color:#475569; font-weight:600; padding:9px 10px; border:1px solid #e2e8f0; }}
                .cs1-table td {{ padding:7px 10px; border:1px solid #e2e8f0; }}
                .cs1-group {{ background:#fff; font-weight:700; color:#1e293b; vertical-align:middle; width:200px; line-height:1.4; }}
                .cs1-ind {{ background:#fcfcfc; }}
                .cs1-val {{ text-align:right; font-family:'Courier New',monospace; font-size:12px; }}
                .cs1-table tr:hover td {{ background:#f1f5f9; }}
            </style>
            <table class="cs1-table">
            <thead><tr>
                <th>Classification</th>
                <th>Indicator</th>
                {r_col_headers}
            </tr></thead>
            <tbody>
        """).strip()
        
        for cat_name, ind_list in cs1_groups:
            for i, (ind_label, ind_col) in enumerate(ind_list):
                cs1_html += "<tr>"
                if i == 0:
                    cs1_html += f'<td class="cs1-group" rowspan="{len(ind_list)}" style="white-space:pre-line;">{cat_name}</td>'
                cs1_html += f'<td class="cs1-ind">{ind_label}</td>'
                for r in royalty_cols:
                    val = lookup.get(ind_col, {}).get(r, float('nan'))
                    fmt = f"{val:,.2f}" if not pd.isna(val) else "—"
                    cs1_html += f'<td class="cs1-val">{fmt}</td>'
                cs1_html += "</tr>"
        
        cs1_html += "</tbody></table>"
        st.markdown(cs1_html, unsafe_allow_html=True)
    else:
        st.warning("⚠️ No sensitivity data found for Corner Solutions 1.")

with t_det6b:
    st.subheader("Corner Solutions 2: Royalties vs Oil Price")
    sens_data = sel_sc.get('sensibilidad', [])
    if sens_data:
        df_s = pd.DataFrame(sens_data)
        def rename_col(col):
            if 'Precio' in col or 'Oil' in col: return 'Oil Price'
            if 'Regal' in col or 'Royalty' in col: return 'Royalty (%)'
            if 'VPN HPOC Post' in col: return 'NPV Contractor Post-Tax (MMUSD)'
            if 'Gov Take' in col: return 'Government Take (%)'
            if 'MCE' in col or 'Peak' in col: return 'Peak Inv. (MCE) (MMUSD)'
            if 'Payout' in col: return 'Payout Time (Years)'
            if 'Max Financ' in col: return 'Max Financing Req. (MMUSD)'
            if 'Break-even' in col or 'Punto' in col: return 'Break-even (USD/bbl)'
            return col
            
        df_s.columns = [rename_col(c) for c in df_s.columns]

        pivot_h = df_s.pivot(index='Royalty (%)', columns='Oil Price', values='NPV Contractor Post-Tax (MMUSD)')
        pivot_g = df_s.pivot(index='Royalty (%)', columns='Oil Price', values='Government Take (%)')
        pivot_m = df_s.pivot(index='Royalty (%)', columns='Oil Price', values='Peak Inv. (MCE) (MMUSD)')
        pivot_p = df_s.pivot(index='Royalty (%)', columns='Oil Price', values='Payout Time (Years)')
        pivot_f = df_s.pivot(index='Royalty (%)', columns='Oil Price', values='Max Financing Req. (MMUSD)')
        pivot_b = df_s.pivot(index='Royalty (%)', columns='Oil Price', values='Break-even (USD/bbl)')

        r1_c1, r1_c2, r1_c3 = st.columns(3)
        with r1_c1:
            st.markdown("#### NPV Contractor Post-Tax (MMUSD)")
            st.dataframe(pivot_h.style.format("{:.1f}").background_gradient(cmap='Blues'), use_container_width=True)
        with r1_c2:
            st.markdown("#### Max Financing Req. (MMUSD)")
            st.dataframe(pivot_f.style.format("{:.1f}").background_gradient(cmap='Oranges'), use_container_width=True)
        with r1_c3:
            st.markdown("#### Peak Investment (MCE) (MMUSD)")
            st.dataframe(pivot_m.style.format("{:.1f}").background_gradient(cmap='YlOrRd_r'), use_container_width=True)

        r2_c1, r2_c2, r2_c3 = st.columns(3)
        with r2_c1:
            st.markdown("#### Government Take (%)")
            st.dataframe(pivot_g.style.format("{:.2f}%").background_gradient(cmap='Reds'), use_container_width=True)
        with r2_c2:
            st.markdown("#### Break-even (USD/bbl)")
            st.dataframe(pivot_b.style.format("{:.2f}").background_gradient(cmap='YlOrRd_r'), use_container_width=True)
        with r2_c3:
            st.markdown("#### Payout Time (Years)")
            st.dataframe(pivot_p.style.format("{:.2f}").background_gradient(cmap='YlGn_r'), use_container_width=True)
    else:
        st.warning("⚠️ No pre-calculated sensitivity data found in this scenario file.")

    # ── Fiscal Sensitivity Analysis (interactive) ─────────────────────────────
    st.markdown("---")
    st.markdown("""
    <div style="border-bottom: 3px solid #0c1c3e; padding-bottom: 10px; margin-bottom: 20px;">
        <h2 style="margin:0; font-family:'Segoe UI',sans-serif; color:#0c1c3e; font-size:1.8rem; font-weight:800;">
            🔬 Fiscal Sensitivity Analysis
        </h2>
        <p style="color:#718096; margin-top:6px; font-size:0.95rem;">
            Multidimensional evaluation of Oil Price vs. Royalty Rate — Powered by STORM-Viewer
        </p>
    </div>
    """, unsafe_allow_html=True)

    sens_data_t8 = sel_sc.get('sensibilidad', [])

    if not sens_data_t8:
        st.info("💡 No sensitivity data found in this scenario file. Please ensure the JSON export includes a 'sensibilidad' key with price/royalty sensitivity results.")
    else:
        df_t8_raw = pd.DataFrame(sens_data_t8)

        def _norm_col(col):
            if 'Precio' in col or 'Oil' in col:    return 'Oil Price'
            if 'Regal' in col or 'Royalty' in col: return 'Royalty (%)'
            if 'VPN HPOC Post' in col:             return 'NPV Post-Tax (MMUSD)'
            if 'VPN HPOC Pre' in col:              return 'NPV Pre-Tax (MMUSD)'
            if 'Gov Take' in col:                  return 'Gov Take (%)'
            if 'IRR' in col:                       return 'IRR Post-Tax (%)'
            if 'MCE' in col or 'Peak' in col:      return 'Peak Inv. (MCE) (MMUSD)'
            if 'Payout' in col:                    return 'Payout (Years)'
            if 'Max Financ' in col:                return 'Max Financing (MMUSD)'
            if 'Break-even' in col or 'Punto' in col: return 'Break-even (USD/bbl)'
            return col

        df_t8_raw.columns = [_norm_col(c) for c in df_t8_raw.columns]
        df_t8 = df_t8_raw.copy()
        if 'Comp Take (%)' not in df_t8.columns:
            df_t8['Comp Take (%)'] = 100 - df_t8['Gov Take (%)']

        # ── Indicator Selector ────────────────────────────────────────────────
        indicators_map_t8 = {
            "NPV":        "NPV Post-Tax (MMUSD)",
            "IRR":        "IRR Post-Tax (%)",
            "GOV. TAKE":  "Gov Take (%)",
            "COMP. TAKE": "Comp Take (%)",
            "PAYBACK":    "Payout (Years)",
            "BREAK-EVEN": "Break-even (USD/bbl)"
        }
        available_inds = {k: v for k, v in indicators_map_t8.items() if v in df_t8.columns}

        _hdr1, _hdr2 = st.columns([1, 1.2])
        with _hdr2:
            if available_inds:
                active_ind_t8 = st.segmented_control(
                    "Select Indicator",
                    options=list(available_inds.keys()),
                    default=list(available_inds.keys())[0],
                    label_visibility="collapsed",
                    key="t8_ind_ctrl"
                ) or list(available_inds.keys())[0]
            else:
                st.warning("No indicators available for this chart.")
                active_ind_t8 = None

        active_col_t8 = available_inds[active_ind_t8]

        col_side_t8, col_curve_t8, col_radar_t8 = st.columns([1, 2.2, 1.2])

        prices_t8    = sorted(df_t8['Oil Price'].unique())
        royalties_t8 = sorted(df_t8['Royalty (%)'].unique())

        with col_side_t8:
            st.markdown("#### ⚙️ INPUT PARAMETERS")
            mode_t8 = st.radio(
                "Sensitivity Mode",
                ["Fix Price / Vary Royalty", "Fix Royalty / Vary Price"],
                key="t8_mode"
            )

            if mode_t8 == "Fix Price / Vary Royalty":
                fixed_price_t8 = st.selectbox(
                    "Crude Price (USD/bbl)", options=prices_t8,
                    format_func=lambda x: f"${x:.1f}", key="t8_price"
                )
                df_curve = df_t8[df_t8['Oil Price'] == fixed_price_t8].sort_values('Royalty (%)')
                x_col_t8 = 'Royalty (%)'
                x_lbl_t8 = "Royalty (%)"
            else:
                fixed_roy_t8 = st.selectbox(
                    "Royalty Rate (%)", options=royalties_t8,
                    format_func=lambda x: f"{x:.0f}%", key="t8_royalty"
                )
                df_curve = df_t8[df_t8['Royalty (%)'] == fixed_roy_t8].sort_values('Oil Price')
                x_col_t8 = 'Oil Price'
                x_lbl_t8 = "Oil Price (USD/bbl)"

            st.markdown("<br>", unsafe_allow_html=True)

            x_opts = sorted(df_curve[x_col_t8].unique())
            if mode_t8 == "Fix Price / Vary Royalty":
                sel_pt = st.select_slider("Selected Point (%)", options=x_opts, value=x_opts[0], key="t8_pt")
            else:
                sel_pt = st.select_slider("Selected Point (USD)", options=x_opts, value=x_opts[0], key="t8_pt")

            pt = df_curve[df_curve[x_col_t8] == sel_pt].iloc[0]

            _vpn = f"${pt['NPV Post-Tax (MMUSD)']:,.1f}M"
            _irr = f"{pt['IRR Post-Tax (%)']:.1f}%" if 'IRR Post-Tax (%)' in pt else "—"
            _gt  = f"{pt['Gov Take (%)']:.1f}%"
            _pb  = f"{pt['Payout (Years)']:.2f} yrs" if 'Payout (Years)' in pt else "—"

            kpi_html = (
                '<div style="background-color:#0c1c3e;color:white;padding:22px;border-radius:18px;'
                'box-shadow:0 8px 24px rgba(0,0,0,0.15);font-family:Segoe UI,sans-serif;">'
                '<p style="font-size:0.75rem;font-weight:700;color:#a0aec0;text-transform:uppercase;'
                'margin:0 0 4px 0;letter-spacing:1px;">KEY INDICATORS</p>'
                '<p style="font-size:2rem;font-weight:900;margin:0 0 14px 0;">' + _vpn + '</p>'
                '<table style="width:100%;border-collapse:collapse;">'
                '<tr style="border-bottom:1px solid rgba(255,255,255,0.12);">'
                '<td style="padding:9px 0;color:#94a3b8;font-size:0.85rem;">NPV Post-Tax</td>'
                '<td style="padding:9px 0;text-align:right;font-weight:700;font-size:1rem;">' + _vpn + '</td>'
                '</tr>'
                '<tr style="border-bottom:1px solid rgba(255,255,255,0.12);">'
                '<td style="padding:9px 0;color:#94a3b8;font-size:0.85rem;">IRR</td>'
                '<td style="padding:9px 0;text-align:right;font-weight:700;color:#4ade80;">' + _irr + '</td>'
                '</tr>'
                '<tr style="border-bottom:1px solid rgba(255,255,255,0.12);">'
                '<td style="padding:9px 0;color:#94a3b8;font-size:0.85rem;">Gov. Take</td>'
                '<td style="padding:9px 0;text-align:right;font-weight:700;color:#fbbf24;">' + _gt + '</td>'
                '</tr>'
                '<tr>'
                '<td style="padding:9px 0;color:#94a3b8;font-size:0.85rem;">Payback</td>'
                '<td style="padding:9px 0;text-align:right;font-weight:700;">' + _pb + '</td>'
                '</tr>'
                '</table>'
                '</div>'
            )
            st.markdown(kpi_html, unsafe_allow_html=True)

        with col_curve_t8:
            fig_curve = go.Figure()
            fig_curve.add_trace(go.Scatter(
                x=df_curve[x_col_t8],
                y=df_curve[active_col_t8],
                mode='lines+markers',
                line=dict(color='#6366f1', width=4),
                marker=dict(size=11, color='white', line=dict(color='#6366f1', width=3)),
                fill='tozeroy',
                fillcolor='rgba(99,102,241,0.06)',
                hovertemplate=f"<b>{x_lbl_t8}:</b> %{{x}}<br><b>{active_ind_t8}:</b> %{{y:.2f}}<extra></extra>"
            ))
            fig_curve.add_trace(go.Scatter(
                x=[sel_pt], y=[pt[active_col_t8]],
                mode='markers',
                marker=dict(size=18, color='#6366f1', line=dict(color='white', width=3)),
                showlegend=False,
                hovertemplate=f"<b>Selected</b><br>{x_lbl_t8}: {sel_pt}<br>{active_ind_t8}: {pt[active_col_t8]:.2f}<extra></extra>"
            ))
            fig_curve.update_layout(
                title=dict(text=f"Curve: {active_ind_t8}", font=dict(size=14, color='#0c1c3e'), x=0),
                xaxis_title=x_lbl_t8, yaxis_title=active_ind_t8,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=50, b=50, l=50, r=20), height=480,
                xaxis=dict(showgrid=True, gridcolor='#f1f5f9', zeroline=False),
                yaxis=dict(showgrid=True, gridcolor='#f1f5f9', zeroline=False),
                font=dict(family='Segoe UI, sans-serif')
            )
            st.plotly_chart(fig_curve, use_container_width=True)

        with col_radar_t8:
            st.markdown("#### PROJECT BALANCE")
            v_vpn_r = pt['NPV Post-Tax (MMUSD)']
            v_tir_r = pt.get('IRR Post-Tax (%)', 0)
            v_gt_r  = pt['Gov Take (%)']
            v_ct_r  = 100 - v_gt_r
            v_pb_r  = pt.get('Payout (Years)', 7.5)
            v_mg_r  = pt.get('Break-even (USD/bbl)', 50)

            r_vals = [
                min(1.0, max(0, v_vpn_r / 500)),
                min(1.0, max(0, v_tir_r / 100)),
                v_gt_r / 100, v_ct_r / 100,
                max(0.05, 1 - (v_pb_r / 15)),
                max(0.05, 1 - (v_mg_r / 100))
            ]

            fig_radar_t8 = go.Figure()
            fig_radar_t8.add_trace(go.Scatterpolar(
                r=r_vals,
                theta=["NPV", "IRR", "Gov Take", "Comp Take", "Payback", "Break-even"],
                fill='toself',
                fillcolor='rgba(99,102,241,0.25)',
                line=dict(color='#6366f1', width=2),
                marker=dict(size=7, color='#6366f1')
            ))
            fig_radar_t8.update_layout(
                polar=dict(
                    radialaxis=dict(visible=False, range=[0, 1]),
                    angularaxis=dict(tickfont=dict(size=10, color='#64748b'))
                ),
                showlegend=False, paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=30, b=30, l=30, r=30), height=320,
                font=dict(family='Segoe UI, sans-serif', size=10, color='#64748b')
            )
            st.plotly_chart(fig_radar_t8, use_container_width=True)

            obs_price = pt.get('Oil Price', '—')
            obs_roy   = pt.get('Royalty (%)', '—')
            st.markdown(
                f'<div style="background:#f8fafc;border-radius:12px;padding:16px;border-left:4px solid #6366f1;margin-top:8px;">'
                f'<div style="font-size:0.72rem;font-weight:700;color:#64748b;margin-bottom:5px;">ℹ️ NOTE</div>'
                f'<div style="font-size:0.88rem;color:#1e293b;">At <b>${obs_price:.1f}/bbl</b>, '
                f'the optimal fiscal balance is found at a royalty rate of <b>{obs_roy:.0f}%</b>.</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown("<br>", unsafe_allow_html=True)
        c_rent_t8, c_heat_t8 = st.columns([1, 1])

        with c_rent_t8:
            st.markdown("#### 💰 RENT DISTRIBUTION")
            st.caption("Relative share of total generated economic rent")
            v_gt_bar = pt['Gov Take (%)']
            v_ct_bar = 100 - v_gt_bar
            fig_rent_t8 = go.Figure()
            fig_rent_t8.add_trace(go.Bar(y=["Distribution"], x=[v_gt_bar], name="State",    orientation='h', marker=dict(color='#f59e0b')))
            fig_rent_t8.add_trace(go.Bar(y=["Distribution"], x=[v_ct_bar], name="Contractor", orientation='h', marker=dict(color='#6366f1')))
            fig_rent_t8.update_layout(
                barmode='stack',
                xaxis=dict(showticklabels=False, range=[0, 100]),
                yaxis=dict(showticklabels=False), showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=40, b=20, l=20, r=20), height=180
            )
            fig_rent_t8.add_annotation(x=v_gt_bar/2,            y=0, text=f"State<br>{v_gt_bar:.1f}%",      showarrow=False, font=dict(color="white", size=13, weight="bold"))
            fig_rent_t8.add_annotation(x=v_gt_bar+v_ct_bar/2,   y=0, text=f"Contractor<br>{v_ct_bar:.1f}%", showarrow=False, font=dict(color="white", size=13, weight="bold"))
            st.plotly_chart(fig_rent_t8, use_container_width=True)

        with c_heat_t8:
            st.markdown("#### 🌡️ NPV INTENSITY MAP")
            st.caption("Full sensitivity overview — Royalty vs. Oil Price")
            try:
                pivot_heat_t8 = df_t8.pivot(index='Royalty (%)', columns='Oil Price', values='NPV Post-Tax (MMUSD)')
                fig_heat_t8 = px.imshow(
                    pivot_heat_t8,
                    labels=dict(x="Oil Price (USD/bbl)", y="Royalty (%)", color="NPV (MMUSD)"),
                    color_continuous_scale='Blues', aspect='auto'
                )
                fig_heat_t8.update_layout(margin=dict(t=10, b=40, l=10, r=10), height=200,
                                          coloraxis_showscale=True, coloraxis_colorbar=dict(thickness=12, len=0.8))
                st.plotly_chart(fig_heat_t8, use_container_width=True)
            except Exception:
                st.info("Heatmap requires a full price × royalty grid in the sensitivity data.")

with t_det7:
    st.subheader("Fiscal Equilibrium Sensitivity (Government Take)")
    st.markdown("Optimization of fiscal terms (Royalty, Integrated Tax, and Income Tax) to balance Government Take vs. Investor Profitability.")
    
    gt_data = sel_sc.get('optimizacion_fiscal', [])
    if gt_data:
        df_gt_res = pd.DataFrame(gt_data)
        
        # Ensure columns are in English and handle any encoding issues
        if len(df_gt_res.columns) >= 6:
            df_gt_res.columns = [
                'Royalty (%)', 'Integrated Tax (%)', 'Income Tax (ISLR) (%)', 
                'NPV Pre-Tax (MMUSD)', 'NPV Post-Tax (MMUSD)', 'Government Take (%)'
            ][:len(df_gt_res.columns)]
        
        # Read Target GT from JSON (params or root)
        target_gt = sel_sc['params'].get('target_gt')
        if target_gt is None: 
            target_gt = sel_sc.get('target_gt', 50.0) # Fallback to 50.0 if missing
        
        st.markdown("---")
        st.subheader("📊 HPOC Optimization Dashboard: NPV vs. Government Take")
        
        total_found = len(df_gt_res)
        
        # Visual Tolerance Margin (Sync with Visualizer style)
        if 'viewer_margen_tol' not in st.session_state:
            st.session_state['viewer_margen_tol'] = 1.0
            
        m_tol = st.session_state['viewer_margen_tol']
        
        # English Categories
        cat_cumple = f"Meets Target ({target_gt-0.5:.1f} - {target_gt+0.5:.1f}%)"
        cat_prox = f"Critical Proximity ({target_gt-m_tol:.1f} - {target_gt-0.5:.1f}% and {target_gt+0.5:.1f} - {target_gt+m_tol:.1f}%)"
        
        def get_cat(gt):
            diff = abs(gt - target_gt)
            if diff <= 0.5: return cat_cumple
            elif diff <= m_tol: return cat_prox
            else: return "Other"
            
        df_gt_res['Category'] = df_gt_res['Government Take (%)'].apply(get_cat)
        df_viz = df_gt_res[df_gt_res['Category'] != "Other"].copy()
        
        num_meta = len(df_viz[df_viz['Category'] == cat_cumple])
        max_vpn_cumple = df_viz[df_viz['Category'] == cat_cumple]['NPV Post-Tax (MMUSD)'].max() if num_meta > 0 else 0
        best_vpn_overall = df_gt_res['NPV Post-Tax (MMUSD)'].max() if len(df_gt_res) > 0 else 0
        
        db_c1, db_c2, db_c3 = st.columns([1, 2, 1])
        
        with db_c1:
            st.markdown("<span style='font-size:10px; font-weight:bold; color:#94a3b8;'>SCENARIOS IN TARGET</span>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='margin-top:-10px;'>{num_meta} <span style='font-size:16px; font-weight:normal; color:#94a3b8;'>of {total_found}</span></h2>", unsafe_allow_html=True)
            st.progress(num_meta / total_found if total_found > 0 else 0)
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.slider("Visual Tolerance Margin (%)", min_value=1.0, max_value=10.0, step=0.5, key="viewer_margen_tol")
            st.caption(f"Note: {num_meta} scenarios meet the target.")
            
            st.markdown("<br><span style='font-size:10px; font-weight:bold; color:#94a3b8;'>MAX NPV (MEETS TARGET)</span>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='margin-top:-10px; color:#059669;'>${max_vpn_cumple:,.2f}M</h2>", unsafe_allow_html=True)
            st.caption("✅ Optimal value under constraint")
            
            st.markdown("<br><span style='font-size:10px; font-weight:bold; color:#94a3b8;'>BEST ABSOLUTE NPV</span>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='margin-top:-10px; color:#2563eb;'>${best_vpn_overall:,.2f}M</h2>", unsafe_allow_html=True)
            st.caption("📈 Independent of target")
            
        with db_c2:
            if len(df_viz) > 0:
                fig = px.scatter(df_viz, 
                                 x="Government Take (%)", 
                                 y="NPV Post-Tax (MMUSD)",
                                 color="Category",
                                 color_discrete_map={cat_cumple: "#10b981", cat_prox: "#64748b"},
                                 hover_data=["Royalty (%)", "Integrated Tax (%)", "Income Tax (ISLR) (%)"],
                                 title="Goal Proximity Analysis")
                fig.add_vline(x=target_gt, line_dash="dash", line_color="#ef4444", annotation_text=f"TARGET {target_gt}%")
                fig.update_traces(marker=dict(size=14, opacity=0.9, line=dict(width=1, color='white')))
                
                fig.update_xaxes(title_text="")
                fig.add_annotation(
                    x=1, y=-0.12, xref='paper', yref='paper',
                    xanchor='right', yanchor='top',
                    text="Government Take (%)", showarrow=False,
                    font=dict(size=12, color="#64748b")
                )
                fig.update_layout(
                    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="left", x=0, title=""),
                    margin=dict(b=80)
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No scenarios found within the visual range. Increase the tolerance margin.")
                
        with db_c3:
            st.markdown(f"**Top Ranked Results**")
            with st.container(height=450):
                if len(df_viz) == 0:
                    st.caption("No scenarios to display.")
                else:
                    sorted_viz = df_viz.sort_values("NPV Post-Tax (MMUSD)", ascending=False)
                    for i, (idx, row) in enumerate(sorted_viz.iterrows()):
                        color = "#10b981" if row['Category'] == cat_cumple else "#64748b"
                        bg_color = "#ecfdf5" if row['Category'] == cat_cumple else "#f8fafc"
                        st.markdown(f"""
                        <div style="padding:12px; border-radius:12px; background:{bg_color}; border: 1px solid {color}44; margin-bottom:10px;">
                            <div style='display: flex; justify-content: space-between;'>
                                <span style="font-size:10px; font-weight:bold; color:#64748b;">RANK {i+1}</span>
                                <span style='font-size: 10px; font-weight: bold; background: #e2e8f0; padding: 2px 8px; border-radius: 10px;'>GT: {row['Government Take (%)']:.2f}%</span>
                            </div>
                            <div style="font-size:1.4rem; font-weight:900; color:#1e293b; margin:5px 0;">${row['NPV Post-Tax (MMUSD)']:.2f} <span style='font-size:0.7rem; color:#94a3b8;'>MMUSD</span></div>
                            <div style='display: flex; gap: 5px; margin-top: 5px;'>
                                <span style='font-size: 0.7rem; background: white; border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px;'>R: {row['Royalty (%)']:.0f}%</span>
                                <span style='font-size: 0.7rem; background: white; border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px;'>Ii: {row['Integrated Tax (%)']:.0f}%</span>
                                <span style='font-size: 0.7rem; background: white; border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px;'>I: {row['Income Tax (ISLR) (%)']:.0f}%</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
        
        with st.expander("📂 View Full Optimization Data Table", expanded=False):
            st.dataframe(
                df_gt_res.drop(columns=['Category']).style.format({
                    "Royalty (%)": "{:.0f}",
                    "Integrated Tax (%)": "{:.0f}",
                    "Income Tax (ISLR) (%)": "{:.0f}",
                    "NPV Pre-Tax (MMUSD)": "{:.2f}",
                    "NPV Post-Tax (MMUSD)": "{:.2f}",
                    "Government Take (%)": "{:.2f}"
                }).background_gradient(subset=["NPV Post-Tax (MMUSD)"], cmap="Greens"),
                use_container_width=True
            )
            
    else:
        st.warning("⚠️ No Fiscal Optimization data found in this scenario file.")





# ─── SECTION 3: MULTI-SCENARIO TABLE ──────────────────────────────────────
if len(scenarios) > 1:
    st.markdown("---")
    st.subheader("📊 Multi-Scenario Comparative Table")
    rows = []
    for sc in scenarios:
        rows.append({
            "Scenario": sc['params'].get('esc_name', sc['_filename']),
            "NPV Post-Tax (MMUSD)": round(ind_mean(sc, 'npv_hpoc_post'), 2),
            "IRR (%)": round(float(sc['indicators'].get('irr_post_annual', 0.0)), 2),
            "MOIC (x)": round(ind_mean(sc, 'moic'), 2),
            "Peak Inv. (MMUSD)": round(ind_mean(sc, 'mce_mm'), 2),
            "Gov. Take (%)": round(ind_mean(sc, 'npv_gov_take'), 2),
        })
    st.dataframe(pd.DataFrame(rows).set_index("Scenario"), use_container_width=True)

