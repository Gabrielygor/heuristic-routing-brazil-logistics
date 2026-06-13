import numpy as np
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional

# ─────────────────────────────────────────────
#  PARÂMETROS DO VEÍCULO E JORNADA LEGAL
# ─────────────────────────────────────────────
@dataclass
class Caminhao:
    nome: str                        = "VW Delivery 11.180"
    capacidade_kg: float             = 5_000.0  # kg
    consumo_cheio_lkm: float         = 0.35     # L/km com carga máxima
    consumo_vazio_lkm: float         = 0.22     # L/km sem carga
    preco_combustivel: float         = 6.50     # R$/L (diesel S-10)
    custo_motorista_hora: float      = 35.00    # R$/h (salário + encargos)
    custo_manutencao_km: float       = 0.18     # R$/km
    velocidade_kmh: float            = 60.0     # km/h média
    tempo_servico_h: float           = 0.30     # 18 min por parada (descarga)
    # Custos de espera/pernoite
    custo_pernoite: float            = 180.00   # R$ — hotel/diária motorista
    custo_espera_hora: float         = 20.00    # R$/h — hora parado (refeição etc.)
    # ── Jornada legal (Lei 13.103/2015 + Res. CONTRAN 493/2014) ──────────
    max_horas_direcao_dia: float     = 8.0      # máx. horas de direção por dia
    bloco_direcao_h: float           = 4.0      # bloco máximo sem pausa contínua
    intervalo_apos_bloco_h: float    = 0.5      # pausa obrigatória de 30 min após bloco
    descanso_entre_jornadas_h: float = 11.0     # descanso mínimo entre jornadas

CAMINHAO = Caminhao()

# ─────────────────────────────────────────────
#  PARÂMETROS DE ROTEIRIZAÇÃO
# ─────────────────────────────────────────────
HORA_INICIO_DIA  = 8.0   # horário de início de cada jornada
LIMIAR_EMPATE_KM = 30.0  # km — margem para desempate por prioridade

# ─────────────────────────────────────────────
#  DADOS DOS PONTOS DE ENTREGA
# ─────────────────────────────────────────────
dados = [
    {"nome": "Deposito (Natal)",  "lat": -5.7945, "lon": -35.2110, "janela": (8, 18), "prioridade": 0, "peso_kg": 0,   "descricao_carga": "—"},
    {"nome": "Parnamirim",        "lat": -5.9156, "lon": -35.2620, "janela": (8, 12), "prioridade": 2, "peso_kg": 800, "descricao_carga": "Bebidas e alimentos"},
    {"nome": "São Gonçalo",       "lat": -5.7936, "lon": -35.3270, "janela": (9, 17), "prioridade": 3, "peso_kg": 600, "descricao_carga": "Material de construção"},
    {"nome": "Ceará-Mirim",       "lat": -5.6350, "lon": -35.4250, "janela": (9, 15), "prioridade": 1, "peso_kg": 450, "descricao_carga": "Eletrônicos"},
    {"nome": "João Câmara",       "lat": -5.5370, "lon": -35.8170, "janela": (8, 12), "prioridade": 2, "peso_kg": 700, "descricao_carga": "Produtos agrícolas"},
    {"nome": "Mossoró",           "lat": -5.1875, "lon": -37.3440, "janela": (8, 18), "prioridade": 3, "peso_kg": 900, "descricao_carga": "Medicamentos e suprimentos"},
    {"nome": "Apodi",             "lat": -5.6640, "lon": -37.7980, "janela": (8, 14), "prioridade": 1, "peso_kg": 350, "descricao_carga": "Ferragens"},
    {"nome": "Pau dos Ferros",    "lat": -6.1100, "lon": -38.2100, "janela": (13, 18),"prioridade": 2, "peso_kg": 500, "descricao_carga": "Têxteis"},
    {"nome": "Açu",               "lat": -5.5830, "lon": -36.9130, "janela": (8, 16), "prioridade": 1, "peso_kg": 400, "descricao_carga": "Hortifrutigranjeiros"},
    {"nome": "Macau",             "lat": -5.1070, "lon": -36.6340, "janela": (9, 15), "prioridade": 2, "peso_kg": 300, "descricao_carga": "Químicos industriais"},
]

n = len(dados)

# ─────────────────────────────────────────────
#  FUNÇÕES AUXILIARES
# ─────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon/2)**2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def consumo_trecho(dist_km, peso_atual_kg):
    fracao = min(peso_atual_kg / CAMINHAO.capacidade_kg, 1.0)
    lkm = (CAMINHAO.consumo_vazio_lkm
           + fracao * (CAMINHAO.consumo_cheio_lkm - CAMINHAO.consumo_vazio_lkm))
    return dist_km * lkm


def hhmm(horas_decimais):
    h = int(horas_decimais) % 24
    m = int(round((horas_decimais - int(horas_decimais)) * 60))
    if m == 60:
        h = (h + 1) % 24
        m = 0
    return f"{h:02d}:{m:02d}"


def dia_label(tempo_abs):
    """Retorna o número do dia (1-based) a partir do tempo absoluto."""
    return int(tempo_abs // 24) + 1


def ajustar_para_janela(chegada, janela):
    """
    Retorna (inicio_entrega, horas_espera, pernoitou).
    Nunca deixa entregar fora da janela — se passou, vai para o próximo dia.
    """
    inicio, fim = janela
    hora_no_dia = chegada % 24
    if hora_no_dia <= fim:
        inicio_entrega = chegada + max(0, inicio - hora_no_dia)
        return inicio_entrega, inicio_entrega - chegada, False
    else:
        # passou do fechamento: aguarda abertura no dia seguinte
        horas_ate_abertura = (24 - hora_no_dia) + inicio
        inicio_entrega = chegada + horas_ate_abertura
        return inicio_entrega, horas_ate_abertura, True


def custo_espera(horas, pernoitou):
    base = horas * CAMINHAO.custo_espera_hora
    if pernoitou:
        base += CAMINHAO.custo_pernoite
    return base


# ─────────────────────────────────────────────
#  CONTROLE DE JORNADA LEGAL
# ─────────────────────────────────────────────
@dataclass
class JornadaMotorista:
    """
    Rastreia o tempo de direção dentro do dia e aplica pausas/descanso
    conforme Lei 13.103/2015 e Res. CONTRAN 493/2014.

    Regras implementadas:
    - Máximo de 8h de direção por jornada diária.
    - A cada 4h contínuas de direção → pausa obrigatória de 30 min.
    - Entre o fim de uma jornada e o início da próxima → 11h de descanso.
    """
    horas_dirigidas_hoje: float = 0.0   # acumulado de direção no dia atual
    horas_bloco_atual: float    = 0.0   # direção contínua desde a última pausa
    inicio_jornada: float       = HORA_INICIO_DIA  # momento em que o dia começou

    def simular_trecho(self, tempo_atual: float, duracao_trecho_h: float):
        """
        Avança o tempo levando em conta pausas e limite diário.
        Retorna (tempo_chegada, horas_pausa_inseridas, forcou_descanso_noturno, custo_pausa).
        """
        horas_pausa_total = 0.0
        forcou_descanso   = False
        tempo             = tempo_atual
        restante          = duracao_trecho_h

        while restante > 0:
            # ── Verifica se atingiu o limite diário de direção ──────────
            if self.horas_dirigidas_hoje >= CAMINHAO.max_horas_direcao_dia:
                # Encerra jornada: descansa 11h a partir do momento atual
                pausa_descanso         = CAMINHAO.descanso_entre_jornadas_h
                tempo                 += pausa_descanso
                horas_pausa_total     += pausa_descanso
                self.horas_dirigidas_hoje = 0.0
                self.horas_bloco_atual    = 0.0
                self.inicio_jornada       = tempo
                forcou_descanso           = True
                continue  # recomeça o loop com o tempo zerado

            # ── Quanto posso dirigir antes de precisar de pausa de bloco ─
            espaco_no_bloco = CAMINHAO.bloco_direcao_h - self.horas_bloco_atual
            # Quanto posso dirigir antes de bater no limite diário
            espaco_no_dia   = CAMINHAO.max_horas_direcao_dia - self.horas_dirigidas_hoje
            # Quanto efetivamente dirige neste passo
            dirigir_agora   = min(restante, espaco_no_bloco, espaco_no_dia)

            tempo                      += dirigir_agora
            self.horas_dirigidas_hoje  += dirigir_agora
            self.horas_bloco_atual     += dirigir_agora
            restante                   -= dirigir_agora

            # ── Pausa de 30 min se completou um bloco de 4h ─────────────
            if restante > 0 and self.horas_bloco_atual >= CAMINHAO.bloco_direcao_h:
                tempo                  += CAMINHAO.intervalo_apos_bloco_h
                horas_pausa_total      += CAMINHAO.intervalo_apos_bloco_h
                self.horas_bloco_atual  = 0.0

        custo_p = horas_pausa_total * CAMINHAO.custo_espera_hora
        return tempo, horas_pausa_total, forcou_descanso, custo_p

    def registrar_parada(self, tempo_servico_h: float):
        """
        Parada de entrega: zera o bloco contínuo (motorista descansou),
        mas NÃO conta como direção.
        """
        self.horas_bloco_atual = 0.0

    def iniciar_novo_dia(self, tempo_atual: float):
        """Força início de novo dia de jornada a partir de tempo_atual."""
        self.horas_dirigidas_hoje = 0.0
        self.horas_bloco_atual    = 0.0
        self.inicio_jornada       = tempo_atual


# ─────────────────────────────────────────────
#  MATRIZ DE DISTÂNCIAS
# ─────────────────────────────────────────────
dist = np.zeros((n, n))
for i in range(n):
    for j in range(n):
        dist[i][j] = haversine(dados[i]["lat"], dados[i]["lon"],
                               dados[j]["lat"], dados[j]["lon"])

# ─────────────────────────────────────────────
#  VALIDAÇÃO DE CAPACIDADE
# ─────────────────────────────────────────────
peso_total_entregas = sum(d["peso_kg"] for d in dados)
if peso_total_entregas > CAMINHAO.capacidade_kg:
    excesso = peso_total_entregas - CAMINHAO.capacidade_kg
    print(f"\n ATENÇÃO: Carga total ({peso_total_entregas:.0f} kg) excede a "
          f"capacidade ({CAMINHAO.capacidade_kg:.0f} kg) em {excesso:.0f} kg!\n")

# ─────────────────────────────────────────────
#  ESTRUTURA DE PARADA
# ─────────────────────────────────────────────
@dataclass
class Parada:
    indice: int
    chegada: float           # chegada física ao ponto (após pausas de jornada)
    inicio_entrega: float    # quando a entrega ocorre (dentro da janela)
    saida: float
    peso_no_momento_kg: float
    dist_trecho_km: float
    litros_trecho: float
    horas_espera_janela: float   # espera por janela de tempo do cliente
    horas_pausa_jornada: float   # pausas legais inseridas no trecho
    pernoitou: bool
    forcou_descanso: bool        # True se o limite diário foi atingido no trecho
    custo_espera_janela: float
    custo_pausa_jornada: float
    status: str


# ─────────────────────────────────────────────
#  ALGORITMO DE ROTEIRIZAÇÃO
# ─────────────────────────────────────────────
def rota_entregas():
    visitado = [False] * n
    visitado[0] = True
    peso_atual = sum(d["peso_kg"] for d in dados if d["peso_kg"] > 0)
    jornada    = JornadaMotorista()

    paradas = [Parada(
        indice=0, chegada=HORA_INICIO_DIA, inicio_entrega=HORA_INICIO_DIA,
        saida=HORA_INICIO_DIA, peso_no_momento_kg=peso_atual,
        dist_trecho_km=0, litros_trecho=0,
        horas_espera_janela=0, horas_pausa_jornada=0,
        pernoitou=False, forcou_descanso=False,
        custo_espera_janela=0, custo_pausa_jornada=0,
        status="depósito",
    )]

    tempo_atual      = HORA_INICIO_DIA
    dist_total       = 0.0
    litros_tot       = 0.0
    custo_espera_tot = 0.0
    custo_jornada_tot= 0.0

    while not all(visitado):
        atual = paradas[-1].indice

        # Seleciona próximo destino (nearest neighbor + desempate por prioridade)
        melhor, melhor_dist, melhor_prio = None, float("inf"), -1
        for j in range(n):
            if visitado[j]:
                continue
            d_j, p_j = dist[atual][j], dados[j]["prioridade"]
            if d_j < melhor_dist:
                melhor_dist, melhor_prio, melhor = d_j, p_j, j
            elif abs(d_j - melhor_dist) < LIMIAR_EMPATE_KM and p_j > melhor_prio:
                melhor_prio, melhor = p_j, j

        d_trecho   = dist[atual][melhor]
        t_viagem_h = d_trecho / CAMINHAO.velocidade_kmh

        # ── Aplica regras de jornada ao trecho de direção ──────────────
        chegada_real, h_pausa, forcou_descanso, c_pausa = jornada.simular_trecho(
            tempo_atual, t_viagem_h
        )
        custo_jornada_tot += c_pausa

        # ── Ajusta para a janela de tempo do cliente ────────────────────
        inicio_j, fim_j = dados[melhor]["janela"]
        inicio_entrega, h_espera_jan, pernoitou = ajustar_para_janela(chegada_real, (inicio_j, fim_j))

        # Se pernoitou aguardando janela, reinicia contadores de jornada
        if pernoitou:
            jornada.iniciar_novo_dia(inicio_entrega)

        c_espera_jan    = custo_espera(h_espera_jan, pernoitou)
        custo_espera_tot += c_espera_jan

        # ── Consumo e peso ──────────────────────────────────────────────
        litros      = consumo_trecho(d_trecho, peso_atual)
        litros_tot += litros
        dist_total += d_trecho
        peso_atual  = max(peso_atual - dados[melhor]["peso_kg"], 0)

        # ── Parada: zera bloco contínuo (motorista desceu do caminhão) ──
        saida = inicio_entrega + CAMINHAO.tempo_servico_h
        jornada.registrar_parada(CAMINHAO.tempo_servico_h)

        # ── Status ──────────────────────────────────────────────────────
        flags = []
        if forcou_descanso:
            flags.append(f"descanso legal")
        if h_pausa > 0 and not forcou_descanso:
            flags.append(f"☕ pausa {h_pausa*60:.0f}min")
        if pernoitou:
            flags.append(f"pernoite")
        elif h_espera_jan > 0:
            flags.append(f"aguarda janela")
        if not flags:
            flags.append("no prazo")
        status = " | ".join(flags)

        paradas.append(Parada(
            indice=melhor,
            chegada=chegada_real,
            inicio_entrega=inicio_entrega,
            saida=saida,
            peso_no_momento_kg=peso_atual,
            dist_trecho_km=d_trecho,
            litros_trecho=litros,
            horas_espera_janela=h_espera_jan,
            horas_pausa_jornada=h_pausa,
            pernoitou=pernoitou,
            forcou_descanso=forcou_descanso,
            custo_espera_janela=c_espera_jan,
            custo_pausa_jornada=c_pausa,
            status=status,
        ))

        visitado[melhor] = True
        tempo_atual = saida

    # ── Retorno ao depósito ─────────────────────────────────────────────
    ultimo  = paradas[-1].indice
    d_volta = dist[ultimo][0]
    t_volta = d_volta / CAMINHAO.velocidade_kmh
    chegada_dep, h_pausa_volta, forcou_volta, c_pausa_volta = jornada.simular_trecho(tempo_atual, t_volta)
    custo_jornada_tot += c_pausa_volta
    litros_volta = consumo_trecho(d_volta, 0)
    litros_tot  += litros_volta
    dist_total  += d_volta

    paradas.append(Parada(
        indice=0, chegada=chegada_dep, inicio_entrega=chegada_dep,
        saida=chegada_dep, peso_no_momento_kg=0,
        dist_trecho_km=d_volta, litros_trecho=litros_volta,
        horas_espera_janela=0, horas_pausa_jornada=h_pausa_volta,
        pernoitou=False, forcou_descanso=forcou_volta,
        custo_espera_janela=0, custo_pausa_jornada=c_pausa_volta,
        status="retorno",
    ))

    return paradas, dist_total, chegada_dep, litros_tot, custo_espera_tot, custo_jornada_tot


# ─────────────────────────────────────────────
#  EXECUÇÃO E RELATÓRIO
# ─────────────────────────────────────────────
paradas, dist_total, tempo_final, litros_total, custo_espera_total, custo_jornada_total = rota_entregas()

horas_totais      = tempo_final - HORA_INICIO_DIA
dias_viagem       = int(tempo_final // 24) + 1
custo_combustivel = litros_total * CAMINHAO.preco_combustivel
custo_motorista   = horas_totais * CAMINHAO.custo_motorista_hora
custo_manutencao  = dist_total * CAMINHAO.custo_manutencao_km
custo_total       = custo_combustivel + custo_motorista + custo_manutencao + custo_espera_total + custo_jornada_total

LINHA = "─" * 128

print(f"\n{'═'*128}")
print(f"  RELATÓRIO DE ROTA — {CAMINHAO.nome}  "
      f"|  Capacidade: {CAMINHAO.capacidade_kg:,.0f} kg  "
      f"|  Jornada máx: {CAMINHAO.max_horas_direcao_dia:.0f}h/dia  "
      f"|  Pausa a cada: {CAMINHAO.bloco_direcao_h:.0f}h  "
      f"|  Descanso entre jornadas: {CAMINHAO.descanso_entre_jornadas_h:.0f}h")
print(f"{'═'*128}")
print(f"{'#':<3} {'Origem':<18} {'Destino':<18} {'Dist':>7} {'Chegada':>9} {'Entrega':>9} "
      f"{'EspJan':>7} {'PausaLeg':>9} {'Status':<35} {'Peso':>7} {'Litros':>7}")
print(LINHA)

for i in range(len(paradas) - 1):
    p  = paradas[i + 1]
    origem  = dados[paradas[i].indice]["nome"]
    destino = dados[p.indice]["nome"]

    d_chegada = dia_label(p.chegada)
    d_entrega = dia_label(p.inicio_entrega)
    chegada_s = f"D{d_chegada} {hhmm(p.chegada)}" if d_chegada > 1 else hhmm(p.chegada)
    entrega_s = f"D{d_entrega} {hhmm(p.inicio_entrega)}" if d_entrega > 1 else hhmm(p.inicio_entrega)

    esp_jan = f"{p.horas_espera_janela:.1f}h" if p.horas_espera_janela > 0 else "—"
    pau_leg = f"{p.horas_pausa_jornada*60:.0f}min" if p.horas_pausa_jornada > 0 else "—"

    print(f"{i+1:<3} {origem:<18} {destino:<18} "
          f"{p.dist_trecho_km:>6.1f}km "
          f"{chegada_s:>9} {entrega_s:>9} "
          f"{esp_jan:>7} {pau_leg:>9}  "
          f"{p.status:<35} "
          f"{p.peso_no_momento_kg:>6.0f}kg "
          f"{p.litros_trecho:>6.1f}L")

print(LINHA)

# ── Cargas entregues ───────────────────────────────────────────────────
print(f"\n��  CARGAS ENTREGUES:")
print(f"    {'Ponto':<20} {'Janela':>12} {'Peso':>8}  Carga")
print(f"    {'─'*65}")
for p in paradas[1:-1]:
    d = dados[p.indice]
    print(f"    {d['nome']:<20} {d['janela'][0]:02d}:00–{d['janela'][1]:02d}:00 "
          f"{d['peso_kg']:>7.0f}kg  {d['descricao_carga']}")

# ── Eventos de jornada ─────────────────────────────────────────────────
eventos_jornada = [p for p in paradas if p.forcou_descanso or p.horas_pausa_jornada > 0]
if eventos_jornada:
    print(f"\n��  EVENTOS DE JORNADA LEGAL:")
    print(f"    {'Destino':<20} {'Tipo':<30} {'Pausa':>8}  {'Custo':>10}")
    print(f"    {'─'*72}")
    for p in eventos_jornada:
        d = dados[p.indice]
        tipo = "Descanso entre jornadas (11h)" if p.forcou_descanso else f"Pausa de bloco (30min)"
        print(f"    {d['nome']:<20} {tipo:<30} "
              f"{p.horas_pausa_jornada*60:>6.0f}min  R$ {p.custo_pausa_jornada:>8.2f}")

pernoites = [p for p in paradas if p.pernoitou]
if pernoites:
    print(f"\n��  PERNOITES (janela de cliente):")
    print(f"    {'Destino':<20} {'Chegada':>9}  {'Abre':>7}  {'Espera':>7}  {'Custo':>10}")
    print(f"    {'─'*65}")
    for p in pernoites:
        d = dados[p.indice]
        print(f"    {d['nome']:<20} {hhmm(p.chegada):>9}  "
              f"{d['janela'][0]:02d}:00   "
              f"{p.horas_espera_janela:>6.1f}h  R$ {p.custo_espera_janela:>8.2f}")

# ── Resumo financeiro ──────────────────────────────────────────────────
print(f"\n{'═'*128}")
print(f"  RESUMO OPERACIONAL")
print(f"{'─'*128}")
print(f"  Distância total          : {dist_total:>10.2f} km")
print(f"  Duração da missão        : {dias_viagem} dia(s) — saída 08:00 D1 → retorno {hhmm(tempo_final)} D{dias_viagem}")
print(f"  Horas acumuladas         : {horas_totais:>10.2f} h  (inclui esperas e pausas legais)")
print(f"  Combustível consumido    : {litros_total:>10.2f} L  (média {dist_total/litros_total:.2f} km/L)")
print(f"  Carga entregue           : {peso_total_entregas:>10.2f} kg ({100*peso_total_entregas/CAMINHAO.capacidade_kg:.1f}% da capacidade)")
print(f"{'─'*128}")
print(f"  CUSTOS OPERACIONAIS")
print(f"{'─'*128}")
print(f"  Combustível  (R$ {CAMINHAO.preco_combustivel:.2f}/L)         : R$ {custo_combustivel:>10.2f}")
print(f"  Motorista    (R$ {CAMINHAO.custo_motorista_hora:.2f}/h)        : R$ {custo_motorista:>10.2f}")
print(f"  Manutenção   (R$ {CAMINHAO.custo_manutencao_km:.2f}/km)        : R$ {custo_manutencao:>10.2f}")
print(f"  Espera/Pernoite (janela cliente)    : R$ {custo_espera_total:>10.2f}")
print(f"  Pausas legais (pausa + descanso)    : R$ {custo_jornada_total:>10.2f}")
print(f"  {'─'*55}")
print(f"  CUSTO TOTAL                         : R$ {custo_total:>10.2f}")
print(f"  Custo por km                        : R$ {custo_total/dist_total:>10.2f}")
print(f"  Custo por entrega                   : R$ {custo_total/(n-1):>10.2f}")
print(f"{'═'*128}\n")
