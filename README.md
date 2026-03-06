# Mundos: Uma Nova História

Motor de RPG de mesa com narração por **Inteligência Artificial**, construído com **Python + Pygame**.

> A ideia é simples: você cria o personagem, define a missão e a IA narra uma aventura única com começo, meio e fim, incluindo trilha sonora dinâmica, combate por turnos (em desenvolvimento) e painel lateral de jogo.
>
> Este projeto nasceu de uma aula de IA com o objetivo de entender IA. Se fizer um  **Fork** pode trocar as músicas, o prompt, as cores e o que mais quiser.

---

## Funcionalidades

| Área | Descrição |
|---|---|
| **Loading animado** | Partículas de brasa e logo com fade na abertura |
| **Janela responsiva** | Redimensionável a qualquer tamanho; F11 para tela cheia |
| **Criação de personagem** | Nome, raça e classe livres; a IA deduz atributos, inventário e habilidades (ainda arrumando)|
| **Modo História** | Chat com a IA (Groq); histórico salvo automaticamente a cada mensagem |
| **Arco narrativo** | A história tem início, meio e fim, pode escolher as opções que ela mostra no chat ou escrever sua própria.|
| **Replay** | Ao concluir, replaye com a mesma missão principal e histórico zerado permite criar uma nova história e como respostas são livres vai ser diferente. |
| **Painel lateral** | 5 abas: Fichas · Inventário · Missões · Batalha · Notas |
| **Combate por turnos** | Botões de ação rápida; barras de HP coloridas; inimigos (em desenvolvimento) |
| **Música dinâmica** | A IA troca a trilha via `<MUSIC>clima</MUSIC>` em tempo real (ainda com poucas opções) |
| **Efeitos sonoros** | Hover, clique, combate, level-up, chuva ambiente e mais |
| **Sistema de Loot** | A IA oferece itens via `<LOOT>`, jogador escolhe Pegar ou Ignorar (em desenvolvimento)|
| **Progressão de XP** | Level-up com novos títulos, habilidades e atributos expandidos (em desenvolvimento)|
| **Auto-save** | Cada mensagem salva; indicador de hora na interface (arquivo json)|
| **Modo offline** | Funciona sem chave Groq com respostas de demonstração (apenas para teste) |
| **Barra de título escura** | Integração com DWM do Windows para visual dark |

---

## Instalação rápida

```bash
# 1. Clone
git clone https://github.com/Gustavo-Gomide/MestreRPG_IA.git
cd MestreRPG_IA

# 2. Ambiente virtual
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / Mac

# 3. Dependências
pip install -r requirements.txt

# 4. Configure a API (opcional)
copy .env.example .env
# Edite .env e adicione:  GROQ_API_KEY=gsk_...
```

> **Sem chave Groq?** O jogo funciona normalmente em modo simulação com respostas pré-programadas, mas é bem ruim e só de teste.
> Obtenha a chave **gratuita** em [console.groq.com/keys](https://console.groq.com/keys).
> As histórias são dinâmicas e podem mudar seu tamanho a qualquer momento, dito isso não é exato, mas com o token gratuito consegui jogar 3 histórias +/- por dia.

```bash
# 5. Executar
python main.py
```

---

## Requisitos

| Dependência | Versão mínima |
|---|---|
| Python | 3.10+ |
| pygame | 2.6.0+ |
| groq | 0.4.0+ |
| python-dotenv | 1.0.0+ |

---

## Sistema de Áudio

Coloque arquivos em `assets/music/` (trilhas) e `assets/sfx/` (efeitos).
Formatos suportados: `.mp3` · `.ogg` · `.wav`

### Trilhas (`settings.py`)

| Constante | Arquivo padrão | Quando toca |
|---|---|---|
| `MUSIC_MENU` / `MUSIC_CHARACTER` / `MUSIC_LOADING` | `musica_principal.mp3` | Menus e loading |
| `MUSIC_STORY` | `exploration_suspense.mp3` | Padrão dentro de uma história |
| `MUSIC_EXPLORATION` | `exploration_suspense.mp3` | Viagem, dungeons, investigação |
| `MUSIC_FIGHT` | `figth.mp3` | Combate |
| `MUSIC_END` | `end.mp3` | Fim da campanha / morte |

Para usar arquivos diferentes, edite os caminhos em `settings.py`.

### Climas da tag `<MUSIC>` (`MUSIC_MAP`)

A IA insere `<MUSIC>clima</MUSIC>` para trocar a trilha durante a narração:

| Climas aceitos | Arquivo |
|---|---|
| `taverna` · `cidade` · `estalagem` · `conversa` · `descanso` · `paz` | `tavern.mp3` |
| `exploration` · `exploracao` · `floresta` · `dungeon` · `misterio` · `suspense` | `exploration_suspense.mp3` |
| `fight` · `combate` · `batalha` | `figth.mp3` |
| `end` · `fim` · `morte` · `conclusao` | `end.mp3` |

Adicione novos climas em `MUSIC_MAP` apontando para o arquivo desejado.

### Efeitos sonoros (`SFX_MAP`)

| Arquivo | Quando dispara |
|---|---|
| `button_hover.wav` | Mouse entra em qualquer botão |
| `select.wav` | Clique confirmado em qualquer botão |
| `exit.wav` | Fechar o programa pelo botão Sair |
| `battle_win.wav` | `<ENDBATTLE/>` — fim de combate |
| `hurt_damage.mp3` | `<DMGENEMY>` — dano em inimigo; dano no personagem |
| `level_up.wav` | `<UPDATE>` com `nivel` subindo — subida de nível |
| `weapon_attack.wav` | `<BATTLE>` — início de combate |
| `spell.wav` | `<SFX>magia</SFX>` pela IA |
| `rain.wav` | `<AMBIENT>chuva</AMBIENT>` — loop no canal 1 |

A IA pode disparar efeitos diretamente com `<SFX>nome</SFX>` (nomes: `ataque`, `magia`, `dano`, `level_up`).

---

## Tags especiais da IA

A narradora insere blocos que atualizam a interface em tempo real.

### `<MUSIC>` — Trocar trilha
```xml
<MUSIC>fight</MUSIC>
```

### `<SFX>` — Efeito sonoro one-shot
```xml
<SFX>magia</SFX>
```

### `<AMBIENT>` — Som ambiente em loop
```xml
<AMBIENT>chuva</AMBIENT>   <!-- inicia -->
<AMBIENT>stop</AMBIENT>    <!-- para -->
```
(Mecânicas de combate e relacionadas ainda em desenvolvimentoe correção)
### `<BATTLE>` / `<ENDBATTLE/>` — Combate
```xml
<BATTLE>[
  {"nome": "Goblin", "hp": 12, "hp_max": 12, "ataque": 5, "defesa": 2, "descricao": "Pequeno e sorrateiro"}
]</BATTLE>
```
→ Abre a aba **Batalha** com barras de HP + botões de ação rápida.
```xml
<ENDBATTLE/>
```
→ Limpa a aba e toca fanfarra de vitória.

### `<DMGENEMY>` — Aplicar dano a inimigo
```xml
<DMGENEMY idx="0" dmg="7"/>
```
→ Aplica 7 de dano ao primeiro inimigo da lista (atualiza a barra em tempo real).

### `<LOOT>` — Itens para o jogador escolher
```json
<LOOT>{"personagem_id": 1, "itens": [
  {"nome": "Espada de Fogo", "historia": "Forjada em lava viva.", "ataque": 15, "defesa": 0,
   "efeito_status": "Dano de fogo +1d6", "resistencia": "Frio"}
]}</LOOT>
```
→ Exibe botões **Pegar** / **Ignorar** na aba Inventário.

(Em ajuste e teste)
### `<QUEST>` — Missão no diário
```json
<QUEST>{"nome": "A Chave Perdida", "descricao": "Encontre a chave nas ruínas.", "status": "Ativa"}</QUEST>
```
Status: `"Ativa"`, `"Concluída"` ou `"Falhou"`.

(Em desenvolvimento)
### `<PUZZLE>` — Pistas de investigação
```json
<PUZZLE>{"titulo": "O Manuscrito", "pistas": ["Símbolo de olho", "Escrito em arcano"]}</PUZZLE>
```

(Em correção)
### `<UPDATE>` — Evolução de personagem
```json
<UPDATE>{"personagem_id": 1, "status": {"xp": 250, "nivel": 2, "hp_atual": 28},
 "novo_titulo": {"nome": "Sobrevivente", "descricao": "...", "beneficio": "+1 FOR"}}</UPDATE>
```
Campos suportados: `status`, `atributos`, `novo_titulo`, `adicionar_inventario`, `adicionar_habilidades`.

### `<ENDSTORY>` — Encerrar campanha
```xml
<ENDSTORY reason="O herói derrotou o dragão e salvou o reino."/>
```
→ Marca a história como concluída, para o som ambiente e toca `end.mp3`.

---

## Estrutura do projeto

```
MestreRPG_IA/
│
├── main.py                    # Loop principal, estados, F11 fullscreen
├── settings.py                # Constantes globais: cores, fontes, caminhos, áudio
├── database.py                # Persistência JSON (personagens + histórias)
├── ui.py                      # Componentes: Button, TextInput, ContentArea…
├── requirements.txt           # Dependências Python
│
├── states/
│   ├── loading.py             # Tela de loading animada com partículas
│   ├── character_creation.py  # Criar / editar / ver detalhes de personagens
│   └── story.py               # Modo história: lista, nova campanha, chat + painel
│
├── assets/
│   ├── dragon.png             # Ícone da janela e logo de loading
│   ├── music/                 # Trilhas sonoras
│   │   ├── musica_principal.mp3
│   │   ├── tavern.mp3
│   │   ├── exploration_suspense.mp3
│   │   ├── figth.mp3
│   │   └── end.mp3
│   └── sfx/                   # Efeitos sonoros
│       ├── button_hover.wav
│       ├── select.wav
│       ├── exit.wav
│       ├── battle_win.wav
│       ├── hurt_damage.mp3
│       ├── level_up.wav
│       ├── rain.wav
│       ├── spell.wav
│       └── weapon_attack.wav
│
├── data/
│   ├── personagens.json       # Personagens criados (excluído do git)
│   └── historias.json         # Campanhas e histórico de chat (excluído do git)
│       └── saves/             # Backups automáticos (excluído do git)
│
├── .env                       # GROQ_API_KEY=gsk_... (não versionar!)
└── .env.example               # Modelo de configuração
```

---

## Customização

### Mudar nome e visual
- **Título:** `main.py` → `_draw_menu()` e `pygame.display.set_caption()`
- **Ícone:** substitua `assets/dragon.png` (recomendado: 512×512 px, fundo transparente)
- **Cores:** bloco `# Cores` em `settings.py`
- **Fontes:** bloco `# Fontes` em `settings.py`

(Pode só criar uma campanha nova passando a missão que ela terá de intro, mas para mais ajustes pode mudar o arquivo)
### Mudar o universo da história
Em `states/story.py → _build_system_prompt()`, edite as primeiras linhas do array `partes`:
```python
partes = [
    "Você é um narrador de ficção científica sombria.",
    "O mundo se chama Nexus-7. Toda magia tem um custo em anos de vida.",
    ...
]
```

### Trocar o modelo de IA
Em `states/story.py → _chamar_groq()` e `states/character_creation.py → _chamar_groq_personagem()`:
```python
model="llama-3.3-70b-versatile"   # troque pelo modelo desejado
```
Modelos Groq disponíveis: `llama-3.3-70b-versatile` · `llama3-70b-8192` · `llama3-8b-8192` · `mixtral-8x7b-32768`

---

## Atalhos de teclado

| Tecla | Ação |
|---|---|
| `F11` | Alternar tela cheia / janela |
| `Enter` | Enviar mensagem no chat |
| `Scroll` | Rolar chat, listas e campos de texto |
| `←` `→` | Mover cursor nos campos de texto (letra por letra)|
| `Backspace` / `Delete` | Editar texto nos campos |

---

## Configurando a API do Groq (IA)

O jogo usa o [Groq](https://groq.com) como motor de IA para a narração. A chave é **gratuita** e leva menos de 2 minutos para obter.

**Passo a passo:**

1. Acesse [console.groq.com/keys](https://console.groq.com/keys) e crie uma conta (pode usar o Google)
2. Clique em **"Create API Key"**, dê um nome qualquer e copie a chave gerada (`gsk_...`)
3. Na pasta do projeto, copie o arquivo de exemplo:
   ```bash
   copy .env.example .env   # Windows
   # cp .env.example .env   # Linux / Mac
   ```
4. Abra o `.env` em qualquer editor de texto e cole sua chave:
   ```env
   GROQ_API_KEY=gsk_SUA_CHAVE_AQUI
   ```
5. Salve o arquivo e rode o jogo normalmente com `python main.py`

> **Sem chave?** O jogo continua funcionando em **modo simulação** com respostas pré-programadas, é útil para testar a interface sem precisar de internet, mas é sempre a mesma coisa e sem muita qualidade (recomendado usar api).

---

## Contribuindo

1. Fork o repositório
2. Crie um branch: `git checkout -b feature/minha-feature`
3. Commit suas mudanças: `git commit -m "feat: minha feature"`
4. Push: `git push origin feature/minha-feature`
5. Abra um Pull Request

---

## Licença

[MIT](LICENSE) — uso livre para projetos pessoais e comerciais. Créditos apreciados.

---

*Mundos: Uma Nova História, motor de RPG básico com IA feito por Gustavo · powered by [Groq](https://groq.com) + [Pygame](https://pygame.org)*
