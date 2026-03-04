import streamlit as st

def load_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;700&display=swap');

        /* 
           PALETA DE COLORES LLA
           Primario (Violeta): #371959
           Secundario (Celeste/Cyan): #A6E3FF (aka Anakiwa) - Usado para acentos suaves
           Texto Oscuro: #333333
           Blanco: #FFFFFF
        */

        /* =========================================
           GLOBAL FONT & BODY
           ========================================= */
        html, body, [class*="css"], [data-testid="stAppViewContainer"] {
            font-family: 'Montserrat', sans-serif !important;
        }

        /* HEADERS */
        h1, h2, h3, h4, h5, h6, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
            font-family: 'Montserrat', sans-serif !important;
            font-weight: 800 !important;
            color: #371959 !important;
            text-transform: uppercase;
            letter-spacing: -0.5px;
        }

        /* =========================================
           SIDEBAR
           ========================================= */
        [data-testid="stSidebar"] {
            background-color: #371959 !important;
        }
        
        /* Texto genérico en sidebar */
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p, 
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
        [data-testid="stSidebar"] label {
            color: #FFFFFF !important;
        }
        
        /* Separator (hr) */
        [data-testid="stSidebar"] hr {
            border-color: #A6E3FF !important; /* Celeste LLA */
            opacity: 0.5;
        }
        
        /* Radio buttons en sidebar */
        [data-testid="stSidebar"] [data-baseweb="radio"] div {
            color: #FFFFFF !important;
        }

        /* =========================================
           MAIN AREA
           ========================================= */
        /* Fondo general */
        [data-testid="stAppViewContainer"] {
            background-color: #FFFFFF;
        }

        /* =========================================
           WIDGETS & INPUTS
           ========================================= */
        /* Botones primarios */
        .stButton > button {
            background-color: #371959 !important;
            color: #FFFFFF !important;
            border: 2px solid #371959 !important;
            border-radius: 4px !important;
            text-transform: uppercase;
            font-weight: 700 !important;
            letter-spacing: 0.5px;
            transition: all 0.3s ease;
        }
        .stButton > button:hover {
            background-color: #58337a !important; /* Un poco más claro */
            border-color: #58337a !important;
            color: #FFFFFF !important;
            box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        }

        /* Inputs de texto y text area */
        div[data-baseweb="input"] > div, 
        div[data-baseweb="base-input"] {
            background-color: white !important;
            border-color: #371959 !important;
            border-radius: 4px !important;
        }
        
        /* Selectbox / Dropdowns */
        div[data-baseweb="select"] > div {
            border-color: #371959 !important;
            border-radius: 4px !important;
        }
        
        /* Checkboxes */
        /* Streamlit checkboxes are tricky, simple color approach */
        [data-baseweb="checkbox"] span {
            color: #333333;
        }

        /* =========================================
           TABS
           ========================================= */
        button[data-baseweb="tab"] {
            font-family: 'Montserrat', sans-serif !important;
            font-weight: 600 !important;
        }
        /* Active Tab */
        button[data-baseweb="tab"][aria-selected="true"] {
            color: #371959 !important;
            border-bottom-color: #371959 !important;
        }

        /* =========================================
           ALERTS / INFO / WARNING
           ========================================= */
        /* Success box usually green, we can keep it or tweak */
        [data-testid="stNotification"] {
            border-radius: 4px;
        }

        /* =========================================
           AGGRID (If used)
           ========================================= */
        /* AgGrid styling is separate but we can try to influence wrappers */
        
        </style>
    """, unsafe_allow_html=True)
