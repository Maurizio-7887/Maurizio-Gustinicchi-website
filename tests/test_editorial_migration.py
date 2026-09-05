import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class EditorialMigrationTests(unittest.TestCase):
    def test_legacy_articoli_table_is_extended_without_losing_rows(self):
        database = Path(tempfile.gettempdir()) / 'mg_website_legacy_migration.db'
        if database.exists():
            database.unlink()
        connection = sqlite3.connect(database)
        connection.executescript('''
            CREATE TABLE articoli (
                id INTEGER PRIMARY KEY,
                slug VARCHAR(200) NOT NULL UNIQUE,
                titolo VARCHAR(300) NOT NULL,
                meta_description TEXT DEFAULT '',
                excerpt TEXT DEFAULT '',
                cover VARCHAR(400) DEFAULT '',
                body TEXT NOT NULL,
                styles TEXT DEFAULT '',
                data_pubblicazione DATE,
                pubblicato BOOLEAN,
                creato_il DATETIME
            );
            INSERT INTO articoli (slug, titolo, body, pubblicato)
            VALUES ('articolo-storico', 'Articolo storico', '<p>legacy</p>', 1);
        ''')
        connection.commit()
        connection.close()

        environment = os.environ.copy()
        environment.update({
            'DATABASE_URL': f'sqlite:///{database}',
            'WEBSITE_ARTICLE_PUBLISH_API_KEY': 'test-key',
            'SECRET_KEY': 'test-secret',
        })
        subprocess.run([sys.executable, '-c', 'import app'], check=True, env=environment)

        connection = sqlite3.connect(database)
        columns = {row[1] for row in connection.execute('PRAGMA table_info(articoli)')}
        legacy_row = connection.execute(
            "SELECT slug, external_id, version FROM articoli WHERE slug = 'articolo-storico'"
        ).fetchone()
        connection.close()
        self.assertTrue({'external_id', 'version', 'payload_hash', 'updated_at'} <= columns)
        self.assertEqual(legacy_row, ('articolo-storico', None, 1))


if __name__ == '__main__':
    unittest.main()
