import {heading, panel} from '../components/common/heading.js';
import {entries, records} from '../components/common/records.js';
import {badge} from '../components/common/status.js';
import {topic} from '../constants/project.js';
import {date, el, esc} from '../utils/dom.js';
import {submit} from '../hooks/submit.js';

function tracePanel(state) {
  const options = state.lots.map(row=>`<option value="${esc(row.ingredient)}:${esc(row.lot)}">${esc(row.ingredient)} · ${esc(row.lot)}${row.status==='sealed'?'（已封存）':''}</option>`).join('');
  const content = options
    ? `<form id="trace-form" class="actions"><label>原料批<select name="ref">${options}</select></label><button>查询追溯</button></form><div id="trace-result" aria-live="polite"></div>`
    : '<p class="empty">尚未登记原料批。</p>';
  return panel('原料批追溯', content);
}

function traceResult(data) {
  const dishes = data.dishes.map(row=>[esc(row.batch), esc(row.name), esc(row.recipe), badge(row.status), esc(date(row.served_at))]);
  const paths = data.dishes.flatMap(row=>row.paths.map(path=>[esc(row.batch), esc(path)]));
  const semis = data.semis.map(row=>[esc(row.batch), esc(row.name), esc(row.recipe)]);
  return `<p class="note">${esc(data.summary)}</p>
    ${records(['成品批号','品名','配方','出餐状态','出餐时间'], dishes, '没有成品批直接或间接使用该原料批。')}
    ${paths.length?records(['成品批号','用料路径'], paths):''}
    ${semis.length?records(['半成品批号','品名','配方'], semis):''}`;
}

export function evidencePage(state, identity) {
  const current = state.evidence.find(row=>row.id===identity) || state.evidence[0];
  const trace = tracePanel(state);
  if (!current) return heading(topic.modules[3]) + '<p class="empty">执行完成后，可查看、复核和导出证据。</p>' + trace;
  const {report} = current;
  const metrics = Object.entries(report.metrics).map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('');
  const sections = report.sections.map(x=>panel(x.title, entries(x.rows))).join('');
  const review = current.reviewer ? `<p data-testid="reviewed">${esc(current.reviewer)} · ${esc(date(current.reviewed_at))}</p><p>${esc(current.review_note)}</p>`
    : state.session.role==='reviewer'?'<form id="review-form"><label>复核意见<textarea name="note" maxlength="500" required></textarea></label><button>签署复核</button></form>'
    : '<p class="note">待复核员签署</p>';
  const history = state.evidence.map(row=>[`<a href="#evidence/${row.id}">执行 ${row.run_id}</a>`, esc(row.report.summary), esc(row.reviewer || '待复核')]);
  return `${heading(topic.modules[3], report.summary, `<button id="download" data-id="${current.id}">导出证据</button>`)}
    <div class="spread evidence-top"><dl class="metrics">${metrics}</dl><aside class="brief"><h2>复核签署</h2>${review}<details><summary>结果校验码</summary><code class="digest">${esc(current.digest)}</code></details></aside></div>
    ${sections}${trace}<details><summary>历史证据</summary>${records(['执行','结论','复核'], history)}</details>`;
}

export function bindEvidence(api, update, fail) {
  const button = document.getElementById('download');
  if (button) {
    const identity = button.dataset.id;
    button.addEventListener('click', async()=>{
      try {
        const response = await api(`/evidence/${identity}/download`, {response:true});
        const url = URL.createObjectURL(await response.blob());
        const link = el('a');
        link.href = url;
        link.download = `evidence-${identity}.json`;
        link.click();
        setTimeout(()=>URL.revokeObjectURL(url), 1000);
      } catch (error) { fail(error); }
    });
    submit('review-form', async data=>{
      await api(`/evidence/${identity}/review`, {method:'POST', data:{note:data.get('note')}});
      await update();
    }, fail);
  }
  submit('trace-form', async data=>{
    const [ingredient, lot] = data.get('ref').split(':');
    const result = await api(`/lots/trace?ingredient=${encodeURIComponent(ingredient)}&lot=${encodeURIComponent(lot)}`);
    document.getElementById('trace-result').innerHTML = traceResult(result);
  }, fail);
}
