/*
 * AviRonda: tela "Minha granja hoje"
 * HTML, CSS e JavaScript puros + three.js r147 (build UMD em vendor/).
 * Compatível com Content Security Policy script-src 'self': nenhum script inline,
 * nenhum onclick no HTML, nenhum style inline gerado por innerHTML
 * (posições e cores dinâmicas são aplicadas por CSSOM ou por classes).
 * Dados: GET /api/v1/propriedade (atributo data-api), lido por adaptar().
 * Se a página tiver data-exemplo e a API falhar na primeira carga, usa o arquivo de exemplo.
 */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var ICONE_VOLTAR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"></path></svg>';
  var ICONE_INFO = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#1f5f3f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v5"></path><path d="M12 16.5v.01"></path></svg>';

  class Painel {
    constructor(root) {
      this.root = root;
      this.D = null;
      this.t3 = null;
      this.state = { sel: null, zona: null, modo: 'carregando', reduz: false };
      this.$ = function (id) { return document.getElementById(id); };
      try { this.state.reduz = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { /* ok */ }
      var q = new URLSearchParams(location.search);
      this.forcar2d = q.get('modo') === '2d';
      this.inicial = q.get('galpao');
      this.ligarEventos();
      this.carregar(true);
      var seg = +(root.dataset.atualizarSeg || 0);
      var self = this;
      if (seg > 0) setInterval(function () { self.carregar(false); }, seg * 1000);
    }

    dados() { return this.D; }

    /* Contrato real da API: galpão em vazio sanitário vem sem lote, zona sem leitura vem com valores nulos. */
    adaptar(d) {
      d.galpoes.forEach(function (g) {
        if (g.vazio_sanitario) {
          g.lote_codigo = 'sem lote';
          g.idade_lote_dias = 0;
          g.faixa_conforto_c = [0, 0];
          g.minutos_sem_leitura = 0;
        }
      });
      d.alertas = d.alertas || [];
      d.previsao_max_c = d.previsao_max_c || [];
      return d;
    }
    semDado(n) { return n === null || n === undefined; }

    carregar(primeira) {
      var self = this;
      var api = this.root.dataset.api, ex = this.root.dataset.exemplo;
      var pega = function (url) {
        return fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' }).then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        });
      };
      var p = api ? pega(api) : Promise.reject(new Error('sem api'));
      p.catch(function () { return primeira && ex ? pega(ex) : null; }).then(function (d) {
        if (!d || !d.galpoes) return;
        d = self.adaptar(d);
        var mudou = !self.D || self.D.atualizado_em !== d.atualizado_em;
        self.D = d;
        if (primeira) self.iniciar();
        else if (mudou) { self.atualizarCores3d(); self.render(); }
      });
    }

    iniciar() {
      var sel = (this.inicial && this.galpao(this.inicial)) ? this.inicial : null;
      var modo = (!this.forcar2d && this.temWebGL()) ? '3d' : '2d';
      this.state.sel = sel;
      this.state.zona = sel ? this.zonaProblema(sel) : null;
      this.state.modo = modo;
      this.renderTopo();
      this.render();
      if (modo === '3d') {
        var c = this.$('ar-canvas');
        c.hidden = false;
        this.iniciar3d(c);
      }
    }

    setState(parcial) {
      var ant = Object.assign({}, this.state);
      Object.assign(this.state, parcial);
      if (parcial.modo === '2d' && ant.modo !== '2d') { this.destruir3d(); this.$('ar-canvas').hidden = true; }
      this.render();
      if (ant.sel !== this.state.sel || ant.zona !== this.state.zona) {
        this.aplicarSelecao(true);
        if (ant.sel !== this.state.sel) {
          var h = this.root.querySelector('[data-foco-titulo]');
          if (h) { try { h.focus({ preventScroll: true }); } catch (e) { h.focus(); } }
        }
      }
      if (parcial.anuncio) this.$('ar-anuncio').textContent = parcial.anuncio;
    }

    ligarEventos() {
      var self = this;
      this.root.addEventListener('click', function (e) {
        var b = e.target.closest('[data-acao]');
        if (!b || !self.root.contains(b)) return;
        var a = b.dataset.acao;
        if (a === 'voltar') self.voltar();
        else if (a === 'abrir') self.selecionar(b.dataset.gc, b.dataset.zc || null);
      });
      document.addEventListener('keydown', function (e) {
        if ((e.key === 'Escape' || e.key === 'Esc') && self.state.sel) { e.preventDefault(); self.voltar(); }
      });
    }

    galpao(c) { return (this.D ? this.D.galpoes : []).filter(function (g) { return g.codigo === c; })[0] || null; }
    idxGalpao(c) { return this.D.galpoes.map(function (g) { return g.codigo; }).indexOf(c); }

    nivelZona(n) {
      var N = {
        normal: { glifo: '✓', nome: 'Normal', bg: '#e3f2e6', fg: '#13502b', c3: 0xb6dfbf },
        atencao: { glifo: '▲', nome: 'Atenção', bg: '#fff2cc', fg: '#6b4a00', c3: 0xffd96a },
        critico: { glifo: '■', nome: 'Crítico', bg: '#fbe0de', fg: '#8a1c14', c3: 0xf08a7e },
        semleitura: { glifo: '●', nome: 'Sem leitura', bg: '#eceeea', fg: '#1b1f1a', c3: 0xcdd1ca }
      };
      return N[n] || N.normal;
    }
    estadoInfo(e) {
      var E = {
        ok: { glifo: '✓', nome: 'Tudo certo', bg: '#e3f2e6', fg: '#13502b', borda: '#13502b' },
        atencao: { glifo: '▲', nome: 'Atenção', bg: '#fff2cc', fg: '#6b4a00', borda: '#6b4a00' },
        critico: { glifo: '■', nome: 'Urgente', bg: '#fbe0de', fg: '#8a1c14', borda: '#8a1c14' },
        semleitura: { glifo: '●', nome: 'Sem leitura', bg: '#eceeea', fg: '#1b1f1a', borda: '#5d655b' },
        vazio: { glifo: '○', nome: 'Vazio sanitário', bg: '#ffffff', fg: '#1b1f1a', borda: '#5d655b' }
      };
      return E[e] || E.ok;
    }
    /* Alerta crítico confirmado só fecha por decisão humana: até lá, o galpão continua urgente. */
    confirmadoAberto(gc) {
      return ((this.D && this.D.alertas) || []).filter(function (a) {
        return a.galpao === gc && a.status === 'confirmado' && a.nivel === 'critico';
      })[0] || null;
    }
    estadoGalpao(g) {
      if (g.vazio_sanitario) return 'vazio';
      if (g.robo_atrasado) return 'semleitura';
      if (this.confirmadoAberto(g.codigo)) return 'critico';
      var pior = 'ok';
      g.zonas.forEach(function (z) {
        if (z.nivel === 'critico') pior = 'critico';
        else if (z.nivel === 'atencao' && pior !== 'critico') pior = 'atencao';
      });
      return pior;
    }
    zonaProblema(c) {
      var g = this.galpao(c);
      if (!g || g.robo_atrasado) return null;
      var crit = g.zonas.filter(function (z) { return z.nivel === 'critico'; })[0];
      var conf = this.confirmadoAberto(c);
      var at = g.zonas.filter(function (z) { return z.nivel === 'atencao'; })[0];
      return (crit || (conf && { codigo: conf.zona }) || at || {}).codigo || null;
    }
    zonaFala(codigo) {
      return { Z1: 'na entrada', Z2: 'nos comedouros do início', Z3: 'no meio do galpão', Z4: 'zona do fundo', Z5: 'perto dos exaustores', Z6: 'na saída de ar' }[codigo] || codigo;
    }
    num(n, d) { if (this.semDado(n)) return 'sem dado'; return Number(n).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }); }
    hora(iso) { var m = /T(\d\d):(\d\d)/.exec(iso); return m ? m[1] + ':' + m[2] : ''; }
    diaSemana(dataISO) {
      var p = dataISO.split('-');
      var d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2]));
      return { curto: ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'][d.getUTCDay()], longo: ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'][d.getUTCDay()], dm: p[2] + '/' + p[1] };
    }
    xZona(k) { return -50 + 20 * k; }
    xMarca(i) { return [-36, -12, 12, 36][i % 4]; }
    zGalpao(i) { return -45 + 30 * i; }


    temWebGL() {
      if (!window.THREE) return false;
      try {
        var c = document.createElement('canvas');
        return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
      } catch (e) { return false; }
    }

    /* ---------- interação ---------- */
    selecionar(gc, zc) {
      var g = this.galpao(gc);
      if (!g) return;
      var zona = zc || this.zonaProblema(gc);
      var est = this.estadoInfo(this.estadoGalpao(g));
      var txt = g.nome + ' aberto em corte. Estado: ' + est.nome + '.';
      if (zona) {
        var zz = g.zonas.filter(function (z) { return z.codigo === zona; })[0];
        if (zz) txt += ' Zona ' + zz.nome + ': ' + this.nivelZona(zz.nivel).nome + '.';
      }
      this.setState({ sel: gc, zona: zona, anuncio: txt });
    }
    voltar() {
      if (!this.state.sel) return;
      this.setState({ sel: null, zona: null, anuncio: 'De volta à visão geral da granja.' });
    }

    iniciar3d(canvas) {
      var T = window.THREE;
      if (!T) { this.setState({ modo: '2d' }); return; }
      var self = this;
      var wrap = canvas.parentNode;
      var w = wrap.clientWidth || 900, h = wrap.clientHeight || 560;
      var renderer;
      try { renderer = new T.WebGLRenderer({ canvas: canvas, antialias: true }); } catch (e) { this.setState({ modo: '2d' }); return; }
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(w, h, false);
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = T.PCFSoftShadowMap;

      var scene = new T.Scene();
      scene.background = new T.Color(0xdde7e2);
      scene.fog = new T.Fog(0xdde7e2, 520, 1100);
      var camera = new T.PerspectiveCamera(38, w / h, 1, 2000);
      camera.position.set(150, 135, 185);

      var controls = null;
      if (T.OrbitControls) {
        controls = new T.OrbitControls(camera, canvas);
        controls.enableDamping = !this.state.reduz;
        controls.dampingFactor = 0.08;
        controls.maxPolarAngle = 1.32;
        controls.minDistance = 30;
        controls.maxDistance = 460;
        controls.target.set(0, 0, 0);
        controls.update();
      } else {
        camera.lookAt(0, 0, 0);
      }

      scene.add(new T.HemisphereLight(0xf2f6ff, 0x6f7d5c, 0.62));
      var sol = new T.DirectionalLight(0xfff6e8, 0.78);
      sol.position.set(-120, 220, 140);
      sol.castShadow = true;
      sol.shadow.mapSize.set(2048, 2048);
      var sc = sol.shadow.camera;
      sc.left = -175; sc.right = 175; sc.top = 135; sc.bottom = -135; sc.near = 50; sc.far = 520;
      sol.shadow.bias = -0.0006;
      scene.add(sol);

      var mat = function (c, o) { return new T.MeshStandardMaterial(Object.assign({ color: c, roughness: 0.92, metalness: 0, flatShading: true }, o || {})); };
      var box = function (sx, sy, sz, cor, x, y, z, pai, sombra) {
        var m = new T.Mesh(new T.BoxGeometry(sx, sy, sz), typeof cor === 'number' ? mat(cor) : cor);
        m.position.set(x, y, z);
        m.castShadow = sombra !== false; m.receiveShadow = true;
        (pai || scene).add(m);
        return m;
      };

      // terreno
      var chao = new T.Mesh(new T.PlaneGeometry(1000, 1000), mat(0x9fb784));
      chao.rotation.x = -Math.PI / 2; chao.receiveShadow = true; scene.add(chao);
      var lote = new T.Mesh(new T.PlaneGeometry(284, 204), mat(0xadc193));
      lote.rotation.x = -Math.PI / 2; lote.position.y = 0.02; lote.receiveShadow = true; scene.add(lote);

      // estradas de terra
      var terra = mat(0xc2a983);
      box(8, 0.08, 230, terra, -78, 0.05, 50, null, false);
      box(420, 0.08, 9, terra, 0, 0.05, 124, null, false);
      for (var gi = 0; gi < 4; gi++) box(12, 0.08, 6, terra, -67, 0.05, this.zGalpao(gi), null, false);
      box(26, 0.08, 6, terra, -95, 0.05, 72, null, false);

      // cerca
      var madeira = mat(0x8a7458);
      var postes = [];
      var x, zz;
      for (x = -140; x <= 140; x += 10) { postes.push([x, -102]); if (x < -86 || x > -70) postes.push([x, 102]); }
      for (zz = -92; zz <= 92; zz += 10) { postes.push([-140, zz]); postes.push([140, zz]); }
      var inst = new T.InstancedMesh(new T.BoxGeometry(0.35, 1.7, 0.35), madeira, postes.length);
      var m4 = new T.Matrix4();
      postes.forEach(function (p, k) { m4.makeTranslation(p[0], 0.85, p[1]); inst.setMatrixAt(k, m4); });
      inst.castShadow = true; scene.add(inst);
      [0.7, 1.35].forEach(function (yy) {
        box(280, 0.12, 0.12, madeira, 0, yy, -102, null, false);
        box(0.12, 0.12, 204, madeira, -140, yy, 0, null, false);
        box(0.12, 0.12, 204, madeira, 140, yy, 0, null, false);
        box(54, 0.12, 0.12, madeira, -113, yy, 102, null, false);
        box(210, 0.12, 0.12, madeira, 35, yy, 102, null, false);
      });
      // portão
      box(0.6, 4.2, 0.6, madeira, -86, 2.1, 102);
      box(0.6, 4.2, 0.6, madeira, -70, 2.1, 102);
      box(17, 1.3, 0.4, mat(0x1f5f3f), -78, 4.6, 102);

      // sede
      var sede = new T.Group(); sede.position.set(-112, 0, 72); scene.add(sede);
      box(15, 4.2, 10, mat(0xf3efe6), 0, 2.1, 0, sede);
      var telhado = new T.Mesh(new T.ConeGeometry(10.6, 3.6, 4), mat(0xb4674c));
      telhado.rotation.y = Math.PI / 4; telhado.scale.set(1.08, 1, 0.76); telhado.position.y = 6.0; telhado.castShadow = true; sede.add(telhado);
      box(2, 2.8, 0.2, mat(0x6b4f3a), 3, 1.4, 5.05, sede);
      box(1.8, 1.2, 0.2, mat(0x9fb8c8), -3.5, 2.4, 5.05, sede);
      box(15, 0.3, 3.5, mat(0xd9d2c3), 0, 0.15, 6.8, sede);
      var caixa = new T.Mesh(new T.CylinderGeometry(1.6, 1.6, 2.4, 10), mat(0x5f7f93));
      caixa.position.set(12, 6.4, -2); caixa.castShadow = true; sede.add(caixa);
      box(0.3, 5.2, 0.3, mat(0x8a8f88), 11, 2.6, -1, sede); box(0.3, 5.2, 0.3, mat(0x8a8f88), 13, 2.6, -3, sede);

      // árvores (posições fixas, semente determinística)
      var semente = 7;
      var rnd = function () { semente = (semente * 16807) % 2147483647; return (semente - 1) / 2147483646; };
      var copas = [mat(0x6f9a62), mat(0x7ea86d), mat(0x5f8a58)];
      var tronco = mat(0x7a5c3e);
      var arvores = 0, tent = 0;
      while (arvores < 46 && tent < 800) {
        tent++;
        var ax = -190 + rnd() * 380, az = -150 + rnd() * 300;
        var dentroGalpoes = ax > -76 && ax < 74 && az > -62 && az < 62;
        var naEstrada = (Math.abs(ax + 78) < 9) || (Math.abs(az - 124) < 9) || (ax > -128 && ax < -92 && az > 58 && az < 86);
        var naCerca = Math.abs(Math.abs(ax) - 140) < 4 || Math.abs(Math.abs(az) - 102) < 4;
        if (dentroGalpoes || naEstrada || naCerca) continue;
        var r = 2.4 + rnd() * 1.6;
        var t = new T.Mesh(new T.CylinderGeometry(0.35, 0.5, 3, 6), tronco);
        t.position.set(ax, 1.5, az); t.castShadow = true; scene.add(t);
        var c = new T.Mesh(new T.IcosahedronGeometry(r, 0), copas[arvores % 3]);
        c.position.set(ax, 3 + r * 0.8, az); c.castShadow = true; scene.add(c);
        arvores++;
      }

      // galpões
      var dados = this.dados();
      var corteMat = function (c) { return mat(c, { transparent: true, opacity: 1 }); };
      var forma = new T.Shape();
      forma.moveTo(-6.8, 0); forma.lineTo(6.8, 0); forma.lineTo(0, 2.3); forma.lineTo(-6.8, 0);
      var telhaGeo = new T.ExtrudeGeometry(forma, { depth: 121.5, bevelEnabled: false });
      var linhaPts = [new T.Vector3(-57, 0.5, 0), new T.Vector3(57, 0.5, 0)];
      var gal = [];
      var hits = [];
      dados.galpoes.forEach(function (g, i) {
        var gz = self.zGalpao(i);
        var grp = new T.Group(); grp.position.set(0, 0, gz); scene.add(grp);
        box(120, 0.3, 12, 0xb9a27a, 0, 0.15, 0, grp, false);
        box(120, 0.7, 0.3, 0xd8d6cf, 0, 0.35, 6.0, grp);
        box(120, 0.7, 0.3, 0xd8d6cf, 0, 0.35, -6.0, grp);
        var cortFrente = box(120, 2.4, 0.12, corteMat(0x9db5c2), 0, 1.9, 6.05, grp);
        box(120, 2.4, 0.12, mat(0x9db5c2), 0, 1.9, -6.05, grp);
        // ponta da placa evaporativa (entrada) e ponta dos exaustores (saída)
        box(0.3, 3.2, 12, 0xd8d6cf, -60, 1.6, 0, grp);
        box(0.5, 2.6, 11.2, 0x6f957b, -60.4, 1.6, 0, grp);
        box(0.3, 3.2, 12, 0xd8d6cf, 60, 1.6, 0, grp);
        [-4, -1.35, 1.35, 4].forEach(function (fz) {
          var f = new T.Mesh(new T.CylinderGeometry(1.05, 1.05, 0.45, 14), mat(0x3a423c));
          f.rotation.z = Math.PI / 2; f.position.set(60.35, 1.65, fz); grp.add(f);
          var hub = new T.Mesh(new T.CylinderGeometry(0.25, 0.25, 0.5, 8), mat(0xb8bcb5));
          hub.rotation.z = Math.PI / 2; hub.position.set(60.4, 1.65, fz); grp.add(hub);
        });
        var telha = new T.Mesh(telhaGeo, mat(0xf1f0ea, { transparent: true, opacity: 1 }));
        telha.rotation.y = Math.PI / 2; telha.position.set(-60.75, 3.1, 0); telha.castShadow = true; telha.receiveShadow = true; grp.add(telha);
        // silo
        var silo = new T.Group(); silo.position.set(-50, 0, 9.4); grp.add(silo);
        var sCorpo = new T.Mesh(new T.CylinderGeometry(1.8, 1.8, 5.2, 12), mat(0xc5c9c3, { metalness: 0.15, roughness: 0.6 }));
        sCorpo.position.y = 4.6; sCorpo.castShadow = true; silo.add(sCorpo);
        var sTopo = new T.Mesh(new T.ConeGeometry(1.8, 1.4, 12), mat(0xb3b8b1)); sTopo.position.y = 7.9; sTopo.castShadow = true; silo.add(sTopo);
        var sBase = new T.Mesh(new T.ConeGeometry(1.8, 1.4, 12), mat(0xb3b8b1)); sBase.rotation.x = Math.PI; sBase.position.y = 1.3; silo.add(sBase);
        [[-1.2, -1.2], [1.2, -1.2], [-1.2, 1.2], [1.2, 1.2]].forEach(function (p) { box(0.2, 2, 0.2, 0x8a8f88, p[0], 1, p[1], silo); });
        var tubo = new T.Mesh(new T.CylinderGeometry(0.18, 0.18, 4.6, 6), mat(0x9aa098));
        tubo.rotation.x = Math.PI / 2.6; tubo.position.set(0, 5.2, -2.2); silo.add(tubo);
        // zonas
        var zonas = g.zonas.map(function (zo, k) {
          var nz = g.robo_atrasado ? self.nivelZona('semleitura') : self.nivelZona(zo.nivel);
          var p = new T.Mesh(new T.PlaneGeometry(19.0, 10.8), new T.MeshBasicMaterial({ color: nz.c3, transparent: true, opacity: 0.95 }));
          p.rotation.x = -Math.PI / 2; p.position.set(self.xZona(k), 0.34, 0); p.visible = false;
          p.userData = { gc: g.codigo, zc: zo.codigo };
          grp.add(p);
          return p;
        });
        // pulso de urgência
        var urg = new T.Mesh(new T.PlaneGeometry(130, 22), new T.MeshBasicMaterial({ color: 0xd2453a, transparent: true, opacity: 0.22, depthWrite: false }));
        urg.rotation.x = -Math.PI / 2; urg.position.y = 0.06; urg.visible = self.estadoGalpao(g) === 'critico'; grp.add(urg);
        // carrinho
        var parado = g.robo_atrasado;
        var robo = new T.Group(); robo.scale.setScalar(1.7); grp.add(robo);
        box(1.6, 0.8, 1.1, parado ? 0x8b928a : 0x1f5f3f, 0, 0.75, 0, robo);
        [[-0.55, 0.6], [0.55, 0.6], [-0.55, -0.6], [0.55, -0.6]].forEach(function (p) {
          var rd = new T.Mesh(new T.CylinderGeometry(0.32, 0.32, 0.18, 10), mat(0x232823));
          rd.rotation.x = Math.PI / 2; rd.position.set(p[0], 0.34, p[1]); robo.add(rd);
        });
        var mastro = new T.Mesh(new T.CylinderGeometry(0.06, 0.06, 1.4, 6), mat(0x555b54)); mastro.position.set(0.3, 1.85, 0); robo.add(mastro);
        box(0.55, 0.32, 0.36, 0xf6f6f1, 0.3, 2.62, 0, robo);
        var led = new T.Mesh(new T.SphereGeometry(0.12, 8, 6), new T.MeshBasicMaterial({ color: parado ? 0x9aa198 : 0x6fe3a0 }));
        led.position.set(-0.6, 1.25, 0); robo.add(led);
        // farol acima do telhado, mostra o carrinho na visão geral
        var farol = new T.Group(); farol.position.y = 7.4; grp.add(farol);
        var fc = new T.Mesh(new T.ConeGeometry(0.9, 1.8, 10), new T.MeshBasicMaterial({ color: parado ? 0x8b928a : 0x1f5f3f }));
        fc.rotation.x = Math.PI; farol.add(fc);
        // trajeto tracejado
        var lg = new T.BufferGeometry().setFromPoints(linhaPts);
        var linha = new T.Line(lg, new T.LineDashedMaterial({ color: 0x1f5f3f, dashSize: 1.8, gapSize: 1.2 }));
        linha.computeLineDistances(); linha.visible = false; grp.add(linha);
        // área clicável
        var hit = new T.Mesh(new T.BoxGeometry(124, 8, 14), new T.MeshBasicMaterial({ visible: false }));
        hit.position.y = 4; hit.userData = { gc: g.codigo }; grp.add(hit); hits.push(hit);
        var k0 = [1, 3, 0, 5][i];
        var xs = parado ? self.xZona(5) : self.xZona(k0);
        robo.position.x = xs; farol.position.x = xs;
        gal.push({ g: g, gz: gz, telha: telha, cort: cortFrente, zonas: zonas, urg: urg, robo: robo, farol: farol, linha: linha,
          r: { k: k0, dir: i % 2 ? -1 : 1, espera: 0.6 * i, x: xs, parado: parado } });
      });

      var ray = new T.Raycaster();
      var ndc = new T.Vector2();
      var pd = null;
      var acerto = function (ev) {
        var rc = canvas.getBoundingClientRect();
        ndc.set(((ev.clientX - rc.left) / rc.width) * 2 - 1, -((ev.clientY - rc.top) / rc.height) * 2 + 1);
        ray.setFromCamera(ndc, camera);
        var sel = self.state.sel;
        if (sel) {
          var gs = gal.filter(function (o) { return o.g.codigo === sel; })[0];
          if (gs) {
            var hz = ray.intersectObjects(gs.zonas, false);
            if (hz.length) return hz[0].object.userData;
          }
        }
        var hh = ray.intersectObjects(hits, false);
        return hh.length ? hh[0].object.userData : null;
      };
      var onDown = function (ev) { pd = { x: ev.clientX, y: ev.clientY }; };
      var onUp = function (ev) {
        if (!pd) return;
        var dx = ev.clientX - pd.x, dy = ev.clientY - pd.y; pd = null;
        if (dx * dx + dy * dy > 36) return;
        var a = acerto(ev);
        if (a) self.selecionar(a.gc, a.zc || null);
      };
      var ultimoMov = 0;
      var onMove = function (ev) {
        var agora = performance.now();
        if (agora - ultimoMov < 80 || pd) return;
        ultimoMov = agora;
        canvas.style.cursor = acerto(ev) ? 'pointer' : 'grab';
      };
      canvas.addEventListener('pointerdown', onDown);
      canvas.addEventListener('pointerup', onUp);
      canvas.addEventListener('pointermove', onMove);

      var ro = null;
      var redimensiona = function () {
        var cw = wrap.clientWidth, ch = wrap.clientHeight;
        if (!cw || !ch) return;
        self.t3.w = cw; self.t3.h = ch;
        renderer.setSize(cw, ch, false);
        camera.aspect = cw / ch; camera.updateProjectionMatrix();
      };
      if (window.ResizeObserver) { ro = new ResizeObserver(redimensiona); ro.observe(wrap); }

      var relogio = new T.Clock();
      var tempo = 0;
      this.t3 = { T: T, renderer: renderer, scene: scene, camera: camera, controls: controls, gal: gal, w: w, h: h, tw: null, ro: ro,
        canvas: canvas, ouvintes: [['pointerdown', onDown], ['pointerup', onUp], ['pointermove', onMove]], raf: 0 };
      var laco = function () {
        self.t3.raf = requestAnimationFrame(laco);
        var dt = Math.min(relogio.getDelta(), 0.1);
        tempo += dt;
        self.passo(dt, tempo);
        if (controls) controls.update();
        renderer.render(scene, camera);
        self.projetar();
      };
      this.aplicarSelecao(false);
      laco();
    }

    destruir3d() {
      var t = this.t3;
      if (!t) return;
      cancelAnimationFrame(t.raf);
      if (t.ro) t.ro.disconnect();
      t.ouvintes.forEach(function (o) { t.canvas.removeEventListener(o[0], o[1]); });
      if (t.controls) t.controls.dispose();
      t.scene.traverse(function (o) {
        if (o.geometry) o.geometry.dispose();
        if (o.material) { (Array.isArray(o.material) ? o.material : [o.material]).forEach(function (m) { m.dispose(); }); }
      });
      t.renderer.dispose();
      this.t3 = null;
    }

    alvoRobo(o) {
      if (o.r.parado) return 5;
      if (this.state.sel === o.g.codigo && this.state.zona) {
        var k = +String(this.state.zona).replace('Z', '') - 1;
        if (k >= 0 && k < 6) return k;
      }
      return null;
    }

    passo(dt, tempo) {
      var t = this.t3, self = this;
      var reduz = this.state.reduz;
      t.gal.forEach(function (o) {
        var r = o.r;
        var fixo = self.alvoRobo(o);
        var alvoK = fixo !== null ? fixo : r.k;
        var alvoX = self.xZona(alvoK);
        if (reduz) {
          r.x = alvoX;
        } else if (r.espera > 0 && fixo === null) {
          r.espera -= dt;
        } else {
          var vel = 7 * dt;
          var d = alvoX - r.x;
          if (Math.abs(d) <= vel) {
            r.x = alvoX;
            if (fixo === null) {
              r.espera = 2.6;
              r.k += r.dir;
              if (r.k > 5) { r.k = 4; r.dir = -1; }
              if (r.k < 0) { r.k = 1; r.dir = 1; }
            }
          } else {
            r.x += d > 0 ? vel : -vel;
            o.robo.rotation.y = d > 0 ? 0 : Math.PI;
          }
        }
        o.robo.position.x = r.x;
        o.farol.position.x = r.x;
        o.farol.position.y = reduz ? 7.4 : 7.4 + Math.sin(tempo * 2.2 + o.gz) * 0.35;
        if (o.urg.visible) o.urg.material.opacity = reduz ? 0.22 : 0.12 + 0.16 * (0.5 + 0.5 * Math.sin(tempo * 2.4));
      });
      if (t.tw) {
        var w = t.tw;
        w.t = Math.min(1, w.t + dt / w.dur);
        var e = w.t < 0.5 ? 4 * w.t * w.t * w.t : 1 - Math.pow(-2 * w.t + 2, 3) / 2;
        t.camera.position.lerpVectors(w.p0, w.p1, e);
        if (t.controls) t.controls.target.lerpVectors(w.a0, w.a1, e); else t.camera.lookAt(w.a1);
        if (w.t >= 1) t.tw = null;
      }
    }

    aplicarSelecao(animar) {
      var t = this.t3;
      if (!t) return;
      var sel = this.state.sel, zona = this.state.zona;
      t.gal.forEach(function (o) {
        var e = o.g.codigo === sel;
        o.telha.material.opacity = e ? 0.1 : 1;
        o.telha.material.depthWrite = !e;
        o.telha.castShadow = !e;
        o.cort.material.opacity = e ? 0.15 : 1;
        o.cort.material.depthWrite = !e;
        o.zonas.forEach(function (p) { p.visible = e; });
        o.linha.visible = e;
        o.farol.visible = !e;
      });
      this.focar(sel, zona, animar && !this.state.reduz);
    }

    focar(gc, zc, animar) {
      var t = this.t3;
      if (!t) return;
      var T = t.T;
      var asp = (t.w || 900) / (t.h || 560);
      var fator = Math.max(1, 1.55 / asp);
      var alvo, pos;
      if (!gc) {
        alvo = new T.Vector3(0, 0, 0);
        pos = asp < 1.1
          ? new T.Vector3(175, 150, 55).multiplyScalar(Math.max(1, 0.95 / asp))
          : new T.Vector3(150, 135, 185).multiplyScalar(fator);
      } else {
        var i = this.idxGalpao(gc);
        var gz = this.zGalpao(i);
        var perto = 1;
        var zx = 0;
        if (zc && zc !== this.zonaProblema(gc)) { perto = 0.62; zx = this.xZona(+zc.replace('Z', '') - 1); }
        if (asp < 1.1) {
          var cx = zc && perto < 1 ? zx : 8;
          alvo = new T.Vector3(cx, 0, gz);
          pos = new T.Vector3(cx - 92 * perto, 66 * perto, gz + 26 * perto);
        } else {
          alvo = new T.Vector3(zx, 0, gz);
          pos = new T.Vector3(zx - 6 * perto, 84 * perto * fator, gz + 96 * perto * fator);
        }
      }
      if (!animar) {
        t.tw = null;
        t.camera.position.copy(pos);
        if (t.controls) { t.controls.target.copy(alvo); t.controls.update(); } else t.camera.lookAt(alvo);
        return;
      }
      t.tw = { p0: t.camera.position.clone(), p1: pos, a0: t.controls ? t.controls.target.clone() : alvo.clone(), a1: alvo, t: 0, dur: 0.95 };
    }


    atualizarCores3d() {
      var t = this.t3, self = this;
      if (!t) return;
      t.gal.forEach(function (o) {
        var g = self.galpao(o.g.codigo);
        if (!g) return;
        o.g = g;
        o.r.parado = !!g.robo_atrasado;
        o.zonas.forEach(function (p, k) {
          var z = g.zonas[k];
          if (!z) return;
          p.material.color.setHex((g.robo_atrasado ? self.nivelZona('semleitura') : self.nivelZona(z.nivel)).c3);
        });
        o.urg.visible = self.estadoGalpao(g) === 'critico';
      });
    }

    /* posições dos marcadores e rótulos sobre a cena: CSSOM, sem re-renderizar */
    projetar() {
      var t = this.t3, self = this;
      if (!t) return;
      var T = t.T, v = new T.Vector3();
      var w = t.w, h = t.h;
      var pr = function (x, y, z) {
        v.set(x, y, z); v.project(t.camera);
        var vis = v.z > -1 && v.z < 1 && v.x > -1.1 && v.x < 1.1 && v.y > -1.15 && v.y < 1.15;
        return { x: Math.round((v.x + 1) / 2 * w), y: Math.round((1 - v.y) / 2 * h), vis: vis };
      };
      var poe = function (el, p, esconder) {
        if (!el) return;
        if (!p.vis || esconder) { el.hidden = true; return; }
        el.hidden = false;
        el.style.left = p.x + 'px';
        el.style.top = p.y + 'px';
      };
      var marcas = this.$('ar-marcas');
      t.gal.forEach(function (o, i) {
        var el = marcas.querySelector('[data-gc="' + o.g.codigo + '"]');
        poe(el, pr(self.xMarca(i), 10, o.gz), self.state.sel === o.g.codigo);
      });
      if (this.state.sel) {
        var o = t.gal.filter(function (q) { return q.g.codigo === self.state.sel; })[0];
        var zonas = this.$('ar-zonas');
        if (o) o.g.zonas.forEach(function (zo, k) {
          poe(zonas.querySelector('[data-zc="' + zo.codigo + '"]'), pr(self.xZona(k), 0.4, o.gz + 2.2), false);
        });
      }
    }

    /* ---------- modelo de exibição (mesma lógica do protótipo) ---------- */
    vm() {
      var self = this, D = this.D, st = this.state, sel = st.sel;
      var galpoes = D.galpoes.map(function (g, i) {
        var ek = self.estadoGalpao(g), e = self.estadoInfo(ek);
        return {
          codigo: g.codigo, nome: g.nome, ek: ek, glifo: e.glifo, estado: e.nome, i: i,
          lote: g.lote_codigo, idade: g.idade_lote_dias + (g.idade_lote_dias === 1 ? ' dia' : ' dias'),
          ultima: self.semDado(g.minutos_sem_leitura) ? 'Nenhuma leitura ainda' : (g.robo_atrasado ? 'Sem leitura há ' : 'Leitura há ') + g.minutos_sem_leitura + ' min',
          aria: g.nome + ': ' + e.nome + '. Lote ' + g.lote_codigo + ', ' + g.idade_lote_dias + ' dias. ' + (sel === g.codigo ? 'Aberto.' : 'Enter para aproximar.')
        };
      });
      var ordem = { critico: 0, atencao: 1, semleitura: 2 };
      var itens = (D.alertas || []).map(function (a) {
        var g = self.galpao(a.galpao) || { nome: a.galpao };
        var nz = self.nivelZona(a.nivel);
        var calor = /ITU|temperatura/i.test(a.motivo || '');
        var co2 = /CO2/i.test(a.motivo || '');
        var oque = calor ? 'calor' : (co2 ? 'CO2' : 'leitura fora da faixa');
        var titulo = g.nome + ', ' + self.zonaFala(a.zona) + ': ' + (a.status === 'confirmado' ? oque + ' confirmado.' : (co2 ? 'CO2 subindo.' : oque + ' em observação.'));
        return { ordem: ordem[a.nivel] ?? 3, gc: a.galpao, zc: a.zona, nk: a.nivel, glifo: nz.glifo, nivel: a.nivel === 'critico' ? 'Urgente' : nz.nome,
          titulo: titulo, acao: a.acao_recomendada, confirmado: a.status === 'confirmado',
          tag: a.status === 'confirmado' ? 'Confirmado' : 'Aguardando nova medição', quando: 'Atualizado às ' + self.hora(a.atualizado_em) };
      });
      D.galpoes.forEach(function (g) {
        if (!g.robo_atrasado) return;
        var nunca = self.semDado(g.minutos_sem_leitura);
        itens.push({ ordem: 2, gc: g.codigo, zc: null, nk: 'semleitura', glifo: '●', nivel: 'Sem leitura',
          titulo: g.nome + (nunca ? ': o carrinho ainda não enviou leitura deste lote.' : ': o carrinho não envia leitura há ' + g.minutos_sem_leitura + ' minutos.'), acao: 'Verifique bateria e Wi-Fi.',
          confirmado: false, tag: 'Sem sinal do carrinho', quando: nunca ? 'Nenhuma leitura recebida' : 'Última leitura há ' + g.minutos_sem_leitura + ' min' });
      });
      itens.sort(function (a, b) { return a.ordem - b.ordem; });

      var det = null;
      if (sel) {
        var g = this.galpao(sel), ek = this.estadoGalpao(g), e = this.estadoInfo(ek), fx = g.faixa_conforto_c;
        var zp = this.zonaProblema(sel);
        var alertasG = (D.alertas || []).filter(function (a) { return a.galpao === sel; }).map(function (a) {
          var nz = self.nivelZona(a.nivel);
          var zz = g.zonas.filter(function (z) { return z.codigo === a.zona; })[0];
          return { nk: a.nivel, glifo: nz.glifo, nivel: a.nivel === 'critico' ? 'Urgente' : nz.nome,
            titulo: 'Zona ' + a.zona + (zz ? ', ' + zz.nome : ''), motivo: a.motivo, acao: a.acao_recomendada,
            confirmado: a.status === 'confirmado', tag: a.status === 'confirmado' ? 'Confirmado' : 'Aguardando nova medição',
            explica: a.status !== 'confirmado' ? 'O carrinho vai medir esta zona de novo antes de confirmar.'
              : (zz && zz.nivel === a.nivel ? 'O carrinho mediu esta zona de novo e o problema continua.'
                : 'A última medição desta zona já melhorou, mas o alerta fica aberto até alguém da granja dar baixa.'),
            quando: 'Atualizado às ' + self.hora(a.atualizado_em) };
        });
        var alertaZ = (D.alertas || []).filter(function (a) { return a.galpao === sel && a.zona === zp; })[0];
        var carrinho;
        var nuncaLeu = this.semDado(g.minutos_sem_leitura);
        if (g.robo_atrasado) carrinho = nuncaLeu ? 'Ainda não enviou leitura deste lote.' : 'Parado, sem enviar leitura há ' + g.minutos_sem_leitura + ' min.';
        else if (st.zona && st.zona !== zp) carrinho = 'A caminho da zona ' + st.zona + ' para medir.';
        else if (zp && alertaZ && alertaZ.status === 'suspeita') carrinho = 'Voltando à zona ' + zp + ' para medir de novo.';
        else if (zp) carrinho = 'Parado na zona ' + zp + ', medindo.';
        else carrinho = 'Em ronda, de zona em zona.';
        var zonas = g.zonas.map(function (z, k) {
          var nz = self.nivelZona(z.nivel), nk = z.nivel, nome = nz.nome;
          var ultimoNivel = nz.nome.toLowerCase();
          if (g.robo_atrasado) { nk = 'semleitura'; nz = self.nivelZona('semleitura'); nome = nz.nome; }
          var nota = z.temperatura_c > fx[1] ? 'acima do ideal' : (z.temperatura_c < fx[0] ? 'abaixo do ideal' : 'na faixa');
          if (g.robo_atrasado) nota = ultimoNivel + ' há ' + g.minutos_sem_leitura + ' min';
          if (self.semDado(z.temperatura_c)) nota = 'sem leitura';
          return { codigo: z.codigo, nome: z.nome, nk: nk, glifo: nz.glifo, nivel: nome, foco: st.zona === z.codigo,
            temp: self.semDado(z.temperatura_c) ? 'sem dado' : self.num(z.temperatura_c, 1) + ' °C', nota: nota,
            umid: self.semDado(z.umidade_pct) ? 'sem dado' : self.num(z.umidade_pct, 0) + '%', co2: self.num(z.co2_ppm, 0), itu: self.num(z.itu, 1),
            aria: 'Zona ' + z.codigo + ', ' + z.nome + ': ' + nome + '. Temperatura ' + self.num(z.temperatura_c, 1) + ' graus, ' + nota + '. Umidade ' + self.num(z.umidade_pct, 0) + ' por cento. CO2 ' + self.num(z.co2_ppm, 0) + ' ppm. ITU ' + self.num(z.itu, 1) + '. Mostrar no mapa.',
            temRobo: g.robo_atrasado ? k === 5 : (st.zona ? st.zona === z.codigo : (zp ? zp === z.codigo : k === 2)) };
        });
        det = { codigo: g.codigo, nome: g.nome, ek: ek, glifo: e.glifo, estado: e.nome, lote: g.lote_codigo, idade: g.idade_lote_dias + ' dias',
          faixa: fx[0] + ' a ' + fx[1] + ' °C', ultima: nuncaLeu ? 'nenhuma ainda' : 'há ' + g.minutos_sem_leitura + ' min', carrinho: carrinho,
          alertas: alertasG, semLeitura: !!g.robo_atrasado, minutos: g.minutos_sem_leitura, tudoCerto: ek === 'ok', zonas: zonas };
      }
      return { galpoes: galpoes, itens: itens, det: det };
    }

    /* ---------- render ---------- */
    renderTopo() {
      var self = this, D = this.D;
      this.$('ar-granja-nome').textContent = D.granja + ', ' + D.municipio;
      if (D.atualizado_em) {
        var dU = this.diaSemana(D.atualizado_em.slice(0, 10));
        this.$('ar-ultima').textContent = dU.curto + ', ' + dU.dm + ', ' + this.hora(D.atualizado_em);
      } else {
        this.$('ar-ultima').textContent = 'nenhuma ainda';
      }
      this.$('ar-previsao').innerHTML = (D.previsao_max_c || []).map(function (p) {
        var d = self.diaSemana(p.data), q = p.max > 32;
        var sr = d.longo + ', ' + d.dm + ': máxima de ' + p.max + ' graus' + (q ? ', acima de 32, dia de calor' : '');
        return '<li><div class="ar-dia' + (q ? ' ar-dia--quente' : '') + '"><span class="ar-sr">' + esc(sr) + '</span>' +
          '<span class="ar-dia__nome" aria-hidden="true">' + esc(d.curto + ' ' + d.dm) + '</span>' +
          '<span class="ar-dia__max" aria-hidden="true">' + (q ? '▲ ' : '') + esc(p.max + ' °C') + '</span></div></li>';
      }).join('');
      var cont = { critico: 0, atencao: 0, semleitura: 0, ok: 0, vazio: 0 };
      D.galpoes.forEach(function (g) { cont[self.estadoGalpao(g)]++; });
      var partes = [];
      if (cont.critico) partes.push(['critico', cont.critico + ' urgente' + (cont.critico > 1 ? 's' : '')]);
      if (cont.atencao) partes.push(['atencao', cont.atencao + ' atenção']);
      if (cont.semleitura) partes.push(['semleitura', cont.semleitura + ' sem leitura']);
      if (cont.vazio) partes.push(['vazio', cont.vazio + ' em vazio sanitário']);
      var txt = D.galpoes.length + ' galpões · ' + partes.map(function (p) { return p[1]; }).join(' · ');
      this.$('ar-resumo').innerHTML = '<span class="ar-sr">' + esc(txt) + '</span><span class="ar-resumo__total" aria-hidden="true">' + D.galpoes.length + ' galpões</span>' +
        partes.map(function (p) { var e = self.estadoInfo(p[0]); return '<span class="ar-pill nv-' + p[0] + '" aria-hidden="true">' + e.glifo + ' ' + esc(p[1]) + '</span>'; }).join('');
    }

    render() {
      if (!this.D) return;
      var self = this, st = this.state, vm = this.vm(), det = vm.det, sel = st.sel;
      this.renderTopo();
      this.$('ar-carregando').hidden = true;
      var cena = this.$('ar-cena');
      cena.classList.toggle('ar-cena--2d', st.modo === '2d');
      this.$('ar-overlay').hidden = st.modo !== '3d';
      this.$('ar-voltar-cena').hidden = !sel;
      this.$('ar-cena-titulo').textContent = sel ? det.nome + ' em corte' : 'Visão geral da granja';
      this.$('ar-legenda-geral').hidden = !!sel;
      this.$('ar-legenda-zonas').hidden = !sel;
      this.$('ar-dica').textContent = st.modo === '3d'
        ? 'Arraste para girar. Role ou use dois dedos para aproximar.' + (st.reduz ? '' : ' Toque num galpão para abrir.')
        : 'Mapa plano: seu aparelho não mostra a cena 3D. As informações são as mesmas.';

      var marcador = function (g, extra) {
        return '<button type="button" class="ar-btn ar-marca-btn ar-marcador nv-' + g.ek + (g.ek === 'critico' ? ' ar-pulso' : '') + (extra || '') + '"' +
          ' data-acao="abrir" data-gc="' + esc(g.codigo) + '" aria-label="' + esc(g.aria) + '">' +
          '<span aria-hidden="true">' + g.glifo + '</span><span>' + esc(g.nome + ': ' + g.estado) + '</span></button>';
      };

      if (st.modo === '3d') {
        this.$('ar-marcas').innerHTML = vm.galpoes.map(function (g) { return marcador(g, sel && sel !== g.codigo ? ' ar-marcador--apagado' : ''); }).join('');
        this.$('ar-zonas').innerHTML = det ? det.zonas.map(function (z) {
          return '<button type="button" class="ar-btn ar-marca-btn ar-rotulo-zona nv-' + z.nk + '" data-acao="abrir" data-gc="' + esc(det.codigo) + '" data-zc="' + esc(z.codigo) + '" aria-label="' + esc(z.aria) + '" hidden>' +
            '<span class="ar-rotulo-zona__cod">' + esc(z.codigo) + '</span><span><span aria-hidden="true">' + z.glifo + '</span> ' + esc(z.nivel) + '</span></button>';
        }).join('') : '';
        this.projetar();
      }

      var m2 = this.$('ar-mapa2d');
      m2.hidden = st.modo !== '2d';
      if (st.modo === '2d') m2.innerHTML = det ? this.htmlPlanta(det) : this.htmlMapa2d(vm.galpoes, marcador);
      if (st.modo === '2d' && !det) this.posicionar2d(m2);

      this.$('ar-painel').innerHTML = det ? this.htmlDetalhe(det) : this.htmlGeral(vm);
    }

    htmlGeral(vm) {
      var itens = vm.itens.map(function (it) {
        var aria = it.nivel + '. ' + it.titulo + ' ' + it.acao + ' ' + it.tag + '. Abrir no mapa.';
        return '<li><button type="button" class="ar-btn ar-item nv-' + it.nk + '" data-acao="abrir" data-gc="' + esc(it.gc) + '"' + (it.zc ? ' data-zc="' + esc(it.zc) + '"' : '') + ' aria-label="' + esc(aria) + '">' +
          '<span class="ar-item__topo"><span class="ar-item__nivel"><span aria-hidden="true">' + it.glifo + '</span> ' + esc(it.nivel) + '</span>' +
          '<span class="ar-tag' + (it.confirmado ? ' ar-tag--confirmado' : '') + '">' + esc(it.tag) + '</span></span>' +
          '<span class="ar-item__titulo">' + esc(it.titulo) + '</span><span class="ar-item__acao">' + esc(it.acao) + '</span>' +
          '<span class="ar-item__quando">' + esc(it.quando) + '</span></button></li>';
      }).join('');
      var gs = vm.galpoes.map(function (g) {
        return '<li><button type="button" class="ar-btn ar-galpao-btn" data-acao="abrir" data-gc="' + esc(g.codigo) + '" aria-label="' + esc(g.aria) + '">' +
          '<span class="ar-galpao-btn__nome">' + esc(g.nome) + '</span>' +
          '<span class="ar-pill nv-' + g.ek + '"><span aria-hidden="true">' + g.glifo + '</span> ' + esc(g.estado) + '</span>' +
          '<span class="ar-galpao-btn__meta">' + esc(g.lote + ' · ' + g.idade) + '</span><span class="ar-galpao-btn__leitura">' + esc(g.ultima) + '</span></button></li>';
      }).join('');
      return '<section class="ar-card" aria-labelledby="ar-precisa"><div><h2 id="ar-precisa" tabindex="-1" data-foco-titulo>Precisa de você</h2>' +
        '<p class="ar-card__sub">Do mais grave para o menos grave. Toque num item para ver no mapa.</p></div>' +
        '<ol class="ar-lista">' + (itens || '<li class="ar-ok nv-ok"><span aria-hidden="true">✓</span> Nada precisa de você agora.</li>') + '</ol>' +
        '<div class="ar-regra">' + ICONE_INFO + '<p><strong>O sistema recomenda, quem decide é o produtor.</strong> Um alerta fica como "aguardando nova medição" até o carrinho medir a mesma zona de novo. Só então vira "confirmado".</p></div></section>' +
        '<section class="ar-card" aria-labelledby="ar-galpoes"><h2 id="ar-galpoes" class="ar-card__h2-menor">Galpões</h2><ul class="ar-galpoes">' + gs + '</ul></section>';
    }

    htmlDetalhe(d) {
      var alertas = d.alertas.map(function (a) {
        return '<div class="ar-alerta nv-' + a.nk + '"><span class="ar-item__topo"><span class="ar-item__nivel"><span aria-hidden="true">' + a.glifo + '</span> ' + esc(a.nivel) + '</span>' +
          '<span class="ar-tag' + (a.confirmado ? ' ar-tag--confirmado' : '') + '">' + esc(a.tag) + '</span></span>' +
          '<span class="ar-alerta__titulo">' + esc(a.titulo) + '</span>' +
          '<span class="ar-alerta__acao"><strong>O que fazer:</strong> ' + esc(a.acao) + '</span>' +
          '<span class="ar-alerta__porque"><strong>Por que:</strong> ' + esc(a.motivo) + '</span>' +
          '<span class="ar-alerta__nota">' + esc(a.explica + ' ' + a.quando + '.') + '</span></div>';
      }).join('');
      var linhas = d.zonas.map(function (z) {
        return '<tr' + (z.foco ? ' class="ar-foco"' : '') + '><td><button type="button" class="ar-btn ar-zona-btn" data-acao="abrir" data-gc="' + esc(d.codigo) + '" data-zc="' + esc(z.codigo) + '" aria-label="' + esc(z.aria) + '">' +
          '<span class="cod">' + esc(z.codigo) + '</span><span class="nome">' + esc(z.nome) + '</span></button></td>' +
          '<td><span class="ar-pill nv-' + z.nk + '"><span aria-hidden="true">' + z.glifo + '</span> ' + esc(z.nivel) + '</span></td>' +
          '<td><span class="num">' + esc(z.temp) + '</span><span class="nota">' + esc(z.nota) + '</span></td>' +
          '<td class="num">' + esc(z.umid) + '</td><td class="num">' + esc(z.co2) + '</td><td class="num">' + esc(z.itu) + '</td></tr>';
      }).join('');
      return '<section class="ar-card" aria-labelledby="ar-detalhe">' +
        '<div class="ar-det__cab"><h2 id="ar-detalhe" class="ar-det__nome" tabindex="-1" data-foco-titulo>' + esc(d.nome) + '</h2>' +
        '<span class="ar-pill ar-det__estado nv-' + d.ek + '"><span aria-hidden="true">' + d.glifo + '</span> ' + esc(d.estado) + '</span></div>' +
        '<dl class="ar-dados"><div><dt>Lote</dt><dd>' + esc(d.lote) + '</dd></div><div><dt>Idade das aves</dt><dd>' + esc(d.idade) + '</dd></div>' +
        '<div><dt>Temperatura ideal para a idade</dt><dd>' + esc(d.faixa) + '</dd></div><div><dt>Última leitura</dt><dd>' + esc(d.ultima) + '</dd></div></dl>' +
        '<p class="ar-carrinho"><span><strong>Carrinho:</strong> ' + esc(d.carrinho) + '</span></p>' +
        (d.semLeitura ? '<div class="ar-alerta nv-semleitura"><span class="ar-item__nivel"><span aria-hidden="true">●</span> Sem leitura</span>' +
          '<span class="ar-alerta__acao">' + (d.minutos === null || d.minutos === undefined ? 'O carrinho ainda não enviou leitura deste lote.' : 'O carrinho não envia leitura há ' + esc(d.minutos) + ' minutos.') + ' Verifique bateria e Wi-Fi.</span>' +
          '<span class="ar-alerta__nota">Os valores abaixo são da última leitura recebida.</span></div>' : '') +
        alertas +
        (d.tudoCerto ? '<div class="ar-ok nv-ok"><span aria-hidden="true">✓</span> Todas as zonas dentro da faixa. Nada a fazer agora.</div>' : '') +
        '<div><h3>Zonas da ronda</h3><div class="ar-tabela-box"><table class="ar-tabela"><caption class="ar-sr">Leituras por zona do ' + esc(d.nome) + '</caption>' +
        '<thead><tr><th scope="col">Zona</th><th scope="col">Nível</th><th scope="col">Temp.</th><th scope="col">Umidade</th><th scope="col">CO2 (ppm)</th><th scope="col">ITU (calor)</th></tr></thead>' +
        '<tbody>' + linhas + '</tbody></table></div></div>' +
        '<button type="button" class="ar-btn ar-btn--voltar-claro" data-acao="voltar">' + ICONE_VOLTAR + ' Voltar à granja</button>' +
        '<p class="ar-det__dica">Dica: a tecla Esc também volta à visão geral.</p></section>';
    }

    /* mapa 2D: coordenadas em metros da cena 3D convertidas para % (lote de 280 x 200 m) */
    htmlMapa2d(galpoes, marcador) {
      var self = this;
      var px = function (x) { return (x + 140) / 280 * 100; }, pz = function (z) { return (z + 100) / 200 * 100; };
      var pos = function (l, t, w, h) { return ' data-pos="' + [l, t, w == null ? '' : w, h == null ? '' : h].join(',') + '"'; };
      var s = 11, rr = function () { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
      var arv = '';
      for (var a = 0, tt = 0; a < 18 && tt < 400; tt++) {
        var ax = -134 + rr() * 268, az = -96 + rr() * 192;
        if ((ax > -82 && ax < 72 && az > -60 && az < 60) || Math.abs(ax + 78) < 8 || (ax > -128 && ax < -92 && az > 58 && az < 86)) continue;
        arv += '<div class="ar-m2 ar-m2--arvore" aria-hidden="true"' + pos(px(ax), pz(az)) + '></div>';
        a++;
      }
      var gs = galpoes.map(function (g) {
        var gz = self.zGalpao(g.i);
        return '<div class="ar-m2 ar-m2--estrada" aria-hidden="true"' + pos(px(-82), pz(gz - 3), 22 / 280 * 100, 3) + '></div>' +
          '<div class="ar-m2 ar-m2--silo" aria-hidden="true"' + pos(px(-51.8), pz(gz + 7.6)) + '></div>' +
          '<div class="ar-m2 ar-m2--galpao nv-' + g.ek + '" aria-hidden="true"' + pos(px(-60), pz(gz - 6), 120 / 280 * 100, 6) + '><span>placa</span><span>' + esc(g.codigo) + '</span><span>exaustores</span></div>' +
          marcador(g, ' ar-m2').replace('<button ', '<button' + pos(50, pz(gz - 6)) + ' ');
      }).join('');
      return '<div class="ar-mapa2d__terreno" role="img" aria-label="Mapa plano da granja: ' + galpoes.length + ' galpões lado a lado, sede, silos, estrada e portão.">' +
        '<div class="ar-m2 ar-m2--estrada" aria-hidden="true"' + pos(px(-82), pz(-60), 8 / 280 * 100, 80) + '></div>' + arv +
        '<div class="ar-m2 ar-m2--sede"' + pos(px(-119.5), pz(67), 15 / 280 * 100, 5) + '>Sede</div>' +
        '<div class="ar-m2 ar-m2--portao"' + pos(px(-86), pz(96), 16 / 280 * 100) + '>Portão</div>' + gs + '</div>';
    }
    posicionar2d(raiz) {
      raiz.querySelectorAll('[data-pos]').forEach(function (el) {
        var p = el.dataset.pos.split(',');
        el.style.left = p[0] + '%'; el.style.top = p[1] + '%';
        if (p[2]) el.style.width = p[2] + '%';
        if (p[3]) el.style.height = p[3] + '%';
      });
    }

    htmlPlanta(d) {
      return '<div class="ar-planta"><div class="ar-planta__pontas"><span>Entrada: placa evaporativa</span><span>Saída: exaustores</span></div>' +
        '<ol class="ar-planta__zonas" aria-label="Zonas da ronda, da entrada até a saída de ar">' + d.zonas.map(function (z) {
          return '<li><div class="ar-planta__robo" aria-hidden="true">' + (z.temRobo ? '<span>Carrinho aqui</span>' : '') + '</div>' +
            '<button type="button" class="ar-btn ar-planta__zona nv-' + z.nk + (z.foco ? ' ar-planta__zona--foco' : '') + '" data-acao="abrir" data-gc="' + esc(d.codigo) + '" data-zc="' + esc(z.codigo) + '" aria-label="' + esc(z.aria) + '">' +
            '<span class="cod">' + esc(z.codigo) + '</span><span class="nome">' + esc(z.nome) + '</span>' +
            '<span class="niv"><span aria-hidden="true">' + z.glifo + '</span> ' + esc(z.nivel) + '</span><span class="tmp">' + esc(z.temp) + '</span></button></li>';
        }).join('') + '</ol><div class="ar-planta__trajeto" aria-hidden="true"></div>' +
        '<div class="ar-planta__legenda" aria-hidden="true">Trajeto do carrinho no corredor central</div></div>';
    }
  }

  function iniciar() {
    var root = document.getElementById('ar-app');
    if (root) window.AviRondaGranja = new Painel(root);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
