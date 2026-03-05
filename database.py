"""
database.py  –  Persistência de dados (JSON) do jogo.

Estrutura de um personagem:
{
    "id": int,
    "nome": str,
    "raca": str,
    "classe": str,
    "historia": str,
    "titulo_ativo": str,
    "titulos_desbloqueados": [
        { "nome": str, "descricao": str, "beneficio": str }
    ],
    "atributos": {
        "forca": int, "destreza": int, "inteligencia": int,
        "constituicao": int, "sabedoria": int, "carisma": int
    },
    "status": {
        "hp_atual": int, "hp_maximo": int,
        "mana_atual": int, "mana_maximo": int,
        "nivel": int, "xp": int
    },
    "inventario": [
        {
            "nome": str,
            "historia": str,
            "ataque": int | str,
            "defesa": int | str,
            "efeito_status": str,
            "resistencia": str
        }
    ],
    "habilidades": [
        { "nome": str, "custo": str, "efeito": str, "recarga": str }
    ]
}

Estrutura de uma história/campanha:
{
    "id": int,
    "titulo": str,
    "descricao": str,
    "tags": list[str],
    "personagem_ids": list[int],
    "historico_chat": list[dict]   <- mensagens da API para 'continuar'
}
"""

import json
import os

DATA_DIR           = "data"
PERSONAGENS_FILE   = os.path.join(DATA_DIR, "personagens.json")
HISTORIAS_FILE     = os.path.join(DATA_DIR, "historias.json")


# ── Utilitários internos ────────────────────────────────────────────────────

def _ensure():
    """Cria o diretório `data/` se ele ainda não existir."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def _load(path: str) -> list:
    """
    Lê um arquivo JSON e retorna uma lista Python.
    Retorna lista vazia se o arquivo não existe, está corrompido ou vazio.
    Nunca lança exceção para o chamador.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

def _save(path: str, data):
    """
    Serializa `data` em JSON formatado (indent=4, Unicode não escapado)
    e grava em `path`. Cria o diretório `data/` se necessário.
    """
    _ensure()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ── Personagens ─────────────────────────────────────────────────────────────

def load_characters() -> list[dict]:
    """Retorna todos os personagens salvos."""
    return _load(PERSONAGENS_FILE)


def save_character(
    nome: str,
    raca: str,
    classe: str,
    historia: str,
    atributos: dict,
    status: dict,
    titulo: dict,
    inventario: list[dict],
    habilidades: list[dict],
) -> int:
    """
    Salva novo personagem com estrutura completa.
    Retorna o id gerado.

    `titulo`     -> {"nome": str, "descricao": str, "beneficio": str}
    `inventario` -> lista de dicts com nome/historia/ataque/defesa/efeito_status/resistencia
    `habilidades`-> lista de dicts com nome/custo/efeito/recarga
    """
    chars = load_characters()
    new_id = (chars[-1]["id"] + 1) if chars else 1

    char = {
        "id": new_id,
        "nome": nome,
        "raca": raca,
        "classe": classe,
        "historia": historia,
        "titulo_ativo": titulo.get("nome", "Sem Titulo"),
        "titulos_desbloqueados": [titulo],
        "atributos": atributos,
        "status": {
            "hp_atual":   status.get("hp_maximo", 30),
            "hp_maximo":  status.get("hp_maximo", 30),
            "mana_atual": status.get("mana_maximo", 10),
            "mana_maximo":status.get("mana_maximo", 10),
            "nivel":      status.get("nivel", 1),
            "xp":         0,
        },
        "inventario":  inventario,
        "habilidades": habilidades,
    }

    chars.append(char)
    _save(PERSONAGENS_FILE, chars)
    return new_id


def delete_character(char_id: int):
    chars = load_characters()
    _save(PERSONAGENS_FILE, [c for c in chars if c["id"] != char_id])


def update_character_name_title(char_id: int, novo_nome: str, novo_titulo_nome: str):
    """Muda apenas o nome e o título ativo (sem alterar nada mais)."""
    chars = load_characters()
    for c in chars:
        if c["id"] == char_id:
            c["nome"] = novo_nome
            c["titulo_ativo"] = novo_titulo_nome
            break
    _save(PERSONAGENS_FILE, chars)


def update_character_after_session(char_id: int, patch: dict):
    """
    Aplica um patch de atualização pós-sessão enviado pela IA.
    O patch pode conter qualquer subconjunto dos campos do personagem:
    atributos, status, raca, classe, novo titulo, inventario, habilidades, etc.
    """
    chars = load_characters()
    for c in chars:
        if c["id"] == char_id:
            # Atributos e status fazem merge recursivo
            for key in ("atributos", "status"):
                if key in patch:
                    c.setdefault(key, {}).update(patch.pop(key))
            # Novo título desbloqueado?
            if "novo_titulo" in patch:
                t = patch.pop("novo_titulo")
                nomes_existentes = [x["nome"] for x in c.get("titulos_desbloqueados", [])]
                if t.get("nome") not in nomes_existentes:
                    c.setdefault("titulos_desbloqueados", []).append(t)
            # Novos itens no inventário?
            if "adicionar_inventario" in patch:
                c.setdefault("inventario", []).extend(patch.pop("adicionar_inventario"))
            # Novas habilidades?
            if "adicionar_habilidades" in patch:
                c.setdefault("habilidades", []).extend(patch.pop("adicionar_habilidades"))
            # Campos simples (nome, raca, classe, titulo_ativo...)
            c.update(patch)
            break
    _save(PERSONAGENS_FILE, chars)


# ── Histórias ───────────────────────────────────────────────────────────────

def load_stories() -> list[dict]:
    return _load(HISTORIAS_FILE)


def save_story(titulo: str, descricao: str, tags: list[str],
               personagem_ids: list[int],
               missao_principal: str = "") -> int:
    """Salva nova campanha. missao_principal é o gancho narrativo central."""
    stories = load_stories()
    new_id  = (stories[-1]["id"] + 1) if stories else 1
    story = {
        "id": new_id,
        "titulo": titulo,
        "descricao": descricao,
        "missao_principal": missao_principal,
        "tags": tags,
        "personagem_ids": personagem_ids,
        "concluida": False,
        "conclusao_texto": "",
        "historico_chat": [],
    }
    stories.append(story)
    _save(HISTORIAS_FILE, stories)
    return new_id


def complete_story(story_id: int, conclusao_texto: str = ""):
    """Marca uma história como concluída."""
    stories = load_stories()
    for s in stories:
        if s["id"] == story_id:
            s["concluida"]       = True
            s["conclusao_texto"] = conclusao_texto
            break
    _save(HISTORIAS_FILE, stories)


def append_chat_message(story_id: int, role: str, content: str):
    """Adiciona uma mensagem ao histórico de chat de uma história."""
    stories = load_stories()
    for s in stories:
        if s["id"] == story_id:
            s.setdefault("historico_chat", []).append(
                {"role": role, "content": content}
            )
            break
    _save(HISTORIAS_FILE, stories)


def get_story_chat(story_id: int) -> list[dict]:
    for s in load_stories():
        if s["id"] == story_id:
            return s.get("historico_chat", [])
    return []
