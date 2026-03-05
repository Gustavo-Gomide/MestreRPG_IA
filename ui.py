"""
ui.py  –  Componentes visuais reutilizáveis do jogo.

Classes exportadas:
  Button              – Botão simples com hover, clique e som automático.
  TextInput           – Campo de texto de linha única com cursor animado.
  MultilineTextInput  – Área de texto multilinha com scroll e cursor.
  CycleButton         – Botão "spinner" que cicla numa lista de opções.
  Dropdown            – Menu suspenso com scroll interno.
  ContentArea         – Área com clipping e rolagem para listas longas.

Função utilitária:
  draw_text_wrapped() – Renderiza texto com quebra automática de linha.

Convenção de coordenadas:
  Todos os widgets usam coordenadas absolutas de tela, EXCETO quando estão
  dentro de um ContentArea – nesse caso recebem coordenadas relativas
  (convertidas por ContentArea.get_adjusted_event).
"""

import pygame
from settings import *


class Button:
    """
    Botão retangular com feedback visual de hover, som automático e evento de clique.

    Parâmetros:
        x, y          – posição superior-esquerda na tela (pixels).
        width, height – dimensões do retângulo clicável.
        text          – rótulo exibido centralizado no botão.
        font          – pygame.font.Font a usar (padrão: FONTE_TEXTO do settings).
        color         – cor de fundo quando não hover.
        hover_color   – cor de fundo quando o mouse está sobre o botão.
        text_color    – cor do texto.

    Comportamento de som:
        - Hover  → play_sfx(SFX_BUTTON_HOVER) disparado em draw() via posição real
          do mouse (não depende de MOUSEMOTION; funciona mesmo em 60 fps).
        - Clique → play_sfx(SFX_SELECT) disparado em handle_event().

    Nota: _prev_screen_hv evita repetir o som de hover a cada frame enquanto
    o mouse permanece parado sobre o botão.
    """
    def __init__(self, x, y, width, height, text, font=FONTE_TEXTO, color=CINZA_ESCURO, hover_color=VERMELHO_HOVER, text_color=BRANCO):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.is_hovered = False
        # Flag separada para o som — usa pygame.mouse.get_pos() em draw()
        # (não sobrescreve is_hovered, que ainda serve para botões dentro de ContentArea)
        self._prev_screen_hv = False

    def draw(self, surface: pygame.Surface) -> None:
        """
        Renderiza o botão na superfície fornecida.

        Etapas:
          1. Verifica colisão mouse↔rect para detectar hover (usa posição real do mouse,
             não a do último MOUSEMOTION – mais confiável em layouts dinâmicos).
          2. Dispara SFX_BUTTON_HOVER na borda de entrada (leading edge).
          3. Pinta fundo com hover_color ou color conforme is_hovered.
          4. Desenha borda dourada de 2px.
          5. Centraliza e renderiza o texto.
        """
        # Som de hover: detectado via posição real do mouse, 60× por segundo.
        # Funciona para botões com posição absoluta (menu, nav, enviar, etc.).
        # Para botões dentro de ContentArea o rect é local; screen_hv pode divergir —
        # isso é aceitável porque list-items não precisam de som de hover.
        screen_hv = self.rect.collidepoint(pygame.mouse.get_pos())
        if screen_hv and not self._prev_screen_hv:
            play_sfx(SFX_BUTTON_HOVER, volume=0.8)
        self._prev_screen_hv = screen_hv

        # Hover visual via is_hovered (atualizado em handle_event para todos os botões)
        current_color = self.hover_color if self.is_hovered else self.color

        pygame.draw.rect(surface, current_color, self.rect, border_radius=8)
        pygame.draw.rect(surface, DOURADO, self.rect, width=2, border_radius=8) # Borda

        text_surf = self.font.render(self.text, True, self.text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """
        Processa eventos de mouse para este botão.

        Retorna True apenas quando o botão é clicado (MOUSEBUTTONDOWN, botão 1).
        Deve ser chamado a cada frame dentro do loop de eventos do estado pai.

        MOUSEMOTION  → atualiza is_hovered (usado para cor visual).
        MOUSEBUTTONDOWN → se is_hovered, toca SFX_SELECT e retorna True.

        Nota: o som de *hover* é tocado em draw(), não aqui — isso evita perder
        o som em botões dentro de ContentArea, cujos eventos têm coords ajustadas.
        """
        # Atualiza is_hovered para todos os botões (inclusive os dentro de ContentArea
        # que recebem 'ev' com coordenadas ajustadas — o som de hover usa draw()).
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.is_hovered:
                play_sfx(SFX_SELECT, volume=0.6)
                return True
        return False

import time


class TextInput:
    """
    Campo de texto de linha única com cursor piscante e suporte a acentuação.

    Usa pygame.TEXTINPUT (em vez de KEYDOWN.unicode) para capturar corretamente
    caracteres compostos (acentos, cedilha, etc.) via IME do sistema operacional.

    Parâmetros:
        x, y          – posição superior-esquerda.
        width, height – dimensões da caixa.
        font          – fonte a usar para renderizar o texto.
        text_color    – cor do texto digitado e do cursor.
        bg_color      – cor de fundo da caixa.
        active_color  – cor da borda quando a caixa está ativa (em foco).

    Atributos públicos:
        text       – string atual digitada pelo usuário.
        cursor_pos – índice de inserção (0 = antes do primeiro caractere).
        is_active  – True quando a caixa está com foco (recebe teclado).
    """
    def __init__(self, x, y, width, height, font=FONTE_TEXTO, text_color=BRANCO, bg_color=CINZA_ESCURO, active_color=DOURADO):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = ""
        self.cursor_pos = 0 # Onde o cursor está piscando
        self.font = font
        self.text_color = text_color
        self.bg_color = bg_color
        self.active_color = active_color
        self.is_active = False
        self.cursor_visible = True
        self.last_cursor_toggle = time.time()

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.is_active = self.rect.collidepoint(event.pos)

        if not self.is_active:
            return False

        # Captura de Teclas Especiais (Setinhas, Backspace, Enter)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                return True
            elif event.key == pygame.K_BACKSPACE:
                if self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos-1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
            elif event.key == pygame.K_DELETE:
                if self.cursor_pos < len(self.text):
                    self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos+1:]
            elif event.key == pygame.K_LEFT:
                self.cursor_pos = max(0, self.cursor_pos - 1)
            elif event.key == pygame.K_RIGHT:
                self.cursor_pos = min(len(self.text), self.cursor_pos + 1)
                
        # Captura de Texto Processado (Resolve TODOS os problemas de acentuação automaticamente)
        elif event.type == pygame.TEXTINPUT:
            self.text = self.text[:self.cursor_pos] + event.text + self.text[self.cursor_pos:]
            self.cursor_pos += len(event.text)

        return False

    def draw(self, surface):
        current_border_color = self.active_color if self.is_active else CINZA_CLARO

        pygame.draw.rect(surface, self.bg_color, self.rect, border_radius=5)
        pygame.draw.rect(surface, current_border_color, self.rect, width=2, border_radius=5)

        # Renderiza o texto
        text_surface = self.font.render(self.text, True, self.text_color)
        surface.blit(text_surface, (self.rect.x + 10, self.rect.y + (self.rect.height - text_surface.get_height()) // 2))

        # Renderiza o Cursor na posição correta
        if self.is_active:
            if time.time() - self.last_cursor_toggle > 0.5:
                self.cursor_visible = not self.cursor_visible
                self.last_cursor_toggle = time.time()
            
            if self.cursor_visible:
                # Calcula a largura do texto até a posição do cursor para desenhar a barrinha
                texto_ate_cursor = self.text[:self.cursor_pos]
                largura_cursor = self.font.size(texto_ate_cursor)[0]
                
                cursor_x = self.rect.x + 10 + largura_cursor + 2
                cursor_y_start = self.rect.y + 10
                cursor_y_end = self.rect.y + self.rect.height - 10
                pygame.draw.line(surface, self.text_color, (cursor_x, cursor_y_start), (cursor_x, cursor_y_end), 2)

def draw_text_wrapped(surface, text, font, color, x, y, max_width):
    """
    Desenha um texto quebrando as linhas automaticamente se passar do max_width.
    Retorna a altura total (y) que o texto ocupou, útil para empilhar textos.
    """
    words = text.split(' ')
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        # Testa se a linha com a nova palavra cabe na largura máxima
        if font.size(test_line)[0] <= max_width:
            current_line.append(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
    lines.append(' '.join(current_line))
    
    y_offset = 0
    for line in lines:
        text_surface = font.render(line, True, color)
        surface.blit(text_surface, (x, y + y_offset))
        y_offset += font.get_linesize() + 5 # +5 para dar um respiro entre as linhas
        
    return y_offset

class CycleButton(Button):
    """
    Um botão que funciona como um 'Spinner'. Cada clique avança para a próxima opção da lista.
    """
    def __init__(self, x, y, width, height, options_list, current_option=""):
        super().__init__(x, y, width, height, "")
        self.options = options_list if options_list else ["Nenhum"]
        
        # Tenta achar o índice da opção atual, senão começa no 0
        try:
            self.index = self.options.index(current_option)
        except ValueError:
            self.index = 0
            
        self.text = f"< {self.options[self.index]} >"

    def handle_event(self, event):
        # Se clicar no botão, avança o índice da lista
        if super().handle_event(event):
            self.index = (self.index + 1) % len(self.options)
            self.text = f"< {self.options[self.index]} >"
            return True
        return False
        
    def get_current_value(self):
        return self.options[self.index]

class MultilineTextInput:
    """Caixa de texto com quebra de linha, auto-scroll do cursor e scroll com roda do mouse."""
    def __init__(self, x, y, width, height, font=FONTE_TEXTO, text_color=BRANCO, bg_color=CINZA_ESCURO, active_color=DOURADO):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = ""
        self.font = font
        self.text_color = text_color
        self.bg_color = bg_color
        self.active_color = active_color
        self.is_active = False
        self.cursor_visible = True
        self.last_cursor_toggle = time.time()
        self.scroll_offset = 0 
        self.cursor_pos = 0 

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # Usa event.pos que já vem ajustado pelo painel
                self.is_active = self.rect.collidepoint(event.pos)
                if self.is_active:
                    self.cursor_visible = True
                    self.last_cursor_toggle = time.time()

        # Se a caixa estiver clicada (ativa), a roda do mouse rola APENAS o texto interno
        if event.type == pygame.MOUSEWHEEL:
            if self.is_active:
                self.scroll_offset -= event.y 
                return True # Avisa que consumiu o evento de rolagem

        if not self.is_active: 
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                if self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos-1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
            elif event.key == pygame.K_DELETE:
                if self.cursor_pos < len(self.text):
                    self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos+1:]
            elif event.key == pygame.K_LEFT:
                self.cursor_pos = max(0, self.cursor_pos - 1)
            elif event.key == pygame.K_RIGHT:
                self.cursor_pos = min(len(self.text), self.cursor_pos + 1)
            elif event.key == pygame.K_RETURN:
                self.text = self.text[:self.cursor_pos] + " " + self.text[self.cursor_pos:]
                self.cursor_pos += 1
        elif event.type == pygame.TEXTINPUT:
            self.text = self.text[:self.cursor_pos] + event.text + self.text[self.cursor_pos:]
            self.cursor_pos += len(event.text)

        return False

    def wrap_text(self):
        words = self.text.split(' ')
        lines = []
        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            if self.font.size(test_line)[0] <= self.rect.width - 20: 
                current_line.append(word)
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        if not lines:
            lines = [""]
        return lines

    def get_cursor_draw_position(self, lines):
        char_count = 0
        for line_idx, line in enumerate(lines):
            line_len = len(line)
            if char_count + line_len >= self.cursor_pos:
                chars_in_this_line = self.cursor_pos - char_count
                text_before_cursor = line[:chars_in_this_line]
                cursor_x = self.rect.x + 10 + self.font.size(text_before_cursor)[0]
                return cursor_x, line_idx
            char_count += line_len + 1 
        last_line = lines[-1] if lines else ""
        return self.rect.x + 10 + self.font.size(last_line)[0], len(lines) - 1

    def draw(self, surface):
        current_border_color = self.active_color if self.is_active else CINZA_CLARO
        pygame.draw.rect(surface, self.bg_color, self.rect, border_radius=5)
        pygame.draw.rect(surface, current_border_color, self.rect, width=2, border_radius=5)

        lines = self.wrap_text()
        line_height = self.font.get_linesize()
        max_lines = (self.rect.height - 20) // line_height 

        # --- AUTO-SCROLL DO CURSOR ---
        # Se você usar as setas, o texto sobe/desce sozinho para acompanhar o cursor
        if self.is_active:
            _, cursor_line_idx = self.get_cursor_draw_position(lines)
            if cursor_line_idx < self.scroll_offset:
                self.scroll_offset = cursor_line_idx
            elif cursor_line_idx >= self.scroll_offset + max_lines:
                self.scroll_offset = cursor_line_idx - max_lines + 1

        # Trava limites do scroll manual
        max_scroll = max(0, len(lines) - max_lines)
        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))

        lines_to_draw = lines[self.scroll_offset : self.scroll_offset + max_lines]

        y_offset = self.rect.y + 10
        for line in lines_to_draw:
            text_surf = self.font.render(line, True, self.text_color)
            surface.blit(text_surf, (self.rect.x + 10, y_offset))
            y_offset += line_height

        # --- DESENHA A BARRINHA DE ROLAGEM VISUAL ---
        if len(lines) > max_lines:
            scroll_ratio = max_lines / len(lines)
            bar_height = max(10, self.rect.height * scroll_ratio)
            scroll_pos = (self.scroll_offset / (len(lines) - max_lines)) * (self.rect.height - bar_height)
            bar_rect = pygame.Rect(self.rect.right - 8, self.rect.y + scroll_pos, 6, bar_height)
            pygame.draw.rect(surface, (100, 100, 110), bar_rect, border_radius=3)

        # Desenha Cursor
        if self.is_active:
            if time.time() - self.last_cursor_toggle > 0.5:
                self.cursor_visible = not self.cursor_visible
                self.last_cursor_toggle = time.time()
                
            if self.cursor_visible:
                cursor_x, cursor_line_idx = self.get_cursor_draw_position(lines)
                if self.scroll_offset <= cursor_line_idx < self.scroll_offset + max_lines:
                    visible_line_idx = cursor_line_idx - self.scroll_offset
                    cursor_y = self.rect.y + 10 + (visible_line_idx * line_height)
                    pygame.draw.line(surface, self.text_color, (cursor_x, cursor_y), (cursor_x, cursor_y + line_height - 4), 2)
                                     
class Dropdown:
    """Menu suspenso com suporte a rolagem (overflow: auto) para listas longas."""
    def __init__(self, x, y, width, height, options, current_option="", font=FONTE_TEXTO):
        self.rect = pygame.Rect(x, y, width, height)
        self.options = options if options else ["Nenhum"]
        try:
            self.index = self.options.index(current_option)
        except ValueError:
            self.index = 0
        self.is_open = False
        self.font = font
        
        # Sistema de Scroll Interno da Lista
        self.scroll_y = 0
        self.max_list_height = 200 # Altura máxima que a lista aberta pode ter
        self.option_height = height

    def handle_event(self, event):
        # Controle de Scroll quando aberto
        if self.is_open and event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            list_rect = pygame.Rect(self.rect.x, self.rect.bottom, self.rect.width, self.max_list_height)
            # Se o mouse não tiver pos (alguns eventos ajustados não têm), assumimos True se estiver aberto
            if not hasattr(event, 'pos') or list_rect.collidepoint(getattr(event, 'pos', mouse_pos)):
                self.scroll_y -= event.y * 20
                max_scroll = max(0, (len(self.options) * self.option_height) - self.max_list_height)
                self.scroll_y = max(0, min(self.scroll_y, max_scroll))
                return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.is_open:
                # Calcula em qual opção clicamos considerando o scroll
                click_y = event.pos[1] - self.rect.bottom + self.scroll_y
                if 0 <= click_y <= len(self.options) * self.option_height and event.pos[0] >= self.rect.x and event.pos[0] <= self.rect.right:
                    # Verifica se clicou dentro da área visível da lista (clip)
                    if event.pos[1] <= self.rect.bottom + self.max_list_height:
                        clicked_index = int(click_y // self.option_height)
                        if 0 <= clicked_index < len(self.options):
                            self.index = clicked_index
                            self.is_open = False
                            return True
                
                # Se clicou fora da lista, fecha
                self.is_open = False
                return self.rect.collidepoint(event.pos)
            
            elif self.rect.collidepoint(event.pos):
                self.is_open = True
                self.scroll_y = 0 # Reseta o scroll ao abrir
                return True
        return False

    def get_current_value(self):
        return self.options[self.index]

    def draw_main(self, surface):
        """Desenha apenas a caixa principal fechada."""
        pygame.draw.rect(surface, (40, 40, 45), self.rect, border_radius=5)
        pygame.draw.rect(surface, CINZA_CLARO, self.rect, width=2, border_radius=5)
        text = self.font.render(self.options[self.index], True, BRANCO)
        surface.blit(text, (self.rect.x + 10, self.rect.y + (self.rect.height - text.get_height()) // 2))
        
        # Setinha para baixo
        pygame.draw.polygon(surface, DOURADO, [(self.rect.right - 20, self.rect.centery - 5), (self.rect.right - 10, self.rect.centery - 5), (self.rect.right - 15, self.rect.centery + 5)])

    def draw_options(self, surface):
        """Desenha a lista suspensa com clip (corte) para não vazar a altura máxima."""
        if not self.is_open:
            return

        total_height = len(self.options) * self.option_height
        visible_height = min(total_height, self.max_list_height)
        
        # Cria uma superfície virtual apenas para a lista
        list_surf = pygame.Surface((self.rect.width, visible_height), pygame.SRCALPHA)
        list_surf.fill((30, 30, 35, 255))
        
        # Desenha as opções respeitando o scroll_y
        for i, option in enumerate(self.options):
            opt_y = (i * self.option_height) - self.scroll_y
            # Só desenha se estiver visível para otimizar
            if opt_y + self.option_height > 0 and opt_y < visible_height:
                opt_rect = pygame.Rect(0, opt_y, self.rect.width, self.option_height)
                pygame.draw.rect(list_surf, DOURADO, opt_rect, width=1)
                text = self.font.render(option, True, BRANCO)
                list_surf.blit(text, (10, opt_y + (self.option_height - text.get_height()) // 2))

        # Cola a lista na tela principal
        surface.blit(list_surf, (self.rect.x, self.rect.bottom))

        # Barra de rolagem interna do Dropdown
        if total_height > visible_height:
            scroll_ratio = visible_height / total_height
            bar_height = max(10, visible_height * scroll_ratio)
            scroll_pos = (self.scroll_y / (total_height - visible_height)) * (visible_height - bar_height)
            bar_rect = pygame.Rect(self.rect.right - 8, self.rect.bottom + scroll_pos, 6, bar_height)
            pygame.draw.rect(surface, DOURADO, bar_rect, border_radius=3)

class ContentArea:
    """
    Área de envelopamento com scroll dinâmico. 
    Itens desenhados aqui dentro não vazam da tela e ganham rolagem automática.
    """
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)
        self.scroll_y = 0
        self.content_height = height # Atualizado dinamicamente pelo dev
        
    def handle_event(self, event):
        """Lida com a rolagem do mouse"""
        if event.type == pygame.MOUSEWHEEL:
            if self.rect.collidepoint(pygame.mouse.get_pos()):
                self.scroll_y -= event.y * 35 # Velocidade do Scroll
                self.clamp()
                return True
        return False

    def clamp(self):
        max_scroll = max(0, self.content_height - self.rect.height)
        self.scroll_y = max(0, min(self.scroll_y, max_scroll))

    def get_adjusted_event(self, event):
        """
        Traduz as coordenadas da tela para as coordenadas virtuais de dentro da caixa.
        Use isso ao repassar eventos para botões que estão dentro do ContentArea.
        """
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            if event.type == pygame.MOUSEBUTTONDOWN and not self.rect.collidepoint(event.pos):
                return None # Ignora cliques fora da área
                
            # Converte X e Y para o "mundo interno" do Scroll
            new_x = event.pos[0] - self.rect.x
            new_y = event.pos[1] - self.rect.y + self.scroll_y
            return pygame.event.Event(event.type, {'pos': (new_x, new_y), 'button': getattr(event, 'button', 1)})
        return event

    def draw(self, screen, draw_func):
        """
        Executa a função de desenho numa superfície virtual e corta (clip) na tela.
        """
        self.clamp()
        total_h = max(self.rect.height, self.content_height)
        
        # Cria um "Quadro em Branco" virtual com a altura total do conteúdo
        content_surf = pygame.Surface((self.rect.width, total_h), pygame.SRCALPHA)
        content_surf.fill((0,0,0,0)) 
        
        # Chama a função que desenha os botões/textos passando o quadro virtual
        draw_func(content_surf)
        
        # Recorta apenas a parte visível baseada na rolagem e cola na tela principal
        clip_rect = pygame.Rect(0, self.scroll_y, self.rect.width, self.rect.height)
        screen.blit(content_surf, (self.rect.x, self.rect.y), clip_rect)
        
        # Barra de Rolagem Visual Dourada
        if self.content_height > self.rect.height:
            scroll_ratio = self.rect.height / self.content_height
            bar_height = max(30, self.rect.height * scroll_ratio)
            scroll_pos = (self.scroll_y / (self.content_height - self.rect.height)) * (self.rect.height - bar_height)
            
            bar_rect = pygame.Rect(self.rect.right - 12, self.rect.y + scroll_pos, 8, bar_height)
            pygame.draw.rect(screen, (218, 165, 32), bar_rect, border_radius=4) # DOURADO