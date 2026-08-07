"""
CEOPRO AI - Database Backup and Recovery Validator.
Creates a snapshot, restores it into a sandbox database, and verifies structural integrity.
"""

import hashlib
import logging
import os
import secrets
import subprocess
import sys
import time
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CEOPRO_BACKUP_CORE")

EXPECTED_TABLE_COUNT = 15


class BackupValidator:
    def __init__(self):
        self.user = os.getenv("POSTGRES_USER")
        self.password = os.getenv("POSTGRES_PASSWORD")
        self.db_name = os.getenv("POSTGRES_DB")
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = os.getenv("POSTGRES_PORT", "5432")

        if not all([self.user, self.password, self.db_name]):
            raise RuntimeError("POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB must be set.")

        self.container_name = "ceopro_postgres"
        self.target_dir = "src/infrastructure/database/backups"
        self.snapshot_path = f"{self.target_dir}/snapshot_{int(time.time_ns())}.sql"
        self.sandbox_db = f"ceopro_sandbox_{secrets.token_hex(4)}"

    def _generate_file_checksum(self, filepath: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def execute_backup_generation(self) -> bool:
        logger.info("Starting database snapshot export.")
        os.makedirs(self.target_dir, exist_ok=True)
        try:
            dump_cmd = [
                "docker", "exec", "-t", self.container_name,
                "pg_dump", "-U", self.user, "-d", self.db_name,
                "--clean", "--if-exists", "--no-owner", "--no-privileges"
            ]
            with open(self.snapshot_path, "w", encoding="utf-8") as out:
                subprocess.run(dump_cmd, stdout=out, stderr=subprocess.PIPE, check=True)

            if os.path.exists(self.snapshot_path) and os.path.getsize(self.snapshot_path) > 500:
                checksum = self._generate_file_checksum(self.snapshot_path)
                logger.info(f"Snapshot created: {self.snapshot_path} SHA256={checksum}")
                return True
            return False
        except subprocess.CalledProcessError as ce:
            logger.critical(f"Snapshot export failed: {ce.stderr}")
            return False
        except Exception as e:
            logger.critical(f"Unexpected backup error: {str(e)}")
            return False

    def validate_restoration_integrity(self) -> bool:
        if not os.path.exists(self.snapshot_path):
            return False

        logger.info(f"Creating sandbox database: {self.sandbox_db}")
        db_created = False
        try:
            create_db_cmd = [
                "docker", "exec", "-i", self.container_name,
                "psql", "-U", self.user, "-d", "postgres",
                "-c", f"CREATE DATABASE {self.sandbox_db};"
            ]
            subprocess.run(create_db_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            db_created = True

            logger.info("Restoring snapshot into sandbox.")
            restore_cmd = [
                "docker", "exec", "-i", self.container_name,
                "psql", "-U", self.user, "-d", self.sandbox_db
            ]
            with open(self.snapshot_path, "r", encoding="utf-8") as inp:
                subprocess.run(restore_cmd, stdin=inp, stderr=subprocess.PIPE, check=True)

            logger.info("Verifying restored schema.")
            sandbox_url = f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.sandbox_db}"
            conn = psycopg2.connect(sandbox_url, connect_timeout=3)

            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(table_name)
                    FROM information_schema.tables
                    WHERE table_schema = 'public';
                    """
                )
                tables = int(cursor.fetchone()[0])
                logger.info(f"Recovered {tables} tables.")

                if tables < EXPECTED_TABLE_COUNT:
                    raise ValueError(f"Expected at least {EXPECTED_TABLE_COUNT} tables, recovered {tables}.")

                cursor.execute("SELECT COUNT(*) FROM companies;")
                logger.info("Tenant table verified intact.")

            conn.close()
            logger.info("Backup and restore validation passed.")
            return True

        except Exception as err:
            logger.error(f"Restoration validation failed: {str(err)}")
            return False

        finally:
            if db_created:
                try:
                    drop_cmd = [
                        "docker", "exec", "-i", self.container_name,
                        "psql", "-U", self.user, "-d", "postgres",
                        "-c", f"DROP DATABASE IF EXISTS {self.sandbox_db} WITH (FORCE);"
                    ]
                    subprocess.run(drop_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    logger.info("Sandbox database dropped.")
                except Exception as cleanup_err:
                    logger.error(f"Failed to clean up sandbox: {str(cleanup_err)}")


if __name__ == "__main__":
    validator = BackupValidator()
    if validator.execute_backup_generation():
        if not validator.validate_restoration_integrity():
            sys.exit(1)
    else:
        sys.exit(1)
