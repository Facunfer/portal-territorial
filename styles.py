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
           SIDEBAR — Fondo
           ========================================= */
        [data-testid="stSidebar"],
        [data-testid="stSidebar"] > div,
        [data-testid="stSidebar"] > div:first-child {
            background-color: #371959 !important;
        }

        /* =========================================
           SIDEBAR — TODO el texto en blanco
           Selectores amplios para cubrir cualquier
           versión de Streamlit en producción
           ========================================= */

        /* Markdown: párrafos, spans, strong, em */
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] strong,
        [data-testid="stSidebar"] em,
        [data-testid="stSidebar"] small,
        [data-testid="stSidebar"] a {
            color: #FFFFFF !important;
        }

        /* Labels de widgets (caption, text_input, selectbox, etc.) */
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
            color: #FFFFFF !important;
        }

        /* stMarkdownContainer (usado por st.markdown y st.caption) */
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] * {
            color: #FFFFFF !important;
        }

        /* Radio buttons: texto de cada opción */
        [data-testid="stSidebar"] [data-baseweb="radio"] div,
        [data-testid="stSidebar"] [data-baseweb="radio"] p,
        [data-testid="stSidebar"] [data-baseweb="radio"] span,
        [data-testid="stSidebar"] [data-testid="stRadio"] label,
        [data-testid="stSidebar"] [data-testid="stRadio"] p {
            color: #FFFFFF !important;
        }

        /* Título del radio group */
        [data-testid="stSidebar"] [data-testid="stRadio"] > label {
            color: #A6E3FF !important;
            font-weight: 700 !important;
            text-transform: uppercase;
            font-size: 0.8rem;
        }

        /* Captura genérica: cualquier div/p dentro del sidebar */
        [data-testid="stSidebar"] div,
        [data-testid="stSidebar"] div p {
            color: #FFFFFF !important;
        }

        /* Separator (hr) */
        [data-testid="stSidebar"] hr {
            border-color: #A6E3FF !important;
            opacity: 0.5;
        }

        /* Botón CERRAR SESIÓN en sidebar */
        [data-testid="stSidebar"] .stButton > button {
            background-color: transparent !important;
            color: #FFFFFF !important;
            border: 1px solid #A6E3FF !important;
            border-radius: 4px !important;
            text-transform: uppercase;
            font-weight: 700 !important;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background-color: #A6E3FF !important;
            color: #371959 !important;
        }

        /* =========================================
           MAIN AREA
           ========================================= */
        [data-testid="stAppViewContainer"] {
            background-color: #FFFFFF;
        }

        /* =========================================
           WIDGETS & INPUTS
           ========================================= */
        /* Botones primarios (área principal) */
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
            background-color: #58337a !important;
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
        button[data-baseweb="tab"][aria-selected="true"] {
            color: #371959 !important;
            border-bottom-color: #371959 !important;
        }

        /* =========================================
           ALERTS / INFO / WARNING
           ========================================= */
        [data-testid="stNotification"] {
            border-radius: 4px;
        }

        </style>
    """, unsafe_allow_html=True)
