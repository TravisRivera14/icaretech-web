import os
import psycopg2
# Pon tu URL de Neon aquí abajo
DATABASE_URL = "postgresql://neondb_owner:npg_rXcGY7BdMpS9@ep-green-forest-ap6dfhlf-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require" 
try:
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    print("¡Conexión exitosa a la base de datos!")
    conn.close()
except Exception as e:
    print(f"Error de conexión: {e}")