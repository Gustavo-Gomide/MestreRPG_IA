"""
settings.py  –  Constantes globais, paleta de cores, fontes e sistema de áudio.

Este módulo é importado com  `from settings import *`  em todos os outros módulos,
tornando todas as constantes e funções de áudio disponíveis diretamente.

Seções:
  - Dimensões e FPS da janela
  - Caminhos de assets (música, SFX, logo)
  - MUSIC_MAP    : dict [clima_str → caminho_mp3]  usado pela tag <MUSIC>
  - SFX_MAP      : dict [nome_str  → caminho_wav]  usado pela tag <SFX>
  - Cores Dark Fantasy
  - Fontes Pygame (Cambria)
  - Funções de áudio: play_music / stop_music / play_sfx / play_sfx_ambient /
                       stop_sfx_ambient
"""

import pygame
import os
from dotenv import load_dotenv

load_dotenv()  # Carrega .env para a API key do Groq

# ── Tela (tamanho padrão; o jogo é redimensionável) ──
WIDTH, HEIGHT = 1280, 720
FPS = 60

# Proporção mínima recomendada
MIN_WIDTH,  MIN_HEIGHT  = 900, 600
SIDEBAR_W = 340   # largura do painel direito em STORY_PLAY

# ── Caminhos ────────────────────────────────────────
ASSETS_DIR = "assets"
MUSIC_DIR  = os.path.join(ASSETS_DIR, "music")
SFX_DIR    = os.path.join(ASSETS_DIR, "sfx")
LOGO_PATH  = os.path.join(ASSETS_DIR, "dragon.png")

# ── Músicas principais ───────────────────────────────
# Coloque os arquivos .mp3 ou .ogg dentro de assets/music/
# Para silenciar uma trilha, basta apontar para um arquivo que não existe.
#
# MUSIC_MENU        – tela de menu principal
# MUSIC_CHARACTER   – tela de criação/edição de personagem
# MUSIC_LOADING     – tela de carregamento inicial
# MUSIC_STORY       – música padrão dentro de uma campanha (exploração/genérica)
#
MUSIC_MENU      = os.path.join(MUSIC_DIR, "musica_principal.mp3")
MUSIC_CHARACTER = os.path.join(MUSIC_DIR, "musica_principal.mp3")  # mesma do menu
MUSIC_LOADING   = os.path.join(MUSIC_DIR, "musica_principal.mp3")  # mesma do menu
MUSIC_STORY     = os.path.join(MUSIC_DIR, "exploration_suspense.mp3")  # padrão de história

# ── Trilhas temáticas ────────────────────────────────────────────────────
# Nomes dos arquivos reais presentes em assets/music/:
#   musica_principal.mp3   – menu, loading e criação de personagem
#   tavern.mp3             – cenas de taverna, cidade, descanso
#   exploration_suspense.mp3 – exploração, viagem, investigação
#   figth.mp3              – combate, batalhas
#   end.mp3                – encerramento da história ou morte do personagem
#
MUSIC_EXPLORATION = os.path.join(MUSIC_DIR, "exploration_suspense.mp3")
MUSIC_FIGHT       = os.path.join(MUSIC_DIR, "figth.mp3")
MUSIC_END         = os.path.join(MUSIC_DIR, "end.mp3")

# ── Mapa de climas (usado pela tag <MUSIC> da IA) ────────────────────────
# A IA insere <MUSIC>clima</MUSIC> no texto para trocar a trilha em tempo real.
# Para adicionar novos climas: coloque o arquivo em assets/music/ e adicione
# uma entrada aqui. Se o arquivo não existir, o jogo ignora silenciosamente.
#
# Climas reconhecidos pela IA:
#   taverna           – bar, estalagem, cidade, descanso
#   exploration       – viagem, floresta, exploração, investigação
#   fight             – combate, batalha
#   end               – conclusão da história, morte do personagem
#
# Atalho para o arquivo de taverna (não passa por MUSIC_STORY)
_MUSIC_TAVERN = os.path.join(MUSIC_DIR, "tavern.mp3")

MUSIC_MAP: dict[str, str] = {
    # internas (usadas pelo código)
    "menu":           MUSIC_MENU,
    "personagem":     MUSIC_CHARACTER,
    "loading":        MUSIC_LOADING,
    # ── Taverna / conversa amigável ──────────────────────────────────────
    # Use quando: bar, estalagem, mercado, conversa relaxada, festa, cidade
    "taverna":        _MUSIC_TAVERN,
    "cidade":         _MUSIC_TAVERN,
    "estalagem":      _MUSIC_TAVERN,
    "conversa":       _MUSIC_TAVERN,
    "amigavel":       _MUSIC_TAVERN,
    "descanso":       _MUSIC_TAVERN,
    "paz":            _MUSIC_TAVERN,
    # ── Exploração / suspense (padrão de história) ───────────────────────
    # Use quando: viagem, floresta, dungeon, investigação, qualquer cena genérica
    "exploration":    MUSIC_EXPLORATION,
    "exploracao":     MUSIC_EXPLORATION,
    "floresta":       MUSIC_EXPLORATION,
    "dungeon":        MUSIC_EXPLORATION,
    "misterio":       MUSIC_EXPLORATION,
    "suspense":       MUSIC_EXPLORATION,
    # ── Combate ─────────────────────────────────────────────────────────
    "fight":          MUSIC_FIGHT,
    "combate":        MUSIC_FIGHT,
    "batalha":        MUSIC_FIGHT,
    # ── Encerramento ────────────────────────────────────────────────────
    "end":            MUSIC_END,
    "fim":            MUSIC_END,
    "morte":          MUSIC_END,
    "conclusao":      MUSIC_END,
}

# ── Efeitos sonoros (SFX) ────────────────────────────────────────────────────
# Todos os arquivos ficam em  assets/sfx/
# A IA pode acionar qualquer efeito via tag  <SFX>nome</SFX>
# O código interno também os dispara automaticamente em eventos de jogo.
#
# Arquivos presentes:
#   battle_win.wav    – fanfarra de vitória (fim de batalha bem-sucedido)
#   button_hover.wav  – mouse entra em um botão (UI)
#   exit.wav          – encerramento do programa
#   hurt_damage.mp3   – dano recebido pelo personagem
#   level_up.wav      – subida de nível / evolução
#   rain.wav          – som ambiente de chuva (loop, canal dedicado)
#   select.wav        – confirmação / clique de botão (UI)
#   spell.wav         – lançamento de magia / habilidade especial
#   weapon_attack.wav – ataque físico com arma
#
SFX_BATTLE_WIN    = os.path.join(SFX_DIR, "battle_win.wav")
SFX_BUTTON_HOVER  = os.path.join(SFX_DIR, "button_hover.wav")  # som ao passar o mouse
SFX_EXIT          = os.path.join(SFX_DIR, "exit.wav")           # encerrar programa
SFX_HURT          = os.path.join(SFX_DIR, "hurt_damage.mp3")
SFX_LEVEL_UP      = os.path.join(SFX_DIR, "level_up.wav")
SFX_RAIN          = os.path.join(SFX_DIR, "rain.wav")           # ambient loop
SFX_SELECT        = os.path.join(SFX_DIR, "select.wav")         # confirmação / clique
SFX_SPELL         = os.path.join(SFX_DIR, "spell.wav")
SFX_WEAPON_ATTACK = os.path.join(SFX_DIR, "weapon_attack.wav")

# Mapa de nomes usados pela tag <SFX>nome</SFX> da IA
# Adicione novos pares para expor outros efeitos ao narrador.
SFX_MAP: dict[str, str] = {
    "battle_win":    SFX_BATTLE_WIN,
    "vitoria":       SFX_BATTLE_WIN,
    "hover":         SFX_BUTTON_HOVER,
    "hurt":          SFX_HURT,
    "dano":          SFX_HURT,
    "level_up":      SFX_LEVEL_UP,
    "nivel":         SFX_LEVEL_UP,
    "rain":          SFX_RAIN,
    "chuva":         SFX_RAIN,
    "select":        SFX_SELECT,
    "confirmar":     SFX_SELECT,
    "spell":         SFX_SPELL,
    "magia":         SFX_SPELL,
    "feitico":       SFX_SPELL,
    "weapon":        SFX_WEAPON_ATTACK,
    "ataque":        SFX_WEAPON_ATTACK,
    "espada":        SFX_WEAPON_ATTACK,
}

# Nomes que ativam o som ambiente em loop (canal 1 dedicado)
# Qualquer outro nome de SFX_MAP é tocado como one-shot no canal 0.
SFX_AMBIENT_NAMES = {"rain", "chuva"}

# ── Cores (Dark Fantasy) ─────────────────────────────
PRETO          = (10,  10,  12)
CINZA_ESCURO   = (30,  30,  35)
CINZA_MEDIO    = (60,  60,  68)
CINZA_CLARO    = (150, 150, 155)
BRANCO         = (240, 240, 240)
VERMELHO_SANGUE= (138,  3,   3)
VERMELHO_HOVER = (180, 20,  20)
DOURADO        = (212, 175, 55)
DOURADO_ESCURO = (160, 130, 30)
VERDE_HP       = (55,  180, 75)
AZUL_MANA      = (55,  120, 220)
ROXO_XP        = (140, 70,  200)

# ── Fontes ───────────────────────────────────────────
pygame.font.init()
FONTE_TITULO    = pygame.font.SysFont("cambria", 64, bold=True)
FONTE_SUBTITULO = pygame.font.SysFont("cambria", 36, bold=True)
FONTE_TEXTO     = pygame.font.SysFont("cambria", 24)
FONTE_PEQUENA   = pygame.font.SysFont("cambria", 18)
FONTE_MICRO     = pygame.font.SysFont("cambria", 14)


# ── Áudio ────────────────────────────────────────────
def play_music(path: str, loops: int = -1, volume: float = 0.5):
    """Toca música de fundo. Falha silenciosamente se o arquivo não existir."""
    try:
        if os.path.exists(path):
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(loops)
    except Exception:
        pass


def stop_music():
    """Para a música de fundo imediatamente."""
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass


# ── Cache e canais de SFX ─────────────────────────────────────────────────────
# Canal 0  – efeitos one-shot (ataque, magia, level-up, etc.)
# Canal 1  – som ambiente em loop (chuva, vento, etc.)
# Aumentar pygame.mixer.set_num_channels() em main.py se precisar de mais canais.
_sfx_cache: dict[str, pygame.mixer.Sound] = {}


def _load_sfx(path: str) -> "pygame.mixer.Sound | None":
    """Carrega e cacheia um pygame.mixer.Sound. Retorna None se o arquivo não existir."""
    if not os.path.exists(path):
        return None
    if path not in _sfx_cache:
        try:
            _sfx_cache[path] = pygame.mixer.Sound(path)
        except Exception:
            return None
    return _sfx_cache[path]


def play_sfx(path: str, volume: float = 0.7):
    """
    Toca um efeito sonoro one-shot no canal 0.
    Silencioso se o arquivo não existir – nunca lança exceção para o chamador.
    """
    snd = _load_sfx(path)
    if snd:
        try:
            snd.set_volume(volume)
            ch = pygame.mixer.Channel(0)
            ch.play(snd)
        except Exception:
            pass


def play_sfx_ambient(path: str, volume: float = 0.3):
    """
    Toca um som ambiente em loop no canal 1 (dedicado a ambientes).
    Se o mesmo arquivo já estiver tocando, não reinicia.
    Para parar, chame stop_sfx_ambient().
    """
    snd = _load_sfx(path)
    if not snd:
        return
    try:
        ch = pygame.mixer.Channel(1)
        # Evita reiniciar se já está tocando o mesmo som
        if ch.get_busy() and ch.get_sound() is snd:
            return
        snd.set_volume(volume)
        ch.play(snd, loops=-1)
    except Exception:
        pass


def stop_sfx_ambient():
    """Para o som ambiente do canal 1."""
    try:
        pygame.mixer.Channel(1).stop()
    except Exception:
        pass