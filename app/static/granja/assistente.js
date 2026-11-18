/*
 * AviRonda: assistente de perguntas (protótipo do RAG da disciplina Generative AI).
 * POST /api/v1/assistente e mostra a resposta, o JSON do contrato e os 4 passos com os valores reais da busca.
 * Sem innerHTML com dado do servidor: tudo entra por textContent (CSP script-src 'self').
 */
(function () {
  'use strict';

  var dialogo = document.getElementById('ar-assistente');
  var abrir = document.getElementById('ar-assistente-abrir');
  if (!dialogo || !abrir || typeof dialogo.showModal !== 'function') {
    if (abrir) abrir.hidden = true;
    return;
  }
  var form = document.getElementById('ar-assistente-form');
  var campo = document.getElementById('ar-assistente-pergunta');
  var saida = document.getElementById('ar-assistente-saida');

  function el(tag, classe, texto) {
    var n = document.createElement(tag);
    if (classe) n.className = classe;
    if (texto !== undefined && texto !== null) n.textContent = texto;
    return n;
  }
  function num(v, casas) {
    return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  }

  function passo(n, titulo, detalhe, extra) {
    var li = el('li');
    li.appendChild(el('span', 'ar-passos__n', String(n)));
    var corpo = el('div');
    corpo.appendChild(el('p', 'ar-passos__t', titulo));
    if (detalhe) corpo.appendChild(el('p', 'ar-passos__d', detalhe));
    if (extra) corpo.appendChild(extra);
    li.appendChild(corpo);
    return li;
  }

  function mostrar(r) {
    var p = r.passos;
    saida.replaceChildren();

    var cartao = el('div', 'ar-resposta ' + (r.encontrou ? 'nv-normal' : 'nv-semleitura'));
    cartao.appendChild(el('span', 'ar-resposta__nivel', r.encontrou ? '✓ Encontrou na base' : '● Não consta na base'));
    cartao.appendChild(el('p', 'ar-resposta__texto', r.resposta));
    if (r.encontrou) {
      var trecho = p.contexto[0];
      cartao.appendChild(el('p', 'ar-resposta__fonte', 'Fonte: ' + trecho.id + ' · ' + trecho.fonte));
    } else {
      cartao.appendChild(el('p', 'ar-resposta__fonte', 'Nenhum trecho chegou perto o bastante. Ele recusa em vez de inventar.'));
    }
    saida.appendChild(cartao);

    saida.appendChild(el('pre', 'ar-json', JSON.stringify({ resposta: r.resposta, fonte: r.fonte, encontrou: r.encontrou }, null, 2)));

    var lista = el('ol', 'ar-passos');
    lista.setAttribute('aria-label', 'Como a resposta foi encontrada');
    lista.appendChild(passo(1, 'A pergunta virou números',
      'Um vetor com ' + p.termos_da_pergunta + ' termos com peso, num espaço de ' + p.dimensoes_do_vetor + ' dimensões, que representa o assunto da pergunta.'));

    var dist = el('ul', 'ar-dist');
    p.contexto.forEach(function (c) {
      var li = el('li');
      li.appendChild(el('span', 'ar-dist__id', c.id));
      var barra = el('span', 'ar-dist__barra');
      barra.setAttribute('aria-hidden', 'true');
      var cheio = el('span', c.distancia <= p.limite_distancia ? '' : 'fora');
      cheio.style.width = Math.max(2, Math.round((1 - c.distancia) * 100)) + '%';
      var marca = el('i');
      marca.style.left = Math.round((1 - p.limite_distancia) * 100) + '%';
      barra.appendChild(cheio);
      barra.appendChild(marca);
      li.appendChild(barra);
      li.appendChild(el('span', 'ar-dist__v', num(c.distancia, 3)));
      li.setAttribute('title', c.fonte);
      dist.appendChild(li);
    });
    lista.appendChild(passo(2, 'Comparou com os ' + p.trechos_na_base + ' trechos da base',
      'Distância de cosseno: quanto menor, mais perto. Acima de ' + num(p.limite_distancia, 2) + ' (o traço vermelho), ele recusa.', dist));

    lista.appendChild(passo(3, 'Os 3 trechos mais próximos viraram o contexto',
      p.contexto.map(function (c) { return c.id + ' (' + c.fonte + ')'; }).join('; ') + '.'));
    lista.appendChild(passo(4, r.encontrou ? 'Respondeu só com o contexto, citando o trecho ' + r.fonte : 'Recusou: não consta na base',
      r.encontrou ? 'A resposta é a frase do trecho ' + r.fonte + ' que mais se parece com a pergunta.' : 'Melhor distância: ' + num(p.contexto[0].distancia, 3) + ', acima do limite.'));
    saida.appendChild(lista);
  }

  function perguntar(texto) {
    saida.replaceChildren(el('p', 'ar-card__sub', 'Buscando nos trechos...'));
    fetch('/api/v1/assistente', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ pergunta: texto })
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(mostrar).catch(function (e) {
      console.error('[assistente]', e);
      saida.replaceChildren(el('p', 'ar-resposta nv-semleitura', 'Não consegui consultar a base agora. Tente de novo em instantes.'));
    });
  }

  abrir.addEventListener('click', function () {
    dialogo.showModal();
    campo.focus();
  });
  document.getElementById('ar-assistente-fechar').addEventListener('click', function () { dialogo.close(); });
  // Esc fecha só o assistente, sem voltar a visão da granja.
  dialogo.addEventListener('keydown', function (e) { if (e.key === 'Escape') e.stopPropagation(); });
  dialogo.addEventListener('click', function (e) { if (e.target === dialogo) dialogo.close(); });
  dialogo.addEventListener('close', function () { abrir.focus(); });
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var texto = campo.value.trim();
    if (texto.length >= 3) perguntar(texto);
  });
  dialogo.querySelectorAll('[data-pergunta]').forEach(function (b) {
    b.addEventListener('click', function () {
      campo.value = b.dataset.pergunta;
      perguntar(b.dataset.pergunta);
    });
  });
})();
