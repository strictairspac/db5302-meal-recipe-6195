"""原料批封存、生产投料登记与成品出餐追溯。

- 投料记录写入后不可更改，换批领料只新增记录。
- 出餐登记在同一事务内对涉及的原料批做当前读加锁：并发封存一旦提交，
  受影响成品批立即被拦截；未使用该批的同名成品不受影响。
- 出餐用条件更新保证幂等：同一成品批不会重复记作已出餐，失败可重试。
"""

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from src.config.settings import engine
from src.constants.workflow import LotStatus, ProductionKind, ProductionStatus
from src.models.tables import batch_inputs, lots, productions
from src.services import domain
from src.services.workflow import found, log
from src.utils.time import utc_time

MAX_TRACE_PATHS = 2_000
KINDS = {kind.value for kind in ProductionKind}


def _code(value, label):
    try:
        return domain._code(value, label)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


def _text(value, label, maximum):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise HTTPException(422, f'{label}须填写 1 至 {maximum} 个字符。')
    return value.strip()


def _amount(value, label):
    try:
        return domain._quantity(domain._decimal(value, label, 1_000_000))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


def _lot_row(conn, ingredient, lot):
    row = conn.execute(select(lots).where(lots.c.ingredient == ingredient,
                                          lots.c.lot == lot)).mappings().first()
    if row is None:
        raise HTTPException(404, f'原料批 {ingredient}:{lot} 未登记')
    return row


def recent_lots():
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(
            select(lots).order_by(lots.c.id.desc()).limit(200)).mappings()]


def recent_productions():
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(
            select(productions).order_by(productions.c.id.desc()).limit(200)).mappings()]


def register_lot(form, actor):
    ingredient = _code(form.ingredient, '原料编号')
    lot = _code(form.lot, '原料批号')
    try:
        with engine.begin() as conn:
            if conn.execute(select(lots.c.id).where(lots.c.ingredient == ingredient,
                                                    lots.c.lot == lot)).first():
                raise HTTPException(409, f'原料批 {ingredient}:{lot} 已登记')
            lot_id = conn.execute(lots.insert().values(
                ingredient=ingredient, lot=lot, status=LotStatus.ACTIVE,
                created_at=utc_time())).inserted_primary_key[0]
            log(conn, actor, 'register_lot', lot_id)
            return found(conn, lots, lot_id)
    except IntegrityError:
        raise HTTPException(409, f'原料批 {ingredient}:{lot} 已登记') from None


def seal_lot(form, actor):
    ingredient = _code(form.ingredient, '原料编号')
    lot = _code(form.lot, '原料批号')
    with engine.begin() as conn:
        row = _lot_row(conn, ingredient, lot)
        count = conn.execute(lots.update()
                             .where(lots.c.id == row['id'], lots.c.status == LotStatus.ACTIVE)
                             .values(status=LotStatus.SEALED, sealed_by=actor,
                                     sealed_at=utc_time())).rowcount
        if count != 1:
            raise HTTPException(409, f'原料批 {ingredient}:{lot} 已封存，请勿重复封存')
        log(conn, actor, 'seal_lot', row['id'])
        return found(conn, lots, row['id'])


def _prepare_inputs(rows):
    entries, seen = [], set()
    for row in rows:
        quantity = _amount(row.quantity, '投料量')
        if row.semi_batch is not None:
            if row.ingredient is not None or row.lot is not None:
                raise HTTPException(422, '同一行投料只能引用原料批或半成品批之一。')
            semi = _code(row.semi_batch, '半成品批号')
            key = ('semi', semi)
            entry = {'semi_batch': semi, 'quantity': quantity}
        else:
            ingredient = _code(row.ingredient, '原料编号')
            lot = _code(row.lot, '原料批号')
            key = ('lot', ingredient, lot)
            entry = {'ingredient': ingredient, 'lot': lot, 'quantity': quantity}
        if key in seen:
            raise HTTPException(422, '投料明细存在重复行，请合并用量。')
        seen.add(key)
        entries.append(entry)
    return entries


def register_production(form, actor):
    batch = _code(form.batch, '生产批号')
    recipe = _code(form.recipe, '配方编号')
    if form.kind not in KINDS:
        raise HTTPException(422, '生产类型须为 semi（半成品）或 dish（成菜）。')
    name = _text(form.name, '品名', 80)
    unit = _text(form.unit, '计量单位', 12)
    quantity = _amount(form.quantity, '生产数量')
    entries = _prepare_inputs(form.inputs)
    try:
        with engine.begin() as conn:
            if conn.execute(select(productions.c.id)
                            .where(productions.c.batch == batch)).first():
                raise HTTPException(409, f'生产批号 {batch} 已登记，历史投料记录不可更改')
            rows = []
            for entry in entries:
                if 'semi_batch' in entry:
                    semi = conn.execute(select(productions).where(
                        productions.c.batch == entry['semi_batch'])).mappings().first()
                    if semi is None:
                        raise HTTPException(422, f"半成品批 {entry['semi_batch']} 未登记")
                    if semi['kind'] != ProductionKind.SEMI:
                        raise HTTPException(422, f"生产批 {entry['semi_batch']} 是成菜，不能作为投料")
                    rows.append({'ingredient': None, 'lot': None,
                                 'semi_batch': entry['semi_batch'], 'quantity': entry['quantity']})
                    continue
                lot = conn.execute(select(lots).where(lots.c.ingredient == entry['ingredient'],
                                                      lots.c.lot == entry['lot'])
                                   .with_for_update()).mappings().first()
                if lot is None:
                    raise HTTPException(422, f"原料批 {entry['ingredient']}:{entry['lot']} 未登记")
                if lot['status'] == LotStatus.SEALED:
                    raise HTTPException(409, f"原料批 {entry['ingredient']}:{entry['lot']} 已封存，禁止投料")
                rows.append({'ingredient': entry['ingredient'], 'lot': entry['lot'],
                             'semi_batch': None, 'quantity': entry['quantity']})
            production_id = conn.execute(productions.insert().values(
                batch=batch, kind=form.kind, recipe=recipe, name=name, unit=unit,
                quantity=quantity, status=ProductionStatus.PRODUCED,
                author=actor, created_at=utc_time())).inserted_primary_key[0]
            conn.execute(batch_inputs.insert(),
                         [dict(row, production_id=production_id) for row in rows])
            log(conn, actor, 'produce', production_id)
            return found(conn, productions, production_id)
    except IntegrityError:
        raise HTTPException(409, f'生产批号 {batch} 已登记，历史投料记录不可更改') from None


def _involved_lots(conn, production_id):
    """汇总该生产批直接和间接投料涉及的原料批。投料记录不可变，快照读即可。"""
    involved, seen, frontier = set(), {production_id}, [production_id]
    while frontier:
        rows = conn.execute(select(batch_inputs)
                            .where(batch_inputs.c.production_id.in_(frontier))).all()
        frontier = []
        semi_batches = []
        for row in rows:
            if row.ingredient is not None:
                involved.add((row.ingredient, row.lot))
            else:
                semi_batches.append(row.semi_batch)
        if semi_batches:
            children = conn.execute(select(productions.c.id)
                                    .where(productions.c.batch.in_(semi_batches))).all()
            frontier.extend(pid for (pid,) in children if pid not in seen)
            seen.update(frontier)
    return involved


def _sealed_inputs(conn, production_id):
    involved = _involved_lots(conn, production_id)
    if not involved:
        return []
    # 当前读并加行锁：并发封存一旦提交，这里立即读到封存状态；
    # 尚未提交的封存事务会阻塞本事务直至其结束，保证封存先生效先拦截。
    rows = conn.execute(select(lots.c.ingredient, lots.c.lot, lots.c.status)
                        .where(or_(*(and_(lots.c.ingredient == ingredient, lots.c.lot == lot)
                                     for ingredient, lot in involved)))
                        .with_for_update()).mappings().all()
    return [row for row in rows if row['status'] == LotStatus.SEALED]


def serve(batch, actor):
    with engine.begin() as conn:
        row = conn.execute(select(productions).where(productions.c.batch == batch)
                           .with_for_update()).mappings().first()
        if row is None:
            raise HTTPException(404, f'生产批 {batch} 未登记')
        if row['kind'] != ProductionKind.DISH:
            raise HTTPException(422, f'生产批 {batch} 是半成品，不能登记出餐')
        if row['status'] == ProductionStatus.SERVED:
            raise HTTPException(409, f'成品批 {batch} 已出餐，请勿重复登记')
        sealed = _sealed_inputs(conn, row['id'])
        if sealed:
            names = '、'.join(f"{item['ingredient']}:{item['lot']}" for item in sealed)
            raise HTTPException(409, f'成品批 {batch} 直接或间接使用了已封存原料批 {names}，禁止出餐')
        count = conn.execute(productions.update()
                             .where(productions.c.id == row['id'],
                                    productions.c.status == ProductionStatus.PRODUCED)
                             .values(status=ProductionStatus.SERVED, served_by=actor,
                                     served_at=utc_time())).rowcount
        if count != 1:
            raise HTTPException(409, f'成品批 {batch} 已出餐，请勿重复登记')
        log(conn, actor, 'serve', row['id'])
        return found(conn, productions, row['id'])


def trace_lot(ingredient, lot):
    ingredient = _code(ingredient, '原料编号')
    lot = _code(lot, '原料批号')
    with engine.connect() as conn:
        lot_row = _lot_row(conn, ingredient, lot)
        direct = conn.execute(select(batch_inputs.c.production_id)
                              .where(batch_inputs.c.ingredient == ingredient,
                                     batch_inputs.c.lot == lot)).all()
        dishes, semis = {}, set()
        queue = [(pid,) for (pid,) in direct]
        budget = MAX_TRACE_PATHS
        while queue:
            path = queue.pop()
            current = conn.execute(select(productions.c.kind, productions.c.batch)
                                   .where(productions.c.id == path[-1])).one()
            if current.kind == ProductionKind.DISH:
                dishes.setdefault(path[-1], []).append(path)
                continue
            semis.add(path[-1])
            children = conn.execute(select(batch_inputs.c.production_id)
                                    .where(batch_inputs.c.semi_batch == current.batch)).all()
            for (child_id,) in children:
                if child_id in path:
                    continue
                budget -= 1
                if budget < 0:
                    raise HTTPException(422, f'追溯路径超过 {MAX_TRACE_PATHS} 条，请缩小批次范围')
                queue.append(path + (child_id,))
        ids = sorted(dishes.keys() | semis)
        rows = {row['id']: row for row in conn.execute(
            select(productions).where(productions.c.id.in_(ids))).mappings()} if ids else {}

        def label(pid):
            return f"{rows[pid]['name']}（{rows[pid]['batch']}）"

        head = f'{ingredient}:{lot}'
        dish_rows = [{
            'batch': rows[pid]['batch'], 'recipe': rows[pid]['recipe'],
            'name': rows[pid]['name'], 'status': rows[pid]['status'],
            'served_at': rows[pid]['served_at'],
            'paths': [' → '.join([head, *(label(p) for p in path)]) for path in paths],
        } for pid, paths in sorted(dishes.items())]
        semi_rows = [{'batch': rows[pid]['batch'], 'recipe': rows[pid]['recipe'],
                      'name': rows[pid]['name']} for pid in sorted(semis)]
        served = sum(row['status'] == ProductionStatus.SERVED for row in dish_rows)
        return {
            'lot': dict(lot_row),
            'dishes': dish_rows,
            'semis': semi_rows,
            'summary': (f'原料批 {ingredient}:{lot} 直接投料 {len(direct)} 次，'
                        f'关联半成品批 {len(semi_rows)} 个、成品批 {len(dish_rows)} 个，'
                        f'其中已出餐 {served} 个。'),
        }
