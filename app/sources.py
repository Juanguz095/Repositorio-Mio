"""Read-only, fixed-schema SQLite connector for local development.

A deployment can expose institutional data through the same named SQL views;
no SQL or database path is accepted from an HTTP payload or from the LLM.
"""
from pathlib import Path
import sqlite3
import pandas as pd
from app.pipeline import FEATURES


class SourceUnavailable(RuntimeError):
    pass


def read_sqlite(path, dataset):
    if dataset not in {'history', 'students'}:
        raise ValueError('Conjunto de origen no permitido')
    source = Path(path).resolve()
    if not source.is_file():
        raise SourceUnavailable('Configura TUTORIA_SOURCE_DB con una base SQLite disponible')
    view = 'academic_history' if dataset == 'history' else 'academic_current'
    columns = ['alumno_id', 'periodo', *FEATURES, *(['deserto'] if dataset == 'history' else [])]
    # Names are constants, never interpolated from user input.
    sql = 'SELECT '+','.join(columns)+' FROM '+view+' ORDER BY periodo,alumno_id LIMIT 10001'
    try:
        with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as connection:
            connection.execute('PRAGMA query_only=ON')
            result = pd.read_sql_query(sql, connection)
        if not 1 <= len(result) <= 10000:
            raise SourceUnavailable('La vista debe contener entre 1 y 10000 filas')
        return result
    except (sqlite3.Error, pd.errors.DatabaseError):
        raise SourceUnavailable('No se pudieron leer las vistas académicas configuradas') from None
