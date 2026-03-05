"""
states/character_creation.py  –  Gerenciador de herois (lista/criacao/detalhe/edicao).

Regras de UX:
- Sem emojis (aparecem como "?" no Pygame).
- Raca e Classe sao campos de texto livres (sem dropdown).
- A IA (simulador agora, API real no futuro) deduz atributos, nivel,
  titulo com beneficio, equipamentos com ficha completa e habilidades.
- Edicao permite apenas renomear e trocar o titulo ativo.
"""

import pygame
import threading
import time
import os
import json
import re
from settings import *
from ui import Button, TextInput, draw_text_wrapped, MultilineTextInput, Dropdown, ContentArea
from database import (
    load_characters, save_character, delete_character,
    update_character_name_title,
)


# ────────────────────────────────────────────────────────────────────────────
# GERAÇÃO DE FICHA VIA IA
# Tenta a API do Groq; caso não haja chave ou ocorra erro, usa o gerador local.
# ────────────────────────────────────────────────────────────────────────────

def _chamar_groq_personagem(nome: str, raca: str, classe: str,
                            historia: str, api_key: str) -> dict:
    """Chama llama-3.3-70b-versatile e pede a ficha completa como JSON puro."""
    from groq import Groq

    historia_info = (
        f'História de origem: "{historia}"'
        if historia.strip()
        else
        "História de origem: (vazia — crie uma história de 2-3 frases temáticas "
        "condizentes com a raça e classe do personagem; retorne em historia_gerada)"
    )

    system_msg = (
        "Você é um gerador de fichas de RPG de mesa. "
        "Retorne APENAS JSON válido, sem texto extra, sem markdown, sem blocos de código."
    )
    user_msg = (
        f"Crie a ficha completa para:\n"
        f"Nome: {nome}\nRaça: {raca}\nClasse: {classe}\n{historia_info}\n\n"
        "Retorne exatamente neste formato JSON (apenas o objeto, sem nada além):\n"
        '{\n'
        '  "atributos": {"forca": int, "destreza": int, "inteligencia": int,'
        ' "constituicao": int, "sabedoria": int, "carisma": int},\n'
        '  "status": {"hp_maximo": int, "mana_maximo": int, "nivel": 1},\n'
        '  "titulo": {"nome": "str", "descricao": "str", "beneficio": "str"},\n'
        '  "historia_gerada": "str (vazio \"\" se já havia história; '
        'caso contrário a history criada)",\n'
        '  "inventario": [{"nome":"str","historia":"str","ataque":int,'
        '"defesa":int,"efeito_status":"str","resistencia":"str"}],\n'
        '  "habilidades": [{"nome":"str","custo":"str","efeito":"str","recarga":"str"}]\n'
        '}\n\n'
        "Regras (português brasileiro obrigatório):\n"
        "- Distribua exatamente 70 pontos entre os 6 atributos (mín 8, máx 18 cada).\n"
        "- HP = 20 + (constituicao // 2) * 5.  Mana = 10 + (inteligencia // 2) * 3.\n"
        "- Título: nome poético único, descrição narrativa (1 frase), benefício mecânico.\n"
        "- Inventário: 3-5 itens temáticos para raça+classe (arma principal, armadura/proteção,"
        " 1-2 itens especiais ou consumíveis).\n"
        "- Habilidades: 2-4 skills/magias condizentes com a classe, custos de mana balanceados.\n"
        "- historia_gerada: NÃO inclua se o jogador já escreveu uma história."
    )

    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.8,
        max_tokens=1200,
    )
    raw = resp.choices[0].message.content.strip()
    # Remove blocos de código Markdown que a IA ocasionalmente envolve o JSON.
    # Etapa 1: elimina qualquer marcador ``` com ou sem linguagem especificada.
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip()
    # Etapa 2 (fallback): extrai o objeto JSON mais externo da string,
    # cobrindo casos onde a IA acrescenta texto explicativo antes/depois.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)

    data = json.loads(raw)
    historia_final = historia.strip() or data.get("historia_gerada", "")
    return {
        "valid":           True,
        "atributos":       data["atributos"],
        "status":          data["status"],
        "titulo":          data["titulo"],
        "historia_gerada": historia_final,
        "inventario":      data.get("inventario", []),
        "habilidades":     data.get("habilidades", []),
    }


def _chamar_api(nome: str, raca: str, classe: str, historia: str) -> dict:
    """Tenta Groq; cai no gerador local se não houver chave ou ocorrer erro."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if api_key:
        try:
            return _chamar_groq_personagem(nome, raca, classe, historia, api_key)
        except Exception:
            pass  # fallback para gerador local
    return _chamar_api_mock(nome, raca, classe, historia)


def _chamar_api_mock(nome: str, raca: str, classe: str, historia: str) -> dict:
    """
    Gerador local (offline). Deduz atributos, equipamentos e habilidades
    com base em palavras-chave da raça, classe e história.
    """
    time.sleep(1.8)   # simula latencia da API

    hist = historia.lower()
    raca_l   = raca.lower()
    classe_l = classe.lower()

    # ── Titulo inicial baseado na historia/raca/classe ─────────────────────
    if any(w in hist for w in ("nobre", "rei", "castelo", "trono")):
        titulo = {
            "nome":      "O Herdeiro Exilado",
            "descricao": "Nascido entre seda e traicao, carrega o peso de uma coroa perdida.",
            "beneficio": "+2 Carisma. NPCs nobres tratam voce com respeito velado.",
        }
    elif any(w in hist for w in ("floresta", "caca", "natureza", "selvagem")):
        titulo = {
            "nome":      "O Rastreador Silencioso",
            "descricao": "A natureza e sua aliada; seus passos nao perturbam nem as folhas.",
            "beneficio": "+2 Destreza. Vantagem em testes de furtividade em ambientes naturais.",
        }
    elif any(w in hist for w in ("magia", "feitico", "arcano", "grimorio")):
        titulo = {
            "nome":      "O Aprendiz Arcano",
            "descricao": "Tocou o veio eterno do arcano antes de entender as consequencias.",
            "beneficio": "+2 Inteligencia. Pode identificar magias de nivel 1-3 sem teste.",
        }
    elif any(w in hist for w in ("sombra", "ladrao", "roubo", "guilda")):
        titulo = {
            "nome":      "O Fantasma das Ruas",
            "descricao": "Sobreviveu onde outros sucumbiram, usando escuridao como aliada.",
            "beneficio": "+2 Destreza. Vantagem em testes de furtividade em ambientes urbanos.",
        }
    elif any(w in raca_l + classe_l for w in ("orc", "dragao", "vampiro", "demonio")):
        titulo = {
            "nome":      "A Fera Encadeada",
            "descricao": "Poder bruto contido por uma vontade de ferro.",
            "beneficio": "+3 Forca. Intimidacao automaticamente bem-sucedida contra alvos com nivel <= seu nivel.",
        }
    else:
        titulo = {
            "nome":      "O Iniciante",
            "descricao": "Toda grande lenda comeca com um primeiro passo hesitante.",
            "beneficio": "+1 em todos os atributos. A sorte do destino ainda sorri para voce.",
        }

    # ── Atributos deduzidos pelo perfil ───────────────────────────────────
    atributos = {"forca": 10, "destreza": 10, "inteligencia": 10,
                 "constituicao": 10, "sabedoria": 10, "carisma": 10}

    for kw, atr, bônus in [
        (("guerreiro","barbaro","paladino","guar"), "forca",        4),
        (("ladino","ranger","monge","ca"),          "destreza",     4),
        (("mago","feiticeiro","bruxo","arcano"),    "inteligencia", 4),
        (("clerigo","druida","sabio","oracu"),      "sabedoria",    4),
        (("bardo","nobre","diplomata"),             "carisma",      4),
        (("anao","draconato","orc","titan"),        "constituicao", 3),
    ]:
        if any(k in classe_l + raca_l for k in kw):
            atributos[atr] = min(20, atributos[atr] + bônus)

    # HP e Mana
    hp_max   = 20 + atributos["constituicao"] // 2 * 5
    mana_max = 10 + atributos["inteligencia"] // 2 * 3

    # ── Equipamentos ──────────────────────────────────────────────────────
    inventario = [
        {
            "nome":          "Roupa de Viajante",
            "historia":      "Tecido resistente que ja viu muitas estradas e mais batalhas ainda.",
            "ataque":        0,
            "defesa":        2,
            "efeito_status": "Nenhum",
            "resistencia":   "Chuva leve",
        },
        {
            "nome":          "Pocao Menor de Cura",
            "historia":      "Liquido vermelho que sabe a framboesas e segunda chance.",
            "ataque":        0,
            "defesa":        0,
            "efeito_status": "Restaura 10 HP quando consumida",
            "resistencia":   "Nenhuma",
        },
    ]

    # Item extra baseado na classe/raca
    if any(k in classe_l for k in ("mago","feiticeiro","bruxo","arcano")):
        inventario.append({
            "nome":          "Cajado de Madeira Runica",
            "historia":      "Entalhado num carvalho atingido por raio; guarda uma centelha do impacto.",
            "ataque":        5,
            "defesa":        1,
            "efeito_status": "Amplifica magias de nivel 1 em 1d4 de dano",
            "resistencia":   "Magias de invocacao",
        })
    elif any(k in classe_l for k in ("guerreiro","paladino","barbaro","lanceiro")):
        inventario.append({
            "nome":          "Espada Longa de Ferro",
            "historia":      "Forjada por um ferreiro anonimo; simples, direta e letal.",
            "ataque":        12,
            "defesa":        0,
            "efeito_status": "Sangramento em critico (1d6 por turno, CD 12)",
            "resistencia":   "Nenhuma",
        })
    elif any(k in classe_l for k in ("ladino","ranger","arqueiro")):
        inventario.append({
            "nome":          "Arco Curto de Teixo",
            "historia":      "Flexivel como o proprio destino; letal a distancias que pusilânimes chamam de seguras.",
            "ataque":        9,
            "defesa":        0,
            "efeito_status": "Disparo preciso: +2 de ataque contra alvos nao alertados",
            "resistencia":   "Nenhuma",
        })
    else:
        inventario.append({
            "nome":          "Adaga Enferrujada",
            "historia":      "Velha, surrada, mas afiada o suficiente para fazer o trabalho.",
            "ataque":        6,
            "defesa":        0,
            "efeito_status": "Nenhum",
            "resistencia":   "Nenhuma",
        })

    # ── Habilidades ───────────────────────────────────────────────────────
    habilidades = [
        {
            "nome":    "Ataque Basico",
            "custo":   "1 acao",
            "efeito":  "Ataque fisico simples. Dano = Forca ou Destreza + nivel.",
            "recarga": "Sem recarga",
        },
    ]

    if any(k in classe_l for k in ("mago","feiticeiro","arcano")):
        habilidades.append({
            "nome":    "Missil Magico",
            "custo":   "5 mana",
            "efeito":  "Dardos de forca arcana que nunca erram. 1d4+1 de dano por dardo (3 dardos).",
            "recarga": "Sem recarga",
        })
        habilidades.append({
            "nome":    "Escudo Arcano",
            "custo":   "8 mana",
            "efeito":  "Cria uma barreira magica que absorve ate 2*nivel de dano no proximo ataque.",
            "recarga": "1 turno",
        })
    elif any(k in classe_l for k in ("guerreiro","barbaro","lanceiro")):
        habilidades.append({
            "nome":    "Golpe Poderoso",
            "custo":   "1 acao + 4 mana",
            "efeito":  "Ataque com toda a forca. Dano x2. Em critico, derruba o alvo.",
            "recarga": "2 turnos",
        })
        habilidades.append({
            "nome":    "Segunda Folego",
            "custo":   "2 acoes",
            "efeito":  "Recupera 1d10 + nivel de HP no campo de batalha.",
            "recarga": "Descanco curto",
        })
    elif any(k in classe_l for k in ("ladino","ranger","sombra")):
        habilidades.append({
            "nome":    "Ataque Furtivo",
            "custo":   "1 acao",
            "efeito":  "Ataque surpresa que causa +2d6 de dano se voce tiver vantagem ou aliado adjacente.",
            "recarga": "1 turno",
        })
        habilidades.append({
            "nome":    "Evasao",
            "custo":   "Reacao",
            "efeito":  "Ao ser atingido, role Destreza CD15. Sucesso: dano reduzido a 0.",
            "recarga": "Descanco curto",
        })
    elif any(k in classe_l for k in ("clerigo","druida","paladino","cura")):
        habilidades.append({
            "nome":    "Cura Divina",
            "custo":   "10 mana",
            "efeito":  "Restaura 2d8+Sabedoria de HP em um aliado a distancia de toque.",
            "recarga": "Sem recarga",
        })
        habilidades.append({
            "nome":    "Benção",
            "custo":   "5 mana",
            "efeito":  "Concede +1d4 em ataques e testes de resistencia por 3 turnos a ate 3 aliados.",
            "recarga": "2 turnos",
        })
    else:
        habilidades.append({
            "nome":    "Determinacao",
            "custo":   "Passiva",
            "efeito":  "Uma vez por descanso, quando chegar a 0 HP, fica em 1 HP.",
            "recarga": "Descanco longo",
        })

    # Gera história de fallback se o jogador deixou o campo em branco.
    # Isso garante que todo personagem criado offline tenha ao menos
    # uma linha de backstory mesmo sem conexão com a API.
    if not historia.strip():
        historia_gerada_mock = (
            f"{nome} é um(a) {raca} {classe} cujo passado é envolto em mistério. "
            f"Poucos sabem de onde veio, mas todos que o cruzam sentem o peso do destino marcado em seus olhos."
        )
    else:
        historia_gerada_mock = historia.strip()

    return {
        "valid":           True,
        "atributos":       atributos,
        "status":          {"hp_maximo": hp_max, "mana_maximo": mana_max, "nivel": 1},
        "titulo":          titulo,
        "historia_gerada": historia_gerada_mock,
        "inventario":      inventario,
        "habilidades":     habilidades,
    }


# ────────────────────────────────────────────────────────────────────────────
# HELPERS DE DESENHO
# ────────────────────────────────────────────────────────────────────────────

def _draw_stat_bar(surf, x, y, w, h, cur, maxi, fill_col, label, font):
    """
    Desenha uma barra de progresso horizontal com rótulo e valor.

    Parâmetros:
        surf      – superfície alvo.
        x, y      – posição superior-esquerda da barra.
        w, h      – largura e altura da barra.
        cur       – valor atual (ex: hp atual).
        maxi      – valor máximo (ex: hp máximo).
        fill_col  – cor de preenchimento (ex: VERDE_HP, AZUL_MANA).
        label     – texto do rótulo (ex: "HP").
        font      – fonte para o rótulo.
    """
    bg = pygame.Rect(x, y, w, h)
    pygame.draw.rect(surf, (25, 25, 32), bg, border_radius=5)
    if maxi > 0 and cur > 0:
        fw = int(w * min(cur / maxi, 1.0))
        pygame.draw.rect(surf, fill_col, pygame.Rect(x, y, fw, h), border_radius=5)
    pygame.draw.rect(surf, CINZA_MEDIO, bg, width=1, border_radius=5)
    t = font.render(f"{label}  {cur}/{maxi}", True, BRANCO)
    surf.blit(t, (x + 8, y + (h - t.get_height()) // 2))


def _draw_sep(surf, x, y, w, cor=CINZA_MEDIO):
    """Traça uma linha separadora horizontal de largura `w` na cor especificada."""
    pygame.draw.line(surf, cor, (x, y), (x + w, y), 1)


def _section_title(surf, x, y, text, font=None):
    """Renderiza um título de seção em dourado e retorna o novo `y` deslocado."""
    font = font or FONTE_TEXTO
    s = font.render(text, True, DOURADO)
    surf.blit(s, (x, y))
    return y + s.get_height() + 8


def _card_box(surf, x, y, w, h, cor_borda=CINZA_MEDIO):
    """Desenha uma caixa de card com fundo escuro e borda arredondada."""
    pygame.draw.rect(surf, (22, 22, 28), pygame.Rect(x, y, w, h), border_radius=6)
    pygame.draw.rect(surf, cor_borda,    pygame.Rect(x, y, w, h), width=1, border_radius=6)


# ────────────────────────────────────────────────────────────────────────────
# STATE PRINCIPAL
# ────────────────────────────────────────────────────────────────────────────

class CharacterCreation:
    """
    Gerenciador de personagens com quatro sub-telas:

      LIST    – Exibe cards dos personagens salvos. Botões Ver/Deletar.
      CREATE  – Formulário de criação: nome, raça, classe, história.
                A IA (Groq ou offline) gera a ficha completa ao clicar em Criar.
      DETAIL  – Visualiza todo o personagem: atributos, status, inventário,
                habilidades, títulos e história de origem.
      EDIT    – Permite renomear e trocar o título ativo.

    O estado é mantido entre chamadas a events()/draw() e sobrevive a
    chamadas a rebuild() (os TextInputs preservam o texto digitado).
    """
    PANEL_W  = 720
    PANEL_H  = 520
    PAD      = 40     # padding horizontal dentro do painel
    CARD_H   = 64     # altura de cada card na lista

    def __init__(self, game):
        self.game             = game
        self.view_mode        = "LIST"
        self.char_selecionado = None

        # Estado (preservado entre rebuilds)
        self.is_generating  = False
        self.status_msg     = "Dê nome à sua lenda."
        self.status_cor     = CINZA_CLARO
        self._dots          = 0
        self._dot_t         = time.time()
        self.cards: list[dict] = []
        self.dd_titulo       = None   # Dropdown criado ao abrir edição

        # Cria widgets pela primeira vez
        self._create_text_inputs()
        self.rebuild(game.sw, game.sh)

    def _create_text_inputs(self):
        """Cria os TextInputs que preservam texto entre rebuilds."""
        pw  = self.PANEL_W
        iw  = pw - self.PAD * 2
        ihw = (iw - 16) // 2
        fx  = self.PAD

        self.input_nome     = TextInput(fx, 70,  iw,  42)
        self.input_raca     = TextInput(fx, 160, ihw, 42)
        self.input_classe   = TextInput(fx + ihw + 16, 160, ihw, 42)
        self.input_historia = MultilineTextInput(fx, 260, iw, 145)
        self.input_edit_nome = TextInput(0, 0, pw, 42)   # posição atualizada no rebuild

    def rebuild(self, w: int, h: int):
        """Recria todos os botões e ContentAreas com as novas dimensões."""
        self.sw, self.sh = w, h
        cx = w // 2

        pw, ph = self.PANEL_W, min(self.PANEL_H, h - 160)
        self.cx = cx
        self.fx  = self.PAD
        self.fw  = pw - self.PAD * 2
        self.lc  = pw // 2

        # ContentArea central
        self.ca = ContentArea(cx - pw // 2, 90, pw, ph)

        # Botões fixos (posições absolutas)
        self.btn_voltar_menu   = Button(cx - 100, h - 68, 200, 48, "< Início",      color=CINZA_ESCURO)
        self.btn_voltar_lista  = Button(30,        h - 68, 170, 48, "< Voltar",      color=CINZA_ESCURO)
        self.btn_editar_heroi  = Button(cx - 115,  h - 68, 220, 48, "Editar Perfil", color=DOURADO, text_color=PRETO)
        self.btn_excluir_heroi = Button(cx + 115,  h - 68, 215, 48, "Excluir Herói", color=(160, 25, 25))

        # Botão da lista (coord local)
        self.btn_novo_heroi = Button(self.lc - 155, 15, 310, 48, "+ Forjar Novo Herói", color=(34, 139, 34))

        # Botões de criação (coords locais ao painel)
        iw  = self.fw
        self.btn_salvar   = Button(self.fx + iw - 210, 425, 210, 48, "Forjar Herói", color=(34, 139, 34))
        self.btn_cancelar = Button(self.fx,              425, 178, 48, "Cancelar",    color=VERMELHO_SANGUE)

        # Botões de edição (coords absolutas)
        ex = cx - pw // 2
        self.input_edit_nome.rect = pygame.Rect(ex, 168, pw, 42)
        self.btn_salvar_edicao   = Button(ex + pw - 230, 310, 230, 48, "Salvar",   color=(34, 139, 34))
        self.btn_cancelar_edicao = Button(ex,             310, 190, 48, "Cancelar", color=CINZA_ESCURO)

        self.carregar_lista()

    # ── Lista ──────────────────────────────────────────────────────────────
    def carregar_lista(self):
        self.cards.clear()
        y = 80
        for c in load_characters():
            nivel  = c.get("status", {}).get("nivel", 1)
            classe = c.get("classe", "?")
            raca   = c.get("raca",   "?")
            titulo = c.get("titulo_ativo", "")
            nom    = c.get("nome", "?").upper()
            if titulo and titulo not in ("", "Nenhum"):
                nom += f"  |  {titulo}"
            sub    = f"Nivel {nivel}   .   {raca}   .   {classe}"
            btn    = Button(self.fx, y, self.fw, self.CARD_H, "", color=(35, 35, 42))
            self.cards.append({"dados": c, "btn": btn, "nom": nom, "sub": sub, "y": y, "classe": classe})
            y += self.CARD_H + 12

    # ── Eventos ────────────────────────────────────────────────────────────
    def events(self, event):
        # EDIT totalmente separado
        if self.view_mode == "EDIT":
            self.input_edit_nome.handle_event(event)
            dd_handled = self.dd_titulo.handle_event(event) if self.dd_titulo else False
            if not dd_handled:
                if self.btn_cancelar_edicao.handle_event(event):
                    self.view_mode = "DETAIL"
                if self.btn_salvar_edicao.handle_event(event):
                    self._salvar_edicao()
            return

        # Botoes fixos
        consumido = False
        if self.view_mode == "LIST":
            if self.btn_voltar_menu.handle_event(event):
                return "MENU"
        elif self.view_mode == "DETAIL":
            if self.btn_voltar_lista.handle_event(event):
                self.view_mode = "LIST"; consumido = True
            elif self.btn_excluir_heroi.handle_event(event):
                delete_character(self.char_selecionado["id"])
                self.carregar_lista()
                self.view_mode = "LIST"; consumido = True
            elif self.btn_editar_heroi.handle_event(event):
                self._abrir_edicao(); consumido = True

        if consumido:
            return

        # ContentArea
        wheel_consumed = False
        if event.type == pygame.MOUSEWHEEL and self.view_mode == "CREATE":
            if self.input_historia.is_active:
                wheel_consumed = self.input_historia.handle_event(event)
        if not wheel_consumed:
            self.ca.handle_event(event)

        adj = self.ca.get_adjusted_event(event)
        ev  = adj if adj else event

        if self.view_mode == "LIST":
            if ev and self.btn_novo_heroi.handle_event(ev):
                self._limpar_campos(); self.view_mode = "CREATE"
            if ev:
                for item in self.cards:
                    if item["btn"].handle_event(ev):
                        self.char_selecionado = item["dados"]
                        self.view_mode = "DETAIL"

        elif self.view_mode == "CREATE":
            if self.is_generating:
                return
            if ev:
                self.input_nome.handle_event(ev)
                self.input_raca.handle_event(ev)
                self.input_classe.handle_event(ev)
                if event.type != pygame.MOUSEWHEEL:
                    self.input_historia.handle_event(ev)
                if self.btn_cancelar.handle_event(ev):
                    self.view_mode = "LIST"
                if self.btn_salvar.handle_event(ev):
                    self._iniciar_geracao()

    # ── Acoes ──────────────────────────────────────────────────────────────
    def _abrir_edicao(self):
        char = self.char_selecionado
        ex   = self.cx - self.PANEL_W // 2
        self.input_edit_nome.text       = char.get("nome", "")
        self.input_edit_nome.cursor_pos = len(self.input_edit_nome.text)

        # Extrai apenas os nomes dos titulos para o Dropdown
        titulos = char.get("titulos_desbloqueados", [])
        nomes_titulos = [t["nome"] if isinstance(t, dict) else str(t) for t in titulos]
        if not nomes_titulos:
            nomes_titulos = [char.get("titulo_ativo", "Sem Titulo")]

        self.dd_titulo = Dropdown(
            ex, 245, self.PANEL_W, 42, nomes_titulos,
            char.get("titulo_ativo", "")
        )
        self.view_mode = "EDIT"

    def _salvar_edicao(self):
        novo_nome   = self.input_edit_nome.text.strip() or self.char_selecionado["nome"]
        novo_titulo = self.dd_titulo.get_current_value() if self.dd_titulo else self.char_selecionado.get("titulo_ativo", "")
        update_character_name_title(self.char_selecionado["id"], novo_nome, novo_titulo)
        self.carregar_lista()
        for item in self.cards:
            if item["dados"]["id"] == self.char_selecionado["id"]:
                self.char_selecionado = item["dados"]
        self.view_mode = "DETAIL"

    def _iniciar_geracao(self):
        """
        Valida os campos do formulário e dispara a geração de ficha em thread
        separada para não bloquear o loop de jogo.

        Validações:
          - Nome é obrigatório (campo vazio mostra mensagem de erro).
          - Raça e Classe usam valor padrão se vazios ("Humano", "Aventureiro").
          - História é opcional; se vazia, a IA gera uma automaticamente.

        Thread daemon: não bloqueia o fechamento do jogo se ainda estiver rodando.
        """
        nome = self.input_nome.text.strip()
        if not nome:
            self.status_msg = "Nome é obrigatório!"
            self.status_cor = VERMELHO_SANGUE
            return
        raca    = self.input_raca.text.strip()    or "Humano"
        classe  = self.input_classe.text.strip()  or "Aventureiro"
        historia= self.input_historia.text.strip()

        self.is_generating = True
        self.status_msg    = "Forjando seu destino"
        self.status_cor    = DOURADO
        self._dots         = 0
        self._dot_t        = time.time()
        threading.Thread(
            target=self._processar,
            args=(nome, raca, classe, historia),
            daemon=True
        ).start()

    def _processar(self, nome, raca, classe, historia):
        """
        Callback da thread de geração. Chama a API (Groq ou mock), salva o
        personagem em `data/personagens.json` e volta para a LIST.

        Executado em thread separada – NÃO toca em widgets Pygame diretamente;
        apenas altera self.view_mode, self.status_msg e self.status_cor, que
        são lidos com segurança na thread principal (GIL do CPython garante).
        """
        res = _chamar_api(nome, raca, classe, historia)
        if res["valid"]:
            # Usa a história gerada pela IA se o jogador deixou vazia
            historia_final = res.get("historia_gerada") or historia
            save_character(
                nome, raca, classe, historia_final,
                res["atributos"], res["status"],
                res["titulo"],
                res["inventario"], res["habilidades"],
            )
            self.carregar_lista()
            self.view_mode = "LIST"
        else:
            self.status_msg = res.get("erro", "Erro desconhecido.")
            self.status_cor = VERMELHO_SANGUE
        self.is_generating = False

    def _limpar_campos(self):
        """Reseta todos os campos do formulário de criação para os valores padrão."""
        for box in (self.input_nome, self.input_raca, self.input_classe):
            box.text       = ""
            box.cursor_pos = 0
        self.input_historia.text         = ""
        self.input_historia.cursor_pos   = 0
        self.input_historia.scroll_offset= 0
        self.status_msg = "De nome a sua lenda."
        self.status_cor = CINZA_CLARO

    # ── Draw principal ─────────────────────────────────────────────────────
    def draw(self, surface):
        surface.fill(PRETO)

        if self.view_mode == "EDIT":
            self._draw_edicao(surface)
            return

        # Fundo do painel
        pygame.draw.rect(surface, (18, 18, 22), self.ca.rect, border_radius=14)
        pygame.draw.rect(surface, CINZA_ESCURO,  self.ca.rect, width=2, border_radius=14)

        def draw_content(cs):
            if self.view_mode == "LIST":
                self._draw_lista(cs)
                h = 80 + len(self.cards) * (self.CARD_H + 12) + 40
            elif self.view_mode == "CREATE":
                self._draw_criacao(cs)
                h = 500
            elif self.view_mode == "DETAIL":
                h = self._draw_detalhe(cs)
            else:
                h = self.PANEL_H
            self.ca.content_height = max(self.PANEL_H, h)

        self.ca.draw(surface, draw_content)

        # Titulos e botoes fixos
        if self.view_mode == "LIST":
            t = FONTE_TITULO.render("SALAO DOS HEROIS", True, DOURADO)
            surface.blit(t, t.get_rect(center=(self.cx, 45)))
            self.btn_voltar_menu.draw(surface)

        elif self.view_mode == "CREATE":
            t = FONTE_SUBTITULO.render("FORJAR NOVO HEROI", True, DOURADO)
            surface.blit(t, t.get_rect(center=(self.cx, 45)))

        elif self.view_mode == "DETAIL":
            t = FONTE_TITULO.render("FICHA DO HEROI", True, DOURADO)
            surface.blit(t, t.get_rect(center=(self.cx, 45)))
            self.btn_voltar_lista.draw(surface)
            self.btn_editar_heroi.draw(surface)
            self.btn_excluir_heroi.draw(surface)

    # ── Subpagina: LISTA ───────────────────────────────────────────────────
    def _draw_lista(self, surf):
        self.btn_novo_heroi.draw(surf)
        if not self.cards:
            t = FONTE_TEXTO.render("Nenhum heroi forjado ainda.", True, CINZA_CLARO)
            surf.blit(t, (self.lc - t.get_width() // 2, 200))
            return
        for item in self.cards:
            item["btn"].draw(surf)
            y   = item["y"]
            # Barra lateral accent (cor por classe)
            pygame.draw.rect(surf, _cor_classe(item["classe"]),
                             pygame.Rect(self.fx, y, 4, self.CARD_H), border_radius=2)
            hover     = item["btn"].is_hovered
            ns = FONTE_TEXTO.render(item["nom"], True, DOURADO if hover else BRANCO)
            surf.blit(ns, (self.fx + 16, y + 10))
            ss = FONTE_PEQUENA.render(item["sub"], True, CINZA_CLARO)
            surf.blit(ss, (self.fx + 16, y + 38))

    # ── Subpagina: CRIACAO ─────────────────────────────────────────────────
    def _draw_criacao(self, surf):
        # Animacao de pontos
        if self.is_generating and time.time() - self._dot_t > 0.4:
            self._dots  = (self._dots + 1) % 4
            self._dot_t = time.time()
        msg = self.status_msg + ("." * self._dots if self.is_generating else "")
        ms  = FONTE_TEXTO.render(msg, True, self.status_cor)
        surf.blit(ms, ms.get_rect(center=(self.lc, 22)))

        # Nome
        surf.blit(FONTE_TEXTO.render("Nome do Heroi  *", True, DOURADO), (self.fx, 46))
        self.input_nome.draw(surf)

        # Raca e Classe
        ihw = (self.fw - 16) // 2
        surf.blit(FONTE_TEXTO.render("Raca", True, DOURADO),   (self.fx,           134))
        surf.blit(FONTE_TEXTO.render("Classe", True, DOURADO), (self.fx + ihw + 16, 134))
        surf.blit(FONTE_PEQUENA.render("(ex: Meio-Vampiro, Elfo Solar)", True, CINZA_CLARO),
                  (self.fx, 157))
        surf.blit(FONTE_PEQUENA.render("(ex: Necromante, Samurai Sombrio)", True, CINZA_CLARO),
                  (self.fx + ihw + 16, 157))
        self.input_raca.draw(surf)
        self.input_classe.draw(surf)

        # Historia
        surf.blit(FONTE_TEXTO.render("Historia de Origem", True, DOURADO), (self.fx, 236))
        surf.blit(FONTE_PEQUENA.render("(opcional - a IA usa isso para criar titulo, atributos e equipamentos)", True, CINZA_CLARO),
                  (self.fx, 258))
        self.input_historia.draw(surf)

        if not self.is_generating:
            self.btn_salvar.draw(surf)
            self.btn_cancelar.draw(surf)
        else:
            info = FONTE_PEQUENA.render("Aguarde... os deuses consultam o destino.", True, DOURADO)
            surf.blit(info, info.get_rect(center=(self.lc, 448)))

    # ── Subpagina: DETALHE ─────────────────────────────────────────────────
    def _draw_detalhe(self, surf) -> int:
        char = self.char_selecionado
        mx   = self.fx
        mw   = self.fw
        y    = 20

        # Nome + titulo ativo
        nome_surf = FONTE_SUBTITULO.render(char.get("nome", "?").upper(), True, DOURADO)
        surf.blit(nome_surf, (mx, y))
        y += nome_surf.get_height() + 4

        titulo_ativo = char.get("titulo_ativo", "")
        if titulo_ativo and titulo_ativo != "Nenhum":
            ts = FONTE_PEQUENA.render(titulo_ativo, True, CINZA_CLARO)
            surf.blit(ts, (mx, y))
            y += ts.get_height() + 6

        # Raca . classe . nivel
        nivel = char.get("status", {}).get("nivel", 1)
        info  = f"{char.get('raca','?')}   .   {char.get('classe','?')}   .   Nivel {nivel}"
        inf_s = FONTE_TEXTO.render(info, True, CINZA_CLARO)
        surf.blit(inf_s, (mx, y))
        y += inf_s.get_height() + 14
        _draw_sep(surf, mx, y, mw); y += 14

        # Barras HP / Mana
        status = char.get("status", {})
        hp_c   = status.get("hp_atual",   status.get("hp_maximo",   30))
        hp_m   = status.get("hp_maximo",  30)
        mp_c   = status.get("mana_atual", status.get("mana_maximo", 10))
        mp_m   = status.get("mana_maximo", 10)
        bw     = (mw - 16) // 2
        _draw_stat_bar(surf, mx,        y, bw, 26, hp_c, hp_m, VERDE_HP,  "HP",   FONTE_PEQUENA)
        _draw_stat_bar(surf, mx+bw+16,  y, bw, 26, mp_c, mp_m, AZUL_MANA, "Mana", FONTE_PEQUENA)
        y += 36

        xp_c = status.get("xp", 0); xp_n = nivel * 100
        _draw_stat_bar(surf, mx, y, mw, 16, xp_c, xp_n, ROXO_XP, "XP", FONTE_MICRO)
        y += 30
        _draw_sep(surf, mx, y, mw); y += 14

        # Atributos
        y = _section_title(surf, mx, y, "Atributos")
        atr  = char.get("atributos", {})
        if not atr:
            atr = {k: char.get(k, "-") for k in ("forca","destreza","inteligencia","constituicao","sabedoria","carisma")}
        ordem = [("Forca", "forca"), ("Destreza","destreza"), ("Inteligencia","inteligencia"),
                 ("Constituicao","constituicao"), ("Sabedoria","sabedoria"), ("Carisma","carisma")]
        cw = mw // 3
        for i, (lbl, key) in enumerate(ordem):
            col = i % 3; row = i // 3
            ax = mx + col * cw; ay = y + row * 30
            _card_box(surf, ax, ay, cw - 6, 24)
            t = FONTE_PEQUENA.render(f"{lbl}: {atr.get(key,'-')}", True, BRANCO)
            surf.blit(t, (ax + 8, ay + (24 - t.get_height()) // 2))
        y += ((len(ordem) + 2) // 3) * 30 + 14
        _draw_sep(surf, mx, y, mw); y += 14

        # Historia
        y = _section_title(surf, mx, y, "Historia de Origem")
        hist = char.get("historia", "").strip()
        if hist:
            y += draw_text_wrapped(surf, hist, FONTE_PEQUENA, CINZA_CLARO, mx, y, mw)
        else:
            t = FONTE_PEQUENA.render("Nenhuma historia registrada.", True, CINZA_MEDIO)
            surf.blit(t, (mx, y)); y += t.get_height()
        y += 14
        _draw_sep(surf, mx, y, mw); y += 14

        # Titulos desbloqueados
        y = _section_title(surf, mx, y, "Titulos Desbloqueados")
        titulos = char.get("titulos_desbloqueados", [])
        if titulos:
            for tit in titulos:
                nome_t = tit["nome"]      if isinstance(tit, dict) else str(tit)
                desc_t = tit.get("descricao", "") if isinstance(tit, dict) else ""
                ben_t  = tit.get("beneficio", "") if isinstance(tit, dict) else ""
                ativo  = (nome_t == titulo_ativo)
                cor_b  = DOURADO if ativo else CINZA_MEDIO
                _card_box(surf, mx, y, mw, 10, cor_b)   # altura provisória
                # Nome do titulo
                nt_s = FONTE_TEXTO.render((">> " if ativo else "   ") + nome_t, True, DOURADO if ativo else BRANCO)
                surf.blit(nt_s, (mx + 10, y + 4))
                yi = y + nt_s.get_height() + 8
                # Descricao
                if desc_t:
                    yi += draw_text_wrapped(surf, desc_t, FONTE_MICRO, CINZA_CLARO, mx + 10, yi, mw - 20)
                # Beneficio
                if ben_t:
                    ben_s = FONTE_MICRO.render("Beneficio: " + ben_t, True, (160, 220, 100))
                    surf.blit(ben_s, (mx + 10, yi))
                    yi += ben_s.get_height() + 4
                # Redesenha a caixa com a altura correta
                _card_box(surf, mx, y, mw, yi - y + 6, cor_b)
                # Redesenha o texto (para ficar acima da caixa - a caixa e desenhada primeiro num jogo real)
                nt_s2 = FONTE_TEXTO.render((">> " if ativo else "   ") + nome_t, True, DOURADO if ativo else BRANCO)
                surf.blit(nt_s2, (mx + 10, y + 4))
                yii = y + nt_s2.get_height() + 8
                if desc_t:
                    yii += draw_text_wrapped(surf, desc_t, FONTE_MICRO, CINZA_CLARO, mx + 10, yii, mw - 20)
                if ben_t:
                    b2 = FONTE_MICRO.render("Beneficio: " + ben_t, True, (160, 220, 100))
                    surf.blit(b2, (mx + 10, yii))
                y = yi + 10
        else:
            nenhum = FONTE_PEQUENA.render("Nenhum titulo desbloqueado.", True, CINZA_MEDIO)
            surf.blit(nenhum, (mx, y)); y += nenhum.get_height()
        y += 14
        _draw_sep(surf, mx, y, mw); y += 14

        # Inventario
        y = _section_title(surf, mx, y, "Inventario")
        inventario = char.get("inventario", [])
        if inventario:
            for item in inventario:
                if isinstance(item, str):
                    # compatibilidade com personagens antigos
                    t = FONTE_PEQUENA.render(f"  .  {item}", True, BRANCO)
                    surf.blit(t, (mx + 6, y)); y += t.get_height() + 4
                    continue
                nome_i = item.get("nome", "Desconhecido")
                hist_i = item.get("historia", "")
                atq_i  = item.get("ataque",        0)
                def_i  = item.get("defesa",        0)
                efs_i  = item.get("efeito_status", "Nenhum")
                res_i  = item.get("resistencia",   "Nenhuma")

                box_y = y
                yi    = y + 6
                # Nome
                ns = FONTE_TEXTO.render(nome_i, True, DOURADO)
                surf.blit(ns, (mx + 10, yi)); yi += ns.get_height() + 4
                # Historia/sinopse
                if hist_i:
                    yi += draw_text_wrapped(surf, hist_i, FONTE_MICRO, CINZA_CLARO, mx + 10, yi, mw - 20)
                # Stats em linha
                stats_txt = f"ATK {atq_i}   DEF {def_i}   Efeito: {efs_i}   Resist: {res_i}"
                st = FONTE_MICRO.render(stats_txt, True, (180, 200, 160))
                surf.blit(st, (mx + 10, yi)); yi += st.get_height() + 6
                _card_box(surf, mx, box_y, mw, yi - box_y)
                # Re-draw texto sobre a caixa
                ns2 = FONTE_TEXTO.render(nome_i, True, DOURADO)
                surf.blit(ns2, (mx + 10, box_y + 6))
                yii = box_y + 6 + ns2.get_height() + 4
                if hist_i:
                    yii += draw_text_wrapped(surf, hist_i, FONTE_MICRO, CINZA_CLARO, mx + 10, yii, mw - 20)
                surf.blit(st, (mx + 10, yii))
                y = yi + 8
        else:
            t = FONTE_PEQUENA.render("Inventario vazio.", True, CINZA_MEDIO)
            surf.blit(t, (mx, y)); y += t.get_height()
        y += 14
        _draw_sep(surf, mx, y, mw); y += 14

        # Habilidades
        y = _section_title(surf, mx, y, "Habilidades")
        habilidades = char.get("habilidades", [])
        if habilidades:
            for hab in habilidades:
                if isinstance(hab, str):
                    t = FONTE_PEQUENA.render(f"  .  {hab}", True, BRANCO)
                    surf.blit(t, (mx + 6, y)); y += t.get_height() + 4
                    continue
                nome_h  = hab.get("nome",   "?")
                custo_h = hab.get("custo",  "?")
                efeito_h= hab.get("efeito", "?")
                rec_h   = hab.get("recarga","?")

                box_y = y; yi = y + 6
                nh = FONTE_TEXTO.render(nome_h, True, DOURADO)
                surf.blit(nh, (mx + 10, yi)); yi += nh.get_height() + 4
                yi += draw_text_wrapped(surf, efeito_h, FONTE_MICRO, CINZA_CLARO, mx + 10, yi, mw - 20)
                meta = FONTE_MICRO.render(f"Custo: {custo_h}   |   Recarga: {rec_h}", True, AZUL_MANA)
                surf.blit(meta, (mx + 10, yi)); yi += meta.get_height() + 6
                _card_box(surf, mx, box_y, mw, yi - box_y)
                nh2 = FONTE_TEXTO.render(nome_h, True, DOURADO)
                surf.blit(nh2, (mx + 10, box_y + 6))
                yii = box_y + 6 + nh2.get_height() + 4
                yii += draw_text_wrapped(surf, efeito_h, FONTE_MICRO, CINZA_CLARO, mx + 10, yii, mw - 20)
                meta2 = FONTE_MICRO.render(f"Custo: {custo_h}   |   Recarga: {rec_h}", True, AZUL_MANA)
                surf.blit(meta2, (mx + 10, yii))
                y = yi + 8
        else:
            t = FONTE_PEQUENA.render("Nenhuma habilidade registrada.", True, CINZA_MEDIO)
            surf.blit(t, (mx, y)); y += t.get_height()

        return y + 50

    # ── Subpagina: EDICAO ──────────────────────────────────────────────────
    def _draw_edicao(self, surface):
        ex = self.cx - self.PANEL_W // 2
        ew = self.PANEL_W

        panel = pygame.Rect(ex - 10, 80, ew + 20, 310)
        pygame.draw.rect(surface, (18, 18, 22), panel, border_radius=14)
        pygame.draw.rect(surface, CINZA_ESCURO,  panel, width=2, border_radius=14)

        t = FONTE_SUBTITULO.render("EDITAR HEROI", True, DOURADO)
        surface.blit(t, t.get_rect(center=(self.cx, 115)))

        surface.blit(FONTE_TEXTO.render("Renomear:", True, DOURADO), (ex, 143))
        self.input_edit_nome.draw(surface)

        surface.blit(FONTE_TEXTO.render("Titulo Ativo:", True, DOURADO), (ex, 222))
        if self.dd_titulo:
            self.dd_titulo.draw_main(surface)

        self.btn_salvar_edicao.draw(surface)
        self.btn_cancelar_edicao.draw(surface)

        if self.dd_titulo:
            self.dd_titulo.draw_options(surface)


# ── Helper local ───────────────────────────────────────────────────────────

_COR_CLASSE = {
    "guerreiro": (200, 80, 40), "paladino":   (200, 190, 60), "barbaro":    (200, 50, 50),
    "mago":      (100, 80,220), "feiticeiro": (160,  60,200), "bruxo":      ( 90, 30,160),
    "clerigo":   (230,220,100), "druida":     ( 60, 180, 60), "monge":      ( 80,200,200),
    "ladino":    ( 60,160,130), "ranger":     ( 70, 150, 80), "bardo":      (220,120,180),
    "necromante":( 80, 40,120), "vampiro":    (160, 20, 60),  "samurai":    (220,180, 40),
    "lanceiro":  (170, 90, 50),
}

def _cor_classe(classe: str) -> tuple:
    cl = classe.lower()
    for k, c in _COR_CLASSE.items():
        if k in cl:
            return c
    return DOURADO
