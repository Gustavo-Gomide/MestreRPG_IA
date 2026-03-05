"""
states/loading.py  –  Tela de carregamento estilo jogo AAA.

Sequência:
  1. Fade-in do logo do dragão com partículas de chama
  2. Barra de progresso com mensagens temáticas
  3. Fade-out -> MENU
"""

import pygame
import os
import math
import random
import time
from settings import *


# Mensagens que aparecem na barra de carregamento
_MENSAGENS = [
    "Invocando os dragoes primordiais...",
    "Forjando o tecido do destino...",
    "Despertando antigas memorias...",
    "Consultando os oraculos...",
    "Atravessando os planos sombrios...",
    "Reunindo as forcas do caos...",
    "O chamado ecoa pelos reinos...",
]


class Particula:
    """Pequena partícula de brasa para o efeito de fogo ao redor do logo."""
    def __init__(self):
        self.reset()

    def reset(self):
        cx, cy = WIDTH // 2, HEIGHT // 2 - 40
        angle  = random.uniform(0, math.pi * 2)
        radius = random.uniform(80, 130)
        self.x     = cx + math.cos(angle) * radius
        self.y     = cy + math.sin(angle) * radius
        self.vx    = random.uniform(-0.4, 0.4)
        self.vy    = random.uniform(-1.8, -0.6)
        self.life  = random.uniform(0.6, 1.4)
        self.age   = 0.0
        r = random.randint(200, 255)
        g = random.randint(80, 160)
        self.color = (r, g, 20)
        self.size  = random.uniform(2, 5)

    def update(self, dt: float):
        self.age += dt
        self.x   += self.vx
        self.y   += self.vy
        self.vy  -= 0.02   # flutuação para cima

    @property
    def alive(self):
        return self.age < self.life

    def draw(self, surf):
        alpha = max(0.0, 1.0 - self.age / self.life)
        r, g, b = self.color
        col = (int(r * alpha), int(g * alpha), int(b * alpha))
        size = max(1, int(self.size * alpha))
        pygame.draw.circle(surf, col, (int(self.x), int(self.y)), size)


class LoadingScreen:
    DURACAO_TOTAL = 4.0   # segundos até avançar para MENU

    def __init__(self):
        # Carrega o logo
        self._logo_orig = None
        if os.path.exists(LOGO_PATH):
            try:
                img = pygame.image.load(LOGO_PATH).convert_alpha()
                # Escala para ~200x200 mantendo proporção
                w, h  = img.get_size()
                scale = 200 / max(w, h)
                self._logo_orig = pygame.transform.smoothscale(
                    img, (int(w * scale), int(h * scale))
                )
            except Exception:
                self._logo_orig = None

        self._start     = time.time()
        self._progress  = 0.0   # 0.0 → 1.0
        self._alpha     = 0.0   # para fade-in/out do logo
        self._msg_idx   = 0
        self._msg_timer = 0.0
        self._particulas: list[Particula] = [Particula() for _ in range(40)]
        self._done      = False

        # Superfície para o fade de toda a tela
        self._fade_surf = pygame.Surface((WIDTH, HEIGHT))
        self._fade_surf.fill(PRETO)

    def update(self) -> bool:
        """Retorna True quando a tela de carregamento terminou."""
        now  = time.time()
        t    = now - self._start
        frac = min(t / self.DURACAO_TOTAL, 1.0)

        self._progress = frac

        # Fade-in (0..0.3) e fade-out (0.75..1.0)
        if frac < 0.25:
            self._alpha = frac / 0.25
        elif frac > 0.80:
            self._alpha = 1.0 - (frac - 0.80) / 0.20
        else:
            self._alpha = 1.0

        # Troca mensagem a cada ~0.7 s
        self._msg_timer += 1 / FPS
        if self._msg_timer > 0.7:
            self._msg_timer  = 0.0
            self._msg_idx   = (self._msg_idx + 1) % len(_MENSAGENS)

        # Partículas
        dt = 1 / FPS
        for p in self._particulas:
            p.update(dt)
            if not p.alive:
                p.reset()

        if frac >= 1.0 and not self._done:
            self._done = True
            return True
        return False

    def draw(self, surface: pygame.Surface):
        surface.fill(PRETO)

        cx = WIDTH  // 2
        cy = HEIGHT // 2 - 40

        # ── Brilho radial de fundo (emanação do logo) ──────────────────
        glow_alpha = int(60 * self._alpha)
        glow_surf  = pygame.Surface((360, 360), pygame.SRCALPHA)
        for r in range(180, 0, -10):
            a = int(glow_alpha * (1 - r / 180))
            pygame.draw.circle(glow_surf, (*VERMELHO_SANGUE, a), (180, 180), r)
        surface.blit(glow_surf, (cx - 180, cy - 180))

        # ── Partículas de brasa ────────────────────────────────────────
        if self._alpha > 0.1:
            for p in self._particulas:
                p.draw(surface)

        # ── Logo ───────────────────────────────────────────────────────
        if self._logo_orig:
            logo = self._logo_orig.copy()
            logo.set_alpha(int(255 * self._alpha))
            rect = logo.get_rect(center=(cx, cy))
            surface.blit(logo, rect)
        else:
            # Fallback: apenas o texto do título
            t = FONTE_TITULO.render("MUNDOS", True, VERMELHO_SANGUE)
            t.set_alpha(int(255 * self._alpha))
            surface.blit(t, t.get_rect(center=(cx, cy)))

        # ── Título do jogo ─────────────────────────────────────────────
        titulo = FONTE_SUBTITULO.render("MUNDOS", True, DOURADO)
        titulo.set_alpha(int(220 * self._alpha))
        surface.blit(titulo, titulo.get_rect(center=(cx, cy + 135)))

        sub = FONTE_PEQUENA.render("U M A   N O V A   H I S T Ó R I A", True, CINZA_CLARO)
        sub.set_alpha(int(200 * self._alpha))
        surface.blit(sub, sub.get_rect(center=(cx, cy + 170)))

        # ── Barra de progresso estilo AAA ──────────────────────────────
        bar_w  = 480
        bar_h  = 6
        bar_x  = cx - bar_w // 2
        bar_y  = HEIGHT - 90

        # Trilho
        pygame.draw.rect(surface, CINZA_ESCURO,
                         pygame.Rect(bar_x - 1, bar_y - 1, bar_w + 2, bar_h + 2),
                         border_radius=4)
        # Preenchimento com brilho
        fill_w = int(bar_w * self._progress)
        if fill_w > 0:
            pygame.draw.rect(surface, DOURADO_ESCURO,
                             pygame.Rect(bar_x, bar_y, fill_w, bar_h),
                             border_radius=4)
            # Brilho na ponta
            glow_x = bar_x + fill_w - 6
            pygame.draw.rect(surface, DOURADO,
                             pygame.Rect(max(bar_x, glow_x), bar_y, 6, bar_h),
                             border_radius=4)

        # Porcentagem
        pct  = FONTE_MICRO.render(f"{int(self._progress * 100)}%", True, CINZA_CLARO)
        surface.blit(pct, (bar_x + bar_w + 10, bar_y - 2))

        # Mensagem temática
        msg  = FONTE_MICRO.render(_MENSAGENS[self._msg_idx], True, CINZA_CLARO)
        surface.blit(msg, msg.get_rect(center=(cx, bar_y - 22)))

        # ── Fade de entrada/saída ──────────────────────────────────────
        fade_alpha = int((1.0 - self._alpha) * 255)
        if fade_alpha > 0:
            self._fade_surf.set_alpha(fade_alpha)
            surface.blit(self._fade_surf, (0, 0))
