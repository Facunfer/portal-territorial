import toml
import os
from supabase import create_client, Client

secrets_path = ".streamlit/secrets.toml"
secrets = toml.load(secrets_path)
url = secrets["supabase"]["url"]
key = secrets["supabase"]["anon_key"]
supabase = create_client(url, key)

users_to_create = [
    {"username": "cabeza_ccaa", "ambito": "VERTICAL_PERSONAS", "vertical": "CCAA", "rol": "CABEZA", "tipo_usuario": "MASTER"},
    {"username": "cabeza_pymes", "ambito": "VERTICAL_PERSONAS", "vertical": "PYMES", "rol": "CABEZA", "tipo_usuario": "MASTER"},
    {"username": "cabeza_jovenes_emp", "ambito": "VERTICAL_PERSONAS", "vertical": "JOVENES_EMPRESARIOS", "rol": "CABEZA", "tipo_usuario": "MASTER"},
    {"username": "cabeza_innovacion", "ambito": "VERTICAL_PERSONAS", "vertical": "INNOVACION_TECNOLOGIA", "rol": "CABEZA", "tipo_usuario": "MASTER"},
    {"username": "cabeza_educacion", "ambito": "VERTICAL_PERSONAS", "vertical": "EDUCACION", "rol": "CABEZA", "tipo_usuario": "MASTER"},
    {"username": "cabeza_salud", "ambito": "VERTICAL_PERSONAS", "vertical": "SALUD", "rol": "CABEZA", "tipo_usuario": "MASTER"},
    {"username": "cabeza_cultura", "ambito": "VERTICAL_PERSONAS", "vertical": "CULTURA", "rol": "CABEZA", "tipo_usuario": "MASTER"},
]

for user in users_to_create:
    user["password_hash"] = user["username"]  # Default password = username
    user["activo"] = True
    
    # check if user exists
    res = supabase.table("usuarios").select("id").eq("username", user["username"]).execute()
    if not res.data:
        try:
            supabase.table("usuarios").insert(user).execute()
            print(f"Created: {user['username']}")
        except Exception as e:
            print(f"Failed to create {user['username']}: {e}")
    else:
        print(f"User {user['username']} already exists.")
