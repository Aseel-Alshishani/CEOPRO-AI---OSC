import os
import sys
import uuid
import random
import math
from datetime import datetime, timedelta
import json
import psycopg2

class EnterprisePlatformSeeder:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            user = os.getenv("POSTGRES_USER", "ceopro_admin")
            pwd = os.getenv("POSTGRES_PASSWORD", "SecureProductionPassword2026")
            host = os.getenv("POSTGRES_HOST", "localhost")
            port = os.getenv("POSTGRES_PORT", "5432")
            db = os.getenv("POSTGRES_DB", "ceopro_platform")
            self.db_url = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

    def generate_normalized_vector(self, dimensions: int = 1024) -> list:
        raw_vector = [random.gauss(0, 1) for _ in range(dimensions)]
        magnitude = math.sqrt(sum(x**2 for x in raw_vector))
        return [x / magnitude for x in raw_vector]

    def execute_seeding_protocol(self) -> None:
        try:
            conn = psycopg2.connect(self.db_url)
            conn.autocommit = False
            cursor = conn.cursor()

            tenant_a = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
            tenant_b = "f9e8d7c6-b5a4-3f2e-1d0c-9b8a7f6e5d4c"

            cursor.execute("""
                INSERT INTO currency_rates (base_currency, target_currency, rate, updated_at)
                VALUES 
                ('USD', 'JOD', 0.7090, NOW()),
                ('USD', 'SAR', 3.7500, NOW()),
                ('JOD', 'SAR', 5.2890, NOW())
                ON CONFLICT (base_currency, target_currency) DO UPDATE SET rate = EXCLUDED.rate;
            """)

            cursor.execute("SET app.current_tenant_id = %s;", (tenant_a,))
            cursor.execute("""
                INSERT INTO companies (id, name, country, currency, created_at)
                VALUES (%s, 'CEOPRO Retail Jordan', 'JO', 'JOD', NOW())
                ON CONFLICT (id) DO NOTHING;
            """, (tenant_a,))

            cursor.execute("""
                INSERT INTO users (id, tenant_id, email, password_hash, role, created_at)
                VALUES (%s, %s, 'manager.jo@ceopro.ai', 'immutable_hash_string', 'admin', NOW())
                ON CONFLICT (id) DO NOTHING;
            """, (str(uuid.uuid4()), tenant_a))

            products_a = []
            product_names_a = ["Premium Olive Oil 1L", "Arabica Coffee Beans 1KG", "Medjool Dates 500G"]
            for name in product_names_a:
                p_id = str(uuid.uuid4())
                base_p = round(random.uniform(8.0, 35.0), 2)
                products_a.append((p_id, base_p))
                cursor.execute("""
                    INSERT INTO products (id, tenant_id, name, sku, base_price, currency, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'JOD', NOW())
                    ON CONFLICT (id) DO NOTHING;
                """, (p_id, tenant_a, name, f"SKU-JO-{random.randint(1000,9999)}", base_p))

            for p_id, base_p in products_a:
                cursor.execute("""
                    INSERT INTO inventory (id, tenant_id, product_id, current_stock, safety_stock, reorder_point, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW());
                """, (str(uuid.uuid4()), tenant_a, p_id, random.randint(80, 250), 20, 40))

                for i in range(30):
                    tx_date = datetime.now() - timedelta(days=i)
                    day_weight = 1.4 if tx_date.weekday() in [4, 5] else 1.0
                    qty = max(1, int(random.poissonvariate(3) * day_weight))
                    total = round(qty * base_p, 2)
                    cursor.execute("""
                        INSERT INTO transactions (id, tenant_id, product_id, quantity, unit_price, total_amount, currency, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, 'JOD', %s);
                    """, (str(uuid.uuid4()), tenant_a, p_id, qty, base_p, total, tx_date))

                cursor.execute("""
                    INSERT INTO demand_forecasts (id, tenant_id, product_id, forecast_date, predicted_quantity, confidence_interval, created_at)
                    VALUES (%s, %s, %s, NOW() + INTERVAL '7 days', %s, 0.94, NOW());
                """, (str(uuid.uuid4()), tenant_a, p_id, random.randint(90, 160)))

            cursor.execute("SET app.current_tenant_id = %s;", (tenant_b,))
            cursor.execute("""
                INSERT INTO companies (id, name, country, currency, created_at)
                VALUES (%s, 'CEOPRO Logistics KSA', 'SA', 'SAR', NOW())
                ON CONFLICT (id) DO NOTHING;
            """, (tenant_b,))

            products_b = []
            product_names_b = ["Industrial Storage Box", "Heavy Duty Pallet", "Cargo Straps Pack"]
            for name in product_names_b:
                p_id = str(uuid.uuid4())
                base_p = round(random.uniform(90.0, 300.0), 2)
                products_b.append((p_id, base_p))
                cursor.execute("""
                    INSERT INTO products (id, tenant_id, name, sku, base_price, currency, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'SAR', NOW())
                    ON CONFLICT (id) DO NOTHING;
                """, (p_id, tenant_b, name, f"SKU-SA-{random.randint(1000,9999)}", base_p))

            for p_id, base_p in products_b:
                cursor.execute("""
                    INSERT INTO inventory (id, tenant_id, product_id, current_stock, safety_stock, reorder_point, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW());
                """, (str(uuid.uuid4()), tenant_b, p_id, random.randint(150, 600), 40, 80))

                for i in range(30):
                    tx_date = datetime.now() - timedelta(days=i)
                    day_weight = 1.3 if tx_date.weekday() in [3, 4] else 1.0
                    qty = max(1, int(random.poissonvariate(8) * day_weight))
                    total = round(qty * base_p, 2)
                    cursor.execute("""
                        INSERT INTO transactions (id, tenant_id, product_id, quantity, unit_price, total_amount, currency, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, 'SAR', %s);
                    """, (str(uuid.uuid4()), tenant_b, p_id, qty, base_p, total, tx_date))

            cursor.execute("SET app.current_tenant_id = %s;", (tenant_a,))
            hardened_vector = self.generate_normalized_vector(1024)
            cursor.execute("""
                INSERT INTO rag_document_chunks (id, tenant_id, document_id, chunk_index, content, embedding, created_at)
                VALUES (%s, %s, %s, 0, 'SME localized economic indicators, exchange fluctuations, and cross-border logistics contracts payload analysis.', %s, NOW());
            """, (str(uuid.uuid4()), tenant_a, str(uuid.uuid4()), hardened_vector))

            conn.commit()
            sys.stdout.write("STDOUT: Advanced transactional matrices populated with strict semantic vectors.\n")
            
        except Exception as e:
            if conn: conn.rollback()
            sys.stderr.write(f"STDERR: Critical infrastructure seeding breach: {str(e)}\n")
            sys.exit(1)
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

if __name__ == '__main__':
    seeder = EnterprisePlatformSeeder()
    seeder.execute_seeding_protocol()
