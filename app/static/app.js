"use strict";

const INTERVALO_MS = 30000;
const NOMES_NIVEL = { normal: "Normal", atencao: "Atenção", critico: "Crítico", falha: "Falha do sensor" };
const NOMES_STATUS = {
  suspeita: "aguardando nova medição",
  confirmado: "confirmado",
  descartado: "descartado após nova medição",
  resolvido: "resolvido",
};

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, filhos = []) {
  const no = document.createElement(tag);
  Object.entries(attrs).forEach(([chave, valor]) => {
    if (chave === "class") no.className = valor;
    else no.setAttribute(chave, valor);
  });
  [].concat(filhos).forEach((f) => no.append(f instanceof Node ? f : document.createTextNode(String(f))));
  return no;
}

function numero(valor, casas = 1, sufixo = "") {
  if (valor === null || valor === undefined) return "-";
  return valor.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }) + sufixo;
}

function hora(iso) {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function buscar(caminho) {
  const resposta = await fetch(caminho, { headers: { Accept: "application/json" } });
  if (!resposta.ok) throw new Error(`${caminho} respondeu ${resposta.status}`);
  return resposta.json();
}

function desenharPainel(dados) {
  $("granja").textContent = `${dados.granja} (${dados.municipio})`;
  $("lote").textContent = dados.lote_codigo;
  $("idade").textContent = `${dados.idade_lote_dias} dias`;
  $("conforto").textContent = `${numero(dados.faixa_conforto_c[0], 0)} a ${numero(dados.faixa_conforto_c[1], 0)} °C`;
  $("qtd-criticas").textContent = dados.zonas.filter((z) => z.nivel === "critico").length;

  const robo = $("robo");
  if (dados.minutos_sem_leitura === null) {
    robo.textContent = "O carrinho ainda não enviou leituras";
    robo.className = "estado-robo atrasado";
  } else if (dados.robo_atrasado) {
    robo.textContent = `Carrinho sem enviar leitura há ${dados.minutos_sem_leitura} min`;
    robo.className = "estado-robo atrasado";
  } else {
    robo.textContent = `Carrinho em ronda, última leitura há ${dados.minutos_sem_leitura} min`;
    robo.className = "estado-robo ok";
  }

  const lista = $("zonas");
  lista.replaceChildren(...dados.zonas.map((z) => {
    const nivel = z.nivel || "vazio";
    return el("li", { class: `zona ${nivel}` }, [
      el("h3", {}, `${z.codigo}. ${z.nome}`),
      el("p", { class: "nivel" }, z.nivel ? NOMES_NIVEL[z.nivel] : "Sem leitura"),
      el("dl", {}, [
        el("dt", {}, "Temperatura"), el("dd", {}, numero(z.temperatura_c, 1, " °C")),
        el("dt", {}, "Umidade"), el("dd", {}, numero(z.umidade_pct, 0, "%")),
        el("dt", {}, "CO2"), el("dd", {}, numero(z.co2_ppm, 0, " ppm")),
        el("dt", {}, "ITU"), el("dd", {}, numero(z.itu, 1)),
      ]),
      el("p", { class: "acao" }, z.acao_recomendada),
    ]);
  }));
}

function desenharAlertas(alertas) {
  const lista = $("alertas");
  if (!alertas.length) {
    lista.replaceChildren(el("li", {}, "Nenhum alerta no momento."));
    return;
  }
  lista.replaceChildren(...alertas.slice(0, 8).map((a) => el("li", {}, [
    el("span", { class: `selo ${a.nivel}` }, NOMES_NIVEL[a.nivel] || a.nivel),
    el("strong", {}, `Zona ${a.zona_codigo}: ${NOMES_STATUS[a.status] || a.status}. `),
    a.motivo,
    el("br"),
    el("span", { class: "quando" }, `${hora(a.atualizado_em)}. ${a.acao_recomendada}`),
  ])));
}

function desenharImpacto(linhas) {
  const corpo = $("impacto");
  if (!linhas.length) {
    corpo.replaceChildren(el("tr", {}, el("td", { colspan: "4" }, "Ainda não há leituras neste lote.")));
    return;
  }
  corpo.replaceChildren(...linhas.map((l) => el("tr", {}, [
    el("th", { scope: "row" }, l.zona_codigo),
    el("td", {}, l.leituras),
    el("td", {}, l.leituras_fora),
    el("td", {}, numero(l.percentual_fora, 1, "%")),
  ])));
}

function desenharClima(clima) {
  const lista = $("clima");
  if (!clima.disponivel) {
    lista.replaceChildren(el("li", {}, clima.mensagem));
    return;
  }
  lista.replaceChildren(...clima.datas.map((d, i) => {
    const dia = new Date(`${d}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit" });
    return el("li", {}, [el("strong", {}, `${dia}: `), numero(clima.temperatura_max_c[i], 0, " °C")]);
  }));
}

async function atualizar() {
  // Cada bloco falha sozinho: se uma parte cair, o resto do painel continua útil.
  const tarefas = [
    buscar("/api/v1/painel").then(desenharPainel),
    buscar("/api/v1/alertas?limite=20").then(desenharAlertas),
    buscar("/api/v1/indicadores/fora-do-limite").then(desenharImpacto),
    buscar("/api/v1/clima").then(desenharClima),
  ];
  const resultados = await Promise.allSettled(tarefas);
  if (resultados[0].status === "rejected") {
    $("robo").textContent = "Sem conexão com o servidor. Tentando de novo em 30 segundos.";
    $("robo").className = "estado-robo atrasado";
  }
}

atualizar();
setInterval(atualizar, INTERVALO_MS);
