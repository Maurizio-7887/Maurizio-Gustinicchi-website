/* Da dove e' arrivato il visitatore in questa sessione (Google, ChatGPT, social...).
   Resta solo nel browser (sessionStorage, si cancella chiudendo la scheda) e viene
   inviato SOLO se il visitatore compila e invia un modulo. Nessun cookie. */
(function () {
  var K = 'mgc_ingresso', dati = null;
  try { dati = JSON.parse(sessionStorage.getItem(K) || 'null'); } catch (e) {}
  if (!dati) {
    var ref = document.referrer || '', interno = false;
    try { interno = ref && new URL(ref).hostname.indexOf('mauriziogustinicchiconsulting.it') !== -1; } catch (e) {}
    var q = new URLSearchParams(location.search);
    dati = { referrer: interno ? '' : ref, pagina: location.pathname,
             utm_source: q.get('utm_source') || '', utm_medium: q.get('utm_medium') || '', gclid: q.get('gclid') || '' };
    try { sessionStorage.setItem(K, JSON.stringify(dati)); } catch (e) {}
  }
  document.addEventListener('submit', function (ev) {
    var f = ev.target;
    if (!f || f.method.toLowerCase() !== 'post') return;
    [['ingresso_referrer', dati.referrer], ['ingresso_pagina', dati.pagina], ['ingresso_utm_source', dati.utm_source],
     ['ingresso_utm_medium', dati.utm_medium], ['ingresso_gclid', dati.gclid]].forEach(function (c) {
      if (f.querySelector('input[name="' + c[0] + '"]')) return;
      var i = document.createElement('input'); i.type = 'hidden'; i.name = c[0]; i.value = (c[1] || '').slice(0, 300);
      f.appendChild(i);
    });
  }, true);
})();
