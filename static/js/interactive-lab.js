/* Local-only tools: no network, cookies, storage or third-party dependencies. */
(function () {
  'use strict';
  function calculateMargin(data) {
    const bounds = {revenue: [1, 1e12], variable: [0, 1e12], fixed: [0, 1e12], discount: [0, 100], days: [0, 730], targetDays: [0, 730]};
    for (const [key, [min, max]] of Object.entries(bounds)) {
      if (typeof data[key] !== 'number' || !Number.isFinite(data[key]) || data[key] < min || data[key] > max) throw new RangeError('Valore non valido: ' + key);
    }
    if (!Number.isInteger(data.days) || !Number.isInteger(data.targetDays)) throw new RangeError('Usa giorni interi');
    const scenarioRevenue = data.revenue * (1 - data.discount / 100);
    const contribution = data.revenue - data.variable;
    const scenarioContribution = scenarioRevenue - data.variable;
    const operating = contribution - data.fixed;
    const scenarioOperating = scenarioContribution - data.fixed;
    return {scenarioRevenue, contribution, scenarioContribution, operating, scenarioOperating,
      operatingRate: operating / data.revenue * 100,
      scenarioRate: scenarioRevenue === 0 ? null : scenarioOperating / scenarioRevenue * 100,
      revenueLoss: data.revenue - scenarioRevenue,
      currentReceivables: data.revenue / 365 * data.days,
      scenarioReceivables: scenarioRevenue / 365 * data.targetDays,
      daysOnlyRelease: data.revenue / 365 * (data.days - data.targetDays)};
  }
  const questions = [
    ['Margini per prodotto o servizio', 'Ricostruisci ricavi e costi attribuibili per prodotto o commessa, distinguendo costi variabili e fissi.'],
    ['Previsione di cassa', 'Prepara una previsione settimanale degli incassi e dei pagamenti, evidenziando le date a rischio.'],
    ['Budget e scostamenti', 'Confronta risultati e budget con cadenza regolare e assegna una causa agli scostamenti rilevanti.'],
    ['Coerenza dei dati tra reparti', 'Individua una fonte condivisa per ogni dato e controlla duplicazioni e passaggi manuali.'],
    ['Crediti e incassi', 'Esamina lo scadenzario clienti e attribuisci un responsabile al sollecito degli importi scaduti.'],
    ['Responsabilità operative', 'Per ogni attività chiave chiarisci chi decide, chi esegue e come si verifica il risultato.'],
    ['Qualità dei dati', 'Controlla origine, completezza, data di aggiornamento e riconciliazione dei dati usati per decidere.'],
    ['Verifica delle azioni', 'Per ogni intervento registra obiettivo, indicatore, responsabile e data della verifica successiva.']
  ];
  function assess(answers) {
    if (answers.length !== questions.length || answers.some(x => !Number.isInteger(x) || x < 0 || x > 2)) throw new RangeError('Completa le otto risposte');
    return {toExplore: answers.filter(x => x === 0).length, partial: answers.filter(x => x === 1).length, systematic: answers.filter(x => x === 2).length};
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {calculateMargin, assess};
  if (typeof document === 'undefined') return;
  const root = document.getElementById('laboratorio-impresa');
  if (!root) return;
  const money = n => new Intl.NumberFormat('it-IT', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}).format(Math.abs(n) < 0.5 ? 0 : n);
  const pct = n => n === null ? 'Non definita (ricavi zero)' : new Intl.NumberFormat('it-IT', {maximumFractionDigits: 1}).format(n) + '%';
  const el = (tag, text, parent) => {const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (parent) parent.appendChild(node); return node;};
  const marginForm = document.getElementById('mgc-margin-form');
  const marginResult = document.getElementById('mgc-margin-result');
  const marginPrint = root.querySelector('[data-print="margin"]');
  marginForm.addEventListener('input', () => {marginResult.hidden = true; marginPrint.hidden = true;});
  marginForm.addEventListener('submit', event => {
    event.preventDefault();
    if (!marginForm.reportValidity()) return;
    const d = Object.fromEntries(Array.from(new FormData(marginForm), ([k, v]) => [k, Number(v)]));
    let result;
    try {result = calculateMargin(d);} catch (_) {marginResult.replaceChildren(); el('p', 'Controlla i valori: usa numeri finiti e giorni interi nei limiti indicati.', marginResult); marginResult.hidden = false; marginPrint.hidden = true; return;}
    marginResult.replaceChildren();
    el('h4', 'Il prezzo cambia il margine. I tempi cambiano la cassa.', marginResult);
    const wrap = el('div', undefined, marginResult); wrap.className = 'mgc-table-wrap';
    const table = el('table', undefined, wrap); el('caption', 'Confronto annuale a volumi invariati', table);
    const head = el('tr', undefined, el('thead', undefined, table));
    ['Indicatore', 'Situazione iniziale', 'Scenario'].forEach(t => {el('th', t, head).scope = 'col';});
    const body = el('tbody', undefined, table);
    [ ['Ricavi', money(d.revenue), money(result.scenarioRevenue)],
      ['Margine di contribuzione', money(result.contribution), money(result.scenarioContribution)],
      ['Risultato operativo semplificato', money(result.operating), money(result.scenarioOperating)],
      ['Risultato / ricavi', pct(result.operatingRate), pct(result.scenarioRate)],
      ['Giorni medi di incasso', String(d.days), String(d.targetDays)],
      ['Crediti stimati a regime', money(result.currentReceivables), money(result.scenarioReceivables)]
    ].forEach(row => {const tr = el('tr', undefined, body); row.forEach((v, i) => {const cell = el(i === 0 ? 'th' : 'td', v, tr); if (i === 0) cell.scope = 'row';});});
    el('p', 'Con uno sconto del ' + pct(d.discount) + ', a volumi e costi invariati, il risultato operativo si riduce di ' + money(result.revenueLoss) + ' annui.', marginResult);
    el('p', result.daysOnlyRelease >= 0 ? 'A ricavi iniziali costanti, passare da ' + d.days + ' a ' + d.targetDays + ' giorni riduce il capitale nei crediti di circa ' + money(result.daysOnlyRelease) + '. Non è utile aggiuntivo né un incasso garantito.' : 'A ricavi iniziali costanti, allungare gli incassi da ' + d.days + ' a ' + d.targetDays + ' giorni assorbe circa ' + money(-result.daysOnlyRelease) + ' in più nei crediti. Non è una perdita economica dello stesso importo.', marginResult);
    if (result.scenarioOperating < 0) el('p', 'Attenzione: nello scenario il risultato operativo semplificato è negativo. Occorre approfondire prezzi, volumi e struttura dei costi.', marginResult);
    el('p', 'Input: costi variabili ' + money(d.variable) + '; costi fissi operativi ' + money(d.fixed) + '; sconto aggiuntivo ' + pct(d.discount) + '.', marginResult);
    el('p', 'Ipotesi: periodo annuale, volumi e costi invariati; vendite tutte a credito e uniformi, valori al netto IVA. Risultato = ricavi − costi variabili − costi fissi operativi. Crediti = ricavi / 365 × giorni. Non sono modellati imposte, oneri finanziari, investimenti o stagionalità. Stima esplorativa, non bilancio o consulenza.', marginResult);
    marginResult.hidden = false; marginPrint.hidden = false;
  });
  const stages = [
    ['Vendite', "L'ordine viene trascritto dall'email in un foglio. Quantità e data richiesta possono divergere tra le copie.", "L'ordine DEMO-104 diventa il riferimento condiviso: quantità, data e revisione sono visibili ai reparti autorizzati.", 'Controllo: confermare condizioni, quantità e versione approvata dal cliente.'],
    ['Magazzino', 'La disponibilità viene chiesta per telefono. Una scorta fisica può essere già impegnata per un altro ordine.', 'Il flusso distingue giacenza fisica, impegni e disponibilità. Una carenza viene segnalata prima di pianificare.', 'Controllo: riconciliare le giacenze e gestire gli impegni, non assumere che disponibile equivalga a presente.'],
    ['Produzione', 'La commessa viaggia su fogli separati. Tempi e consumi vengono ricostruiti a posteriori.', 'Alla commessa dimostrativa vengono associati fasi, responsabili, tempi e consumi registrati.', 'Controllo: validare avanzamenti e consuntivi; il software non sostituisce i controlli di qualità.'],
    ['Consegna', 'La quantità consegnata viene ricopiata. I residui delle consegne parziali possono perdere allineamento.', "Si confrontano quantità ordinata, completata, consegnata e residua prima di autorizzare l'uscita.", 'Controllo: autorizzazione della consegna e verifica documentale. Nessun DDT reale viene generato qui.'],
    ['Controllo di gestione', 'Il margine viene ricostruito unendo fogli diversi, spesso quando la commessa è già chiusa.', 'Ricavi e costi registrati alimentano un confronto tra preventivo e consuntivo, con evidenza degli scostamenti.', 'Controllo: controllare completezza e criteri di attribuzione dei costi prima di decidere.']
  ];
  let stage = 0, mode = 'before';
  const prev = document.getElementById('mgc-process-prev'), next = document.getElementById('mgc-process-next');
  function renderProcess() {
    const output = document.getElementById('mgc-process-result'); output.replaceChildren();
    el('h4', (stage + 1) + '/5 · ' + stages[stage][0] + ' · ' + (mode === 'before' ? 'dati separati' : 'flusso collegato'), output);
    el('p', stages[stage][mode === 'before' ? 1 : 2], output); el('p', stages[stage][3], output);
    root.querySelectorAll('[data-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mode === mode)));
    document.querySelectorAll('#mgc-process-steps li').forEach((item, i) => {if(i === stage) item.setAttribute('aria-current', 'step'); else item.removeAttribute('aria-current');});
    prev.disabled = stage === 0; next.disabled = stage === stages.length - 1;
  }
  prev.addEventListener('click', () => {stage = Math.max(0, stage - 1); renderProcess();});
  next.addEventListener('click', () => {stage = Math.min(4, stage + 1); renderProcess();});
  document.getElementById('mgc-process-reset').addEventListener('click', () => {stage = 0; mode = 'before'; renderProcess();});
  root.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => {mode = button.dataset.mode; renderProcess();}));
  renderProcess();
  const checkForm = document.getElementById('mgc-check-form'), checkResult = document.getElementById('mgc-check-result'), checkPrint = root.querySelector('[data-print="check"]');
  const hideCheck = () => {checkResult.hidden = true; checkPrint.hidden = true;};
  checkForm.addEventListener('change', hideCheck); checkForm.addEventListener('reset', hideCheck);
  checkForm.addEventListener('submit', event => {
    event.preventDefault(); if (!checkForm.reportValidity()) return;
    const form = new FormData(checkForm), answers = questions.map((_, i) => Number(form.get('q' + i)));
    const result = assess(answers); checkResult.replaceChildren(); el('h4', 'La mappa delle tue risposte', checkResult);
    el('p', result.toExplore + ' aree da chiarire · ' + result.partial + ' pratiche da consolidare · ' + result.systematic + ' pratiche dichiarate sistematiche.', checkResult);
    el('p', 'Non è un voto: “No / Non so” indica un punto da verificare, non dimostra che il controllo sia assente. Le risposte non sono verificate con documenti.', checkResult);
    const list = el('ol', undefined, checkResult);
    const labels = ['No / Non so: da chiarire', 'In parte: da consolidare', 'Sì, sistematicamente: da mantenere e verificare'];
    questions.forEach(([topic, action], i) => {const li = el('li', undefined, list); el('strong', topic + ' — ' + labels[answers[i]] + '.', li); el('p', action, li);});
    el('p', 'Primo passo: scegli un’area da chiarire o consolidare, assegna un responsabile e una data di verifica. Se tutte le pratiche sono sistematiche, verificane le evidenze e la continuità.', checkResult);
    checkResult.hidden = false; checkPrint.hidden = false;
  });
  const printReport = document.getElementById('mgc-print-report');
  function cleanPrint() {document.body.classList.remove('mgc-printing'); printReport.hidden = true; printReport.replaceChildren();}
  window.addEventListener('afterprint', cleanPrint);
  root.querySelectorAll('[data-print]').forEach(button => button.addEventListener('click', () => {
    const source = button.dataset.print === 'margin' ? marginResult : checkResult;
    if (source.hidden) return;
    printReport.replaceChildren(); el('h1', 'Maurizio Gustinicchi Consulting', printReport);
    el('h2', button.dataset.print === 'margin' ? 'Simulazione margine e liquidità' : 'Autovalutazione del controllo di gestione', printReport);
    el('p', 'Riepilogo generato il ' + new Date().toLocaleDateString('it-IT') + ' · Dati e risposte forniti dall’utilizzatore, non verificati.', printReport);
    const copy = source.cloneNode(true); copy.removeAttribute('id'); copy.removeAttribute('role'); copy.removeAttribute('aria-live'); printReport.appendChild(copy);
    el('p', 'Strumento esplorativo: non è un audit, una previsione garantita o consulenza personalizzata. www.mauriziogustinicchiconsulting.it', printReport);
    printReport.hidden = false; document.body.classList.add('mgc-printing');
    try {window.print();} catch (_) {cleanPrint();}
  }));
  function openHash() {const target = document.getElementById(location.hash.slice(1)); if(target && target.matches('.mgc-card')) target.open = true;}
  window.addEventListener('hashchange', openHash); openHash();
})();
