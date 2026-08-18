import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
import os

from core.data_loader import load_data
from core.stochastic_engine import run_montecarlo
from core.economic_model import calculate_cash_flow

st.set_page_config(page_title="CHIMIRE Economic Evaluation", layout="wide", page_icon="🛢️")

with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
c1, c2 = st.sidebar.columns(2)
with c1:
    if os.path.exists('assets/mi_logo.png'):
        st.image('assets/mi_logo.png', use_container_width=True)
with c2:
    if os.path.exists('assets/logo_app.png'):
        st.image('assets/logo_app.png', use_container_width=True)

st.sidebar.markdown("---")

# Navigation
NAV_CONFIG    = "⚙️ Configuración"
NAV_RESULTS   = "📊 Resultados"
NAV_COMPARE   = "🔬 Comparador"
NAV_GLOSSARY  = "📖 Ayuda / Glosario"

has_results = 'sim_results' in st.session_state

nav_options = [NAV_CONFIG]
if has_results:
    nav_options.append(NAV_RESULTS)
nav_options.append(NAV_COMPARE)
nav_options.append(NAV_GLOSSARY)

page = st.sidebar.radio("Navegación", nav_options, label_visibility="collapsed")


st.sidebar.markdown("---")
st.sidebar.markdown("### 📂 Archivo de Datos")
st.sidebar.caption("⚠️ **Importante:** Asegúrese de cerrar el archivo en Excel antes de cargarlo. Si el archivo está abierto, la carga fallará (línea roja).")
uploaded_file = st.sidebar.file_uploader("Cargar Excel", type=['xlsx', 'xlsm'], label_visibility="collapsed")

import io

# ── Data loading ──────────────────────────────────────────────────────────────
default_file = r"RSMPP - CPP Chimire_Esc 2 (21_04_2026_11_01_42).xlsx"

# Cache version — bump this string whenever data_loader.py changes
_CACHE_VERSION = "v3"

@st.cache_data(show_spinner="Procesando datos del proyecto...")
def get_data(file_bytes_or_path, _version=_CACHE_VERSION):
    if isinstance(file_bytes_or_path, bytes):
        return load_data(io.BytesIO(file_bytes_or_path))
    return load_data(file_bytes_or_path)

if uploaded_file is not None:
    # Read into memory directly to avoid PermissionError if open in Excel
    file_bytes = uploaded_file.getvalue()
    if 'last_file' not in st.session_state or st.session_state['last_file'] != uploaded_file.name:
        st.session_state['last_file'] = uploaded_file.name
        # Clear old simulation results if file changed
        for k in ['sim_results', 'econ_results', 'data_dict', 'params']:
            st.session_state.pop(k, None)
    data_dict_full = get_data(file_bytes)
    st.sidebar.success("✅ Datos cargados correctamente")
    st.sidebar.caption(f"📅 **{len(data_dict_full['dates'])}** meses detectados ({data_dict_full['dates'][0].strftime('%b %Y')} - {data_dict_full['dates'][-1].strftime('%b %Y')})")
elif os.path.exists(default_file):
    data_dict_full = get_data(default_file)
    st.sidebar.info("📂 Usando archivo por defecto")
    st.sidebar.caption(f"📅 **{len(data_dict_full['dates'])}** meses detectados")
else:
    st.sidebar.error("Cargue un archivo Excel para continuar.")
    st.stop()

# ── Global Plotting Utilities ────────────────────────────────────────────────
def hist_plot(arr, title, color, nom_val=None, nbins=28):
    """Premium gradient histogram — Precision Architect design system."""
    arr = np.asarray(arr, dtype=float)
    p10, p50, p90 = np.percentile(arr, [10, 50, 90])
    mean_val = np.mean(arr)

    counts, edges = np.histogram(arr, bins=nbins)
    centers = (edges[:-1] + edges[1:]) / 2
    widths  = (edges[1:] - edges[:-1]) * 0.92

    max_dist = max(np.abs(centers - p50).max(), 1e-9)
    opacities = 0.22 + 0.78 * (1.0 - np.abs(centers - p50) / max_dist)

    fig = go.Figure()
    for i in range(len(counts)):
        fig.add_trace(go.Bar(
            x=[centers[i]], y=[counts[i]], width=[widths[i]],
            marker=dict(color=color, opacity=float(opacities[i]), line=dict(width=0)),
            showlegend=False,
            hovertemplate=f"{edges[i]:.1f} – {edges[i+1]:.1f} MM USD<br>Frecuencia: {counts[i]}<extra></extra>"
        ))

    for val, lbl in [(p90, 'P90'), (p50, 'P50'), (p10, 'P10')]:
        fig.add_vline(x=val, line=dict(color='#222222', dash='dash', width=1.4),
                      annotation=dict(text=f"<b>{lbl}</b>:{val:.1f}", font=dict(size=9, color='#222222'), yref='paper', y=1.02, showarrow=False))

    left_text  = f"<b>Media (VP):</b> {mean_val:.2f}"
    if nom_val is not None: left_text += f"<br><span style='color:#888'>Media Nominal:</span> {nom_val:.2f}"
    right_text = f"P90: {p90:.2f}&nbsp;&nbsp;&nbsp;&nbsp;P10: {p10:.2f}"
    for txt, ax, anchor in [(left_text, 0, 'left'), (right_text, 1, 'right')]:
        fig.add_annotation(x=ax, y=-0.22, xref='paper', yref='paper', text=txt, showarrow=False, font=dict(size=9, color='#555555'), align=anchor, xanchor=anchor)

    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color='#1a1a2e'), x=0, xanchor='left', y=0.97),
        xaxis=dict(title=dict(text='MM USD', font=dict(size=11, color='#555')), showgrid=False, zeroline=False, showline=True, linecolor='#d0d0d0', linewidth=1),
        yaxis=dict(title=dict(text='Frecuencia', font=dict(size=11, color='#555')), showgrid=True, gridcolor='#f0f0f0', gridwidth=1, zeroline=False),
        bargap=0.0, paper_bgcolor='white', plot_bgcolor='white', margin=dict(t=55, b=80, l=55, r=25), showlegend=False, hovermode='x'
    )
    return fig

def reserves_bar(res_dict, title, color_1p, color_2p, color_3p, y_label):
    labels = list(res_dict.keys())
    values = list(res_dict.values())
    colors = [color_1p, color_2p, color_3p]
    fig = go.Figure()
    for i, (lbl, val) in enumerate(zip(labels, values)):
        fig.add_trace(go.Bar(
            x=[lbl], y=[val], name=lbl,
            marker_color=colors[i],
            text=[f"{val:.1f}"], textposition='outside',
            width=0.5
        ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=16)),
        yaxis_title=y_label,
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=60, b=40),
        yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.06)')
    )
    return fig

def plot_dual(dates, rate_data, cum_data, res_dict, title, y1_lbl, y2_lbl, color):
    # Support both 2D (Montecarlo full array) and 3D tuple (already precomputed P10,P50,P90)
    if isinstance(rate_data, tuple):
        r10, r50, r90 = rate_data
        c10, c50, c90 = cum_data
    else:
        r10, r50, r90 = np.percentile(rate_data, [10, 50, 90], axis=0)
        c10, c50, c90 = np.percentile(cum_data,  [10, 50, 90], axis=0)
        
    fig = go.Figure()
    # Rate band
    fig.add_trace(go.Scatter(x=dates, y=r10, name='Q P10', line=dict(color=color, width=1), opacity=0.35))
    fig.add_trace(go.Scatter(x=dates, y=r90, name='Q P90', line=dict(color=color, width=1),
                             fill='tonexty', fillcolor=f'rgba(0,128,0,0.15)' if 'green' in color else 'rgba(214,39,40,0.15)', opacity=0.35))
    fig.add_trace(go.Scatter(x=dates, y=r50, name='Q P50', line=dict(color=color, width=3)))
    # Cumulative
    fig.add_trace(go.Scatter(x=dates, y=c10, name='Cum P10', yaxis='y2', line=dict(color=color, width=1, dash='dot'), opacity=0.5))
    fig.add_trace(go.Scatter(x=dates, y=c50, name='Cum P50', yaxis='y2', line=dict(color=color, width=2, dash='dot')))
    fig.add_trace(go.Scatter(x=dates, y=c90, name='Cum P90', yaxis='y2', line=dict(color=color, width=1, dash='dot'), opacity=0.5))
    # Reserves
    dash_colors = ['#1a1a2e', '#4a4e69', '#9a8c98']
    for i, (nm, val) in enumerate(res_dict.items()):
        fig.add_trace(go.Scatter(x=dates, y=[val]*len(dates), name=nm, yaxis='y2',
                                 line=dict(color=dash_colors[i], width=1.5, dash='dashdot')))
    fig.update_layout(
        title=dict(text=title, font=dict(size=20, color=color), y=0.98, x=0, xanchor='left'),
        xaxis_title='Fecha',
        yaxis=dict(title=y1_lbl, showgrid=True, gridcolor='rgba(0,0,0,0.05)'),
        yaxis2=dict(title=y2_lbl, overlaying='y', side='right', showgrid=False),
        legend=dict(orientation='h', yanchor='top', y=-0.2, xanchor='center', x=0.5, font=dict(size=10)),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=100, l=50, r=50, b=100), hovermode='x unified'
    )
    return fig

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════
if page == NAV_CONFIG:
    st.title("⚙️ Configuración del Modelo")
    st.markdown("Define el horizonte temporal y los parámetros económicos antes de ejecutar la simulación.")
    st.markdown("---")

    # Dates limits from data
    min_date = data_dict_full['dates'][0].date()
    max_date = data_dict_full['dates'][-1].date()

    # Auto-detect end date: first date where Qo - Media < 10 bpd
    def detect_end_date(data_full):
        try:
            qo_row_candidates = [idx for idx in data_full['oil'].index if 'Qo' in idx and 'Media' in idx]
            if qo_row_candidates:
                qo_series = data_full['oil'].loc[qo_row_candidates[0]]
                # Find first date where Qo < 10 bpd
                below_thresh = qo_series[qo_series < 10]
                if not below_thresh.empty:
                    return below_thresh.index[0].date()
        except Exception:
            pass
        return max_date

    auto_end_date = detect_end_date(data_dict_full)

    # Restore from session if available, otherwise use defaults
    prev_cfg = st.session_state.get('cfg', {})
    default_start = prev_cfg.get('start_dt', pd.Timestamp(min_date)).date() if prev_cfg else min_date
    default_end   = prev_cfg.get('end_dt',   pd.Timestamp(auto_end_date)).date() if prev_cfg else auto_end_date

    st.markdown("### 📋 Identificación del Escenario")
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        proj_name = st.text_input("Nombre del Proyecto", value=prev_cfg.get('proj_name', "STORM-Matrix"))
    with col_n2:
        esc_name = st.text_input("Nombre del Escenario", value=prev_cfg.get('esc_name', "Esc. Base"),
                                 help="Nombre corto para identificar el escenario (ej. Esc. 1, Caso Alto)")

    esc_desc = st.text_area("Descripción del Escenario", value=prev_cfg.get('esc_desc', ""),
                            height=80, help="Descripción breve del plan de desarrollo (ej. 'Perforación de 5 pozos + compresores')")

    st.markdown("### 🛠️ Intervenciones")
    col_i1, col_i2, col_i3, col_i4, col_i5 = st.columns(5)
    with col_i1:
        n_terminaciones = st.number_input("N° de Terminaciones", value=int(prev_cfg.get('n_terminaciones', prev_cfg.get('n_interventions', 0))), min_value=0, step=1)
    with col_i2:
        n_rma = st.number_input("N° de RMA", value=int(prev_cfg.get('n_rma', 0)), min_value=0, step=1)
    with col_i3:
        n_cambio_zona = st.number_input("N° de Cambio de Zona", value=int(prev_cfg.get('n_cambio_zona', 0)), min_value=0, step=1)
    with col_i4:
        n_limpieza = st.number_input("N° de Limpieza y Estimulación", value=int(prev_cfg.get('n_limpieza', 0)), min_value=0, step=1)
    with col_i5:
        n_reactivacion = st.number_input("N° de Reactivación", value=int(prev_cfg.get('n_reactivacion', 0)), min_value=0, step=1)

    st.markdown("---")
    st.markdown("### 📅 Horizonte del Proyecto")
    st.caption(f"Fecha Fin sugerida automáticamente: **{auto_end_date}** (primer mes con Qo < 10 bpd)")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("Fecha Inicio", min_value=min_date, max_value=max_date, value=default_start)
    with col_d2:
        end_date = st.date_input("Fecha Fin", min_value=min_date, max_value=max_date, value=default_end)

    start_dt = pd.to_datetime(start_date)
    end_dt   = pd.to_datetime(end_date)

    if start_dt > end_dt:
        st.error("La Fecha de Inicio debe ser anterior a la Fecha Fin.")
        st.stop()

    st.markdown("---")
    st.markdown("### 💰 Parámetros Económicos")
    col_p1, col_p2, col_p3 = st.columns(3)

    with col_p1:
        st.markdown("**Precios**")
        oil_price = st.number_input("Crude Oil (WTI) - USD/bl", value=float(prev_cfg.get('oil_price', 60.0)), step=1.0)
        gas_price = st.number_input("Gas (Henry Hub) - USD/mcf", value=float(prev_cfg.get('gas_price', 3.0)), step=0.1)
        discount_rate = st.number_input("Tasa de Descuento (%)", value=float(prev_cfg.get('discount_rate', 15.0)), step=0.5)

    with col_p2:
        st.markdown("**Impuestos y Regalías** *(Ley Hidrocarburos 2026)*")
        royalty_rate  = st.number_input("Regalías (%) — Máx. legal 30%", value=float(prev_cfg.get('royalty_rate', 30.0)), step=1.0, min_value=0.0, max_value=30.0)
        int_tax_rate  = st.number_input("Impuesto Integrado (%) — Máx. legal 15%", value=float(prev_cfg.get('int_tax_rate', 3.33)), step=0.01, min_value=0.0, max_value=15.0)
        islr_rate     = st.number_input("ISLR (%) — Máx. legal 50%", value=float(prev_cfg.get('islr_rate', 50.0)), step=1.0, min_value=0.0, max_value=50.0)

    with col_p3:
        st.markdown("**Recuperación de Costos**")
        recovery_capex_rate = st.number_input("% Recuperación CAPEX", value=float(prev_cfg.get('recovery_capex_rate', 100.0)), step=1.0)
        recovery_opex_rate  = st.number_input("% Recuperación OPEX",  value=float(prev_cfg.get('recovery_opex_rate', 100.0)), step=1.0)

    st.markdown("---")
    col_p4, col_p5 = st.columns(2)
    with col_p4:
        st.markdown("### 🔧 Disponibilidad del Sistema")
        prev_avail = prev_cfg.get('avail_params', {'type': 'constant', 'val': 0.95})
        avail_type = st.selectbox("Tipo de Distribución", ["Constante", "Distribuido (BetaPERT)"],
                                  index=0 if prev_avail.get('type','constant')=='constant' else 1)
        if avail_type == "Constante":
            avail_val    = st.number_input("Disponibilidad (%)", value=float(prev_avail.get('val',0.95))*100, step=1.0) / 100.0
            avail_params = {'type': 'constant', 'val': avail_val}
        else:
            a1, a2, a3 = st.columns(3)
            with a1: avail_min  = st.number_input("Mínimo (%)",       value=float(prev_avail.get('min',0.85))*100, step=1.0) / 100.0
            with a2: avail_mode = st.number_input("Más Probable (%)", value=float(prev_avail.get('mode',0.95))*100, step=1.0) / 100.0
            with a3: avail_max  = st.number_input("Máximo (%)",       value=float(prev_avail.get('max',0.98))*100, step=1.0) / 100.0
            avail_params = {'type': 'betapert', 'min': avail_min, 'mode': avail_mode, 'max': avail_max}

    with col_p5:
        st.markdown("### 🎲 Simulación Monte Carlo")
        n_iterations = st.number_input("Iteraciones", value=int(prev_cfg.get('n_iterations', 500)), step=100, min_value=100, max_value=5000)

    st.markdown("---")

    # Store config in session for results page
    st.session_state['cfg'] = dict(
        proj_name=proj_name, esc_name=esc_name,
        esc_desc=esc_desc, 
        n_terminaciones=int(n_terminaciones), n_rma=int(n_rma),
        n_cambio_zona=int(n_cambio_zona), n_limpieza=int(n_limpieza),
        n_reactivacion=int(n_reactivacion),
        start_dt=start_dt, end_dt=end_dt,
        oil_price=oil_price, gas_price=gas_price,
        discount_rate=discount_rate,
        royalty_rate=royalty_rate, int_tax_rate=int_tax_rate, islr_rate=islr_rate,
        recovery_capex_rate=recovery_capex_rate, recovery_opex_rate=recovery_opex_rate,
        avail_params=avail_params, n_iterations=int(n_iterations)
    )

    if st.button("🚀 Ejecutar Simulación Económica Integrada", type="primary", use_container_width=True):
        cfg = st.session_state['cfg']
        filtered_dates = [d for d in data_dict_full['dates'] if cfg['start_dt'] <= d <= cfg['end_dt']]
        data_dict = {'dates': filtered_dates}
        for key in ['oil', 'gas', 'capex', 'opex', 'abex', 'other_income']:
            data_dict[key] = data_dict_full[key][filtered_dates]

        params = {
            'proj_name': cfg['proj_name'], 'esc_name': cfg['esc_name'],
            'esc_desc': cfg['esc_desc'], 
            'n_terminaciones': cfg['n_terminaciones'],
            'n_rma': cfg['n_rma'],
            'n_cambio_zona': cfg['n_cambio_zona'],
            'n_limpieza': cfg['n_limpieza'],
            'n_reactivacion': cfg['n_reactivacion'],
            'oil_price': cfg['oil_price'], 'gas_price': cfg['gas_price'],
            'discount_rate': cfg['discount_rate'],
            'royalty_rate': cfg['royalty_rate'], 'integrated_tax_rate': cfg['int_tax_rate'],
            'islr_rate': cfg['islr_rate'],
            'recovery_capex_rate': cfg['recovery_capex_rate'], 'recovery_opex_rate': cfg['recovery_opex_rate'],
            'availability_type': cfg['avail_params']['type'],
            'availability_val':  cfg['avail_params'].get('val', 1.0),
            'availability_min':  cfg['avail_params'].get('min', 1.0),
            'availability_mode': cfg['avail_params'].get('mode', 1.0),
            'availability_max':  cfg['avail_params'].get('max', 1.0),
        }

        with st.spinner("Ejecutando simulación Monte Carlo..."):
            sim_results  = run_montecarlo(data_dict, params, cfg['n_iterations'])
            econ_results = calculate_cash_flow(sim_results, params)
            st.session_state['sim_results']  = sim_results
            st.session_state['econ_results'] = econ_results
            st.session_state['data_dict']    = data_dict
            st.session_state['params']       = params

        st.success("✅ Simulación completada. Navega a **📊 Resultados** en el menú izquierdo.")
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: RESULTADOS
# ══════════════════════════════════════════════════════════════════════════════
elif page == NAV_RESULTS:
    sim_results  = st.session_state['sim_results']
    econ_results = st.session_state['econ_results']
    data_dict    = st.session_state['data_dict']
    params       = st.session_state['params']
    dates        = sim_results['dates']

    st.title("📊 Resultados de la Simulación")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🛢️ Pronósticos", "💸 Egresos", "📈 Distribuciones NPV",
        "💼 Flujo de Caja", "🎯 Indicadores & Sensibilidad", "⚖️ Equilibrio Fiscal / GT"
    ])

    # ── helpers ──────────────────────────────────────────────────────────────
    # (Plot functions are now globally available)

    # ── TAB 1: Pronósticos ────────────────────────────────────────────────────
    with tab1:
        st.header("Pronósticos de Producción")
        col1, col2 = st.columns(2)

        # Oil reserves
        def safe_res(df, key):
            try:    return df.loc[key].iloc[0]
            except: return 0.0

        res_oil = {
            '1P': safe_res(data_dict['oil'], 'Reservas Aceite-1P (MMb)'),
            '2P': safe_res(data_dict['oil'], 'Reservas Aceite-2P (MMb)'),
            '3P': safe_res(data_dict['oil'], 'Reservas Aceite-3P (MMb)'),
        }
        res_gas = {
            '1P': safe_res(data_dict['gas'], 'Reservas Gas-1P (MMMpc)'),
            '2P': safe_res(data_dict['gas'], 'Reservas Gas-2P (MMMpc)'),
            '3P': safe_res(data_dict['gas'], 'Reservas Gas-3P (MMMpc)'),
        }

        with col1:
            st.plotly_chart(plot_dual(
                dates, sim_results['simulations']['Qo'], sim_results['simulations']['NP'],
                res_oil, "Pronóstico Integral de Aceite (Bruta)", "Gasto (bpd)", "Np (MMbls)", "green"
            ), use_container_width=True)
            # Reserves bar
            st.plotly_chart(reserves_bar(
                res_oil, "Reservas de Aceite (MMb)",
                '#1a1a2e', '#1f77b4', '#74b9ff', "MMb"
            ), use_container_width=True)

        with col2:
            st.plotly_chart(plot_dual(
                dates, sim_results['simulations']['Qg'], sim_results['simulations']['GP'],
                res_gas, "Pronóstico Integral de Gas (Bruta)", "Gasto (Mpcd)", "Gp (MMMpc)", "#d62728"
            ), use_container_width=True)
            # Reserves bar
            st.plotly_chart(reserves_bar(
                res_gas, "Reservas de Gas (MMMpc)",
                '#1a1a2e', '#d62728', '#ff7f7f', "MMMpc"
            ), use_container_width=True)

    # ── TAB 2: Egresos ────────────────────────────────────────────────────────
    with tab2:
        st.header("Flujo de Egresos Mensual")
        capex_m = np.mean(econ_results['cash_flows']['capex'], axis=0)
        opex_m  = np.mean(econ_results['cash_flows']['opex'],  axis=0)
        abex_m  = np.mean(econ_results['cash_flows']['abex'],  axis=0)

        # Premium Metric Cards (VP vs Nominal)
        ind = econ_results['indicators']
        c_cap, c_op, c_ab = st.columns(3)
        
        card_tpl = """
        <div style="background: white; border-left: 5px solid #00d4ff; padding: 12px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 15px;">
            <div style="color: #6c757d; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px;">{label}</div>
            <div style="display: flex; flex-direction: column;">
                <div style="color: #0c1c3e; font-size: 1.6rem; font-weight: 800; line-height: 1.2;">{vp} <span style="font-size: 0.8rem; font-weight: 400; color: #00d4ff;">MMUSD (VP)</span></div>
                <div style="color: #a0aec0; font-size: 1.0rem; font-weight: 600; margin-top: 4px;">{nominal} <span style="font-size: 0.7rem; font-weight: 400;">Nominal</span></div>
            </div>
        </div>
        """
        
        vp_capex = np.mean(ind['npv_capex'])
        vp_opex  = np.mean(ind['npv_opex'])
        vp_abex  = np.mean(ind['npv_abex'])
        
        nom_capex = np.sum(capex_m)
        nom_opex  = np.sum(opex_m)
        nom_abex  = np.sum(abex_m)

        with c_cap: st.markdown(card_tpl.format(label="CAPEX TOTAL", value="", vp=f"{vp_capex:.2f}", nominal=f"{nom_capex:.2f}"), unsafe_allow_html=True)
        with c_op:  st.markdown(card_tpl.format(label="OPEX TOTAL",  value="", vp=f"{vp_opex:.2f}",  nominal=f"{nom_opex:.2f}"),  unsafe_allow_html=True)
        with c_ab:  st.markdown(card_tpl.format(label="ABEX TOTAL",  value="", vp=f"{vp_abex:.2f}",  nominal=f"{nom_abex:.2f}"),  unsafe_allow_html=True)
        cum_c   = np.cumsum(capex_m + opex_m + abex_m)

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=dates, y=capex_m, name='CAPEX', marker_color='#1f77b4'))
        fig2.add_trace(go.Bar(x=dates, y=opex_m,  name='OPEX',  marker_color='#ff7f0e'))
        fig2.add_trace(go.Bar(x=dates, y=abex_m,  name='ABEX',  marker_color='#2ca02c'))
        fig2.add_trace(go.Scatter(x=dates, y=cum_c, name='Costo Acumulado',
                                  yaxis='y2', line=dict(color='black', width=3)))
        fig2.update_layout(
            barmode='stack', title="Inversiones y Gastos Esperados (Media Monte Carlo)",
            xaxis_title="Fecha", yaxis_title="Desembolso Mensual (MMUSD)",
            yaxis2=dict(title="Costo Acumulado (MMUSD)", overlaying='y', side='right'),
            legend=dict(orientation='h', yanchor='top', y=-0.2, xanchor='center', x=0.5),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
            margin=dict(b=100),
            hovermode='x unified'
        )
        
        col_chart1, col_chart2 = st.columns([2, 1])
        with col_chart1:
            st.plotly_chart(fig2, use_container_width=True)
            
        with col_chart2:
            tot_int = params.get('n_terminaciones', 0) + params.get('n_rma', 0) + params.get('n_cambio_zona', 0) + params.get('n_limpieza', 0) + params.get('n_reactivacion', 0)
            st.markdown(f"#### CANTIDAD DE ACTIVIDAD")
            st.markdown(f"**Total: {tot_int}**")
            
            fig_act = go.Figure()
            x_act = ["Reactivación", "Limpieza y<br>Estimulación", "Cambio de Zona", "RMA", "Terminaciones"]
            y_act = [params.get('n_reactivacion', 0), params.get('n_limpieza', 0), params.get('n_cambio_zona', 0), params.get('n_rma', 0), params.get('n_terminaciones', 0)]
            
            fig_act.add_trace(go.Bar(
                x=x_act, y=y_act,
                marker_color='#1f77b4',
                text=y_act,
                textposition='outside'
            ))
            fig_act.update_layout(
                yaxis_title="# Intervenciones",
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=20, b=50),
                showlegend=False,
                xaxis=dict(tickangle=-45)
            )
            st.plotly_chart(fig_act, use_container_width=True)

    # ── TAB 3: Distribuciones NPV ─────────────────────────────────────────────
    with tab3:
        st.header("Distribuciones de Valor Presente (MMUSD)")


        # Nominal sums for annotation
        cf = econ_results['cash_flows']
        nom_pre   = float(np.mean(np.sum(cf['cf_pre_tax'],   axis=1)))
        nom_post  = float(np.mean(np.sum(cf['cf_post_tax'],  axis=1)))
        nom_state = float(np.mean(np.sum(cf['state_income'], axis=1)))
        nom_roy   = float(np.mean(np.sum(cf['royalty'],      axis=1)))

        c1, c2 = st.columns(2)
        ind = econ_results['indicators']
        with c1:
            st.plotly_chart(hist_plot(ind['npv_hpoc_pre'],  "VPN Pre-Impuesto HPOC",      '#1f77b4', nom_val=nom_pre),   use_container_width=True)
            st.plotly_chart(hist_plot(ind['npv_state'],     "VP Estado Venezolano Total", '#7B2FBE', nom_val=nom_state), use_container_width=True)
        with c2:
            st.plotly_chart(hist_plot(ind['npv_hpoc_post'], "VPN Post-Impuesto HPOC",     '#17becf', nom_val=nom_post),  use_container_width=True)
            st.plotly_chart(hist_plot(ind['npv_royalty'],   "VP Regalías",                '#2ca02c', nom_val=nom_roy),   use_container_width=True)


    # ── TAB 4: Flujo de Caja ──────────────────────────────────────────────────
    with tab4:
        st.header("Análisis de Flujo de Caja")
        inc_m  = np.mean(econ_results['cash_flows']['gross_income'], axis=0)
        cost_m = np.mean(econ_results['cash_flows']['capex'] + econ_results['cash_flows']['opex'] + econ_results['cash_flows']['abex'], axis=0)
        tax_royalty = np.mean(econ_results['cash_flows']['royalty'], axis=0)
        tax_int     = np.mean(econ_results['cash_flows']['int_tax'], axis=0)
        tax_islr    = np.mean(econ_results['cash_flows']['islr'], axis=0)
        net_m       = np.mean(econ_results['cash_flows']['cf_post_tax'], axis=0)

        fig4 = go.Figure()
        fig4.add_trace(go.Bar(x=dates, y=inc_m,   name='Ingresos Brutos',       marker_color='#17becf'))
        fig4.add_trace(go.Bar(x=dates, y=-cost_m,  name='Costos (CAPEX+OPEX+ABEX)', marker_color='#d62728'))
        fig4.add_trace(go.Bar(x=dates, y=-tax_royalty, name='Regalías',           marker_color='#a0aec0'))
        fig4.add_trace(go.Bar(x=dates, y=-tax_int,     name='Impuesto Integrado', marker_color='#718096'))
        fig4.add_trace(go.Bar(x=dates, y=-tax_islr,    name='ISLR',               marker_color='#4a5568'))
        fig4.add_trace(go.Scatter(x=dates, y=net_m, name='Flujo de Caja Neto',  line=dict(color='black', width=2)))
        fig4.update_layout(
            barmode='relative', title="Flujo de Caja Esperado (Media Monte Carlo)",
            xaxis_title="Fecha", yaxis_title="MM USD",
            legend=dict(orientation='h', yanchor='top', y=-0.2, xanchor='center', x=0.5),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
            margin=dict(b=100),
            hovermode='x unified'
        )
        st.plotly_chart(fig4, use_container_width=True)

    # ── TAB 5: Indicadores & Sensibilidad ─────────────────────────────────────
    with tab5:
        st.header("Resumen de Indicadores Económicos")
        ind = econ_results['indicators']

        def agg(arr):
            arr = np.asarray(arr, dtype=float)
            return {'Media': np.mean(arr), 'Desv Est': np.std(arr),
                    'Mínimo': np.min(arr), 'P10': np.percentile(arr,10),
                    'P50': np.percentile(arr,50), 'P90': np.percentile(arr,90),
                    'Máximo': np.max(arr)}

        # ── Grupo 1: Indicadores de Valor Presente (VP) ────────────────────────────────────
        st.markdown("#### 🏦 Indicadores de Valor Presente (VP)")
        df_vp = pd.DataFrame({
            "VP Regalías (MMUSD)":        agg(ind['npv_royalty']),
            "VP Imp. Integrado (MMUSD)":  agg(ind['npv_int_tax']),
            "VP ISLR (MMUSD)":            agg(ind.get('npv_islr', [0])),
            "VP Estado Total (MMUSD)":    agg(ind['npv_state']),
        }).T
        st.dataframe(df_vp.style.format("{:.2f}"), use_container_width=True)

        # ── Grupo 2: VPN HPOC ───────────────────────────────────────────────────────
        st.markdown("#### 💰 VPN HPOC (Rentabilidad 'High Performance Operation Consortia')")
        df_hpoc = pd.DataFrame({
            "VPN HPOC Pre-Tax (MMUSD)":   agg(ind['npv_hpoc_pre']),
            "VPN HPOC Post-Tax (MMUSD)":  agg(ind['npv_hpoc_post']),
        }).T
        st.dataframe(df_hpoc.style.format("{:.2f}"), use_container_width=True)

        # ── Grupo 3: Rentabilidad Relativa (IRR) ──────────────────────────────────────
        st.markdown("#### 📈 Indicadores de Rentabilidad Relativa (IRR / TIR)")
        c_irr1, c_irr2 = st.columns(2)
        with c_irr1: st.metric("IRR Pre-Tax (% anual)",  f"{ind['irr_pre_annual']:.2f}%")
        with c_irr2: st.metric("IRR Post-Tax (% anual)", f"{ind['irr_post_annual']:.2f}%")

        # ── Grupo 4: Eficiencia Operativa y Recuperación del Capital ──────────────
        st.markdown("#### ⚙️ Eficiencia Operativa y Recuperación del Capital")
        df_eff = pd.DataFrame({
            "MCE / Pico Inversión (MMUSD)":                  agg(ind['mce_mm']),
            "Tiempo Recuperación (Años)":                    agg(ind['payout_years']),
            "MOIC (Múltiplo Inversión)":                     agg(ind['moic']),
            "Punto de Equilibrio (Break-even) (USD/bbl)":    agg(ind.get('breakeven_price', [0])),
            "Máx. Req. Financiamiento Contratista (MMUSD)":  agg(ind.get('max_financing_mm', [0])),
        }).T
        st.dataframe(df_eff.style.format("{:.2f}"), use_container_width=True)

        # ── Grupo 5: Medida de Competitividad Internacional ──────────────────────────
        st.markdown("#### 🌍 Medida de Competitividad Internacional")
        df_comp = pd.DataFrame({
            "Government Take (%)": agg(ind['npv_gov_take']),
        }).T
        st.dataframe(df_comp.style.format("{:.2f}"), use_container_width=True)

        st.markdown("---")
        st.subheader("Análisis de Sensibilidad: Regalías vs Precio Aceite")
        cs1, cs2, cs3, cs4 = st.columns(4)
        with cs1: p1 = st.number_input("Precio 1 (USD/bl)", value=50.0)
        with cs2: p2 = st.number_input("Precio 2 (USD/bl)", value=60.0)
        with cs3: p3 = st.number_input("Precio 3 (USD/bl)", value=70.0)
        with cs4: p4 = st.number_input("Precio 4 (USD/bl)", value=80.0)

        if st.button("Ejecutar Sensibilidad", type="secondary"):
            with st.spinner("Calculando..."):
                rows = []
                for price in [p1, p2, p3, p4]:
                    for r in np.arange(30, 19, -1):
                        tp = params.copy()
                        tp['oil_price']    = price
                        tp['royalty_rate'] = float(r)
                        te = calculate_cash_flow(sim_results, tp)
                        ind_s = te['indicators']
                        rows.append({
                            'Precio Aceite': price, 'Regalía (%)': r,
                            'VPN HPOC Pre (MMUSD)':  np.mean(ind_s['npv_hpoc_pre']),
                            'VPN HPOC Post (MMUSD)': np.mean(ind_s['npv_hpoc_post']),
                            'Max Financ. (MMUSD)':   np.mean(ind_s.get('max_financing_mm', [0])),
                            'Gov Take (%)':          np.mean(ind_s['npv_gov_take']),
                            'IRR Post-Tax (%)':      float(ind_s['irr_post_annual']),
                            'Break-even (USD/bbl)':  np.mean(ind_s.get('breakeven_price', [0])),
                            'Payout (Years)':        np.mean(ind_s.get('payout_years', [0])),
                            'MCE (MMUSD)':           np.mean(ind_s.get('mce_mm', [0])),
                        })
                st.session_state['tab5_sens_df'] = pd.DataFrame(rows)
                # ── Guardar los precios configurados para uso en la exportación ──
                st.session_state['tab5_sens_prices'] = [p1, p2, p3, p4]

        if 'tab5_sens_df' in st.session_state:
            df_s = st.session_state['tab5_sens_df']
            
            def mk_pivot(col):
                return df_s.pivot(index='Regalía (%)', columns='Precio Aceite', values=col)

            pivot_pre  = mk_pivot('VPN HPOC Pre (MMUSD)')
            pivot_post = mk_pivot('VPN HPOC Post (MMUSD)')
            pivot_mf   = mk_pivot('Max Financ. (MMUSD)')
            pivot_gt   = mk_pivot('Gov Take (%)')
            pivot_irr  = mk_pivot('IRR Post-Tax (%)')
            pivot_be   = mk_pivot('Break-even (USD/bbl)')

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

            r2_c1, r2_c2, r2_c3 = st.columns(3)
            with r2_c1:
                st.markdown("#### Government Take (%)")
                st.dataframe(pivot_gt.style.background_gradient(cmap='Reds').format("{:.2f}%"), use_container_width=True)
            with r2_c2:
                st.markdown("#### IRR Post-Tax (% anual)")
                st.dataframe(pivot_irr.style.background_gradient(cmap='Greens').format("{:.2f}%"), use_container_width=True)
            with r2_c3:
                st.markdown("#### Punto de Equilibrio (USD/bbl)")
                st.dataframe(pivot_be.style.background_gradient(cmap='YlOrRd_r').format("{:.2f}"), use_container_width=True)


    # ── TAB 6: Government Take Sensibilidad ──────────────────────────────────
    with tab6:
        st.header("⚖️ Sensibilidad de Equilibrio Fiscal (Government Take)")
        st.markdown("""
        Esta herramienta busca las combinaciones de **Regalía**, **Impuesto Integrado** e **ISLR** que cumplen con un objetivo de **Government Take (GT)**.
        Los resultados se ordenan de mayor a menor rentabilidad para el contratista (**VPN Post-Tax**).
        """)
        
        cgt1, cgt2 = st.columns([1, 2])
        with cgt1:
            target_gt = st.number_input("Objetivo Government Take (%)", min_value=1.0, max_value=99.0, value=50.0, step=1.0)
            tolerance = st.slider("Tolerancia (+/- %)", 0.1, 5.0, 1.0, step=0.1)
            precision = st.radio("Precisión de búsqueda", ["Fina (1%)", "Media (2%)", "Gruesa (5%)"], index=0, horizontal=True)
        
        with cgt2:
            st.info(f"Se buscarán combinaciones que resulten en un GT entre **{(target_gt - tolerance):.1f}%** y **{(target_gt + tolerance):.1f}%**.")
            st.caption("Esta herramienta utiliza un modelo lineal de Valor Presente para evaluar miles de opciones instantáneamente.")

        st.markdown("### 🎚️ Rangos de Sensibilidad Fiscal")
        st.caption("Define los límites de búsqueda para cada parámetro. Se muestran los límites legales para referencia.")
        cr1, cr2, cr3 = st.columns(3)
        with cr1:
            range_royalty = st.slider("Regalía (%)", 0, 30, (20, 30), step=1)
            st.markdown("<div style='font-size: 0.8rem; color: #6c757d; margin-top: -15px;'>Mín: 0% | Máx: 30% (Ley 2026)</div>", unsafe_allow_html=True)
        with cr2:
            range_int_tax = st.slider("Impuesto Integrado (%)", 0, 15, (5, 15), step=1)
            st.markdown("<div style='font-size: 0.8rem; color: #6c757d; margin-top: -15px;'>Mín: 0% | Máx: 15% (Ley 2026)</div>", unsafe_allow_html=True)
        with cr3:
            range_islr = st.slider("ISLR (%)", 0, 50, (0, 50), step=1)
            st.markdown("<div style='font-size: 0.8rem; color: #6c757d; margin-top: -15px;'>Mín: 0% | Máx: 50% (Ley 2026)</div>", unsafe_allow_html=True)

        st.markdown("---")
        if st.button("🔍 Buscar Combinaciones Óptimas", type="primary"):
            with st.spinner("Realizando búsqueda ultra-rápida..."):
                # 1. Pre-calcular bases de Valor Presente (Media de iteraciones)
                dr = st.session_state['cfg'].get('discount_rate', 15.0) / 100.0
                mr = (1 + dr) ** (1/12) - 1
                n_periods = len(sim_results['dates'])
                dm = (1 + mr) ** np.arange(n_periods)
                
                # Acceso correcto a los flujos desde econ_results
                cf_bases = econ_results['cash_flows']
                
                # NPV de Ingreso Bruto y Costos Totales (CAPEX + OPEX + ABEX)
                gi_pv    = np.mean(np.sum(cf_bases['gross_income'] / dm, axis=1))
                costs_total_mm = cf_bases['capex'] + cf_bases['opex'] + cf_bases['abex']
                costs_pv = np.mean(np.sum(costs_total_mm / dm, axis=1))
                total_rent_pv = gi_pv - costs_pv
                
                if total_rent_pv <= 0:
                    st.error("El proyecto no genera renta económica positiva en estas condiciones. No es posible calcular el Government Take.")
                else:
                    # 2. Definir rangos según precisión
                    step = 1 if "Fina" in precision else (2 if "Media" in precision else 5)
                    r_range = np.arange(range_royalty[0], range_royalty[1] + 1, step)
                    i_range = np.arange(range_int_tax[0], range_int_tax[1] + 1, step)
                    s_range = np.arange(range_islr[0],    range_islr[1]    + 1, step)
                    
                    rows_gt = []
                    # 3. Evaluación aritmética ultra-rápida
                    for r_rate in r_range:
                        for i_rate in i_range:
                            for s_rate in s_range:
                                # Tasas en decimal
                                r_dec = r_rate / 100.0
                                i_dec = i_rate / 100.0
                                s_dec = s_rate / 100.0
                                
                                # Modelo Lineal
                                v_roy = r_dec * gi_pv
                                v_iih = i_dec * gi_pv
                                taxable_pv = gi_pv - v_roy - v_iih - costs_pv
                                v_islr = s_dec * max(0, taxable_pv)
                                
                                v_state = v_roy + v_iih + v_islr
                                v_hpoc_pre = taxable_pv
                                v_hpoc_post = taxable_pv - v_islr
                                
                                gt_calc = (v_state / total_rent_pv) * 100
                                
                                if abs(gt_calc - target_gt) <= tolerance:
                                    rows_gt.append({
                                        "Regalía (%)": r_rate,
                                        "Imp. Integrado (%)": i_rate,
                                        "ISLR (%)": s_rate,
                                        "VPN HPOC Pre-Tax (MMUSD)": v_hpoc_pre,
                                        "VPN HPOC Post-Tax (MMUSD)": v_hpoc_post,
                                        "Government Take (%)": gt_calc
                                    })
                    
                    if rows_gt:
                        st.session_state['tab6_gt_df'] = pd.DataFrame(rows_gt).sort_values("VPN HPOC Post-Tax (MMUSD)", ascending=False)
                    else:
                        st.session_state['tab6_gt_df'] = None
                        st.warning("No se encontraron combinaciones en el rango especificado. Intenta aumentar la tolerancia o ajustar el objetivo.")
                
        if 'tab6_gt_df' in st.session_state and st.session_state['tab6_gt_df'] is not None:
            df_gt_res = st.session_state['tab6_gt_df']
            
            st.markdown("---")
            st.subheader("📊 Dashboard de Optimización HPOC: VPN vs. Government Take")
            
            total_found = min(100, len(df_gt_res))
            display_count = total_found
            
            # Nuevo selector de margen de tolerancia visual solicitado (1-10%)
            if 'margen_tolerancia_viz' not in st.session_state:
                st.session_state['margen_tolerancia_viz'] = 1.0
            
            df_plot = df_gt_res.head(display_count).copy()
            
            # Categorías visuales dinámicas basadas en el slider de db_c1 (definido abajo pero usado aquí tras rerun)
            m_tol = st.session_state['margen_tolerancia_viz']
            cat_cumple = f"Cumple Meta ({target_gt-0.5:.1f} - {target_gt+0.5:.1f}%)"
            cat_prox = f"Proximidad Crítica ({target_gt-m_tol:.1f} - {target_gt-0.5:.1f}% y {target_gt+0.5:.1f} - {target_gt+m_tol:.1f}%)"
            
            def get_cat(gt):
                diff = abs(gt - target_gt)
                if diff <= 0.5:
                    return cat_cumple
                elif diff <= m_tol:
                    return cat_prox
                else:
                    return "Resto"
            
            df_plot['Categoria'] = df_plot['Government Take (%)'].apply(get_cat)
            
            # Filtrar "Resto de Escenarios" de la gráfica y lista
            df_viz = df_plot[df_plot['Categoria'] != "Resto"].copy()
            
            num_meta = len(df_viz[df_viz['Categoria'] == cat_cumple])
            max_vpn_cumple = df_viz[df_viz['Categoria'] == cat_cumple]['VPN HPOC Post-Tax (MMUSD)'].max() if num_meta > 0 else 0
            best_vpn_overall = df_plot['VPN HPOC Post-Tax (MMUSD)'].max() if len(df_plot) > 0 else 0
            
            db_c1, db_c2, db_c3 = st.columns([1, 2, 1])
            
            with db_c1:
                st.markdown("<span style='font-size:10px; font-weight:bold; color:#94a3b8;'>ESCENARIOS EN META</span>", unsafe_allow_html=True)
                
                # Volvemos al formato original: dos números fijos
                st.markdown(f"<h2 style='margin-top:-10px;'>{num_meta} <span style='font-size:16px; font-weight:normal; color:#94a3b8;'>de {total_found}</span></h2>", unsafe_allow_html=True)
                st.progress(num_meta / total_found if total_found > 0 else 0)
                
                # Selector de margen de tolerancia (1-10%) solicitado, debajo de la barra
                st.markdown("<br>", unsafe_allow_html=True)
                st.slider("Margen de Tolerancia Visual (%)", min_value=1.0, max_value=10.0, step=0.5, key="margen_tolerancia_viz", help="Ajusta el rango para considerar escenarios en 'Proximidad Crítica'")
                
                st.caption(f"Nota: {num_meta} escenarios cumplen la meta.")
                
                st.markdown("<br><span style='font-size:10px; font-weight:bold; color:#94a3b8;'>MÁXIMO VPN (CUMPLE)</span>", unsafe_allow_html=True)
                st.markdown(f"<h2 style='margin-top:-10px; color:#059669;'>${max_vpn_cumple:,.2f}M</h2>", unsafe_allow_html=True)
                st.caption("✅ Valor óptimo bajo restricción")
                
                st.markdown("<br><span style='font-size:10px; font-weight:bold; color:#94a3b8;'>MEJOR VPN ABSOLUTO</span>", unsafe_allow_html=True)
                st.markdown(f"<h2 style='margin-top:-10px; color:#2563eb;'>${best_vpn_overall:,.2f}M</h2>", unsafe_allow_html=True)
                st.caption("📈 Independiente de la meta")
                
            with db_c2:
                if len(df_viz) > 0:
                    fig = px.scatter(df_viz, 
                                     x="Government Take (%)", 
                                     y="VPN HPOC Post-Tax (MMUSD)",
                                     color="Categoria",
                                     color_discrete_map={cat_cumple: "#10b981", cat_prox: "#64748b"},
                                     hover_data=["Regalía (%)", "Imp. Integrado (%)", "ISLR (%)"],
                                     title="Análisis de Proximidad a la Meta")
                    fig.add_vline(x=target_gt, line_dash="dash", line_color="#ef4444", annotation_text=f"META {target_gt}%")
                    fig.update_traces(marker=dict(size=14, opacity=0.9, line=dict(width=1, color='white')))
                    
                    # Ocultar el título nativo del eje X y agregarlo como anotación a la derecha
                    fig.update_xaxes(title_text="")
                    fig.add_annotation(
                        x=1, y=-0.12,
                        xref='paper', yref='paper',
                        xanchor='right', yanchor='top',
                        text="Government Take (%)",
                        showarrow=False,
                        font=dict(size=12, color="#64748b")
                    )
                    
                    fig.update_layout(
                        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="left", x=0, title=""),
                        margin=dict(b=80)
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No hay escenarios en el rango visual (Meta +/- 1.0%). Amplía la tolerancia en la búsqueda.")
            
            with db_c3:
                st.markdown(f"**Top Resultados (Visualizados)**")
                with st.container(height=450):
                    if len(df_viz) == 0:
                        st.caption("No hay escenarios para mostrar.")
                    for i, (_, row) in enumerate(df_viz.iterrows()):
                        bg_color = "#ecfdf5" if row['Categoria'] == cat_cumple else "#f8fafc"
                        border_color = "#a7f3d0" if row['Categoria'] == cat_cumple else "#e2e8f0"
                        st.markdown(f"""
                        <div style='background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 12px; padding: 12px; margin-bottom: 10px;'>
                            <div style='display: flex; justify-content: space-between; margin-bottom: 5px;'>
                                <span style='font-size: 0.75rem; font-weight: bold; color: #64748b;'>RANK {i+1}</span>
                                <span style='font-size: 0.75rem; font-weight: bold; background-color: #e2e8f0; padding: 2px 8px; border-radius: 10px;'>GT: {row['Government Take (%)']:.2f}%</span>
                            </div>
                            <div style='font-size: 1.4rem; font-weight: 900; color: #1e293b; margin: 5px 0;'>
                                ${row['VPN HPOC Post-Tax (MMUSD)']:.2f} <span style='font-size: 0.7rem; font-weight: normal; color: #94a3b8;'>MMUSD</span>
                            </div>
                            <div style='display: flex; gap: 5px; margin-top: 8px;'>
                                <span style='font-size: 0.7rem; background-color: rgba(255,255,255,0.6); border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px;'>R: {row['Regalía (%)']:.0f}%</span>
                                <span style='font-size: 0.7rem; background-color: rgba(255,255,255,0.6); border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px;'>Ii: {row['Imp. Integrado (%)']:.0f}%</span>
                                <span style='font-size: 0.7rem; background-color: rgba(255,255,255,0.6); border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px;'>I: {row['ISLR (%)']:.0f}%</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
            
            with st.expander("Ver Tabla de Datos Completa", expanded=False):
                st.dataframe(
                    df_gt_res.head(100).style.format({
                        "Regalía (%)": "{:.0f}%",
                        "Imp. Integrado (%)": "{:.0f}%",
                        "ISLR (%)": "{:.0f}%",
                        "VPN HPOC Pre-Tax (MMUSD)": "{:.2f}",
                        "VPN HPOC Post-Tax (MMUSD)": "{:.2f}",
                        "Government Take (%)": "{:.2f}%"
                    }).background_gradient(subset=["VPN HPOC Post-Tax (MMUSD)"], cmap="Greens"),
                    use_container_width=True
                )




    # --- This block was moved below to be global ---


elif page == NAV_COMPARE:
    # ── Integrated STORM-Viewer (Comparador) ──────────────────────────────────
    st.title("🔬 Comparador de Escenarios (STORM-Viewer)")
    st.markdown("Carga múltiples escenarios (.json) exportados desde el Simulador para compararlos visualmente.")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📂 Cargar Escenarios")
    st.sidebar.caption("Sube archivos `.json` exportados.")
    
    uploaded_files = st.sidebar.file_uploader(
        "Archivos de Escenario (.json)",
        type=["json"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    if not uploaded_files:
        st.info("👆 Carga al menos un archivo `.json` desde la barra lateral para comenzar.")
    else:
        import json
        import numpy as np
        PALETTE = ["#2196F3", "#FF9800", "#4CAF50", "#E91E63", "#9C27B0", "#00BCD4", "#F44336", "#8BC34A"]
        scenarios = []
        for idx, uf in enumerate(uploaded_files):
            try:
                data = json.loads(uf.read())
                data['_color'] = PALETTE[idx % len(PALETTE)]
                scenarios.append(data)
            except Exception as e:
                st.error(f"Error al cargar {uf.name}: {e}")

        if scenarios:
            def ind_mean(sc, key):
                arr = sc['indicators'].get(key, [0.0])
                return float(np.mean(arr))

            # --- SECTION 1: BUBBLE CHART ---
            st.markdown("---")
            st.subheader("📊 Análisis Comparativo de KPI (Burbujas)")
            c1, c2 = st.columns(2)
            y_axis_opt = c1.selectbox("Indicador eje Y (KPI)", ["VPN HPOC Post-Tax (MMUSD)", "VPN HPOC Pre-Tax (MMUSD)", "IRR Post-Tax (%)", "MOIC (Múltiplo)"])
            bubble_size_opt = c2.selectbox("Tamaño de burbuja", ["Np P50 (MMbls)", "Np P10 (MMbls)", "Np P90 (MMbls)"])

            y_key_map = {
                "VPN HPOC Post-Tax (MMUSD)": ("npv_hpoc_post", False),
                "VPN HPOC Pre-Tax (MMUSD)":  ("npv_hpoc_pre",  False),
                "IRR Post-Tax (%)":          ("irr_post_annual", True),
                "MOIC (Múltiplo)":           ("moic", False),
            }
            size_key_map = {"Np P50 (MMbls)": "np_p50", "Np P10 (MMbls)": "np_p10", "Np P90 (MMbls)": "np_p90"}

            bubble_fig = go.Figure()
            for sc in scenarios:
                p = sc['params']
                y_key, is_scalar = y_key_map[y_axis_opt]
                y_val = float(sc['indicators'].get(y_key, 0.0)) if is_scalar else ind_mean(sc, y_key)
                np_val = sc.get('production', {}).get(size_key_map[bubble_size_opt], 1.0)
                
                tot_int = p.get('n_terminaciones', p.get('n_interventions', 0)) + p.get('n_rma', 0) + p.get('n_cambio_zona', 0) + p.get('n_limpieza', 0) + p.get('n_reactivacion', 0)

                bubble_fig.add_trace(go.Scatter(
                    x=[tot_int], y=[y_val], mode='markers+text',
                    name=p.get('esc_name', 'N/A'),
                    marker=dict(size=max(np_val * 3, 18), color=sc['_color'], opacity=0.82, line=dict(color='white', width=2)),
                    text=[p.get('esc_name', 'N/A')], textposition='top center',
                    customdata=[[p.get('esc_name', ''), p.get('esc_desc', ''), np_val, ind_mean(sc, 'npv_gov_take')]],
                    hovertemplate="<b>%{customdata[0]}</b><br>Intervenciones (Total): %{x}<br>"+y_axis_opt+": %{y:.2f}<br>Np P50: %{customdata[2]:.2f} MMbls<br>Gov. Take: %{customdata[3]:.1f}%<extra></extra>"
                ))
            bubble_fig.update_layout(xaxis_title="N° de Intervenciones", yaxis_title=y_axis_opt, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(248,249,250,0.8)')
            st.plotly_chart(bubble_fig, use_container_width=True)

            # --- SECTION 2: DETAIL CARD ---
            st.markdown("---")
            st.subheader("📋 Detalle por Escenario")
            sel_esc_name = st.radio("Seleccionar Escenario para detalle:", [s['params'].get('esc_name', '') for s in scenarios], horizontal=True)
            sel_sc = next(s for s in scenarios if s['params'].get('esc_name', '') == sel_esc_name)
            sel_color = sel_sc['_color']
            
            m_cols = st.columns(6)
            metrics = [
                ("VPN Post-Tax", f"{ind_mean(sel_sc, 'npv_hpoc_post'):.1f} MMUSD"),
                ("IRR Post-Tax", f"{float(sel_sc['indicators'].get('irr_post_annual', 0.0)):.2f}%"),
                ("MOIC", f"{ind_mean(sel_sc, 'moic'):.2f}x"),
                ("Gov. Take", f"{ind_mean(sel_sc, 'npv_gov_take'):.1f}%"),
                ("MCE", f"{ind_mean(sel_sc, 'mce_mm'):.1f} MMUSD"),
                ("Payout", f"{ind_mean(sel_sc, 'payout_years'):.1f} Años"),
            ]
            for col, (label, val) in zip(m_cols, metrics):
                col.metric(label, val)

            # Detalle expandido del escenario seleccionado
            st.markdown(f"### 🔍 Inspección Detallada: {sel_esc_name}")
            t_det1, t_det2, t_det3, t_det4, t_det5, t_det6 = st.tabs(["🏗️ Cascada Fiscal", "🛢️ Pronósticos", "💸 Egresos", "📈 Distribuciones", "💼 Flujo de Caja", "🎯 Sensibilidad"])

            with t_det1:
                # --- WATERFALL ---
                st.subheader("Cascada Fiscal por Barril (USD/boe) — Ley 2026")
                prod_sel = sel_sc.get('production', {})
                boe_total = prod_sel.get('np_p50', 1.0) * 1e6
                def nom_total(sc, key):
                    arr = sc['cash_flows'].get(key, [[0.0]])
                    return float(np.mean(np.sum(arr, axis=1)))

                comp = {
                    "Precio Bruto": nom_total(sel_sc, 'gross_income'),
                    "(-) Regalías": -nom_total(sel_sc, 'royalty'),
                    "(-) Imp. Int": -nom_total(sel_sc, 'int_tax'),
                    "(-) CAPEX": -nom_total(sel_sc, 'capex'),
                    "(-) OPEX": -nom_total(sel_sc, 'opex'),
                    "(-) ABEX": -nom_total(sel_sc, 'abex'),
                    "(-) ISLR": -nom_total(sel_sc, 'islr'),
                    "Utilidad Neta": nom_total(sel_sc, 'cf_post_tax')
                }
                wf_vals = [(v * 1e6) / boe_total for v in comp.values()]
                wf_fig = go.Figure(go.Waterfall(
                    orientation="v", x=list(comp.keys()), y=wf_vals,
                    measure=["absolute","relative","relative","relative","relative","relative","relative","total"],
                    decreasing=dict(marker_color="#EF5350"), increasing=dict(marker_color=sel_color),
                    totals=dict(marker_color="#1A237E"), text=[f"{v:+.2f}" for v in wf_vals], textposition="outside"
                ))
                wf_fig.update_layout(yaxis_title="USD / Barril", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(248,249,250,0.8)', height=500)
                st.plotly_chart(wf_fig, use_container_width=True)

            with t_det2:
                # --- FORECASTS ---
                st.subheader("Pronósticos de Producción")
                sc_dates = sel_sc.get('dates', [])
                
                if 'Qo' in prod_sel and 'reserves_oil' in sel_sc:
                    c1, c2 = st.columns(2)
                    with c1:
                        st.plotly_chart(plot_dual(
                            sc_dates, np.array(prod_sel['Qo']), np.array(prod_sel['NP']),
                            sel_sc['reserves_oil'], "Pronóstico Integral de Aceite (Bruta)", "Gasto (bpd)", "Np (MMbls)", "green"
                        ), use_container_width=True)
                        st.plotly_chart(reserves_bar(
                            sel_sc['reserves_oil'], "Reservas de Aceite (MMb)",
                            '#1a1a2e', '#1f77b4', '#74b9ff', "MMb"
                        ), use_container_width=True)

                    with c2:
                        st.plotly_chart(plot_dual(
                            sc_dates, np.array(prod_sel['Qg']), np.array(prod_sel['GP']),
                            sel_sc['reserves_gas'], "Pronóstico Integral de Gas (Bruta)", "Gasto (Mpcd)", "Gp (MMMpc)", "#d62728"
                        ), use_container_width=True)
                        st.plotly_chart(reserves_bar(
                            sel_sc['reserves_gas'], "Reservas de Gas (MMMpc)",
                            '#1a1a2e', '#d62728', '#ff7f7f', "MMMpc"
                        ), use_container_width=True)
                else:
                    st.warning("⚠️ El archivo JSON cargado es de una versión anterior y no contiene los vectores completos de producción. Por favor, vuelve al simulador, carga los datos, ejecuta la simulación y descarga el archivo JSON actualizado.")

            with t_det3:
                # --- EXPENDITURES ---
                st.subheader("Flujo de Egresos Mensual")
                c_m = np.mean(sel_sc['cash_flows'].get('capex', [[0]]), axis=0)
                o_m = np.mean(sel_sc['cash_flows'].get('opex', [[0]]), axis=0)
                a_m = np.mean(sel_sc['cash_flows'].get('abex', [[0]]), axis=0)
                cum_c = np.cumsum(c_m + o_m + a_m)
                
                ind = sel_sc['indicators']
                c_cap, c_op, c_ab = st.columns(3)
                card_tpl = """
                <div style="background: white; border-left: 5px solid #00d4ff; padding: 12px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 15px;">
                    <div style="color: #6c757d; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px;">{label}</div>
                    <div style="display: flex; flex-direction: column;">
                        <div style="color: #0c1c3e; font-size: 1.6rem; font-weight: 800; line-height: 1.2;">{vp} <span style="font-size: 0.8rem; font-weight: 400; color: #00d4ff;">MMUSD (VP)</span></div>
                        <div style="color: #a0aec0; font-size: 1.0rem; font-weight: 600; margin-top: 4px;">{nominal} <span style="font-size: 0.7rem; font-weight: 400;">Nominal</span></div>
                    </div>
                </div>
                """
                
                # Use safely get to avoid errors if the key isn't in older JSON
                vp_capex = np.mean(ind.get('npv_capex', [0.0]))
                vp_opex  = np.mean(ind.get('npv_opex', [0.0]))
                vp_abex  = np.mean(ind.get('npv_abex', [0.0]))
                
                with c_cap: st.markdown(card_tpl.format(label="CAPEX TOTAL", vp=f"{vp_capex:.2f}", nominal=f"{np.sum(c_m):.2f}"), unsafe_allow_html=True)
                with c_op:  st.markdown(card_tpl.format(label="OPEX TOTAL",  vp=f"{vp_opex:.2f}",  nominal=f"{np.sum(o_m):.2f}"),  unsafe_allow_html=True)
                with c_ab:  st.markdown(card_tpl.format(label="ABEX TOTAL",  vp=f"{vp_abex:.2f}",  nominal=f"{np.sum(a_m):.2f}"),  unsafe_allow_html=True)

                fig_ex = go.Figure()
                fig_ex.add_trace(go.Bar(x=sc_dates, y=c_m, name="CAPEX", marker_color='#1f77b4'))
                fig_ex.add_trace(go.Bar(x=sc_dates, y=o_m, name="OPEX", marker_color='#ff7f0e'))
                fig_ex.add_trace(go.Bar(x=sc_dates, y=a_m, name="ABEX", marker_color='#2ca02c'))
                fig_ex.add_trace(go.Scatter(x=sc_dates, y=cum_c, name='Costo Acumulado', yaxis='y2', line=dict(color='black', width=3)))
                
                fig_ex.update_layout(
                    barmode='stack', title="Inversiones y Gastos Esperados (Media Monte Carlo)",
                    xaxis_title="Fecha", yaxis_title="Desembolso Mensual (MMUSD)",
                    yaxis2=dict(title="Costo Acumulado (MMUSD)", overlaying='y', side='right'),
                    legend=dict(orientation='h', yanchor='top', y=-0.2, xanchor='center', x=0.5),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(b=100), hovermode='x unified'
                )
                st.plotly_chart(fig_ex, use_container_width=True)

            with t_det4:
                # --- DISTRIBUTIONS ---
                st.subheader("Distribución de Probabilidad VPN (MMUSD)")
                
                cf = sel_sc['cash_flows']
                ind = sel_sc['indicators']
                
                if isinstance(ind.get('npv_hpoc_post'), list) and len(ind['npv_hpoc_post']) > 1:
                    nom_pre   = float(np.mean(np.sum(cf.get('cf_pre_tax', [[0]]), axis=1)))
                    nom_post  = float(np.mean(np.sum(cf.get('cf_post_tax', [[0]]), axis=1)))
                    nom_state = float(np.mean(np.sum(cf.get('state_income', [[0]]), axis=1)))
                    nom_roy   = float(np.mean(np.sum(cf.get('royalty', [[0]]), axis=1)))
                    
                    cd1, cd2 = st.columns(2)
                    with cd1:
                        st.plotly_chart(hist_plot(ind.get('npv_hpoc_pre', [0]), "VPN Pre-Impuesto HPOC", '#1f77b4', nom_val=nom_pre), use_container_width=True)
                        st.plotly_chart(hist_plot(ind.get('npv_state', [0]), "VPN Estado Venezolano Total", '#7B2FBE', nom_val=nom_state), use_container_width=True)
                    with cd2:
                        st.plotly_chart(hist_plot(ind.get('npv_hpoc_post', [0]), "VPN Post-Impuesto HPOC", '#17becf', nom_val=nom_post), use_container_width=True)
                        st.plotly_chart(hist_plot(ind.get('npv_royalty', [0]), "VPN Regalías", '#2ca02c', nom_val=nom_roy), use_container_width=True)
                else:
                    st.warning("Este archivo JSON no contiene iteraciones Monte Carlo múltiples.")

            with t_det5:
                # --- FLUJO DE CAJA ---
                st.subheader("Análisis de Flujo de Caja")
                inc_m  = np.mean(sel_sc['cash_flows'].get('gross_income', [[0]]), axis=0)
                cost_m = np.mean(np.array(sel_sc['cash_flows'].get('capex', [[0]])) + np.array(sel_sc['cash_flows'].get('opex', [[0]])) + np.array(sel_sc['cash_flows'].get('abex', [[0]])), axis=0)
                tax_m  = np.mean(np.array(sel_sc['cash_flows'].get('royalty', [[0]])) + np.array(sel_sc['cash_flows'].get('int_tax', [[0]])) + np.array(sel_sc['cash_flows'].get('islr', [[0]])), axis=0)
                net_m  = np.mean(sel_sc['cash_flows'].get('cf_post_tax', [[0]]), axis=0)

                fig4 = go.Figure()
                fig4.add_trace(go.Bar(x=sc_dates, y=inc_m, name='Ingresos Brutos', marker_color='#17becf'))
                fig4.add_trace(go.Bar(x=sc_dates, y=-cost_m, name='Costos (CAPEX+OPEX+ABEX)', marker_color='#d62728'))
                fig4.add_trace(go.Bar(x=sc_dates, y=-tax_m, name='Impuestos y Regalías', marker_color='#7f7f7f'))
                fig4.add_trace(go.Scatter(x=sc_dates, y=net_m, name='Flujo de Caja Neto', line=dict(color='black', width=2)))
                fig4.update_layout(
                    barmode='relative', xaxis_title="Fecha", yaxis_title="MM USD",
                    legend=dict(orientation='h', yanchor='top', y=-0.2, xanchor='center', x=0.5),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig4, use_container_width=True)

            with t_det6:
                st.header("Resumen de Indicadores Económicos")
                ind_det = sel_sc['indicators']

                def agg(arr):
                    return {'Media': np.mean(arr), 'Desv Est': np.std(arr),
                            'Mínimo': np.min(arr), 'P10': np.percentile(arr,10),
                            'P50': np.percentile(arr,50), 'P90': np.percentile(arr,90),
                            'Máximo': np.max(arr)}

                # Safe aggregation in case some arrays are scalars in older JSONs
                def safe_agg(arr):
                    if isinstance(arr, (list, np.ndarray)) and len(arr) > 1: return agg(arr)
                    val = float(arr[0]) if isinstance(arr, (list, np.ndarray)) else float(arr)
                    return {'Media': val, 'Desv Est': 0.0, 'Mínimo': val, 'P10': val, 'P50': val, 'P90': val, 'Máximo': val}

                df_sum = pd.DataFrame({
                    "VPN Regalías (MMUSD)":          safe_agg(ind_det.get('npv_royalty', [0])),
                    "VPN Imp. Integrado (MMUSD)":    safe_agg(ind_det.get('npv_int_tax', [0])),
                    "VPN Estado Total (MMUSD)":      safe_agg(ind_det.get('npv_state', [0])),
                    "VPN HPOC Pre-Tax (MMUSD)":      safe_agg(ind_det.get('npv_hpoc_pre', [0])),
                    "VPN HPOC Post-Tax (MMUSD)":     safe_agg(ind_det.get('npv_hpoc_post', [0])),
                    "MCE / Pico Inversión (MMUSD)":  safe_agg(ind_det.get('mce_mm', [0])),
                    "Tiempo Recuperación (Años)":    safe_agg(ind_det.get('payout_years', [0])),
                    "MOIC (Múltiplo Inversión)":     safe_agg(ind_det.get('moic', [0])),
                    "Government Take (%)":           safe_agg(ind_det.get('npv_gov_take', [0])),
                }).T
                st.dataframe(df_sum.style.format("{:.2f}"), use_container_width=True)

                c_irr1, c_irr2 = st.columns(2)
                with c_irr1: st.metric("IRR Pre-Tax (% anual)",  f"{ind_det.get('irr_pre_annual', 0.0):.2f}%")
                with c_irr2: st.metric("IRR Post-Tax (% anual)", f"{ind_det.get('irr_post_annual', 0.0):.2f}%")

                st.markdown("---")
                st.subheader("Análisis de Sensibilidad: Regalías vs Precio Aceite")
                sens_data = sel_sc.get('sensibilidad', [])
                if sens_data:
                    df_s = pd.DataFrame(sens_data)
                    pivot_h = df_s.pivot(index='Regalía (%)', columns='Precio Aceite', values='VPN HPOC Post (MMUSD)')
                    pivot_g = df_s.pivot(index='Regalía (%)', columns='Precio Aceite', values='Gov Take (%)')
                    pivot_m = df_s.pivot(index='Regalía (%)', columns='Precio Aceite', values='MCE (MMUSD)')
                    pivot_p = df_s.pivot(index='Regalía (%)', columns='Precio Aceite', values='Payout (Years)')

                    r1_c1, r1_c2 = st.columns(2)
                    with r1_c1:
                        st.markdown("#### VPN HPOC Post-Tax (MMUSD)")
                        st.dataframe(pivot_h.style.background_gradient(cmap='Blues').format("{:.1f}"), use_container_width=True)
                    with r1_c2:
                        st.markdown("#### Government Take (%)")
                        st.dataframe(pivot_g.style.background_gradient(cmap='Reds').format("{:.2f}%"), use_container_width=True)

                    r2_c1, r2_c2 = st.columns(2)
                    with r2_c1:
                        st.markdown("#### MCE / Pico Inversión (MMUSD)")
                        st.dataframe(pivot_m.style.background_gradient(cmap='YlOrRd_r').format("{:.1f}"), use_container_width=True)
                    with r2_c2:
                        st.markdown("#### Payout Time / Tiempo Recuperación (Years)")
                        st.dataframe(pivot_p.style.background_gradient(cmap='YlGn_r').format("{:.2f}"), use_container_width=True)
                else:
                    st.warning("⚠️ Este archivo JSON no contiene datos de sensibilidad precalculados. Vuelva a exportar el archivo desde la etapa de Configuración.")

            # --- SECTION 4: TABLE ---
            if len(scenarios) > 1:

                st.markdown("---")
                st.subheader("📊 Comparativa Multi-Escenario")
                rows = []
                for sc in scenarios:
                    rows.append({
                        "Escenario": sc['params'].get('esc_name', 'N/A'),
                        "VPN Post-Tax": round(ind_mean(sc, 'npv_hpoc_post'), 2),
                        "IRR (%)": round(float(sc['indicators'].get('irr_post_annual', 0.0)), 2),
                        "MOIC (x)": round(ind_mean(sc, 'moic'), 2),
                        "MCE (MMUSD)": round(ind_mean(sc, 'mce_mm'), 2),
                        "Gov. Take (%)": round(ind_mean(sc, 'npv_gov_take'), 2),
                    })
                st.dataframe(pd.DataFrame(rows).set_index("Escenario"), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: GLOSARIO
# ══════════════════════════════════════════════════════════════════════════════
elif page == NAV_GLOSSARY:
    st.title("📖 Ayuda y Glosario de Indicadores")
    st.markdown("Consulta las definiciones conceptuales y operativas de los indicadores clave utilizados en la evaluación económica de proyectos de hidrocarburos bajo el marco legal de 2026.")

    lang = st.radio("Idioma / Language:", ["Español", "English"], horizontal=True)
    ES = (lang == "Español")

    GROUPS = [
        {
            "es_header": "🏦 Indicadores de Valor Presente (VP)",
            "en_header": "🏦 Present Value (PV) Indicators",
            "items": [
                {
                    "es_title": "VP Regalías (MMUSD)",
                    "en_title": "PV Royalties (MMUSD)",
                    "es_desc": "Valor presente de los pagos al Estado venezolano por derecho de extracción. La regalía de 2026 tiene un techo del 30% de los volúmenes extraídos, con posibilidad de reducción para garantizar la viabilidad económica del proyecto.",
                    "en_desc": "Present value of payments to the Venezuelan State for the extraction right. The 2026 royalty is capped at 30% of extracted volumes, with the possibility of reduction to guarantee economic viability."
                },
                {
                    "es_title": "VP Imp. Integrado (MMUSD)",
                    "en_title": "PV Integrated Tax / IIH (MMUSD)",
                    "es_desc": "Valor presente del Impuesto Integrado de Hidrocarburos (IIH), creado en 2026 para sustituir los antiguos gravámenes a la producción y exportación. Alícuota de hasta el 15% sobre ingresos brutos.",
                    "en_desc": "Present value of the Integrated Hydrocarbons Tax (IIH), created in 2026 to replace former production and export taxes. Rate capped at 15% on gross revenues."
                },
                {
                    "es_title": "VP ISLR (MMUSD)",
                    "en_title": "PV Income Tax / ISLR (MMUSD)",
                    "es_desc": "Valor Presente del Impuesto sobre la Renta. Mide la carga fiscal sobre utilidades netas. En la reforma de 2026 se establece hasta en un 50%, deducidos OPEX, CAPEX, Regalías e IIH.",
                    "en_desc": "Present Value of the Income Tax (ISLR). Measures fiscal burden on net profits. Under the 2026 reform, it is set at up to 50%, after deducting OPEX, CAPEX, royalties, and IIH."
                },
                {
                    "es_title": "VP Estado Total (MMUSD)",
                    "en_title": "PV Total State Take (MMUSD)",
                    "es_desc": "Indicador agregado: suma de VP Regalías + VP IIH + VP ISLR + Ventajas Especiales. Representa la magnitud total de la renta capturada por el Estado venezolano.",
                    "en_desc": "Aggregate indicator: sum of PV Royalties + PV IIH + PV ISLR + Special Advantages. Represents the total rent captured by the Venezuelan State."
                },
            ]
        },
        {
            "es_header": "💰 VPN HPOC (Rentabilidad 'High Performance Operation Consortia')",
            "en_header": "💰 NPV HPOC (Investor Profitability)",
            "items": [
                {
                    "es_title": "VPN HPOC Pre-Tax (MMUSD)",
                    "en_title": "NPV HPOC Pre-Tax (MMUSD)",
                    "es_desc": "Valor Presente Neto del flujo del operador después de cubrir OPEX, CAPEX, Regalías e IIH, pero antes del ISLR. Mide la rentabilidad operativa intrínseca independientemente del ISLR corporativo.",
                    "en_desc": "Net Present Value of the operator's cash flow after covering OPEX, CAPEX, Royalties, and IIH, but before ISLR. Measures intrinsic operational profitability regardless of corporate income tax."
                },
                {
                    "es_title": "VPN HPOC Post-Tax (MMUSD)",
                    "en_title": "NPV HPOC Post-Tax (MMUSD)",
                    "es_desc": "Indicador de rentabilidad final para el accionista. Valor presente de los flujos de caja netos después de cumplir todas las obligaciones fiscales, incluyendo el ISLR. Un VPN Post-Tax positivo indica que el proyecto supera la tasa de descuento exigida.",
                    "en_desc": "Final profitability indicator for the shareholder. Present value of net cash flows after all tax obligations including ISLR. A positive Post-Tax NPV indicates the project exceeds the required discount rate."
                },
            ]
        },
        {
            "es_header": "📈 Indicadores de Rentabilidad Relativa (IRR / TIR)",
            "en_header": "📈 Relative Profitability Indicators (IRR)",
            "items": [
                {
                    "es_title": "IRR Pre-Tax (% anual)",
                    "en_title": "IRR Pre-Tax (% annual)",
                    "es_desc": "Tasa Interna de Retorno calculada sobre el flujo antes del ISLR. Permite evaluar la eficiencia del proyecto frente a la carga fiscal sectorial (Regalía + IIH) sin el efecto del impuesto sobre beneficios.",
                    "en_desc": "Internal Rate of Return calculated on the pre-ISLR cash flow. Evaluates project efficiency against the sectoral fiscal burden (Royalty + IIH) without the income-tax effect."
                },
                {
                    "es_title": "IRR Post-Tax (% anual)",
                    "en_title": "IRR Post-Tax (% annual)",
                    "es_desc": "Rentabilidad anualizada definitiva del proyecto para la contratista, una vez cumplidas todas las obligaciones fiscales incluyendo el ISLR. Es la TIR que se compara con el WACC para decidir la viabilidad del proyecto.",
                    "en_desc": "Definitive annualized return for the contractor after all fiscal obligations including ISLR. This is the IRR compared against the WACC to decide project viability."
                },
            ]
        },
        {
            "es_header": "⚙️ Indicadores de Eficiencia Operativa y Recuperación del Capital",
            "en_header": "⚙️ Operational Efficiency and Capital Recovery Indicators",
            "items": [
                {
                    "es_title": "MCE / Pico Inversión (MMUSD)",
                    "en_title": "ECF / Investment Peak (MMUSD)",
                    "es_desc": "MCE (Margen de Caja Excedente): flujo de caja operativo remanente después de cubrir OPEX y compromisos fiscales inmediatos, destinado a financiar el CAPEX. Pico de Inversión: monto máximo de CAPEX en un solo año fiscal. ¿En qué momento el proyecto me debe más dinero?",
                    "en_desc": "ECF (Excess Cash Flow): operating cash flow remaining after OPEX and immediate tax obligations, available to fund CAPEX. Investment Peak: maximum CAPEX disbursed in a single fiscal year. At what point does the project owe me the most money?"
                },
                {
                    "es_title": "Tiempo Recuperación (Años)",
                    "en_title": "Payout Time (Years)",
                    "es_desc": "Tiempo en que los flujos de caja netos acumulados igualan la inversión inicial. Bajo la Ley 2026, la reducción de regalías busca acortar este periodo para mitigar el riesgo del inversionista.",
                    "en_desc": "Time for cumulative net cash flows to equal the initial investment. Under the 2026 Law, royalty reductions aim to shorten this period to reduce investor risk."
                },
                {
                    "es_title": "MOIC (Múltiplo Inversión)",
                    "en_title": "MOIC (Multiple on Invested Capital)",
                    "es_desc": "Indicador estático que muestra cuántas veces se multiplica el capital invertido durante la vida del proyecto. Complementa la IRR al mostrar la magnitud absoluta de la ganancia.",
                    "en_desc": "Static indicator showing how many times the invested capital is multiplied over project life. Complements the IRR by showing the absolute magnitude of the profit."
                },
                {
                    "es_title": "Punto de Equilibrio (Break-even Point) (USD/bbl)",
                    "en_title": "Break-even Point (USD/bbl)",
                    "es_desc": "Precio del crudo al cual el VPN Post-Tax del proyecto es igual a cero. Por debajo de este precio el proyecto destruye valor. Es fundamental para evaluar la resiliencia del proyecto ante caídas de precio del mercado.",
                    "en_desc": "Oil price at which the project's Post-Tax NPV equals zero. Below this price the project destroys value. It is fundamental for evaluating project resilience to market price drops."
                },
                {
                    "es_title": "Máximo Requerimiento de Financiamiento (Contratista) (MMUSD)",
                    "en_title": "Maximum Financing Requirement (Contractor) (MMUSD)",
                    "es_desc": "Máximo flujo de caja acumulado negativo del proyecto (valor absoluto). Representa la exposición de liquidez máxima que la contratista debe financiar externamente antes de que el proyecto genere flujo positivo. Es el dato clave para dimensionar líneas de crédito y la estructura de capital. ¿Cuánto crédito o capital externo necesito conseguir?",
                    "en_desc": "Maximum absolute negative cumulative cash flow of the project. Represents the peak liquidity exposure the contractor must finance externally before the project generates positive cash flow. It is the key figure for sizing credit lines and capital structure. How much credit or external capital do I need to obtain?"
                },
            ]
        },
        {
            "es_header": "🌍 Medida de Competitividad Internacional",
            "en_header": "🌍 International Competitiveness Measure",
            "items": [
                {
                    "es_title": "Government Take (%)",
                    "en_title": "Government Take (%)",
                    "es_desc": "Proporción de la renta económica total del proyecto capturada por el Estado (Regalías + IIH + ISLR). La reforma de 2026 busca ajustar el GT dinámicamente al rango 40–65%, competitivo con otros países de la región. Históricamente en Venezuela superó el 90%.",
                    "en_desc": "Proportion of total project economic rent captured by the State (Royalties + IIH + ISLR). The 2026 reform seeks to dynamically adjust GT to the 40–65% range, competitive with regional peers. Historically in Venezuela it exceeded 90%."
                },
            ]
        },
    ]

    st.markdown("---")
    for group in GROUPS:
        header = group["es_header"] if ES else group["en_header"]
        st.markdown(f"### {header}")
        for item in group["items"]:
            title = item["es_title"] if ES else item["en_title"]
            desc  = item["es_desc"]  if ES else item["en_desc"]
            with st.expander(f"**{title}**"):
                st.write(desc)
        st.markdown("")

# ── EXPORTACIÓN GLOBAL DE ESCENARIO (Disponible si hay resultados) ──────────

if 'sim_results' in st.session_state:
    import json
    import datetime

    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.ndarray):
                # Reducir peso del JSON redondeando a 3 decimales
                if np.issubdtype(obj.dtype, np.floating):
                    return np.round(obj, 3).tolist()
                return obj.tolist()
            if isinstance(obj, np.generic):
                if isinstance(obj, np.floating):
                    return round(float(obj), 3)
                return obj.item()
            if isinstance(obj, (pd.Timestamp, datetime.date, datetime.datetime)):
                return obj.isoformat()
            if isinstance(obj, pd.DatetimeIndex):
                return [d.isoformat() for d in obj]
            return super().default(obj)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📥 Exportar Escenario")
    st.sidebar.caption("Genera un archivo consolidado para el Visualizador.")
    
    # ALWAYS pull from session state to ensure consistency with what is shown in Module 1
    exp_sim_results  = st.session_state['sim_results']
    exp_econ_results = st.session_state['econ_results']
    exp_data_dict    = st.session_state['data_dict']
    exp_params       = st.session_state['params']
    
    def safe_res_exp(df, key):
        try:    return df.loc[key].iloc[0]
        except: return 0.0

    # Auto-generate sensitivity for export using the exact prices the user configured
    # Priority 1: use what was already computed and stored in session_state (tab5_sens_df)
    sens_export = []
    if 'tab5_sens_df' in st.session_state:
        df_existing = st.session_state['tab5_sens_df'].copy()
        # Ensure all required columns exist; recalculate missing ones
        sens_prices = st.session_state.get('tab5_sens_prices', None)
        needs_recalc = 'Payout (Years)' not in df_existing.columns or 'MCE (MMUSD)' not in df_existing.columns
        
        if needs_recalc and sens_prices:
            # Recalculate with the correct prices to get full column set
            for price in sens_prices:
                for r in np.arange(30, 19, -1):
                    tp = exp_params.copy()
                    tp['oil_price'] = price
                    tp['royalty_rate'] = float(r)
                    te = calculate_cash_flow(exp_sim_results, tp)
                    ind_exp = te['indicators']
                    sens_export.append({
                        'Precio Aceite':         price,
                        'Regalía (%)':           r,
                        'VPN HPOC Post (MMUSD)': float(np.mean(ind_exp['npv_hpoc_post'])),
                        'Gov Take (%)':          float(np.mean(ind_exp['npv_gov_take'])),
                        'MCE (MMUSD)':           float(np.mean(ind_exp['mce_mm'])),
                        'Payout (Years)':        float(np.mean(ind_exp['payout_years'])),
                        'Max Financ. (MMUSD)':   float(np.mean(ind_exp.get('max_financing_mm', [0]))),
                        'Break-even (USD/bbl)':  float(np.mean(ind_exp.get('breakeven_price', [0]))),
                    })
        else:
            # Use the stored DataFrame directly — rename columns to match STORM-Viewer schema
            col_map = {
                'VPN HPOC Post (MMUSD)': 'VPN HPOC Post (MMUSD)',
                'Max Financ. (MMUSD)':   'Max Financ. (MMUSD)',
                'Gov Take (%)':          'Gov Take (%)',
                'Break-even (USD/bbl)':  'Break-even (USD/bbl)',
                'Payout (Years)':        'Payout (Years)',
                'MCE (MMUSD)':           'MCE (MMUSD)',
            }
            for _, row in df_existing.iterrows():
                entry = {'Precio Aceite': row['Precio Aceite'], 'Regalía (%)': row['Regalía (%)']}
                for col in col_map:
                    if col in row:
                        entry[col] = float(row[col])
                sens_export.append(entry)
    else:
        # Fallback: use user-configured prices if available, else derive from base price
        sens_prices = st.session_state.get('tab5_sens_prices')
        if not sens_prices:
            base_p = exp_params.get('oil_price', 60.0)
            sens_prices = [base_p - 10, base_p, base_p + 10, base_p + 20]
        for price in sens_prices:
            for r in np.arange(30, 19, -1):
                tp = exp_params.copy()
                tp['oil_price'] = price
                tp['royalty_rate'] = float(r)
                te = calculate_cash_flow(exp_sim_results, tp)
                ind_exp = te['indicators']
                sens_export.append({
                    'Precio Aceite':         price,
                    'Regalía (%)':           r,
                    'VPN HPOC Post (MMUSD)': float(np.mean(ind_exp['npv_hpoc_post'])),
                    'Gov Take (%)':          float(np.mean(ind_exp['npv_gov_take'])),
                    'MCE (MMUSD)':           float(np.mean(ind_exp['mce_mm'])),
                    'Payout (Years)':        float(np.mean(ind_exp['payout_years'])),
                    'Max Financ. (MMUSD)':   float(np.mean(ind_exp.get('max_financing_mm', [0]))),
                    'Break-even (USD/bbl)':  float(np.mean(ind_exp.get('breakeven_price', [0]))),
                })

    # Include Fiscal Optimization (Module 6) results if available
    exp_gt_df = st.session_state.get('tab6_gt_df')
    gt_export = None
    if exp_gt_df is not None:
        gt_export = exp_gt_df.to_dict(orient='records')

    export_data = {
        'params': exp_params,
        'sim_timestamp': exp_params.get('esc_name', 'Escenario_Exportado'),
        'dates': exp_sim_results['dates'],
        'indicators': exp_econ_results['indicators'],
        'cash_flows': exp_econ_results['cash_flows'],
        'production': {
            'Qo': exp_sim_results['simulations']['Qo'],
            'NP': exp_sim_results['simulations']['NP'],
            'Qg': exp_sim_results['simulations']['Qg'],
            'GP': exp_sim_results['simulations']['GP'],
            'np_p10': float(np.percentile(exp_sim_results['simulations']['NP'][:,-1], 10)),
            'np_p50': float(np.percentile(exp_sim_results['simulations']['NP'][:,-1], 50)),
            'np_p90': float(np.percentile(exp_sim_results['simulations']['NP'][:,-1], 90)),
            'gp_p50': float(np.percentile(exp_sim_results['simulations']['GP'][:,-1], 50)),
        },
        'reserves_oil': {
            '1P': safe_res_exp(exp_data_dict['oil'], 'Reservas Aceite-1P (MMb)'),
            '2P': safe_res_exp(exp_data_dict['oil'], 'Reservas Aceite-2P (MMb)'),
            '3P': safe_res_exp(exp_data_dict['oil'], 'Reservas Aceite-3P (MMb)'),
        },
        'reserves_gas': {
            '1P': safe_res_exp(exp_data_dict['gas'], 'Reservas Gas-1P (MMMpc)'),
            '2P': safe_res_exp(exp_data_dict['gas'], 'Reservas Gas-2P (MMMpc)'),
            '3P': safe_res_exp(exp_data_dict['gas'], 'Reservas Gas-3P (MMMpc)'),
        },
        'sensibilidad': sens_export,
        'optimizacion_fiscal': gt_export
    }
    
    json_str = json.dumps(export_data, cls=NumpyEncoder)
    safe_name = str(exp_params.get('esc_name', 'Escenario')).replace(" ", "_").replace("/", "_")
    file_name = f"{safe_name}.json"
    
    st.sidebar.download_button(
        label=f"⬇️ Descargar {file_name} (Navegador)",
        data=json_str,
        file_name=file_name,
        mime="application/json",
        use_container_width=True
    )
    
    # ── GUARDADO DIRECTO A DISCO (Bypass de Memoria del Navegador) ──
    st.sidebar.markdown("---")
    st.sidebar.caption("O si el navegador se bloquea por tamaño, guárdalo directamente en la carpeta del visualizador:")
    if st.sidebar.button("💾 Enviar a STORM-Viewer-Standalone", use_container_width=True, type="primary"):
        try:
            target_dir = r"D:\3_Trabajo\48_PDVSA\CHIMIRE\STORM-Viewer-Standalone\scenarios"
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, file_name)
            
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(json_str)
                
            st.sidebar.success(f"¡Guardado exitosamente!\n\n`{file_name}` listo en el visualizador.")
        except Exception as e:
            st.sidebar.error(f"Error al guardar: {e}")


