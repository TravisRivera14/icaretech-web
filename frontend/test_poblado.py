import psycopg2

DATABASE_URL = "postgresql://neondb_owner:npg_rXcGY7BdMpS9@ep-green-forest-ap6dfhlf-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require"

def limpiar_residuo_neon():
    print("⏳ Conectando con Neon para limpiar residuos estructurales...")
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        c = conn.cursor()
        
        # Eliminamos la tabla si existía con errores del pasado
        c.execute("DROP TABLE IF EXISTS configuracionhacienda CASCADE;")
        conn.commit()
        print("🧹 ¡Neon limpio de residuos viejos exitosamente!")
        
        c.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error conectando a Neon: {e}")

if __name__ == '__main__':
    limpiar_residuo_neon()