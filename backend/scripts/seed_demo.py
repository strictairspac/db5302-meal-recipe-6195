from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from src.config.settings import IS_MYSQL, engine
from src.constants.workflow import Role
from src.models.tables import (audit, batch_inputs, cases, evidence, lots,
                               productions, runs, schema, users)
from src.services.domain import SPEC
from src.services.security import hash_password
from src.utils.time import utc_time


def keep_existing(conn, table, key, values):
    if IS_MYSQL:
        statement = mysql_insert(table).values(**values).on_duplicate_key_update(id=table.c.id)
    else:
        statement = postgres_insert(table).values(**values).on_conflict_do_nothing(index_elements=[key])
    conn.execute(statement)


def seed_trace(conn):
    """演示用原料批与投料链：换批领料不改旧记录，封存后可从备料单页追溯。"""
    if conn.execute(select(func.count()).select_from(lots)).scalar_one():
        return
    now = utc_time()
    conn.execute(lots.insert(), [
        {'ingredient': 'M01', 'lot': 'L1118', 'status': 'active', 'created_at': now},
        {'ingredient': 'M01', 'lot': 'L1121', 'status': 'active', 'created_at': now},
        {'ingredient': 'M02', 'lot': 'L1120', 'status': 'active', 'created_at': now},
    ])
    semi_id = conn.execute(productions.insert().values(
        batch='S-R01-1121', kind='semi', recipe='R01', name='手工鲜面', unit='kg',
        quantity='21.6', status='produced', author='demo', created_at=now)).inserted_primary_key[0]
    dish_id = conn.execute(productions.insert().values(
        batch='D-C01-1121', kind='dish', recipe='C01', name='葱油拌面', unit='份',
        quantity='120', status='produced', author='demo', created_at=now)).inserted_primary_key[0]
    conn.execute(batch_inputs.insert(), [
        {'production_id': semi_id, 'ingredient': 'M01', 'lot': 'L1118',
         'semi_batch': None, 'quantity': '17.28'},
        {'production_id': dish_id, 'ingredient': None, 'lot': None,
         'semi_batch': 'S-R01-1121', 'quantity': '21.6'},
        {'production_id': dish_id, 'ingredient': 'M02', 'lot': 'L1120',
         'semi_batch': None, 'quantity': '2.1'},
    ])


def seed():
    with engine.begin() as conn:
        for role in Role:
            keep_existing(conn, users, 'username', {'username': role.value, 'role': role.value,
                'password_hash': hash_password('Demo-Walkthrough-2026')})
        keep_existing(conn, cases, 'slug', {'slug': 'demo', 'title': SPEC['name'],
            'payload': SPEC['sample'], 'author': 'demo', 'created_at': utc_time()})
        seed_trace(conn)
        return {table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
                for table in (users, cases, runs, evidence, audit, lots, productions)}


if __name__ == '__main__':
    schema.create_all(engine)
    print(seed())
