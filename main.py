"""
main.py – Entrada do jogo "Mundos: Uma Nova História".

Funcionalidades:
- Janela redimensionável (arraste as bordas).
- F11 para alternar tela cheia / janela.
- Transições de estado com gerência de música.
- Todos os estados recebem self.game e consultam game.sw / game.sh
  para calcular layouts responsivos.
"""

import pygame
import sys
import ctypes
from settings import *


def _apply_dark_titlebar() -> None:
    """Ativa o modo escuro na barra de título do Windows (10/11)."""
    try:
        hwnd = pygame.display.get_wm_info().get("window", 0)
        if not hwnd:
            return
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win 10 build 19041+)
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


from ui import Button, draw_text_wrapped
from states.loading import LoadingScreen
from states.character_creation import CharacterCreation
from states.story import StoryMode


class Game:
    def __init__(self):
        pygame.init()
        pygame.mixer.init()
        # Canal 0 → efeitos sonoros one-shot (SFX)
        # Canal 1 → som ambiente em loop (chuva, vento, etc.)
        # Aumentar se precisar de mais efeitos simultâneos.
        pygame.mixer.set_num_channels(8)

        # Ícone da janela e nome do jogo
        _icon_path = os.path.join(ASSETS_DIR, "dragon.png")
        if os.path.exists(_icon_path):
            pygame.display.set_icon(pygame.image.load(_icon_path))

        # Janela inicial – redimensionável
        self.fullscreen = False
        self.screen = pygame.display.set_mode(
            (WIDTH, HEIGHT),
            pygame.RESIZABLE,
        )
        pygame.display.set_caption("Mundos: Uma Nova História")
        _apply_dark_titlebar()
        self.clock = pygame.time.Clock()

        # Dimensões reais da janela (atualizam em _apply_resize)
        self.sw, self.sh = self.screen.get_size()

        # Estado atual
        self.state       = "LOADING"
        self._prev_state = None

        # ── States ──────────────────────────────────────────────────────────
        self.loading_screen     = LoadingScreen()
        self.character_creation = CharacterCreation(self)
        self.story_mode         = StoryMode(self)

        # ── Menu: botões (criados pelo layout) ──────────────────────────────
        self.btn_historia   = None
        self.btn_personagem = None
        self.btn_sair       = None
        self._build_menu_buttons()

        # Música de loading
        self._current_music: str = ""
        self._play_if_different(MUSIC_LOADING)

    # ── Layout responsivo ─────────────────────────────────────────────────
    def _build_menu_buttons(self):
        """Recria os botões do menu com base nas dimensões atuais."""
        bw, bh = 420, 58
        bx = self.sw // 2 - bw // 2
        cy = self.sh // 2
        self.btn_historia   = Button(bx, cy - 50,  bw, bh, "Nova História / Continuar")
        self.btn_personagem = Button(bx, cy + 18,  bw, bh, "Criar / Editar Personagem")
        self.btn_sair       = Button(bx, cy + 86,  bw, bh, "Sair",
                                     color=CINZA_ESCURO, text_color=CINZA_CLARO)

    def _apply_resize(self, w: int, h: int):
        """Chamado quando a janela muda de tamanho."""
        w = max(w, MIN_WIDTH)
        h = max(h, MIN_HEIGHT)
        self.sw, self.sh = w, h
        if not self.fullscreen:
            self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        self._build_menu_buttons()
        self.character_creation.rebuild(w, h)
        self.story_mode.rebuild(w, h)

    def _toggle_fullscreen(self):
        """Alterna entre tela cheia e janela redimensionável."""
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            info = pygame.display.Info()
            self.screen = pygame.display.set_mode(
                (info.current_w, info.current_h),
                pygame.FULLSCREEN,
            )
        else:
            self.screen = pygame.display.set_mode(
                (WIDTH, HEIGHT),
                pygame.RESIZABLE,
            )
        _apply_dark_titlebar()
        self._apply_resize(*self.screen.get_size())

    # ── Troca de estado ───────────────────────────────────────────────────
    def _change_state(self, new_state: str):
        if self.state == new_state:
            return
        self._prev_state = self.state
        self.state       = new_state

        if new_state == "MENU":
            self._play_if_different(MUSIC_MENU)
        elif new_state == "STORY_MENU":
            self._play_if_different(MUSIC_STORY)
        elif new_state == "CHARACTER_MENU":
            self._play_if_different(MUSIC_CHARACTER)

    def _play_if_different(self, path: str):
        """Toca a música apenas se for um arquivo diferente do que está tocando."""
        if path != self._current_music:
            self._current_music = path
            play_music(path)

    # ── Loop principal ────────────────────────────────────────────────────
    def run(self):
        while True:
            self.events()
            self.update()
            self.draw()
            self.clock.tick(FPS)

    # ── Eventos ───────────────────────────────────────────────────────────
    def events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            # ── Redimensionamento / tela cheia ───────────────────────────
            if event.type == pygame.VIDEORESIZE:
                self._apply_resize(event.w, event.h)
                continue

            if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                self._toggle_fullscreen()
                continue

            # ── Roteamento por estado ────────────────────────────────────
            if self.state == "MENU":
                if self.btn_historia.handle_event(event):
                    self._change_state("STORY_MENU")
                elif self.btn_personagem.handle_event(event):
                    self._change_state("CHARACTER_MENU")
                elif self.btn_sair.handle_event(event):
                    # Toca o som de saída e aguarda ele terminar antes de fechar
                    play_sfx(SFX_EXIT, volume=0.8)
                    pygame.time.wait(900)  # ms – ajuste conforme a duração do arquivo
                    pygame.quit()
                    sys.exit()

            elif self.state == "CHARACTER_MENU":
                result = self.character_creation.events(event)
                if result == "MENU":
                    self._change_state("MENU")

            elif self.state == "STORY_MENU":
                result = self.story_mode.events(event)
                if result == "MENU":
                    self._change_state("MENU")

    # ── Update ────────────────────────────────────────────────────────────
    def update(self):
        if self.state == "LOADING":
            done = self.loading_screen.update()
            if done:
                self._change_state("MENU")

    # ── Draw ──────────────────────────────────────────────────────────────
    def draw(self):
        if self.state == "LOADING":
            self.loading_screen.draw(self.screen)
        elif self.state == "MENU":
            self._draw_menu()
        elif self.state == "CHARACTER_MENU":
            self.character_creation.draw(self.screen)
        elif self.state == "STORY_MENU":
            self.story_mode.draw(self.screen)

        pygame.display.flip()

    def _draw_menu(self):
        W, H = self.sw, self.sh
        self.screen.fill(PRETO)
        cx = W // 2

        # Título
        t = FONTE_TITULO.render("MUNDOS", True, VERMELHO_SANGUE)
        self.screen.blit(t, t.get_rect(center=(cx, int(H * 0.15))))

        # Subtítulo
        s = FONTE_SUBTITULO.render("Uma Nova História", True, DOURADO)
        self.screen.blit(s, s.get_rect(center=(cx, int(H * 0.26))))

        # Linha decorativa
        pygame.draw.line(self.screen, DOURADO_ESCURO,
                         (cx - 220, int(H * 0.31)), (cx + 220, int(H * 0.31)), 1)

        # Botões
        self.btn_historia.draw(self.screen)
        self.btn_personagem.draw(self.screen)
        self.btn_sair.draw(self.screen)

        # Dica F11
        hint = FONTE_MICRO.render("F11 – alternar tela cheia", True, CINZA_MEDIO)
        self.screen.blit(hint, (W - hint.get_width() - 12, H - hint.get_height() - 8))


if __name__ == "__main__":
    Game().run()
