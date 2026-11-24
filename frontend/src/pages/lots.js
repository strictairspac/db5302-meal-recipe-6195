import {heading, panel} from '../components/common/heading.js';
import {records} from '../components/common/records.js';
import {badge} from '../components/common/status.js';
import {kindLabels, lotActionLabels} from '../constants/workflow.js';
import {topic} from '../constants/project.js';
import {date, esc} from '../utils/dom.js';
import {submit} from '../hooks/submit.js';

const INPUT_EXAMPLE = '[{"ingredient":"M01","lot":"L1121","quantity":8},{"semi_batch":"S-R01-1121","quantity":2}]';

function lotForm() {
  return `<h2>登记原料批</h2><form id="lot-form">
    <label class="field"><span>原料编号</span><input name="ingredient" required maxlength="32" placeholder="M01"></label>
    <label class="field"><span>原料批号</span><input name="lot" required maxlength="32" placeholder="L1121"></label>
    <div class="actions"><button>登记原料批</button></div></form>
    <p class="note">同一原料可登记多个批号；封存后禁止投料与出餐。</p>`;
}

function productionForm() {
  return `<form id="production-form"><div class="field-grid">
    <label class="field"><span>生产批号</span><input name="batch" required maxlength="32" placeholder="D-C01-1122"></label>
    <label class="field"><span>类型</span><select name="kind"><option value="semi">半成品</option><option value="dish">成菜</option></select></label>
    <label class="field"><span>配方编号</span><input name="recipe" required maxlength="32" placeholder="C01"></label>
    <label class="field"><span>品名</span><input name="name" required maxlength="80" placeholder="葱油拌面"></label>
    <label class="field"><span>计量单位</span><input name="unit" required maxlength="12" placeholder="份"></label>
    <label class="field"><span>生产数量</span><input name="quantity" required inputmode="decimal" placeholder="120"></label></div>
    <label class="field data"><span>投料明细</span><small>每行引用一个原料批（ingredient + lot）或一个半成品批（semi_batch），并给出 quantity</small><textarea name="inputs" rows="4" spellcheck="false" required>${esc(INPUT_EXAMPLE)}</textarea></label>
    <div class="actions form-actions"><button>登记生产批</button></div></form>
    <p class="note">投料记录保存后不可更改，换批领料请登记新的生产批。</p>`;
}

export function lotsPage(state) {
  const operator = state.session.role==='operator';
  const lotRows = state.lots.map(row=>[esc(row.ingredient), esc(row.lot), badge(row.status),
    esc(row.sealed_by || '—'), esc(date(row.sealed_at)), esc(date(row.created_at)),
    operator && row.status==='active'
      ? `<button class="secondary" data-seal="${esc(row.ingredient)}:${esc(row.lot)}">封存</button>` : '']);
  const productionRows = state.productions.map(row=>[esc(row.batch), esc(kindLabels[row.kind] || row.kind),
    esc(row.name), esc(row.recipe), esc(row.quantity), esc(row.unit), badge(row.status),
    esc(date(row.served_at)), esc(date(row.created_at)),
    operator && row.kind==='dish' && row.status==='produced'
      ? `<button class="secondary" data-serve="${esc(row.batch)}">出餐</button>` : '']);
  const audit = state.audit.filter(row=>row.action in lotActionLabels)
    .map(row=>[esc(row.actor), esc(lotActionLabels[row.action]), esc(date(row.created_at))]);
  return `${heading(topic.modules[4], '按实际投料记录批号，原料批封存后即刻拦截受影响成品。')}
    <div class="spread"><section aria-label="原料批">${records(['原料编号','批号','状态','封存经办','封存时间','登记时间','操作'], lotRows, '尚未登记原料批。')}</section>
    <aside class="brief">${operator ? lotForm() : '<h2>原料批</h2><p class="note">经办员可登记原料批、封存与出餐。</p>'}</aside></div>
    ${operator ? panel('登记生产批', productionForm()) : ''}
    ${panel('生产批记录', records(['生产批号','类型','品名','配方','数量','单位','状态','出餐时间','登记时间','操作'], productionRows, '尚未登记生产批。'))}
    ${audit.length ? panel('操作记录', records(['操作者','操作','时间'], audit)) : ''}`;
}

export function bindLots(api, update, fail) {
  submit('lot-form', async data=>{
    await api('/lots', {method:'POST', data:{ingredient:data.get('ingredient'), lot:data.get('lot')}});
    await update();
  }, fail);
  submit('production-form', async data=>{
    let inputs;
    try { inputs = JSON.parse(data.get('inputs')); }
    catch { throw new Error('投料明细须为 JSON 数组。'); }
    await api('/productions', {method:'POST', data:{
      batch:data.get('batch'), kind:data.get('kind'), recipe:data.get('recipe'),
      name:data.get('name'), unit:data.get('unit'), quantity:data.get('quantity'), inputs}});
    await update();
  }, fail);
  document.querySelectorAll('[data-seal]').forEach(button=>button.addEventListener('click', async()=>{
    const [ingredient, lot] = button.dataset.seal.split(':');
    try { await api('/lots/seal', {method:'POST', data:{ingredient, lot}}); await update(); }
    catch (error) { fail(error); }
  }));
  document.querySelectorAll('[data-serve]').forEach(button=>button.addEventListener('click', async()=>{
    try { await api(`/productions/${encodeURIComponent(button.dataset.serve)}/serve`, {method:'POST'}); await update(); }
    catch (error) { fail(error); }
  }));
}
