"""
states/story.py  –  Modo História (single ou multiplayer).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TELAS
  STORY_LIST  – lista de campanhas salvas + botão "Nova Campanha"
  STORY_NEW   – formulário: título, missão principal, personagens
  STORY_PLAY  – chat com IA + painel lateral:
                  Fichas | Inventário | Missões | Batalha | Notas

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TAGS QUE A IA PODE INSERIR NA RESPOSTA

  <MUSIC>clima</MUSIC>
      Troca a trilha de fundo.  Climas aceitos (ver MUSIC_MAP em settings.py):
      taverna | exploration | fight | end

  <SFX>nome</SFX>
      Dispara um efeito sonoro one-shot.  Nomes aceitos (ver SFX_MAP):
      ataque | magia | dano | level_up   (e aliases; ver settings.py)

  <AMBIENT>nome</AMBIENT>
      Liga/desliga som ambiente em loop no canal 1.
      Nomes aceitos: chuva  (rain.wav)
      Use <AMBIENT>stop</AMBIENT> para silenciar.

  <BATTLE>[{nome,hp,hp_max,ataque,defesa,descricao}]</BATTLE>
      Inicia combate; mostra painel Batalha + toca weapon_attack.wav.

  <ENDBATTLE/>
      Encerra combate; toca battle_win.wav.

  <QUEST>{"nome","descricao","status"}</QUEST>
      Adiciona/atualiza missão no diário.

  <PUZZLE>{"titulo","pistas":[str]}</PUZZLE>
      Adiciona pistas no painel Notas.

  <UPDATE>{"personagem_id":N, "status":{...}}</UPDATE>
      Atualiza atributos do personagem; toca level_up.wav se 'nivel' subiu.

  <ENDSTORY reason="..."/>
      Encerra a campanha, toca end.mp3 + stop ambient.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIGURAÇÃO
  Copie .env.example para .env e preencha:
    GROQ_API_KEY=gsk_...
"""

import os, re, json, threading, time
import pygame
from settings import *
from ui import Button, TextInput, MultilineTextInput, ContentArea, draw_text_wrapped
from database import (
    load_characters, load_stories, save_story, complete_story,
    append_chat_message, get_story_chat, update_character_after_session,
)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ─────────────────────────────────────────────────────────────────────────────
# CAMADA DE API (Groq)
# ─────────────────────────────────────────────────────────────────────────────

CHAT_SPLIT = 0.64   # fração da largura dedicada ao chat


def _build_system_prompt(personagens: list[dict], descricao: str, tags: list[str],
                         missao_principal: str = "") -> str:
    """
    Monta o prompt de sistema completo para a IA narradora.
    Inclui: personagens, arco narrativo, finais possíveis, regras de música e tags.
    """
    partes = [
        "Você é um Mestre de RPG de mesa imersivo, criativo e narrativamente coerente.",
        "Narre a história em português, com acentuação e gramática corretas.",
        "Corrija silenciosamente erros gramaticais dos jogadores ao narrar, sem comentar.",
        "",
    ]

    if missao_principal:
        partes += [
            "== MISSÃO PRINCIPAL ==",
            missao_principal,
            "",
        ]
    else:
        partes += [
            "== INSTRUÇÃO: MISSÃO NÃO DEFINIDA ==",
            "O jogador não definiu uma missão. VOCÊ deve inventar uma agora:",
            "- Escolha um conflito central urgente e específico (não genérico).",
            "- Relacione a missão ao histórico/classe/raça dos personagens.",
            "- Registre via <QUEST> na cena de abertura.",
            "- Não mencione ao jogador que não havia missão — apenas narre.",
            "",
        ]

    if descricao:
        partes += [f"Tom/ambientação da campanha: {descricao}", ""]
    else:
        partes += [
            "== INSTRUÇÃO: AMBIENTAÇÃO NÃO DEFINIDA ==",
            "O jogador não definiu ambientação. VOCÊ deve escolher:",
            "- Um cenário com personalidade forte (ex: cidade portuária corrupta,",
            "  floresta mágica que corrói a sanidade, reino em guerra civil, ruínas",
            "  de uma civilização perdida, subterrâneo infestado de criaturas).",
            "- Mantenha CONSISTÊNCIA com esse cenário durante toda a campanha.",
            "",
        ]

    if tags:
        partes += [f"Tags: {', '.join(tags)}", ""]

    partes += ["", "== PERSONAGENS PARTICIPANTES =="]
    for p in personagens:
        atr = p.get("atributos", {})
        sts = p.get("status", {})
        # IMPORTANTE: inclui o ID real do personagem para que a IA use o valor
        # correto em <UPDATE personagem_id=N> e <LOOT personagem_id=N>.
        # Sem isso a IA chuta o ID (geralmente 1) e o update nunca encontra o char.
        partes.append(
            f"- {p['nome']} [personagem_id={p['id']}] ({p.get('raca','?')} / {p.get('classe','?')}, "
            f"Nível {sts.get('nivel',1)}, Título: {p.get('titulo_ativo','')}) | "
            f"FOR {atr.get('forca',10)} DES {atr.get('destreza',10)} "
            f"INT {atr.get('inteligencia',10)} "
            f"HP {sts.get('hp_atual', sts.get('hp_maximo',30))}/{sts.get('hp_maximo',30)} "
            f"MP {sts.get('mana_atual', sts.get('mana_maximo',10))}/{sts.get('mana_maximo',10)}"
        )
        inv  = [i['nome'] if isinstance(i,dict) else str(i) for i in p.get("inventario",[])]
        hab  = [h['nome'] if isinstance(h,dict) else str(h) for h in p.get("habilidades",[])]
        hist = p.get("historia","")
        if inv:  partes.append(f"  Inventário: {', '.join(inv)}")
        if hab:  partes.append(f"  Habilidades: {', '.join(hab)}")
        if hist:
            partes.append(f"  História: {hist[:300]}")
        else:
            partes.append(
                f"  História: (vazia — mencione uma origem breve e temática para "
                f"{p['nome']} durante a narração, integrando à cena. Não avise o jogador.)"
            )

    partes += [
        "",
        "== ARCO NARRATIVO ==",
        "- A história deve ter início, meio e fim. Não é infinita.",
        "- Na cena de abertura, estabeleça a situção, o conflito central e dê ao jogador",
        "  uma noção indireta de que há 2-3 caminhos possíveis (desfechos diferentes).",
        "- O final pode ser: vitória, derrota tragédia, ou conclusão moralmente ambígua.",
        "- Mantenha um ritmo: introdução (1-2 cenas), desenvolvimento (3-6 cenas), clímax, desfecho.",
        "- Quando a história chegar ao fim natural (missão resolvida, personagem morto, etc.),",
        "  inclua ao FINAL da mensagem:",
        '  <ENDSTORY reason="Descrição breve do desfecho"/>',
        "",
        "== SISTEMA DE COMBATE POR TURNOS ==",
        "O combate DEVE ser estruturado por turnos claros. Siga este fluxo:",
        "",
        "[ABERTURA DO COMBATE]",
        "  - Declare quem age primeiro (baseado em DES ou contexto narrativo).",
        "  - Descreva posicionamento, ambiente e estado inicial dos combatentes.",
        "  - Inclua <BATTLE>[...]</BATTLE> para registrar os inimigos.",
        "",
        "[TURNO DO JOGADOR]",
        "  O jogador pode escolher UMA acao por turno:",
        "  • Atacar      – ataque fisico com a arma equipada.",
        "  • Defender    – postura defensiva; reduz dano recebido neste turno.",
        "  • Magias      – feitico ou habilidade; mais poderoso, gasta MP.",
        "  • Usar Item   – consome item do inventario (pocao, bomba, etc.).",
        "  • Inspecionar – revela fraquezas ou padrao de ataque do alvo.",
        "  • Fugir        – tentativa de fuga baseada em DES vs velocidade do inimigo.",
        "  AGUARDE a descricao do jogador antes de resolver o turno.",
        "",
        "[RESOLUCAO DO TURNO]",
        "  1. Descreva o resultado da acao do jogador (acertou? errou? critico?).",
        "  2. Reporte o dano causado ao inimigo: <DMGENEMY idx=\"0\" dmg=\"7\"/>",
        "     onde idx = posicao do inimigo na lista (0=primeiro, 1=segundo...).",
        "  3. Se o inimigo morreu: <DMGENEMY idx=\"0\" dmg=\"9999\"/> + narre a morte.",
        "  4. Descreva a acao dos inimigos vivos (cada um age diferente!).",
        "  5. Se inimigo causou dano ao jogador: <UPDATE>{\"personagem_id\":N,",
        "     \"status\":{\"hp_atual\": NOVO_HP}}</UPDATE>",
        "  6. Pergunte: 'O que voce faz no seu proximo turno?'",
        "",
        "[VARIEDADE DE INIMIGOS]",
        "  - Inimigos covardes fogem quando HP < 20%.",
        "  - Inimigos inteligentes exploram fraquezas de classe (ladino vs guerreiro).",
        "  - Inimigos em grupo coordenam: um distrai, outro flanqueia.",
        "  - Use descricao tatica: posicionamento, terreno, iluminacao.",
        "",
        "[FIM DO COMBATE]",
        "  - Quando TODOS os inimigos morrerem: use <ENDBATTLE/> + descreva o pos-combate.",
        "  - Ao fim do combate, ofereça XP balanceado e SEMPRE use <LOOT> se houver itens.",
        "",
        "== PROGRESSÃO E RECOMPENSAS ==",
        "",
        "[XP POR EVENTO — inclua sempre via <UPDATE>]",
        "  Inimigo fraco  :  20–50 XP   |   Inimigo médio : 50–100 XP",
        "  Inimigo forte  : 100–200 XP  |   Boss/miniboss : 200–500 XP",
        "  Missão concluída: +50% do XP do combate correspondente",
        "  Puzzle resolvido:  30–60 XP  |   Escolha narrativa impactante: 10–30 XP",
        "",
        "[LEVEL UP — fórmula: nivel_novo = 1 + xp_total // 100  (máximo 20)]",
        "  Ao detectar que xp acumulado cruza o limiar, SEMPRE inclua em <UPDATE>:",
        "  1. status.nivel = novo_nivel",
        "  2. status.hp_maximo  += 10 (guerreiro/bárbaro/paladino) ou +5 (outras classes)",
        "  3. status.mana_maximo += 8 (mago/feiticeiro/bruxo/clérigo) ou +3 (outras classes)",
        "  4. atributos: +1 em 2 atributos temáticos para a classe/raça",
        "  5. novo_titulo: {\"nome\":\"...\",\"descricao\":\"...\",\"beneficio\":\"...\"}",
        "     — crie um título narrativo ÚNICO que reflita as conquistas da sessão",
        "  6. adicionar_habilidades: [{nova skill desbloqueada pelo nível}]",
        "  7. Adicione <SFX>level_up</SFX> imediatamente antes do <UPDATE>.",
        "  Exemplo completo de UPDATE de level-up:",
        f'  <UPDATE>{{"personagem_id":{personagens[0]["id"] if personagens else "ID_DO_PERSONAGEM"},"status":{{"xp":250,"nivel":3,',
        '   "hp_maximo":50,"mana_maximo":25,"hp_atual":50},',
        '   "atributos":{"forca":14,"destreza":12},',
        '   "novo_titulo":{"nome":"Sobrevivente das Sombras",',
        '    "descricao":"...","beneficio":"+2 DEF nas trevas"},',
        '   "adicionar_habilidades":[{"nome":"Golpe Brutal",',
        '    "custo":"6 mana","efeito":"Dano x2","recarga":"2 turnos"}]}</UPDATE>',
        "",
        "[LOOT — itens encontrados após eventos]",
        "  Use <LOOT> sempre que o jogador encontrar itens: após combate, exploração,",
        "  compra, recompensa ou evento narrativo. Ofereça 1–3 itens por evento.",
        "  Varie raridade: itens comuns (maioria), raros (~1 por sessão), épicos (boss only).",
        "  Formato: <LOOT>{\"personagem_id\": N, \"itens\": [{\"nome\":\"...\",",
        "  \"historia\":\"...\",\"ataque\":int,\"defesa\":int,",
        "  \"efeito_status\":\"...\",\"resistencia\":\"...\"}]}</LOOT>",
        "  O jogador verá os itens no painel Inventário e escolherá pegar ou ignorar.",
        "",
        "== REGRAS DE MÚSICA E SOM (OBRIGATÓRIO) ==",
        "- Ao INÍCIO de cada resposta, use <MUSIC>clima</MUSIC> para a trilha de fundo.",
        "",
        "  <MUSIC>exploration</MUSIC>  ← PADRÃO. Use na maioria das cenas:",
        "       viagem, floresta, dungeon, investigação, tensão, cenas genéricas.",
        "  <MUSIC>taverna</MUSIC>      ← APENAS quando: bar, estalagem, mercado,",
        "       conversa amigável/relaxada, festa, cidade em paz.",
        "  <MUSIC>fight</MUSIC>        ← combate ativo.",
        "  <MUSIC>end</MUSIC>          ← epílogo, morte, conclusão.",
        "",
        "- Troque o clima sempre que a atmosfera da cena mudar.",
        "- Para cenas chuvosas/tempestade: adicione <AMBIENT>chuva</AMBIENT>.",
        "- <AMBIENT>stop</AMBIENT> para silenciar o ambiente.",
        "- Efeitos de ação (máx. 1-2 por mensagem):",
        "  <SFX>ataque</SFX> | <SFX>magia</SFX> | <SFX>dano</SFX>",
        "",
        "== TAGS DISPONÍVEIS (use EXATAMENTE esta sintaxe) ==",
        "",
        "[MÚSICA DE FUNDO — inclua no INÍCIO de cada mensagem]",
        "  <MUSIC>taverna</MUSIC>    – taverna, cidade, descanso",
        "  <MUSIC>exploration</MUSIC> – viagem, floresta, dungeon, investigação",
        "  <MUSIC>fight</MUSIC>      – combate ativo",
        "  <MUSIC>end</MUSIC>        – epílogo, morte, conclusão",
        "",
        "[EFEITOS SONOROS — one-shot, dispara imediatamente]",
        "  <SFX>ataque</SFX>    – golpe de arma física",
        "  <SFX>magia</SFX>     – feitiço ou habilidade especial",
        "  <SFX>dano</SFX>      – personagem sofre dano",
        "  <SFX>level_up</SFX>  – personagem evolui (use junto com <UPDATE>)",
        "",
        "[SOM AMBIENTE — loop no fundo, acumula com a música]",
        "  <AMBIENT>chuva</AMBIENT>   – começa chuva ambiente",
        "  <AMBIENT>stop</AMBIENT>    – para o som ambiente atual",
        "",
        "[COMBATE]",
        '  <BATTLE>[{"nome":"Inimigo","hp":20,"hp_max":20,',
        '           "ataque":8,"defesa":3,"descricao":"..."}]</BATTLE>',
        "  <ENDBATTLE/>   – fim do combate (toca fanfarra de vitória)",
        "",
        "[MISSÃO / PUZZLE / EVOLUÇÃO]",
        '  <QUEST>{"nome":"...","descricao":"...","status":"Ativa"}</QUEST>',
        '  <PUZZLE>{"titulo":"...","pistas":["..."]}</PUZZLE>',
        f'  <UPDATE>{{"personagem_id":{personagens[0]["id"] if personagens else "ID"},"status":{{"xp":150,"nivel":2,"hp_atual":25}}}}</UPDATE>',
        '  <DMGENEMY idx="0" dmg="7"/>   – aplica 7 dano ao 1º inimigo da lista',
        "",
        "[LOOT — itens para o jogador escolher]",
        f'  <LOOT>{{"personagem_id":{personagens[0]["id"] if personagens else "ID"},"itens":[{{"nome":"Espada de Fogo","historia":"...",',
        '   "ataque":15,"defesa":0,"efeito_status":"Dano de fogo +1d6","resistencia":"Frio"}]}</LOOT>',
        "",
        "[FIM DA HISTÓRIA — inclua ao final da última mensagem]",
        '  <ENDSTORY reason="Desfecho breve"/>',
    ]
    return "\n".join(p for p in partes if p is not None)


def _chamar_groq(historico: list[dict], system_prompt: str) -> str:
    """
    Envia o histórico de chat para a API Groq e retorna a resposta do narrador.

    Parâmetros:
        historico     – lista de mensagens [{role, content}] acumuladas na sessão.
        system_prompt – prompt de sistema gerado por _build_system_prompt().

    Fluxo:
        1. Lê GROQ_API_KEY do ambiente (.env carregado em settings.py).
        2. Se a chave não existir, usa _mock_narracao() como fallback offline.
        3. Chama llama-3.3-70b-versatile com temperatura 0.9 e máx. 1500 tokens.
        4. Em caso de erro (rede, quota, etc.) retorna mensagem de erro + mock.

    Retorna:
        String com a resposta do narrador (pode conter tags de jogo).
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return _mock_narracao(historico)
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        messages = [{"role": "system", "content": system_prompt}] + historico
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.9,
            max_tokens=1500,
        )
        return resp.choices[0].message.content
    except ImportError:
        return "[Instale o pacote groq: pip install groq]\n\n" + _mock_narracao(historico)
    except Exception as e:
        return f"[Erro Groq: {e}]\n\n" + _mock_narracao(historico)


def _mock_narracao(historico: list[dict]) -> str:
    respostas = [
        "<QUEST>{\"nome\":\"A Taverna Sussurrante\",\"descricao\":\"Descubra de onde vêm os rumores sinistrós\",\"status\":\"Ativa\"}</QUEST>\n\n"
        "As sombras dançam nas paredes da taverna enquanto vocês se olham. "
        "O vento faz a chama das tochas tremer. Algo está por vir...\n"
        "O que vocês fazem?",

        "O caminho se bifurca: à esquerda, um bosque sussurrante; "
        "à direita, fumarolas de enxofre sobem de uma ravina.\n"
        "<PUZZLE>{\"titulo\":\"A Bifurcação\",\"pistas\":[\"Marcas de garras no solo esquerdo\",\"Cheiro de enxofre à direita\"]}</PUZZLE>\n"
        "Qual caminho tomam?",

        "<BATTLE>[{\"nome\":\"Goblin Batedores\",\"hp\":12,\"hp_max\":12,\"ataque\":5,\"defesa\":2,\"descricao\":\"Pequenos e rápidos, mas covardes\"},{\"nome\":\"Goblin Arqueiro\",\"hp\":8,\"hp_max\":8,\"ataque\":7,\"defesa\":1,\"descricao\":\"Mantém distância e atira com precisão\"}]</BATTLE>\n\n"
        "De trás das pedras saltam duas criaturas esverdeadas! Role iniciativa!\n"
        "O que vocês fazem neste turno?",

        "<ENDBATTLE/>\n\nCom o último goblin caído, a claridade da floresta retorna. "
        "Nos bolsos da criatura, vocês encontram uma chave enferrujada e uma nota cifrada.\n"
        "<PUZZLE>{\"titulo\":\"Nota Cifrada\",\"pistas\":[\"Símbolo de olho no canto\",\"Texto em língua desconhecida\"]}</PUZZLE>\n"
        "O que fazem a seguir?",
    ]
    idx = len([m for m in historico if m["role"] == "user"]) % len(respostas)
    return respostas[idx]


# ─────────────────────────────────────────────────────────────────────────────
# BOLHA DE MENSAGEM
# ─────────────────────────────────────────────────────────────────────────────

class MessageBubble:
    PADDING = 10

    def __init__(self, role: str, content: str, bubble_max_w: int = 560):
        self.role    = role
        self.content = content
        self.max_w   = bubble_max_w
        self.lines   = self._wrap(content)
        lh = FONTE_PEQUENA.get_linesize() + 2
        self.height  = len(self.lines) * lh + self.PADDING * 2 + FONTE_MICRO.get_linesize() + 4

    def _wrap(self, text: str) -> list[str]:
        result = []
        inner_w = self.max_w - self.PADDING * 2
        for raw in text.split("\n"):
            words, line = raw.split(" "), ""
            for w in words:
                test = (line + " " + w).strip()
                if FONTE_PEQUENA.size(test)[0] <= inner_w:
                    line = test
                else:
                    if line: result.append(line)
                    line = w
            result.append(line)
        return result

    def draw(self, surf: pygame.Surface, x: int, y: int, panel_w: int):
        is_user = (self.role == "user")
        bw      = min(panel_w - 20, self.max_w)
        bx      = (panel_w - bw - 8) if is_user else 8
        bg_col  = (42, 32, 55) if is_user else (20, 32, 48)
        bdr_col = ROXO_XP     if is_user else AZUL_MANA

        box = pygame.Rect(bx + x, y, bw, self.height)
        pygame.draw.rect(surf, bg_col,  box, border_radius=8)
        pygame.draw.rect(surf, bdr_col, box, width=1, border_radius=8)

        lbl = FONTE_MICRO.render("Você" if is_user else "Narrador", True, bdr_col)
        surf.blit(lbl, (bx + x + self.PADDING, y + 5))

        lh = FONTE_PEQUENA.get_linesize() + 2
        ty = y + 5 + FONTE_MICRO.get_linesize() + 4
        for line in self.lines:
            ts = FONTE_PEQUENA.render(line, True, BRANCO)
            surf.blit(ts, (bx + x + self.PADDING, ty))
            ty += lh


# ─────────────────────────────────────────────────────────────────────────────
# ESTADO DO MODO HISTÓRIA
# ─────────────────────────────────────────────────────────────────────────────

TAB_NAMES = ["Fichas", "Inventário", "Missões", "Batalha", "Notas"]
TAB_COLORS = [
    (40, 90, 180),   # azul – Fichas
    (60, 130, 60),   # verde – Inventário
    (160, 120, 30),  # dourado – Missões
    (160, 40, 40),   # vermelho – Batalha
    (80, 60, 120),   # roxo – Notas
]


class StoryMode:

    def __init__(self, game):
        self.game      = game
        self.view_mode = "STORY_LIST"

        # ── Dados da sessão ──────────────────────────────────────────────
        self.story_ativo          : dict | None      = None
        self.personagens_ativo    : list[dict]       = []
        self.system_prompt        : str              = ""
        self.bubbles              : list[MessageBubble] = []
        self.is_waiting           : bool             = False
        self._typing_t            : float            = time.time()
        self._typing_dots         : int              = 0
        self._last_save_t         : float | None     = None   # hora do último auto-save
        # ── Painel lateral: estado ───────────────────────────────────────
        self.sidebar_tab          : int              = 0   # índice de TAB_NAMES
        self.missoes              : list[dict]       = []  # {nome, descricao, status}
        self.batalha_inimigos     : list[dict]       = []  # lista de inimigos ativos
        self.puzzle_notas         : list[dict]       = []  # {titulo, pistas}

        # ── STORY_NEW: dados temporários ─────────────────────────────────
        self.char_checks          : list[dict] = []
        self.story_cards          : list[dict] = []
        self._scroll_new          : int        = 0
        self._story_concluida_id  : int | None = None  # id marcado para encerramento
        # Rects dos botões de ação rápida do painel Batalha.
        # Populados a cada frame em _draw_tab_batalha; lidos em _ev_play.
        self._battle_action_rects : list[dict] = []
        # Loot pendente: itens encontrados que o jogador ainda não pegou/ignorou.
        # Exibidos no painel Inventário; rects populados em _draw_tab_inventario.
        self.loot_pendente        : list[dict] = []  # [{personagem_id, item}]
        self._loot_rects          : list[dict] = []  # [{rect, action, idx}]
        # Widgets criados em rebuild()
        self.rebuild(game.sw, game.sh)

    # ─────────────────────────────────────────────────────────────────────
    # LAYOUT RESPONSIVO
    # ─────────────────────────────────────────────────────────────────────

    def rebuild(self, w: int, h: int):
        """Recria todos os widgets com base nas dimensões (w, h)."""
        self.sw, self.sh = w, h
        PAD = 10

        # ── Botões globais ───────────────────────────────────────────────
        self.btn_voltar_menu  = Button(PAD, h - 58, 190, 44, "< Início",   color=CINZA_ESCURO)
        self.btn_voltar_lista = Button(PAD, h - 58, 190, 44, "< Voltar",   color=CINZA_ESCURO)
        self.btn_nova_hist    = Button(w - 240 - PAD, h - 58, 240, 44,
                                       "+ Nova Campanha", color=(34, 100, 34))

        # ── STORY_LIST ───────────────────────────────────────────────────
        self.ca_list = ContentArea(PAD, 70, w - PAD * 2, h - 140)

        # ── STORY_NEW ───────────────────────────────────────────────────
        fx = PAD * 2 + 4
        fw = w - fx * 2
        self.input_titulo    = TextInput(fx, 106, fw, 40)
        self.input_descricao = MultilineTextInput(fx, 200, fw, 80)
        self.input_missao    = MultilineTextInput(fx, 332, fw, 80)
        self.ca_chars_new    = ContentArea(fx, 464, fw, max(60, h - 530))
        self.btn_iniciar     = Button(w - 230 - PAD, h - 58, 230, 44,
                                       "Iniciar Campanha", color=(34, 100, 34))
        self.btn_cancel_new  = Button(PAD, h - 58, 190, 44, "Cancelar",
                                       color=VERMELHO_SANGUE)

        # ── STORY_PLAY ─────────────────────────────────────────────────
        split_x    = int(w * CHAT_SPLIT)
        chat_w     = split_x - PAD - 5
        sidebar_x  = split_x + 5
        sidebar_w  = w - sidebar_x - PAD

        # Área de chat (rolável)
        self.chat_area = ContentArea(PAD, 66, chat_w, h - 66 - 96)

        # Input e botão Enviar
        input_w = chat_w - 80
        self.input_msg  = MultilineTextInput(PAD, h - 88, input_w, 70)
        self.btn_enviar = Button(PAD + input_w + 8, h - 88, chat_w - input_w - 8, 70,
                                  "Enviar", color=(34, 100, 34))

        # Botão de sair da história (cabeçalho do chat)
        self.btn_sair_historia = Button(chat_w - 186, 12, 180, 40,
                                         "Sair da História", color=CINZA_ESCURO)

        # Sidebar tabs
        tab_w = sidebar_w // len(TAB_NAMES)
        self.tab_btns: list[Button] = []
        for i, name in enumerate(TAB_NAMES):
            self.tab_btns.append(
                Button(sidebar_x + i * tab_w, 66, tab_w, 30, name,
                       font=FONTE_MICRO, color=CINZA_ESCURO)
            )

        # Sidebar ContentArea (abaixo dos tabs)
        self.ca_sidebar = ContentArea(sidebar_x, 100, sidebar_w, h - 110)

        # Guarda dimensões para uso em draw
        self._sidebar_x = sidebar_x
        self._sidebar_w = sidebar_w
        self._chat_w    = chat_w

        # Reconstrói lista de stories (mantém dados, reseta botões)
        self._carregar_stories()

    # ─────────────────────────────────────────────────────────────────────
    # STORY_LIST
    # ─────────────────────────────────────────────────────────────────────

    def _carregar_stories(self):
        self.story_cards.clear()
        PAD = 10
        y = 10
        for s in load_stories():
            btn = Button(PAD, y, self.sw - PAD * 2 - 10, 72, "", color=(28, 28, 36))
            self.story_cards.append({"dados": s, "btn": btn, "y": y})
            y += 82

    # ─────────────────────────────────────────────────────────────────────
    # STORY_NEW
    # ─────────────────────────────────────────────────────────────────────

    def _abrir_nova(self, prefill_missao: str = "", prefill_titulo: str = ""):
        self.char_checks.clear()
        for c in load_characters():
            self.char_checks.append({"dados": c, "selecionado": False})
        self.input_titulo.text    = prefill_titulo
        self.input_descricao.text = ""
        self.input_missao.text    = prefill_missao
        self.view_mode = "STORY_NEW"

    def _iniciar_campanha(self):
        titulo           = self.input_titulo.text.strip() or "Sem Título"
        descricao        = self.input_descricao.text.strip()
        missao_principal = self.input_missao.text.strip()
        selecionados     = [c["dados"] for c in self.char_checks if c["selecionado"]]
        if not selecionados:
            return
        story_id = save_story(titulo, descricao, [],
                              [c["id"] for c in selecionados],
                              missao_principal)
        self._carregar_stories()
        self._iniciar_play(story_id, selecionados, descricao, [], titulo, missao_principal)

    # ─────────────────────────────────────────────────────────────────────
    # STORY_PLAY – Abertura / Continuação
    # ─────────────────────────────────────────────────────────────────────

    def _iniciar_play(self, story_id: int, personagens: list[dict],
                      descricao: str, tags: list[str],
                      titulo: str = "", missao_principal: str = ""):
        self.story_ativo       = {"id": story_id, "titulo": titulo}
        self.personagens_ativo = personagens
        self.system_prompt     = _build_system_prompt(
            personagens, descricao, tags, missao_principal)
        self.bubbles.clear()
        self.missoes.clear()
        self.batalha_inimigos.clear()
        self.puzzle_notas.clear()
        self.loot_pendente.clear()
        self._loot_rects.clear()
        self.sidebar_tab = 0
        self.chat_area.scroll_y = 0

        historico = get_story_chat(story_id)
        for m in historico:
            self.bubbles.append(MessageBubble(m["role"], m["content"],
                                              bubble_max_w=self._chat_w - 20))
        if not historico:
            if missao_principal:
                _prompt_inicial = (
                    f"Inicie a aventura. Missão: '{missao_principal}'. "
                    "Crie uma cena de abertura imersiva que contextualize esta missão — "
                    "descreva o local, o que está em jogo e o primeiro gancho narrativo. "
                    "Termine com uma escolha ou ação para o jogador. "
                    "Use <QUEST> para registrar a missão e <MUSIC> para a trilha."
                )
            else:
                _prompt_inicial = (
                    "Inicie a aventura do zero: invente um cenário e missão únicos baseados "
                    "nos personagens listados acima. Crie uma cena de abertura com: "
                    "(1) local específico e atmosférico, "
                    "(2) uma crise ou ameaça imediata que envolva os personagens pessoalmente, "
                    "(3) um NPC ou pista para o primeiro objetivo. "
                    "Registre via <QUEST>, defina trilha com <MUSIC>. "
                    "Termine pedindo a ação do jogador."
                )
            self._enviar_para_ia(_prompt_inicial)

        self.view_mode = "STORY_PLAY"
        self._atualizar_chat_height()

    def _continuar_campanha(self, story_dict: dict):
        chars_ids   = story_dict.get("personagem_ids", [])
        all_chars   = {c["id"]: c for c in load_characters()}
        personagens = [all_chars[i] for i in chars_ids if i in all_chars]
        self._iniciar_play(story_dict["id"], personagens,
                           story_dict.get("descricao", ""),
                           story_dict.get("tags", []),
                           story_dict.get("titulo", ""),
                           story_dict.get("missao_principal", ""))

    def _replay_campanha(self, story_dict: dict):
        """Cria nova campanha com a mesma missão principal, histórico zerado."""
        missao   = story_dict.get("missao_principal", "")
        titulo   = story_dict.get("titulo", "Sem Título") + " (Nova Corrida)"
        self._abrir_nova(prefill_missao=missao, prefill_titulo=titulo)

    # ─────────────────────────────────────────────────────────────────────
    # CHAT
    # ─────────────────────────────────────────────────────────────────────

    def _enviar_mensagem(self):
        msg = self.input_msg.text.strip()
        if not msg or self.is_waiting:
            return
        self.input_msg.text       = ""
        self.input_msg.cursor_pos = 0
        self.bubbles.append(MessageBubble("user", msg, bubble_max_w=self._chat_w - 20))
        append_chat_message(self.story_ativo["id"], "user", msg)
        self._last_save_t = time.time()
        self._atualizar_chat_height()
        self.is_waiting    = True
        self._typing_dots  = 0
        self._typing_t     = time.time()
        historico = get_story_chat(self.story_ativo["id"])
        threading.Thread(target=self._resposta_ia, args=(historico,), daemon=True).start()

    def _enviar_para_ia(self, msg_sistema: str):
        self.is_waiting   = True
        self._typing_dots = 0
        self._typing_t    = time.time()
        threading.Thread(
            target=self._resposta_ia,
            args=([{"role": "user", "content": msg_sistema}],),
            daemon=True,
        ).start()

    def _resposta_ia(self, historico: list[dict]):
        texto = _chamar_groq(historico, self.system_prompt)
        texto_limpo = self._processar_tags(texto)
        self.bubbles.append(MessageBubble("assistant", texto_limpo,
                                          bubble_max_w=self._chat_w - 20))
        append_chat_message(self.story_ativo["id"], "assistant", texto_limpo)
        self._last_save_t = time.time()
        self._atualizar_chat_height()
        self.is_waiting = False

    def _processar_tags(self, texto: str) -> str:
        """
        Lê a resposta bruta da IA, aplica todos os efeitos de jogo
        (música, sfx, estado de batalha, missões, etc.) e devolve
        o texto limpo (sem tags) para exibição nas bolhas de chat.

        Ordem de processamento:
          1. MUSIC   – troca trilha de fundo
          2. SFX     – efeito sonoro one-shot
          3. AMBIENT – som ambiente em loop
          4. BATTLE  – inicia inimigos no painel Batalha
          5. ENDBATTLE – encerra combate (fanfarra)
          6. UPDATE  – evolução de personagem (level-up sfx)
          7. QUEST   – adiciona/atualiza missão
          8. PUZZLE  – adiciona pistas de investigação
          9. ENDSTORY – encerra a campanha
        """

        # ── 1. MUSIC ─────────────────────────────────────────────────────
        # A IA inclui <MUSIC>clima</MUSIC> para sinalizar troca de trilha.
        # A troca usa _play_if_different() via game para não reiniciar a mesma música.
        for mood in re.findall(r"<MUSIC>(.*?)</MUSIC>", texto):
            mood    = mood.strip().lower()
            arquivo = MUSIC_MAP.get(mood, MUSIC_STORY)
            # Atualiza o tracker central para evitar reinício desnecessário
            if arquivo != self.game._current_music:
                self.game._current_music = arquivo
                play_music(arquivo)

        # ── 2. SFX ───────────────────────────────────────────────────────
        # <SFX>nome</SFX> – efeito sonoro one-shot.
        # Consulte SFX_MAP em settings.py para a lista completa de nomes.
        for sfx_nome in re.findall(r"<SFX>(.*?)</SFX>", texto):
            sfx_nome = sfx_nome.strip().lower()
            caminho  = SFX_MAP.get(sfx_nome)
            if caminho and sfx_nome not in SFX_AMBIENT_NAMES:
                play_sfx(caminho)

        # ── 3. AMBIENT ───────────────────────────────────────────────────
        # <AMBIENT>chuva</AMBIENT> – inicia loop no canal 1.
        # <AMBIENT>stop</AMBIENT>  – para o loop.
        for amb in re.findall(r"<AMBIENT>(.*?)</AMBIENT>", texto):
            amb = amb.strip().lower()
            if amb == "stop":
                stop_sfx_ambient()
            else:
                caminho = SFX_MAP.get(amb)
                if caminho:
                    play_sfx_ambient(caminho)

        # ── 4. BATTLE ────────────────────────────────────────────────────
        # <BATTLE>[{nome,hp,hp_max,ataque,defesa,descricao}]</BATTLE>
        # Popula a lista de inimigos e muda para o painel Batalha.
        for raw in re.findall(r"<BATTLE>(.*?)</BATTLE>", texto, re.DOTALL):
            try:
                self.batalha_inimigos = json.loads(raw)
                self.sidebar_tab = TAB_NAMES.index("Batalha")
                # Som de início de combate: golpe de arma
                play_sfx(SFX_WEAPON_ATTACK)
            except Exception:
                pass

        # ── 4b. DMGENEMY ────────────────────────────────────────────────
        # <DMGENEMY idx="0" dmg="7"/> – aplica dano ao inimigo na posição idx.
        # Permite atualizar a barra de HP em tempo real sem reenviar a lista completa.
        for m in re.finditer(r'<DMGENEMY\s+idx=["\']?(\d+)["\']?\s+dmg=["\']?(\d+)["\']?\s*/?>', texto):
            try:
                idx = int(m.group(1))
                dmg = int(m.group(2))
                if 0 <= idx < len(self.batalha_inimigos):
                    inimigo = self.batalha_inimigos[idx]
                    inimigo["hp"] = max(0, inimigo.get("hp", 0) - dmg)
                    # Som de dano ao inimigo
                    play_sfx(SFX_HURT)
            except Exception:
                pass

        # Remove inimigos com HP zerado da lista após processar todos os danos.
        # Isso garante que inimigos mortós desapareçam do painel Batalha mesmo que
        # a IA não envie <ENDBATTLE/> manualmente.
        havia_inimigos = bool(self.batalha_inimigos)
        self.batalha_inimigos = [e for e in self.batalha_inimigos if e.get("hp", 0) > 0]
        # Se todos morreram sem tag <ENDBATTLE/>, toca a fanfarra de vitória já
        if havia_inimigos and not self.batalha_inimigos:
            if not re.search(r"<ENDBATTLE\s*/>", texto):
                play_sfx(SFX_BATTLE_WIN)

        # ── 5. ENDBATTLE ─────────────────────────────────────────────────
        # <ENDBATTLE/> – limpa a lista de inimigos e toca fanfarra de vitória.
        if re.search(r"<ENDBATTLE\s*/>", texto):
            self.batalha_inimigos.clear()
            play_sfx(SFX_BATTLE_WIN)

        # ── 5c. LOOT ─────────────────────────────────────────────────────
        # <LOOT>{"personagem_id":N, "itens":[{...}]}</LOOT>
        # Ou lista direta [...] → atribui ao 1º personagem.
        for raw in re.findall(r"<LOOT>(.*?)</LOOT>", texto, re.DOTALL):
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    pid   = self.personagens_ativo[0]["id"] if self.personagens_ativo else None
                    itens = data
                else:
                    pid   = data.get("personagem_id")
                    if pid is None and self.personagens_ativo:
                        pid = self.personagens_ativo[0]["id"]
                    # Garante que o pid seja int para bater com c["id"] no banco
                    try:
                        pid = int(pid) if pid is not None else None
                    except (ValueError, TypeError):
                        pid = self.personagens_ativo[0]["id"] if self.personagens_ativo else None
                    itens = data.get("itens", [])
                for item in itens:
                    self.loot_pendente.append({"personagem_id": pid, "item": item})
                if self.loot_pendente:
                    self.sidebar_tab = TAB_NAMES.index("Inventário")
            except Exception:
                pass

        # ── 6. UPDATE ────────────────────────────────────────────────────
        # <UPDATE>{"personagem_id":N, "status":{...}}</UPDATE>
        # Persiste alterações no personagem; toca level_up se o nível subiu.
        for u in re.findall(r"<UPDATE>(.*?)</UPDATE>", texto, re.DOTALL):
            try:
                patch = json.loads(u)
                pid   = patch.pop("personagem_id", None)
                if pid is not None:
                    # Garante tipo int para bater com c["id"] no banco de dados
                    try:
                        pid = int(pid)
                    except (ValueError, TypeError):
                        pid = None
                if pid:
                    # Verifica se houve subida de nível para tocar o sfx.
                    # IMPORTANTE: só toca o som se o novo nível for MAIOR que o atual;
                    # isso evita disparar SFX_LEVEL_UP em todo UPDATE que simplesmente
                    # inclui o campo "nivel" sem modificá-lo (e.g. dano ou cura).
                    novo_nivel = (patch.get("status") or {}).get("nivel")
                    if novo_nivel is not None:
                        char_atual  = next(
                            (c for c in load_characters() if c["id"] == pid), None
                        )
                        nivel_atual = (
                            (char_atual.get("status") or {}).get("nivel", 1)
                            if char_atual else 1
                        )
                        if int(novo_nivel) > int(nivel_atual):
                            play_sfx(SFX_LEVEL_UP)
                    update_character_after_session(pid, patch)
            except Exception:
                pass

        # ── 7. QUEST ─────────────────────────────────────────────────────
        # <QUEST>{"nome":"...","descricao":"...","status":"Ativa"}</QUEST>
        # Adiciona nova missão ou atualiza existente no diário.
        for raw in re.findall(r"<QUEST>(.*?)</QUEST>", texto, re.DOTALL):
            try:
                q        = json.loads(raw)
                existing = next(
                    (m for m in self.missoes if m.get("nome") == q.get("nome")), None
                )
                if existing:
                    existing.update(q)
                else:
                    self.missoes.append(q)
            except Exception:
                pass

        # ── 8. PUZZLE ────────────────────────────────────────────────────
        # <PUZZLE>{"titulo":"...","pistas":["..."]}</PUZZLE>
        # Acumula pistas de investigação no painel Notas.
        for raw in re.findall(r"<PUZZLE>(.*?)</PUZZLE>", texto, re.DOTALL):
            try:
                p        = json.loads(raw)
                existing = next(
                    (n for n in self.puzzle_notas if n.get("titulo") == p.get("titulo")), None
                )
                if existing:
                    # Merge sem duplicar pistas
                    for pista in p.get("pistas", []):
                        if pista not in existing["pistas"]:
                            existing["pistas"].append(pista)
                else:
                    self.puzzle_notas.append(p)
                    if len(self.puzzle_notas) == 1:
                        self.sidebar_tab = TAB_NAMES.index("Notas")
            except Exception:
                pass

        # ── 9. ENDSTORY ──────────────────────────────────────────────────
        # <ENDSTORY reason="..."/> – marca a campanha como concluída.
        # Para o som ambiente, troca para trilha de encerramento.
        end_match = re.search(r'<ENDSTORY\s*reason="([^"]*)"\/>', texto)
        if end_match:
            conclusao = end_match.group(1)
            if self.story_ativo:
                complete_story(self.story_ativo["id"], conclusao)
                self._story_concluida_id = self.story_ativo["id"]
            stop_sfx_ambient()                   # silencia chuva/vento/etc.
            play_music(MUSIC_END)
            self.game._current_music = MUSIC_END
            self._carregar_stories()

        # ── Limpeza: remove TODAS as tags do texto antes de exibir ───────
        limpo = re.sub(
            r"<UPDATE>.*?</UPDATE>"
            r"|<BATTLE>.*?</BATTLE>"
            r"|<ENDBATTLE\s*/>"
            r"|<QUEST>.*?</QUEST>"
            r"|<PUZZLE>.*?</PUZZLE>"
            r"|<MUSIC>.*?</MUSIC>"
            r"|<SFX>.*?</SFX>"
            r"|<AMBIENT>.*?</AMBIENT>"
            r"|<DMGENEMY[^/]*/>"
            r"|<ENDSTORY[^/]*/>" ,
            "", texto, flags=re.DOTALL,
        ).strip()
        return limpo

    def _atualizar_chat_height(self):
        total = 20
        for b in self.bubbles:
            total += b.height + 10
        self.chat_area.content_height = max(self.chat_area.rect.height, total + 40)
        self.chat_area.scroll_y = max(0, self.chat_area.content_height - self.chat_area.rect.height)

    # ─────────────────────────────────────────────────────────────────────
    # EVENTOS
    # ─────────────────────────────────────────────────────────────────────

    def events(self, event) -> str | None:
        """
        Roteamento de eventos para o sub-state ativo.

        Retorna "MENU" quando o usuário clica em Voltar ao Mênius, senão None.
        Deve ser chamado a cada frame pelo Game loop.
        """
        if self.view_mode == "STORY_LIST":
            return self._ev_lista(event)
        elif self.view_mode == "STORY_NEW":
            return self._ev_nova(event)
        elif self.view_mode == "STORY_PLAY":
            return self._ev_play(event)

    def _ev_lista(self, event):
        """
        Eventos da tela de lista de campanhas.

        Gerência:
          - Scroll da ContentArea de cards.
          - Botão 'Voltar ao Menu'.
          - Botão '+ Nova Campanha'.
          - Cliques nos cards de história (continuar) e botões de exclusão.
        """
        self.ca_list.handle_event(event)
        adj = self.ca_list.get_adjusted_event(event)
        ev  = adj if adj else event

        if self.btn_voltar_menu.handle_event(event):
            return "MENU"
        # btn_nova_hist está fora do ContentArea (posição absoluta) → usa event cru
        if self.btn_nova_hist.handle_event(event):
            self._abrir_nova()
            return None
        # Cliques dentro das story cards (event ajustado pela ContentArea)
        if ev:
            for sc in self.story_cards:
                if sc["btn"].handle_event(ev):
                    if sc["dados"].get("concluida"):
                        # Clicou num card concluído: verifica se foi no botão replay
                        replay_r = sc.get("btn_replay_rect")
                        if replay_r and replay_r.collidepoint(
                                event.pos[0],
                                event.pos[1] + self.ca_list.scroll_y):
                            self._replay_campanha(sc["dados"])
                        else:
                            self._continuar_campanha(sc["dados"])
                    else:
                        self._continuar_campanha(sc["dados"])
                    return None
        return None

    def _ev_nova(self, event):
        """
        Eventos da tela de criação de campanha.

        Gerência:
          - Botão 'Cancelar' (volta para a lista).
          - Botão 'Iniciar Campanha' (dispara _iniciar_campanha).
          - Scroll/inputs dos campos de texto.
          - Scroll do seletor de personagens (ContentArea).
          - Seleção/desseleção de personagens por clique.
        """
        if self.btn_cancel_new.handle_event(event):
            self.view_mode = "STORY_LIST"
            return None
        if self.btn_iniciar.handle_event(event):
            self._iniciar_campanha()
            return None

        self.ca_chars_new.handle_event(event)
        adj = self.ca_chars_new.get_adjusted_event(event)

        # Clique em checkbox de personagem
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for cc in self.char_checks:
                r = cc.get("btn_rect")
                if r and r.collidepoint(event.pos):
                    cc["selecionado"] = not cc["selecionado"]
                    return None

        # Inputs de texto
        if event.type != pygame.MOUSEWHEEL:
            self.input_titulo.handle_event(event)
            self.input_descricao.handle_event(event)
            self.input_missao.handle_event(event)
        return None

    def _ev_play(self, event):
        """
        Eventos da tela de jogo (STORY_PLAY).

        Gerência:
          - Botão 'Sair da História' (volta para a lista, auto-save já ocorreu).
          - Cliques nas abas do sidebar.
          - Scroll da área de chat.
          - Input de texto do jogador (TEXTINPUT, KEYDOWN).
          - Botão 'Enviar' ou Enter para submeter mensagem à IA.
          - Cliques nos botões de ação rápida de batalha (_battle_action_rects).
          - Cliques em 'Pegar'/'Ignorar' dos itens de loot (_loot_rects).
          - Cliques no botão de exclusão de missão/nota.
        """
        if self.btn_sair_historia.handle_event(event):
            # Auto-save já ocorre em cada mensagem; apenas volta à lista
            self.view_mode = "STORY_LIST"
            return None

        # Tabs do sidebar
        for i, tb in enumerate(self.tab_btns):
            if tb.handle_event(event):
                self.sidebar_tab = i
                return None

        # Botões de loot no painel Inventário
        if (self.sidebar_tab == TAB_NAMES.index("Inventário")
                and self.loot_pendente
                and event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1):
            adj_sb = self.ca_sidebar.get_adjusted_event(event)
            if adj_sb:
                to_remove = None
                for lr in self._loot_rects:
                    if lr["rect"].collidepoint(adj_sb.pos):
                        idx = lr["idx"]
                        if 0 <= idx < len(self.loot_pendente):
                            entry = self.loot_pendente[idx]
                            if lr["action"] == "pegar":
                                pid = entry.get("personagem_id")
                                if pid:
                                    # Cast para int: a tag JSON pode retornar string
                                    try:
                                        pid = int(pid)
                                    except (ValueError, TypeError):
                                        pass
                                    update_character_after_session(
                                        pid, {"adicionar_inventario": [entry["item"]]}
                                    )
                                    play_sfx(SFX_SELECT)
                            to_remove = idx
                        break
                if to_remove is not None:
                    self.loot_pendente.pop(to_remove)
                    self._loot_rects.clear()
                return None

        # Botões de ação rápida do painel Batalha
        # Clicando em um botão, o texto correspondente é inserido no input de mensagem.
        if (self.sidebar_tab == TAB_NAMES.index("Batalha")
                and self.batalha_inimigos
                and event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1):
            adj_sb = self.ca_sidebar.get_adjusted_event(event)
            if adj_sb:
                for act in self._battle_action_rects:
                    if act["rect"].collidepoint(adj_sb.pos):
                        self.input_msg.text = act["text"]
                        self.input_msg.is_active = True
                        return None

        # Scroll: chat vs input
        if event.type == pygame.MOUSEWHEEL:
            if self.input_msg.is_active:
                self.input_msg.handle_event(event)
            elif self.ca_sidebar.rect.collidepoint(pygame.mouse.get_pos()):
                self.ca_sidebar.handle_event(event)
            else:
                self.chat_area.handle_event(event)
            return None

        self.chat_area.handle_event(event)
        self.ca_sidebar.handle_event(event)
        self.input_msg.handle_event(event)

        if self.btn_enviar.handle_event(event):
            self._enviar_mensagem()
            return None

        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            if not (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                self._enviar_mensagem()
        return None

    # ─────────────────────────────────────────────────────────────────────
    # DRAW
    # ─────────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface):
        """
        Renderiza o sub-state ativo (lista, nova campanha ou modo jogo).
        Chamado a cada frame pelo Game.draw().
        """
        surface.fill(PRETO)
        if self.view_mode == "STORY_LIST":
            self._draw_lista(surface)
        elif self.view_mode == "STORY_NEW":
            self._draw_nova(surface)
        elif self.view_mode == "STORY_PLAY":
            self._draw_play(surface)

    # ── Lista ─────────────────────────────────────────────────────────────

    def _draw_lista(self, surface: pygame.Surface):
        """Renderiza a tela de listagem de campanhas salvas com cards clicáveis."""
        W = self.sw
        t = FONTE_TITULO.render("HISTÓRIAS", True, DOURADO)
        surface.blit(t, t.get_rect(center=(W // 2, 36)))

        self.btn_voltar_menu.draw(surface)
        self.btn_nova_hist.draw(surface)

        pygame.draw.rect(surface, (16, 16, 20), self.ca_list.rect, border_radius=12)
        pygame.draw.rect(surface, CINZA_ESCURO,  self.ca_list.rect, width=1, border_radius=12)

        def _inner_lista(cs: pygame.Surface):
            if not self.story_cards:
                msg = FONTE_TEXTO.render("Nenhuma campanha salva. Crie uma nova!", True, CINZA_CLARO)
                cs.blit(msg, (cs.get_width() // 2 - msg.get_width() // 2, 40))
                self.ca_list.content_height = self.ca_list.rect.height
                return

            all_c = {c["id"]: c for c in load_characters()}
            for sc in self.story_cards:
                sc["btn"].draw(cs)
                y   = sc["y"]
                d   = sc["dados"]
                concluida = d.get("concluida", False)

                # Título
                cor_nm = (150, 150, 155) if concluida else (DOURADO if sc["btn"].is_hovered else BRANCO)
                nm = FONTE_TEXTO.render(d.get("titulo", "?"), True, cor_nm)
                cs.blit(nm, (16, y + 6))

                # Badge CONCLUÍDA
                if concluida:
                    badge = FONTE_MICRO.render("[CONCLUÍDA]", True, VERDE_HP)
                    cs.blit(badge, (nm.get_width() + 24, y + 10))

                desc = d.get("descricao", "")[:80]
                if desc:
                    ds = FONTE_MICRO.render(desc, True, CINZA_CLARO)
                    cs.blit(ds, (16, y + 30))

                chars_ids = d.get("personagem_ids", [])
                nomes = ", ".join(all_c[i].get("nome","?") for i in chars_ids if i in all_c)
                if nomes:
                    ns = FONTE_MICRO.render(f"Personagens: {nomes}", True, AZUL_MANA)
                    cs.blit(ns, (16, y + 50))

                # Botão Jogar Novamente para histórias concluídas
                if concluida:
                    rw = self.sw - 40
                    replay_r = pygame.Rect(rw - 180, y + 4, 175, 30)
                    sc["btn_replay_rect"] = replay_r
                    pygame.draw.rect(cs, (34, 100, 34), replay_r, border_radius=5)
                    pygame.draw.rect(cs, VERDE_HP,      replay_r, width=1, border_radius=5)
                    rp_s = FONTE_MICRO.render("Jogar Novamente", True, BRANCO)
                    cs.blit(rp_s, rp_s.get_rect(center=replay_r.center))

            h = 10 + len(self.story_cards) * 82 + 20
            self.ca_list.content_height = max(self.ca_list.rect.height, h)

        self.ca_list.draw(surface, _inner_lista)

    # ── Nova Campanha ─────────────────────────────────────────────────────

    def _draw_nova(self, surface: pygame.Surface):
        """
        Renderiza o formulário de criação de nova campanha.

        Campos:
          - Título da Campanha (TextInput de linha única).
          - Tom / Ambientação (MultilineTextInput).
          - Missão Principal (MultilineTextInput com hint).
          - Seletor de Personagens (caixas de seleção com scroll).

        Botões fixos no rodapé: 'Iniciar Campanha' e 'Cancelar'.
        """
        W, H = self.sw, self.sh
        fx = 24; fw = W - fx * 2

        t = FONTE_SUBTITULO.render("NOVA CAMPANHA", True, DOURADO)
        surface.blit(t, t.get_rect(center=(W // 2, 36)))

        # Fundo do formulário
        form_rect = pygame.Rect(fx - 10, 66, fw + 20, H - 76)
        pygame.draw.rect(surface, (16, 16, 20), form_rect, border_radius=12)
        pygame.draw.rect(surface, CINZA_ESCURO,  form_rect, width=1, border_radius=12)

        # Título
        surface.blit(FONTE_TEXTO.render("Título da Campanha:", True, DOURADO), (fx, 82))
        self.input_titulo.draw(surface)

        # Descrição / Tom
        surface.blit(FONTE_TEXTO.render("Tom / Ambientação:", True, DOURADO), (fx, 158))
        self.input_descricao.draw(surface)

        # Missão Principal
        surface.blit(FONTE_TEXTO.render("Missão Principal (gancho narrativo):", True, DOURADO), (fx, 296))
        hint = FONTE_MICRO.render("Descreva o objetivo central — a IA criará o arco e 2-3 desfechos possíveis.", True, CINZA_MEDIO)
        surface.blit(hint, (fx, 318))
        self.input_missao.draw(surface)

        # Personagens
        surface.blit(FONTE_TEXTO.render("Selecionar Personagens:", True, DOURADO), (fx, 430))

        def _inner_chars(cs: pygame.Surface):
            if not self.char_checks:
                msg = FONTE_PEQUENA.render("Nenhum personagem criado ainda.", True, CINZA_MEDIO)
                cs.blit(msg, (10, 10))
                self.ca_chars_new.content_height = self.ca_chars_new.rect.height
                return
            y_c = 6
            for cc in self.char_checks:
                sel = cc["selecionado"]
                # Rect na tela real (para hit-test)
                cr_on_screen = pygame.Rect(fx, self.ca_chars_new.rect.y + y_c,
                                           fw, 38)
                cc["btn_rect"] = cr_on_screen
                # Rect dentro da surface do ContentArea
                cr = pygame.Rect(0, y_c, cs.get_width(), 38)
                bg = (45, 45, 55) if sel else (28, 28, 36)
                bd = DOURADO if sel else CINZA_MEDIO
                pygame.draw.rect(cs, bg, cr, border_radius=6)
                pygame.draw.rect(cs, bd, cr, width=1, border_radius=6)
                mark = "[X]" if sel else "[ ]"
                d    = cc["dados"]
                nm   = f"{mark}  {d.get('nome','?')} – {d.get('raca','?')} / {d.get('classe','?')}"
                ts   = FONTE_TEXTO.render(nm, True, BRANCO)
                cs.blit(ts, (10, y_c + (38 - ts.get_height()) // 2))
                y_c += 46
            self.ca_chars_new.content_height = max(self.ca_chars_new.rect.height, y_c + 10)

        self.ca_chars_new.draw(surface, _inner_chars)

        self.btn_iniciar.draw(surface)
        self.btn_cancel_new.draw(surface)

    # ── Play (tela de jogo) ───────────────────────────────────────────────

    def _draw_play(self, surface: pygame.Surface):
        """
        Renderiza a tela de jogo principal dividida em duas colunas:

          Esquerda (chat_w):
            - Cabeçalho com título da campanha e indicador de auto-save.
            - Área de chat com bolhas de mensagens (ContentArea com scroll).
            - Input de texto para o jogador.
            - Indicador de "IA digitando..." quando is_waiting=True.
            - Botão Voltar.

          Direita (sidebar_w):
            - Abas navegáveis: Fichas | Inventário | Missões | Batalha | Notas.
            - Conteúdo da aba ativa (renderizado em ContentArea com scroll).
        """
        W, H = self.sw, self.sh

        # ── Cabeçalho ─────────────────────────────────────────────────────────
        titulo_s = self.story_ativo.get("titulo", "MODO HISTÓRIA") if self.story_ativo else "MODO HISTÓRIA"
        t = FONTE_TEXTO.render(titulo_s.upper(), True, DOURADO)
        surface.blit(t, t.get_rect(center=(self._chat_w // 2, 38)))

        # Indicador de auto-save
        if self._last_save_t:
            import datetime
            hora = datetime.datetime.fromtimestamp(self._last_save_t).strftime("%H:%M")
            save_s = FONTE_MICRO.render(f"● salvo {hora}", True, VERDE_HP)
        else:
            save_s = FONTE_MICRO.render("● auto-save ativo", True, CINZA_MEDIO)
        surface.blit(save_s, (12, 52))

        self.btn_sair_historia.draw(surface)

        # ── Área de chat ──────────────────────────────────────────────────
        pygame.draw.rect(surface, (14, 14, 18), self.chat_area.rect, border_radius=8)
        pygame.draw.rect(surface, CINZA_ESCURO,  self.chat_area.rect, width=1, border_radius=8)

        def _inner_chat(cs: pygame.Surface):
            y = 10
            for b in self.bubbles:
                b.draw(cs, 0, y, cs.get_width())
                y += b.height + 8
            if self.is_waiting:
                if time.time() - self._typing_t > 0.4:
                    self._typing_dots = (self._typing_dots + 1) % 4
                    self._typing_t    = time.time()
                dots = "." * self._typing_dots
                dt = FONTE_PEQUENA.render(f"Narrador está escrevendo{dots}", True, CINZA_CLARO)
                cs.blit(dt, (12, y))

        self.chat_area.draw(surface, _inner_chat)

        # ── Input ─────────────────────────────────────────────────────────
        inp_bg = pygame.Rect(10, H - 92, self._chat_w, 78)
        pygame.draw.rect(surface, (18, 18, 24), inp_bg, border_radius=8)
        pygame.draw.rect(surface, CINZA_ESCURO,  inp_bg, width=1, border_radius=8)
        self.input_msg.draw(surface)
        self.btn_enviar.draw(surface)

        hint = FONTE_MICRO.render("Enter = enviar  |  Shift+Enter = nova linha", True, CINZA_MEDIO)
        surface.blit(hint, (12, H - hint.get_height() - 3))

        # ── Divisor vertical ──────────────────────────────────────────────
        pygame.draw.line(surface, CINZA_MEDIO,
                         (self._sidebar_x - 4, 66),
                         (self._sidebar_x - 4, H - 10), 1)

        # ── Tabs do painel lateral ────────────────────────────────────────
        for i, tb in enumerate(self.tab_btns):
            tb.color = TAB_COLORS[i] if i == self.sidebar_tab else CINZA_ESCURO
            tb.draw(surface)

        # ── Conteúdo do sidebar ───────────────────────────────────────────
        pygame.draw.rect(surface, (14, 14, 18), self.ca_sidebar.rect, border_radius=6)
        pygame.draw.rect(surface, CINZA_ESCURO,  self.ca_sidebar.rect, width=1, border_radius=6)
        sw = self._sidebar_w

        tab = self.sidebar_tab
        if tab == 0:
            self.ca_sidebar.draw(surface, lambda cs: self._draw_tab_fichas(cs, sw))
        elif tab == 1:
            self.ca_sidebar.draw(surface, lambda cs: self._draw_tab_inventario(cs, sw))
        elif tab == 2:
            self.ca_sidebar.draw(surface, lambda cs: self._draw_tab_missoes(cs, sw))
        elif tab == 3:
            self.ca_sidebar.draw(surface, lambda cs: self._draw_tab_batalha(cs, sw))
        elif tab == 4:
            self.ca_sidebar.draw(surface, lambda cs: self._draw_tab_notas(cs, sw))

    # ── Painel lateral: Fichas ─────────────────────────────────────────────

    def _draw_tab_fichas(self, cs: pygame.Surface, sw: int):
        """
        Aba 'Fichas': exibe um card compacto por personagem ativo mostrando
        barras de HP/MP/XP, atributos numéricos e título atual.
        Renderizado dentro de ca_sidebar (ContentArea com scroll).
        """
        y = 8
        if not self.personagens_ativo:
            s = FONTE_PEQUENA.render("Nenhum personagem ativo.", True, CINZA_CLARO)
            cs.blit(s, (10, y)); self.ca_sidebar.content_height = self.ca_sidebar.rect.height; return

        for p in self.personagens_ativo:
            sts  = p.get("status", {})
            atr  = p.get("atributos", {})
            hp   = sts.get("hp_atual",   sts.get("hp_maximo", 30))
            hpm  = sts.get("hp_maximo",  30)
            mp   = sts.get("mana_atual",  sts.get("mana_maximo", 10))
            mpm  = sts.get("mana_maximo", 10)
            xp   = sts.get("xp", 0)
            nivel= sts.get("nivel", 1)
            xp_max = nivel * 100

            # Card
            card_h = 160
            card = pygame.Rect(6, y, sw - 12, card_h)
            pygame.draw.rect(cs, (25, 25, 32), card, border_radius=8)
            pygame.draw.rect(cs, DOURADO_ESCURO, card, width=1, border_radius=8)

            # Nome + classe
            nm = FONTE_TEXTO.render(p.get("nome","?"), True, DOURADO)
            cs.blit(nm, (14, y + 6))
            cl = FONTE_MICRO.render(f"{p.get('raca','?')} / {p.get('classe','?')} • Nv {nivel}", True, CINZA_CLARO)
            cs.blit(cl, (14, y + 28))

            # Barras
            bx, bw = 14, sw - 28
            y_bar  = y + 48

            def _bar(label, val, maxi, col, yy):
                pct = _clamp(val / maxi, 0, 1) if maxi else 0
                s   = FONTE_MICRO.render(f"{label} {val}/{maxi}", True, col)
                cs.blit(s, (bx, yy))
                bg_r = pygame.Rect(bx, yy + 14, bw, 8)
                fg_r = pygame.Rect(bx, yy + 14, int(bw * pct), 8)
                pygame.draw.rect(cs, CINZA_MEDIO, bg_r, border_radius=4)
                if fg_r.width > 0:
                    pygame.draw.rect(cs, col, fg_r, border_radius=4)

            _bar("HP",  hp,  hpm,  VERDE_HP,  y_bar)
            _bar("MP",  mp,  mpm,  AZUL_MANA, y_bar + 26)
            _bar("XP",  xp,  xp_max, ROXO_XP, y_bar + 52)

            # Atributos compactos
            atr_items = [("FOR", atr.get("forca",10)), ("DES", atr.get("destreza",10)),
                         ("INT", atr.get("inteligencia",10)), ("CON", atr.get("constituicao",10)),
                         ("SAB", atr.get("sabedoria",10)),    ("CAR", atr.get("carisma",10))]
            ax, ay = bx, y_bar + 82
            col_w  = (sw - 20) // 6
            for label, val in atr_items:
                s = FONTE_MICRO.render(f"{label}\n{val}", True, CINZA_CLARO)
                s2= FONTE_MICRO.render(label, True, CINZA_CLARO)
                s3= FONTE_MICRO.render(str(val), True, BRANCO)
                cs.blit(s2, (ax, ay))
                cs.blit(s3, (ax, ay + 14))
                ax += col_w

            y += card_h + 10

        self.ca_sidebar.content_height = max(self.ca_sidebar.rect.height, y + 10)

    # ── Painel lateral: Inventário ────────────────────────────────────────

    def _draw_tab_inventario(self, cs: pygame.Surface, sw: int):
        """
        Aba 'Inventário': lista todos os itens de cada personagem ativo,
        com nome, efeito e barra de ataque/defesa.

        Loot pendente: exibe botões 'Pegar' e 'Ignorar' para itens oferecidos
        pela IA via tag <LOOT>. Os rects desses botões são guardados em
        self._loot_rects (lista de dicts com 'item', 'pid', 'b_pegar', 'b_ignorar')
        e lidos pelo handler _ev_play() para processar a escolha do jogador.
        """
        self._loot_rects.clear()  # reseta a cada frame
        y = 8
        if not self.personagens_ativo:
            cs.blit(FONTE_PEQUENA.render("Sem personagens ativos.", True, CINZA_CLARO), (10, y))
            self.ca_sidebar.content_height = self.ca_sidebar.rect.height; return

        for p in self.personagens_ativo:
            # Recarrega atributos frescos do disco para refletir UPDATEs
            from database import load_characters as _lc
            fresh = next((c for c in _lc() if c["id"] == p.get("id")), p)

            nm = FONTE_TEXTO.render(fresh.get("nome","?"), True, DOURADO)
            cs.blit(nm, (10, y)); y += nm.get_height() + 4

            inv = fresh.get("inventario", [])
            if not inv:
                s = FONTE_MICRO.render("– Inventário vazio –", True, CINZA_MEDIO)
                cs.blit(s, (16, y)); y += s.get_height() + 6
            for item in inv:
                nome_item = item["nome"] if isinstance(item, dict) else str(item)
                atq = item.get("ataque", 0) if isinstance(item, dict) else 0
                dfs = item.get("defesa", 0) if isinstance(item, dict) else 0
                card = pygame.Rect(8, y, sw - 16, 42)
                pygame.draw.rect(cs, (28, 28, 38), card, border_radius=5)
                pygame.draw.rect(cs, CINZA_MEDIO, card, width=1, border_radius=5)
                s = FONTE_PEQUENA.render(nome_item, True, BRANCO)
                cs.blit(s, (14, y + 5))
                stat = FONTE_MICRO.render(f"ATQ:{atq}  DEF:{dfs}", True, CINZA_CLARO)
                cs.blit(stat, (14, y + 24))
                y += 48

            y += 8
            pygame.draw.line(cs, CINZA_ESCURO, (8, y), (sw - 16, y)); y += 8

        # ── Loot pendente ────────────────────────────────────────────────
        if self.loot_pendente:
            hdr = FONTE_TEXTO.render("Itens Encontrados:", True, DOURADO)
            cs.blit(hdr, (10, y)); y += hdr.get_height() + 6

            for idx, entry in enumerate(self.loot_pendente):
                pid   = entry.get("personagem_id")
                item  = entry["item"]
                nm_i  = item.get("nome", "?")
                atq   = item.get("ataque", 0)
                dfs   = item.get("defesa", 0)
                ef    = (item.get("efeito_status") or "")[:34]
                char_label = ""
                if pid and len(self.personagens_ativo) > 1:
                    c = next((p for p in self.personagens_ativo if p["id"] == pid), None)
                    if c:
                        char_label = f"  [{c['nome']}]"

                card_h = 64
                card   = pygame.Rect(8, y, sw - 16, card_h)
                pygame.draw.rect(cs, (25, 45, 20), card, border_radius=6)
                pygame.draw.rect(cs, VERDE_HP,     card, width=1, border_radius=6)

                s1 = FONTE_PEQUENA.render(nm_i + char_label, True, BRANCO)
                cs.blit(s1, (14, y + 5))
                s2 = FONTE_MICRO.render(f"ATQ:{atq}  DEF:{dfs}  {ef}", True, CINZA_CLARO)
                cs.blit(s2, (14, y + 24))

                btn_pegar  = pygame.Rect(sw - 82,  y + 18, 68, 26)
                btn_ignora = pygame.Rect(sw - 158, y + 18, 68, 26)

                pygame.draw.rect(cs, (40, 110, 40), btn_pegar,  border_radius=5)
                pygame.draw.rect(cs, VERDE_HP,      btn_pegar,  width=1, border_radius=5)
                pygame.draw.rect(cs, (90, 30, 30),  btn_ignora, border_radius=5)
                pygame.draw.rect(cs, VERMELHO_SANGUE, btn_ignora, width=1, border_radius=5)

                tp = FONTE_MICRO.render("Pegar",   True, BRANCO)
                ti = FONTE_MICRO.render("Ignorar", True, BRANCO)
                cs.blit(tp, tp.get_rect(center=btn_pegar.center))
                cs.blit(ti, ti.get_rect(center=btn_ignora.center))

                self._loot_rects.append({"rect": btn_pegar,  "action": "pegar",   "idx": idx})
                self._loot_rects.append({"rect": btn_ignora, "action": "ignorar", "idx": idx})
                y += card_h + 6

        self.ca_sidebar.content_height = max(self.ca_sidebar.rect.height, y + 10)

    # ── Painel lateral: Missões ───────────────────────────────────────────

    def _draw_tab_missoes(self, cs: pygame.Surface, sw: int):
        """
        Aba 'Missões': exibe o diário de missões com badge colorido por status
        (Ativa=verde, Concluída=azul, Falhou=vermelho).
        Missões são adicionadas/atualizadas via tag <QUEST> na resposta da IA.
        """
        y = 8
        if not self.missoes:
            s = FONTE_PEQUENA.render("Nenhuma missão registrada.", True, CINZA_CLARO)
            cs.blit(s, (10, y)); self.ca_sidebar.content_height = self.ca_sidebar.rect.height; return

        status_cores = {"Ativa": VERDE_HP, "Concluída": AZUL_MANA, "Falhou": VERMELHO_SANGUE}
        for m in self.missoes:
            st  = m.get("status", "Ativa")
            col = status_cores.get(st, DOURADO)
            # Cabeçalho
            nm = FONTE_TEXTO.render(m.get("nome","?"), True, col)
            cs.blit(nm, (10, y)); y += nm.get_height() + 2
            # Status badge
            badge = FONTE_MICRO.render(f"[{st}]", True, col)
            cs.blit(badge, (10, y)); y += badge.get_height() + 3
            # Descrição com wrap
            desc = m.get("descricao","")
            for line in _wrap_text(desc, FONTE_MICRO, sw - 20):
                s = FONTE_MICRO.render(line, True, CINZA_CLARO)
                cs.blit(s, (10, y)); y += s.get_height() + 1
            y += 8
            pygame.draw.line(cs, CINZA_ESCURO, (8, y), (sw - 16, y)); y += 8

        self.ca_sidebar.content_height = max(self.ca_sidebar.rect.height, y + 10)

    # ── Painel lateral: Batalha ───────────────────────────────────────────

    def _draw_tab_batalha(self, cs: pygame.Surface, sw: int):
        """
        Exibe as barras de HP dos inimigos + botões de ação rápida.
        Os botões pre-preenchem o input de chat com a ação escolhida.
        Rects são armazenados em self._battle_action_rects para o handler de eventos.
        """
        y = 8
        self._battle_action_rects.clear()  # reseta a cada frame

        if not self.batalha_inimigos:
            s = FONTE_PEQUENA.render("Sem combate em andamento.", True, CINZA_CLARO)
            cs.blit(s, (10, y))
            self.ca_sidebar.content_height = self.ca_sidebar.rect.height
            return

        titulo = FONTE_TEXTO.render("-- COMBATE --", True, VERMELHO_SANGUE)
        cs.blit(titulo, (sw // 2 - titulo.get_width() // 2, y))
        y += titulo.get_height() + 6

        # ── Cards de inimigos ────────────────────────────────────────
        for inimigo in self.batalha_inimigos:
            hp  = inimigo.get("hp",    1)
            hpm = inimigo.get("hp_max", 1)
            atq = inimigo.get("ataque", 0)
            dfs = inimigo.get("defesa", 0)
            morto = hp <= 0

            card_h = 90
            card   = pygame.Rect(6, y, sw - 12, card_h)
            bg_col = (20, 10, 10) if morto else (40, 15, 15)
            bd_col = CINZA_MEDIO  if morto else VERMELHO_SANGUE
            pygame.draw.rect(cs, bg_col, card, border_radius=8)
            pygame.draw.rect(cs, bd_col, card, width=1, border_radius=8)

            # Nome (riscado se morto)
            nome_txt = inimigo.get("nome", "?")
            if morto:
                nome_txt = f"[MORTO] {nome_txt}"
            nm = FONTE_TEXTO.render(nome_txt, True, (100, 60, 60) if morto else (255, 100, 100))
            cs.blit(nm, (14, y + 6))

            # Barra de HP
            bx, bw = 14, sw - 28
            pct = _clamp(hp / hpm, 0, 1) if hpm else 0
            # Cor da barra: verde > amarelo > vermelho conforme HP
            if pct > 0.5:
                bar_col = VERDE_HP
            elif pct > 0.25:
                bar_col = (220, 180, 30)  # amarelo
            else:
                bar_col = VERMELHO_SANGUE
            hp_label = FONTE_MICRO.render(f"HP {hp}/{hpm}", True, bar_col)
            cs.blit(hp_label, (bx, y + 28))
            bg_r = pygame.Rect(bx, y + 42, bw, 8)
            fg_r = pygame.Rect(bx, y + 42, int(bw * pct), 8)
            pygame.draw.rect(cs, CINZA_MEIO, bg_r, border_radius=4)
            if fg_r.width > 0:
                pygame.draw.rect(cs, bar_col, fg_r, border_radius=4)

            # Atributos e descrição
            stats = FONTE_MICRO.render(f"ATQ: {atq}   DEF: {dfs}", True, CINZA_CLARO)
            cs.blit(stats, (bx, y + 54))
            desc = inimigo.get("descricao", "")[:50]
            if desc:
                ds = FONTE_MICRO.render(desc, True, (180, 140, 140))
                cs.blit(ds, (bx, y + 70))

            y += card_h + 8

        # ── Botões de ação rápida ───────────────────────────────────
        # Se ainda há inimigos vivos, mostra as opções de ação.
        # Clicar num botão pré-preenche o input de chat.
        vivos = [e for e in self.batalha_inimigos if e.get("hp", 1) > 0]
        if not vivos:
            self.ca_sidebar.content_height = max(self.ca_sidebar.rect.height, y + 10)
            return

        y += 4
        sep = FONTE_MICRO.render("--- AÇÕES DO TURNO ---", True, DOURADO)
        cs.blit(sep, (sw // 2 - sep.get_width() // 2, y))
        y += sep.get_height() + 6

        # Definição das ações disponíveis
        # Para Atacar: gera uma opção por inimigo vivo (até 3)
        acoes = []
        for inimigo in vivos[:3]:
            nome_i = inimigo.get("nome", "o inimigo")
            acoes.append({
                "label": f"⚔ Atacar {nome_i[:18]}",
                "text":  f"Ataco {nome_i} com minha arma principal!",
                "cor":   VERMELHO_SANGUE,
            })
        acoes += [
            {"label": "🛡 Defender",
             "text":  "Adoto postura defensiva, priorizando bloquear ataques neste turno.",
             "cor":   AZUL_MANA},
            {"label": "✨ Magia / Habilidade",
             "text":  "Uso uma das minhas magias ou habilidades especiais!",
             "cor":   ROXO_XP},
            {"label": "🎒 Usar Item",
             "text":  "Uso um item do meu inventário para me ajudar.",
             "cor":   (60, 130, 60)},
            {"label": "🔍 Inspecionar",
             "text":  "Inspeciono os inimigos em busca de fraquezas ou padrões de ataque.",
             "cor":   (100, 160, 180)},
            {"label": "🏃 Fugir",
             "text":  "Tento fugir do combate!",
             "cor":   CINZA_MEDIO},
        ]

        btn_h  = 28
        btn_gap = 4
        for acao in acoes:
            r = pygame.Rect(6, y, sw - 12, btn_h)
            # Destaque leve no hover (verifica posição do mouse ajustada)
            mx, my = pygame.mouse.get_pos()
            # Converte para coordenadas do ContentArea
            adj_mx = mx - self.ca_sidebar.rect.x
            adj_my = my - self.ca_sidebar.rect.y + self.ca_sidebar.scroll_y
            hovered = r.collidepoint(adj_mx, adj_my)
            bg = tuple(min(255, c + 30) for c in acao["cor"]) if hovered else tuple(max(0, c - 60) for c in acao["cor"])
            pygame.draw.rect(cs, bg, r, border_radius=5)
            pygame.draw.rect(cs, acao["cor"], r, width=1, border_radius=5)
            lbl = FONTE_MICRO.render(acao["label"], True, BRANCO)
            cs.blit(lbl, lbl.get_rect(center=r.center))
            # Registra o rect para o handler de eventos
            self._battle_action_rects.append({"rect": r, "text": acao["text"]})
            y += btn_h + btn_gap

        y += 6
        dica = FONTE_MICRO.render("Clique para pré-preencher o chat", True, CINZA_MEDIO)
        cs.blit(dica, (sw // 2 - dica.get_width() // 2, y))
        y += dica.get_height() + 8

        self.ca_sidebar.content_height = max(self.ca_sidebar.rect.height, y + 10)

    # ── Painel lateral: Notas / Puzzles ───────────────────────────────────

    def _draw_tab_notas(self, cs: pygame.Surface, sw: int):
        """
        Aba 'Notas': exibe pistas de invenção/puzzle organizadas por título.
        Cada nota contém uma lista de pistas descobertas, adicionadas via <PUZZLE>.
        """
        y = 8
        if not self.puzzle_notas:
            s = FONTE_PEQUENA.render("Nenhuma pista encontrada ainda.", True, CINZA_CLARO)
            cs.blit(s, (10, y)); self.ca_sidebar.content_height = self.ca_sidebar.rect.height; return

        for nota in self.puzzle_notas:
            titulo_s = FONTE_TEXTO.render(nota.get("titulo","?"), True, (180, 150, 255))
            cs.blit(titulo_s, (10, y)); y += titulo_s.get_height() + 4

            for pista in nota.get("pistas", []):
                bullet = FONTE_MICRO.render("• " + pista, True, CINZA_CLARO)
                for line in _wrap_text("• " + pista, FONTE_MICRO, sw - 20):
                    ls = FONTE_MICRO.render(line, True, CINZA_CLARO)
                    cs.blit(ls, (12, y)); y += ls.get_height() + 2

            y += 8
            pygame.draw.line(cs, CINZA_ESCURO, (8, y), (sw - 16, y)); y += 8

        self.ca_sidebar.content_height = max(self.ca_sidebar.rect.height, y + 10)


# ─────────────────────────────────────────────────────────────────────────────
# UTIL
# ─────────────────────────────────────────────────────────────────────────────

def _wrap_text(text: str, font: pygame.font.Font, max_w: int) -> list[str]:
    result = []
    for raw in text.split("\n"):
        words, line = raw.split(" "), ""
        for w in words:
            test = (line + " " + w).strip()
            if font.size(test)[0] <= max_w:
                line = test
            else:
                if line: result.append(line)
                line = w
        result.append(line)
    return result


# CINZA_MEDIO é importado de settings.py via `from settings import *`
# Definido aqui como alias para não depender do nome exato em settings.
CINZA_MEIO = CINZA_MEDIO
