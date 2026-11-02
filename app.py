import streamlit as st
import networkx as nx
import osmnx as ox
import folium
import math
import os
import json
import hashlib
import streamlit.components.v1 as components
from streamlit_folium import st_folium
import importlib
from html import escape
import r2i_engine
from candidate_routes import optimize_routes
from traffic_provider import get_traffic_snapshot
from assistant_context import build_route_context
from imagine_client import ImagineAPIError, chat_completion

# Streamlit reruns this file while keeping imported modules in sys.modules.
# Reload the engine so a newly added route helper is available after an edit.
r2i_engine = importlib.reload(r2i_engine)
load_network = r2i_engine.load_network
calculate_route_comparison = r2i_engine.calculate_route_comparison
calculate_external_route_comparison = r2i_engine.calculate_external_route_comparison
calculate_google_baseline = r2i_engine.calculate_google_baseline

st.set_page_config(page_title="R2I Eco-Routing Engine", layout="wide", page_icon="🌿")

# --- PAPER / BLUEPRINT DESIGN SYSTEM ---
ILLOCA_STYLE = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap');
    :root { --paper:#050608; --paper-light:#111318; --ink:#f0f1f4; --muted:#858b97; --line:#252831; --blue:#2347ff; --blue-dark:#1837d2; --orange:#f08364; }
    .stApp { color:var(--ink); background-color:var(--paper); background-image:radial-gradient(rgba(175,184,202,.12) .7px,transparent .8px); background-size:13px 13px; font-family:"DM Sans",Inter,"Segoe UI",sans-serif; }
    .stApp button,.stApp input,.stApp textarea,.stApp [data-baseweb] { font-family:"DM Sans",Inter,"Segoe UI",sans-serif; }
    [data-testid="stHeader"] { background:rgba(5,6,8,.96); }
    [data-testid="stToolbar"] { right:1rem; }
    [data-testid="stAppViewContainer"] { background:transparent; }
    [data-testid="stMain"] { color:var(--ink); }
    [data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li { color:#c2cad4; }
    [data-testid="stMainBlockContainer"] { max-width:1320px; padding-top:2.2rem; }
    [data-testid="stSidebar"] { background:#090a0d; border-right:1px solid #202229; box-shadow:8px 0 28px rgba(0,0,0,.22); }
    [data-testid="stSidebar"]>div:first-child { padding-top:1.35rem; }
    [data-testid="stSidebar"] h2 { color:#f0f1f4!important; font-family:"Space Grotesk",Inter,sans-serif; letter-spacing:-.045em; font-size:1.4rem; margin:0 0 .25rem; }
    .sidebar-brand { display:flex; align-items:center; gap:.7rem; margin:0 0 1.35rem; color:#e8ebf2; font:600 .69rem/1.35 "IBM Plex Mono",monospace; letter-spacing:.09em; }
    .sidebar-brand-mark { display:grid; place-items:center; width:34px; height:34px; color:white; background:#2347ff; border:1px solid #5671ff; font:700 1.1rem/1 "Space Grotesk",sans-serif; box-shadow:3px 3px 0 rgba(35,71,255,.25); }
    .sidebar-brand small { display:block; margin-top:.15rem; color:#818a9a; font:500 .58rem/1.4 "IBM Plex Mono",monospace; letter-spacing:.12em; }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,[data-testid="stSidebar"] label { color:#c5ced9!important; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color:#aab5c3!important; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color:#aab5c3!important; font-size:.88rem; }
    [data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stMarkdownContainer"] p { color:#d9e0e9!important; }
    [data-testid="stSidebar"] [data-baseweb="select"]>div { background:#111318!important; border:1px solid #292d36!important; color:#f0f1f4!important; border-radius:4px; min-height:44px; }
    [data-testid="stSidebar"] [data-baseweb="select"] input { color:#f0f1f4!important; }
    [data-testid="stSidebar"] [data-baseweb="select"] svg { fill:#c5ced9!important; }
    [data-testid="stSidebar"] [data-testid="stCheckbox"] label p { color:#d9e0e9!important; }
    [data-testid="stSidebar"] [role="slider"] { background:#2347ff!important; }
    [data-testid="stSidebar"] [data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] { background:#2347ff!important; border-color:#6f89ff!important; box-shadow:0 0 0 3px rgba(113,148,255,.18); }
    [data-testid="stSidebar"] [data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stTickBar"] { background:#344151!important; }
    [data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stMarkdownContainer"] { color:#c5ced9; }
    [data-testid="stSidebar"] [data-testid="stCheckbox"] input:checked+div { background:#2347ff!important; border-color:#6f89ff!important; }
    [data-testid="stSidebar"] [data-testid="stAlert"] { background:#111318!important; border:1px solid #292d36!important; color:#d9e0e9!important; }
    [data-testid="stSidebar"] [data-testid="stAlert"] p { color:#d9e0e9!important; }
    [data-testid="stSidebar"] hr { border-color:#292d36!important; margin:1.1rem 0!important; }
    [data-testid="stSidebar"] [data-testid="stElementContainer"] { margin-bottom:.12rem; }
    [data-testid="stSidebar"] [data-testid="stSelectbox"] label,[data-testid="stSidebar"] [data-testid="stSlider"] label { font-size:.88rem!important; font-weight:500!important; }
    [data-testid="stSidebar"] [data-testid="stCheckbox"] label { font-size:.88rem!important; }
    [data-testid="stSidebar"] [data-testid="stForm"] { padding:.95rem!important; border:1px solid #292d36!important; border-radius:12px!important; background:linear-gradient(155deg,rgba(17,19,24,.92),rgba(10,11,14,.92))!important; }
    [data-testid="stSidebar"] [data-testid="stForm"] [data-testid="stMarkdownContainer"] p { line-height:1.5; }
    [data-testid="stSidebar"] [data-testid="stExpander"] { border:1px solid #292d36!important; border-radius:9px!important; background:#0d0f13!important; }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary { min-height:44px; color:#dce2eb!important; font-weight:600; }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover { color:#fff!important; }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] button { min-width:36px; min-height:36px; }
    [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button { min-height:48px; margin-top:.35rem; color:#fff!important; background:#1837d2!important; border:1px solid #2347ff!important; border-radius:6px!important; font-size:.96rem!important; font-weight:600!important; box-shadow:0 0 0 1px rgba(35,71,255,.15)!important; transition:background .18s ease,box-shadow .18s ease,transform .18s ease; }
    [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button:hover { color:#fff!important; background:#2347ff!important; border-color:#4563ff!important; box-shadow:0 0 18px rgba(35,71,255,.22)!important; transform:translateY(-1px); }
    [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button:focus-visible { outline:3px solid #6f89ff!important; outline-offset:2px; }
    [data-testid="stSidebar"] [data-testid="stSlider"] { padding-top:.08rem; padding-bottom:.2rem; }
    [data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stMarkdownContainer"] p { font-size:.82rem; }
    .route-desk-intro { margin:.15rem 0 .9rem; color:#9ba5b5; font-size:.86rem; line-height:1.5; }
    .sidebar-section-kicker { margin:.9rem 0 .45rem; color:#8798c3; font:600 .65rem/1.4 "IBM Plex Mono",monospace; letter-spacing:.13em; }
    .sidebar-helper { margin:-.35rem 0 .7rem; color:#818a98; font-size:.76rem; line-height:1.45; }
    .sidebar-map-title { margin:.85rem 0 .45rem; color:#e7ebf2; font:600 .92rem/1.3 "Space Grotesk",sans-serif; }
    .st-key-route_assistant_panel { margin:.6rem 0 1rem; padding:1rem 1.1rem .85rem; border:1px solid #282d36; border-radius:12px; background:linear-gradient(145deg,rgba(17,19,24,.92),rgba(10,11,14,.94)); }
    .assistant-panel-heading { display:flex; align-items:center; justify-content:space-between; gap:.75rem; margin-bottom:.35rem; }
    .assistant-panel-title { color:#f0f1f4; font:600 1.08rem/1.3 "Space Grotesk",sans-serif; letter-spacing:-.025em; }
    .assistant-panel-tag { padding:.25rem .5rem; border:1px solid #29334f; border-radius:999px; color:#9eaeff; background:rgba(35,71,255,.09); font:600 .61rem "IBM Plex Mono",monospace; letter-spacing:.1em; }
    .assistant-comparison { margin:.6rem 0 .85rem; padding:.65rem .8rem; border-left:2px solid #2347ff; border-radius:0 8px 8px 0; background:#10131a; color:#d0d7e3; font-size:.82rem; line-height:1.5; }
    .assistant-comparison strong { color:#f1f3f8; font-weight:600; }
    .st-key-route_assistant_transcript { max-height:245px; overflow-y:auto; padding:.7rem .8rem; border:1px solid #252a33; border-radius:10px; background:#090b0f; scrollbar-color:#3a4352 #090b0f; }
    .assistant-chat-bubble { width:fit-content; max-width:88%; margin:.25rem 0 .55rem; padding:.55rem .7rem; border:1px solid #282c34; border-radius:2px; background:#111318; color:#d5d9e0; font-size:.86rem; line-height:1.5; white-space:pre-wrap; overflow-wrap:anywhere; }
    .assistant-chat-bubble.user { margin-left:auto; border-color:#30343d; background:#121419; }
    .assistant-chat-bubble.assistant { margin-right:auto; border-color:#282c34; background:#101216; }
    .assistant-chat-role { display:block; margin-bottom:.15rem; color:#9299a5; font:600 .59rem "IBM Plex Mono",monospace; letter-spacing:.1em; }
    .st-key-route_assistant_panel [data-testid="InputInstructions"] { display:none!important; }
    .st-key-route_assistant_panel [data-testid="stTextInput"] input { min-height:42px; }
    .st-key-route_assistant_panel [data-testid="stBaseButton-secondary"] { color:#c5ced9!important; background:#111318!important; border-color:#303641!important; box-shadow:none!important; }
    .st-key-route_assistant_panel [data-testid="stBaseButton-secondary"]:hover { color:#fff!important; border-color:#596477!important; background:#171a21!important; }
    .st-key-route_assistant_panel [data-testid="stBaseButton-primary"] { color:#fff!important; background:#1837d2!important; border:1px solid #2347ff!important; border-radius:4px!important; box-shadow:0 0 0 1px rgba(35,71,255,.15)!important; }
    .st-key-route_assistant_panel [data-testid="stBaseButton-primary"]:hover { background:#2347ff!important; border-color:#4563ff!important; }
    .st-key-route_assistant_panel [data-testid="stFormSubmitButton"] button { min-height:42px; color:#fff!important; background:#1837d2!important; border:1px solid #2347ff!important; border-radius:8px!important; font-weight:600!important; }
    .st-key-route_assistant_panel [data-testid="stFormSubmitButton"] button:hover { background:#2347ff!important; }
    .masthead { position:relative; max-width:1200px; margin:0 auto 1.4rem; padding:1.4rem 0 1rem; text-align:left; background:transparent; border:0; box-shadow:none; }
    .masthead:before { content:"R2I  /  URBAN ROUTING SYSTEM     ·     BENGALURU"; display:block; margin-bottom:.7rem; color:#8792aa; font:600 .68rem/1.3 "IBM Plex Mono",monospace; letter-spacing:.16em; }
    .masthead h1 { margin:0!important; color:var(--ink)!important; font:600 clamp(2.15rem,4vw,3.4rem)/1 "Space Grotesk",Inter,sans-serif!important; letter-spacing:-.065em!important; }
    .masthead p { max-width:600px; margin:1rem auto 0; color:#a1a6b1; font:400 clamp(.98rem,1.5vw,1.08rem)/1.55 "DM Sans",Inter,sans-serif; }
    .masthead .scribble { position:absolute; right:0; bottom:1.2rem; color:#7c8493; font:600 .65rem/1.3 ui-monospace,monospace; letter-spacing:.12em; }
    h2,h3 { color:var(--ink)!important; font-family:"Space Grotesk",Inter,sans-serif!important; letter-spacing:-.045em!important; }
    h3 { font-size:1.75rem!important; }
    hr { border-color:var(--line)!important; }
    [data-testid="stMetric"] { min-height:122px; padding:1.15rem 1.25rem!important; border:1px solid #39485b!important; border-radius:3px!important; background:rgba(17,19,24,.94)!important; box-shadow:3px 3px 0 rgba(0,0,0,.12); transition:border-color .18s ease,transform .18s ease; }
    [data-testid="stMetric"]:hover { border-color:var(--blue)!important; transform:translateY(-2px); }
    [data-testid="stMetricLabel"] { color:#aab5c3!important; font-size:.76rem!important; letter-spacing:.09em; text-transform:uppercase; }
    [data-testid="stMetricValue"] { color:#f0f1f4!important; font:600 1.9rem/1.2 "Space Grotesk",Inter,sans-serif!important; }
    [data-testid="stMetricDelta"] { font-size:.78rem!important; }
    .stButton>button { min-height:44px; color:#fff!important; background:var(--blue-dark)!important; border:1px solid var(--blue-dark)!important; border-radius:3px!important; font-weight:600!important; letter-spacing:.01em; box-shadow:3px 3px 0 rgba(36,75,184,.18); transition:background .18s ease,transform .18s ease; }
    .stButton>button:hover { background:var(--blue)!important; border-color:var(--blue)!important; color:white!important; transform:translateY(-1px); }
    .stButton>button:focus-visible,[data-baseweb="select"]:focus-within { outline:3px solid var(--orange)!important; outline-offset:2px; }
    [data-baseweb="select"]>div,[data-baseweb="input"]>div { background:#111318; border-color:#435166; color:#f2eee5; }
    [data-testid="stAlert"] { background:#111318!important; border:1px solid #292d36!important; color:#d9e0e9!important; }
    [data-testid="stAlert"] p { color:#d9e0e9!important; }
    [data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] { background:#2347ff!important; border-color:#6f89ff!important; }
    [data-testid="stSlider"] [data-testid="stTickBar"] { background:#344151!important; }
    [data-testid="stCheckbox"] input:checked+div { background:#2347ff!important; border-color:#6f89ff!important; }
    [data-testid="stRadio"] label,[data-testid="stSelectbox"] label,[data-testid="stSlider"] label { color:#d9e0e9!important; }
    [data-testid="stMarkdownContainer"] h1,[data-testid="stMarkdownContainer"] h2,[data-testid="stMarkdownContainer"] h3 { color:#f0f1f4!important; }
    [data-testid="stAlert"] { border-radius:2px!important; }
    iframe[title="streamlit_folium.st_folium"] { border:1px solid #39485b; border-radius:3px; }
    .map-heading { display:flex; align-items:end; justify-content:space-between; gap:1rem; margin:1.1rem 0 .8rem; padding-bottom:.8rem; border-bottom:1px solid #252831; }
    .map-heading .eyebrow { color:#747d8e; font:600 .65rem "IBM Plex Mono",monospace; letter-spacing:.15em; }
    .map-heading h2 { margin:.4rem 0 0; color:#f0f1f4!important; font:500 clamp(1.35rem,2.3vw,2rem)/1.1 "Space Grotesk",Inter,sans-serif!important; letter-spacing:-.045em!important; }
    .map-status { display:flex; align-items:center; gap:.55rem; color:#9ba2af; font:600 .67rem "IBM Plex Mono",monospace; letter-spacing:.1em; white-space:nowrap; }
    .map-status:before { content:""; width:7px; height:7px; border-radius:50%; background:#2347ff; box-shadow:0 0 12px rgba(35,71,255,.75); }
    .route-compare-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.8rem; margin:.55rem 0 .45rem; }
    .route-compare-card { position:relative; min-height:128px; padding:1rem 1.1rem .9rem; background:linear-gradient(145deg,#12151a,#0d0f13); border:1px solid #2b303a; border-radius:10px; overflow:hidden; }
    .route-compare-card:after { content:""; position:absolute; inset:0 auto 0 0; width:3px; opacity:.95; }
    .route-compare-card.r2i { border-color:#244334; background:linear-gradient(145deg,rgba(22,55,37,.38),#0d1110 76%); }
    .route-compare-card.r2i:after { background:#287a4c; }
    .route-compare-card.google:after { background:repeating-linear-gradient(to bottom,#adb5c0 0 3px,transparent 3px 7px); }
    .route-compare-top { display:flex; justify-content:space-between; align-items:center; gap:.7rem; }
    .route-compare-label { display:flex; align-items:center; gap:.55rem; color:#c3ccd8; font:600 .66rem "IBM Plex Mono",monospace; letter-spacing:.1em; }
    .route-compare-swatch { display:inline-block; width:23px; flex:0 0 23px; border-top:2px dashed #adb5c0; }
    .route-compare-card.r2i .route-compare-swatch { border-top:3px solid #287a4c; }
    .route-compare-tag { color:#7e8998; font:500 .58rem "IBM Plex Mono",monospace; letter-spacing:.08em; white-space:nowrap; }
    .route-compare-card.r2i .route-compare-tag { color:#6ea987; }
    .route-compare-measures { display:flex; align-items:baseline; gap:.6rem; margin-top:.8rem; }
    .route-compare-value { color:#f2f4f7; font:600 1.55rem/1 "Space Grotesk",sans-serif; letter-spacing:-.04em; }
    .route-compare-unit { color:#aab3c0; font-size:.78rem; }
    .route-compare-bottom { display:flex; align-items:center; justify-content:space-between; gap:.5rem; margin-top:.55rem; color:#aab3c0; font-size:.77rem; }
    .route-compare-time { color:#e1e5eb; font-weight:600; }
    .route-compare-distance-delta { color:#828c99; font-size:.7rem; }
    .route-compare-summary { display:flex; justify-content:center; margin:0 0 .7rem; }
    .route-compare-summary span { padding:.32rem .65rem; border:1px solid #2b303a; border-radius:999px; background:#101217; color:#aeb8c5; font:500 .68rem "IBM Plex Mono",monospace; }
    [data-testid="stMetric"] { border-color:#252831!important; }
    iframe[title="streamlit_folium.st_folium"] { display:block; width:100%; background:#08090c; border:1px solid #303642!important; border-radius:16px!important; overflow:hidden; box-shadow:0 18px 48px rgba(0,0,0,.28); }
    [data-testid="stElementContainer"]:has(> iframe[title="streamlit_folium.st_folium"]) { overflow:hidden; border-radius:16px; }
    .stButton>button { box-shadow:0 0 0 1px rgba(35,71,255,.15); }
    .stButton>button:hover { box-shadow:0 0 20px rgba(35,71,255,.22); }
    @media(max-width:700px) { [data-testid="stMainBlockContainer"]{padding:1.3rem 1rem 2rem}.masthead{margin-bottom:1rem;padding:1rem 0 .8rem}.map-heading{align-items:start;flex-direction:column}.map-status{margin-top:.4rem}.masthead .scribble{position:static;display:block;margin-top:1rem}.route-compare-grid{grid-template-columns:1fr} }
    @media(prefers-reduced-motion:reduce) { *,*::before,*::after{scroll-behavior:auto!important;transition-duration:.01ms!important} }
</style>
"""
st.markdown(ILLOCA_STYLE, unsafe_allow_html=True)

# --- HEADER SECTION ---
st.markdown("""
<header class="masthead">
  <h1>Take the quieter road.</h1>
  <p>Compare a direct drive with a lower-impact route across Bengaluru.</p>
  <span class="scribble">R2I  /  NETWORK ACTIVE</span>
</header>
""", unsafe_allow_html=True)

def get_app_secret(name):
    """Read an optional Streamlit secret without failing when no file exists."""
    try:
        return st.secrets.get(name, "")
    except Exception:
        # Streamlit lazily parses secrets and raises StreamlitSecretNotFoundError
        # on lookup when neither configured secrets.toml path exists.
        return ""


GOOGLE_API_KEY = (
    os.getenv("GOOGLE_MAPS_SERVER_API_KEY")
    or os.getenv("GOOGLE_MAPS_API_KEY")
    or get_app_secret("google_maps_server_api_key")
    or get_app_secret("google_maps_api_key")
).strip()
GOOGLE_MAPS_BROWSER_KEY = (
    os.getenv("GOOGLE_MAPS_BROWSER_API_KEY")
    or os.getenv("GOOGLE_MAPS_API_KEY")
    or get_app_secret("google_maps_browser_api_key")
    or get_app_secret("google_maps_api_key")
).strip()
if "redacted" in GOOGLE_API_KEY.lower():
    GOOGLE_API_KEY = ""
if "redacted" in GOOGLE_MAPS_BROWSER_KEY.lower():
    GOOGLE_MAPS_BROWSER_KEY = ""

IMAGINE_API_KEY = (
    os.getenv("INFERENCE_CLOUD_API_KEY")
    or get_app_secret("inference_cloud_api_key")
).strip()
IMAGINE_API_ENDPOINT = (
    os.getenv("INFERENCE_CLOUD_ENDPOINT")
    or get_app_secret("inference_cloud_endpoint")
    or "https://aisuite.cirrascale.com/apis/v2"
).strip().rstrip("/")
IMAGINE_MODEL = (
    os.getenv("INFERENCE_CLOUD_MODEL")
    or get_app_secret("inference_cloud_model")
    or "Llama-3.1-8B"
).strip()

if 'route_results' not in st.session_state:
    st.session_state.route_results = None

@st.cache_data(ttl=1800, show_spinner=False)
def get_cached_city_route(start_coords, end_coords, vehicle_type, alpha):
    return calculate_external_route_comparison(start_coords, end_coords, vehicle_type, alpha)

# --- SIDEBAR (The Control Panel) ---
st.sidebar.markdown("<div class='sidebar-brand'><span class='sidebar-brand-mark'>R</span><span>R2I / ROUTE LAB<small>KORAMANGALA · IN</small></span></div>", unsafe_allow_html=True)

def find_nearest_node_manual(G, lon, lat):
    best_node = None
    min_dist = float('inf')
    for node, data in G.nodes(data=True):
        try:
            node_x = float(data.get('x', 0))
            node_y = float(data.get('y', 0))
            d = ((node_x - lon)**2 + (node_y - lat)**2)**0.5
            if d < min_dist:
                min_dist = d
                best_node = node
        except (TypeError, ValueError):
            continue
    return best_node

def distance_to_landmark_m(G, node, coordinates):
    """Approximate the snap distance from a selected place to the road graph."""
    lat, lon = coordinates
    node_lat = float(G.nodes[node]["y"])
    node_lon = float(G.nodes[node]["x"])
    east_m = (node_lon - lon) * 111_320 * math.cos(math.radians(lat))
    north_m = (node_lat - lat) * 111_320
    return math.hypot(east_m, north_m)

def build_google_comparison_map(result, zoom):
    """Render both the Google baseline and R2I overlay on a Google map."""
    google_path = json.dumps(result["standard_path"])
    r2i_path = json.dumps(result["eco_path"])
    copyrights = json.dumps(result.get("google_copyrights", "Google Maps"))
    eco_coordinates = result.get("eco_path", [])
    start_coords = json.dumps(result.get("start_coordinates", eco_coordinates[0] if eco_coordinates else [0, 0]))
    end_coords = json.dumps(result.get("end_coordinates", eco_coordinates[-1] if eco_coordinates else [0, 0]))
    start_label = json.dumps(result.get("start_label", "Starting point"))
    end_label = json.dumps(result.get("end_label", "Destination"))
    return f"""
    <style>
      html, body {{ margin:0; padding:0; overflow:hidden; }}
      #r2i-map-frame {{ position:relative; height:560px; width:100%; overflow:hidden; border-radius:14px; background:#101318; }}
      #r2i-google-map {{ height:100%; width:100%; }}
      #google-map-credit {{ position:absolute; top:10px; left:10px; z-index:2; max-width:calc(100% - 20px); padding:4px 7px; border:1px solid rgba(174,184,197,.18); border-radius:4px; background:rgba(8,10,13,.82); color:#aeb8c5; font:11px 'DM Sans',Arial,sans-serif; pointer-events:none; }}
    </style>
    <div id="r2i-map-frame">
      <div id="r2i-google-map"></div>
      <div id="google-map-credit"></div>
    </div>
    <script>
      const googlePath = {google_path}.map(([lat, lng]) => ({{lat, lng}}));
      const r2iPath = {r2i_path}.map(([lat, lng]) => ({{lat, lng}}));
      const mapCredit = {copyrights};
      const startPoint = {start_coords};
      const endPoint = {end_coords};
      const startName = {start_label};
      const endName = {end_label};
      function initR2IMap() {{
        const map = new google.maps.Map(document.getElementById('r2i-google-map'), {{
          center: googlePath[Math.floor(googlePath.length / 2)], zoom: {int(zoom)},
          mapTypeControl: false, streetViewControl: false, fullscreenControl: true,
          styles: [
            {{elementType:'geometry',stylers:[{{color:'#101318'}}]}},
            {{elementType:'labels',stylers:[{{visibility:'off'}}]}},
            {{featureType:'road',elementType:'geometry',stylers:[{{color:'#20252b'}}]}},
            {{featureType:'road',elementType:'geometry.stroke',stylers:[{{color:'#15191e'}}]}},
            {{featureType:'water',elementType:'geometry',stylers:[{{color:'#0b1015'}}]}},
            {{featureType:'poi',stylers:[{{visibility:'off'}}]}},
            {{featureType:'transit',stylers:[{{visibility:'off'}}]}},
            {{featureType:'administrative',elementType:'geometry',stylers:[{{color:'#171b20'}}]}}
          ]
        }});
        new google.maps.Polyline({{path:r2iPath,geodesic:true,strokeColor:'#071b11',strokeOpacity:.98,strokeWeight:10,zIndex:4}}).setMap(map);
        new google.maps.Polyline({{path:r2iPath,geodesic:true,strokeColor:'#174a2d',strokeOpacity:1,strokeWeight:5,zIndex:5}}).setMap(map);
        const googleRoute = new google.maps.Polyline({{
          path: googlePath, geodesic: true, strokeOpacity: 0,
          icons: [{{icon: {{path: google.maps.SymbolPath.CIRCLE, scale: 2.4,
            fillColor: '#aeb5c0', fillOpacity: .9, strokeOpacity: 0}}, offset: '0', repeat: '12px'}}],
          zIndex: 7
        }});
        googleRoute.setMap(map);
        new google.maps.Marker({{
          position: {{lat: startPoint[0], lng: startPoint[1]}}, map, title: 'Start: ' + startName,
          label: {{text: 'S', color: '#ffffff', fontWeight: '700'}},
          icon: {{path: google.maps.SymbolPath.CIRCLE, fillColor: '#28784d', fillOpacity: 1, strokeColor: '#ffffff', strokeWeight: 2, scale: 10}}, zIndex: 10
        }});
        new google.maps.Marker({{
          position: {{lat: endPoint[0], lng: endPoint[1]}}, map, title: 'Destination: ' + endName,
          label: {{text: 'D', color: '#111318', fontWeight: '700'}},
          icon: {{path: google.maps.SymbolPath.CIRCLE, fillColor: '#f0b44d', fillOpacity: 1, strokeColor: '#ffffff', strokeWeight: 2, scale: 10}}, zIndex: 10
        }});
        const bounds = new google.maps.LatLngBounds();
        googlePath.concat(r2iPath).forEach(point => bounds.extend(point));
        bounds.extend({{lat: startPoint[0], lng: startPoint[1]}});
        bounds.extend({{lat: endPoint[0], lng: endPoint[1]}});
        map.fitBounds(bounds, 42);
        document.getElementById('google-map-credit').textContent = mapCredit;
      }}
      window.gm_authFailure = function() {{
        document.getElementById('google-map-credit').textContent = 'Google Maps could not authenticate this key. Check Maps JavaScript API access and key restrictions.';
      }};
    </script>
    <script async defer src="https://maps.googleapis.com/maps/api/js?key={GOOGLE_MAPS_BROWSER_KEY}&callback=initR2IMap"></script>
    """

@st.cache_resource
def get_graph():
    try:
        G = load_network("bengaluru_grid.graphml")
        for node, data in G.nodes(data=True):
            if 'x' in data: G.nodes[node]['x'] = float(data['x'])
            if 'y' in data: G.nodes[node]['y'] = float(data['y'])
        if len(G) > 0:
            scc = max(nx.weakly_connected_components(G), key=len)
            G = G.subgraph(scc).copy()
        return G
    except Exception as e:
        st.error(f"Map data error: {e}. Please run fetch_map.py first.")
        return None

G = get_graph()

if G:
    landmarks = {
        "Sony World Signal · Koramangala": (12.932, 77.623),
        "Wipro Park · Koramangala": (12.930, 77.620),
        "Koramangala 5th Block": (12.938, 77.630),
        "Forum Mall · Koramangala": (12.933, 77.625),
        "St. John's Hospital": (12.940, 77.618),
        "Koramangala 1st Block": (12.928, 77.628),
        "Koramangala 3rd Block": (12.935, 77.621),
        "Koramangala 6th Block": (12.931, 77.635),
        "RV University": (12.912, 77.496),
        "Jayanagar 4th Block": (12.925, 77.583),
        "MG Road · Trinity Metro": (12.975, 77.606),
        "Cubbon Park": (12.976, 77.592),
        "Majestic · Kempegowda Bus Station": (12.976, 77.571),
        "Indiranagar Metro": (12.978, 77.640),
        "Whitefield · Hope Farm": (12.969, 77.750),
        "HSR Layout · Sector 2": (12.911, 77.639)
    }

    with st.sidebar.form("route_controls"):
        st.markdown("## Route desk")
        st.markdown("<p class='route-desk-intro'>Choose two places to compare routes across Bengaluru.</p>", unsafe_allow_html=True)
        st.markdown("<p class='sidebar-section-kicker'>01 / YOUR ROUTE</p>", unsafe_allow_html=True)
        start_landmark = st.selectbox("Starting point", list(landmarks.keys()), key="route_origin")
        end_landmark = st.selectbox("Destination", list(landmarks.keys()), index=1, key="route_destination")
        vehicle_type = st.selectbox("Vehicle", ["ICE", "EV"], format_func=lambda value: {"ICE": "Combustion · ICE", "EV": "Electric · EV"}[value], key="route_vehicle")
        alpha = st.slider("Eco ↔ time priority", 0.0, 1.0, 0.3, help="Choose what matters more: lower emissions or a shorter trip.", key="route_priority")
        st.markdown("<p class='sidebar-helper'>Left favors lower emissions · right favors less travel time</p>", unsafe_allow_html=True)
        scenario_name = st.selectbox("Traffic conditions", ["Normal conditions", "Peak bottleneck", "Incident / road closure", "Stale / missing traffic"], key="route_traffic_scenario")
        with st.expander("More route options", expanded=False):
            st.caption("Optional limits for the routes included in your comparison.")
            max_detour_ratio = st.slider("Maximum detour", 1.0, 2.0, 1.5, 0.05, help="Limit route travel time compared with the fastest option.", key="route_max_detour")
            max_failure_probability = st.slider("Maximum route risk", 0.0, 0.8, 0.5, 0.05, help="Exclude routes whose estimated failure risk is above this value.", key="route_max_risk")
            max_trip_time = st.number_input("Time limit in minutes", min_value=0, max_value=240, value=0, step=5, help="Set 0 for no time limit.", key="route_time_limit")
        calculate_clicked = st.form_submit_button("Find a route", use_container_width=True, type="primary")

    st.sidebar.markdown("<p class='sidebar-section-kicker'>02 / MAP VIEW</p><p class='sidebar-helper'>Adjust what is shown on the route map.</p>", unsafe_allow_html=True)
    show_traffic = st.sidebar.checkbox("Show traffic conditions", value=True, key="map_show_traffic")
    with st.sidebar.expander("Map detail", expanded=False):
        map_zoom = st.slider("Neighborhood zoom", 10, 18, 14, help="Higher values show a closer street-level view.", key="map_zoom")

    st.sidebar.markdown("<div style='margin-top:1rem;padding:.9rem 1rem;background:#111318;border:1px solid #292d36;border-left:3px solid #2347ff;border-radius:9px;color:#c5ced9;font-size:.84rem;line-height:1.55'><span style='display:block;color:#9eacc0;font:600 .65rem ui-monospace,monospace;letter-spacing:.13em;margin-bottom:.35rem'>COVERAGE AREA</span><strong style='color:#f2eee5;font-weight:600'>Bengaluru corridors</strong><br>South · Central · East</div>", unsafe_allow_html=True)

    if calculate_clicked:
        with st.spinner("Comparing street-level routes..."):
            try:
                start_coords = landmarks[start_landmark]
                end_coords = landmarks[end_landmark]

                start_node = find_nearest_node_manual(G, start_coords[1], start_coords[0])
                end_node = find_nearest_node_manual(G, end_coords[1], end_coords[0])

                if start_node is None or end_node is None:
                    raise ValueError("Could not locate nearest valid nodes in the network.")
                max_snap_distance_m = 800
                start_snap_m = distance_to_landmark_m(G, start_node, start_coords)
                end_snap_m = distance_to_landmark_m(G, end_node, end_coords)
                outside_local_graph = max(start_snap_m, end_snap_m) > max_snap_distance_m
                google_error = None
                google_route = None
                if not GOOGLE_API_KEY or not GOOGLE_MAPS_BROWSER_KEY:
                    google_error = "Add a valid Google Maps key to enable the Google baseline."
                else:
                    try:
                        google_route = calculate_google_baseline(start_coords, end_coords, GOOGLE_API_KEY, vehicle_type)
                    except Exception as error:
                        google_error = str(error)

                traffic_snapshot = get_traffic_snapshot(scenario_name, google_route)

                traffic_multiplier = google_route.get("traffic_multiplier", 1.0) if google_route else 1.0
                if outside_local_graph:
                    if google_route:
                        comparison = calculate_external_route_comparison(
                            start_coords, end_coords, vehicle_type, alpha, traffic_multiplier,
                            google_route.get("traffic_segments", []),
                        )
                    else:
                        comparison = get_cached_city_route(start_coords, end_coords, vehicle_type, alpha)
                else:
                    comparison = optimize_routes(
                        G, start_node, end_node,
                        vehicle_type=vehicle_type,
                        eco_priority=alpha,
                        seed=42,
                        max_detour_ratio=max_detour_ratio,
                        max_failure_probability=max_failure_probability,
                        max_time_min=max_trip_time or None,
                        traffic_multiplier=traffic_multiplier,
                        traffic_segments=google_route.get("traffic_segments", []) if google_route else None,
                        scenario_delays=traffic_snapshot.delay_by_highway,
                        closed_highways=traffic_snapshot.closed_highways,
                    )

                if google_route:
                    if comparison.get("path_coordinates"):
                        eco_coords = comparison["eco_path"]
                    else:
                        eco_coords = [
                            [float(G.nodes[node]["y"]), float(G.nodes[node]["x"])]
                            for node in comparison["eco_path"]
                        ]
                    google_stats = google_route["stats"]
                    eco_stats = comparison["eco"]
                    savings = {
                        "carbon_g": google_stats["carbon_g"] - eco_stats["carbon_g"],
                        "fuel_ml": google_stats["fuel_ml"] - eco_stats["fuel_ml"],
                        "energy_kwh": google_stats["energy_kwh"] - eco_stats["energy_kwh"],
                        "money_inr": google_stats["cost_inr"] - eco_stats["cost_inr"],
                        "time_diff": eco_stats["travel_time_min"] - google_stats["travel_time_min"],
                    }
                    savings["tree_equiv"] = savings["carbon_g"] / r2i_engine.CO2_PER_DAY_TREE
                    comparison.update({
                        "standard_path": google_route["path"],
                        "eco_path": eco_coords,
                        "standard": google_stats,
                        "path_coordinates": True,
                        "source": google_route["source"],
                        "google_copyrights": google_route["copyrights"],
                        "google_summary": google_route["summary"],
                        "traffic_multiplier": traffic_multiplier,
                        "has_live_traffic": google_route["has_live_traffic"],
                        "traffic_segments": google_route.get("traffic_segments", []),
                        "traffic_source": traffic_snapshot.source,
                        "traffic_confidence": traffic_snapshot.confidence,
                        "traffic_observed_at": traffic_snapshot.observed_at,
                        "savings": savings,
                    })

                standard_path = comparison["standard_path"]
                eco_path = comparison["eco_path"]
                savings = comparison["savings"]

                st.session_state.route_results = {
                    "standard_path": standard_path,
                    "eco_path": eco_path,
                    "start_label": start_landmark,
                    "end_label": end_landmark,
                    "start_coordinates": start_coords,
                    "end_coordinates": end_coords,
                    "traffic_scenario": scenario_name,
                    "eco_priority": alpha,
                    "max_detour_ratio": max_detour_ratio,
                    "max_failure_probability": max_failure_probability,
                    "max_trip_time_min": max_trip_time or None,
                    "standard": comparison["standard"],
                    "eco": comparison["eco"],
                    "metrics": {
                        "carbon_s": savings["carbon_g"],
                        "fuel_s": savings["fuel_ml"],
                        "energy_s": savings["energy_kwh"],
                        "money_s": savings["money_inr"],
                        "tree_s": savings["tree_equiv"],
                        "time_diff": savings["time_diff"],
                        "is_ev": vehicle_type == "EV",
                        "same_route": standard_path == eco_path,
                        "path_coordinates": comparison.get("path_coordinates", False),
                    }
                }
                st.session_state.route_results["source"] = comparison.get("source", "Local R2I road graph")
                st.session_state.route_results["google_error"] = google_error
                st.session_state.route_results["google_copyrights"] = comparison.get("google_copyrights", "")
                st.session_state.route_results["google_summary"] = comparison.get("google_summary", "")
                st.session_state.route_results["traffic_multiplier"] = comparison.get("traffic_multiplier", 1.0)
                st.session_state.route_results["has_live_traffic"] = comparison.get("has_live_traffic", False)
                st.session_state.route_results["traffic_segments"] = comparison.get("traffic_segments", [])
                st.session_state.route_results["traffic_source"] = comparison.get("traffic_source", traffic_snapshot.source)
                st.session_state.route_results["traffic_confidence"] = comparison.get("traffic_confidence", traffic_snapshot.confidence)
                st.session_state.route_results["traffic_observed_at"] = comparison.get("traffic_observed_at", traffic_snapshot.observed_at)
                st.session_state.route_results["optimizer"] = comparison.get("solver")
                st.session_state.route_results["candidate_count"] = comparison.get("candidate_count", 0)
                st.session_state.route_results["objective_components"] = comparison.get("objective_components", {})
                st.session_state.route_results["weights"] = comparison.get("weights", {})
                st.session_state.route_results["routing_runtime_ms"] = comparison.get("routing_runtime_ms")
                st.session_state.route_results["classical_weighted"] = comparison.get("classical_weighted")
            except nx.NetworkXNoPath:
                st.error("No path found between these landmarks. The road network might be disconnected.")
                st.session_state.route_results = None
            except Exception as e:
                st.error(f"Routing error: {e}")
                st.session_state.route_results = None

    if st.session_state.route_results:
        res = st.session_state.route_results
        metrics = res["metrics"]

        st.markdown("<p style='color:#8992a3;font:600 .67rem ui-monospace,monospace;letter-spacing:.15em;margin:1.7rem 0 .6rem'>ROUTE IMPACT  /  THIS JOURNEY</p>", unsafe_allow_html=True)
        comparison_label = "vs Google Maps" if res.get("source") == "Google Maps baseline" else "vs normal route"
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("CO₂ change", f"{metrics['carbon_s']:.1f} g", delta=f"{metrics['carbon_s']:.1f} g {comparison_label}")
        if metrics["is_ev"]:
            m2.metric("Grid energy change", f"{metrics['energy_s']:.2f} kWh", delta=f"{metrics['energy_s']:.2f} kWh {comparison_label}")
        else:
            m2.metric("Fuel change", f"{metrics['fuel_s']:.1f} mL", delta=f"{metrics['fuel_s']:.1f} mL {comparison_label}")
        m3.metric("Cost change", f"₹{metrics['money_s']:.2f}", delta=f"₹{metrics['money_s']:.2f} {comparison_label}")
        m4.metric("Time difference", f"{metrics['time_diff']:.1f} min", delta=f"{metrics['time_diff']:.1f}", delta_color="inverse")
        if res.get("source") == "Google Maps baseline":
            st.markdown("**Route comparison**")
            baseline, r2i_route = res["standard"], res["eco"]
            time_delta = r2i_route["travel_time_min"] - baseline["travel_time_min"]
            distance_delta = r2i_route["distance_km"] - baseline["distance_km"]
            time_message = f"{abs(time_delta):.1f} min {'slower' if time_delta > 0 else 'faster'} with R2I" if abs(time_delta) >= 0.05 else "Similar travel time"
            distance_message = f"{abs(distance_delta):.1f} km {'longer' if distance_delta > 0 else 'shorter'}" if abs(distance_delta) >= 0.05 else "Same distance"
            st.markdown(f"""
            <div class="route-compare-grid">
              <div class="route-compare-card google">
                <div class="route-compare-top"><div class="route-compare-label"><span class="route-compare-swatch"></span>GOOGLE MAPS</div><span class="route-compare-tag">FASTEST BASELINE</span></div>
                <div class="route-compare-measures"><span class="route-compare-value">{baseline['distance_km']:.1f}</span><span class="route-compare-unit">km</span></div>
                <div class="route-compare-bottom"><span><span class="route-compare-time">{baseline['travel_time_min']:.1f} min</span> estimated</span><span class="route-compare-distance-delta">Normal route</span></div>
              </div>
              <div class="route-compare-card r2i">
                <div class="route-compare-top"><div class="route-compare-label"><span class="route-compare-swatch"></span>R2I ENGINE</div><span class="route-compare-tag">ECO-OPTIMIZED</span></div>
                <div class="route-compare-measures"><span class="route-compare-value">{r2i_route['distance_km']:.1f}</span><span class="route-compare-unit">km</span></div>
                <div class="route-compare-bottom"><span><span class="route-compare-time">{r2i_route['travel_time_min']:.1f} min</span> estimated</span><span class="route-compare-distance-delta">R2I route</span></div>
              </div>
            </div>
            <div class="route-compare-summary"><span>{time_message} · {distance_message}</span></div>
            """, unsafe_allow_html=True)
            st.caption(f"Google Maps route: {res.get('google_summary', 'Driving route')}. {res.get('google_copyrights', '')}")
            source_note = "Impact values are estimates based on each route's distance and time."
            if res.get("has_live_traffic"):
                traffic_segments = res.get("traffic_segments", [])
                slow_sections = sum(segment.get("speed") == "SLOW" for segment in traffic_segments)
                jam_sections = sum(segment.get("speed") == "TRAFFIC_JAM" for segment in traffic_segments)
                if traffic_segments:
                    st.caption(f"Live Google traffic applied to nearby R2I road edges: {slow_sections} slow sections, {jam_sections} traffic-jam sections; trip delay factor ×{res.get('traffic_multiplier', 1.0):.2f}.")
                else:
                    st.caption(f"Live traffic duration applied to R2I congestion weighting: trip delay factor ×{res.get('traffic_multiplier', 1.0):.2f}; no localized traffic sections were returned.")
            else:
                st.caption("Google returned a route, but no live traffic duration; R2I is using its road-class congestion estimates.")
        elif res.get("source") == "City routing alternatives":
            source_note = "OSRM city route alternatives; impact estimates use route distance because local road-segment data is unavailable."
        else:
            source_note = "Local R2I graph with road-class assumptions where segment traffic data is missing."
        st.caption(f"{source_note} Positive resource changes mean the R2I route is lower than the normal route; negative values mean it is higher.")
        if res.get("google_error"):
            st.info(f"Google Maps comparison is not connected yet: {res['google_error']} Add a valid key with Routes API and Maps JavaScript API enabled in `.streamlit/secrets.toml` to show the Google baseline.")
        if metrics["same_route"]:
            if res.get("source") == "Google Maps baseline":
                st.caption("The R2I and Google routes overlap for this trip. Compare the distance and time cards above; small differences can be difficult to see at this zoom.")
            elif res.get("source") == "City routing alternatives":
                st.caption("The city routing service returned no distinct eco-priority alternative for this trip, so the route impact difference is zero.")
            else:
                st.caption("Both priorities selected the same road sequence for this trip, so the predicted route difference is zero. Try a longer trip or move the slider toward eco to compare alternatives.")
        if res.get("optimizer"):
            optimizer = res["optimizer"]
            with st.expander("How R2I selected this route"):
                st.write("Candidate routes are generated with classical shortest-path search, then scored for travel time, estimated CO₂, congestion exposure, reliability risk, and detour. Simulated annealing selects a route from a one-hot QUBO. This is a classical quantum-inspired method, not quantum hardware.")
                st.caption(f"Solver: {optimizer['solver']} · candidates: {res.get('candidate_count', 0)} · solver: {optimizer['runtime_ms']:.2f} ms · routing: {res.get('routing_runtime_ms', 0):.2f} ms · seed: {optimizer['seed']} · QUBO energy: {optimizer['qubo_energy']:.4f}")
                st.caption(f"Traffic: {res.get('traffic_source', 'unknown')} · confidence: {res.get('traffic_confidence', 0):.0%} · observed: {res.get('traffic_observed_at', 'unknown')}")
                if optimizer.get("fallback"):
                    st.warning("The annealing sample did not improve on the exact classical selection, so the best feasible candidate was retained.")
                if res.get("classical_weighted"):
                    st.caption("The weighted classical selector has the same candidate set. The one-hot QUBO is exactly solvable by argmin, so this prototype demonstrates the QUBO workflow rather than claiming a speed or quality advantage over classical selection.")
                st.json({"objective_weights": res.get("weights", {}), "selected_weighted_contributions": res.get("objective_components", {})})

        assistant_context = build_route_context(res)
        assistant_fingerprint = hashlib.sha256(
            json.dumps(assistant_context, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if st.session_state.get("assistant_route_fingerprint") != assistant_fingerprint:
            st.session_state.assistant_route_fingerprint = assistant_fingerprint
            st.session_state.assistant_messages = []

        time_delta = float(metrics.get("time_diff", 0) or 0)
        carbon_delta = float(metrics.get("carbon_s", 0) or 0)
        money_delta = float(metrics.get("money_s", 0) or 0)
        if abs(time_delta) < 0.05:
            time_summary = "about the same travel time"
        elif time_delta < 0:
            time_summary = f"{abs(time_delta):.1f} min faster"
        else:
            time_summary = f"{time_delta:.1f} min slower"
        if abs(carbon_delta) < 0.5:
            carbon_summary = "about the same CO₂"
        elif carbon_delta > 0:
            carbon_summary = f"saves about {carbon_delta:,.0f} g CO₂"
        else:
            carbon_summary = f"about {abs(carbon_delta):,.0f} g more CO₂"
        if abs(money_delta) < 0.01:
            money_summary = "about the same cost"
        elif money_delta > 0:
            money_summary = f"saves about ₹{money_delta:,.2f}"
        else:
            money_summary = f"costs about ₹{abs(money_delta):,.2f} more"

        with st.container(key="route_assistant_panel"):
            st.markdown(
                "<div class='assistant-panel-heading'><span class='assistant-panel-title'>Route assistant</span><span class='assistant-panel-tag'>R2I EXPLAINER</span></div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='assistant-comparison'><strong>Compared with the usual route</strong> &nbsp;·&nbsp; {time_summary} &nbsp;·&nbsp; {carbon_summary} &nbsp;·&nbsp; {money_summary}</div>",
                unsafe_allow_html=True,
            )
            assistant_enabled = bool(IMAGINE_API_KEY and IMAGINE_API_ENDPOINT)
            header_left, header_right = st.columns([3, 1])
            with header_left:
                explain_clicked = st.button(
                    "Explain this comparison",
                    key="explain_route_comparison",
                    disabled=not assistant_enabled,
                    type="primary",
                )
            with header_right:
                clear_clicked = st.button(
                    "Clear chat",
                    key="clear_route_assistant_v2",
                    disabled=not bool(st.session_state.get("assistant_messages")),
                    type="secondary",
                )
            if clear_clicked:
                st.session_state["assistant_messages"] = []
                st.session_state.pop("assistant_meta", None)
                st.session_state["route_assistant_question"] = ""
                st.rerun()
            if not assistant_enabled:
                st.info("Assistant unavailable: configure INFERENCE_CLOUD_API_KEY and INFERENCE_CLOUD_ENDPOINT in the server environment or Streamlit secrets.")

            with st.form("route_assistant_form", clear_on_submit=True, border=False):
                question_col, ask_col = st.columns([5, 1])
                with question_col:
                    assistant_question = st.text_input(
                        "Ask a follow-up",
                        placeholder="Ask about time, emissions, cost, or route choice…",
                        label_visibility="collapsed",
                        disabled=not assistant_enabled,
                        key="route_assistant_question",
                    )
                with ask_col:
                    ask_clicked = st.form_submit_button("Ask", use_container_width=True, disabled=not assistant_enabled)

            default_explanation = (
                "Explain why the R2I route differs from the normal route using the actual method in the context. "
                "Briefly describe how the candidate route is generated and selected, then state the main time, "
                "distance, CO2, and money differences using rounded values. If the local QUBO method was used, "
                "identify it as classical simulated annealing, not quantum hardware. Keep it to three short bullets "
                "and note that impact figures are estimates."
            )
            request_question = default_explanation if explain_clicked else (assistant_question if ask_clicked else None)
            displayed_question = "Explain this comparison" if explain_clicked else request_question
            assistant_error = None
            if request_question:
                prior_history = st.session_state.get("assistant_messages", [])
                with st.spinner("Preparing a concise explanation…"):
                    try:
                        answer, assistant_meta = chat_completion(
                            api_key=IMAGINE_API_KEY,
                            endpoint=IMAGINE_API_ENDPOINT,
                            model=IMAGINE_MODEL,
                            context=assistant_context,
                            question=request_question,
                            history=prior_history,
                        )
                        st.session_state.assistant_messages = (prior_history + [
                            {"role": "user", "content": displayed_question},
                            {"role": "assistant", "content": answer},
                        ])[-4:]
                        st.session_state.assistant_meta = assistant_meta
                    except ImagineAPIError as error:
                        assistant_error = str(error)
                    except Exception:
                        assistant_error = "The route assistant encountered an unexpected issue. Your computed route and metrics are unchanged."

            if assistant_error:
                st.warning(assistant_error)
            messages = st.session_state.get("assistant_messages", [])
            if messages:
                with st.container(key="route_assistant_transcript"):
                    for message in messages:
                        role = message["role"]
                        label = "YOU" if role == "user" else "R2I ASSISTANT"
                        bubble_type = "user" if role == "user" else "assistant"
                        st.markdown(
                            f"<div class='assistant-chat-bubble {bubble_type}'><span class='assistant-chat-role'>{label}</span>{escape(message['content'])}</div>",
                            unsafe_allow_html=True,
                        )
            meta = st.session_state.get("assistant_meta")
            if messages and meta:
                st.caption(f"AI-generated · {meta['model']} · {meta['elapsed_ms']:.0f} ms · showing the latest two exchanges")

    has_route = bool(st.session_state.route_results)
    displayed_route = st.session_state.route_results or {}
    displayed_start = escape(displayed_route.get("start_label", start_landmark))
    displayed_end = escape(displayed_route.get("end_label", end_landmark))
    st.markdown(f"""
    <div class="map-heading">
      <div><div class="eyebrow">BENGALURU ROAD NETWORK  /  ROUTE COMPARISON</div>
      <h2>{displayed_start + ' → ' + displayed_end if has_route else 'Plan a city journey'}</h2></div>
      <div class="map-status">{'ROUTE READY' if has_route else 'NETWORK ONLINE'}</div>
    </div>
    """, unsafe_allow_html=True)

    m = folium.Map(location=[12.9352, 77.6245], zoom_start=map_zoom, tiles="OpenStreetMap", control_scale=True)
    m.get_root().header.add_child(folium.Element(f"""
    <style>
      #{m.get_name()} .leaflet-container {{ background:#08090c !important; border-radius:15px; }}
      #{m.get_name()} .leaflet-tile-pane {{ filter:grayscale(1) invert(1) brightness(.88) contrast(1.08); }}
    </style>
    """))
    if show_traffic and has_route:
        route_result = st.session_state.route_results
        eco_path = route_result["eco_path"]
        if not route_result["metrics"].get("path_coordinates"):
            route_points = [G.nodes[node] for node in eco_path]
            south = min(float(point['y']) for point in route_points) - 0.003
            north = max(float(point['y']) for point in route_points) + 0.003
            west = min(float(point['x']) for point in route_points) - 0.003
            east = max(float(point['x']) for point in route_points) + 0.003
            for u, v, data in G.edges(data=True):
                a, b = G.nodes[u], G.nodes[v]
                if not (south <= float(a['y']) <= north and west <= float(a['x']) <= east):
                    continue
                if not (south <= float(b['y']) <= north and west <= float(b['x']) <= east):
                    continue
                prob = float(data.get('idle_probability', 0.1))
                if prob > 0.7: color = "#ec5d68"
                elif prob > 0.4: color = "#e0a44f"
                else: color = "#455164"
                coords = [[float(G.nodes[u]['y']), float(G.nodes[u]['x'])], [float(G.nodes[v]['y']), float(G.nodes[v]['x'])]]
                folium.PolyLine(coords, color=color, weight=2, opacity=0.38).add_to(m)

    if has_route and st.session_state.route_results.get("source") != "Google Maps baseline":
        res = st.session_state.route_results
        start_point = res.get("start_coordinates", landmarks.get(res.get("start_label", start_landmark)))
        end_point = res.get("end_coordinates", landmarks.get(res.get("end_label", end_landmark)))
        start_name = escape(res.get("start_label", start_landmark))
        end_name = escape(res.get("end_label", end_landmark))
        folium.Marker(
            location=start_point,
            tooltip=f"Start · {start_name}",
            popup=folium.Popup(f"<strong>Start</strong><br>{start_name}", max_width=260),
            icon=folium.DivIcon(html="<div style='display:grid;place-items:center;width:25px;height:25px;border:2px solid #fff;border-radius:50%;background:#28784d;color:#fff;font:700 11px Arial;box-shadow:0 2px 8px #0009'>S</div>", icon_size=(25, 25), icon_anchor=(12, 12)),
        ).add_to(m)
        folium.Marker(
            location=end_point,
            tooltip=f"Destination · {end_name}",
            popup=folium.Popup(f"<strong>Destination</strong><br>{end_name}", max_width=260),
            icon=folium.DivIcon(html="<div style='display:grid;place-items:center;width:25px;height:25px;border:2px solid #fff;border-radius:50%;background:#f0b44d;color:#111318;font:700 11px Arial;box-shadow:0 2px 8px #0009'>D</div>", icon_size=(25, 25), icon_anchor=(12, 12)),
        ).add_to(m)
        if res["metrics"].get("path_coordinates"):
            std_coords = res["standard_path"]
            eco_coords = res["eco_path"]
        else:
            std_coords = [[float(G.nodes[n]['y']), float(G.nodes[n]['x'])] for n in res["standard_path"]]
            eco_coords = [[float(G.nodes[n]['y']), float(G.nodes[n]['x'])] for n in res["eco_path"]]
        folium.PolyLine(std_coords, color="#858d99", weight=4, opacity=0.95, dash_array='6, 9', tooltip="Normal route").add_to(m)
        folium.PolyLine(eco_coords, color="#174d32", weight=11, opacity=0.8, tooltip="R2I eco route").add_to(m)
        folium.PolyLine(eco_coords, color="#28784d", weight=7, opacity=1, tooltip="R2I eco route").add_to(m)
        legend = """
        <div style="position:fixed;bottom:22px;left:22px;z-index:9999;padding:12px 15px;background:rgba(9,11,14,.94);border:1px solid #343a44;border-radius:10px;color:#e8ebf0;font:500 12px/1.4 'DM Sans',Arial,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.32)">
          <div style="display:flex;align-items:center;gap:9px;margin-bottom:7px"><span style="width:24px;border-top:4px solid #28784d;border-radius:4px"></span>R2I eco route</div>
          <div style="display:flex;align-items:center;gap:9px;margin-bottom:7px"><span style="width:24px;border-top:3px dashed #858d99"></span>Normal route</div>
          <div style="display:flex;align-items:center;gap:9px;margin-bottom:4px"><span style="display:grid;place-items:center;width:17px;height:17px;border-radius:50%;background:#28784d;color:#fff;font-size:10px;font-weight:700">S</span>Start · __START_NAME__</div>
          <div style="display:flex;align-items:center;gap:9px"><span style="display:grid;place-items:center;width:17px;height:17px;border-radius:50%;background:#f0b44d;color:#111318;font-size:10px;font-weight:700">D</span>Destination · __END_NAME__</div>
        </div>
        """.replace("__START_NAME__", start_name).replace("__END_NAME__", end_name)
        m.get_root().html.add_child(folium.Element(legend))
        if std_coords:
            bounds_points = std_coords + eco_coords + [start_point, end_point]
            bounds = [[min(c[0] for c in bounds_points), min(c[1] for c in bounds_points)], [max(c[0] for c in bounds_points), max(c[1] for c in bounds_points)]]
            m.fit_bounds(bounds, padding=(28, 28))

    if has_route and st.session_state.route_results.get("source") == "Google Maps baseline":
        google_result = st.session_state.route_results
        google_start = escape(google_result.get("start_label", start_landmark))
        google_end = escape(google_result.get("end_label", end_landmark))
        st.markdown(f"<div style='display:flex;gap:18px;flex-wrap:wrap;margin:0 0 8px;color:#aeb8c5;font:500 .75rem ui-monospace,monospace'><span>··· GOOGLE MAPS NORMAL</span><span style='color:#48a86e'>━━ R2I ECO ROUTE</span><span style='color:#69b489'>● S · START: {google_start}</span><span style='color:#f0b44d'>● D · DESTINATION: {google_end}</span></div>", unsafe_allow_html=True)
        components.html(build_google_comparison_map(st.session_state.route_results, map_zoom), height=560, scrolling=False)
    else:
        st_folium(m, width=1200, height=560, key="r2i_map", returned_objects=[])
